"""
Scriber — Active Application Context Detector
Detects frontmost macOS application using bundle identifiers and WindowServer layers
to enable smart context-aware dictation without getting stuck or fooled by helper processes.
"""

import os
import subprocess
from AppKit import NSWorkspace, NSRunningApplication
from Foundation import NSRunLoop, NSDate
import Quartz

# Immutable reverse-DNS Bundle Identifier mapping
# This eliminates ambiguity where Electron apps report 'Electron' at process level
BUNDLE_ID_MAP = {
    # IDEs, Code Editors & Terminals
    "com.google.antigravity-ide": ("Antigravity", "code", "💻"),
    "com.microsoft.VSCode": ("VS Code", "code", "💻"),
    "com.microsoft.VSCodeInsiders": ("VS Code", "code", "💻"),
    "com.todesktop.230313mzl4w4u92": ("Cursor", "code", "💻"),
    "com.apple.dt.Xcode": ("Xcode", "code", "💻"),
    "com.apple.Terminal": ("Terminal", "code", "💻"),
    "com.googlecode.iterm2": ("iTerm", "code", "💻"),
    "dev.warp.Warp-Stable": ("Warp", "code", "💻"),
    "com.mitchellh.ghostty": ("Ghostty", "code", "💻"),
    "com.sublimetext.4": ("Sublime", "code", "💻"),
    "com.jetbrains.pycharm": ("PyCharm", "code", "💻"),
    "com.jetbrains.intellij": ("IntelliJ", "code", "💻"),
    "com.jetbrains.WebStorm": ("WebStorm", "code", "💻"),
    "com.jetbrains.CLion": ("CLion", "code", "💻"),
    "dev.zed.Zed": ("Zed", "code", "💻"),

    # Web Browsers
    "com.brave.Browser": ("Brave", "browser", "🌐"),
    "com.google.Chrome": ("Chrome", "browser", "🌐"),
    "com.google.Chrome.canary": ("Chrome Canary", "browser", "🌐"),
    "com.apple.Safari": ("Safari", "browser", "🌐"),
    "company.thebrowser.Browser": ("Arc", "browser", "🌐"),
    "org.mozilla.firefox": ("Firefox", "browser", "🌐"),
    "com.microsoft.edgemac": ("Edge", "browser", "🌐"),
    "com.operasoftware.Opera": ("Opera", "browser", "🌐"),
    "com.vivaldi.Vivaldi": ("Vivaldi", "browser", "🌐"),
    "at.studio.AsideBrowser": ("Aside", "browser", "🌐"),
    "app.zen-browser.zen": ("Zen Browser", "browser", "🌐"),
    "com.kagi.kagimacOS": ("Orion", "browser", "🌐"),

    # Communication & Chat
    "com.tinyspeck.slackmacgap": ("Slack", "chat", "💬"),
    "com.hnc.Discord": ("Discord", "chat", "💬"),
    "com.apple.MobileSMS": ("Messages", "chat", "💬"),
    "ru.keepcoder.Telegram": ("Telegram", "chat", "💬"),
    "net.whatsapp.WhatsApp": ("WhatsApp", "chat", "💬"),
    "com.microsoft.teams2": ("Teams", "chat", "💬"),
    "com.skype.skype": ("Skype", "chat", "💬"),

    # AI Assistants & LLMs
    "com.anthropic.claudefordesktop": ("Claude", "chat", "🤖"),
    "com.anthropic.claude-desktop": ("Claude", "chat", "🤖"),
    "com.openai.chat": ("ChatGPT", "chat", "🤖"),

    # Email
    "com.apple.mail": ("Mail", "email", "✉️"),
    "com.microsoft.Outlook": ("Outlook", "email", "✉️"),
    "com.superhuman.electron": ("Superhuman", "email", "✉️"),
    "com.readdle.smartemail-Mac": ("Spark", "email", "✉️"),

    # Notes & Productivity
    "com.apple.Notes": ("Notes", "notes", "📝"),
    "notion.id": ("Notion", "notes", "📝"),
    "md.obsidian": ("Obsidian", "notes", "📝"),
    "com.microsoft.Word": ("Word", "notes", "📝"),
    "com.apple.iWork.Pages": ("Pages", "notes", "📝"),
    "com.apple.TextEdit": ("TextEdit", "notes", "📝"),
    "com.apple.finder": ("Finder", "general", "✨"),
}

# General keyword categories for unknown bundle IDs
APP_CATEGORIES = {
    "browser": {
        "chrome", "brave", "safari", "arc", "firefox", "edge", "opera",
        "vivaldi", "aside", "zen", "orion", "browser", "chromium"
    },
    "code": {
        "code", "cursor", "xcode", "terminal", "iterm", "warp", "ghostty",
        "sublime", "pycharm", "intellij", "webstorm", "antigravity", "clion", "zed"
    },
    "email": {
        "mail", "outlook", "superhuman", "spark", "thunderbird"
    },
    "chat": {
        "slack", "discord", "messages", "telegram", "whatsapp", "teams", "signal", "skype", "claude", "chatgpt"
    },
    "notes": {
        "notes", "notion", "obsidian", "word", "pages", "textedit", "bear", "craft"
    },
}

APP_ICONS = {
    "browser": "🌐",
    "code": "💻",
    "email": "✉️",
    "chat": "💬",
    "notes": "📝",
    "general": "✨",
}


def get_frontmost_app() -> dict:
    """
    Detect the active frontmost macOS application.
    Prioritizes direct Quartz WindowServer inspection (live z-order, zero runloop caching)
    with graceful fallback to NSWorkspace (with runloop flush) and System Events.
    """
    bid = ""
    raw_name = ""

    # Known system overlays and helper processes to ignore
    SYSTEM_IGNORE = {
        "window server", "dock", "spotlight", "windowmanager",
        "systemuiserver", "control center", "notification center",
        "screencapturekit", "universalaccessd", "autofill"
    }
    SCRIBER_PIDS = {os.getpid(), os.getppid()}

    # Priority 1: Direct Quartz Window Server inspection (always live, zero cache)
    # Inspects on-screen windows in true z-order (<0.7ms, talks directly to WindowServer)
    try:
        windows = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
            Quartz.kCGNullWindowID,
        )
        for w in windows:
            layer = w.get("kCGWindowLayer", 0)
            pid = w.get("kCGWindowOwnerPID", 0)
            owner = (w.get("kCGWindowOwnerName", "") or "").strip()
            owner_l = owner.lower()

            # Normal application windows are layer 0
            if layer != 0:
                continue

            # Skip Scriber processes & system overlays
            if pid in SCRIBER_PIDS or owner_l in SYSTEM_IGNORE or owner_l in {"electron", "scriber"}:
                continue

            app = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
            if app:
                app_bid = (app.bundleIdentifier() or "").strip()
                # Skip if the bundle ID indicates Scriber/Electron helper
                if app_bid in {"com.github.Electron", "com.scriber.app"}:
                    continue
                bid = app_bid
                raw_name = (app.localizedName() or owner).strip()
                if bid or raw_name:
                    break
            elif owner:
                raw_name = owner
                break
    except Exception:
        pass

    # Priority 2: In-process NSWorkspace query with runloop flush fallback
    if not bid and not raw_name:
        try:
            # Briefly pump the Cocoa runloop to process pending WindowServer notifications
            NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.001))
            app = NSWorkspace.sharedWorkspace().frontmostApplication()
            if app:
                bid = (app.bundleIdentifier() or "").strip()
                raw_name = (app.localizedName() or "").strip()
        except Exception:
            pass

    # Priority 3: Fallback to System Events
    if not bid and not raw_name:
        try:
            cmd = 'tell application "System Events" to return (bundle identifier of first application process whose frontmost is true) & "|||" & (name of first application process whose frontmost is true)'
            res = subprocess.run(["osascript", "-e", cmd], capture_output=True, text=True, timeout=0.3)
            if res.returncode == 0 and res.stdout.strip():
                parts = res.stdout.strip().split("|||")
                bid = parts[0].strip() if len(parts) > 0 else ""
                raw_name = parts[1].strip() if len(parts) > 1 else ""
        except Exception:
            pass

    # Direct match via Bundle Identifier
    if bid and bid in BUNDLE_ID_MAP:
        name, cat, icon = BUNDLE_ID_MAP[bid]
        return {"name": name, "category": cat, "icon": icon}

    # Fallback: Keyword matching on name or bundle ID
    combined = f"{raw_name} {bid}".lower()
    category = "general"
    for cat, app_set in APP_CATEGORIES.items():
        if any(kw in combined for kw in app_set):
            category = cat
            break

    display_name = raw_name if raw_name and raw_name.lower() != "electron" else "System"

    return {
        "name": display_name,
        "category": category,
        "icon": APP_ICONS.get(category, "✨"),
    }

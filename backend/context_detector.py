"""
Scriber — Active Application Context Detector
Detects frontmost macOS application using AppKit NSWorkspace, Quartz WindowServer,
and AppleScript fallbacks to enable smart context-aware dictation.
"""

import subprocess
from AppKit import NSWorkspace
import Quartz

# Processes to ignore (Scriber's own Electron processes and system layers)
IGNORED_APPS = {
    "scriber", "electron", "node", "npm exec electron .",
    "window server", "dock", "spotlight", "control center", "systemuiserver"
}

# Clean, human-readable display names for common apps
CLEAN_NAMES = {
    "google chrome": "Chrome",
    "brave browser": "Brave",
    "brave": "Brave",
    "safari": "Safari",
    "microsoft edge": "Edge",
    "firefox": "Firefox",
    "arc": "Arc",
    "opera": "Opera",
    "vivaldi": "Vivaldi",
    "aside": "Aside",
    "zen": "Zen Browser",
    "orion": "Orion",
    "antigravity ide": "Antigravity",
    "antigravity": "Antigravity",
    "visual studio code": "VS Code",
    "code": "VS Code",
    "cursor": "Cursor",
    "xcode": "Xcode",
    "iterm2": "iTerm",
    "iterm": "iTerm",
    "terminal": "Terminal",
    "warp": "Warp",
    "ghostty": "Ghostty",
    "sublime text": "Sublime",
    "slack": "Slack",
    "discord": "Discord",
    "messages": "Messages",
    "telegram": "Telegram",
    "whatsapp": "WhatsApp",
    "microsoft teams": "Teams",
    "teams": "Teams",
    "microsoft outlook": "Outlook",
    "outlook": "Outlook",
    "apple mail": "Mail",
    "mail": "Mail",
    "superhuman": "Superhuman",
    "spark": "Spark",
    "apple notes": "Notes",
    "notes": "Notes",
    "notion": "Notion",
    "obsidian": "Obsidian",
    "microsoft word": "Word",
    "word": "Word",
    "pages": "Pages",
    "textedit": "TextEdit",
    "finder": "Finder",
}

# Known application name sets mapped to dictation modes
APP_CATEGORIES = {
    "browser": {
        "google chrome", "chrome", "brave browser", "brave", "safari", "arc", 
        "firefox", "microsoft edge", "edge", "opera", "vivaldi", "aside", "zen", 
        "orion", "browser", "chromium"
    },
    "code": {
        "code", "visual studio code", "cursor", "xcode", "terminal", "iterm", "iterm2", 
        "warp", "ghostty", "alacritty", "sublime text", "pycharm", "intellij idea", 
        "webstorm", "antigravity ide", "antigravity", "clion", "neovim", "macvim", "zed"
    },
    "email": {
        "mail", "microsoft outlook", "outlook", "superhuman", "spark", "thunderbird", 
        "canary mail", "airmail", "boxer", "apple mail"
    },
    "chat": {
        "slack", "discord", "messages", "telegram", "whatsapp", "signal", "teams", 
        "microsoft teams", "mattermost", "element", "skype", "wechat"
    },
    "notes": {
        "notes", "apple notes", "notion", "obsidian", "bear", "craft", "pages", 
        "word", "microsoft word", "textedit", "drafts", "ulysses", "scrivener", "logseq"
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


def _is_ignored(name: str) -> bool:
    """Check if app name belongs to Scriber or system layers."""
    if not name:
        return True
    n = name.lower().strip()
    return any(ig in n for ig in IGNORED_APPS)


def get_frontmost_app() -> dict:
    """
    Get the currently active macOS application name and category using a robust
    3-layer detection strategy (NSWorkspace → Quartz WindowServer → AppleScript).
    Returns: {"name": str, "category": str, "icon": str}
    """
    raw_name = None

    # Layer 1: AppKit NSWorkspace frontmostApplication
    try:
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if app:
            n = (app.localizedName() or "").strip()
            bid = (app.bundleIdentifier() or "").strip()
            if n and not _is_ignored(n) and bid != "com.github.Electron":
                raw_name = n
    except Exception:
        pass

    # Layer 2: Quartz WindowServer (inspect top-most Layer 0 on-screen window)
    # Essential when Scriber's own window or menu bar was just clicked
    if not raw_name:
        try:
            windows = Quartz.CGWindowListCopyWindowInfo(
                Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
                Quartz.kCGNullWindowID,
            )
            for w in windows:
                layer = w.get("kCGWindowLayer", 0)
                owner = (w.get("kCGWindowOwnerName", "") or "").strip()
                if layer == 0 and owner and not _is_ignored(owner):
                    raw_name = owner
                    break
        except Exception:
            pass

    # Layer 3: AppleScript System Events fallback
    if not raw_name:
        try:
            res = subprocess.run(
                ["osascript", "-e", 'tell application "System Events" to get name of first application process whose frontmost is true'],
                capture_output=True,
                text=True,
                timeout=0.6,
            )
            if res.returncode == 0:
                candidate = res.stdout.strip()
                if candidate and not _is_ignored(candidate):
                    raw_name = candidate
        except Exception:
            pass

    if not raw_name:
        return {"name": "General", "category": "general", "icon": "✨"}

    name_lower = raw_name.lower().strip()

    # Determine dictation category
    category = "general"
    for cat, app_set in APP_CATEGORIES.items():
        if name_lower in app_set or any(kw in name_lower for kw in app_set):
            category = cat
            break

    # Determine clean display name for HUD badge
    clean_name = CLEAN_NAMES.get(name_lower, raw_name)

    return {
        "name": clean_name,
        "category": category,
        "icon": APP_ICONS.get(category, "✨"),
    }

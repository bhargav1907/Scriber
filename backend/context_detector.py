"""
Scriber — Active Application Context Detector
Detects frontmost macOS application using AppKit NSWorkspace to enable smart context-aware dictation.
"""

from AppKit import NSWorkspace

# Known application name sets mapped to dictation modes
APP_CATEGORIES = {
    "code": {
        "code", "visual studio code", "cursor", "xcode", "terminal", "iterm", "iterm2", 
        "warp", "ghostty", "alacritty", "sublime text", "pycharm", "intellij idea", 
        "webstorm", "antigravity ide", "clion", "neovim", "macvim", "zed"
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
    "code": "💻",
    "email": "✉️",
    "chat": "💬",
    "notes": "📝",
    "general": "✨",
}


def get_frontmost_app() -> dict:
    """
    Get the currently active macOS application name, bundle ID, and category.
    Returns: {"name": str, "category": str, "icon": str}
    """
    try:
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if not app:
            return {"name": "System", "category": "general", "icon": "✨"}

        raw_name = app.localizedName() or "Unknown"
        name_lower = raw_name.lower().strip()

        # Ignore Scriber itself if focused
        if "scriber" in name_lower:
            return {"name": "Desktop", "category": "general", "icon": "✨"}

        category = "general"
        for cat, app_set in APP_CATEGORIES.items():
            if name_lower in app_set or any(kw in name_lower for kw in app_set):
                category = cat
                break

        return {
            "name": raw_name,
            "category": category,
            "icon": APP_ICONS.get(category, "✨"),
        }
    except Exception as e:
        print(f"[Scriber] Could not detect frontmost app: {e}")
        return {"name": "Active App", "category": "general", "icon": "✨"}

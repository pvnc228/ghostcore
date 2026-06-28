"""
GhostCore OS — Phase 0: Package category → Nix package name mapping.

This is the deterministic lookup table. The LLM never invents package
names — it picks categories, and this map resolves them to real Nixpkgs.
"""

from __future__ import annotations

CATEGORY_PACKAGES: dict[str, list[str]] = {
    "development": [
        "git",
        "neovim",
        "vscode",
        "ripgrep",
        "fd",
        "jq",
        "lazygit",
        "direnv",
        "nix-direnv",
    ],
    "media": [
        "mpv",
        "vlc",
        "imv",
        "zathura",
        "obs-studio",
    ],
    "gaming": [
        "steam",
        "lutris",
        "gamemode",
        "mangohud",
        "wine",
    ],
    "office": [
        "libreoffice",
        "obsidian",
        "zotero",
    ],
    "communication": [
        "discord",
        "signal-desktop",
        "telegram-desktop",
        "thunderbird",
    ],
    "system-tools": [
        "htop",
        "btop",
        "fastfetch",
        "eza",
        "zoxide",
        "fzf",
        "bat",
        "tree",
        "unzip",
        "p7zip",
    ],
    "creative": [
        "gimp",
        "inkscape",
        "kdenlive",
        "blender",
    ],
    "security": [
        "firejail",
        "keepassxc",
        "gnupg",
        "age",
        "sops-nix",
    ],
}

WM_PACKAGES: dict[str, list[str]] = {
    "hyprland": ["hyprland", "waybar", "wofi", "dunst", "swaybg", "swaylock", "grim", "slurp"],
    "sway": ["sway", "waybar", "wofi", "dunst", "swaybg", "swaylock", "grim", "slurp"],
    "i3": ["i3", "i3status", "dunst", "rofi", "feh", "picom"],
    "gnome": ["gnome", "gnome-tweaks"],
    "kde": ["plasma5", "plasma-systemsettings"],
    "xfce": ["xfce", "xfce4-terminal", "xfce4-panel-profiles"],
    "none": [],
}

THEME_PACKAGES: dict[str, list[str]] = {
    "catppuccin-mocha": ["catppuccin-gtk"],
    "catppuccin-latte": ["catppuccin-gtk"],
    "dracula": ["dracula-theme"],
    "nord": ["nordic"],
    "gruvbox-dark": ["gruvbox-gtk-theme"],
    "gruvbox-light": ["gruvbox-gtk-theme"],
    "tokyo-night": ["tokyo-night-gtk"],
    "rose-pine": ["rose-pine-gtk-theme"],
    "adwaita": [],
    "breeze": [],
}

ICON_PACKAGES: dict[str, list[str]] = {
    "papirus": ["papirus-icon-theme"],
    "tela": ["tela-icon-theme"],
    "colloid": ["colloid-icon-theme"],
    "breeze": ["breeze-icons"],
    "adwaita": [],
    "nordic": ["nordic"],
}

BROWSER_PACKAGES: dict[str, str] = {
    "firefox": "firefox",
    "chromium": "chromium",
    "librewolf": "librewolf",
    "floorp": "floorp",
    "qutebrowser": "qutebrowser",
    "nyxt": "nyxt",
}

TERMINAL_PACKAGES: dict[str, str] = {
    "alacritty": "alacritty",
    "foot": "foot",
    "kitty": "kitty",
    "wezterm": "wezterm",
    "ghostty": "ghostty",
    "konsole": "konsole",
}

SHELL_PACKAGES: dict[str, str] = {
    "bash": "bash",
    "zsh": "zsh",
    "fish": "fish",
    "nushell": "nushell",
    "dash": "dash",
}


def resolve_packages(categories: list[str]) -> list[str]:
    """Expand package category names into a deduplicated sorted list of Nixpkgs names."""
    pkgs: set[str] = set()
    for cat in categories:
        pkgs.update(CATEGORY_PACKAGES.get(cat, []))
    return sorted(pkgs)

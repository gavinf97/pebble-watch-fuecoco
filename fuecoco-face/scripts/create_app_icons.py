#!/usr/bin/env python3
"""
Create app icons from a screenshot.

Vendored from coredevices/pebble-watchface-agent-skill (scripts/create_app_icons.py),
with the screenshot lookup order adjusted for this project's flint (Pebble 2 Duo) target.

Usage:
    python3 create_app_icons.py [project_dir]

If project_dir is not specified, uses current directory.
Looks for screenshot_flint.png, then screenshot.png, then screenshot_emery.png/screenshot_basalt.png.

Creates:
    - icon_80x80.png (small app icon)
    - icon_144x144.png (large app icon)
"""

import sys
import os
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("Error: Pillow is required. Install with: pip3 install Pillow")
    sys.exit(1)


def create_app_icons(project_dir: str = "."):
    """Create 80x80 and 144x144 app icons from screenshot"""

    project_path = Path(project_dir)

    # Try flint first (this project's target), then generic/legacy names
    candidates = ["screenshot_flint.png", "screenshot.png", "screenshot_emery.png", "screenshot_basalt.png"]
    screenshot_path = None
    for name in candidates:
        candidate = project_path / name
        if candidate.exists():
            screenshot_path = candidate
            break

    if screenshot_path is None:
        print(f"Error: No screenshot found (tried {', '.join(candidates)})")
        print("Run './dev.sh screenshot' (or 'pebble screenshot --no-open --emulator flint ...') first")
        sys.exit(1)

    # Load the screenshot
    img = Image.open(screenshot_path)
    print(f"Using: {screenshot_path}")

    # Create 80x80 icon
    icon_80 = img.resize((80, 80), Image.Resampling.LANCZOS)
    icon_80_path = project_path / "icon_80x80.png"
    icon_80.save(icon_80_path)
    print(f"Created: {icon_80_path}")

    # Create 144x144 icon
    icon_144 = img.resize((144, 144), Image.Resampling.LANCZOS)
    icon_144_path = project_path / "icon_144x144.png"
    icon_144.save(icon_144_path)
    print(f"Created: {icon_144_path}")

    print("\nApp icons created successfully!")


if __name__ == "__main__":
    project_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    create_app_icons(project_dir)

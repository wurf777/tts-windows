"""System tray icon using pystray. Runs in its own daemon thread."""

import pystray
from PIL import Image, ImageDraw

import config


def _fmt_hotkey(hk: str) -> str:
    """Format 'ctrl+alt+s' → 'Ctrl+Alt+S'."""
    return "+".join(part.capitalize() for part in hk.split("+"))

_icon: pystray.Icon = None


def _create_icon_image() -> Image.Image:
    """Simple 64×64 blue circle with white sound-wave lines."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Blue circle background
    draw.ellipse([2, 2, size - 2, size - 2], fill=(52, 120, 210, 255))

    # Simple speaker / sound wave symbol (three arcs approximated as rectangles)
    cx, cy = size // 2, size // 2

    # Speaker body
    draw.rectangle([cx - 10, cy - 8, cx - 2, cy + 8], fill=(255, 255, 255, 255))
    # Speaker cone (triangle-ish)
    draw.polygon(
        [(cx - 2, cy - 8), (cx + 8, cy - 16), (cx + 8, cy + 16), (cx - 2, cy + 8)],
        fill=(255, 255, 255, 255),
    )
    # Sound arcs
    for r, w in [(14, 3), (20, 3)]:
        draw.arc(
            [cx + 2, cy - r, cx + 2 + r * 2, cy + r],
            start=-60,
            end=60,
            fill=(255, 255, 255, 255),
            width=w,
        )

    return img


def run(root, on_read_selected, on_screenshot_ocr, on_open_settings, on_exit):
    """Blocking call — runs the pystray event loop. Call from a daemon thread."""
    global _icon

    menu = pystray.Menu(
        pystray.MenuItem(
            lambda item: f"Läs markerad text  ({_fmt_hotkey(config.HOTKEY_READ_SELECTED)})",
            lambda icon, item: root.after(0, on_read_selected),
        ),
        pystray.MenuItem(
            lambda item: f"Screenshot OCR  ({_fmt_hotkey(config.HOTKEY_SCREENSHOT_OCR)})",
            lambda icon, item: root.after(0, on_screenshot_ocr),
        ),
        pystray.MenuItem(
            "Inställningar",
            lambda icon, item: root.after(0, on_open_settings),
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "Avsluta",
            lambda icon, item: root.after(0, on_exit),
        ),
    )

    _icon = pystray.Icon(
        name="tts-windows",
        icon=_create_icon_image(),
        title="TTS Windows",
        menu=menu,
    )
    _icon.run()


def stop():
    """Stop the pystray icon loop. Safe to call from any thread."""
    global _icon
    if _icon is not None:
        _icon.stop()

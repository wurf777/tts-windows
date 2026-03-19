"""Global hotkey registration using the keyboard library.

Runs keyboard.wait() in the caller's thread to keep hooks alive.
All callbacks are routed through root.after(0, ...) to stay on the main thread.

NOTE: The keyboard library requires the process to run as Administrator on
Windows for reliable global hotkey interception in all contexts.
"""

import keyboard
import config_loader

_current_hotkeys: list[str] = []


def register(root, on_read_selected, on_screenshot_ocr):
    """Register hotkeys from config and block the calling thread forever."""
    _apply(root, on_read_selected, on_screenshot_ocr)
    keyboard.wait()  # blocks; daemon thread, so it won't prevent app exit


def _apply(root, on_read_selected, on_screenshot_ocr):
    global _current_hotkeys

    # Remove previously registered hotkeys
    for hk in _current_hotkeys:
        try:
            keyboard.remove_hotkey(hk)
        except KeyError:
            pass
    _current_hotkeys = []

    cfg = config_loader.load()
    hk1 = keyboard.add_hotkey(
        cfg.HOTKEY_READ_SELECTED,
        lambda: root.after(0, on_read_selected),
    )
    hk2 = keyboard.add_hotkey(
        cfg.HOTKEY_SCREENSHOT_OCR,
        lambda: root.after(0, on_screenshot_ocr),
    )
    _current_hotkeys = [cfg.HOTKEY_READ_SELECTED, cfg.HOTKEY_SCREENSHOT_OCR]


def re_register(root, on_read_selected, on_screenshot_ocr):
    """Update hotkey bindings after config has changed. Safe to call from main thread."""
    _apply(root, on_read_selected, on_screenshot_ocr)

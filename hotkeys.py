"""Global hotkey registration using the keyboard library.

Runs keyboard.wait() in the caller's thread to keep hooks alive.
All callbacks are routed through root.after(0, ...) to stay on the main thread.

NOTE: The keyboard library requires the process to run as Administrator on
Windows for reliable global hotkey interception in all contexts.
"""

import keyboard
import config_loader

_current_hotkeys = []


def register(root, on_read_selected, on_screenshot_ocr, on_open_text_input):
    """Register hotkeys from config and block the calling thread forever."""
    _apply(root, on_read_selected, on_screenshot_ocr, on_open_text_input)
    keyboard.wait()  # blocks; daemon thread, so it won't prevent app exit


def _apply(root, on_read_selected, on_screenshot_ocr, on_open_text_input):
    global _current_hotkeys

    # Remove previously registered hotkeys
    for hk in _current_hotkeys:
        try:
            keyboard.remove_hotkey(hk)
        except (KeyError, ValueError):
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
    hk3 = keyboard.add_hotkey(
        cfg.HOTKEY_OPEN_TEXT_INPUT,
        lambda: root.after(0, on_open_text_input),
    )
    _current_hotkeys = [
        hk1,
        hk2,
        hk3,
    ]


def re_register(root, on_read_selected, on_screenshot_ocr, on_open_text_input):
    """Update hotkey bindings after config has changed. Safe to call from main thread."""
    _apply(root, on_read_selected, on_screenshot_ocr, on_open_text_input)

"""
TTS Windows — entrypoint.

Threading model:
  Main thread  : tkinter mainloop + all UI operations
  pystray thread (daemon): tray icon
  keyboard thread (daemon): global hotkeys
  TTS thread (daemon, per utterance): Azure synthesis
  OCR thread (daemon, per screenshot): winsdk OCR
"""

import queue
import threading
import tkinter as tk
import time
import importlib

import pyperclip
import keyboard as kb

import config
import tray
import hotkeys
from tts_engine import TTSEngine
from playback_window import PlaybackWindow
from screenshot import ScreenshotOverlay
from settings_window import SettingsWindow
from text_input_window import TextInputWindow


# Shared state (only accessed from main thread except where noted)
word_queue: queue.Queue = queue.Queue()
tts_engine: TTSEngine = None
playback_window: PlaybackWindow = None
settings_window_ref: SettingsWindow = None
text_input_window_ref: TextInputWindow = None
root: tk.Tk = None


def get_selected_text() -> str:
    """Simulate Ctrl+C and read the clipboard. Runs on main thread."""
    try:
        old = pyperclip.paste()
    except Exception:
        old = ""

    pyperclip.copy("")
    # Release any held modifier keys so they don't interfere with ctrl+c
    for mod in ("ctrl", "alt", "shift"):
        kb.release(mod)
    kb.send("ctrl+c")
    time.sleep(config.CLIPBOARD_DELAY_MS / 1000)

    text = pyperclip.paste()

    try:
        pyperclip.copy(old)
    except Exception:
        pass

    return text.strip()


def on_read_selected():
    """Called on main thread when user triggers 'Läs markerad text'."""
    global tts_engine, playback_window
    print("[DEBUG] on_read_selected triggered")
    if playback_window is not None:
        print("[DEBUG] playback_window is not None, skipping")
        return  # already reading

    text = get_selected_text()
    print(f"[DEBUG] got text: {repr(text[:80]) if text else '(empty)'}")
    if not text:
        return

    tts_engine = TTSEngine(word_queue)
    threading.Thread(target=tts_engine.speak, args=(text,), daemon=True).start()


def on_screenshot_ocr():
    """Called on main thread — opens screenshot overlay."""
    if playback_window is not None:
        return  # already reading
    overlay = ScreenshotOverlay(root, on_ocr_text_ready)
    overlay.start()


def on_ocr_text_ready(text: str):
    """Called on main thread after OCR completes."""
    global tts_engine, playback_window
    if not text:
        return
    if playback_window is not None:
        return

    tts_engine = TTSEngine(word_queue)
    threading.Thread(target=tts_engine.speak, args=(text,), daemon=True).start()


def on_open_text_input():
    """Called on main thread — opens or focuses text input window."""
    global text_input_window_ref
    if text_input_window_ref is not None:
        try:
            text_input_window_ref.win.lift()
            text_input_window_ref.win.focus_force()
            return
        except tk.TclError:
            text_input_window_ref = None

    def on_read_pasted_text(text: str):
        global tts_engine, playback_window
        if playback_window is not None:
            return
        tts_engine = TTSEngine(word_queue)
        threading.Thread(target=tts_engine.speak, args=(text,), daemon=True).start()

    text_input_window_ref = TextInputWindow(root, on_read_pasted_text)


def on_open_settings():
    """Called on main thread — opens or focuses settings window."""
    global settings_window_ref
    if settings_window_ref is not None:
        try:
            settings_window_ref.win.lift()
            settings_window_ref.win.focus_force()
            return
        except tk.TclError:
            settings_window_ref = None

    settings_window_ref = SettingsWindow(root, on_settings_closed)


def on_settings_closed():
    global settings_window_ref
    settings_window_ref = None
    # Reload config so new settings take effect for next TTS call
    importlib.reload(config)
    hotkeys.re_register(root, on_read_selected, on_screenshot_ocr)


def on_cancel():
    """Called on main thread from Cancel button in playback window."""
    global tts_engine, playback_window
    if tts_engine is not None:
        tts_engine.stop()
    if playback_window is not None:
        try:
            playback_window.close()
        except Exception:
            pass
        playback_window = None


def poll_word_queue():
    """Drains the word_queue every 50 ms on the main thread."""
    global playback_window

    while True:
        try:
            msg = word_queue.get_nowait()
        except queue.Empty:
            break

        msg_type = msg.get("type")

        if msg_type == "start":
            if playback_window is None:
                playback_window = PlaybackWindow(root, msg["text"], on_cancel)

        elif msg_type == "word":
            if playback_window is not None:
                try:
                    playback_window.highlight_word(msg["offset"], msg["length"])
                except tk.TclError:
                    playback_window = None

        elif msg_type == "done":
            if playback_window is not None:
                try:
                    playback_window.close()
                except Exception:
                    pass
                playback_window = None

    root.after(50, poll_word_queue)


def on_exit():
    """Clean shutdown."""
    if tts_engine is not None:
        tts_engine.stop()
    tray.stop()
    root.quit()


def main():
    global root

    root = tk.Tk()
    root.withdraw()  # hide the root window — we only use it as a message pump

    # Start tray icon in daemon thread
    threading.Thread(
        target=tray.run,
        args=(root, on_read_selected, on_screenshot_ocr, on_open_text_input, on_open_settings, on_exit),
        daemon=True,
    ).start()

    # Start hotkey listener in daemon thread
    threading.Thread(
        target=hotkeys.register,
        args=(root, on_read_selected, on_screenshot_ocr),
        daemon=True,
    ).start()

    # Start word-queue poll loop
    root.after(50, poll_word_queue)

    root.mainloop()


if __name__ == "__main__":
    main()

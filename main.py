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

import pyperclip
import keyboard as kb

import config_loader
import tray
import hotkeys
import abbreviations
import markdown_utils
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
abbreviations_window_ref = None
root: tk.Tk = None


def _preprocess(text: str) -> str:
    return abbreviations.expand(text)


def _on_read_text(text: str):
    """Internal helper to start TTS on a string with markdown support."""
    global tts_engine, playback_window
    if not text or playback_window is not None:
        return

    text = _preprocess(text)
    cfg = config_loader.load()
    
    # Parse markdown to get display text, SSML for audio, and formatting tags
    display_text, ssml_text, tags = markdown_utils.process_markdown(text, cfg.AZURE_VOICE_NAME)
    
    tts_engine = TTSEngine(word_queue)
    threading.Thread(
        target=tts_engine.speak, 
        args=(display_text, ssml_text, tags), 
        daemon=True
    ).start()


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
    time.sleep(config_loader.load().CLIPBOARD_DELAY_MS / 1000)

    text = pyperclip.paste()

    try:
        pyperclip.copy(old)
    except Exception:
        pass

    return text.strip()


def on_read_selected():
    """Called on main thread when user triggers 'Läs markerad text'."""
    print("[DEBUG] on_read_selected triggered")
    text = get_selected_text()
    print(f"[DEBUG] got text: {repr(text[:80]) if text else '(empty)'}")
    _on_read_text(text)


def on_screenshot_ocr():
    """Called on main thread — opens screenshot overlay."""
    if playback_window is not None:
        return  # already reading
    overlay = ScreenshotOverlay(root, on_ocr_text_ready)
    overlay.start()


def on_ocr_text_ready(text: str):
    """Called on main thread after OCR completes."""
    _on_read_text(text)


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

    text_input_window_ref = TextInputWindow(root, _on_read_text)


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


def on_open_abbreviations():
    """Called on main thread — opens or focuses the abbreviations window."""
    global abbreviations_window_ref
    if abbreviations_window_ref is not None:
        try:
            abbreviations_window_ref.win.lift()
            abbreviations_window_ref.win.focus_force()
            return
        except tk.TclError:
            abbreviations_window_ref = None

    from abbreviations_window import AbbreviationsWindow

    def _on_closed():
        global abbreviations_window_ref
        abbreviations_window_ref = None

    abbreviations_window_ref = AbbreviationsWindow(root, _on_closed)


def on_settings_closed():
    global settings_window_ref
    settings_window_ref = None
    # Hotkeys may have changed — re-register with fresh config
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
                playback_window = PlaybackWindow(
                    root, 
                    msg["text"], 
                    on_cancel, 
                    tags=msg.get("tags")
                )

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


def _create_splash(root: tk.Tk) -> tuple[tk.Toplevel, tk.Label]:
    """Create a small splash window showing startup status."""
    from tkinter import font as tkfont

    win = tk.Toplevel(root)
    win.overrideredirect(True)
    win.attributes("-topmost", True)

    frame = tk.Frame(win, bg="#2b2b2b", padx=20, pady=14, highlightbackground="#555",
                     highlightthickness=1)
    frame.pack(fill=tk.BOTH, expand=True)

    title_font = tkfont.Font(family="Segoe UI", size=12, weight="bold")
    tk.Label(frame, text="TTS Windows", font=title_font, fg="#FFD700",
             bg="#2b2b2b").pack(anchor="w")

    status_font = tkfont.Font(family="Segoe UI", size=10)
    status_lbl = tk.Label(frame, text="Startar...", font=status_font, fg="#cccccc",
                          bg="#2b2b2b", anchor="w")
    status_lbl.pack(anchor="w", pady=(4, 0))

    win.update_idletasks()
    w, h = win.winfo_reqwidth(), win.winfo_reqheight()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = sw - w - 40
    y = sh - h - 80
    win.geometry(f"+{x}+{y}")

    # Force the window to actually render on screen
    win.update()

    return win, status_lbl


def main():
    global root

    root = tk.Tk()
    root.withdraw()  # hide the root window — we only use it as a message pump

    # Show splash
    splash_win, splash_status = _create_splash(root)

    def splash_update(text: str):
        splash_status.config(text=text)
        splash_win.update()

    import time as _time
    _splash_start = _time.time()

    # Load config
    splash_update("Laddar konfiguration...")
    cfg = config_loader.load()

    # Start tray icon in daemon thread
    splash_update("Startar systemfältsikon...")
    threading.Thread(
        target=tray.run,
        args=(root, on_read_selected, on_screenshot_ocr, on_open_text_input, on_open_settings, on_open_abbreviations, on_exit),
        daemon=True,
    ).start()

    # Start hotkey listener in daemon thread
    splash_update("Registrerar snabbtangenter...")
    threading.Thread(
        target=hotkeys.register,
        args=(root, on_read_selected, on_screenshot_ocr),
        daemon=True,
    ).start()

    # Start word-queue poll loop
    root.after(50, poll_word_queue)

    # Ensure splash is visible for at least 2 seconds total
    splash_update("Redo!")
    _elapsed_ms = int((_time.time() - _splash_start) * 1000)
    _remaining = max(2000 - _elapsed_ms, 400)
    root.after(_remaining, splash_win.destroy)

    root.mainloop()


if __name__ == "__main__":
    main()

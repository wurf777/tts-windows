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
import webbrowser
from tkinter import messagebox

import pyperclip
import keyboard as kb

import config_loader
import tray
import hotkeys
import abbreviations
import markdown_utils
from tts_engine import TTSEngine
from playback_window import PlaybackWindow
from screenshot import ScreenshotOverlay, configure_dpi_awareness
from settings_window import SettingsWindow
from text_input_window import TextInputWindow


# Shared state (only accessed from main thread except where noted)
word_queue: queue.Queue = queue.Queue()
tts_engine: TTSEngine = None
playback_window: PlaybackWindow = None
playback_start_time: float = 0.0
playback_token = None
pending_word_events = []
settings_window_ref: SettingsWindow = None
text_input_window_ref: TextInputWindow = None
abbreviations_window_ref = None
root: tk.Tk = None


def _preprocess(text: str) -> str:
    return abbreviations.expand(text)


def _on_read_text(text: str) -> bool:
    """Internal helper to start TTS on a string with markdown support."""
    global tts_engine, playback_window
    if not text or tts_engine is not None or playback_window is not None:
        return False

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
    return True


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


def on_open_azure_costs():
    """Open the configured Azure cost/budget page in the default browser."""
    url = config_loader.load().AZURE_COST_URL.strip()
    if url:
        webbrowser.open(url)


def on_settings_closed():
    global settings_window_ref
    settings_window_ref = None
    # Hotkeys may have changed — re-register with fresh config
    hotkeys.re_register(root, on_read_selected, on_screenshot_ocr, on_open_text_input)


def on_cancel():
    """Called on main thread from Cancel button in playback window."""
    global tts_engine, playback_window, playback_token, pending_word_events
    if tts_engine is not None:
        tts_engine.stop()
        tts_engine = None
    playback_token = None
    pending_word_events.clear()
    if playback_window is not None:
        try:
            playback_window.close()
        except Exception:
            pass
        playback_window = None


def _highlight_word(offset: int, length: int):
    global playback_window
    if playback_window is None:
        return
    try:
        playback_window.highlight_word(offset, length)
    except tk.TclError:
        playback_window = None


def _flush_due_word_events():
    if tts_engine is None or playback_window is None:
        return

    playback_ms = tts_engine.playback_position_ms()
    due_events = []
    while pending_word_events and pending_word_events[0]["audio_offset_ms"] <= playback_ms + 25:
        due_events.append(pending_word_events.pop(0))

    if due_events:
        event = due_events[-1]
        _highlight_word(event["offset"], event["length"])


def poll_word_queue():
    """Drains the word_queue every 50 ms on the main thread."""
    global tts_engine, playback_window, playback_start_time, playback_token, pending_word_events

    while True:
        try:
            msg = word_queue.get_nowait()
        except queue.Empty:
            break

        msg_type = msg.get("type")
        msg_token = msg.get("token")
        active_token = tts_engine.message_token if tts_engine is not None else None
        if msg_token is not None and msg_token != active_token:
            continue

        if msg_type == "start":
            if playback_window is None:
                playback_start_time = time.monotonic()
                playback_token = msg_token
                pending_word_events.clear()
                playback_window = PlaybackWindow(
                    root, 
                    msg["text"], 
                    on_cancel, 
                    tags=msg.get("tags")
                )

        elif msg_type == "word":
            if playback_window is not None:
                audio_offset_ms = msg.get("audio_offset_ms")
                if audio_offset_ms is None:
                    _highlight_word(msg["offset"], msg["length"])
                else:
                    pending_word_events.append(
                        {
                            "audio_offset_ms": audio_offset_ms,
                            "offset": msg["offset"],
                            "length": msg["length"],
                        }
                    )

        elif msg_type == "error":
            messagebox.showerror(
                msg.get("title", "TTS-fel"),
                msg.get("message", "Texten kunde inte läsas upp."),
                parent=root,
            )

        elif msg_type == "done":
            tts_engine = None
            playback_token = None
            pending_word_events.clear()
            if playback_window is not None:
                try:
                    playback_window.close()
                except Exception:
                    pass
                playback_window = None

    _flush_due_word_events()
    root.after(20, poll_word_queue)


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

    configure_dpi_awareness()
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
        args=(root, on_read_selected, on_screenshot_ocr, on_open_text_input, on_open_settings, on_open_abbreviations, on_open_azure_costs, on_exit),
        daemon=True,
    ).start()

    # Start hotkey listener in daemon thread
    splash_update("Registrerar snabbtangenter...")
    threading.Thread(
        target=hotkeys.register,
        args=(root, on_read_selected, on_screenshot_ocr, on_open_text_input),
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

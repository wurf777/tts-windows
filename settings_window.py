"""Settings window — lets the user edit config.py via a GUI.

Must only be created from the main (tkinter) thread.
Saves by rewriting config.py next to the executable / script.
"""

import tkinter as tk
from tkinter import ttk, messagebox

import config_loader

# ------------------------------------------------------------------
# Predefined voices per language
# ------------------------------------------------------------------
VOICES: dict[str, list[tuple[str, str]]] = {
    "sv": [
        ("sv-SE-MattiasNeural", "Mattias (Man)"),
        ("sv-SE-SofieNeural", "Sofie (Kvinna)"),
        ("sv-SE-HilleviNeural", "Hillevi (Kvinna)"),
    ],
    "en": [
        ("en-US-GuyNeural", "Guy – en-US (Man)"),
        ("en-US-JennyNeural", "Jenny – en-US (Kvinna)"),
        ("en-US-AriaNeural", "Aria – en-US (Kvinna)"),
        ("en-US-DavisNeural", "Davis – en-US (Man)"),
        ("en-GB-RyanNeural", "Ryan – en-GB (Man)"),
        ("en-GB-SoniaNeural", "Sonia – en-GB (Kvinna)"),
    ],
}

LANGUAGE_LABELS = {"sv": "Svenska", "en": "Engelska"}


class SettingsWindow:
    def __init__(self, root: tk.Tk, on_closed):
        self._root = root
        self._on_closed = on_closed

        self.win = tk.Toplevel(root)
        self.win.title("Inställningar")
        self.win.resizable(False, False)
        self.win.attributes("-topmost", True)
        self.win.protocol("WM_DELETE_WINDOW", self._on_cancel)

        # Centre on screen
        self.win.update_idletasks()
        w, h = 460, 320
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        self.win.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

        self._build_ui()
        self._load_from_config()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        pad = {"padx": 14, "pady": 4}
        lbl_w = 22  # label column width in characters

        frame = tk.Frame(self.win, padx=10, pady=10)
        frame.pack(fill=tk.BOTH, expand=True)

        # API-nyckel
        tk.Label(frame, text="Azure API-nyckel:", anchor="w", width=lbl_w).grid(
            row=0, column=0, sticky="w", **pad
        )
        self._key_var = tk.StringVar()
        tk.Entry(frame, textvariable=self._key_var, width=34, show="*").grid(
            row=0, column=1, sticky="ew", **pad
        )

        # Region
        tk.Label(frame, text="Region:", anchor="w", width=lbl_w).grid(
            row=1, column=0, sticky="w", **pad
        )
        self._region_var = tk.StringVar()
        tk.Entry(frame, textvariable=self._region_var, width=34).grid(
            row=1, column=1, sticky="ew", **pad
        )

        # Språk (radio)
        tk.Label(frame, text="Språk:", anchor="w", width=lbl_w).grid(
            row=2, column=0, sticky="w", **pad
        )
        lang_frame = tk.Frame(frame)
        lang_frame.grid(row=2, column=1, sticky="w", **pad)
        self._lang_var = tk.StringVar(value="sv")
        for code, label in LANGUAGE_LABELS.items():
            tk.Radiobutton(
                lang_frame,
                text=label,
                variable=self._lang_var,
                value=code,
                command=self._on_language_changed,
            ).pack(side=tk.LEFT, padx=(0, 12))

        # Röst (dropdown)
        tk.Label(frame, text="Röst:", anchor="w", width=lbl_w).grid(
            row=3, column=0, sticky="w", **pad
        )
        self._voice_var = tk.StringVar()
        self._voice_combo = ttk.Combobox(
            frame,
            textvariable=self._voice_var,
            state="readonly",
            width=32,
        )
        self._voice_combo.grid(row=3, column=1, sticky="ew", **pad)

        # Snabbtangent – läs text
        tk.Label(frame, text="Snabbtangent – Läs text:", anchor="w", width=lbl_w).grid(
            row=4, column=0, sticky="w", **pad
        )
        self._hotkey_read_var = tk.StringVar()
        tk.Entry(frame, textvariable=self._hotkey_read_var, width=34).grid(
            row=4, column=1, sticky="ew", **pad
        )

        # Snabbtangent – screenshot
        tk.Label(
            frame, text="Snabbtangent – Screenshot:", anchor="w", width=lbl_w
        ).grid(row=5, column=0, sticky="w", **pad)
        self._hotkey_shot_var = tk.StringVar()
        tk.Entry(frame, textvariable=self._hotkey_shot_var, width=34).grid(
            row=5, column=1, sticky="ew", **pad
        )

        frame.columnconfigure(1, weight=1)

        # Button bar
        btn_bar = tk.Frame(self.win)
        btn_bar.pack(fill=tk.X, padx=14, pady=(4, 12))
        tk.Button(btn_bar, text="Avbryt", width=10, command=self._on_cancel).pack(
            side=tk.RIGHT, padx=(6, 0)
        )
        tk.Button(
            btn_bar, text="Spara", width=10, command=self._on_save, default=tk.ACTIVE
        ).pack(side=tk.RIGHT)

    # ------------------------------------------------------------------
    # Data binding
    # ------------------------------------------------------------------

    def _load_from_config(self):
        cfg = config_loader.load()
        self._key_var.set(cfg.AZURE_SPEECH_KEY)
        self._region_var.set(cfg.AZURE_SPEECH_REGION)

        lang = cfg.LANGUAGE
        if lang not in VOICES:
            lang = "sv"
        self._lang_var.set(lang)
        self._populate_voices(lang)

        current_voice = cfg.AZURE_VOICE_NAME
        # Try to select the current voice in the combo
        voice_ids = [v[0] for v in VOICES[lang]]
        if current_voice in voice_ids:
            idx = voice_ids.index(current_voice)
            self._voice_combo.current(idx)
        else:
            self._voice_combo.current(0)

        self._hotkey_read_var.set(cfg.HOTKEY_READ_SELECTED)
        self._hotkey_shot_var.set(cfg.HOTKEY_SCREENSHOT_OCR)

    def _populate_voices(self, lang: str):
        voices = VOICES.get(lang, VOICES["sv"])
        display = [label for _, label in voices]
        self._voice_combo["values"] = display
        if display:
            self._voice_combo.current(0)

    def _on_language_changed(self):
        lang = self._lang_var.get()
        self._populate_voices(lang)

    # ------------------------------------------------------------------
    # Save / cancel
    # ------------------------------------------------------------------

    def _on_save(self):
        key = self._key_var.get().strip()
        region = self._region_var.get().strip()

        if not key or not region:
            messagebox.showwarning(
                "Saknade fält",
                "API-nyckel och Region måste fyllas i.",
                parent=self.win,
            )
            return

        lang = self._lang_var.get()
        voices = VOICES.get(lang, VOICES["sv"])
        voice_idx = self._voice_combo.current()
        voice_name = voices[voice_idx][0] if 0 <= voice_idx < len(voices) else voices[0][0]

        hotkey_read = self._hotkey_read_var.get().strip() or "ctrl+alt+s"
        hotkey_shot = self._hotkey_shot_var.get().strip() or "ctrl+alt+o"

        cfg = config_loader.load()
        content = (
            f'# Azure Speech Service\n'
            f'AZURE_SPEECH_KEY = {key!r}\n'
            f'AZURE_SPEECH_REGION = {region!r}\n'
            f'AZURE_VOICE_NAME = {voice_name!r}\n'
            f'\n'
            f'# Hotkeys (keyboard library format)\n'
            f'HOTKEY_READ_SELECTED = {hotkey_read!r}\n'
            f'HOTKEY_SCREENSHOT_OCR = {hotkey_shot!r}\n'
            f'\n'
            f'# Language: "sv" for Swedish, "en" for English\n'
            f'LANGUAGE = {lang!r}\n'
            f'\n'
            f'# Milliseconds to wait after Ctrl+C before reading clipboard\n'
            f'CLIPBOARD_DELAY_MS = {cfg.CLIPBOARD_DELAY_MS}\n'
        )

        try:
            with open(config_loader.CONFIG_PATH, "w", encoding="utf-8") as fh:
                fh.write(content)
        except OSError as exc:
            messagebox.showerror(
                "Fel",
                f"Kunde inte skriva config.py:\n{exc}",
                parent=self.win,
            )
            return

        self.win.destroy()
        self._on_closed()

    def _on_cancel(self):
        self.win.destroy()
        self._on_closed()

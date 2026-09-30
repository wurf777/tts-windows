"""Flexible settings window for the Piper and Azure TTS providers."""

import os
import re
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk

import keyboard

import config_loader


AZURE_VOICES: dict[str, list[tuple[str, str]]] = {
    "sv": [
        ("sv-SE-MattiasNeural", "Mattias (man)"),
        ("sv-SE-SofieNeural", "Sofie (kvinna)"),
        ("sv-SE-HilleviNeural", "Hillevi (kvinna)"),
    ],
    "en": [
        ("en-US-GuyNeural", "Guy – en-US (man)"),
        ("en-US-JennyNeural", "Jenny – en-US (kvinna)"),
        ("en-US-AriaNeural", "Aria – en-US (kvinna)"),
        ("en-US-DavisNeural", "Davis – en-US (man)"),
        ("en-GB-RyanNeural", "Ryan – en-GB (man)"),
        ("en-GB-SoniaNeural", "Sonia – en-GB (kvinna)"),
    ],
}

LANGUAGE_LABELS = {"sv": "Svenska", "en": "Engelska"}
PIPER_LOCALE_LABELS = {
    "sv_SE": "Svenska",
    "en_US": "Engelska (USA)",
    "en_GB": "Engelska (Storbritannien)",
}
TTS_PROVIDER_LABELS = {
    "piper": "Piper (lokal)",
    "azure": "Azure Neural (premium)",
}

_PIPER_MODEL_RE = re.compile(
    r"^(?P<locale>[a-z]{2}_[A-Z]{2})-(?P<voice>.+)-(?P<quality>x_low|low|medium|high)$"
)


class SettingsWindow:
    def __init__(self, root: tk.Tk, on_closed):
        self._root = root
        self._on_closed = on_closed
        self._original_key = ""
        self._piper_models: list[dict] = []
        self._piper_selected_model_path = ""

        self.win = tk.Toplevel(root)
        self.win.title("Inställningar")
        self.win.resizable(False, False)
        self.win.attributes("-topmost", True)
        self.win.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self._build_ui()
        self._load_from_config()
        self._position_window()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        pad = {"padx": 12, "pady": 5}
        lbl_w = 24

        self._body = tk.Frame(self.win, padx=14, pady=14)
        self._body.pack(fill=tk.BOTH, expand=True)

        tk.Label(self._body, text="TTS-motor:", anchor="w", width=lbl_w).grid(
            row=0, column=0, sticky="w", **pad
        )
        self._provider_var = tk.StringVar()
        self._provider_combo = ttk.Combobox(
            self._body,
            textvariable=self._provider_var,
            values=list(TTS_PROVIDER_LABELS.values()),
            state="readonly",
            width=36,
        )
        self._provider_combo.grid(row=0, column=1, sticky="ew", **pad)
        self._provider_combo.bind("<<ComboboxSelected>>", self._on_provider_changed)

        self._piper_frame = tk.Frame(self._body)
        self._build_piper_panel(self._piper_frame, lbl_w, pad)

        self._azure_frame = tk.Frame(self._body)
        self._build_azure_panel(self._azure_frame, lbl_w, pad)

        self._common_frame = tk.Frame(self._body)
        self._build_common_panel(self._common_frame, lbl_w, pad)
        self._common_frame.grid(row=3, column=0, columnspan=3, sticky="ew")

        self._body.columnconfigure(1, weight=1)

        btn_bar = tk.Frame(self.win)
        btn_bar.pack(fill=tk.X, padx=26, pady=(10, 18))
        tk.Button(btn_bar, text="Avbryt", width=10, command=self._on_cancel).pack(
            side=tk.RIGHT, padx=(6, 0)
        )
        tk.Button(
            btn_bar, text="Spara", width=10, command=self._on_save, default=tk.ACTIVE
        ).pack(side=tk.RIGHT)

    def _build_piper_panel(self, parent, lbl_w, pad):
        parent.grid(row=1, column=0, columnspan=3, sticky="ew")

        tk.Label(parent, text="Språk:", anchor="w", width=lbl_w).grid(
            row=0, column=0, sticky="w", **pad
        )
        self._piper_language_combo = ttk.Combobox(
            parent, textvariable=tk.StringVar(), state="readonly", width=36
        )
        # Keep the StringVar separately so both provider panels can use the
        # same configured LANGUAGE value without sharing widget state.
        self._piper_language_var = tk.StringVar()
        self._piper_language_combo.configure(textvariable=self._piper_language_var)
        self._piper_language_combo.grid(row=0, column=1, sticky="ew", **pad)
        self._piper_language_combo.bind(
            "<<ComboboxSelected>>", self._on_piper_language_changed
        )

        tk.Label(parent, text="Röst / modell:", anchor="w", width=lbl_w).grid(
            row=1, column=0, sticky="w", **pad
        )
        self._piper_voice_var = tk.StringVar()
        self._piper_voice_combo = ttk.Combobox(
            parent, textvariable=self._piper_voice_var, state="readonly", width=36
        )
        self._piper_voice_combo.grid(row=1, column=1, sticky="ew", **pad)
        self._piper_voice_combo.bind(
            "<<ComboboxSelected>>", self._on_piper_voice_changed
        )

        self._piper_info_var = tk.StringVar()
        tk.Label(
            parent,
            textvariable=self._piper_info_var,
            anchor="w",
            justify=tk.LEFT,
            fg="#555555",
        ).grid(row=2, column=1, sticky="w", **pad)
        tk.Button(parent, text="Uppdatera modeller", command=self._refresh_piper_models).grid(
            row=2, column=2, sticky="e", **pad
        )

    def _build_azure_panel(self, parent, lbl_w, pad):
        parent.grid(row=1, column=0, columnspan=3, sticky="ew")

        tk.Label(parent, text="API-nyckel:", anchor="w", width=lbl_w).grid(
            row=0, column=0, sticky="w", **pad
        )
        self._key_var = tk.StringVar()
        tk.Entry(parent, textvariable=self._key_var, width=34, show="*").grid(
            row=0, column=1, sticky="ew", **pad
        )

        tk.Label(parent, text="Region:", anchor="w", width=lbl_w).grid(
            row=1, column=0, sticky="w", **pad
        )
        self._region_var = tk.StringVar()
        tk.Entry(parent, textvariable=self._region_var, width=34).grid(
            row=1, column=1, sticky="ew", **pad
        )

        tk.Label(parent, text="Språk:", anchor="w", width=lbl_w).grid(
            row=2, column=0, sticky="w", **pad
        )
        self._azure_language_combo = ttk.Combobox(
            parent,
            textvariable=tk.StringVar(),
            values=list(LANGUAGE_LABELS.values()),
            state="readonly",
            width=36,
        )
        self._azure_language_var = tk.StringVar()
        self._azure_language_combo.configure(textvariable=self._azure_language_var)
        self._azure_language_combo.grid(row=2, column=1, sticky="ew", **pad)
        self._azure_language_combo.bind(
            "<<ComboboxSelected>>", self._on_azure_language_changed
        )

        tk.Label(parent, text="Röst:", anchor="w", width=lbl_w).grid(
            row=3, column=0, sticky="w", **pad
        )
        self._azure_voice_var = tk.StringVar()
        self._azure_voice_combo = ttk.Combobox(
            parent, textvariable=self._azure_voice_var, state="readonly", width=36
        )
        self._azure_voice_combo.grid(row=3, column=1, sticky="ew", **pad)

        tk.Label(parent, text="Kostnadslänk:", anchor="w", width=lbl_w).grid(
            row=4, column=0, sticky="w", **pad
        )
        self._cost_url_var = tk.StringVar()
        tk.Entry(parent, textvariable=self._cost_url_var, width=34).grid(
            row=4, column=1, columnspan=2, sticky="ew", **pad
        )

    def _build_common_panel(self, parent, lbl_w, pad):
        tk.Label(parent, text="Snabbtangent – Läs text:", anchor="w", width=lbl_w).grid(
            row=0, column=0, sticky="w", **pad
        )
        self._hotkey_read_var = tk.StringVar()
        tk.Entry(parent, textvariable=self._hotkey_read_var, width=24).grid(
            row=0, column=1, sticky="ew", **pad
        )
        self._btn_listen_read = tk.Button(
            parent,
            text="Lyssna",
            width=7,
            command=lambda: self._start_listening(
                self._hotkey_read_var, self._btn_listen_read
            ),
        )
        self._btn_listen_read.grid(row=0, column=2, **pad)

        tk.Label(
            parent, text="Snabbtangent – Screenshot:", anchor="w", width=lbl_w
        ).grid(row=1, column=0, sticky="w", **pad)
        self._hotkey_shot_var = tk.StringVar()
        tk.Entry(parent, textvariable=self._hotkey_shot_var, width=24).grid(
            row=1, column=1, sticky="ew", **pad
        )
        self._btn_listen_shot = tk.Button(
            parent,
            text="Lyssna",
            width=7,
            command=lambda: self._start_listening(
                self._hotkey_shot_var, self._btn_listen_shot
            ),
        )
        self._btn_listen_shot.grid(row=1, column=2, **pad)

        tk.Label(
            parent, text="Snabbtangent – Textinmatning:", anchor="w", width=lbl_w
        ).grid(row=2, column=0, sticky="w", **pad)
        self._hotkey_text_input_var = tk.StringVar()
        tk.Entry(parent, textvariable=self._hotkey_text_input_var, width=24).grid(
            row=2, column=1, sticky="ew", **pad
        )
        self._btn_listen_text_input = tk.Button(
            parent,
            text="Lyssna",
            width=7,
            command=lambda: self._start_listening(
                self._hotkey_text_input_var, self._btn_listen_text_input
            ),
        )
        self._btn_listen_text_input.grid(row=2, column=2, **pad)
        parent.columnconfigure(1, weight=1)

    def _position_window(self):
        self.win.update_idletasks()
        w = max(600, self.win.winfo_reqwidth())
        h = max(430, self.win.winfo_reqheight())
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        self.win.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    # ------------------------------------------------------------------
    # Provider and model selection
    # ------------------------------------------------------------------

    def _provider_key(self) -> str:
        return next(
            (key for key, label in TTS_PROVIDER_LABELS.items() if label == self._provider_var.get()),
            "piper",
        )

    def _on_provider_changed(self, _event=None):
        provider = self._provider_key()
        self._piper_frame.grid_remove()
        self._azure_frame.grid_remove()
        if provider == "azure":
            self._azure_frame.grid()
            self._populate_azure_languages()
        else:
            self._piper_frame.grid()
            self._populate_piper_languages()
        self._position_window()

    def _populate_azure_languages(self):
        labels = list(LANGUAGE_LABELS.values())
        self._azure_language_combo["values"] = labels
        code = self._language_code_from_value(self._azure_language_var.get(), LANGUAGE_LABELS)
        if code not in LANGUAGE_LABELS:
            code = "sv"
        self._azure_language_var.set(LANGUAGE_LABELS[code])
        self._populate_azure_voices(code)

    def _on_azure_language_changed(self, _event=None):
        code = self._language_code_from_value(self._azure_language_var.get(), LANGUAGE_LABELS)
        self._populate_azure_voices(code)

    def _populate_azure_voices(self, lang: str):
        voices = AZURE_VOICES.get(lang, AZURE_VOICES["sv"])
        self._azure_voice_combo["values"] = [label for _, label in voices]
        current = getattr(self, "_azure_voice_name", "")
        ids = [voice_id for voice_id, _ in voices]
        index = ids.index(current) if current in ids else 0
        if voices:
            self._azure_voice_combo.current(index)
            self._azure_voice_name = voices[index][0]

    def _refresh_piper_models(self):
        configured_path = getattr(self, "_piper_selected_model_path", "")
        self._piper_models = _discover_piper_models(configured_path)
        self._populate_piper_languages()
        self._position_window()

    def _populate_piper_languages(self):
        # Piper models are selected by locale (for example sv_SE/en_GB), not
        # only by their two-letter language code. Keeping the locale here is
        # also what lets British and American English coexist in the list.
        languages = sorted({model["locale"] for model in self._piper_models})
        labels = [self._piper_language_label(locale) for locale in languages]
        self._piper_language_combo["values"] = labels
        if not languages:
            self._piper_language_var.set("")
            self._piper_voice_combo["values"] = []
            self._piper_info_var.set(
                "Ingen Piper-modell hittades. Lägg .onnx och .onnx.json i models/."
            )
            return

        configured_lang = self._language_code_from_value(
            self._piper_language_var.get(),
            {lang: self._piper_language_label(lang) for lang in languages},
        )
        if configured_lang not in languages:
            configured_lang = languages[0]
        self._piper_language_var.set(self._piper_language_label(configured_lang))
        self._populate_piper_voices(configured_lang)

    def _on_piper_language_changed(self, _event=None):
        language_map = {
            model["locale"]: self._piper_language_label(model["locale"])
            for model in self._piper_models
        }
        locale = self._language_code_from_value(self._piper_language_var.get(), language_map)
        self._populate_piper_voices(locale)

    def _populate_piper_voices(self, locale: str):
        models = [model for model in self._piper_models if model["locale"] == locale]
        models.sort(key=lambda model: (model["voice"], model["quality"]))
        labels = [model["label"] for model in models]
        self._piper_voice_combo["values"] = labels
        current = self._piper_selected_model_path
        index = next(
            (i for i, model in enumerate(models) if _same_path(model["path"], current)),
            0,
        )
        if models:
            self._piper_voice_combo.current(index)
            self._piper_selected_model_path = models[index]["path"]
            self._piper_info_var.set(
                f"Vald modell: {models[index]['quality']} · {models[index]['config_path']}"
            )
        else:
            self._piper_info_var.set("Ingen modell finns för det valda språket.")

    def _on_piper_voice_changed(self, _event=None):
        locale = self._language_code_from_value(
            self._piper_language_var.get(),
            {model["locale"]: self._piper_language_label(model["locale"]) for model in self._piper_models},
        )
        models = [model for model in self._piper_models if model["locale"] == locale]
        index = self._piper_voice_combo.current()
        if 0 <= index < len(models):
            self._piper_selected_model_path = models[index]["path"]
            self._piper_info_var.set(
                f"Vald modell: {models[index]['quality']} · {models[index]['config_path']}"
            )

    @staticmethod
    def _language_code_from_value(value: str, labels: dict[str, str]) -> str:
        for code, label in labels.items():
            if value == label or value == code:
                return code
        return ""

    @staticmethod
    def _piper_language_label(locale: str) -> str:
        return PIPER_LOCALE_LABELS.get(locale, locale.replace("_", "-"))

    # ------------------------------------------------------------------
    # Data binding
    # ------------------------------------------------------------------

    def _load_from_config(self):
        cfg = config_loader.load()
        self._original_key = cfg.AZURE_SPEECH_KEY
        self._key_var.set(cfg.AZURE_SPEECH_KEY)
        self._region_var.set(cfg.AZURE_SPEECH_REGION)
        self._cost_url_var.set(cfg.AZURE_COST_URL)
        self._azure_voice_name = cfg.AZURE_VOICE_NAME
        self._piper_selected_model_path = cfg.PIPER_MODEL_PATH

        self._hotkey_read_var.set(cfg.HOTKEY_READ_SELECTED)
        self._hotkey_shot_var.set(cfg.HOTKEY_SCREENSHOT_OCR)
        self._hotkey_text_input_var.set(cfg.HOTKEY_OPEN_TEXT_INPUT)

        self._piper_models = _discover_piper_models(cfg.PIPER_MODEL_PATH)
        provider = str(cfg.TTS_PROVIDER).lower()
        if provider not in TTS_PROVIDER_LABELS:
            provider = "piper"
        self._provider_var.set(TTS_PROVIDER_LABELS[provider])

        lang = cfg.LANGUAGE if cfg.LANGUAGE in LANGUAGE_LABELS else "sv"
        self._azure_language_var.set(LANGUAGE_LABELS[lang])
        self._piper_language_var.set(lang)
        self._on_provider_changed()

    # ------------------------------------------------------------------
    # Hotkey listener
    # ------------------------------------------------------------------

    def _start_listening(self, var: tk.StringVar, btn: tk.Button):
        btn.config(text="Tryck...", state=tk.DISABLED)

        def _listen():
            hotkey = keyboard.read_hotkey(suppress=False)
            self._root.after(0, lambda: self._finish_listening(var, btn, hotkey))

        threading.Thread(target=_listen, daemon=True).start()

    def _finish_listening(self, var: tk.StringVar, btn: tk.Button, hotkey: str):
        var.set(hotkey)
        btn.config(text="Lyssna", state=tk.NORMAL)

    # ------------------------------------------------------------------
    # Save / cancel
    # ------------------------------------------------------------------

    def _on_save(self):
        provider = self._provider_key()
        key = self._key_var.get().strip()
        region = self._region_var.get().strip()
        cfg = config_loader.load()

        if provider == "azure":
            if not key or not region:
                messagebox.showwarning(
                    "Saknade fält",
                    "API-nyckel och Region måste fyllas i för Azure.",
                    parent=self.win,
                )
                return
            if key == "your-key-here" or len(key) < 20:
                messagebox.showwarning(
                    "Ogiltig API-nyckel",
                    "Azure API-nyckeln ser för kort ut.",
                    parent=self.win,
                )
                return
            if self._original_key and key != self._original_key:
                if not messagebox.askyesno(
                    "API-nyckeln har ändrats",
                    "Du har ändrat Azure API-nyckeln. Vill du verkligen spara den nya nyckeln?",
                    parent=self.win,
                ):
                    return

        if provider == "piper" and not self._piper_selected_model_path:
            messagebox.showwarning(
                "Piper-modell saknas",
                "Välj eller installera minst en Piper-modell först.",
                parent=self.win,
            )
            return

        if provider == "azure":
            lang = self._language_code_from_value(self._azure_language_var.get(), LANGUAGE_LABELS)
            voices = AZURE_VOICES.get(lang, AZURE_VOICES["sv"])
            voice_idx = self._azure_voice_combo.current()
            voice_name = voices[voice_idx][0] if 0 <= voice_idx < len(voices) else voices[0][0]
            piper_model_path = cfg.PIPER_MODEL_PATH
        else:
            locale = self._language_code_from_value(
                self._piper_language_var.get(),
                {model["locale"]: self._piper_language_label(model["locale"]) for model in self._piper_models},
            )
            lang = locale.split("_")[0].lower() if locale else "sv"
            voice_name = cfg.AZURE_VOICE_NAME
            piper_model_path = _config_model_path(self._piper_selected_model_path)

        hotkey_read = self._hotkey_read_var.get().strip() or "ctrl+alt+s"
        hotkey_shot = self._hotkey_shot_var.get().strip() or "ctrl+alt+o"
        hotkey_text_input = self._hotkey_text_input_var.get().strip() or "ctrl+alt+v"
        content = (
            f'# TTS-motor: "piper" (lokal) eller "azure" (premium)\n'
            f'TTS_PROVIDER = {provider!r}\n'
            f'PIPER_MODEL_PATH = {piper_model_path!r}\n'
            f'\n'
            f'# Azure Speech Service\n'
            f'AZURE_SPEECH_KEY = {key!r}\n'
            f'AZURE_SPEECH_REGION = {region!r}\n'
            f'AZURE_VOICE_NAME = {voice_name!r}\n'
            f'\n'
            f'# Hotkeys (keyboard library format)\n'
            f'HOTKEY_READ_SELECTED = {hotkey_read!r}\n'
            f'HOTKEY_SCREENSHOT_OCR = {hotkey_shot!r}\n'
            f'HOTKEY_OPEN_TEXT_INPUT = {hotkey_text_input!r}\n'
            f'\n'
            f'# Language: "sv" for Swedish, "en" for English\n'
            f'LANGUAGE = {lang!r}\n'
            f'\n'
            f'# Milliseconds to wait after Ctrl+C before reading clipboard\n'
            f'CLIPBOARD_DELAY_MS = {cfg.CLIPBOARD_DELAY_MS}\n'
            f'\n'
            f'# Optional local link opened from the tray menu\n'
            f'AZURE_COST_URL = {self._cost_url_var.get().strip()!r}\n'
        )

        try:
            with open(config_loader.CONFIG_PATH, "w", encoding="utf-8") as fh:
                fh.write(content)
        except OSError as exc:
            messagebox.showerror(
                "Fel", f"Kunde inte skriva config.py:\n{exc}", parent=self.win
            )
            return

        self.win.destroy()
        self._on_closed()

    def _on_cancel(self):
        self.win.destroy()
        self._on_closed()


def _model_roots() -> list[str]:
    roots = [os.path.join(config_loader.APP_DIR, "models")]
    bundle_dir = getattr(sys, "_MEIPASS", "")
    if bundle_dir:
        roots.append(os.path.join(bundle_dir, "models"))
    # In a one-file build PyInstaller may expose the extracted bundle through
    # __file__ even when _MEIPASS is not available on the imported module.
    module_dir = os.path.dirname(os.path.abspath(__file__))
    roots.append(os.path.join(module_dir, "models"))

    unique = []
    seen = set()
    for root in roots:
        key = os.path.normcase(os.path.abspath(root))
        if key not in seen:
            unique.append(root)
            seen.add(key)
    return unique


def _discover_piper_models(configured_path: str = "") -> list[dict]:
    models = []
    seen = set()
    for root in _model_roots():
        if not os.path.isdir(root):
            continue
        for filename in os.listdir(root):
            if not filename.lower().endswith(".onnx"):
                continue
            path = os.path.join(root, filename)
            if not os.path.isfile(path) or not os.path.isfile(path + ".json"):
                continue
            model = _parse_piper_model(path)
            if model and os.path.normcase(os.path.abspath(path)) not in seen:
                model["config_path"] = os.path.join("models", filename).replace("\\", "/")
                models.append(model)
                seen.add(os.path.normcase(os.path.abspath(path)))

    if configured_path:
        configured_abs = _resolve_config_path(configured_path)
        if os.path.isfile(configured_abs) and os.path.isfile(configured_abs + ".json"):
            model = _parse_piper_model(configured_abs)
            if model and os.path.normcase(os.path.abspath(configured_abs)) not in seen:
                model["config_path"] = configured_path
                models.append(model)
    return sorted(models, key=lambda model: (model["locale"], model["voice"], model["quality"]))


def _parse_piper_model(path: str):
    match = _PIPER_MODEL_RE.match(os.path.splitext(os.path.basename(path))[0])
    if not match:
        return None
    locale = match.group("locale")
    voice = match.group("voice")
    quality = match.group("quality")
    return {
        "path": path,
        "locale": locale,
        "lang": locale.split("_")[0].lower(),
        "voice": voice,
        "quality": quality,
        "label": f"{voice} ({quality})",
    }


def _resolve_config_path(path: str) -> str:
    if os.path.isabs(path):
        return path
    return os.path.join(config_loader.APP_DIR, path)


def _same_path(first: str, second: str) -> bool:
    if not first or not second:
        return False
    return _model_reference(first) == _model_reference(second)


def _config_model_path(path: str) -> str:
    """Store models inside the app's models folder as a portable path."""
    absolute = os.path.abspath(path)
    for root in _model_roots():
        root_abs = os.path.abspath(root)
        try:
            if os.path.commonpath([absolute, root_abs]) == root_abs:
                return os.path.join("models", os.path.basename(absolute)).replace("\\", "/")
        except ValueError:
            continue
    return absolute


def _model_reference(path: str) -> str:
    """Return a stable comparison key for external and bundled model paths."""
    if not os.path.isabs(path):
        normalized = path.replace("\\", "/")
        if normalized.lower().startswith("models/"):
            return os.path.normcase(normalized)
    absolute = os.path.abspath(_resolve_config_path(path))
    for root in _model_roots():
        root_abs = os.path.abspath(root)
        try:
            if os.path.commonpath([absolute, root_abs]) == root_abs:
                return os.path.normcase(
                    ("models/" + os.path.basename(absolute)).replace("\\", "/")
                )
        except ValueError:
            continue
    return os.path.normcase(absolute)

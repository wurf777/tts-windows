"""Text input window — lets the user paste text and have it read aloud.

Must only be created from the main (tkinter) thread.
"""

import tkinter as tk
from tkinter import font as tkfont, ttk


class TextInputWindow:
    def __init__(self, root: tk.Tk, on_read_text):
        """
        on_read_text(text: str) — callback invoked with the text to speak.
        """
        self._root = root
        self._on_read_text = on_read_text
        self._closed = False

        self.win = tk.Toplevel(root)
        self.win.title("Klistra in text")
        self.win.attributes("-topmost", True)
        self.win.resizable(True, True)
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.win.bind("<Escape>", lambda _: self.close())

        # Centre on screen
        self.win.update_idletasks()
        w, h = 540, 360
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        self.win.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

        self._build_ui()
        self.win.after(100, self._focus)

    def _focus(self):
        self.win.focus_force()
        self._text_widget.focus_set()

    def _build_ui(self):
        # Label
        tk.Label(
            self.win,
            text="Klistra in eller skriv text nedan och tryck Läs upp:",
            anchor="w",
        ).pack(fill=tk.X, padx=12, pady=(10, 4))

        # Button bar — packed BEFORE text widget so it always has room
        btn_frame = tk.Frame(self.win, pady=4)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=(0, 10))

        ttk.Button(
            btn_frame,
            text="Stäng",
            command=self.close,
        ).pack(side=tk.RIGHT, padx=(6, 0), ipadx=8, ipady=2)

        ttk.Button(
            btn_frame,
            text="Läs upp",
            command=self._on_read,
        ).pack(side=tk.RIGHT, ipadx=8, ipady=2)

        # Text widget — fills remaining space
        text_font = tkfont.Font(family="Segoe UI", size=11)
        self._text_widget = tk.Text(
            self.win,
            wrap=tk.WORD,
            font=text_font,
            relief=tk.SUNKEN,
            padx=8,
            pady=6,
        )
        self._text_widget.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 6))

        # Ctrl+Enter to read
        self.win.bind("<Control-Return>", lambda _: self._on_read())

    def _on_read(self):
        text = self._text_widget.get("1.0", tk.END).strip()
        if text:
            self._on_read_text(text)

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self.win.destroy()
        except tk.TclError:
            pass

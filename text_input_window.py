"""Text input window — lets the user paste text and have it read aloud.

Must only be created from the main (tkinter) thread.
"""

import tkinter as tk
from tkinter import font as tkfont, ttk


AUTO_CLOSE_SECONDS = 5


class TextInputWindow:
    def __init__(self, root: tk.Tk, on_read_text):
        """
        on_read_text(text: str) — callback invoked with the text to speak.
        """
        self._root = root
        self._on_read_text = on_read_text
        self._closed = False
        self._auto_close_after_id = None
        self._auto_close_remaining = 0

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

        self._read_button = ttk.Button(
            btn_frame,
            text="Läs upp (Ctrl+Enter)",
            command=self._on_read,
            width=22,
        )
        self._read_button.pack(side=tk.RIGHT, ipadx=8, ipady=2)

        self._countdown_var = tk.DoubleVar(value=0)
        self._countdown_bar = ttk.Progressbar(
            btn_frame,
            variable=self._countdown_var,
            maximum=AUTO_CLOSE_SECONDS,
            mode="determinate",
            length=140,
        )

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
        self._build_context_menu()

        # Ctrl+Enter to read
        self.win.bind("<Control-Return>", self._on_read_shortcut)
        self._text_widget.bind("<Control-Return>", self._on_read_shortcut)

    def _on_read_shortcut(self, _event):
        self._on_read()
        return "break"

    def _build_context_menu(self):
        self._context_menu = tk.Menu(self.win, tearoff=False)
        self._context_menu.add_command(label="Klipp ut", command=self._cut)
        self._context_menu.add_command(label="Kopiera", command=self._copy)
        self._context_menu.add_command(label="Klistra in", command=self._paste)
        self._context_menu.add_separator()
        self._context_menu.add_command(label="Markera allt", command=self._select_all)
        self._text_widget.bind("<Button-3>", self._show_context_menu)

    def _show_context_menu(self, event):
        self._text_widget.focus_set()
        try:
            self._text_widget.index(tk.SEL_FIRST)
            has_selection = True
        except tk.TclError:
            has_selection = False

        state = tk.NORMAL if has_selection else tk.DISABLED
        self._context_menu.entryconfigure("Klipp ut", state=state)
        self._context_menu.entryconfigure("Kopiera", state=state)
        self._context_menu.tk_popup(event.x_root, event.y_root)
        return "break"

    def _cut(self):
        self._text_widget.event_generate("<<Cut>>")

    def _copy(self):
        self._text_widget.event_generate("<<Copy>>")

    def _paste(self):
        self._text_widget.focus_set()
        self._text_widget.event_generate("<<Paste>>")

    def _select_all(self):
        self._text_widget.tag_add(tk.SEL, "1.0", tk.END)
        self._text_widget.mark_set(tk.INSERT, "1.0")
        self._text_widget.see(tk.INSERT)
        return "break"

    def _on_read(self):
        if self._auto_close_after_id is not None:
            self._cancel_auto_close()
            return

        text = self._text_widget.get("1.0", tk.END).strip()
        if text:
            started = self._on_read_text(text)
            if started is not False:
                self._start_auto_close()

    def _start_auto_close(self):
        self._cancel_auto_close(reset_button=False)
        self._auto_close_remaining = AUTO_CLOSE_SECONDS
        self._countdown_var.set(AUTO_CLOSE_SECONDS)
        self._countdown_bar.pack(side=tk.RIGHT, padx=(0, 10), fill=tk.X)
        self._tick_auto_close()

    def _tick_auto_close(self):
        if self._closed:
            return

        self._read_button.config(text=f"Behåll öppen ({self._auto_close_remaining})")
        self._countdown_var.set(self._auto_close_remaining)

        if self._auto_close_remaining <= 0:
            self.close()
            return

        self._auto_close_remaining -= 1
        self._auto_close_after_id = self.win.after(1000, self._tick_auto_close)

    def _cancel_auto_close(self, reset_button=True):
        if self._auto_close_after_id is not None:
            try:
                self.win.after_cancel(self._auto_close_after_id)
            except tk.TclError:
                pass
        self._auto_close_after_id = None
        self._auto_close_remaining = 0
        if reset_button and not self._closed:
            self._read_button.config(text="Läs upp (Ctrl+Enter)")
            self._countdown_var.set(0)
            self._countdown_bar.pack_forget()

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._cancel_auto_close(reset_button=False)
        try:
            self.win.destroy()
        except tk.TclError:
            pass

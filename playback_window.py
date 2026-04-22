"""Playback window — shows text and highlights the current word in real time.

Must only be created and manipulated from the main (tkinter) thread.
"""

import tkinter as tk
from tkinter import font as tkfont, ttk


class PlaybackWindow:
    def __init__(self, root: tk.Tk, text: str, on_cancel, tags=None):
        self._root = root
        self._on_cancel = on_cancel
        self._closed = False

        self.win = tk.Toplevel(root)
        self.win.title("Läser…")
        self.win.attributes("-topmost", True)
        self.win.resizable(True, False)
        self.win.protocol("WM_DELETE_WINDOW", self._cancel)
        self.win.bind("<Escape>", lambda _: self._cancel())
        self.win.after(100, self.win.focus_force)

        # Position near bottom-right of screen
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        win_w, win_h = 520, 240
        x = screen_w - win_w - 40
        y = screen_h - win_h - 80
        self.win.geometry(f"{win_w}x{win_h}+{x}+{y}")

        # Text widget
        self._base_font = tkfont.Font(family="Segoe UI", size=12)
        self._bold_font = tkfont.Font(family="Segoe UI", size=12, weight="bold")
        self._italic_font = tkfont.Font(family="Segoe UI", size=12, slant="italic")
        self._heading_font = tkfont.Font(family="Segoe UI", size=16, weight="bold")

        self._text_widget = tk.Text(
            self.win,
            wrap=tk.WORD,
            font=self._base_font,
            state=tk.DISABLED,
            relief=tk.FLAT,
            padx=12,
            pady=10,
            cursor="arrow",
            height=6,
            bg="#fdfdfd"
        )
        self._text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 4))

        # Tags configuration
        self._text_widget.tag_configure("highlight", background="#FFD700", foreground="#1a1a1a")
        self._text_widget.tag_configure("bold", font=self._bold_font)
        self._text_widget.tag_configure("italic", font=self._italic_font)
        self._text_widget.tag_configure("heading", font=self._heading_font, foreground="#005a9e")

        # Button bar
        btn_frame = tk.Frame(self.win, pady=4)
        btn_frame.pack(fill=tk.X, padx=10, pady=(0, 8))

        cancel_btn = ttk.Button(
            btn_frame,
            text="Avbryt",
            command=self._cancel,
        )
        cancel_btn.pack(side=tk.RIGHT, ipadx=8, ipady=2)

        self._set_text(text, tags)

    # ------------------------------------------------------------------
    # Public methods — call only from main thread
    # ------------------------------------------------------------------

    def highlight_word(self, offset: int, length: int) -> None:
        """Highlight the word at character position [offset, offset+length)."""
        if self._closed:
            return
        tw = self._text_widget
        tw.tag_remove("highlight", "1.0", tk.END)
        start = f"1.0 + {offset} chars"
        end = f"1.0 + {offset + length} chars"
        tw.tag_add("highlight", start, end)
        # Ensure the current word is visible
        tw.see(start)

    def close(self) -> None:
        """Destroy the window."""
        if self._closed:
            return
        self._closed = True
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _set_text(self, text: str, tags=None) -> None:
        tw = self._text_widget
        tw.configure(state=tk.NORMAL)
        tw.delete("1.0", tk.END)
        tw.insert("1.0", text)
        
        if tags:
            for tag_name, start, end in tags:
                start_pos = f"1.0 + {start} chars"
                end_pos = f"1.0 + {end} chars"
                tw.tag_add(tag_name, start_pos, end_pos)
                
        tw.configure(state=tk.DISABLED)

    def _cancel(self) -> None:
        self._on_cancel()

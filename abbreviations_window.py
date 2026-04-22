"""Abbreviations management window.

Lets the user add, edit, and delete abbreviation → expansion pairs.
Must only be created from the main (tkinter) thread.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional

import abbreviations


class AbbreviationsWindow:
    def __init__(self, root: tk.Tk, on_closed):
        self._root = root
        self._on_closed = on_closed

        self.win = tk.Toplevel(root)
        self.win.title("Förkortningar")
        self.win.resizable(True, True)
        self.win.attributes("-topmost", True)
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)

        self.win.update_idletasks()
        w, h = 560, 400
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        self.win.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
        self.win.minsize(400, 280)

        self._build_ui()
        self._load_list()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        # Toolbar
        toolbar = tk.Frame(self.win, pady=6, padx=10)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        tk.Button(toolbar, text="Lägg till", width=10, command=self._on_add).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        tk.Button(toolbar, text="Redigera", width=10, command=self._on_edit).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        tk.Button(toolbar, text="Ta bort", width=10, command=self._on_delete).pack(
            side=tk.LEFT
        )

        # List area
        list_frame = tk.Frame(self.win, padx=10)
        list_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        cols = ("abbr", "expansion")
        self._tree = ttk.Treeview(list_frame, columns=cols, show="headings", selectmode="browse")
        self._tree.heading("abbr", text="Förkortning")
        self._tree.heading("expansion", text="Expansion")
        self._tree.column("abbr", width=160, stretch=False)
        self._tree.column("expansion", stretch=True)
        self._tree.bind("<Double-1>", lambda e: self._on_edit())

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)

        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Button bar
        btn_bar = tk.Frame(self.win, pady=8, padx=10)
        btn_bar.pack(side=tk.BOTTOM, fill=tk.X)
        tk.Button(btn_bar, text="Stäng", width=10, command=self._on_close).pack(side=tk.RIGHT)

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def _load_list(self):
        self._tree.delete(*self._tree.get_children())
        abbrevs = abbreviations.load()
        for abbr in sorted(abbrevs.keys(), key=str.lower):
            self._tree.insert("", tk.END, values=(abbr, abbrevs[abbr]))

    def _selected_abbr(self) -> Optional[str]:
        sel = self._tree.selection()
        if not sel:
            return None
        return self._tree.item(sel[0], "values")[0]

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_add(self):
        self._open_edit_dialog()

    def _on_edit(self):
        abbr = self._selected_abbr()
        if abbr is None:
            messagebox.showinfo("Ingen vald", "Välj en förkortning att redigera.", parent=self.win)
            return
        abbrevs = abbreviations.load()
        self._open_edit_dialog(abbr=abbr, expansion=abbrevs.get(abbr, ""))

    def _on_delete(self):
        abbr = self._selected_abbr()
        if abbr is None:
            messagebox.showinfo("Ingen vald", "Välj en förkortning att ta bort.", parent=self.win)
            return
        if not messagebox.askyesno(
            "Ta bort",
            f'Ta bort förkortningen "{abbr}"?',
            parent=self.win,
        ):
            return
        abbrevs = abbreviations.load()
        abbrevs.pop(abbr, None)
        abbreviations.save(abbrevs)
        self._load_list()

    def _open_edit_dialog(self, abbr: str = "", expansion: str = ""):
        is_new = abbr == ""
        dialog = tk.Toplevel(self.win)
        dialog.title("Lägg till förkortning" if is_new else "Redigera förkortning")
        dialog.resizable(False, False)
        dialog.attributes("-topmost", True)
        dialog.transient(self.win)
        dialog.grab_set()

        dialog.update_idletasks()
        w, h = 380, 140
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        dialog.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

        frame = tk.Frame(dialog, padx=14, pady=10)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(frame, text="Förkortning:", anchor="w", width=14).grid(
            row=0, column=0, sticky="w", pady=4
        )
        abbr_var = tk.StringVar(value=abbr)
        abbr_entry = tk.Entry(frame, textvariable=abbr_var, width=24)
        abbr_entry.grid(row=0, column=1, sticky="ew", pady=4)
        if is_new:
            abbr_entry.focus_set()

        tk.Label(frame, text="Expansion:", anchor="w", width=14).grid(
            row=1, column=0, sticky="w", pady=4
        )
        exp_var = tk.StringVar(value=expansion)
        exp_entry = tk.Entry(frame, textvariable=exp_var, width=24)
        exp_entry.grid(row=1, column=1, sticky="ew", pady=4)
        if not is_new:
            exp_entry.focus_set()

        frame.columnconfigure(1, weight=1)

        def _save():
            new_abbr = abbr_var.get().strip()
            new_exp = exp_var.get().strip()
            if not new_abbr or not new_exp:
                messagebox.showwarning(
                    "Saknade fält", "Både förkortning och expansion måste fyllas i.", parent=dialog
                )
                return
            abbrevs = abbreviations.load()
            if is_new and new_abbr in abbrevs:
                if not messagebox.askyesno(
                    "Ersätt?",
                    f'Förkortningen "{new_abbr}" finns redan. Ersätta?',
                    parent=dialog,
                ):
                    return
            if not is_new and abbr != new_abbr:
                abbrevs.pop(abbr, None)
            abbrevs[new_abbr] = new_exp
            abbreviations.save(abbrevs)
            dialog.destroy()
            self._load_list()

        btn_bar = tk.Frame(dialog, pady=6, padx=14)
        btn_bar.pack(side=tk.BOTTOM, fill=tk.X)
        tk.Button(btn_bar, text="Avbryt", width=8, command=dialog.destroy).pack(
            side=tk.RIGHT, padx=(6, 0)
        )
        tk.Button(btn_bar, text="Spara", width=8, command=_save, default=tk.ACTIVE).pack(
            side=tk.RIGHT
        )

        dialog.bind("<Return>", lambda e: _save())
        dialog.bind("<Escape>", lambda e: dialog.destroy())
        dialog.wait_window()

    # ------------------------------------------------------------------
    # Close
    # ------------------------------------------------------------------

    def _on_close(self):
        self.win.destroy()
        self._on_closed()

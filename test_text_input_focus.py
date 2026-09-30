"""Opt-in Windows GUI regression checks: set TTS_GUI_TESTS=1 to run."""

import os
import time
import tkinter as tk
import unittest

from text_input_window import TextInputWindow


@unittest.skipUnless(os.environ.get("TTS_GUI_TESTS") == "1", "Requires a desktop session")
class TextInputFocusTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.window = TextInputWindow(self.root, lambda text: False)

    def tearDown(self):
        self.window.close()
        self.root.destroy()

    def pump(self, seconds=0.45):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.root.update()
            time.sleep(0.01)

    def test_first_open_focuses_editor(self):
        self.pump()
        self.assertEqual(self.root.focus_get(), self.window._text_widget)

    def test_existing_window_open_command_focuses_editor(self):
        import main

        self.pump()
        self.window._text_widget.insert("1.0", "Behåll texten")
        self.window._read_button.focus_force()
        self.root.update()
        previous = main.text_input_window_ref
        main.text_input_window_ref = self.window
        try:
            main.on_open_text_input()
            self.pump()
            self.assertEqual(self.root.focus_get(), self.window._text_widget)
            self.assertEqual(self.window._text_widget.get("1.0", "end-1c"), "Behåll texten")
        finally:
            main.text_input_window_ref = previous

    def test_minimized_window_is_restored(self):
        self.pump()
        self.window.win.iconify()
        self.root.update()
        self.assertEqual(self.window.win.state(), "iconic")
        self.window.show()
        self.pump()
        self.assertEqual(self.window.win.state(), "normal")
        self.assertEqual(self.root.focus_get(), self.window._text_widget)

    def test_pending_check_does_not_steal_focus_from_button(self):
        self.pump()
        self.window.show()
        self.root.update()
        self.window._read_button.focus_force()
        self.pump()
        self.assertEqual(self.root.focus_get(), self.window._read_button)

    def test_close_cancels_pending_focus(self):
        self.window.close()
        self.pump()
        self.assertIsNone(self.window._focus_after_id)
        self.assertFalse(self.window.show())


if __name__ == "__main__":
    unittest.main()

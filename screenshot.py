"""Screenshot overlay + Windows OCR.

Phase 1 (main thread): Full-screen transparent tkinter overlay for region selection.
Phase 2 (main thread, after 100 ms delay): Capture region with Pillow.
Phase 3 (daemon thread): Run Windows OCR via winsdk, return text to main thread.
"""

import asyncio
import ctypes
import io
import threading
import tkinter as tk

import keyboard
from PIL import ImageFilter, ImageGrab, ImageOps

import config_loader


def configure_dpi_awareness() -> None:
    """Make Tkinter and screenshots use real screen pixels on Windows."""
    if not hasattr(ctypes, "windll"):
        return

    user32 = ctypes.windll.user32
    shcore = getattr(ctypes.windll, "shcore", None)

    # Must be called before Tk creates any windows. Per-monitor v2 gives the
    # cleanest mapping between Tk root coordinates and ImageGrab pixels.
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass

    if shcore is not None:
        try:
            shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
            return
        except Exception:
            pass

    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass


def _virtual_screen_bbox() -> tuple[int, int, int, int]:
    """Return the full desktop bounds in physical pixels."""
    user32 = ctypes.windll.user32
    left = user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
    top = user32.GetSystemMetrics(77)  # SM_YVIRTUALSCREEN
    width = user32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
    height = user32.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN
    return left, top, left + width, top + height


def _tk_geometry_offset(value: int) -> str:
    return f"+{value}" if value >= 0 else str(value)


class ScreenshotOverlay:
    def __init__(self, root: tk.Tk, on_text_ready):
        self._root = root
        self._on_text_ready = on_text_ready  # called on main thread with the OCR text

        self._start_x = 0
        self._start_y = 0
        self._rect_id = None
        self._win: tk.Toplevel | None = None
        self._canvas: tk.Canvas | None = None
        self._esc_hook = None

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Open the full-screen selection overlay. Call from main thread."""
        left, top, right, bottom = _virtual_screen_bbox()

        self._win = tk.Toplevel(self._root)
        self._win.geometry(
            f"{right - left}x{bottom - top}"
            f"{_tk_geometry_offset(left)}{_tk_geometry_offset(top)}"
        )
        self._win.attributes("-topmost", True)
        self._win.attributes("-alpha", 0.25)
        self._win.configure(bg="black")
        self._win.overrideredirect(True)

        self._canvas = tk.Canvas(
            self._win,
            bg="black",
            cursor="crosshair",
            highlightthickness=0,
        )
        self._canvas.pack(fill=tk.BOTH, expand=True)

        self._canvas.bind("<ButtonPress-1>", self._on_press)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self._win.focus_force()
        self._win.grab_set()
        self._canvas.focus_set()

        # The keyboard library installs a low-level hook that intercepts keys
        # before tkinter sees them, so tkinter's <Escape> binding is unreliable.
        # Register a direct keyboard hook instead.
        self._esc_hook = keyboard.add_hotkey(
            "escape", lambda: self._root.after(0, self._close)
        )

    # ------------------------------------------------------------------
    # Mouse event handlers (main thread)
    # ------------------------------------------------------------------

    def _on_press(self, event: tk.Event) -> None:
        self._start_x = event.x_root
        self._start_y = event.y_root
        if self._rect_id is not None:
            self._canvas.delete(self._rect_id)
            self._rect_id = None

    def _on_drag(self, event: tk.Event) -> None:
        if self._rect_id is not None:
            self._canvas.delete(self._rect_id)
        # Convert root coords to canvas coords
        cx = self._canvas.winfo_rootx()
        cy = self._canvas.winfo_rooty()
        x0 = self._start_x - cx
        y0 = self._start_y - cy
        x1 = event.x_root - cx
        y1 = event.y_root - cy
        self._rect_id = self._canvas.create_rectangle(
            x0, y0, x1, y1,
            outline="#00AAFF",
            width=2,
            fill="",
        )

    def _close(self) -> None:
        """Destroy the overlay and remove the escape hook. Main thread only."""
        if self._esc_hook is not None:
            try:
                keyboard.remove_hotkey(self._esc_hook)
            except Exception:
                pass
            self._esc_hook = None
        if self._win is not None:
            self._win.destroy()
            self._win = None

    def _on_release(self, event: tk.Event) -> None:
        x1 = min(self._start_x, event.x_root)
        y1 = min(self._start_y, event.y_root)
        x2 = max(self._start_x, event.x_root)
        y2 = max(self._start_y, event.y_root)

        self._close()

        if x2 - x1 < 5 or y2 - y1 < 5:
            return  # ignore accidental clicks

        # Wait 100 ms for the DWM to fully remove the overlay before capturing
        self._root.after(100, lambda: self._capture(x1, y1, x2, y2))

    # ------------------------------------------------------------------
    # Capture + OCR
    # ------------------------------------------------------------------

    def _capture(self, x1: int, y1: int, x2: int, y2: int) -> None:
        """Grab the screen region and start OCR in a worker thread."""
        try:
            bbox = (int(x1), int(y1), int(x2), int(y2))
            print(f"[Screenshot] capture bbox={bbox}")
            img = ImageGrab.grab(bbox=bbox, all_screens=True)
            print(f"[Screenshot] captured image size: {img.size}")
        except Exception as exc:
            print(f"[Screenshot] Capture failed: {exc}")
            return

        threading.Thread(
            target=self._run_ocr,
            args=(img,),
            daemon=True,
        ).start()

    def _run_ocr(self, pil_image) -> None:
        """Run Windows OCR in a worker thread, then call back on main thread."""
        try:
            text = asyncio.run(self._ocr_async(pil_image))
        except Exception as exc:
            print(f"[OCR] Error: {exc}")
            text = ""

        print(f"[OCR] result: {repr(text)}")
        if text:
            self._root.after(0, lambda: self._on_text_ready(text))

    async def _ocr_async(self, pil_image) -> str:
        """Convert PIL image to a winsdk SoftwareBitmap and run OCR."""
        from winsdk.windows.media.ocr import OcrEngine
        from winsdk.windows.globalization import Language
        from winsdk.windows.graphics.imaging import BitmapDecoder
        from winsdk.windows.storage.streams import InMemoryRandomAccessStream, DataWriter

        # Determine OCR language
        lang_code = "sv" if config_loader.load().LANGUAGE == "sv" else "en-US"
        lang = Language(lang_code)

        if not OcrEngine.is_language_supported(lang):
            # Fallback: try without language hint (uses system default)
            engine = OcrEngine.try_create_from_user_profile_languages()
        else:
            engine = OcrEngine.try_create_from_language(lang)

        if engine is None:
            print(f"[OCR] No engine available for language '{lang_code}'")
            return ""

        # Encode PIL image as PNG into an in-memory WinRT stream
        pil_image = self._prepare_for_ocr(pil_image)
        buf = io.BytesIO()
        pil_image.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        stream = InMemoryRandomAccessStream()
        writer = DataWriter(stream)
        writer.write_bytes(png_bytes)
        await writer.store_async()
        await writer.flush_async()
        stream.seek(0)

        decoder = await BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()

        result = await engine.recognize_async(bitmap)
        return result.text

    @staticmethod
    def _prepare_for_ocr(pil_image):
        """Improve contrast and text size before Windows OCR sees the crop."""
        image = pil_image.convert("L")
        image = ImageOps.autocontrast(image)
        image = image.filter(ImageFilter.SHARPEN)

        width, height = image.size
        longest_side = max(width, height)
        scale = 1
        if longest_side < 900:
            scale = 3
        elif longest_side < 1400:
            scale = 2

        if scale > 1:
            image = image.resize((width * scale, height * scale))

        return image.convert("RGBA")

"""Small Windows PCM player with immediate buffer reset on stop."""

import ctypes
import queue
import threading
import time
from typing import Optional


WAVE_FORMAT_PCM = 1
WAVE_MAPPER = -1
CALLBACK_EVENT = 0x00050000
WHDR_DONE = 0x00000001


class WAVEFORMATEX(ctypes.Structure):
    _fields_ = [
        ("wFormatTag", ctypes.c_ushort),
        ("nChannels", ctypes.c_ushort),
        ("nSamplesPerSec", ctypes.c_uint),
        ("nAvgBytesPerSec", ctypes.c_uint),
        ("nBlockAlign", ctypes.c_ushort),
        ("wBitsPerSample", ctypes.c_ushort),
        ("cbSize", ctypes.c_ushort),
    ]


class WAVEHDR(ctypes.Structure):
    _fields_ = [
        ("lpData", ctypes.c_void_p),
        ("dwBufferLength", ctypes.c_uint),
        ("dwBytesRecorded", ctypes.c_uint),
        ("dwUser", ctypes.c_void_p),
        ("dwFlags", ctypes.c_uint),
        ("dwLoops", ctypes.c_uint),
        ("lpNext", ctypes.c_void_p),
        ("reserved", ctypes.c_void_p),
    ]


class _QueuedWaveBuffer:
    def __init__(self, data: bytes):
        self.data = ctypes.create_string_buffer(data)
        self.header = WAVEHDR(
            lpData=ctypes.cast(self.data, ctypes.c_void_p),
            dwBufferLength=len(data),
            dwBytesRecorded=0,
            dwUser=None,
            dwFlags=0,
            dwLoops=0,
            lpNext=None,
            reserved=None,
        )
        self.length = len(data)


class PcmAudioPlayer:
    def __init__(self, sample_rate: int, channels: int, bits_per_sample: int):
        self._sample_rate = sample_rate
        self._channels = channels
        self._bits_per_sample = bits_per_sample
        self._block_align = channels * bits_per_sample // 8
        self._bytes_per_ms = sample_rate * self._block_align / 1000
        self._target_buffer_bytes = self._aligned_bytes_for_ms(120)
        self._prebuffer_bytes = self._aligned_bytes_for_ms(240)
        self._max_queued_buffers = 6
        self._queue: queue.Queue[Optional[bytes]] = queue.Queue(maxsize=12)
        self._pending_input = bytearray()
        self._input_lock = threading.Lock()
        self._stop_requested = threading.Event()
        self._close_requested = threading.Event()
        self._closed = threading.Event()
        self._thread = threading.Thread(target=self._play_loop, daemon=True)
        self._wave_out = ctypes.c_void_p()
        self._event = None
        self._lock = threading.Lock()
        self._completed_bytes = 0
        self._submitted_bytes = 0
        self._playback_anchor_time: Optional[float] = None

    def start(self) -> None:
        self._thread.start()

    def write(self, data: bytes) -> None:
        if data and not self._stop_requested.is_set():
            chunks = []
            with self._input_lock:
                self._pending_input.extend(data)
                while len(self._pending_input) >= self._target_buffer_bytes:
                    chunks.append(bytes(self._pending_input[: self._target_buffer_bytes]))
                    del self._pending_input[: self._target_buffer_bytes]

            for chunk in chunks:
                self._put(chunk)

    def close(self) -> None:
        if self._close_requested.is_set():
            return
        self._close_requested.set()

        final_chunk = None
        with self._input_lock:
            if self._pending_input:
                final_chunk = bytes(self._pending_input)
                self._pending_input.clear()

        if final_chunk:
            self._put(final_chunk)
        self._put(None)

    def stop(self) -> None:
        self._stop_requested.set()
        with self._lock:
            if self._wave_out.value:
                ctypes.windll.winmm.waveOutReset(self._wave_out)
        self._clear_queue()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass

    def wait_closed(self, timeout: Optional[float] = None) -> bool:
        return self._closed.wait(timeout)

    def playback_position_ms(self) -> float:
        with self._lock:
            if self._playback_anchor_time is None:
                return 0.0

            elapsed_ms = max(0.0, (time.monotonic() - self._playback_anchor_time) * 1000)
            submitted_ms = self._submitted_bytes / self._bytes_per_ms
            completed_ms = self._completed_bytes / self._bytes_per_ms
            return min(max(elapsed_ms, completed_ms), submitted_ms)

    def _put(self, item: Optional[bytes]) -> None:
        while not self._stop_requested.is_set():
            try:
                self._queue.put(item, timeout=0.1)
                return
            except queue.Full:
                pass

    def _clear_queue(self) -> None:
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                return

    def _aligned_bytes_for_ms(self, duration_ms: int) -> int:
        size = int(self._bytes_per_ms * duration_ms)
        size -= size % self._block_align
        return max(size, self._block_align)

    def _play_loop(self) -> None:
        active_buffers: list[_QueuedWaveBuffer] = []
        try:
            self._open_device()
            self._run_output_loop(active_buffers)
        finally:
            self._close_device(active_buffers)
            self._closed.set()

    def _run_output_loop(self, active_buffers: list[_QueuedWaveBuffer]) -> None:
        input_closed = False
        output_started = False
        staged_buffers = []
        staged_bytes = 0

        while not self._stop_requested.is_set():
            self._reap_done_buffers(active_buffers)

            if input_closed and not active_buffers and not staged_buffers:
                break

            if not output_started:
                item = self._get_next_input(wait=True)
                if item is None:
                    input_closed = True
                elif item:
                    staged_buffers.append(item)
                    staged_bytes += len(item)

                if staged_buffers and (staged_bytes >= self._prebuffer_bytes or input_closed):
                    for data in staged_buffers:
                        self._submit_buffer(data, active_buffers)
                    staged_buffers.clear()
                    staged_bytes = 0
                    output_started = True
                continue

            while len(active_buffers) < self._max_queued_buffers and not input_closed:
                item = self._get_next_input(wait=False)
                if item is False:
                    break
                if item is None:
                    input_closed = True
                    break
                self._submit_buffer(item, active_buffers)

            if input_closed and not active_buffers:
                break

            ctypes.windll.kernel32.WaitForSingleObject(self._event, 15)

    def _get_next_input(self, wait: bool):
        try:
            if wait:
                return self._queue.get(timeout=0.05)
            return self._queue.get_nowait()
        except queue.Empty:
            return False

    def _open_device(self) -> None:
        block_align = self._channels * self._bits_per_sample // 8
        fmt = WAVEFORMATEX(
            wFormatTag=WAVE_FORMAT_PCM,
            nChannels=self._channels,
            nSamplesPerSec=self._sample_rate,
            nAvgBytesPerSec=self._sample_rate * block_align,
            nBlockAlign=block_align,
            wBitsPerSample=self._bits_per_sample,
            cbSize=0,
        )

        self._event = ctypes.windll.kernel32.CreateEventW(None, False, False, None)
        result = ctypes.windll.winmm.waveOutOpen(
            ctypes.byref(self._wave_out),
            WAVE_MAPPER,
            ctypes.byref(fmt),
            self._event,
            0,
            CALLBACK_EVENT,
        )
        if result != 0:
            raise RuntimeError(f"waveOutOpen failed: {result}")

    def _submit_buffer(self, data: bytes, active_buffers: list[_QueuedWaveBuffer]) -> None:
        if self._stop_requested.is_set():
            return

        wave_buffer = _QueuedWaveBuffer(data)
        with self._lock:
            if not self._wave_out.value:
                return
            result = ctypes.windll.winmm.waveOutPrepareHeader(
                self._wave_out,
                ctypes.byref(wave_buffer.header),
                ctypes.sizeof(wave_buffer.header),
            )
            if result != 0:
                raise RuntimeError(f"waveOutPrepareHeader failed: {result}")

            if self._submitted_bytes == self._completed_bytes:
                completed_ms = self._completed_bytes / self._bytes_per_ms
                self._playback_anchor_time = time.monotonic() - (completed_ms / 1000)

            result = ctypes.windll.winmm.waveOutWrite(
                self._wave_out,
                ctypes.byref(wave_buffer.header),
                ctypes.sizeof(wave_buffer.header),
            )
            if result != 0:
                ctypes.windll.winmm.waveOutUnprepareHeader(
                    self._wave_out,
                    ctypes.byref(wave_buffer.header),
                    ctypes.sizeof(wave_buffer.header),
                )
                raise RuntimeError(f"waveOutWrite failed: {result}")

            self._submitted_bytes += wave_buffer.length

        active_buffers.append(wave_buffer)

    def _reap_done_buffers(self, active_buffers: list[_QueuedWaveBuffer]) -> None:
        remaining = []
        for wave_buffer in active_buffers:
            if not (wave_buffer.header.dwFlags & WHDR_DONE):
                remaining.append(wave_buffer)
                continue

            with self._lock:
                if self._wave_out.value:
                    ctypes.windll.winmm.waveOutUnprepareHeader(
                        self._wave_out,
                        ctypes.byref(wave_buffer.header),
                        ctypes.sizeof(wave_buffer.header),
                    )
                    self._completed_bytes += wave_buffer.length

        active_buffers[:] = remaining

    def _close_device(self, active_buffers: list[_QueuedWaveBuffer]) -> None:
        with self._lock:
            if self._wave_out.value:
                ctypes.windll.winmm.waveOutReset(self._wave_out)
                for wave_buffer in active_buffers:
                    ctypes.windll.winmm.waveOutUnprepareHeader(
                        self._wave_out,
                        ctypes.byref(wave_buffer.header),
                        ctypes.sizeof(wave_buffer.header),
                    )
                active_buffers.clear()
                ctypes.windll.winmm.waveOutClose(self._wave_out)
                self._wave_out = ctypes.c_void_p()

        if self._event:
            ctypes.windll.kernel32.CloseHandle(self._event)
            self._event = None

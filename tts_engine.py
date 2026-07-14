"""TTS providers for Azure Speech and local Piper.

``speak`` runs in a dedicated daemon thread.  Both providers write PCM audio
to the same Windows player and communicate with the Tkinter thread only via
the shared word queue.
"""

import os
import queue
import re
import sys
import threading
from typing import Optional

import azure.cognitiveservices.speech as speechsdk

import config_loader
from wave_player import PcmAudioPlayer


TTS_SAMPLE_RATE = 24000
TTS_CHANNELS = 1
TTS_BITS_PER_SAMPLE = 16
_SENTENCE_BREAK_RE = re.compile(
    r"(?:[.!?\u2026]+[\"'\u2019\u201d\u00bb\)\]\}]*\s+|\r?\n+)",
    re.UNICODE,
)
_STRESS_MARKS = frozenset({"\u02c8", "\u02cc", "'", "\u00b4"})
_LENGTH_MARKS = frozenset({"\u02d0", "\u02d1"})
_IPA_VOWELS = frozenset(
    "aeiouy\u00e5\u00e4\u00f6\u00e6\u0153\u0250\u0251\u0252\u025b"
    "\u025c\u025e\u0259\u025a\u025d\u0268\u026a\u028a\u028c\u0264\u026f"
)
_WORD_RE = re.compile(r"\w+(?:['’\-]\w+)*", re.UNICODE)


class _AzureAudioOutputCallback(speechsdk.audio.PushAudioOutputStreamCallback):
    def __init__(self, player: PcmAudioPlayer, stop_requested: threading.Event):
        super().__init__()
        self._player = player
        self._stop_requested = stop_requested

    def write(self, audio_buffer: memoryview) -> int:
        if not self._stop_requested.is_set():
            self._player.write(bytes(audio_buffer))
        return len(audio_buffer)

    def close(self) -> None:
        self._player.close()


class TTSEngine:
    def __init__(self, word_queue: queue.Queue):
        self._word_queue = word_queue
        self._synthesizer: Optional[speechsdk.SpeechSynthesizer] = None
        self._audio_player: Optional[PcmAudioPlayer] = None
        self._lock = threading.Lock()
        self._stop_requested = threading.Event()
        self.message_token = id(self)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def speak(self, display_text: str, ssml_text: str, tags: Optional[list] = None) -> None:
        """Synthesize text with the configured provider and emit queue events."""
        self._stop_requested.clear()
        cfg = config_loader.load()

        self._word_queue.put(
            {
                "type": "start",
                "token": self.message_token,
                "text": display_text,
                "tags": tags,
            }
        )

        try:
            if str(cfg.TTS_PROVIDER).lower() == "azure":
                self._speak_azure(cfg, display_text, ssml_text)
            else:
                self._speak_piper(cfg, display_text)
        except Exception as exc:
            print(f"[TTS] Exception during synthesis: {exc}")
            provider_name = "Azure" if str(cfg.TTS_PROVIDER).lower() == "azure" else "Piper"
            self._emit_error(f"{provider_name} TTS-fel", str(exc))
        finally:
            self._close_active_player()
            self._word_queue.put({"type": "done", "token": self.message_token})

    def stop(self) -> None:
        """Stop active synthesis without blocking the caller. Thread-safe."""
        self._stop_requested.set()
        with self._lock:
            synth = self._synthesizer
            audio_player = self._audio_player
            self._synthesizer = None
            self._audio_player = None
        if audio_player is not None:
            audio_player.stop()
        if synth is not None:
            threading.Thread(
                target=self._stop_synthesizer,
                args=(synth,),
                daemon=True,
            ).start()

    @staticmethod
    def _stop_synthesizer(synth: speechsdk.SpeechSynthesizer) -> None:
        try:
            synth.stop_speaking_async().get()
        except Exception:
            pass

    def playback_position_ms(self) -> float:
        with self._lock:
            audio_player = self._audio_player
        if audio_player is None:
            return 0.0
        return audio_player.playback_position_ms()

    # ------------------------------------------------------------------
    # Piper provider
    # ------------------------------------------------------------------

    def _speak_piper(self, cfg, display_text: str) -> None:
        try:
            from piper import PiperVoice
        except ImportError as exc:
            raise RuntimeError(
                "Piper är inte installerat. Kör .venv\\Scripts\\python.exe "
                "-m pip install -r requirements.txt."
            ) from exc

        model_path = _resolve_piper_model_path(cfg.PIPER_MODEL_PATH)
        if not os.path.isfile(model_path):
            raise FileNotFoundError(
                f"Piper-modellen saknas: {model_path}. "
                "Lägg sv_SE-nst-medium.onnx och dess .onnx.json bredvid modellen."
            )

        print(f"[TTS] Loading Piper model: {model_path}")
        voice = PiperVoice.load(model_path)
        audio_chunks = []
        timing_segments = []
        sample_rate = None
        sample_width = None
        channels = None
        audio_offset_ms = 0.0

        # The installed voices do not expose word alignments, but the exact
        # duration of each segment gives the estimator a fresh sentence anchor.
        for segment_text, words, segment_end in _split_piper_segments(display_text):
            segment_bytes = []
            segment_duration_ms = 0.0
            for chunk in voice.synthesize(segment_text):
                if self._stop_requested.is_set():
                    return
                if sample_rate is None:
                    sample_rate = chunk.sample_rate
                    sample_width = chunk.sample_width
                    channels = chunk.sample_channels
                chunk_bytes = chunk.audio_int16_bytes
                segment_bytes.append(chunk_bytes)
                segment_duration_ms += (
                    len(chunk_bytes)
                    / (chunk.sample_rate * chunk.sample_width * chunk.sample_channels)
                    * 1000
                )

            if not segment_bytes:
                continue

            audio_chunks.extend(segment_bytes)
            timing_segments.append(
                (audio_offset_ms, segment_duration_ms, words, segment_end)
            )
            audio_offset_ms += segment_duration_ms

        if not audio_chunks or not sample_rate:
            raise RuntimeError("Piper gav inget ljud för texten.")

        self._emit_estimated_word_events(voice, display_text, timing_segments)

        player = PcmAudioPlayer(sample_rate, channels, sample_width * 8)
        with self._lock:
            self._audio_player = player
        player.start()
        for audio_data in audio_chunks:
            if self._stop_requested.is_set():
                break
            player.write(audio_data)
        player.close()
        player.wait_closed()
        with self._lock:
            if self._audio_player is player:
                self._audio_player = None

    def _emit_estimated_word_events(self, voice, display_text: str, timing_segments) -> None:
        """Emit sentence-anchored, pronunciation-weighted Piper timings.

        Each segment uses its exact audio duration while word lengths are
        estimated from eSpeak phonemes and punctuation pauses. Azure continues
        to use the provider's exact word-boundary events.
        """
        pronunciation_cache = {}

        for segment_start_ms, duration_ms, words, segment_end in timing_segments:
            word_weights = []
            gap_weights = []
            for index, match in enumerate(words):
                word = match.group(0)
                cache_key = word.casefold()
                if cache_key not in pronunciation_cache:
                    pronunciation_cache[cache_key] = _pronunciation_weight(voice, word)
                word_weights.append(pronunciation_cache[cache_key])

                next_start = (
                    words[index + 1].start()
                    if index + 1 < len(words)
                    else segment_end
                )
                gap_weights.append(
                    _pause_weight(
                        display_text[match.end():next_start],
                        final_word=index + 1 == len(words),
                    )
                )

            # Account for Piper's natural onset before the first audible word.
            leading_weight = 0.8
            total_weight = leading_weight + sum(word_weights) + sum(gap_weights)
            elapsed_weight = leading_weight

            for match, word_weight, gap_weight in zip(
                words, word_weights, gap_weights
            ):
                offset_ms = segment_start_ms + duration_ms * (
                    elapsed_weight / max(total_weight, 1.0)
                )
                self._word_queue.put(
                    {
                        "type": "word",
                        "token": self.message_token,
                        "offset": match.start(),
                        "length": len(match.group(0)),
                        "audio_offset_ms": offset_ms,
                    }
                )
                elapsed_weight += word_weight + gap_weight

    # ------------------------------------------------------------------
    # Azure provider
    # ------------------------------------------------------------------

    def _speak_azure(self, cfg, display_text: str, ssml_text: str) -> None:
        if not cfg.AZURE_SPEECH_KEY or cfg.AZURE_SPEECH_KEY == "your-key-here":
            self._emit_error(
                "Azure API-nyckel saknas",
                "Fyll i en giltig Azure Speech-nyckel i Inställningar.",
            )
            return

        speech_cfg = speechsdk.SpeechConfig(
            subscription=cfg.AZURE_SPEECH_KEY,
            region=cfg.AZURE_SPEECH_REGION,
        )
        speech_cfg.speech_synthesis_voice_name = cfg.AZURE_VOICE_NAME
        speech_cfg.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Raw24Khz16BitMonoPcm
        )

        audio_player = PcmAudioPlayer(TTS_SAMPLE_RATE, TTS_CHANNELS, TTS_BITS_PER_SAMPLE)
        audio_player.start()
        audio_stream = speechsdk.audio.PushAudioOutputStream(
            _AzureAudioOutputCallback(audio_player, self._stop_requested)
        )
        audio_cfg = speechsdk.audio.AudioOutputConfig(stream=audio_stream)
        synth = speechsdk.SpeechSynthesizer(
            speech_config=speech_cfg,
            audio_config=audio_cfg,
        )

        with self._lock:
            self._synthesizer = synth
            self._audio_player = audio_player

        last_search_pos = 0

        def on_word_boundary(evt: speechsdk.SpeechSynthesisWordBoundaryEventArgs):
            nonlocal last_search_pos
            if self._stop_requested.is_set() or not evt.text:
                return
            found_idx = display_text.lower().find(evt.text.lower(), last_search_pos)
            if found_idx == -1:
                return
            last_search_pos = found_idx + len(evt.text)
            self._word_queue.put(
                {
                    "type": "word",
                    "token": self.message_token,
                    "offset": found_idx,
                    "length": len(evt.text),
                    "audio_offset_ms": evt.audio_offset / 10000,
                }
            )

        synth.synthesis_word_boundary.connect(on_word_boundary)
        synthesis_done = threading.Event()
        final_result = {"result": None}

        def on_synthesis_done(evt: speechsdk.SpeechSynthesisEventArgs):
            final_result["result"] = evt.result
            synthesis_done.set()

        synth.synthesis_completed.connect(on_synthesis_done)
        synth.synthesis_canceled.connect(on_synthesis_done)

        print("[TTS] Synthesizing with Azure SSML...")
        result = None
        try:
            start_result = synth.start_speaking_ssml_async(ssml_text).get()
            if start_result.reason == speechsdk.ResultReason.Canceled:
                result = start_result
            else:
                while not synthesis_done.wait(0.1):
                    if self._stop_requested.is_set():
                        break
                result = final_result["result"] or start_result

            if result.reason == speechsdk.ResultReason.Canceled:
                details = speechsdk.SpeechSynthesisCancellationDetails(result)
                print(f"[TTS] Azure error: {details.error_details}")
                if not self._stop_requested.is_set():
                    self._emit_error("Azure TTS misslyckades", _friendly_error(details.error_details))
            elif result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                print("[TTS] Azure success")
        finally:
            with self._lock:
                if self._synthesizer is synth:
                    self._synthesizer = None
            audio_player.close()
            audio_player.wait_closed()
            with self._lock:
                if self._audio_player is audio_player:
                    self._audio_player = None

    # ------------------------------------------------------------------

    def _emit_error(self, title: str, message: str) -> None:
        self._word_queue.put(
            {
                "type": "error",
                "token": self.message_token,
                "title": title,
                "message": message,
            }
        )

    def _close_active_player(self) -> None:
        with self._lock:
            player = self._audio_player
            self._audio_player = None
        if player is not None:
            player.close()
            player.wait_closed()


def _split_piper_segments(display_text: str):
    """Split text into sentence-like spans while preserving word offsets."""
    words = list(_WORD_RE.finditer(display_text))
    if not words:
        return []

    segments = []
    first_word_index = 0
    for index in range(len(words) - 1):
        gap = display_text[words[index].end():words[index + 1].start()]
        if not _SENTENCE_BREAK_RE.search(gap):
            continue

        segment_start = words[first_word_index].start()
        segment_end = words[index + 1].start()
        segments.append(
            (
                display_text[segment_start:segment_end],
                words[first_word_index:index + 1],
                segment_end,
            )
        )
        first_word_index = index + 1

    segment_start = words[first_word_index].start()
    segment_end = len(display_text)
    segments.append(
        (
            display_text[segment_start:segment_end],
            words[first_word_index:],
            segment_end,
        )
    )
    return segments


def _pronunciation_weight(voice, word: str) -> float:
    """Estimate spoken word length from the voice's eSpeak phonemes."""
    weight = 0.0
    try:
        sentence_phonemes = voice.phonemize(word)
    except Exception:
        sentence_phonemes = []

    for phonemes in sentence_phonemes:
        for phoneme in phonemes:
            for symbol in phoneme:
                if symbol in _STRESS_MARKS or not symbol.strip():
                    continue
                if symbol in _LENGTH_MARKS:
                    weight += 0.7
                elif symbol.casefold() in _IPA_VOWELS:
                    weight += 1.3
                else:
                    weight += 1.0

    # Character length is a safe fallback for numbers and unusual symbols.
    return max(weight, min(max(len(word) * 0.55, 1.0), 5.0))


def _pause_weight(gap: str, final_word: bool = False) -> float:
    """Estimate the relative pause after a word from nearby punctuation."""
    weight = 0.35 if any(char.isspace() for char in gap) else 0.15
    if "\n" in gap or "\r" in gap:
        weight = max(weight, 1.8)
    if any(mark in gap for mark in ".!?\u2026"):
        weight = max(weight, 2.2)
    elif any(mark in gap for mark in ";:"):
        weight = max(weight, 1.4)
    elif "," in gap:
        weight = max(weight, 0.9)
    elif any(mark in gap for mark in "-\u2013\u2014"):
        weight = max(weight, 0.7)

    if final_word:
        weight = max(weight, 0.65)
    return weight


def _resolve_piper_model_path(model_path: str) -> str:
    if os.path.isabs(model_path):
        return model_path
    external_path = os.path.join(config_loader.APP_DIR, model_path)
    if os.path.isfile(external_path):
        return external_path

    # In a PyInstaller one-file build bundled data is extracted to _MEIPASS.
    bundle_dir = getattr(sys, "_MEIPASS", "")
    if bundle_dir:
        bundled_path = os.path.join(bundle_dir, model_path)
        if os.path.isfile(bundled_path):
            return bundled_path
    return external_path


def _friendly_error(error_details: str) -> str:
    if "401" in error_details or "Authentication error" in error_details:
        return (
            "Azure nekade API-nyckeln eller regionen. Kontrollera att nyckeln "
            "kommer från rätt Speech-resurs och att regionen stämmer."
        )
    return error_details or "Okänt fel från Azure Speech."

"""Azure Speech SDK TTS wrapper.

speak() is designed to run in a dedicated daemon thread.
stop() is thread-safe and can be called from any thread.
Word boundary events are pushed to the shared word_queue so the
main thread can update the playback window without any tkinter
calls happening off the main thread.
"""

import queue
import threading

import azure.cognitiveservices.speech as speechsdk

import config_loader


class TTSEngine:
    def __init__(self, word_queue: queue.Queue):
        self._word_queue = word_queue
        self._synthesizer: speechsdk.SpeechSynthesizer | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def speak(self, text: str) -> None:
        """Synthesise text and emit word-boundary messages. Blocks until done."""
        cfg = config_loader.load()

        speech_cfg = speechsdk.SpeechConfig(
            subscription=cfg.AZURE_SPEECH_KEY,
            region=cfg.AZURE_SPEECH_REGION,
        )
        speech_cfg.speech_synthesis_voice_name = cfg.AZURE_VOICE_NAME

        audio_cfg = speechsdk.audio.AudioOutputConfig(use_default_speaker=True)
        synth = speechsdk.SpeechSynthesizer(
            speech_config=speech_cfg,
            audio_config=audio_cfg,
        )

        with self._lock:
            self._synthesizer = synth

        def on_word_boundary(evt: speechsdk.SessionEventArgs):
            self._word_queue.put(
                {
                    "type": "word",
                    "offset": evt.text_offset,
                    "length": evt.word_length,
                }
            )

        synth.synthesis_word_boundary.connect(on_word_boundary)

        # Signal playback window to open
        self._word_queue.put({"type": "start", "text": text})

        print(f"[DEBUG] Starting synthesis for: {repr(text[:60])}")
        result: speechsdk.SpeechSynthesisResult = synth.speak_text_async(text).get()
        print(f"[DEBUG] Synthesis result: {result.reason}")

        if result.reason == speechsdk.ResultReason.Canceled:
            details = speechsdk.SpeechSynthesisCancellationDetails(result)
            print(f"[TTS] Cancelled: {details.reason} — {details.error_details}")
        elif result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            print("[DEBUG] Audio synthesis completed successfully")

        self._word_queue.put({"type": "done"})

        with self._lock:
            self._synthesizer = None

    def stop(self) -> None:
        """Stop active synthesis. Thread-safe."""
        with self._lock:
            synth = self._synthesizer
            self._synthesizer = None
        if synth is not None:
            try:
                synth.stop_speaking_async().get()
            except Exception:
                pass

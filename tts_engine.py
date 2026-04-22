"""Azure Speech SDK TTS wrapper.

speak() is designed to run in a dedicated daemon thread.
stop() is thread-safe and can be called from any thread.
Word boundary events are pushed to the shared word_queue so the
main thread can update the playback window without any tkinter
calls happening off the main thread.
"""

import queue
import threading
from typing import Optional

import azure.cognitiveservices.speech as speechsdk

import config_loader


class TTSEngine:
    def __init__(self, word_queue: queue.Queue):
        self._word_queue = word_queue
        self._synthesizer: Optional[speechsdk.SpeechSynthesizer] = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def speak(self, display_text: str, ssml_text: str, tags: Optional[list] = None) -> None:
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

        # State to track word matching in display_text
        self._last_search_pos = 0

        def on_word_boundary(evt: speechsdk.SpeechSynthesisWordBoundaryEventArgs):
            # When using SSML, evt.text_offset is relative to the SSML string (including tags).
            # To highlight correctly, we search for the word text in our display_text.
            word = evt.text
            if not word:
                return

            # Find the word in the display text starting from the last known position
            # This handles duplicate words correctly by progressing through the text.
            found_idx = display_text.lower().find(word.lower(), self._last_search_pos)
            
            if found_idx != -1:
                self._last_search_pos = found_idx + len(word)
                self._word_queue.put(
                    {
                        "type": "word",
                        "offset": found_idx,
                        "length": len(word),
                    }
                )

        synth.synthesis_word_boundary.connect(on_word_boundary)

        # Signal playback window to open
        self._word_queue.put({"type": "start", "text": display_text, "tags": tags})

        print(f"[TTS] Synthesizing with SSML...")
        try:
            result = synth.speak_ssml_async(ssml_text).get()
            
            if result.reason == speechsdk.ResultReason.Canceled:
                details = speechsdk.SpeechSynthesisCancellationDetails(result)
                print(f"[TTS] Error: {details.reason}")
                print(f"[TTS] Error Details: {details.error_details}")
            elif result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                print("[TTS] Success")
            else:
                print(f"[TTS] Stopped with reason: {result.reason}")
                
        except Exception as e:
            print(f"[TTS] Exception during synthesis: {e}")

        self._word_queue.put({"type": "done"})

        with self._lock:
            self._synthesizer = None

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

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
from wave_player import PcmAudioPlayer


TTS_SAMPLE_RATE = 24000
TTS_CHANNELS = 1
TTS_BITS_PER_SAMPLE = 16


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
        """Synthesise text and emit word-boundary messages. Blocks until done."""
        self._stop_requested.clear()
        cfg = config_loader.load()

        if not cfg.AZURE_SPEECH_KEY or cfg.AZURE_SPEECH_KEY == "your-key-here":
            self._word_queue.put(
                {
                    "type": "error",
                    "token": self.message_token,
                    "title": "Azure API-nyckel saknas",
                    "message": "Fyll i en giltig Azure Speech-nyckel i Inställningar.",
                }
            )
            self._word_queue.put({"type": "done", "token": self.message_token})
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

        # State to track word matching in display_text.
        self._last_search_pos = 0

        def on_word_boundary(evt: speechsdk.SpeechSynthesisWordBoundaryEventArgs):
            if self._stop_requested.is_set():
                return

            # When using SSML, evt.text_offset is relative to the SSML string
            # (including tags). Search the display text instead.
            word = evt.text
            if not word:
                return

            # Handles duplicate words correctly by progressing through the text.
            found_idx = display_text.lower().find(word.lower(), self._last_search_pos)

            if found_idx != -1:
                self._last_search_pos = found_idx + len(word)
                self._word_queue.put(
                    {
                        "type": "word",
                        "token": self.message_token,
                        "offset": found_idx,
                        "length": len(word),
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

        self._word_queue.put(
            {
                "type": "start",
                "token": self.message_token,
                "text": display_text,
                "tags": tags,
            }
        )

        print("[TTS] Synthesizing with SSML...")
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
                print(f"[TTS] Error: {details.reason}")
                print(f"[TTS] Error Details: {details.error_details}")
                if not self._stop_requested.is_set():
                    self._word_queue.put(
                        {
                            "type": "error",
                            "token": self.message_token,
                            "title": "Azure TTS misslyckades",
                            "message": _friendly_error(details.error_details),
                        }
                    )
            elif result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                print("[TTS] Success")
            else:
                print(f"[TTS] Stopped with reason: {result.reason}")

        except Exception as e:
            print(f"[TTS] Exception during synthesis: {e}")
            self._word_queue.put(
                {
                    "type": "error",
                    "token": self.message_token,
                    "title": "Azure TTS-fel",
                    "message": str(e),
                }
            )

        if result is not None:
            if result.reason == speechsdk.ResultReason.Canceled:
                details = speechsdk.SpeechSynthesisCancellationDetails(result)
                print(f"[TTS] Cancelled: {details.reason} - {details.error_details}")
            elif result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                print("[DEBUG] Audio synthesis completed successfully")

        with self._lock:
            if self._synthesizer is synth:
                self._synthesizer = None

        audio_player.close()
        audio_player.wait_closed()

        with self._lock:
            if self._audio_player is audio_player:
                self._audio_player = None

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


def _friendly_error(error_details: str) -> str:
    if "401" in error_details or "Authentication error" in error_details:
        return (
            "Azure nekade API-nyckeln eller regionen. Kontrollera att nyckeln "
            "kommer från rätt Speech-resurs och att regionen stämmer."
        )
    return error_details or "Okänt fel från Azure Speech."

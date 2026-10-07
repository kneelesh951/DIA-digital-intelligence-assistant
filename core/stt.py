"""
core/stt.py

Offline, multilingual (en/hi/de) speech-to-text using faster-whisper.

Two activation modes (set via config.yaml > app.activation_mode):

  push_to_talk  — hold TALK button / SPACE. Stream kept persistently
                  open; buffering toggled on press/release. Fixes the
                  macOS bug where re-creating sd.InputStream after close
                  sometimes fails silently.

  always_on     — background VAD loop. Detects speech automatically
                  using RMS energy threshold, collects audio until
                  silence, transcribes, fires callback. No button press
                  needed — just speak.
"""

import threading
import time as _time
from typing import Callable, Optional

import numpy as np

SAMPLE_RATE   = 16000   # Whisper expects 16kHz mono
CHUNK_SECS    = 0.1     # VAD chunk size (100 ms)
CHUNK_FRAMES  = int(SAMPLE_RATE * CHUNK_SECS)

# VAD tuning — raise ENERGY_THRESHOLD if ARIA triggers on background noise
ENERGY_THRESHOLD  = 0.012   # RMS level considered "speech"
SPEECH_ON_CHUNKS  = 3       # consecutive loud chunks → start collecting
SILENCE_OFF_CHUNKS = 10     # consecutive quiet chunks → end of utterance
PRE_ROLL_CHUNKS   = 5       # chunks to prepend before speech detected
MIN_SPEECH_CHUNKS = 4       # ignore utterances shorter than this


class Transcriber:
    def __init__(self, config: dict, on_warning=None):
        self.cfg        = config["stt"]
        self.on_warning = on_warning or (lambda msg: None)
        self._model     = None

        # Shared persistent stream
        self._stream    = None
        self._stream_lock = threading.Lock()

        # Push-to-talk state
        self._ptt_frames: list[np.ndarray] = []
        self._ptt_recording = False
        self._ptt_lock = threading.Lock()

        # Always-on state
        self._always_on        = False
        self._always_on_thread: Optional[threading.Thread] = None

        # Post-TTS mute: set to future timestamp to suppress VAD until then
        self._vad_muted_until: float = 0.0

    # ── Model ──────────────────────────────────────────────────────────────

    def _ensure_model(self):
        if self._model is not None:
            return
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            self.on_warning("faster-whisper not installed. Run: pip install -r requirements.txt")
            raise
        self._model = WhisperModel(
            self.cfg["model_size"],
            device=self.cfg.get("device", "cpu"),
            compute_type=self.cfg.get("compute_type", "int8"),
        )

    # ── Persistent stream ──────────────────────────────────────────────────

    def _ensure_stream(self, callback):
        """Open the sounddevice input stream if it isn't already open."""
        with self._stream_lock:
            if self._stream and self._stream.active:
                return
            try:
                import sounddevice as sd
            except ImportError:
                self.on_warning("sounddevice not installed. Run: pip install -r requirements.txt")
                raise
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=CHUNK_FRAMES,
                callback=callback,
            )
            self._stream.start()

    def _close_stream(self):
        with self._stream_lock:
            if self._stream:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None

    # ── Transcription helper ───────────────────────────────────────────────

    def _transcribe(self, frames: list[np.ndarray], language_hint: Optional[str] = None) -> str:
        if not frames:
            return ""
        audio = np.concatenate(frames, axis=0).flatten()
        if audio.size < SAMPLE_RATE * 0.3:
            return ""
        self._ensure_model()
        lang = language_hint if language_hint in self.cfg.get("languages", []) else None
        segments, _ = self._model.transcribe(audio, language=lang, vad_filter=True)
        return " ".join(s.text.strip() for s in segments).strip()

    # ── Push-to-talk ───────────────────────────────────────────────────────

    def start_recording(self):
        """Begin buffering microphone audio (PTT press)."""
        def _ptt_callback(indata, _frames, _time_info, status):
            if status:
                self.on_warning(f"Mic: {status}")
            with self._ptt_lock:
                if self._ptt_recording:
                    self._ptt_frames.append(indata.copy())

        with self._ptt_lock:
            if self._ptt_recording:
                return
            self._ptt_frames = []
            self._ptt_recording = True

        self._ensure_stream(_ptt_callback)

    def stop_recording_and_transcribe(self, language_hint: Optional[str] = None) -> str:
        """Stop buffering and transcribe captured audio (PTT release)."""
        with self._ptt_lock:
            self._ptt_recording = False
            frames = list(self._ptt_frames)
            self._ptt_frames = []

        # Don't close the stream — keep it warm for the next press
        return self._transcribe(frames, language_hint)

    # ── Always-on VAD ──────────────────────────────────────────────────────

    def start_always_on(
        self,
        on_speech: Callable[[str], None],
        on_state: Optional[Callable[[str], None]] = None,
        language_hint: Optional[str] = None,
    ):
        """
        Start the always-on VAD loop in a background thread.

        on_speech(text)  — called with the transcribed text when speech ends
        on_state(state)  — called with 'listening'|'processing'|'idle'
                           so the UI can update its animation
        """
        if self._always_on:
            return
        self._always_on = True
        self._always_on_thread = threading.Thread(
            target=self._vad_loop,
            args=(on_speech, on_state or (lambda s: None), language_hint),
            daemon=True,
        )
        self._always_on_thread.start()

    def stop_always_on(self):
        self._always_on = False
        self._close_stream()

    def mute_vad(self, seconds: float):
        """Suppress VAD transcription for `seconds` after DIA finishes speaking."""
        self._vad_muted_until = _time.time() + seconds

    def _vad_loop(
        self,
        on_speech: Callable[[str], None],
        on_state: Callable[[str], None],
        language_hint: Optional[str],
    ):
        """Background VAD loop. Runs until self._always_on is False."""
        import queue as q_mod
        audio_q: q_mod.Queue = q_mod.Queue()

        def _vad_callback(indata, _frames, _time_info, status):
            if status:
                self.on_warning(f"Mic: {status}")
            audio_q.put(indata.copy())

        self._ensure_stream(_vad_callback)

        pre_roll:    list[np.ndarray] = []
        speech_buf:  list[np.ndarray] = []
        loud_count   = 0
        quiet_count  = 0
        collecting   = False

        while self._always_on:
            try:
                chunk = audio_q.get(timeout=0.5)
            except Exception:
                continue

            # Post-TTS mute: drop audio and reset VAD state so DIA's
            # own voice (picked up by mic) is never transcribed as user input.
            if _time.time() < self._vad_muted_until:
                if collecting:
                    collecting = False
                    speech_buf = []
                    loud_count = quiet_count = 0
                    on_state("idle")
                pre_roll = []
                continue

            rms = float(np.sqrt(np.mean(chunk ** 2)))
            is_loud = rms > ENERGY_THRESHOLD

            if is_loud:
                loud_count  += 1
                quiet_count  = 0
            else:
                quiet_count += 1
                loud_count   = 0

            if not collecting:
                # Maintain a short pre-roll buffer
                pre_roll.append(chunk)
                if len(pre_roll) > PRE_ROLL_CHUNKS:
                    pre_roll.pop(0)

                if loud_count >= SPEECH_ON_CHUNKS:
                    # Speech started — begin collecting
                    collecting  = True
                    speech_buf  = list(pre_roll)
                    pre_roll    = []
                    loud_count  = 0
                    on_state("listening")
            else:
                speech_buf.append(chunk)

                if quiet_count >= SILENCE_OFF_CHUNKS:
                    # Silence long enough → end of utterance
                    collecting  = False
                    quiet_count = 0
                    on_state("processing")

                    if len(speech_buf) >= MIN_SPEECH_CHUNKS:
                        lang = language_hint() if callable(language_hint) else language_hint
                        text = self._transcribe(speech_buf, lang)
                        if text:
                            on_speech(text)

                    speech_buf = []
                    on_state("idle")

        self._close_stream()

    # ── File transcription (testing) ───────────────────────────────────────

    def transcribe_file(self, path: str, language_hint: Optional[str] = None) -> str:
        self._ensure_model()
        lang = language_hint if language_hint in self.cfg.get("languages", []) else None
        segments, _ = self._model.transcribe(path, language=lang, vad_filter=True)
        return " ".join(s.text.strip() for s in segments).strip()

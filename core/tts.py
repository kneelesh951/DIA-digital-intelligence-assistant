"""
core/tts.py

Text-to-speech using macOS's built-in `say` command — offline, free,
zero extra dependencies. Wraps voice selection (core/voices.py) so
callers just say "speak this, in German, male" and don't worry about
which exact voice name that maps to on this particular Mac.
"""

import re
import subprocess
import threading
from typing import Optional

from core.voices import resolve_voice, describe_missing, list_installed_voices


def _preprocess(text: str) -> str:
    """Make speech more natural by injecting macOS say pause markers."""
    # Spell out common symbols so they aren't skipped or mispronounced
    text = re.sub(r'(\d+)%', r'\1 percent', text)
    text = re.sub(r'\$(\d+(?:\.\d+)?)', r'\1 dollars', text)
    text = re.sub(r'°C', ' degrees Celsius', text)
    text = re.sub(r'°F', ' degrees Fahrenheit', text)
    # Add breathing-room pauses using say's embedded speech commands
    text = re.sub(r'([.!?])\s+', r'\1 [[slnc 280]] ', text)
    text = re.sub(r'([;:])\s+', r'\1 [[slnc 160]] ', text)
    text = re.sub(r',\s+', r', [[slnc 90]] ', text)
    # Strip leftover markdown that would be read literally
    text = re.sub(r'\*+', '', text)
    text = re.sub(r'#+\s*', '', text)
    return text.strip()


class Speaker:
    def __init__(self, config: dict, on_warning=None):
        self.config = config
        self.voice_cfg = config["voice"]
        self.on_warning = on_warning or (lambda msg: None)
        self._installed = list_installed_voices()
        self._current_process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()

        if not self._installed:
            self.on_warning(
                "No macOS 'say' voices detected. TTS will not work — this "
                "usually means you're not running on macOS, or the "
                "'say' command isn't available."
            )

    def _voice_for(self, language: str, gender: str):
        lang_cfg = self.voice_cfg["languages"].get(language)
        if not lang_cfg:
            return None
        voice = resolve_voice(lang_cfg, gender, self._installed)
        if not voice:
            self.on_warning(describe_missing(lang_cfg.get("label", language), gender))
        return voice

    def speak(self, text: str, language: Optional[str] = None, gender: Optional[str] = None, blocking: bool = True):
        """Speak `text` using the resolved voice for language/gender (or the configured defaults)."""
        language = language or self.voice_cfg["default_language"]
        gender = gender or self.voice_cfg["default_gender"]
        voice = self._voice_for(language, gender)

        rate = str(self.voice_cfg.get("speech_rate_wpm", 163))
        cmd = ["say", "-r", rate]
        if voice:
            cmd += ["-v", voice.name]
        cmd.append(_preprocess(text))

        with self._lock:
            self.stop()
            self._current_process = subprocess.Popen(cmd)
            proc = self._current_process

        if blocking:
            proc.wait()

    def stop(self):
        """Interrupt whatever is currently being spoken (e.g. user says 'stop')."""
        if self._current_process and self._current_process.poll() is None:
            self._current_process.terminate()
        self._current_process = None

    def available_languages(self) -> list[str]:
        return list(self.voice_cfg["languages"].keys())

"""
core/voices.py

Detects which macOS text-to-speech voices are actually installed on this
Mac (via `say -v ?`) and resolves the best match for a requested
language + gender, using the preferences in config.yaml.

macOS does not expose voice gender programmatically, so we keep a
best-effort name -> gender table. Anything not in the table is still
usable, just not selectable specifically as "male" or "female".
"""

import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional


@dataclass
class VoiceInfo:
    name: str
    locale: str
    gender: Optional[str] = None  # "male" | "female" | None if unknown


KNOWN_VOICE_GENDERS = {
    # English — standard voices
    "Alex": "male", "Fred": "male", "Daniel": "male", "Oliver": "male",
    "Aaron": "male", "Arthur": "male", "Nathan": "male", "Gordon": "male",
    "Samantha": "female", "Victoria": "female", "Ava": "female", "Zoe": "female",
    "Karen": "female", "Susan": "female", "Allison": "female", "Nicky": "female",
    "Tessa": "female", "Moira": "female", "Kate": "female",
    # English — macOS Ventura/Sonoma character voices (parenthesised locale names)
    "Flo (English (US))": "female", "Flo (English (UK))": "female",
    "Sandy (English (US))": "female", "Sandy (English (UK))": "female",
    "Shelley (English (US))": "female", "Shelley (English (UK))": "female",
    "Grandma (English (US))": "female", "Grandma (English (UK))": "female",
    "Reed (English (US))": "male", "Reed (English (UK))": "male",
    "Rocko (English (US))": "male", "Rocko (English (UK))": "male",
    "Eddy (English (US))": "male", "Eddy (English (UK))": "male",
    "Grandpa (English (US))": "male", "Grandpa (English (UK))": "male",
    # German
    "Anna": "female", "Petra": "female", "Markus": "male",
    # Hindi
    "Lekha": "female", "Isha": "female", "Rishi": "male",
}


def list_installed_voices() -> list[VoiceInfo]:
    """Parse `say -v ?` output into VoiceInfo entries. Returns [] off-macOS or if `say` is missing."""
    if not shutil.which("say"):
        return []
    try:
        result = subprocess.run(
            ["say", "-v", "?"], capture_output=True, text=True, timeout=10
        )
    except Exception:
        return []

    voices: list[VoiceInfo] = []
    for line in result.stdout.splitlines():
        line = line.rstrip()
        if not line:
            continue
        parts = line.split()
        # Locale token looks like "en_US", "hi_IN", "de_DE" — 5 chars, underscore at index 2.
        locale_idx = next(
            (i for i, tok in enumerate(parts) if len(tok) == 5 and tok[2] == "_"),
            None,
        )
        if locale_idx is None:
            continue
        name = " ".join(parts[:locale_idx])
        locale = parts[locale_idx]
        voices.append(VoiceInfo(name=name, locale=locale, gender=KNOWN_VOICE_GENDERS.get(name)))
    return voices


def resolve_voice(
    language_cfg: dict, gender: str, installed: Optional[list[VoiceInfo]] = None
) -> Optional[VoiceInfo]:
    """
    Pick the best installed voice for a config.yaml `voice.languages.<lang>`
    block and requested gender. Fallback order:
      1. exact preferred-name match that is actually installed
      2. any installed voice matching locale + gender
      3. any installed voice matching locale (gender unknown/mismatched)
      4. None
    """
    if installed is None:
        installed = list_installed_voices()

    locale_codes = set(language_cfg.get("locale_codes", []))
    preferred_names = language_cfg.get("preferred_voices", {}).get(gender, [])

    by_name = {v.name: v for v in installed}
    for name in preferred_names:
        if name in by_name:
            return by_name[name]

    for v in installed:
        if v.locale in locale_codes and v.gender == gender:
            return v

    for v in installed:
        if v.locale in locale_codes:
            return v

    return None


def describe_missing(language_label: str, gender: str) -> str:
    return (
        f"No installed macOS voice found for {language_label} ({gender}). "
        f"Add one via System Settings > Accessibility > Spoken Content > "
        f"System Voice > Manage Voices, then restart the app."
    )


def voice_report(config: dict) -> list[dict]:
    """
    Build a per-language/gender availability report, used at startup and
    by the HUD's language/voice selector so the UI only offers voices
    that actually exist on this machine.
    """
    installed = list_installed_voices()
    report = []
    for lang_code, lang_cfg in config["voice"]["languages"].items():
        for gender in ("female", "male"):
            match = resolve_voice(lang_cfg, gender, installed)
            report.append(
                {
                    "language": lang_code,
                    "label": lang_cfg.get("label", lang_code),
                    "gender": gender,
                    "voice_name": match.name if match else None,
                    "available": match is not None,
                    "warning": None if match else describe_missing(lang_cfg.get("label", lang_code), gender),
                }
            )
    return report

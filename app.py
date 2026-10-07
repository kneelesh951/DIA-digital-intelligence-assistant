"""
app.py

Entry point for ARIA. Loads config.yaml, wires up the voice layer
(TTS/STT), the agent orchestrator, and the pywebview bridge, then
opens the HUD window.

Run with:   python app.py
First-time setup (dependencies, mic/automation permissions, Whisper
model download): see README.md.
"""

import os
import sys
from pathlib import Path

import webview
import yaml

from bridge import Bridge
from core.orchestrator import Orchestrator
from core.stt import Transcriber
from core.tts import Speaker

ROOT = Path(__file__).parent


def _load_dotenv():
    """Load .env file into os.environ without third-party deps."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def load_config() -> dict:
    with open(ROOT / "config.yaml", "r") as f:
        return yaml.safe_load(f)


def main():
    _load_dotenv()
    config = load_config()

    def log(msg):
        print(f"[ARIA] {msg}", file=sys.stderr)

    speaker = Speaker(config, on_warning=log)
    transcriber = Transcriber(config, on_warning=log)
    orchestrator = Orchestrator(config, log_fn=log)
    bridge = Bridge(config, orchestrator, speaker, transcriber, log_fn=log)

    window = webview.create_window(
        config["app"]["name"],
        str(ROOT / "ui" / "index.html"),
        js_api=bridge,
        width=1280,
        height=800,
        background_color="#010802",
        min_size=(1000, 640),
    )

    def on_start(win):
        bridge.set_window(win)

    webview.start(on_start, window, debug=False)


if __name__ == "__main__":
    main()

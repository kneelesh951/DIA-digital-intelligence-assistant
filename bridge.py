"""
bridge.py

The pywebview API object exposed to the HUD's JavaScript as
window.pywebview.api. Every method here is callable from JS.

Also owns the always-on VAD integration: when activation_mode is
"always_on", start_always_on_listener() wires the Transcriber's VAD
loop to the HUD via evaluate_js callbacks.
"""

import json

from core.voices import voice_report


class Bridge:
    def __init__(self, config: dict, orchestrator, speaker, transcriber, log_fn=None):
        self.config       = config
        self.orchestrator = orchestrator
        self.speaker      = speaker
        self.transcriber  = transcriber
        self.log          = log_fn or (lambda *a, **k: None)
        self._current_lang   = config["voice"]["default_language"]
        self._current_gender = config["voice"]["default_gender"]
        self._window  = None
        self._speaking = False   # mute VAD while TTS is playing

    def set_window(self, window):
        """Called by app.py once the pywebview window exists."""
        self._window = window

    def start_always_on(self):
        """Called from JS after HUD is fully initialized and ready."""
        if self.config.get("app", {}).get("activation_mode") == "always_on":
            self.start_always_on_listener()
        self._start_briefing_scheduler()
        return {"ok": True}

    def _start_briefing_scheduler(self):
        """Background thread: fires daily briefing at the configured time."""
        import threading, time as _t
        cfg = self.config.get("briefing", {})
        if not cfg.get("enabled", False):
            return
        daily_time = cfg.get("daily_time", "").strip()
        if not daily_time:
            return
        try:
            h, m = map(int, daily_time.split(":"))
        except ValueError:
            self.log(f"Invalid briefing.daily_time '{daily_time}' — use HH:MM format.")
            return

        def _loop():
            from datetime import datetime
            last_date = None
            while True:
                now = datetime.now()
                today = now.date()
                if now.hour == h and now.minute == m and last_date != today:
                    last_date = today
                    self.log("Scheduled briefing triggered.")
                    self._js('window.ariaAutoTranscript("morning briefing")')
                _t.sleep(30)

        t = threading.Thread(target=_loop, daemon=True, name="briefing-scheduler")
        t.start()
        self.log(f"Daily briefing scheduled for {daily_time}.")

    def _js(self, expression: str):
        """Safely call a JS expression on the HUD window."""
        if self._window:
            try:
                self._window.evaluate_js(expression)
            except Exception as e:
                self.log(f"evaluate_js error: {e}")

    def start_always_on_listener(self):
        """Start the VAD background loop and wire callbacks to the HUD."""
        STOP_WORDS = {"stop", "shut up", "quiet", "silence", "pause", "enough"}

        try:
            def on_speech(text: str):
                if self._speaking:
                    # while ARIA is talking, only honour "stop"
                    if any(w in text.lower() for w in STOP_WORDS):
                        self.speaker.stop()
                        self._speaking = False
                    return
                self.log(f"[always-on] heard: {text}")
                safe = json.dumps(text)
                self._js(f"window.ariaAutoTranscript({safe})")

            def on_state(state: str):
                if self._speaking and state == "listening":
                    return  # suppress listening indicator during TTS
                self._js(f"window.ariaAutoState({json.dumps(state)})")

            self.transcriber.start_always_on(
                on_speech=on_speech,
                on_state=on_state,
                language_hint=lambda: self._current_lang,
            )
            self.log("Always-on VAD started.")
        except Exception as e:
            self.log(f"VAD start failed (mic permission denied?): {e}")

    def log_js_error(self, message):
        self.log(f"[JS] {message}")
        return {"ok": True}

    # ── Startup info ────────────────────────────────────────────────────────

    def get_config(self):
        report   = voice_report(self.config)
        warnings = [r["warning"] for r in report if r["warning"]]
        return {
            "app_name":        self.config["app"]["name"],
            "tagline":         self.config["app"]["tagline"],
            "activation_mode": self.config["app"].get("activation_mode", "push_to_talk"),
            "default_language": self._current_lang,
            "default_gender":   self._current_gender,
            "voice_warnings":   warnings,
        }

    def get_roster(self):
        return self.orchestrator.agent_roster()

    def set_voice(self, language, gender):
        self._current_lang   = language
        self._current_gender = gender
        return {"ok": True}

    # ── Voice I/O ───────────────────────────────────────────────────────────

    def start_recording(self):
        try:
            self.transcriber.start_recording()
        except Exception as exc:
            self.log(f"Mic error: {exc}")
        return {"ok": True}

    def stop_recording(self):
        try:
            return self.transcriber.stop_recording_and_transcribe(
                language_hint=self._current_lang
            )
        except Exception as exc:
            self.log(f"Transcription error: {exc}")
            return ""

    def speak(self, text, language=None, gender=None):
        import time
        self._speaking = True
        # Mute VAD for the duration of TTS + 2s cooldown so DIA's voice
        # isn't picked up by the mic and re-transcribed as a new command.
        words = len(text.split())
        est_secs = max(4.0, words / 2.5)   # rough WPM estimate
        self.transcriber.mute_vad(est_secs + 2.0)
        try:
            self.speaker.speak(
                text,
                language=language or self._current_lang,
                gender=gender or self._current_gender,
                blocking=True,
            )
            time.sleep(0.4)
        except Exception as exc:
            self.log(f"Speech error: {exc}")
        finally:
            self._speaking = False
            self.transcriber.mute_vad(2.0)  # accurate 2s cooldown from actual TTS end
        return {"ok": True}

    def stop_speaking(self):
        self.speaker.stop()
        self._speaking = False
        return {"ok": True}

    # ── Command handling ─────────────────────────────────────────────────────

    def send_text(self, text):
        STOP_WORDS = {"stop", "shut up", "quiet", "silence", "pause", "enough"}
        if any(w in text.lower() for w in STOP_WORDS):
            self.speaker.stop()
            self._speaking = False
            return {"type": "chat", "message": ""}
        return self.orchestrator.interpret(text, lang=self._current_lang)

    def get_system_stats(self):
        """Return CPU, RAM, battery, disk, and network stats."""
        import psutil, time
        try:
            cpu  = round(psutil.cpu_percent(interval=None))
            mem  = psutil.virtual_memory()
            bat  = psutil.sensors_battery()
            disk = psutil.disk_usage("/")
            boot = psutil.boot_time()
            up   = int(time.time() - boot)
            h, r = divmod(up, 3600); m = r // 60

            # Network delta
            net = psutil.net_io_counters()
            now = time.time()
            prev = getattr(self, "_prev_net", None)
            self._prev_net = (net.bytes_sent, net.bytes_recv, now)
            if prev:
                ps, pr, pt = prev
                dt = max(now - pt, 0.1)
                def _fmt(bps):
                    if bps < 1024:       return f"{bps:.0f} B/s"
                    if bps < 1024**2:    return f"{bps/1024:.0f} KB/s"
                    return               f"{bps/1024**2:.1f} MB/s"
                net_up = _fmt((net.bytes_sent - ps) / dt)
                net_dn = _fmt((net.bytes_recv - pr) / dt)
            else:
                net_up = net_dn = "—"

            return {
                "cpu": cpu,
                "ram": round(mem.percent),
                "ram_used": f"{mem.used/1e9:.1f}",
                "ram_total": f"{mem.total/1e9:.1f}",
                "battery": round(bat.percent) if bat else None,
                "charging": bat.power_plugged if bat else None,
                "uptime": f"{h}h {m}m",
                "disk": round(disk.percent),
                "disk_used": f"{disk.used/1e9:.0f}",
                "disk_total": f"{disk.total/1e9:.0f}",
                "net_up": net_up,
                "net_dn": net_dn,
            }
        except Exception as e:
            self.log(f"Stats error: {e}")
            return {}

    def get_weather(self):
        """Fetch weather from wttr.in (no API key needed)."""
        import urllib.request, json as _json
        _ICONS = {
            113: ("☀", "SUNNY"),       116: ("⛅", "PARTLY CLOUDY"),
            119: ("☁", "CLOUDY"),      122: ("☁", "OVERCAST"),
            143: ("🌫", "MISTY"),      176: ("🌦", "LIGHT RAIN"),
            200: ("⛈", "THUNDERSTORM"),248: ("🌫", "FOG"),
            260: ("🌫", "FREEZING FOG"),293: ("🌦", "LIGHT RAIN"),
            296: ("🌦", "DRIZZLE"),    299: ("🌧", "RAIN"),
            302: ("🌧", "HEAVY RAIN"), 305: ("🌧", "HEAVY RAIN"),
            308: ("🌧", "TORRENTIAL"), 323: ("🌨", "LIGHT SNOW"),
            326: ("🌨", "SNOW"),       329: ("❄", "HEAVY SNOW"),
            386: ("⛈", "THUNDER"),    389: ("⛈", "HEAVY STORM"),
        }
        try:
            req = urllib.request.Request(
                "https://wttr.in/?format=j1",
                headers={"User-Agent": "curl/7.64"}
            )
            with urllib.request.urlopen(req, timeout=7) as resp:
                data = _json.loads(resp.read().decode())
            curr = data["current_condition"][0]
            code = int(curr["weatherCode"])
            icon, desc = _ICONS.get(code, ("🌤", curr["weatherDesc"][0]["value"].upper()[:14]))
            area = data.get("nearest_area", [{}])[0]
            city = area.get("areaName", [{}])[0].get("value", "")
            return {
                "icon": icon, "desc": desc,
                "temp_c": int(curr["temp_C"]),
                "feels_c": int(curr["FeelsLikeC"]),
                "humidity": int(curr["humidity"]),
                "city": city[:14],
            }
        except Exception as e:
            self.log(f"Weather error: {e}")
            return None

    def get_calendar_events(self):
        """Fetch upcoming events from macOS Calendar (syncs Google Calendar).
        Requires: System Settings -> Internet Accounts -> Google -> Calendar ON
        """
        import subprocess
        # Use whose clause (Calendar-native filter, fast) with ASCII >= <=
        script = (
            'tell application "Calendar"\n'
            '    set out to ""\n'
            '    set now_d to current date\n'
            '    set end_d to now_d + (14 * 24 * 60 * 60)\n'
            '    repeat with c in calendars\n'
            '        try\n'
            '            set evts to (every event of c whose start date >= now_d and start date <= end_d)\n'
            '            repeat with e in evts\n'
            '                set out to out & (summary of e as text) & "|" & (start date of e as text) & "\\n"\n'
            '            end repeat\n'
            '        end try\n'
            '    end repeat\n'
            '    return out\n'
            'end tell'
        )
        try:
            r = subprocess.run(["osascript", "-e", script],
                               capture_output=True, text=True, timeout=15)
            if r.returncode != 0:
                self.log(f"Calendar osascript error: {r.stderr.strip()}")
            events = []
            for line in r.stdout.strip().split("\n"):
                if "|" in line:
                    title, date = line.split("|", 1)
                    t, d = title.strip(), date.strip()
                    if t:
                        events.append({"title": t, "date": d})
            # Sort by date string (lexicographic works for macOS date format)
            events.sort(key=lambda e: e["date"])
            return events[:8]
        except Exception as e:
            self.log(f"Calendar error: {e}")
            return []

    def quick_action(self, action: str):
        """Instant system actions (screenshot, lock, mute, spotlight)."""
        import subprocess, time as _t
        try:
            if action == "screenshot":
                import os
                fname = os.path.expanduser(f"~/Desktop/DIA_{int(_t.time())}.png")
                subprocess.run(["screencapture", "-x", fname], check=True)
                subprocess.run(["open", fname])
                return {"ok": True, "msg": "Screenshot saved to Desktop."}
            elif action == "lock":
                subprocess.run(["pmset", "displaysleepnow"])
                return {"ok": True, "msg": "Display locked."}
            elif action == "mute":
                subprocess.run(["osascript", "-e", "set volume output muted true"])
                return {"ok": True}
            elif action == "unmute":
                subprocess.run(["osascript", "-e", "set volume output muted false"])
                return {"ok": True}
            elif action == "spotlight":
                subprocess.run(["osascript", "-e",
                    'tell application "System Events" to keystroke " " using {command down}'])
                return {"ok": True}
            else:
                return {"ok": False, "error": f"Unknown action: {action}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_stocks(self):
        """Fetch top 5 day-gainers and day-losers from Yahoo Finance (no API key)."""
        import urllib.request, json as _json
        HDRS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", "Accept": "application/json"}
        def _screen(scrid):
            url = (f"https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
                   f"?scrIds={scrid}&count=5&lang=en-US&region=US")
            req = urllib.request.Request(url, headers=HDRS)
            with urllib.request.urlopen(req, timeout=8) as r:
                d = _json.loads(r.read().decode())
            qs = d["finance"]["result"][0]["quotes"]
            return [{"sym": q["symbol"],
                     "pct": round(float(q.get("regularMarketChangePercent", 0)), 2),
                     "px":  round(float(q.get("regularMarketPrice", 0)), 2)} for q in qs]
        try:
            return {"gainers": _screen("day_gainers"), "losers": _screen("day_losers")}
        except Exception as e:
            self.log(f"Stocks error: {e}")
            return None

    def get_watchlist_prices(self):
        """Return live prices for all watchlist symbols (for the HUD widget)."""
        import json as _json
        from pathlib import Path
        wl_file = Path.home() / ".dia_watchlist.json"
        if not wl_file.exists():
            return []
        try:
            symbols = _json.loads(wl_file.read_text())
        except Exception:
            return []
        if not symbols:
            return []
        import urllib.request as _req
        HDRS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        results = []
        for sym in symbols[:8]:   # cap at 8 to keep API calls fast
            try:
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=1d"
                r = _req.Request(url, headers=HDRS)
                with _req.urlopen(r, timeout=5) as resp:
                    d = _json.loads(resp.read())
                m = d["chart"]["result"][0]["meta"]
                price = float(m.get("regularMarketPrice", 0))
                prev  = float(m.get("chartPreviousClose") or m.get("previousClose") or price)
                pct   = round((price - prev) / prev * 100, 2) if prev else 0
                results.append({
                    "sym":   m.get("symbol", sym).upper(),
                    "name":  (m.get("shortName") or sym)[:14],
                    "price": round(price, 2),
                    "pct":   pct,
                })
            except Exception:
                results.append({"sym": sym, "name": sym, "price": 0, "pct": 0})
        return results

    def get_clipboard(self):
        """Return current macOS clipboard text (pbpaste)."""
        import subprocess
        try:
            r = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=2)
            t = r.stdout.strip()
            return t[:250] if t else None
        except Exception as e:
            self.log(f"Clipboard error: {e}")
            return None

    def get_now_playing(self):
        """Return currently playing track from Spotify or Apple Music."""
        import subprocess
        for app in ["Spotify", "Music"]:
            try:
                if subprocess.run(["pgrep", "-x", app], capture_output=True, timeout=1).returncode != 0:
                    continue
                scr = (f'tell application "{app}"\n'
                       f'    if player state is playing then\n'
                       f'        return (name of current track) & " — " & (artist of current track)\n'
                       f'    else\n'
                       f'        return ""\n'
                       f'    end if\n'
                       f'end tell')
                r = subprocess.run(["osascript", "-e", scr],
                                   capture_output=True, text=True, timeout=3)
                txt = r.stdout.strip()
                if txt:
                    return {"track": txt, "app": app}
            except Exception:
                continue
        return None

    def confirm(self, pending_id):
        return self.orchestrator.confirm(pending_id)

    def cancel(self, pending_id):
        return self.orchestrator.cancel(pending_id)

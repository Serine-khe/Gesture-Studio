"""Gesture Studio main program.

    camera thread  ->  hand tracking (vision.py)
    main loop      ->  hands -> gestures -> current mode -> audio engine commands
    audio process  ->  real-time synth (engine.py)
    web server     ->  the interface in an app window (server.py + web/)

The main loop is the only place that changes the app's state; clicks in the
interface arrive as "actions" on a queue and are applied here, one at a time.
"""

import argparse
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass

from .audio import AudioEngine
from .camera import CAMERA_HELP, Camera, scan_cameras
from .config import PROJECT_DIR, load_config
from .gestures import HandTracker, gesture_catalog, gesture_label
from .modes import FreePlayMode, SongsMode, SoundShaping, SynthMode
from .music import KEY_NAMES, VOICINGS
from .presets import PRESETS, preset_catalog
from .server import StudioServer
from .settings import STABLE_FRAMES, Settings
from .songs import SongLibrary, build, clean_song
from .triggers import GestureStabilizer, TriggerGate
from .vision import VisionWorker

WEB_DIR = os.path.join(PROJECT_DIR, "web")


@dataclass
class HandState:
    """One hand after smoothing - what the modes work with."""
    side: str          # the user's real hand: "left" / "right"
    gesture: str       # steady gesture name
    changed: bool      # True on the frame the steady gesture changed
    tilt_out: float    # degrees leaning away from the body (outward)
    height: float      # 0 = bottom of picture, 1 = top
    fingers: dict


class Studio:
    def __init__(self, config_path=None, camera_index=None):
        self.config, warnings = load_config(config_path)
        self.settings = Settings()
        self.library = SongLibrary(self.config["songs_file"])
        for warning in warnings + self.library.warnings:
            print(f"[config] {warning}")
        if camera_index is not None:
            self.settings.set("camera_index", camera_index)

        self.running = True
        self.octave = self.settings["default_octave"]
        self.preset = self.settings["default_preset"]
        self.muted = False
        self._actions = queue.Queue()
        self._toast = {"id": 0, "text": ""}
        self._state_cond = threading.Condition()
        self._state_json = "{}"
        self._state_id = 0
        self._last_publish = 0.0
        self._clients = 0
        self._last_client_time = None
        self.camera = None
        self.vision = None
        self.camera_state = {"status": "starting", "message": "Starting camera..."}
        self.cameras_found = None
        self._last_readings = {}

        audio = self.config["audio"]
        self.audio = AudioEngine(audio["sample_rate"], audio["chunk_size"])
        det = self.config["detection"]
        self.tracker = HandTracker(det["min_detection_confidence"], det["min_tracking_confidence"],
                                   det["model_complexity"], self.settings["thumb_sensitivity"])
        self._make_filters()
        self.shaping = SoundShaping(self)
        self.modes = {"synth": SynthMode(self), "free": FreePlayMode(self), "songs": SongsMode(self)}
        self.mode = self.modes["synth"]

    # ================================================================ start-up
    def run(self, open_window=None):
        print("Starting the sound engine...")
        if self.audio.wait_ready():
            print("[audio] OK")
        else:
            print(f"[audio] Sound is unavailable ({self.audio.error}). The app still works, silently.")
        self._sync_audio()
        threading.Thread(target=self._open_camera, args=(self.settings["camera_index"], True),
                         daemon=True).start()

        ui = self.config["interface"]
        try:
            self.server = StudioServer(self, WEB_DIR, ui["port"])
        except OSError as exc:
            print(f"Could not start the interface: {exc}")
            self.shutdown()
            return 1
        self.server.start()
        url = self.server.url
        print(f"\nGesture Studio is running at {url}")
        if open_window if open_window is not None else ui["open_window"]:
            how = open_app_window(url)
            print("Opened the app window." if how == "app" else "Opened your web browser.")
        print("Close the Gesture Studio window (or press Ctrl+C here) to quit.\n")

        self.mode.enter()
        try:
            while self.running:
                self._tick()
        except KeyboardInterrupt:
            pass
        finally:
            self.shutdown()
        return 0

    def _make_filters(self):
        frames = STABLE_FRAMES[self.settings["steadiness"]]
        cooldown = self.config["trigger"]["cooldown_seconds"]
        self.stabilizers = {r: GestureStabilizer(frames, lost_frames=6) for r in ("harmony", "sound")}
        self.gates = {r: TriggerGate(cooldown) for r in ("harmony", "sound")}

    def _sync_audio(self):
        """Send every sound setting to the engine (start-up and after a restart)."""
        self.audio.preset(self.preset)
        self.audio.volume(self.settings["volume"])
        self.audio.mute(self.muted)
        self.audio.repeat_interval(self.settings["piano_repeat"])
        self.shaping.send(force=True)

    def _open_camera(self, index, search_others=False):
        """Runs on a helper thread: opening a camera can take a second or two."""
        self.camera_state = {"status": "starting", "message": f"Opening camera {index}..."}
        cam_cfg = self.config["camera"]
        camera = Camera(index, cam_cfg["width"], cam_cfg["height"])
        if not camera.open(search_other_indexes=search_others):
            self.camera_state = {"status": "error", "message": camera.error, "help": CAMERA_HELP[1:]}
            print(f"[camera] {camera.error}")
            return
        if self.vision is None:
            self.vision = VisionWorker(camera, self.tracker, self.settings["mirror"])
            self.vision.start()
        else:
            old = self.vision.set_camera(camera)
            if old is not None:
                old.release()
        self.camera = camera
        self.settings.set("camera_index", camera.active_index)
        self.camera_state = {"status": "ok", "message": f"Camera {camera.active_index}"}

    def _scan_cameras(self):
        in_use = self.camera.active_index if self.camera else None
        self.cameras_found = scan_cameras(in_use=in_use)

    # =============================================================== main loop
    def _tick(self):
        now = time.perf_counter()
        if self.vision is not None:
            fresh, ok, _frame, readings = self.vision.latest(timeout=0.04)
            if not ok and self.camera_state["status"] == "ok":
                self.camera_state = {"status": "warning", "message": "Camera feed lost - reconnecting..."}
            elif ok and self.camera_state["status"] == "warning":
                self.camera_state = {"status": "ok", "message": f"Camera {self.camera.active_index}"}
        else:
            time.sleep(0.04)
            fresh, ok, readings = True, False, []

        self.audio.poll()
        self._apply_actions()

        if fresh:
            harmony, sound = self._hand_states(readings if ok else [], now)
            if harmony and sound and harmony.gesture == "fist" and sound.gesture == "fist" \
                    and (harmony.changed or sound.changed):
                self.stop_all("Both fists: everything stopped")
            self.mode.update(harmony, sound)
            self._publish(harmony, sound, readings if ok else [])
        elif now - self._last_publish > 0.25:
            self._publish(None, None, [])

        self.settings.save_if_needed()
        self._check_window_closed(now)

    def _hand_states(self, readings, now):
        mirrored = self.settings["mirror"]
        by_side = {r.side: r for r in readings}
        harmony_side = "right" if self.settings["swap_hands"] else "left"
        sound_side = "left" if harmony_side == "right" else "right"
        states = []
        for role, side in (("harmony", harmony_side), ("sound", sound_side)):
            reading = by_side.get(side)
            if reading is not None:
                self._last_readings[role] = reading
            stable = self.stabilizers[role].update(reading.gesture if reading else None)
            changed = self.gates[role].check(stable, now)
            if stable is None:
                states.append(None)
                continue
            r = reading or self._last_readings[role]
            outward = (-r.tilt if side == "left" else r.tilt) * (1 if mirrored else -1)
            states.append(HandState(side, stable, changed, outward, r.height, r.fingers))
        return states

    def _check_window_closed(self, now):
        if not self.config["interface"]["quit_when_window_closed"]:
            return
        if self._clients == 0 and self._last_client_time is not None and now - self._last_client_time > 8.0:
            print("The window was closed - quitting.")
            self.running = False

    # ================================================================= actions
    def enqueue(self, action):
        """Called by the web server threads; applied on the main loop."""
        self._actions.put(action)

    def _apply_actions(self):
        while True:
            try:
                action = self._actions.get_nowait()
            except queue.Empty:
                return
            try:
                self._apply(action)
            except Exception as exc:  # a bad request must never crash the instrument
                print(f"[action] {action!r} failed: {exc}")

    def _apply(self, a):
        kind = a.get("type")
        value = a.get("value")
        songs = self.modes["songs"]
        if kind == "mode" and value in self.modes:
            self.set_mode(value)
        elif kind == "mute":
            self.muted = (not self.muted) if value is None else bool(value)
            self.audio.mute(self.muted)
            self.toast("Muted" if self.muted else "Sound on")
        elif kind == "stop":
            self.stop_all("Stopped")
        elif kind == "volume":
            self.audio.volume(self.settings.set("volume", value))
        elif kind == "preset" and value in PRESETS:
            self.preset = value
            self.audio.preset(value)
        elif kind == "key":
            self.settings.set("key", value)
        elif kind == "scale":
            self.settings.set("scale", value)
        elif kind == "octave":
            self.octave = min(max(int(value), 1), 5)
        elif kind == "expression":
            self.settings.set("expression", value)
            self.shaping.send(force=True)
        elif kind == "voicing" and value in VOICINGS:
            self.shaping.voicing = value
        elif kind == "register":
            self.shaping.register = min(max(int(value), -1), 1)
        elif kind == "brightness":
            self.shaping.manual_brightness = min(max(float(value), 0.0), 1.0)
            self.shaping.send()
        elif kind == "setting":
            self._apply_setting(a.get("key"), value)
        elif kind == "scan_cameras":
            self.cameras_found = None
            threading.Thread(target=self._scan_cameras, daemon=True).start()
        elif kind == "camera":
            threading.Thread(target=self._open_camera, args=(int(value), False), daemon=True).start()
        elif kind == "restart_audio":
            self.audio.restart()
            self.audio.wait_ready()
            self._sync_audio()
            self.toast("Sound engine restarted" if self.audio.available else "Sound is still unavailable")
        elif kind == "song_select":
            songs.select(value)
            self.set_mode("songs")
        elif kind == "song_save":
            try:
                song = self.library.save_song(value)
            except ValueError as exc:
                self.toast(f"Not saved: {exc}")
                return
            songs.reload()
            songs.select(song["id"], announce=False)
            self.set_mode("songs")
            self.toast(f"Saved {song['title']}")
        elif kind == "song_delete":
            song = self.library.get(value)
            if song is not None:
                self.library.delete(value)
                songs.reload()
                self.toast(f"Deleted {song['title']}")
        elif kind == "song_restart" and songs.song:
            songs.restart()
        elif kind == "song_transpose" and songs.song:
            songs.set_transpose(songs.transpose + int(value))
        elif kind == "song_section" and songs.song:
            songs.jump(int(value))

    def _apply_setting(self, key, value):
        value = self.settings.set(key, value)
        if key == "mirror" and self.vision:
            self.vision.set_mirror(value)
        elif key == "thumb_sensitivity":
            self.tracker.thumb_sensitivity = value
        elif key == "steadiness":
            self._make_filters()
        elif key == "default_octave":
            self.octave = value
        elif key == "default_preset":
            self.preset = value
            self.audio.preset(value)
        elif key == "volume":
            self.audio.volume(value)
        elif key == "piano_repeat":
            self.audio.repeat_interval(value)
        elif key == "camera_index":
            threading.Thread(target=self._open_camera, args=(value, False), daemon=True).start()
        elif key in ("expression", "tilt_filter"):
            self.shaping.send(force=True)

    def set_mode(self, key):
        new = self.modes[key]
        if new is self.mode:
            return
        self.mode.leave()
        self.mode = new
        for gate in self.gates.values():
            gate.reset()
        new.enter()

    def stop_all(self, message):
        self.audio.panic()
        for mode in self.modes.values():
            mode.stop()
        self.toast(message)

    def toast(self, text):
        self._toast = {"id": self._toast["id"] + 1, "text": text}

    # ============================================================ interface
    def init_payload(self):
        """Things the interface needs once: lists for menus and guides."""
        return {
            "presets": preset_catalog(),
            "keys": KEY_NAMES,
            "voicings": [{"id": k, "label": v} for k, v in VOICINGS.items()],
            "gestures": gesture_catalog(),
            "songs": self.songs_payload(),
        }

    def songs_payload(self):
        """Your song guides for the My Songs page and its editor."""
        return [{"id": s["id"], "title": s["title"], "artist": s["artist"], "sections": s["sections"],
                 "gestures": len(s["gesture_chords"]), "unmapped": s["unmapped"]}
                for s in list(self.library.songs)]

    @staticmethod
    def check_song(entry):
        """Preview of a guide being typed: which gesture plays which chord, or what is wrong.
        Runs on a web server thread - it only reads the entry, nothing is saved."""
        try:
            song = build(clean_song(entry))
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "chords": len(song["chords"]), "unmapped": song["unmapped"],
                "gestures": [{"gesture": g, "chord": c, "also": [v for v in song["variants"][g] if v != c]}
                             for g, c in song["gesture_chords"].items()]}

    def _publish(self, harmony, sound, readings):
        snap = self.mode.snapshot(harmony, sound)
        roles = {"harmony": harmony, "sound": sound}
        hands = {}
        harmony_side = "right" if self.settings["swap_hands"] else "left"
        for reading in readings:
            role = "harmony" if reading.side == harmony_side else "sound"
            info = reading.as_dict()
            info["role"] = role
            steady = roles.get(role)
            info["steady"] = steady.gesture if steady else None
            info["label"] = gesture_label(info["steady"]) if steady else ""
            hands[role] = info
        state = {
            "mode": self.mode.key,
            "muted": self.muted,
            "volume": self.settings["volume"],
            "preset": self.preset,
            "octave": self.octave,
            "key": self.settings["key"],
            "scale": snap.get("scale", self.settings["scale"]),
            "settings": self.settings.values,
            "shaping": self.shaping.describe(),
            "camera": dict(self.camera_state, available=self.cameras_found,
                           index=self.camera.active_index if self.camera else None),
            "audio": {"status": self.audio.status, "message": self.audio.error,
                      "underruns": self.audio.underruns},
            "hands": hands,
            "fps": round(self.vision.fps, 1) if self.vision else 0,
            "toast": self._toast,
            "display": snap["display"],
            "guides": snap["guides"],
            "song": snap.get("song"),
            "songs_rev": self.library.rev,
        }
        data = json.dumps(state, separators=(",", ":"))
        with self._state_cond:
            self._state_json = data
            self._state_id += 1
            self._state_cond.notify_all()
        self._last_publish = time.perf_counter()

    def wait_state(self, last_id, timeout=1.0):
        with self._state_cond:
            if self._state_id == last_id:
                self._state_cond.wait(timeout)
            return self._state_id, self._state_json

    def client_connected(self):
        self._clients += 1
        self._last_client_time = time.perf_counter()

    def client_disconnected(self):
        self._clients = max(0, self._clients - 1)
        self._last_client_time = time.perf_counter()

    # =============================================================== shut down
    def shutdown(self):
        self.running = False
        self.settings.save_if_needed(force=True)
        if getattr(self, "server", None):
            self.server.stop()
        if self.vision:
            self.vision.stop()
        if self.camera:
            self.camera.release()
        self.tracker.close()
        self.audio.close()
        print("Goodbye!")


def open_app_window(url):
    """Open the interface in a clean app-style window (Edge/Chrome), else a browser tab."""
    candidates = []
    if sys.platform.startswith("win"):
        for base in (os.environ.get("ProgramFiles(x86)", ""), os.environ.get("ProgramFiles", ""),
                     os.environ.get("LocalAppData", "")):
            if base:
                candidates.append(os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"))
                candidates.append(os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"))
    elif sys.platform == "darwin":
        candidates += ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                       "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"]
    else:
        candidates += [shutil.which(n) or "" for n in ("google-chrome", "chromium", "chromium-browser",
                                                        "microsoft-edge")]
    for exe in candidates:
        if exe and os.path.exists(exe):
            try:
                subprocess.Popen([exe, f"--app={url}", "--window-size=1400,900"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return "app"
            except OSError:
                continue
    webbrowser.open(url)
    return "browser"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Gesture Studio - a hand-gesture synthesizer.")
    parser.add_argument("--camera", type=int, default=None, help="camera number (0 = default webcam)")
    parser.add_argument("--config", default=None, help="path to a config JSON file")
    parser.add_argument("--check", action="store_true", help="test camera, audio and packages, then exit")
    parser.add_argument("--no-window", action="store_true", help="don't open a window (open the URL yourself)")
    args = parser.parse_args(argv)

    if args.check:
        from .diagnostics import run_checks
        return run_checks(args.camera or 0)
    return Studio(args.config, args.camera).run(open_window=False if args.no_window else None)

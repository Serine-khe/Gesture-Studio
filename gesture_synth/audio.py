"""Remote control for the synth engine process (see engine.py).

The main program calls simple methods like `audio.notes("chord", [57, 61, 64])`.
Each call becomes a small message on a queue; the engine process picks it up
within ~2 ms. Nothing here ever waits for audio, so the camera loop stays smooth.
"""

import multiprocessing as mp
import queue
import time

from .engine import run_engine


class AudioEngine:
    def __init__(self, sample_rate=44100, chunk=1024):
        self.sample_rate = sample_rate
        self.chunk = chunk
        self.status = "starting"     # starting | ok | unavailable | error
        self.error = None
        self.underruns = 0
        self._proc = None
        self._start()

    @property
    def available(self):
        return self.status == "ok"

    def _start(self):
        ctx = mp.get_context("spawn")
        self._cmd = ctx.Queue()
        self._evt = ctx.Queue()
        self.status, self.error = "starting", None
        try:
            self._proc = ctx.Process(target=run_engine, name="gesture-studio-audio", daemon=True,
                                     args=(self._cmd, self._evt, self.sample_rate, self.chunk))
            self._proc.start()
        except Exception as exc:
            self.status, self.error = "error", f"could not start the audio engine: {exc}"

    def restart(self):
        self.close()
        self._start()

    def wait_ready(self, timeout=15.0):
        """Block until the engine reports in (used once at start-up)."""
        end = time.perf_counter() + timeout
        while self.status == "starting" and time.perf_counter() < end:
            self.poll(wait=0.1)
        if self.status == "starting":
            self.status, self.error = "error", "the audio engine did not respond"
        return self.available

    def poll(self, wait=0.0):
        """Read the engine's status messages (ready, stats, errors)."""
        try:
            item = self._evt.get(timeout=wait) if wait else self._evt.get_nowait()
            while True:
                kind, data = item
                if kind == "ready":
                    self.status = "ok" if data.get("ok") else "unavailable"
                    self.error = data.get("error")
                    self.sample_rate = data.get("sample_rate", self.sample_rate)
                elif kind == "stats":
                    self.underruns = data.get("underruns", 0)
                elif kind == "error":
                    print(f"[audio] {data}")
                item = self._evt.get_nowait()
        except (queue.Empty, EOFError, OSError):
            pass
        if self._proc is not None and self.status in ("ok", "unavailable") and not self._proc.is_alive():
            self.status, self.error = "error", "the audio engine stopped unexpectedly"

    # ------------------------------------------------------------ commands
    def _send(self, *cmd):
        if self._proc is None or not self._proc.is_alive():
            return
        try:
            self._cmd.put_nowait(cmd)
        except Exception:
            pass

    def notes(self, group, notes, live=False):
        """Make a group ("chord", "free_left"...) play exactly these MIDI notes ([] = silence).
        `live`: played by a held gesture (the piano re-strikes held live notes)."""
        self._send("notes", group, [int(n) for n in notes], bool(live))

    def repeat_interval(self, seconds):
        """How often a held live piano note is struck again."""
        self._send("repeat_interval", float(seconds))

    def preset(self, key):
        self._send("preset", key)

    def volume(self, value):
        self._send("volume", float(value))

    def mute(self, muted):
        self._send("mute", bool(muted))

    def expression(self, volume, brightness):
        self._send("expression", float(volume), float(brightness))

    def release_all(self, seconds=None):
        self._send("release_all", seconds)

    def panic(self):
        self._send("panic")

    def close(self):
        if self._proc is None:
            return
        self._send("quit")
        self._proc.join(timeout=2.0)
        if self._proc.is_alive():
            self._proc.terminate()
        self._proc = None

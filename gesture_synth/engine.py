"""Real-time synthesizer engine. Runs in its OWN process (see audio.py).

Why a separate process? Python only runs one thread at a time per process.
Hand tracking keeps the main process busy, which would make audio stutter.
In its own process, the synth renders sound every ~12 ms without interruptions.

How sound is made (per 512-sample chunk):
  1. every active Voice (one note) reads its preset's wavetable -> raw tone
  2. each voice is shaped by its envelope (fade in / sustain / fade out)
  3. all voices are mixed, filtered (brightness), volume-ramped and soft-clipped
  4. the chunk is queued on a pygame mixer channel, which plays it gaplessly

Everything is played live by your hands: there is no clock or backing track.
"""

import os
import queue
import sys
import time

import numpy as np

from .presets import DEFAULT_PRESET, TABLE_SIZE, load_presets

ATTACK, DECAY, RELEASE = 0, 1, 2
MAX_VOICES = 28     # notes sounding at once (including fading ones)
MAX_FADING = 14     # fading notes allowed to overlap new chords
REPEAT_DAMP = 0.006  # s: how fast a re-struck piano note's previous strike is damped


def _raise_priority():
    """Ask the OS to favour this process slightly, for smoother audio."""
    try:
        if sys.platform.startswith("win"):
            import ctypes
            ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x8000)
        else:
            os.nice(-2)
    except Exception:
        pass


class Voice:
    """One sounding note."""
    __slots__ = ("midi", "freq", "preset", "phases", "start", "level", "stage", "age", "release_tau")

    def __init__(self, midi, preset):
        self.midi = midi
        self.freq = 440.0 * 2.0 ** ((midi - 69) / 12.0)
        self.preset = preset
        self.phases = np.random.random(len(preset.unison))
        self.start = self.phases.copy()      # phases at the strike (a re-strike reuses them)
        self.level = 0.0
        self.stage = ATTACK
        self.age = 0
        self.release_tau = max(preset.release, 0.01) / 4.6

    def release(self, seconds=None):
        self.stage = RELEASE
        if seconds is not None:
            self.release_tau = max(seconds, 0.003) / 4.6

    @property
    def finished(self):
        return (self.stage == RELEASE or self.preset.sustain == 0.0) and self.stage != ATTACK \
            and self.level < 1e-4


class SynthCore:
    def __init__(self, sample_rate):
        self.sr = sample_rate
        self.presets = load_presets(sample_rate)
        self.preset = self.presets[DEFAULT_PRESET]
        # Stack every wavetable into one big array so all oscillators can be read at once.
        blocks = []
        for p in self.presets.values():
            p.row0 = sum(len(b) for b in blocks)
            blocks.append(p.tables)
            p.dull_row0 = -1
            if p.dull_tables is not None:
                p.dull_row0 = sum(len(b) for b in blocks)
                blocks.append(p.dull_tables)
        bank = np.vstack(blocks).astype(np.float64)
        self._stride = bank.shape[1]
        self._bank = bank.ravel()
        self.voices = []
        self.groups = {}               # group name -> {midi: Voice}
        self.master = 0.8
        self.muted = False
        self.expr_volume = 1.0
        self.brightness = 0.5
        self._gain = 0.0
        self._cutoff = self.preset.cutoff
        self._zi = np.zeros((2, 2))
        # Live (gesture-played) groups. With a preset that has `live_repeat` (the piano),
        # a held note is struck again every `repeat_interval` seconds, like pressing the
        # key repeatedly. group -> samples until the next strike (from the chunk start).
        self.live_groups = set()
        self.repeat_due = {}
        self.repeat_interval = 0.5
        self.underruns = 0
        from scipy.signal import lfilter
        self._lfilter = lfilter

    # ---------------------------------------------------------- commands
    def handle(self, cmd):
        op, args = cmd[0], cmd[1:]
        if op == "notes":
            group, notes = args[:2]
            live = bool(args[2]) if len(args) > 2 else False
            self.set_group(group, notes)
            if live and notes:
                self.live_groups.add(group)
                if self.preset.live_repeat:
                    # One hammer strikes all of a key's strings together: start the
                    # unison copies in phase, so every press (and every re-strike,
                    # which reuses these phases) has the same full attack.
                    for voice in self.groups.get(group, {}).values():
                        if voice.age == 0:
                            voice.phases[:] = voice.phases[0]
                            voice.start = voice.phases.copy()
            else:
                self.live_groups.discard(group)
            self._schedule_repeat(group)
        elif op == "preset":
            self.set_preset(args[0])
            for group in self.live_groups:
                self._schedule_repeat(group)
        elif op == "repeat_interval":
            self.repeat_interval = float(np.clip(args[0], 0.1, 3.0))
        elif op == "volume":
            self.master = float(np.clip(args[0], 0.0, 1.0))
        elif op == "mute":
            self.muted = bool(args[0])
        elif op == "expression":
            self.expr_volume = float(np.clip(args[0], 0.0, 1.0))
            self.brightness = float(np.clip(args[1], 0.0, 1.0))
        elif op == "release_all":
            self.release_all(args[0] if args else None)
        elif op == "panic":
            self.release_all(0.03)

    def set_group(self, group, notes):
        """Make `group` play exactly `notes`. Notes already sounding keep going
        (no restart), removed notes fade out, new notes start."""
        current = self.groups.get(group, {})
        wanted = [int(n) for n in notes]
        kept = {}
        for midi, voice in current.items():
            if midi in wanted and voice.stage != RELEASE and voice.preset is self.preset:
                kept[midi] = voice
            else:
                voice.release()
        for midi in wanted:
            if midi not in kept:
                voice = Voice(midi, self.preset)
                self.voices.append(voice)
                kept[midi] = voice
        self.groups[group] = kept
        self._limit_voices()

    def _schedule_repeat(self, group):
        """(Re)start the repeat timer of a live group from now - or stop it."""
        if group in self.live_groups and self.preset.live_repeat and self.groups.get(group):
            self.repeat_due[group] = self.repeat_interval * self.sr
        else:
            self.repeat_due.pop(group, None)

    def _repeat_strike(self, group):
        """Strike a held live note again, like pressing the same piano key: a fresh voice
        with the preset's own attack and decay replaces the old one. The new voice starts
        with the same oscillator phases as the first strike, so every strike sounds the
        same (no random loudness from the detuned strings); the old voice is damped
        quickly so voices don't pile up."""
        fresh = {}
        for midi, voice in self.groups.get(group, {}).items():
            new = Voice(midi, self.preset)
            new.phases = voice.start.copy()
            new.start = voice.start
            voice.release(REPEAT_DAMP)
            fresh[midi] = new
            self.voices.append(new)
        if fresh:
            self.groups[group] = fresh
            self._limit_voices()

    def set_preset(self, key):
        if key not in self.presets or self.presets[key] is self.preset:
            return
        self.preset = self.presets[key]
        for group, voices in list(self.groups.items()):
            self.set_group(group, list(voices))  # crossfade sounding notes to the new sound

    def release_all(self, seconds=None):
        for voice in self.voices:
            voice.release(seconds)
        self.groups = {}
        self.live_groups.clear()
        self.repeat_due = {}

    def _limit_voices(self):
        """Keep CPU use bounded: quickly fade the oldest fading notes when too many pile up."""
        fading = [v for v in self.voices if v.stage == RELEASE]
        excess = len(self.voices) - MAX_VOICES
        for voice in fading[:max(excess, len(fading) - MAX_FADING)]:
            voice.release(0.06)
        if len(self.voices) > MAX_VOICES + 8:  # still too many (e.g. huge chords): cut oldest
            for voice in self.voices[: len(self.voices) - MAX_VOICES - 8]:
                voice.release(0.02)

    # ----------------------------------------------------------- rendering
    def render(self, n):
        """Render n stereo samples as a float array of shape (n, 2)."""
        out = np.zeros((n, 2))
        pos = 0
        while pos < n:
            end = n
            for due in self.repeat_due.values():
                if due < end:
                    end = max(pos, int(due))
            if end > pos:
                self._render_voices(out[pos:end])
            pos = end
            for group, due in list(self.repeat_due.items()):
                if due < n and int(due) <= pos:
                    self._repeat_strike(group)
                    self.repeat_due[group] = due + self.repeat_interval * self.sr
        for group in self.repeat_due:
            self.repeat_due[group] -= n
        self.voices = [v for v in self.voices if not v.finished]
        return self._master(out)

    def _render_voices(self, out):
        """Render every oscillator of every voice in one vectorised NumPy pass.

        Each voice has 2-4 slightly detuned oscillators (unison). Their wavetable
        positions form one (oscillators x samples) matrix, so the whole chord costs
        a handful of NumPy operations instead of hundreds of small ones.
        """
        if not self.voices:
            return
        n = len(out)
        t = np.arange(1, n + 1, dtype=np.float64)
        envs, motion, mixes = [], [], []
        steps, phase0, rows, dull_rows, left, right, owner = [], [], [], [], [], [], []
        for vi, voice in enumerate(self.voices):
            p = voice.preset
            envs.append(self._envelope(voice, n) * p.gain)
            if p.vibrato_depth:  # pitch wobble -> phase advances unevenly
                motion.append(np.cumsum(1.0 + p.vibrato_depth * np.sin(
                    2 * np.pi * p.vibrato_rate * (voice.age + t) / self.sr)))
            else:
                motion.append(t)
            mixes.append(np.exp(-(voice.age + t) / (p.pluck * self.sr)) if p.pluck else None)
            level = int(np.clip(np.log2(voice.freq / 20.0), 0, 10))
            for j, (cents, pan) in enumerate(p.unison):
                steps.append(voice.freq * 2.0 ** (cents / 1200.0) / self.sr)
                phase0.append(voice.phases[j])
                rows.append(p.row0 + level)
                dull_rows.append(p.dull_row0 + level if p.pluck else -1)
                left.append(np.sqrt((1.0 - pan) * 0.5))
                right.append(np.sqrt((1.0 + pan) * 0.5))
                owner.append(vi)
            voice.age += n

        owner = np.array(owner)
        phase = np.array(phase0)[:, None] + np.array(steps)[:, None] * np.vstack(motion)[owner]
        end_phase = phase[:, -1] % 1.0
        k = 0
        for voice in self.voices:
            for j in range(len(voice.phases)):
                voice.phases[j] = end_phase[k]
                k += 1

        idx = (phase % 1.0) * TABLE_SIZE
        i0 = idx.astype(np.int64)
        frac = idx - i0
        flat = np.array(rows)[:, None] * self._stride + i0
        s = self._bank[flat]
        s += (self._bank[flat + 1] - s) * frac
        dull_rows = np.array(dull_rows)
        plucked = dull_rows >= 0
        if plucked.any():  # crossfade from the bright table to the dull one
            fd = dull_rows[plucked][:, None] * self._stride + i0[plucked]
            sd = self._bank[fd] + (self._bank[fd + 1] - self._bank[fd]) * frac[plucked]
            mix = np.vstack([mixes[v] for v in owner[plucked]])
            s[plucked] = s[plucked] * mix + sd * (1.0 - mix)
        s *= np.vstack(envs)[owner]
        out[:, 0] += np.array(left) @ s
        out[:, 1] += np.array(right) @ s

    def _envelope(self, voice, n):
        """Envelope values for the next n samples (and advance the voice's state)."""
        p = voice.preset
        out = np.empty(n)
        i = 0
        while i < n:
            m = n - i
            if voice.stage == ATTACK:
                rate = 1.0 / max(p.attack * self.sr, 1.0)
                k = min(m, max(1, int(np.ceil((1.0 - voice.level) / rate))))
                seg = np.minimum(voice.level + rate * np.arange(1, k + 1), 1.0)
                out[i:i + k] = seg
                voice.level = seg[-1]
                i += k
                if voice.level >= 1.0:
                    voice.stage = DECAY
            elif voice.stage == DECAY:  # glide exponentially to the sustain level
                coef = np.exp(-1.0 / max(p.decay * self.sr / 4.0, 1.0))
                seg = p.sustain + (voice.level - p.sustain) * coef ** np.arange(1, m + 1)
                out[i:] = seg
                voice.level = seg[-1]
                i = n
            else:  # RELEASE: exponential fade to silence
                coef = np.exp(-1.0 / max(voice.release_tau * self.sr, 1.0))
                seg = voice.level * coef ** np.arange(1, m + 1)
                out[i:] = seg
                voice.level = seg[-1]
                i = n
        return out

    def _master(self, out):
        n = len(out)
        # Brightness (0..1) moves the filter cutoff over 4 octaves around the preset's value.
        target = np.clip(self.preset.cutoff * 2.0 ** ((self.brightness - 0.5) * 4.0), 90.0, 18000.0)
        self._cutoff = float(np.exp(0.75 * np.log(self._cutoff) + 0.25 * np.log(target)))
        w0 = 2 * np.pi * self._cutoff / self.sr
        alpha = np.sin(w0) / (2.0 * self.preset.resonance)
        cosw = np.cos(w0)
        a0 = 1.0 + alpha
        b = np.array([(1 - cosw) / 2, 1 - cosw, (1 - cosw) / 2]) / a0
        a = np.array([1.0, -2 * cosw / a0, (1 - alpha) / a0])
        out, self._zi = self._lfilter(b, a, out, axis=0, zi=self._zi)

        # Volume: a smooth ramp across the chunk avoids clicks.
        # 0.45 = headroom so a full chord doesn't hit the soft clipper too hard.
        target_gain = 0.0 if self.muted else 0.45 * (self.master ** 1.6) * (self.expr_volume ** 1.4)
        ramp = np.linspace(self._gain, target_gain, n)
        self._gain = target_gain
        out *= ramp[:, None]
        return np.tanh(out)

def run_engine(cmd_queue, event_queue, sample_rate=44100, chunk=512):
    """Entry point of the audio process."""
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    _raise_priority()
    ok, error, channels = False, None, 2
    try:
        import pygame
        pygame.mixer.pre_init(sample_rate, -16, 2, 512)
        pygame.mixer.init()
        init = pygame.mixer.get_init()
        if init is None:
            raise RuntimeError("the audio device did not start")
        sample_rate, _fmt, channels = init
        channel = pygame.mixer.Channel(0)
        ok = True
    except Exception as exc:  # no device, device busy, driver problems...
        error = str(exc) or exc.__class__.__name__

    try:
        core = SynthCore(sample_rate)
    except Exception as exc:
        event_queue.put(("ready", {"ok": False, "error": f"synth failed to start: {exc}"}))
        return
    event_queue.put(("ready", {"ok": ok, "error": error, "sample_rate": sample_rate}))

    started = False
    next_time = time.perf_counter()
    last_report = time.perf_counter()
    while True:
        try:
            while True:
                cmd = cmd_queue.get_nowait()
                if cmd[0] == "quit":
                    if ok:
                        pygame.mixer.quit()
                    return
                core.handle(cmd)
        except queue.Empty:
            pass
        except Exception as exc:
            event_queue.put(("error", f"command failed: {exc}"))

        try:
            if ok:
                if channel.get_queue() is None:
                    data = core.render(chunk)
                    pcm = (data * 32767.0).astype(np.int16)
                    if channels == 1:
                        pcm = pcm.mean(axis=1).astype(np.int16)
                    elif channels > 2:
                        pcm = np.repeat(pcm[:, :1], channels, axis=1)
                    sound = pygame.mixer.Sound(buffer=np.ascontiguousarray(pcm).tobytes())
                    if channel.get_busy():
                        channel.queue(sound)
                    else:
                        if started:
                            core.underruns += 1
                        channel.play(sound)
                        started = True
            else:
                # No sound card: keep rendering in real time, so notes still start and stop.
                now = time.perf_counter()
                if now >= next_time:
                    core.render(chunk)
                    next_time += chunk / sample_rate
                    if now - next_time > 0.5:
                        next_time = now
        except Exception as exc:
            event_queue.put(("error", f"render failed: {exc}"))
            time.sleep(0.05)

        now = time.perf_counter()
        if now - last_report > 1.0:
            event_queue.put(("stats", {"voices": len(core.voices), "underruns": core.underruns}))
            last_report = now
        time.sleep(0.002)

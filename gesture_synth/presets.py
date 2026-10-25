"""The five synth sounds, described as data.

Each preset is built from:
  * a harmonic recipe (how loud each overtone is) -> the basic tone colour
  * unison: several slightly detuned copies of each note, spread left/right -> width
  * an envelope (attack, decay, sustain, release) -> how notes start and fade
  * a low-pass filter cutoff -> brightness
  * optional vibrato and "pluck" (bright attack that quickly mellows)

Change the numbers here to design your own sounds.
"""

import numpy as np

TABLE_SIZE = 2048

PRESETS = {
    "retro": {
        "label": "Retro Synth",
        "description": "Electronic, a little nostalgic",
        "harmonics": "pulse",
        "unison": [(-9.0, -0.6), (9.0, 0.6)],        # (detune in cents, pan -1..1)
        "vibrato": (5.5, 0.0025),                     # (rate Hz, depth as pitch fraction)
        "envelope": (0.008, 0.35, 0.72, 0.35),        # attack, decay, sustain, release (s)
        "cutoff": 3200.0, "resonance": 1.4, "gain": 0.85,
    },
    "warm": {
        "label": "Warm Synth",
        "description": "Soft and rounded",
        "harmonics": "warm",
        "unison": [(-5.0, -0.4), (5.0, 0.4)],
        "vibrato": (4.5, 0.0008),
        "envelope": (0.04, 0.6, 0.85, 0.6),
        "cutoff": 1900.0, "resonance": 0.75, "gain": 1.0,
    },
    "bright": {
        "label": "Bright Synth",
        "description": "Clear and sharp",
        "harmonics": "saw",
        "unison": [(-4.0, -0.5), (0.0, 0.0), (4.0, 0.5)],
        "vibrato": (0.0, 0.0),
        "envelope": (0.004, 0.25, 0.7, 0.3),
        "cutoff": 9000.0, "resonance": 0.9, "gain": 0.72,
    },
    "pad": {
        "label": "Soft Pad",
        "description": "Slow, airy, made for singing over",
        "harmonics": "pad",
        "unison": [(-11.0, -0.8), (-4.0, -0.3), (4.0, 0.3), (11.0, 0.8)],
        "vibrato": (0.35, 0.0015),
        "envelope": (0.7, 1.2, 0.9, 1.8),
        "cutoff": 2300.0, "resonance": 0.7, "gain": 1.05,
    },
    "pluck": {
        "label": "Plucked Synth",
        "description": "Short and percussive",
        "harmonics": "saw",
        "unison": [(-3.0, -0.3), (3.0, 0.3)],
        "vibrato": (0.0, 0.0),
        "envelope": (0.002, 0.55, 0.0, 0.25),
        "pluck": 0.12,                                # seconds for the bright attack to mellow
        "cutoff": 6500.0, "resonance": 0.9, "gain": 1.0,
    },

    # ---- Instruments: modelled on how the real instrument behaves --------------
    "piano": {
        "label": "Piano",
        "description": "Hammer attack that mellows and fades, like a real piano",
        "group": "Instruments",
        "harmonics": "piano", "dull": "piano_dull",
        "unison": [(-1.5, -0.25), (1.5, 0.25)],      # two slightly detuned strings per note
        "vibrato": (0.0, 0.0),
        "envelope": (0.002, 3.6, 0.0, 0.35),         # fades even while held, like a piano key
        "pluck": 0.35,
        "live_repeat": True,                         # a held gesture re-strikes the key (engine.py)
        "cutoff": 7000.0, "resonance": 0.7, "gain": 1.05,
    },
    "epiano": {
        "label": "Electric Piano",
        "description": "Soft, bell-like tine sound",
        "group": "Instruments",
        "harmonics": "bell", "dull": "sine",
        "unison": [(-3.0, -0.4), (3.0, 0.4)],
        "vibrato": (4.5, 0.0012),
        "envelope": (0.002, 2.8, 0.28, 0.45),
        "pluck": 0.28,
        "cutoff": 6000.0, "resonance": 0.7, "gain": 1.0,
    },
    "guitar": {
        "label": "Acoustic Guitar",
        "description": "Plucked strings with a natural fade",
        "group": "Instruments",
        "harmonics": "guitar", "dull": "dull",
        "unison": [(-2.0, -0.3), (2.0, 0.3)],
        "vibrato": (0.0, 0.0),
        "envelope": (0.002, 2.4, 0.0, 0.3),
        "pluck": 0.2,
        "cutoff": 6500.0, "resonance": 0.8, "gain": 1.05,
    },
    "strings": {
        "label": "Strings",
        "description": "A bowed string section that swells in",
        "group": "Instruments",
        "harmonics": "saw",
        "unison": [(-12.0, -0.8), (-5.0, -0.3), (5.0, 0.3), (12.0, 0.8)],
        "vibrato": (5.2, 0.003),
        "envelope": (0.35, 1.0, 0.9, 0.9),
        "cutoff": 3200.0, "resonance": 0.7, "gain": 0.95,
    },
    "organ": {
        "label": "Organ",
        "description": "Sustained drawbar organ with a gentle rotary wobble",
        "group": "Instruments",
        "harmonics": "organ",
        "unison": [(-2.0, -0.5), (2.0, 0.5)],
        "vibrato": (6.5, 0.0018),
        "envelope": (0.01, 0.05, 1.0, 0.08),
        "cutoff": 7000.0, "resonance": 0.7, "gain": 0.8,
    },
}

_ORGAN_DRAWBARS = {1: 1.0, 2: 0.7, 3: 0.5, 4: 0.4, 6: 0.25, 8: 0.2}
_BELL = {1: 1.0, 2: 0.45, 3: 0.12, 4: 0.3, 7: 0.22}

DEFAULT_PRESET = "warm"


def _amplitudes(recipe, harmonics):
    k = np.arange(1, harmonics + 1, dtype=float)
    if recipe == "pulse":       # 25% pulse wave: classic 8-bit/analogue sound
        return np.abs(np.sin(np.pi * k * 0.25)) / k
    if recipe == "saw":         # all harmonics: bright and buzzy
        return 1.0 / k
    if recipe == "warm":        # quickly fading harmonics: round, soft
        return 1.0 / k ** 1.9
    if recipe == "pad":         # gentle, mostly low harmonics
        return np.exp(-0.38 * (k - 1)) / k ** 0.5
    if recipe == "dull":        # a muted version of saw (end of a pluck)
        return np.exp(-0.55 * (k - 1)) / k
    if recipe == "piano":       # rich hammer strike
        return np.exp(-0.05 * (k - 1)) / k ** 1.35
    if recipe == "piano_dull":  # the warm tone a piano note settles into
        return np.exp(-0.45 * (k - 1)) / k ** 1.2
    if recipe == "guitar":      # plucked near the bridge: some harmonics are weaker
        return (0.35 + np.abs(np.sin(np.pi * k * 0.2))) / k ** 1.1
    if recipe == "sine":
        return (k == 1).astype(float)
    if recipe == "bell":        # electric-piano tine
        return np.array([_BELL.get(int(x), 0.0) for x in k])
    if recipe == "organ":       # drawbars 16' 8' 5 1/3' 4' 2 2/3' 2'
        return np.array([_ORGAN_DRAWBARS.get(int(x), 0.0) for x in k])
    raise ValueError(f"unknown harmonic recipe {recipe}")


def build_tables(recipe, sample_rate, levels=11, lowest=20.0):
    """Band-limited wavetables, one per octave, so high notes never alias.

    Table i is used for notes from lowest*2^i to lowest*2^(i+1) Hz and contains
    only the harmonics that stay below the Nyquist frequency.
    """
    tables = np.zeros((levels, TABLE_SIZE + 1), dtype=np.float32)
    for level in range(levels):
        top = lowest * 2 ** (level + 1)
        harmonics = int(max(1, min(TABLE_SIZE // 2 - 1, (sample_rate * 0.45) // top)))
        spectrum = np.zeros(TABLE_SIZE // 2 + 1)
        spectrum[1:harmonics + 1] = _amplitudes(recipe, harmonics)
        wave = np.fft.irfft(-1j * spectrum, TABLE_SIZE) * TABLE_SIZE / 2  # sum of sines
        tables[level, :TABLE_SIZE] = wave
    # Normalise loudness so every preset has a similar volume.
    rms = np.sqrt(np.mean(tables[3, :TABLE_SIZE] ** 2))
    tables /= max(rms, 1e-9) * 3.2
    tables[:, TABLE_SIZE] = tables[:, 0]  # wrap-around sample for interpolation
    return tables


class Preset:
    """A preset with its wavetables pre-computed (built once at start-up)."""

    def __init__(self, key, spec, sample_rate):
        self.key = key
        self.label = spec["label"]
        self.unison = spec["unison"]
        self.vibrato_rate, self.vibrato_depth = spec["vibrato"]
        self.attack, self.decay, self.sustain, self.release = spec["envelope"]
        self.cutoff = spec["cutoff"]
        self.resonance = spec["resonance"]
        self.gain = spec["gain"] / np.sqrt(len(self.unison))
        self.pluck = spec.get("pluck", 0.0)
        self.live_repeat = spec.get("live_repeat", False)
        self.tables = build_tables(spec["harmonics"], sample_rate)
        # Plucked/struck sounds start bright and fade towards this softer tone.
        self.dull_tables = build_tables(spec.get("dull", "dull"), sample_rate) if self.pluck else None


def load_presets(sample_rate):
    return {key: Preset(key, spec, sample_rate) for key, spec in PRESETS.items()}


def preset_catalog():
    """What the interface needs to show the preset dropdown (grouped)."""
    return [{"id": key, "label": spec["label"], "description": spec["description"],
             "group": spec.get("group", "Synths")}
            for key, spec in PRESETS.items()]

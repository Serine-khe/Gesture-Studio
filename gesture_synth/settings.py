"""Your preferences (chosen in the Settings screen), saved to user_settings.json.

The file is written automatically whenever something changes, and read when
the app starts. Delete it to go back to the defaults.
"""

import json
import os
import threading
import time

from .config import PROJECT_DIR
from .music import KEY_NAMES
from .presets import PRESETS

SETTINGS_PATH = os.path.join(PROJECT_DIR, "user_settings.json")

DEFAULTS = {
    "camera_index": 0,
    "mirror": True,
    "steadiness": 3,             # 1 = very responsive ... 5 = very steady
    "thumb_sensitivity": 0.6,    # higher = thumb must stick out further to count
    "show_left_guide": True,
    "show_right_guide": True,
    "show_hand_outlines": True,
    "swap_hands": False,         # for left-handed players: right hand picks chords
    "default_octave": 3,
    "default_preset": "warm",
    "piano_repeat": 0.5,         # seconds between strikes while a piano note is held
    "volume": 0.8,
    "key": "C",
    "scale": "major",
    "expression": "gesture",     # "gesture" = right hand shapes the sound, "manual" = sliders
    "tilt_filter": True,         # right-hand tilt changes brightness
    "tilt_minor": False,         # left-hand tilt switches major/minor
}

# Allowed values for each setting (validation for anything read from disk or the UI).
_RULES = {
    "camera_index": ("int", 0, 9),
    "mirror": ("bool",),
    "steadiness": ("int", 1, 5),
    "thumb_sensitivity": ("float", 0.3, 1.2),
    "show_left_guide": ("bool",),
    "show_right_guide": ("bool",),
    "show_hand_outlines": ("bool",),
    "swap_hands": ("bool",),
    "default_octave": ("int", 1, 5),
    "default_preset": ("choice", tuple(PRESETS)),
    "piano_repeat": ("float", 0.15, 1.5),
    "volume": ("float", 0.0, 1.0),
    "key": ("choice", tuple(KEY_NAMES)),
    "scale": ("choice", ("major", "minor")),
    "expression": ("choice", ("gesture", "manual")),
    "tilt_filter": ("bool",),
    "tilt_minor": ("bool",),
}

STABLE_FRAMES = {1: 2, 2: 3, 3: 4, 4: 6, 5: 8}   # steadiness -> frames a gesture must be held


def clean(key, value):
    """Return a valid value for `key`, or raise ValueError."""
    rule = _RULES.get(key)
    if rule is None:
        raise ValueError(f"unknown setting {key}")
    kind = rule[0]
    if kind == "bool":
        if isinstance(value, bool):
            return value
    elif kind in ("int", "float") and not isinstance(value, bool):
        number = int(round(float(value))) if kind == "int" else float(value)
        return min(max(number, rule[1]), rule[2])
    elif kind == "choice" and value in rule[1]:
        return value
    raise ValueError(f"invalid value {value!r} for {key}")


class Settings:
    def __init__(self, path=SETTINGS_PATH):
        self.path = path
        self.values = dict(DEFAULTS)
        self._dirty = False
        self._last_save = 0.0
        self._lock = threading.Lock()
        self.load()

    def load(self):
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8-sig") as handle:
                stored = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[settings] Could not read {os.path.basename(self.path)} ({exc}); using defaults.")
            return
        for key, value in stored.items():
            try:
                self.values[key] = clean(key, value)
            except (ValueError, TypeError):
                pass  # ignore unknown/invalid entries

    def __getitem__(self, key):
        return self.values[key]

    def set(self, key, value):
        value = clean(key, value)
        with self._lock:
            changed = self.values.get(key) != value
            self.values[key] = value
            self._dirty = self._dirty or changed
        return value

    def save_if_needed(self, force=False):
        """Write the file at most once a second (called from the main loop)."""
        now = time.perf_counter()
        if not self._dirty or (not force and now - self._last_save < 1.0):
            return False
        with self._lock:
            data, self._dirty = dict(self.values), False
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2)
            os.replace(tmp, self.path)
            self._last_save = now
            return True
        except OSError as exc:
            print(f"[settings] Could not save preferences: {exc}")
            return False

"""Loads config.json (advanced, rarely-changed options), fills in defaults and
fixes invalid values. Everyday preferences live in settings.py instead and are
changed from the Settings screen.

Any problem in the file produces a friendly warning in the console and falls
back to the default value, so a typo never crashes the app.
"""

import copy
import json
import os

from .gestures import GESTURES
from .music import parse_note

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_CONFIG = {
    "camera": {"index": 0, "width": 640, "height": 480},
    "detection": {
        "min_detection_confidence": 0.6,
        "min_tracking_confidence": 0.5,
        "model_complexity": 0,
    },
    "trigger": {"cooldown_seconds": 0.12},
    "audio": {"sample_rate": 44100, "chunk_size": 1024},
    "free_play": {
        # gesture -> scale degree (1-7, follows the chosen key) or a fixed note like "C4"
        "gesture_notes": {"one": 1, "two": 2, "three": 3, "four": 4, "palm": 5, "rock": 6, "shaka": 7},
    },
    "interface": {"port": 8765, "open_window": True, "quit_when_window_closed": True},
    "songs_file": "my_songs.json",   # your song guides (made in the app)
}


def default_config_path():
    return os.path.join(PROJECT_DIR, "config.json")


def load_config(path=None):
    """Return (config dict, list of warning strings)."""
    path = path or default_config_path()
    warnings = []
    config = copy.deepcopy(DEFAULT_CONFIG)
    if not os.path.exists(path):
        warnings.append(f"No config file at {path} - using built-in defaults.")
        return config, warnings
    try:
        # utf-8-sig tolerates the invisible BOM that Windows Notepad may add.
        with open(path, "r", encoding="utf-8-sig") as handle:
            user = json.load(handle)
    except json.JSONDecodeError as exc:
        warnings.append(f"config.json has a typo near line {exc.lineno}, column {exc.colno} "
                        f"({exc.msg}). Using defaults until it is fixed.")
        return config, warnings
    except OSError as exc:
        warnings.append(f"Could not read config.json ({exc}). Using defaults.")
        return config, warnings
    if not isinstance(user, dict):
        warnings.append("config.json must contain a { ... } object. Using defaults.")
        return config, warnings
    _merge(config, user, warnings, "")
    _validate(config, warnings)
    return config, warnings


def _merge(base, override, warnings, prefix):
    for key, value in override.items():
        if key.startswith("_"):  # "_comment" style keys are ignored
            continue
        where = f"{prefix}{key}"
        if key not in base:
            if prefix.rstrip(".").endswith("gesture_notes"):
                base[key] = value
            else:
                warnings.append(f"Unknown setting '{where}' was ignored (check spelling).")
            continue
        if isinstance(base[key], dict) and isinstance(value, dict):
            if key == "gesture_notes":
                base[key] = {}  # the user's mapping replaces the default one
            _merge(base[key], value, warnings, where + ".")
        else:
            base[key] = value


def _number(section, key, low, high, default, warnings, where, cast=float):
    value = section.get(key)
    try:
        if isinstance(value, bool):
            raise TypeError
        value = cast(value)
        if not low <= value <= high:
            raise ValueError
        section[key] = value
    except (TypeError, ValueError):
        warnings.append(f"{where}.{key} should be a number from {low} to {high}; using {default}.")
        section[key] = default


def _flag(section, key, default, warnings, where):
    if not isinstance(section.get(key), bool):
        warnings.append(f"{where}.{key} must be true or false; using {str(default).lower()}.")
        section[key] = default


def _validate(cfg, warnings):
    d = DEFAULT_CONFIG
    cam, dcam = cfg["camera"], d["camera"]
    _number(cam, "index", 0, 10, dcam["index"], warnings, "camera", int)
    _number(cam, "width", 160, 3840, dcam["width"], warnings, "camera", int)
    _number(cam, "height", 120, 2160, dcam["height"], warnings, "camera", int)

    det, ddet = cfg["detection"], d["detection"]
    _number(det, "min_detection_confidence", 0.1, 1.0, ddet["min_detection_confidence"], warnings, "detection")
    _number(det, "min_tracking_confidence", 0.1, 1.0, ddet["min_tracking_confidence"], warnings, "detection")
    _number(det, "model_complexity", 0, 1, ddet["model_complexity"], warnings, "detection", int)

    _number(cfg["trigger"], "cooldown_seconds", 0.0, 5.0, d["trigger"]["cooldown_seconds"], warnings, "trigger")

    aud, daud = cfg["audio"], d["audio"]
    _number(aud, "sample_rate", 22050, 96000, daud["sample_rate"], warnings, "audio", int)
    _number(aud, "chunk_size", 256, 4096, daud["chunk_size"], warnings, "audio", int)

    ui, dui = cfg["interface"], d["interface"]
    _number(ui, "port", 1024, 65535, dui["port"], warnings, "interface", int)
    _flag(ui, "open_window", dui["open_window"], warnings, "interface")
    _flag(ui, "quit_when_window_closed", dui["quit_when_window_closed"], warnings, "interface")

    mapping = cfg["free_play"].get("gesture_notes")
    if not isinstance(mapping, dict):
        warnings.append("free_play.gesture_notes must be a { gesture: note } object; using defaults.")
        mapping = dict(d["free_play"]["gesture_notes"])
    for gesture, value in list(mapping.items()):
        if gesture not in GESTURES or gesture == "fist":
            warnings.append(f"free_play.gesture_notes: '{gesture}' is not a usable gesture. "
                            f"Valid: {', '.join(g for g in GESTURES if g != 'fist')}.")
            del mapping[gesture]
            continue
        if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 14:
            continue
        try:
            parse_note(value)
        except ValueError as exc:
            warnings.append(f"free_play.gesture_notes.{gesture}: use a scale step 1-7 or a note. {exc}")
            del mapping[gesture]
    cfg["free_play"]["gesture_notes"] = mapping
    if not isinstance(cfg.get("songs_file"), str):
        cfg["songs_file"] = d["songs_file"]

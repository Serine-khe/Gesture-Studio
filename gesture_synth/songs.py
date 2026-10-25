"""Your song guides, saved to my_songs.json.

A guide is a song you type in yourself: a title, and its sections (Verse,
Chorus...) as the chords you looked up, in order. The app gives every chord a
hand gesture and shows you which one comes next while you play.

    {"songs": [{"id": "my-song", "title": "My Song", "artist": "",
                "sections": [{"name": "Verse", "chords": ["C", "G", "Am", "F"]}]}]}

Guides are made in the app (My Songs > New song), so you never need to edit
this file by hand. Delete it to start over.
"""

import json
import os
import re
import threading

from .config import PROJECT_DIR
from .music import chord_family, parse_chord

# Gestures handed out (in this order) to a song's chords.
AUTO_GESTURES = ["one", "two", "three", "four", "palm", "rock", "shaka"]

MAX_SONGS = 500
MAX_SECTIONS = 16
MAX_CHORDS = 64          # per section
MAX_TEXT = 80            # title / artist / section name length

# Shown the first time the app starts, so there is something to try right away.
EXAMPLE = {"id": "example", "title": "Example: four-chord practice", "artist": "",
           "sections": [{"name": "Verse", "chords": ["C", "G", "Am", "F"]},
                        {"name": "Chorus", "chords": ["F", "G", "C", "Am"]}]}

# Other ways chord charts write the same chord.
_SPELLINGS = [("♯", "#"), ("♭", "b"), ("Δ", "maj7"), ("°7", "dim7"), ("°", "dim"), ("ø7", "m7b5"),
              ("ø", "m7b5"), ("min7", "m7"), ("M7", "maj7"), ("+", "aug")]


def normalize_chord(text):
    """'B♭' -> 'Bb', 'Cmin7' -> 'Cm7', 'G+' -> 'Gaug' (the spellings the app knows)."""
    text = text.strip()
    for old, new in _SPELLINGS:
        text = text.replace(old, new)
    return text


def parse_chords(value, where):
    """Chords typed as "C G Am F" (spaces, commas or bars between them) or a list.
    Returns the list of chord symbols; raises ValueError naming every bad chord."""
    items = value if isinstance(value, list) else re.split(r"[\s,|]+", str(value))
    chords, bad = [], []
    for item in items:
        symbol = normalize_chord(str(item))
        if not symbol or re.fullmatch(r"[-–—.:/\\]+", symbol):   # separators like "C - G"
            continue
        try:
            parse_chord(symbol)
            chords.append(symbol)
        except ValueError:
            bad.append(str(item).strip())
    if bad:
        raise ValueError(f"{where}: unknown chord{'s' if len(bad) > 1 else ''} {', '.join(bad)} "
                         f"(write chords like C, F#m, Bb7, Am/G, Dsus4)")
    if len(chords) > MAX_CHORDS:
        raise ValueError(f"{where}: at most {MAX_CHORDS} chords per section")
    return chords


def _text(value, limit):
    return " ".join(str(value or "").split())[:limit]


def clean_song(entry):
    """Check a guide (from the editor or the file) and return its stored form."""
    if not isinstance(entry, dict):
        raise ValueError("a song must be a { ... } object")
    title = _text(entry.get("title"), MAX_TEXT)
    if not title:
        raise ValueError("give the song a title")
    sections = entry.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError("add at least one section with chords")
    if len(sections) > MAX_SECTIONS:
        raise ValueError(f"at most {MAX_SECTIONS} sections")
    cleaned = []
    for i, section in enumerate(sections):
        if not isinstance(section, dict):
            raise ValueError("each section must be { \"name\": ..., \"chords\": ... }")
        name = _text(section.get("name"), MAX_TEXT) or f"Part {i + 1}"
        chords = parse_chords(section.get("chords", ""), name)
        if chords:
            cleaned.append({"name": name, "chords": chords})
    if not cleaned:
        raise ValueError("add the chords of at least one section")
    return {"id": str(entry.get("id") or ""), "title": title,
            "artist": _text(entry.get("artist"), MAX_TEXT), "sections": cleaned}


def auto_gestures(chords):
    """Give gestures to a song's chords. Returns (mapping, mode).

    "exact": the song has at most 7 different chords, so every chord - including
    slash chords like G/B and colours like Fmaj7 - gets its own gesture.
    "family": more than 7, so variants of one chord (F, Fmaj7, F6, F/A) share a
    gesture and the app plays whichever variant the song has at that moment.
    """
    unique = list(dict.fromkeys(chords))
    if len(unique) <= len(AUTO_GESTURES):
        return dict(zip(AUTO_GESTURES, unique)), "exact"
    count, first, names = {}, {}, {}
    for i, chord in enumerate(chords):
        fam = chord_family(chord)
        count[fam] = count.get(fam, 0) + 1
        first.setdefault(fam, i)
        names.setdefault(fam, {})
        names[fam][chord] = names[fam].get(chord, 0) + 1
    chosen = sorted(count, key=count.get, reverse=True)[:len(AUTO_GESTURES)]
    chosen.sort(key=first.get)  # gestures follow the order chords first appear
    return {g: max(names[fam], key=names[fam].get) for g, fam in zip(AUTO_GESTURES, chosen)}, "family"


def build(stored):
    """Everything the player needs from a stored guide: one list of chords in
    playing order, its sections, a key (for transposing) and the gestures."""
    chords, parts = [], []
    for section in stored["sections"]:
        parts.append({"name": section["name"], "index": len(chords), "length": len(section["chords"])})
        chords.extend({"chord": c, "section": section["name"]} for c in section["chords"])
    symbols = [c["chord"] for c in chords]
    mapping, gesture_mode = auto_gestures(symbols)
    if gesture_mode == "exact":
        variants = {g: [c] for g, c in mapping.items()}
    else:
        variants = {g: list(dict.fromkeys(c for c in symbols if chord_family(c) == chord_family(rep)))
                    for g, rep in mapping.items()}
    covered = {v for vs in variants.values() for v in vs}
    # The key is read from the first chord: it only decides sharps or flats when transposing.
    key_pc, kind = chord_family(symbols[0])
    return dict(stored, chords=chords, parts=parts, key_pc=key_pc, mode="minor" if kind == "m" else "major",
                gesture_chords=mapping, gesture_mode=gesture_mode, variants=variants,
                unmapped=[c for c in dict.fromkeys(symbols) if c not in covered])


def _slug(title, taken):
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "song"
    slug, n = base, 2
    while slug in taken:
        slug, n = f"{base}-{n}", n + 1
    return slug


class SongLibrary:
    """The guides in my_songs.json. Changed only from the main loop; saved at once."""

    def __init__(self, filename="my_songs.json"):
        self.path = filename if os.path.isabs(filename) else os.path.join(PROJECT_DIR, filename)
        self.songs = []          # built guides, in the order they were added
        self.rev = 0             # goes up on every change (the interface reloads its list)
        self.warnings = []
        self._lock = threading.Lock()
        self.load()

    def load(self):
        if not os.path.exists(self.path):
            self.songs = [build(EXAMPLE)]
            return
        try:
            with open(self.path, "r", encoding="utf-8-sig") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            self.warnings.append(f"Could not read {os.path.basename(self.path)}: {exc}")
            return
        entries = data.get("songs", []) if isinstance(data, dict) else []
        taken = set()
        for i, entry in enumerate(entries[:MAX_SONGS] if isinstance(entries, list) else []):
            try:
                stored = clean_song(entry)
            except ValueError as exc:
                self.warnings.append(f"my_songs.json song {i + 1}: {exc} (skipped)")
                continue
            if not stored["id"] or stored["id"] in taken:
                stored["id"] = _slug(stored["title"], taken)
            taken.add(stored["id"])
            self.songs.append(build(stored))

    def get(self, song_id):
        return next((s for s in self.songs if s["id"] == song_id), None)

    def save_song(self, entry):
        """Add a new guide or replace one (same id). Returns the built guide."""
        stored = clean_song(entry)
        old = self.get(stored["id"]) if stored["id"] else None
        if old is None:
            if len(self.songs) >= MAX_SONGS:
                raise ValueError(f"at most {MAX_SONGS} songs")
            stored["id"] = _slug(stored["title"], {s["id"] for s in self.songs})
        song = build(stored)
        if old is None:
            self.songs.append(song)
        else:
            self.songs[self.songs.index(old)] = song
        self._write()
        return song

    def delete(self, song_id):
        song = self.get(song_id)
        if song is not None:
            self.songs.remove(song)
            self._write()

    @staticmethod
    def stored(song):
        return {"id": song["id"], "title": song["title"], "artist": song["artist"], "sections": song["sections"]}

    def _write(self):
        self.rev += 1
        data = {"songs": [self.stored(s) for s in self.songs]}
        with self._lock:
            try:
                tmp = self.path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as handle:
                    json.dump(data, handle, indent=2, ensure_ascii=False)
                os.replace(tmp, self.path)
            except OSError as exc:
                print(f"[songs] Could not save your songs: {exc}")

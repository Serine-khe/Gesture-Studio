"""Music theory helpers, written so you don't need to know music theory.

Vocabulary used in this project:
  * pitch class (pc): a note name without octave, as a number 0-11 (C=0, C#=1 ... B=11)
  * MIDI number: a specific piano key. Middle C (C4) = 60. One octave = 12 steps.
  * scale degree 1-7: the 1st..7th note of a major/minor scale. Building a chord on
    each degree gives the 7 chords that "belong" to a key - they always sound good together.
  * voicing: which octave each chord note is placed in (root position, inversions...)
"""

import re
from dataclasses import dataclass

SHARP_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLAT_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
KEY_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]  # friendly spellings

SCALES = {
    "major": (0, 2, 4, 5, 7, 9, 11),
    "minor": (0, 2, 3, 5, 7, 8, 10),   # natural minor
}

_LETTER_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_ACCIDENTAL = {"": 0, "#": 1, "b": -1}
_NOTE_RE = re.compile(r"^([A-Ga-g])([#b]?)(-?\d)$")
_CHORD_RE = re.compile(r"^([A-Ga-g])([#b]?)(.*)$")
_PC_RE = re.compile(r"^([A-Ga-g])([#b]?)$")

# Chord quality suffix -> semitone intervals above the root.
CHORD_QUALITIES = {
    "": (0, 4, 7), "maj": (0, 4, 7), "m": (0, 3, 7), "min": (0, 3, 7),
    "7": (0, 4, 7, 10), "maj7": (0, 4, 7, 11), "m7": (0, 3, 7, 10),
    "m7b5": (0, 3, 6, 10), "6": (0, 4, 7, 9), "m6": (0, 3, 7, 9),
    "add9": (0, 4, 7, 14), "sus2": (0, 2, 7), "sus4": (0, 5, 7), "sus": (0, 5, 7),
    "dim": (0, 3, 6), "aug": (0, 4, 8), "5": (0, 7),
    "add2": (0, 2, 4, 7), "madd9": (0, 3, 7, 14), "9": (0, 4, 7, 10, 14), "m9": (0, 3, 7, 10, 14),
    "maj9": (0, 4, 7, 11, 14), "7sus4": (0, 5, 7, 10), "dim7": (0, 3, 6, 9), "mmaj7": (0, 3, 7, 11),
    "6sus2": (0, 2, 7, 9), "add11": (0, 4, 7, 17), "madd11": (0, 3, 7, 17),
}
_SLASH_RE = re.compile(r"^(.+?)/([A-Ga-g])([#b]?)$")


def split_slash(symbol):
    """'C/E' -> ('C', pitch class of E); 'Am' -> ('Am', None)."""
    text = str(symbol).strip()
    match = _SLASH_RE.match(text)
    if not match:
        return text, None
    main, letter, accidental = match.groups()
    return main, (_LETTER_PC[letter.upper()] + _ACCIDENTAL[accidental]) % 12

# How each chord type is described to a beginner: (suffix, long name, feeling)
_QUALITY_INFO = {
    (0, 4, 7): ("", "major", "bright"),
    (0, 3, 7): ("m", "minor", "mellow"),
    (0, 3, 6): ("dim", "diminished", "tense"),
    (0, 4, 8): ("aug", "augmented", "dreamy"),
    (0, 4, 7, 11): ("maj7", "major 7th", "smooth"),
    (0, 3, 7, 10): ("m7", "minor 7th", "soulful"),
    (0, 4, 7, 10): ("7", "dominant 7th", "bluesy"),
    (0, 3, 6, 10): ("m7b5", "half-diminished", "mysterious"),
    (0, 2, 7): ("sus2", "sus2", "open"),
    (0, 5, 7): ("sus4", "sus4", "floating"),
    (0, 7): ("5", "power chord", "punchy"),
}

ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII"]


@dataclass(frozen=True)
class Note:
    name: str     # e.g. "C#"
    octave: int   # e.g. 4
    midi: int     # MIDI number, C4 = 60

    @property
    def label(self):
        return f"{self.name}{self.octave}"


def midi_to_freq(midi):
    return 440.0 * 2.0 ** ((midi - 69) / 12.0)


def uses_flats(key_pc, scale):
    """Keys like F, Bb, Eb (and D/G/C minor) are traditionally written with flats."""
    major_equivalent = key_pc if scale == "major" else (key_pc + 3) % 12
    return major_equivalent in (5, 10, 3, 8, 1, 6)


def pc_name(pc, flats=False):
    return (FLAT_NAMES if flats else SHARP_NAMES)[pc % 12]


def midi_name(midi, flats=False):
    return Note(pc_name(midi, flats), midi // 12 - 1, midi)


def parse_pitch_class(text):
    match = _PC_RE.match(str(text).strip())
    if not match:
        raise ValueError(f"'{text}' is not a valid key (examples: C, F#, Bb).")
    letter, accidental = match.groups()
    return (_LETTER_PC[letter.upper()] + _ACCIDENTAL[accidental]) % 12


def parse_note(text):
    """Parse "C#4" into a Note. Raises ValueError with a friendly message."""
    match = _NOTE_RE.match(str(text).strip())
    if not match:
        raise ValueError(f"'{text}' is not a valid note. Use a letter A-G, optional # or b, "
                         f"then an octave number, e.g. C4, F#3, Bb5.")
    letter, accidental, octave = match.groups()
    letter = letter.upper()
    octave = int(octave)
    midi = 12 * (octave + 1) + _LETTER_PC[letter] + _ACCIDENTAL[accidental]
    return Note(letter + accidental, octave, midi)


def chord_bass(symbol):
    """Pitch class of a slash chord's bass note ('C/E' -> 4), or None."""
    return split_slash(symbol)[1]


def chord_family(symbol):
    """The basic chord behind a symbol: 'Fmaj7', 'F6' and 'F/A' are all ('F', major).
    Used to match what you play with what the song expects."""
    root, intervals = parse_chord(symbol)
    triad = set(intervals)
    kind = "dim" if {3, 6} <= triad and 7 not in triad else "m" if 3 in triad and 4 not in triad else ""
    return root, kind


def parse_chord(symbol):
    """Parse "F#m" (or "C/E") into (root pitch class 0-11, intervals). Raises ValueError."""
    symbol, _bass = split_slash(symbol)
    match = _CHORD_RE.match(str(symbol).strip())
    if not match:
        raise ValueError(f"'{symbol}' is not a valid chord (examples: C#, A, F#m, G7).")
    letter, accidental, quality = match.groups()
    if quality not in CHORD_QUALITIES:
        known = ", ".join(q or "(major)" for q in CHORD_QUALITIES)
        raise ValueError(f"Unknown chord type '{quality}' in '{symbol}'. Known types: {known}.")
    root_pc = (_LETTER_PC[letter.upper()] + _ACCIDENTAL[accidental]) % 12
    return root_pc, CHORD_QUALITIES[quality]


def transpose_symbol(symbol, semitones, flats=False):
    """'F#m' moved up 2 semitones -> 'G#m' (spelled with flats if `flats`)."""
    if semitones % 12 == 0:
        return symbol
    main, bass = split_slash(symbol)
    letter, accidental, quality = _CHORD_RE.match(main).groups()
    pc = (_LETTER_PC[letter.upper()] + _ACCIDENTAL[accidental] + semitones) % 12
    text = pc_name(pc, flats) + quality
    if bass is not None:
        text += "/" + pc_name(bass + semitones, flats)
    return text


# ----------------------------------------------------------- keys and scales
def scale_note(key_pc, scale, degree, octave):
    """MIDI number of scale degree 1-7 (degree 8 = next octave's 1, etc.)."""
    steps = SCALES[scale]
    index = degree - 1
    return 12 * (octave + 1) + key_pc + steps[index % 7] + 12 * (index // 7)


def diatonic_chord(key_pc, scale, degree, seventh=False):
    """The chord that belongs to the key on this scale degree.

    Built by stacking every other scale note ("thirds"), which is how the
    seven chords of a key are formed. Returns (root pc, intervals).
    """
    steps = SCALES[scale]
    index = degree - 1
    tones = []
    for i in range(4 if seventh else 3):
        j = index + 2 * i
        tones.append(steps[j % 7] + 12 * (j // 7))
    root = tones[0]
    return (key_pc + root) % 12, tuple(t - root for t in tones)


def add_seventh(root_pc, intervals, key_pc=None, scale="major"):
    """Turn a triad into a 7th chord, choosing the 7th that fits the key.

    e.g. in A major: A -> Amaj7, E -> E7 (dominant), F#m -> F#m7, C# -> C#7.
    """
    if len(intervals) >= 4:
        return tuple(intervals)
    triad = tuple(intervals[:3])
    if key_pc is not None:
        scale_pcs = {(key_pc + s) % 12 for s in SCALES[scale]}
        for candidate in (11, 10):
            if (root_pc + candidate) % 12 in scale_pcs and (triad, candidate) != ((0, 3, 7), 11):
                return triad + (candidate,)
    return triad + ((11,) if triad == (0, 4, 7) else (10,))


def chord_info(root_pc, intervals, flats=False):
    """Display names for a chord: symbol 'F#m7', name 'F# minor 7th', feeling 'soulful'."""
    suffix, long_name, mood = _QUALITY_INFO.get(tuple(intervals), ("", "chord", ""))
    root = pc_name(root_pc, flats)
    return {"symbol": root + suffix, "name": f"{root} {long_name}", "mood": mood, "quality": long_name}


def roman_numeral(degree, intervals):
    """'I', 'ii', 'V7', 'vii°' - the chord's position in the key."""
    numeral = ROMAN[(degree - 1) % 7]
    triad = tuple(intervals[:3])
    if triad in ((0, 3, 7), (0, 3, 6)):
        numeral = numeral.lower()
    if triad == (0, 3, 6):
        numeral += "°" if len(intervals) == 3 else "ø"
    elif len(intervals) >= 4:
        numeral += "7"
    return numeral


# ------------------------------------------------------------------ voicing
VOICINGS = {
    "root": "Root position",
    "first": "1st inversion",
    "second": "2nd inversion",
    "seventh": "Seventh chord",
    "spread": "Open & wide",
}


def voice_lead(root_pc, intervals, previous=None, octave=3, register=0, bass_pc=None):
    """Voice a chord the way a player would when moving from the previous chord.

    The bass plays the chord's root (or the slash-chord bass) in a fixed low range,
    and the upper notes use whichever inversion moves least from `previous`
    (the previous chord's upper notes). Returns (all notes, upper notes).
    """
    shift = 12 * (octave - 3 + register)
    low = 53 + shift                                    # F3: bottom of the upper-voice range
    pcs = list(dict.fromkeys((root_pc + i) % 12 for i in intervals))
    candidates = []
    for start in range(len(pcs)):
        notes, current = [], None
        for pc in pcs[start:] + pcs[:start]:
            current = low + (pc - low) % 12 if current is None else current + ((pc - current) % 12 or 12)
            notes.append(current)
        candidates.append(notes)
    if previous:
        def cost(notes):
            return (sum(min(abs(n - p) for p in previous) for n in notes)
                    + sum(min(abs(p - n) for n in notes) for p in previous))
        upper = min(candidates, key=cost)
    else:
        upper = candidates[0]                           # first chord: root position
    bass_note = bass_pc if bass_pc is not None else root_pc
    bass = 40 + shift + (bass_note - (40 + shift)) % 12   # E2..D#3, always below the upper notes
    return sorted(set([bass] + upper)), upper


def voice_chord(root_pc, intervals, voicing="root", octave=3, register=0, bass_pc=None):
    """Place chord notes on the keyboard. Returns a sorted list of MIDI notes.

    root: notes stacked from the root (C-E-G)
    first/second inversion: the lowest notes move up an octave (E-G-C, G-C-E),
        which often sounds smoother when changing chords
    seventh: the caller adds a 4th note first; it is voiced like root position
    spread: open, wide voicing (root, 5th, octave, 10th) - big and airy
    A bass note one octave below the lowest note makes the chord feel grounded.
    `bass_pc` (slash chords like C/E) puts that note in the bass instead.
    """
    base = 12 * (octave + 1) + root_pc
    tones = [base + i for i in intervals]
    if voicing == "first":
        tones = tones[1:] + [tones[0] + 12]
    elif voicing == "second" and len(tones) >= 3:
        tones = tones[2:] + [t + 12 for t in tones[:2]]
    elif voicing == "spread" and len(tones) >= 3:
        third, fifth = tones[1], tones[2]
        extra = [tones[3] + 12] if len(tones) >= 4 else []
        tones = [base, fifth, base + 12, third + 12] + extra
    lowest = min(tones)
    if bass_pc is None:
        bass = lowest - 12
    else:
        bass = lowest - ((lowest - bass_pc) % 12 or 12)
        if lowest - bass < 5:  # keep the bass clearly below the chord
            bass -= 12
    notes = sorted(set([bass] + tones))
    return [n + 12 * register for n in notes]

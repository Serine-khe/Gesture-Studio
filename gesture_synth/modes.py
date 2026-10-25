"""The three ways to play: Synth (two-handed chords), Free Play (single notes)
and My Songs (play along with a song guide you made).

Every mode receives the two hands once per camera frame:
  * harmony hand (left by default) - picks WHAT is played
  * sound hand (right by default)  - shapes HOW it sounds
and tells the audio engine what to play. Modes also describe themselves for
the interface (`snapshot()`), so the screen always shows what each gesture does.
"""

from .gestures import gesture_label
from .music import (VOICINGS, add_seventh, chord_bass, chord_family, chord_info, diatonic_chord, midi_name,
                    parse_chord,
                    parse_note, parse_pitch_class, pc_name, roman_numeral, scale_note, transpose_symbol,
                    uses_flats, voice_chord, voice_lead)

# Left (harmony) hand: finger shapes -> scale degree 1-7
DEGREE_GESTURES = {"one": 1, "two": 2, "three": 3, "four": 4, "palm": 5, "rock": 6, "shaka": 7}
# Right (sound) hand: finger shapes -> voicing
VOICING_GESTURES = {"one": "root", "two": "first", "three": "second", "four": "seventh", "palm": "spread"}
REGISTER_LABELS = {-1: "Low", 0: "Middle", 1: "High"}
GUIDE_VOICINGS = {"root": "Root", "first": "Inversion 1", "second": "Inversion 2",
                  "seventh": "7th chord", "spread": "Wide"}  # short names for the guide
ORDINAL = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th", 6: "6th", 7: "7th"}


class SoundShaping:
    """Right-hand controls shared by Synth and Songs: voicing, register,
    volume (hand height) and brightness (hand tilt) - or manual sliders."""

    def __init__(self, studio):
        self.studio = studio
        self.voicing = "root"
        self.register = 0
        self.gesture_volume = 0.85     # last level set by hand height
        self.gesture_brightness = 0.5
        self.manual_brightness = 0.5
        self._sent = None

    @property
    def manual(self):
        return self.studio.settings["expression"] == "manual"

    def update(self, hand):
        """Returns True if the voicing or register changed (chords must be re-voiced)."""
        changed = False
        if not self.manual and hand is not None:
            if hand.changed:
                g = hand.gesture
                if g in VOICING_GESTURES and VOICING_GESTURES[g] != self.voicing:
                    self.voicing, changed = VOICING_GESTURES[g], True
                elif g == "rock":
                    self.register, changed = (0 if self.register == 1 else 1), True
                    self.studio.toast(f"Register: {REGISTER_LABELS[self.register]}")
                elif g == "shaka":
                    self.register, changed = (0 if self.register == -1 else -1), True
                    self.studio.toast(f"Register: {REGISTER_LABELS[self.register]}")
            # Hand height -> volume: bottom of the picture = silent, upper area = full.
            target = min(max((hand.height - 0.12) / 0.6, 0.0), 1.0)
            self.gesture_volume += (target - self.gesture_volume) * 0.35
            if self.studio.settings["tilt_filter"]:
                tilt = hand.tilt_out
                tilt = 0.0 if abs(tilt) < 6 else tilt - 6 * (1 if tilt > 0 else -1)
                target = min(max(0.5 + tilt / 60.0, 0.0), 1.0)
                self.gesture_brightness += (target - self.gesture_brightness) * 0.3
        self.send()
        return changed

    def levels(self):
        if self.manual:
            return 1.0, self.manual_brightness
        bright = self.gesture_brightness if self.studio.settings["tilt_filter"] else 0.5
        return self.gesture_volume, bright

    def send(self, force=False):
        levels = self.levels()
        if force or self._sent is None or max(abs(a - b) for a, b in zip(levels, self._sent)) > 0.004:
            self.studio.audio.expression(*levels)
            self._sent = levels

    def describe(self):
        return {"voicing": self.voicing, "voicing_label": VOICINGS[self.voicing],
                "register": self.register, "register_label": REGISTER_LABELS[self.register],
                "volume": round(self.levels()[0], 3), "brightness": round(self.levels()[1], 3),
                "manual": self.manual}

    def guide_rows(self, hand_gesture):
        rows = [{"gesture": g, "label": gesture_label(g), "value": GUIDE_VOICINGS[v],
                 "active": self.voicing == v, "now": hand_gesture == g}
                for g, v in VOICING_GESTURES.items()]
        rows.append({"gesture": "rock", "label": gesture_label("rock"), "value": "Higher",
                     "active": self.register == 1, "now": hand_gesture == "rock"})
        rows.append({"gesture": "shaka", "label": gesture_label("shaka"), "value": "Lower",
                     "active": self.register == -1, "now": hand_gesture == "shaka"})
        return rows


class SynthMode:
    """Two-handed chord synth: left hand chooses the chord, right hand shapes it."""
    key = "synth"

    def __init__(self, studio):
        self.studio = studio
        self.degree = None
        self.sounding = []
        self._tilt_minor = False

    def enter(self):
        self.sounding = []
        self.studio.shaping.send(force=True)

    def leave(self):
        self.studio.audio.notes("chord", [])
        self.sounding = []

    def stop(self):
        self.sounding = []

    def scale(self):
        st = self.studio.settings
        if st["tilt_minor"]:
            return "minor" if self._tilt_minor else "major"
        return st["scale"]

    def chord_for(self, degree, scale=None):
        st = self.studio.settings
        scale = scale or self.scale()
        key_pc = parse_pitch_class(st["key"])
        shaping = self.studio.shaping
        root_pc, intervals = diatonic_chord(key_pc, scale, degree, seventh=shaping.voicing == "seventh")
        return root_pc, intervals

    def notes_for(self, degree):
        shaping = self.studio.shaping
        root_pc, intervals = self.chord_for(degree)
        voicing = "root" if shaping.voicing == "seventh" else shaping.voicing
        return voice_chord(root_pc, intervals, voicing, self.studio.octave, shaping.register)

    def update(self, harmony, sound):
        self.studio.shaping.update(sound)
        if self.studio.settings["tilt_minor"] and harmony is not None:
            # Hysteresis: lean clearly outward to go minor, come back clearly to return.
            if harmony.tilt_out > 22:
                self._tilt_minor = True
            elif harmony.tilt_out < 10:
                self._tilt_minor = False
        gesture = harmony.gesture if harmony is not None else None
        self.degree = DEGREE_GESTURES.get(gesture)
        if gesture == "unknown" and self.sounding:
            return  # keep the chord while the hand is between shapes
        notes = self.notes_for(self.degree) if self.degree else []
        if notes != self.sounding:
            self.studio.audio.notes("chord", notes, live=True)
            self.sounding = notes

    def snapshot(self, harmony, sound):
        st = self.studio.settings
        scale = self.scale()
        key_pc = parse_pitch_class(st["key"])
        flats = uses_flats(key_pc, scale)
        display = {"active": bool(self.sounding), "notes": [midi_name(n, flats).label for n in self.sounding]}
        if self.degree and self.sounding:
            root_pc, intervals = self.chord_for(self.degree)
            info = chord_info(root_pc, intervals, flats)
            display.update(headline=info["symbol"], title=info["name"],
                           caption=f"{roman_numeral(self.degree, intervals)} · {info['mood']}",
                           detail=f"{VOICINGS[self.studio.shaping.voicing]} · "
                                  f"{REGISTER_LABELS[self.studio.shaping.register]} register")
        else:
            display.update(headline="", title=f"{st['key']} {scale}",
                           caption="Show 1-5 fingers with your left hand to play a chord",
                           detail="")
        rows = []
        for g, degree in DEGREE_GESTURES.items():
            root_pc, intervals = self.chord_for(degree, scale)
            rows.append({"gesture": g, "label": gesture_label(g), "value": chord_info(root_pc, intervals, flats)["symbol"],
                         "sub": roman_numeral(degree, intervals), "active": self.degree == degree,
                         "now": harmony is not None and harmony.gesture == g})
        rows.append({"gesture": "fist", "label": "Fist", "value": "Stop chord", "sub": "",
                     "active": False, "now": harmony is not None and harmony.gesture == "fist"})
        return {
            "display": display,
            "scale": scale,
            "guides": {
                "harmony": {"title": "Chords", "rows": rows,
                            "footer": "Tilt outward for minor" if st["tilt_minor"] else ""},
                "sound": {"title": "Sound", "rows": self.studio.shaping.guide_rows(
                    sound.gesture if sound else None),
                          "footer": "Raise or lower your hand to change volume"
                                    + (" · tilt it to change brightness" if st["tilt_filter"] else "")},
            },
        }


class FreePlayMode:
    """Single notes: each hand plays the note its gesture is mapped to.
    The sound hand plays one octave higher than the harmony hand."""
    key = "free"

    def __init__(self, studio):
        self.studio = studio
        self.current = {"harmony": None, "sound": None}
        self.last = None   # (role, midi, gesture)

    def enter(self):
        self.studio.audio.expression(1.0, 0.5)
        self.studio.shaping._sent = None

    def leave(self):
        for role in self.current:
            self.studio.audio.notes(f"free_{role}", [])
        self.current = {"harmony": None, "sound": None}

    def stop(self):
        self.current = {"harmony": None, "sound": None}

    def note_for(self, gesture, role):
        st = self.studio.settings
        value = self.studio.config["free_play"]["gesture_notes"].get(gesture)
        if value is None:
            return None
        octave = self.studio.octave + (1 if role == "sound" else 0)
        if isinstance(value, int):
            return scale_note(parse_pitch_class(st["key"]), st["scale"], value, octave)
        return parse_note(value).midi + 12 * (octave - self.studio.settings["default_octave"])

    def update(self, harmony, sound):
        for role, hand in (("harmony", harmony), ("sound", sound)):
            gesture = hand.gesture if hand is not None else None
            if gesture == "unknown" and self.current[role] is not None:
                continue
            midi = self.note_for(gesture, role) if gesture else None
            if midi != self.current[role]:
                self.studio.audio.notes(f"free_{role}", [midi] if midi is not None else [], live=True)
                self.current[role] = midi
                if midi is not None:
                    self.last = (role, midi, gesture)

    def _describe(self, midi, gesture):
        st = self.studio.settings
        key_pc = parse_pitch_class(st["key"])
        note = midi_name(midi, uses_flats(key_pc, st["scale"]))
        value = self.studio.config["free_play"]["gesture_notes"].get(gesture)
        step = f"{ORDINAL.get(value, str(value))} note of {st['key']} {st['scale']}" if isinstance(value, int) \
            else "fixed note"
        return note, step

    def snapshot(self, harmony, sound):
        st = self.studio.settings
        sounding = [m for m in self.current.values() if m is not None]
        display = {"active": bool(sounding)}
        key_pc = parse_pitch_class(st["key"])
        flats = uses_flats(key_pc, st["scale"])
        display["notes"] = [midi_name(m, flats).label for m in sorted(sounding)]
        if self.last and self.last[1] in sounding:
            note, step = self._describe(self.last[1], self.last[2])
            display.update(headline=note.name, title=f"Octave {note.octave}", caption=step,
                           detail="Both hands: " + " + ".join(display["notes"]) if len(sounding) > 1 else "")
        else:
            display.update(headline="", title=f"{st['key']} {st['scale']} scale",
                           caption="Each finger shape plays a note of the scale - try them in any order",
                           detail="")
        guides = {}
        for role, hand in (("harmony", harmony), ("sound", sound)):
            rows = []
            for g in self.studio.config["free_play"]["gesture_notes"]:
                midi = self.note_for(g, role)
                rows.append({"gesture": g, "label": gesture_label(g),
                             "value": midi_name(midi, flats).label, "sub": "",
                             "active": self.current[role] == midi and hand is not None and hand.gesture == g,
                             "now": hand is not None and hand.gesture == g})
            rows.append({"gesture": "fist", "label": "Fist", "value": "Silence", "sub": "", "active": False,
                         "now": hand is not None and hand.gesture == "fist"})
            guides[role] = {"title": "Low notes" if role == "harmony" else "High notes", "rows": rows,
                            "footer": ""}
        return {"display": display, "scale": st["scale"], "guides": guides}


class SongsMode:
    """Play along with one of your song guides. You play every chord with your
    harmony hand; the guide shows what comes next and moves on when you play it."""
    key = "songs"

    def __init__(self, studio):
        self.studio = studio
        self.song = None
        self.position = -1            # index of the chord you are on (-1 = before the first)
        self.started = False          # False after a restart or section jump, until you play the next chord
        self.user_symbol = None
        self.sounding = []
        self.transpose = 0            # semitones away from the key the chords are written in
        self._upper = None            # upper notes of the last chord you played (voice leading)
        if studio.library.songs:
            self.select(studio.library.songs[0]["id"], announce=False)

    # ---------------------------------------------------------- song control
    def select(self, song_id, announce=True):
        song = self.studio.library.get(song_id)
        if song is None:
            return
        self.studio.audio.notes("chord", [])
        self.song = song
        self.sounding = []
        self.transpose = 0
        self.restart()
        if announce:
            self.studio.toast(song["title"])

    def reload(self):
        """The guides changed (saved or deleted): keep the open song up to date."""
        song = self.studio.library.get(self.song["id"]) if self.song else None
        if song is None:
            self.song = None
            self.studio.audio.notes("chord", [])
            self.sounding = []
            if self.studio.library.songs:
                self.select(self.studio.library.songs[0]["id"], announce=False)
        elif song is not self.song:
            self.song = song
            self.restart()

    # Transposing: every chord moves by the same number of semitones.
    @property
    def key_pc(self):
        return (self.song["key_pc"] + self.transpose) % 12

    def flats(self):
        return uses_flats(self.key_pc, self.song["mode"])

    def name(self, symbol):
        """How a chord is shown in the current key."""
        return transpose_symbol(symbol, self.transpose, self.flats()) if symbol else symbol

    def set_transpose(self, semitones):
        self.transpose = int(min(max(semitones, -6), 6))
        key = pc_name(self.key_pc, self.flats())
        self.studio.toast(f"Key: {key} {self.song['mode']}"
                          + (f" ({self.transpose:+d})" if self.transpose else " (as written)"))

    def jump(self, index):
        """Start from a section (index of its first chord)."""
        index = int(index) % len(self.song["chords"])
        self.position = index - 1 if index else -1
        self.started = False
        self.user_symbol = None
        self._skip_unplayable(None)

    def restart(self):
        self.position = -1
        self.started = False
        self.user_symbol = None
        self._upper = None
        if self.song:
            self._skip_unplayable(None)

    def chord_notes(self, symbol, previous=None):
        """MIDI notes for a song chord. With the default voicing, chords are voice-led:
        the bass plays the root, and the upper notes move as little as possible from
        `previous` (the upper notes of the chord before) - like a real accompanist.
        Returns (notes, upper notes)."""
        shaping = self.studio.shaping
        root_pc, intervals = parse_chord(symbol)
        root_pc = (root_pc + self.transpose) % 12
        bass = chord_bass(symbol)
        if bass is not None:
            bass = (bass + self.transpose) % 12
        if shaping.voicing == "root":
            return voice_lead(root_pc, intervals, previous, self.studio.octave, shaping.register, bass)
        if shaping.voicing == "seventh":
            intervals = add_seventh(root_pc, intervals, self.key_pc, self.song["mode"])
        voicing = "root" if shaping.voicing == "seventh" else shaping.voicing
        notes = voice_chord(root_pc, intervals, voicing, self.studio.octave, shaping.register, bass)
        return notes, notes[1:]

    def chord_key(self, symbol):
        """What identifies a chord for gestures: the exact symbol when every chord of
        the song has its own gesture, otherwise its family (F = Fmaj7 = F/A)."""
        return symbol if self.song["gesture_mode"] == "exact" else chord_family(symbol)

    def _mapped_families(self):
        return {self.chord_key(c) for c in self.song["gesture_chords"].values()}

    def same(self, a, b):
        """True if two chord symbols are played with the same gesture."""
        return bool(a and b) and self.chord_key(a) == self.chord_key(b)

    def _skip_unplayable(self, holding):
        """Step over chords you don't need to play again: repeats of the chord you are
        holding (Am Am, or Am Am/G in a family song) and chords that have no gesture."""
        chords = self.song["chords"]
        mapped = self._mapped_families()
        for _ in range(len(chords)):
            following = chords[(self.position + 1) % len(chords)]["chord"]
            if self.chord_key(following) in mapped and not self.same(following, holding):
                break
            self.position = (self.position + 1) % len(chords)

    # ------------------------------------------------------------- per frame
    def enter(self):
        self.studio.shaping.send(force=True)

    def leave(self):
        self.studio.audio.notes("chord", [])
        self.sounding = []

    def stop(self):
        self.sounding = []

    def update(self, harmony, sound):
        self.studio.shaping.update(sound)
        if not self.song:
            return
        gesture = harmony.gesture if harmony is not None else None
        if gesture == "unknown" and self.sounding:
            return
        symbol = self.song["gesture_chords"].get(gesture)
        if symbol and not harmony.changed and self.same(self.user_symbol, symbol):
            symbol = self.user_symbol      # same gesture still held: keep the chord that is sounding
        elif symbol and self.song["gesture_mode"] == "family":
            # Play the exact chord the song has here (e.g. Fmaj7 or C/E rather than plain F or C).
            chords = self.song["chords"]
            for index in ((self.position + 1) % len(chords), self.position):
                if index >= 0 and self.same(chords[index]["chord"], symbol):
                    symbol = chords[index]["chord"]
                    break
        notes, upper = self.chord_notes(symbol, self._upper) if symbol else ([], self._upper)
        if notes != self.sounding:
            self.studio.audio.notes("chord", notes, live=True)
            self.sounding = notes
            self._upper = upper
            if symbol and symbol != self.user_symbol:
                # Move on when you play the chord that comes next.
                chords = self.song["chords"]
                upcoming = (self.position + 1) % len(chords)
                if self.same(chords[upcoming]["chord"], symbol):
                    self.position = upcoming
                    self.started = True
                    self._skip_unplayable(symbol)
        self.user_symbol = symbol

    # -------------------------------------------------------------- display
    def snapshot(self, harmony, sound):
        if not self.song:
            return {"display": {"headline": "", "title": "No songs yet",
                                "caption": "Make a song guide in My Songs", "detail": "", "notes": [],
                                "active": False},
                    "scale": "major", "guides": {}, "song": None}
        song = self.song
        chords = song["chords"]
        n = len(chords)
        gesture_of = {}
        for g, c in song["gesture_chords"].items():
            gesture_of.setdefault(self.chord_key(c), g)
        current = chords[self.position]["chord"] if self.started else None
        next_index = (self.position + 1) % n
        nxt = chords[next_index]["chord"]
        focus = self.position if self.started else next_index
        part = max((p for p in song["parts"] if p["index"] <= focus), key=lambda p: p["index"])
        display = {"active": bool(self.sounding), "notes": []}
        # Kept short on purpose: the chord, and what comes next.
        shown = self.user_symbol if self.user_symbol and self.sounding else current
        if shown:
            display.update(headline=self.name(shown), title="", caption=f"Next: {self.name(nxt)}", detail="")
        else:
            display.update(headline="", title="", caption=f"First: {self.name(nxt)}", detail="")
        variants = song["variants"]
        rows = [{"gesture": g, "label": gesture_label(g), "value": self.name(c),
                 # Family songs: list the other versions this gesture also plays (e.g. "Fmaj7 F6").
                 "sub": " ".join(self.name(v) for v in variants.get(g, []) if v != c),
                 "active": self.same(c, self.user_symbol), "now": harmony is not None and harmony.gesture == g,
                 "next": self.same(c, nxt)}
                for g, c in song["gesture_chords"].items()]
        rows.append({"gesture": "fist", "label": "Fist", "value": "Stop chord", "sub": "",
                     "active": False, "now": harmony is not None and harmony.gesture == "fist"})
        unmapped = song["unmapped"]
        footer = f"No gesture left for {', '.join(self.name(c) for c in unmapped)} (skipped)" if unmapped else ""
        return {
            "display": display,
            "scale": song["mode"],
            "guides": {
                "harmony": {"title": "Song chords", "rows": rows, "footer": footer},
                "sound": {"title": "Sound", "rows": self.studio.shaping.guide_rows(sound.gesture if sound else None),
                          "footer": "Raise or lower your hand to change volume"},
            },
            "song": {
                "id": song["id"], "title": song["title"], "artist": song["artist"],
                "key": f"{pc_name(self.key_pc, self.flats())} {song['mode']}", "transpose": self.transpose,
                "position": self.position if self.started else -1, "next_index": next_index,
                "chords": [self.name(c["chord"]) for c in chords],
                "parts": song["parts"], "part": part["index"],
                "current": self.name(current), "next": self.name(nxt),
                "next_gesture": gesture_of.get(self.chord_key(nxt)), "user_chord": self.name(self.user_symbol),
            },
        }

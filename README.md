# Gesture Studio

Play music with your hands through your webcam: no musical knowledge needed.

* **Left hand picks the chord.** Show 1–5 fingers (or the rock / shaka sign), and you get one of the 7 chords that belong to the key, so everything you play sounds good together.
* **Right hand shapes the sound.** Raise it to get louder, lower it to fade, tilt it to brighten or darken. Finger shapes change the chord's colour (inversions, 7th chords, octave up and down).
* **Chords keep ringing while you hold the shape**, so you can sing over them.

It also has a **Free Play** mode for single notes, and **My Songs**: look up the chords of any song, type them in, and the app turns them into a play-along guide. Every chord gets its own hand sign, and the guide shows you which chord comes next. You play everything yourself: there is no backing track.

All sound is synthesized live. No samples, no internet, no paid services.

---

## 1. Quick start

### Windows

1. Double-click **`setup_windows.bat`** once. It installs everything into a private `.venv` folder, checks the camera and plays a test chord on each sound. The first time takes a few minutes.
2. Double-click **`run_windows.bat`** to play. Gesture Studio opens in its own window.

### macOS / Linux

```bash
cd "path/to/Gesture Studio"
chmod +x setup_mac_linux.sh run_mac_linux.sh
./setup_mac_linux.sh
./run_mac_linux.sh
```

To quit, close the Gesture Studio window (the app stops a few seconds later) or press `Ctrl+C` in the black console window.

> **Windows note:** keep the project **outside** `Documents`, `Desktop` and OneDrive folders. Windows' *Controlled folder access* blocks Python from writing there, so setup fails with `[WinError 2]`. `C:\Users\<you>\Projects\` works well.

---

## 2. Python version

| Python | Works? |
|---|---|
| 3.9, 3.10, **3.11 (recommended)**, 3.12 | Yes |
| 3.13 or newer | **No.** MediaPipe 0.10.21 has no packages for it |

Gesture Studio uses **MediaPipe 0.10.21**, the last version with the hand-tracking API used here. If you only have Python 3.13+, install Python 3.11 alongside it; the setup scripts pick 3.11 automatically (`py -0` lists your Pythons on Windows).

Tested on Windows 11 with Python 3.11.9, mediapipe 0.10.21, opencv-contrib-python 4.11, pygame 2.6.1, numpy 1.26.4 and scipy 1.17.

---

## 3. Manual setup (virtual environment)

A virtual environment (`.venv`) is a private folder with this project's packages. You create it once.

**Windows (PowerShell)**
```powershell
cd "$HOME\Projects\Gesture Studio"
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

**macOS / Linux**
```bash
cd "path/to/Gesture Studio"
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python run.py
```

| Command | What it does |
|---|---|
| `python run.py` | Start Gesture Studio (opens its window) |
| `python run.py --check` | Test packages, camera and sound (plays each preset), then exit |
| `python run.py --camera 1` | Use another webcam |
| `python run.py --no-window` | Don't open a window; open the printed address (`http://127.0.0.1:8765/`) in Chrome or Edge yourself |

---

## 4. Playing

Hold your hands up with **palms towards the camera**, about an arm's length away. Your left hand appears on the left of the picture (it works like a mirror). Coloured outlines show what is tracked: orange is the chord hand, blue is the sound hand.

### Gestures

| Shape | How | Left hand: chord | Right hand: sound |
|---|---|---|---|
| **1 finger** | Index up | Chord I (home) | Root position |
| **2 fingers** | Index + middle | Chord ii | Inversion 1 (smoother) |
| **3 fingers** | Index, middle, ring | Chord iii | Inversion 2 |
| **4 fingers** | Four up, thumb tucked in | Chord IV | 7th chord (jazzier) |
| **Open hand** | All five spread | Chord V | Wide, open voicing |
| **Rock** | Index + pinky | Chord vi | Octave up (again = back) |
| **Shaka** | Thumb + pinky | Chord vii | Octave down (again = back) |
| **Fist** | All curled | Stop the chord | No change (rest) |
| **Two fists** | Both hands | **Stop everything** | |

* **Volume:** right hand high = loud, low (near the bottom of the picture) = silent. If you take your right hand away, the volume stays where it was.
* **Brightness:** tilt your right hand outward to brighten, inward to darken (can be turned off in Settings).
* **Major / minor:** use the Major / Minor switch at the bottom. Optional: turn on *Tilt for minor* in Settings and lean your left hand outward to switch to minor.
* The guides on both sides show what every gesture does **right now**, with the actual chord names for your key.

### Modes (tabs at the top)

* **Synth:** two-handed chords as described above. Pick a key (C, D, E… any works) and a sound.
* **Free Play:** each gesture plays a single note of the scale. Your left hand plays low notes and your right hand plays notes an octave higher. Fist = silence. Change the key, scale and octave at the bottom.
* **My Songs:** your own play-along guides (see *Making a song guide* below). Open a song and play its chords with your left hand:
  * The left guide shows which hand sign plays each chord. The big display shows the chord you're on and the **next** chord, with its hand sign. Play the next chord and the guide moves on. Play another chord and it simply sounds, while the guide waits.
  * The chord row follows you through the song. When the same chord comes twice in a row, keep holding it and the guide moves on.
  * **Sections:** click **Verse**, **Chorus**… to start from there. The **↻** button goes back to the first chord.
  * **Key:** the **Key − / +** buttons transpose the whole song a semitone at a time (up to ±6), so it fits your voice. Chord names update everywhere. Your saved song isn't changed.
  * The **pencil** button edits the song.
  * Your right hand still shapes the sound (volume, brightness, inversions, 7ths, octave).
* **Settings:** camera, mirror, gesture sensitivity, left-handed mode, tilt options, guides, default sound/octave/scale/volume and the **Gesture check**.

### Sounds

| Sound | Character |
|---|---|
| Retro Synth | Pulse wave with gentle vibrato, slightly nostalgic |
| Warm Synth | Soft, rounded |
| Bright Synth | Clear and sharp (bright saw wave) |
| Soft Pad | Slow fade-in, long tail: made for singing over |
| Plucked Synth | Short and percussive, bright attack that mellows |
| **Instruments** | |
| Piano | Hammer attack that mellows and fades. Played by gesture, a held note is struck again at a steady pace, like pressing the key repeatedly (see below) |
| Electric Piano | Soft, bell-like tine sound |
| Acoustic Guitar | Plucked strings with a natural fade |
| Strings | A bowed string section that swells in |
| Organ | Sustained drawbar organ with a gentle rotary wobble |

All sounds are synthesized live (no recordings). Pick them from the **Sound** menu; the instruments are grouped under "Instruments".

**Piano repeat.** A piano can't hold a note forever, so when you play the Piano (Synth, Free Play or My Songs), holding a gesture re-strikes the same note or chord at a steady pace. Each strike is a fresh hammer attack with the piano's normal fade, every strike equally loud. Change the gesture to move to another note, or lower your hand (or make a fist) to stop. Set the pace under **Settings → Sound → Piano repeat** (0.15–1.5 s, default 0.5 s). The other sounds are not affected: they hold the note as long as you hold the gesture.

### Keyboard shortcuts

| Key | Action |
|---|---|
| **Space** | Mute / unmute (also the Mute button, top right) |
| **Esc** | Stop everything |
| **1 2 3 4** | Synth / Free Play / My Songs / Settings |
| **↑ ↓** | Volume |
| **[ ]** | Octave down / up |
| **R** | Back to the first chord of the song |

---

## 5. Testing each feature (checklist)

1. `python run.py --check` should show *Camera: OK* and *Audio: OK*, and you should hear a test chord on each sound.
2. Start the app. Both status dots (top right) are green. With no hands visible, the hint "Show your hands…" appears.
3. **Synth tab, left hand only:** show 1 → 2 → 3 → 4 fingers → open hand → rock → shaka. The big display shows C, Dm, Em, F, G, Am, Bdim (in C major), and the matching row lights up in the left guide. Hold a shape: the chord keeps ringing without restarting. Make a fist: it fades out.
4. **Add the right hand:** move it up and down and watch the *Volume* bar. Tilt it and watch *Brightness*. Show 2 fingers (Inversion 1), 4 fingers (7th chords: the left guide changes to Cmaj7, Dm7…), rock (octave up).
5. Switch **Major → Minor**: the chord names change (Cm, Ddim, Eb…).
6. Change the **Sound** menu while a chord rings: the sound changes immediately.
7. **Mute:** press Space; the button turns red. Press again. **Stop:** show two fists, or press Esc.
8. Switch **Expression → Manual**: the right hand no longer affects the sound; use the Voicing menu, Low/Mid/High and the Bright slider instead.
9. **Free Play:** each gesture plays one note; the display shows the note and octave ("E · Octave 4 · 3rd note of C major"). Use both hands.
10. **My Songs → New song:** type a title and `C G Am F` as the Verse. Under the chords you see which hand sign plays each one. Type a wrong chord (e.g. `Hm`): the error names it and Save is refused. Fix it and **Save**: the song opens.
11. **Play along:** the display says *First: C*. Play C (1 finger), then G (2), Am (3), F (4): the chord row follows you and loops. Click **Chorus**, try **Key +2**, press **↻**. Edit the song with the pencil button, then delete it with **Delete song**.
12. **Settings:** toggle *Left-handed* and check that the roles swap. Change *Default sound* and restart the app; it is remembered.

---

## 6. Customising

### Settings screen
Everything everyday is in **Settings** and saved automatically to `user_settings.json`. Delete that file to reset.

### Making a song guide (My Songs)
1. Look up the song's chords (any chord website or songbook).
2. In **My Songs**, click **New song**. Type the title (the artist is optional).
3. Type each section's chords in the order they are played, one section per row: e.g. Verse `Am F C G`, Chorus `F G Am Am/G`. Use **+ Add section** for more rows. Separate chords with spaces, commas or `|`.
4. Below the chords you see which hand sign plays each one. Press **Save**.

* **Chord names:** `C`, `F#m`, `Bb7`, `Dmaj7`, `Gm7`, `Asus4`, `Cadd9`, `Ab6`, `Bdim`, slash chords like `G/B`, … Chart spellings like `B♭`, `F♯m`, `Cmin7`, `GM7`, `E+`, `B°` and `Dø` work too. An unknown chord is named in red, and the song isn't saved until it's fixed.
* **Hand signs:** you have 7 (1–4 fingers, open hand, rock, shaka). A song with up to 7 different chords gives every chord its own sign, slash chords and sevenths included. With more, versions of the same chord share a sign (F, Fmaj7 and F/A are all played with the "F" sign, and the app plays the version the song has at that moment). If a song still has more than 7 different basic chords, the least used ones are skipped and the app tells you which.
* **Where it's saved:** your songs are saved to `my_songs.json` in the project folder. It stays on your computer and is not uploaded to GitHub (it's listed in `.gitignore`). The first time you start the app, an example song is shown; delete it if you like.
* **Musical key:** the key is taken from the first chord. It only decides whether transposed chords are written with sharps or flats.

### Advanced options (`config.json`)
Camera resolution, detection confidence, audio chunk size, the interface port and the **Free Play note mapping** (`free_play.gesture_notes`: a number 1–7 is a step of the chosen scale, a note like `"C4"` is fixed). Restart the app after editing.

### Designing sounds (`gesture_synth/presets.py`)
Each preset is a short list of numbers (harmonics, detune, envelope, filter). Change them to create your own sounds.

---

## 7. Troubleshooting

**A gesture isn't recognised or flickers**
* Open **Settings → Gesture check**: it shows which fingers are detected for each hand, live.
* *4 fingers* read as *Open hand*: move **Thumb detection** right, or tuck your thumb into your palm. The opposite: move it left and spread your thumb wide.
* Flickering: move **Gesture sensitivity** towards *Steady*. Use even light from the front (not a bright window behind you) and keep your whole hand in the picture.
* Hands swapped: turn **Mirror preview** on, or enable **Left-handed** if you prefer the other way round.
* Tilt controls not behaving: turn off *Tilt for brightness* / *Tilt for minor*, or use **Expression → Manual**.

**"No camera" (red dot) or "Camera not available"**
* Close other apps using the camera (Zoom, Teams, Discord, browser tabs), check the laptop's camera switch or shutter, then press **Try again**.
* Windows: *Settings → Privacy & security → Camera* → allow desktop apps. macOS: *System Settings → Privacy & Security → Camera* → allow Terminal.
* Another webcam: **Settings → Camera → Find cameras**, or `python run.py --camera 1`.

**"No sound" (red dot) or no audio**
* Check speakers/headphones and the system volume, then **Settings → Restart sound**.
* Another app may be using the audio device exclusively: close it and restart sound.
* Crackles on a slow computer: set `"chunk_size": 2048` in `config.json`.
* The app keeps working without sound (visuals only).

**The window doesn't open / shows nothing**
* Open `http://127.0.0.1:8765/` in Chrome or Edge yourself. If port 8765 is busy, the console prints the address actually used.
* "Gesture Studio has stopped" means the Python program was closed. Start it again.

**`setup_windows.bat` fails with `[WinError 2] ... .venv`**
* Windows *Controlled folder access* is blocking the folder. Move the project out of Documents/Desktop/OneDrive (see Quick start), or allow Python in *Windows Security → Ransomware protection*.

**`ModuleNotFoundError` / "Some required packages are missing"**
* Run the setup script again, or `.venv\Scripts\python.exe -m pip install -r requirements.txt`.

**pip says "No matching distribution found for mediapipe"**
* Your Python is too new (3.13+) or 32-bit. Install 64-bit Python 3.11, delete `.venv` and run setup again.

---

## 8. How it works

```
Gesture Studio/
├── run.py                 start here
├── config.json            advanced options
├── my_songs.json          your song guides (created when you save one)
├── user_settings.json     your preferences (created automatically)
├── web/                   the interface: index.html, styles.css, app.js (no frameworks)
└── gesture_synth/
    ├── app.py         main loop: hands → gestures → current mode → sound; applies clicks
    ├── vision.py      background thread: camera frames + hand tracking + video picture
    ├── camera.py      webcam opening, fallbacks, reconnect, camera search
    ├── gestures.py    MediaPipe (2 hands) → fingers up/down → gesture, tilt, height, left/right
    ├── triggers.py    steadiness filter + "fire once per gesture change"
    ├── modes.py       Synth, Free Play and My Songs behaviour; what the guides show
    ├── music.py       keys, the 7 chords of a key, inversions, 7ths, chord names
    ├── songs.py       your song guides: reads chords, gives them hand signs, saves my_songs.json
    ├── engine.py      the real-time synthesizer (runs in its own process)
    ├── presets.py     the ten sounds, described as data
    ├── audio.py       sends commands to the synth process
    ├── server.py      tiny local web server for the interface (127.0.0.1 only)
    ├── settings.py    saves your preferences
    ├── config.py      loads config.json
    ├── deps.py        friendly checks for Python version / missing packages
    └── diagnostics.py run.py --check
```

* **Responsive audio:** the synthesizer runs in a separate process, so camera processing can never make the sound stutter. It renders about 23 ms of audio at a time, holding notes for as long as you hold a gesture. When you change chords, notes the two chords share keep ringing while the others fade, so changes are smooth and click-free.
* **Interface:** Python serves a local web page (HTML/CSS/JavaScript) in an app-style Edge/Chrome window. It receives live state about 30 times a second and sends your clicks back. Nothing leaves your computer.

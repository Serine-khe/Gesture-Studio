"""Hand tracking (MediaPipe) and gesture recognition for BOTH hands.

For each visible hand we work out:
  * which fingers are up (rotation-tolerant: a finger is "up" when its tip is
    clearly farther from the wrist than its middle joint AND it is fairly straight)
  * a gesture name (fist, one, two, three, four, palm, rock, shaka)
  * tilt: how far the hand leans sideways, in degrees (0 = fingers pointing up)
  * height: how high the hand is in the picture (0 = bottom, 1 = top)
  * whether it is the user's LEFT or RIGHT hand
"""

import math
from dataclasses import dataclass, field

import cv2
import mediapipe as mp

_mp_hands = mp.solutions.hands

FINGERS = ("thumb", "index", "middle", "ring", "pinky")

# gesture -> (short label, how to make it, finger pattern thumb..pinky; 2 = "either")
GESTURES = {
    "fist": ("Fist", "All fingers curled", (2, 0, 0, 0, 0)),
    "one": ("1 finger", "Index finger up", (2, 1, 0, 0, 0)),
    "two": ("2 fingers", "Index + middle (peace sign)", (2, 1, 1, 0, 0)),
    "three": ("3 fingers", "Index, middle and ring up", (2, 1, 1, 1, 0)),
    "four": ("4 fingers", "Four fingers up, thumb tucked in", (0, 1, 1, 1, 1)),
    "palm": ("Open hand", "All five fingers spread", (1, 1, 1, 1, 1)),
    "rock": ("Rock", "Index + pinky up", (2, 1, 0, 0, 1)),
    "shaka": ("Shaka", "Thumb + pinky out (call me)", (1, 0, 0, 0, 1)),
}

_FINGER_JOINTS = {  # mcp, pip, tip landmark indices
    "index": (5, 6, 8),
    "middle": (9, 10, 12),
    "ring": (13, 14, 16),
    "pinky": (17, 18, 20),
}


@dataclass
class HandReading:
    points: list                  # 21 (x, y) positions, normalised 0..1 in the (mirrored) frame
    side: str                     # "left" or "right" = the user's real hand
    score: float = 0.0
    fingers: dict = field(default_factory=dict)
    gesture: str = "unknown"
    tilt: float = 0.0             # degrees, + = leaning towards the screen's right
    height: float = 0.5           # 0 = bottom of picture, 1 = top

    def as_dict(self):
        return {
            "side": self.side,
            "gesture": self.gesture,
            "fingers": self.fingers,
            "tilt": round(self.tilt, 1),
            "height": round(self.height, 3),
            "points": [[round(x, 4), round(y, 4)] for x, y in self.points],
        }


class HandTracker:
    def __init__(self, min_detection_confidence=0.6, min_tracking_confidence=0.5,
                 model_complexity=0, thumb_sensitivity=0.6):
        self.thumb_sensitivity = thumb_sensitivity
        self._hands = _mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            model_complexity=model_complexity,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )

    def process(self, frame_bgr, mirrored=True):
        """Return a list of HandReading (0, 1 or 2 hands)."""
        height, width = frame_bgr.shape[:2]
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        result = self._hands.process(rgb)
        if not result.multi_hand_landmarks:
            return []
        readings = []
        for landmarks, handedness in zip(result.multi_hand_landmarks, result.multi_handedness):
            label = handedness.classification[0].label.lower()   # "left" / "right"
            score = handedness.classification[0].score
            # MediaPipe assumes a mirrored (selfie) picture. Without mirroring, swap.
            side = label if mirrored else ("left" if label == "right" else "right")
            points = [(lm.x, lm.y) for lm in landmarks.landmark]
            pixels = [(x * width, y * height) for x, y in points]
            fingers = finger_states(pixels, self.thumb_sensitivity)
            readings.append(HandReading(points, side, score, fingers, classify(fingers),
                                        hand_tilt(pixels), 1.0 - palm_center(points)[1]))
        return assign_sides(readings, mirrored)

    def close(self):
        self._hands.close()


def assign_sides(readings, mirrored=True):
    """If both hands got the same label (it happens), decide by screen position.
    In a mirrored picture the user's left hand appears on the left side."""
    if len(readings) == 2 and readings[0].side == readings[1].side:
        a, b = sorted(readings, key=lambda r: palm_center(r.points)[0])
        a.side, b.side = ("left", "right") if mirrored else ("right", "left")
    return readings


def palm_center(points):
    ids = (0, 5, 9, 13, 17)
    return (sum(points[i][0] for i in ids) / 5.0, sum(points[i][1] for i in ids) / 5.0)


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _straightness(a, b, c):
    """Cosine of the bend at b: 1.0 = perfectly straight, <0 = folded back."""
    v1 = (b[0] - a[0], b[1] - a[1])
    v2 = (c[0] - b[0], c[1] - b[1])
    norm = math.hypot(*v1) * math.hypot(*v2)
    return (v1[0] * v2[0] + v1[1] * v2[1]) / norm if norm else 0.0


def finger_states(points, thumb_sensitivity=0.6):
    """Which fingers are up. `points` are pixel positions (keeps proportions right)."""
    wrist = points[0]
    palm = max(_dist(points[0], points[9]), 1e-6)
    states = {}
    for name, (mcp, pip, tip) in _FINGER_JOINTS.items():
        far = _dist(wrist, points[tip]) > _dist(wrist, points[pip]) * 1.1
        straight = _straightness(points[mcp], points[pip], points[tip]) > 0.5
        states[name] = far and straight
    # The thumb is "out" when its tip is far from the base of the index finger.
    states["thumb"] = _dist(points[4], points[5]) / palm > thumb_sensitivity
    return {f: bool(states[f]) for f in FINGERS}


def classify(fingers):
    key = tuple(int(fingers[f]) for f in ("index", "middle", "ring", "pinky"))
    thumb = fingers["thumb"]
    if key == (0, 0, 0, 0):
        return "fist"
    if key == (1, 0, 0, 0):
        return "one"
    if key == (1, 1, 0, 0):
        return "two"
    if key == (1, 1, 1, 0):
        return "three"
    if key == (1, 1, 1, 1):
        return "palm" if thumb else "four"
    if key == (1, 0, 0, 1):
        return "rock"
    if key == (0, 0, 0, 1) and thumb:
        return "shaka"
    return "unknown"


def hand_tilt(pixels):
    """Sideways lean in degrees, from the wrist to the base of the middle finger.
    0 = upright, positive = leaning towards the right side of the screen."""
    dx = pixels[9][0] - pixels[0][0]
    dy = pixels[0][1] - pixels[9][1]   # image y grows downwards
    return math.degrees(math.atan2(dx, dy))


def gesture_label(key):
    return GESTURES[key][0] if key in GESTURES else ("Not sure" if key == "unknown" else "-")


def gesture_catalog():
    """For the interface: label, how-to text and finger pattern of every gesture."""
    return {key: {"label": label, "how": how, "pattern": list(pattern)}
            for key, (label, how, pattern) in GESTURES.items()}

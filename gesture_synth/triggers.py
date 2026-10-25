"""Turns a noisy per-frame gesture stream into clean, well-timed triggers."""


class GestureStabilizer:
    """Only reports a gesture after it has been seen for `stable_frames` frames
    in a row, and only reports "no hand" after `lost_frames` empty frames.
    This removes flicker while you move between gestures."""

    def __init__(self, stable_frames=4, lost_frames=6):
        self.stable_frames = stable_frames
        self.lost_frames = lost_frames
        self.current = None
        self._candidate = None
        self._count = 0
        self._missing = 0

    def update(self, raw_gesture):
        if raw_gesture is None:
            self._missing += 1
            if self._missing >= self.lost_frames:
                self.current = None
                self._candidate = None
                self._count = 0
            return self.current
        self._missing = 0
        if raw_gesture == self._candidate:
            self._count += 1
        else:
            self._candidate = raw_gesture
            self._count = 1
        if self._count >= self.stable_frames:
            self.current = raw_gesture
        return self.current


class TriggerGate:
    """Decides when a stable gesture should actually make a sound.

    * A sound fires when the gesture CHANGES (fist -> one finger).
    * Never faster than `cooldown` seconds apart.
    * Holding a gesture does nothing more, unless `retrigger_while_held`
      is on, in which case it repeats every `retrigger_interval` seconds.
    * Removing your hand from view resets, so showing the same gesture
      again plays it again. "unknown" poses are ignored.
    """

    def __init__(self, cooldown=0.25, retrigger_while_held=False, retrigger_interval=1.0):
        self.cooldown = cooldown
        self.retrigger_while_held = retrigger_while_held
        self.retrigger_interval = retrigger_interval
        self.last_gesture = None
        self.last_time = float("-inf")

    def reset(self):
        self.last_gesture = None

    def check(self, gesture, now, ignore_cooldown=False):
        if gesture is None:
            self.last_gesture = None
            return False
        if gesture == "unknown":
            return False
        if gesture != self.last_gesture:
            if ignore_cooldown or now - self.last_time >= self.cooldown:
                self.last_gesture = gesture
                self.last_time = now
                return True
            return False  # still cooling down; we'll fire on a later frame
        interval = max(self.retrigger_interval, self.cooldown)
        if self.retrigger_while_held and now - self.last_time >= interval:
            self.last_time = now
            return True
        return False

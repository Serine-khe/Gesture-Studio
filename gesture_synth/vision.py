"""Background worker: grabs camera frames, runs hand tracking and prepares
the JPEG picture shown in the interface.

Running this on its own thread means the rest of the app (sound, interface)
never waits for the camera or for MediaPipe.
"""

import threading
import time

import cv2


class VisionWorker:
    def __init__(self, camera, tracker, mirror=True, jpeg_quality=78):
        self.camera = camera
        self.tracker = tracker
        self.mirror = mirror
        self.jpeg_quality = jpeg_quality
        self.want_jpeg = True
        self.error = None
        self.fps = 0.0
        self._lock = threading.Condition()
        self._tracker_lock = threading.Lock()
        self._result = (False, None, [])   # (camera ok, frame, [HandReading])
        self._result_id = 0
        self._seen_id = 0
        self._jpeg = None
        self._jpeg_id = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="vision", daemon=True)

    def start(self):
        self._thread.start()

    def set_mirror(self, mirror):
        with self._tracker_lock:
            self.mirror = mirror

    def set_camera(self, camera):
        """Swap to another camera; returns the old one (caller releases it)."""
        with self._tracker_lock:
            old, self.camera = self.camera, camera
        return old

    def _run(self):
        last = time.perf_counter()
        while not self._stop.is_set():
            with self._tracker_lock:
                camera, tracker, mirror = self.camera, self.tracker, self.mirror
            ok, frame = camera.read() if camera is not None else (False, None)
            readings = []
            jpeg = None
            if ok:
                if mirror:
                    frame = cv2.flip(frame, 1)
                try:
                    readings = tracker.process(frame, mirrored=mirror)
                    self.error = None
                except Exception as exc:  # keep the app alive if one frame fails
                    self.error = str(exc)
                if self.want_jpeg:
                    good, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
                    jpeg = buf.tobytes() if good else None
                now = time.perf_counter()
                self.fps = 0.9 * self.fps + 0.1 / max(now - last, 1e-6)
                last = now
            else:
                time.sleep(0.05)
            with self._lock:
                self._result = (ok, frame, readings)
                self._result_id += 1
                if jpeg is not None:
                    self._jpeg = jpeg
                    self._jpeg_id += 1
                self._lock.notify_all()

    def latest(self, timeout=0.1):
        """Return (fresh, ok, frame, readings). `fresh` is False if nothing new arrived."""
        with self._lock:
            if self._result_id == self._seen_id:
                self._lock.wait(timeout)
            fresh = self._result_id != self._seen_id
            self._seen_id = self._result_id
            return (fresh,) + self._result

    def wait_jpeg(self, last_id, timeout=1.0):
        """Used by the video stream: wait for a picture newer than `last_id`."""
        with self._lock:
            if self._jpeg_id == last_id:
                self._lock.wait(timeout)
            return self._jpeg_id, self._jpeg

    def stop(self):
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=1.5)

"""Webcam access with automatic fallbacks and reconnection.

Frames are captured on a background thread, so hand tracking and drawing
run while the camera is busy delivering the next frame (higher FPS).
"""

import sys
import threading
import time

import cv2


def _backends():
    if sys.platform.startswith("win"):
        return [("DirectShow", cv2.CAP_DSHOW), ("Media Foundation", cv2.CAP_MSMF), ("default", cv2.CAP_ANY)]
    if sys.platform == "darwin":
        return [("AVFoundation", cv2.CAP_AVFOUNDATION), ("default", cv2.CAP_ANY)]
    return [("V4L2", cv2.CAP_V4L2), ("default", cv2.CAP_ANY)]


CAMERA_HELP = [
    "Things to check:",
    "  - Is a webcam connected and switched on? Some laptops have a privacy slider or an F-key for it.",
    "  - Close other apps that use the camera (Zoom, Teams, Discord, OBS, browser tabs).",
    "  - Windows: Settings > Privacy & security > Camera > allow desktop apps to use the camera.",
    "  - macOS: System Settings > Privacy & Security > Camera > allow Terminal (or your editor).",
    "  - Using an external/second camera? Pick it in Settings, or start with:  python run.py --camera 1",
]


def scan_cameras(in_use=None, max_index=5):
    """Return the camera numbers that deliver a picture. The camera that is
    already open (`in_use`) is listed without being re-opened."""
    found = []
    for index in range(max_index):
        if index == in_use:
            found.append(index)
            continue
        backend = _backends()[0][1]
        cap = cv2.VideoCapture(index, backend)
        try:
            if cap.isOpened():
                ok, _ = cap.read()
                if ok:
                    found.append(index)
        finally:
            cap.release()
    return found


class Camera:
    def __init__(self, index=0, width=640, height=480):
        self.index = index
        self.width = width
        self.height = height
        self.active_index = None
        self.backend_name = None
        self.error = None
        self._cap = None
        self._lock = threading.Lock()
        self._new_frame = threading.Condition(self._lock)
        self._frame = None
        self._frame_id = 0
        self._read_id = 0
        self._last_frame_time = 0.0
        self._stop = threading.Event()
        self._thread = None
        self._last_attempt = 0.0

    # ------------------------------------------------------------- opening
    def open(self, search_other_indexes=True):
        indexes = [self.index]
        if search_other_indexes:
            indexes += [i for i in range(4) if i != self.index]
        for index in indexes:
            for name, backend in _backends():
                cap = self._try_open(index, backend)
                if cap is not None:
                    self._cap, self.active_index, self.backend_name = cap, index, name
                    if index != self.index:
                        print(f"[camera] Camera {self.index} was not available; using camera {index}.")
                    print(f"[camera] Using camera {index} via {name}.")
                    self._start_thread()
                    return True
        self.error = f"Could not open a webcam (tried camera numbers {', '.join(map(str, indexes))})."
        return False

    def _try_open(self, index, backend):
        try:
            cap = cv2.VideoCapture(index, backend)
        except Exception:
            return None
        if not cap.isOpened():
            cap.release()
            return None
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # keep latency low
        for _ in range(15):  # some cameras need a few frames to warm up
            ok, frame = cap.read()
            if ok and frame is not None:
                with self._lock:
                    self._frame, self._last_frame_time = frame, time.perf_counter()
                    self._frame_id += 1
                return cap
            time.sleep(0.05)
        cap.release()
        return None

    # ------------------------------------------------------ capture thread
    def _start_thread(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._capture_loop, name="camera", daemon=True)
        self._thread.start()

    def _capture_loop(self):
        cap = self._cap
        failures = 0
        while not self._stop.is_set():
            ok, frame = cap.read()
            if ok and frame is not None:
                failures = 0
                with self._lock:
                    self._frame, self._last_frame_time = frame, time.perf_counter()
                    self._frame_id += 1
                    self._new_frame.notify_all()
            else:
                failures += 1
                if failures > 30:
                    print("[camera] Lost the camera feed; trying to reconnect...")
                    break
                time.sleep(0.02)
        cap.release()

    # ------------------------------------------------------------- reading
    def read(self, timeout=0.1):
        """Return (ok, newest frame). Waits briefly for a frame we haven't seen yet."""
        if self._thread is None or not self._thread.is_alive():
            self._reconnect()
            return False, None
        with self._lock:
            if self._frame_id == self._read_id:
                self._new_frame.wait(timeout)
            if self._frame is None or time.perf_counter() - self._last_frame_time > 1.5:
                return False, None
            self._read_id = self._frame_id
            return True, self._frame

    def _reconnect(self):
        now = time.perf_counter()
        if now - self._last_attempt > 2.0:
            self._last_attempt = now
            if self.active_index is not None:
                self.index = self.active_index
            if self.open(search_other_indexes=False):
                print("[camera] Reconnected.")
        time.sleep(0.03)

    def release(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

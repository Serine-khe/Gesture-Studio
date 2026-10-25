"""Tiny local web server for the interface (Python standard library only).

Only reachable from this computer (127.0.0.1). It serves:
  /               the interface (web/index.html, styles, script)
  /video.mjpg     the live camera picture (a stream of JPEG images)
  /events         live app state, ~30 times a second (Server-Sent Events)
  /api/init       lists for menus (presets, gestures, your songs...)
  /api/songs      your song guides (reloaded after you save one)
  /api/action     button clicks and slider moves from the interface
  /api/song_check checks a song guide while you type it (nothing is saved)
"""

import json
import mimetypes
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

_DISCONNECTS = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError, OSError)


class StudioServer:
    def __init__(self, studio, web_dir, port):
        self.studio = studio
        self.web_dir = os.path.realpath(web_dir)
        handler = type("Handler", (_Handler,), {"studio": studio, "web_dir": self.web_dir})
        last_error = None
        for candidate in range(port, port + 20):  # if the port is busy, try the next ones
            try:
                self.httpd = _QuietServer(("127.0.0.1", candidate), handler)
                break
            except OSError as exc:
                last_error = exc
        else:
            raise OSError(f"no free port between {port} and {port + 19}: {last_error}")
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}/"
        self._thread = threading.Thread(target=self.httpd.serve_forever, name="web", daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class _QuietServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        """A window closing mid-request is normal - don't print a scary traceback for it."""
        import sys
        if not isinstance(sys.exc_info()[1], _DISCONNECTS):
            super().handle_error(request, client_address)


class _Handler(BaseHTTPRequestHandler):
    studio = None
    web_dir = ""
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # keep the console quiet
        pass

    def _host_ok(self):
        """Reject requests that don't come from our own page (DNS-rebinding protection)."""
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    # ------------------------------------------------------------------ GET
    def do_GET(self):
        if not self._host_ok():
            return self.send_error(403)
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._file("index.html")
        if path.startswith("/static/"):
            return self._file(path[len("/static/"):])
        if path == "/api/init":
            return self._json(self.studio.init_payload())
        if path == "/api/songs":
            return self._json(self.studio.songs_payload())
        if path == "/events":
            return self._events()
        if path == "/video.mjpg":
            return self._video()
        self.send_error(404)

    # ----------------------------------------------------------------- POST
    def do_POST(self):
        if not self._host_ok() or self.headers.get("X-Gesture-Studio") != "1":
            return self.send_error(403)  # custom header = only our own page can send actions
        path = urlparse(self.path).path
        if path not in ("/api/action", "/api/song_check"):
            return self.send_error(404)
        try:
            length = min(int(self.headers.get("Content-Length", 0)), 65536)
            action = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(action, dict):
                raise ValueError
        except (ValueError, json.JSONDecodeError):
            return self.send_error(400)
        if path == "/api/song_check":
            return self._json(self.studio.check_song(action))
        self.studio.enqueue(action)
        self._json({"ok": True})

    # -------------------------------------------------------------- helpers
    def _json(self, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, name):
        path = os.path.realpath(os.path.join(self.web_dir, name))
        if not path.startswith(self.web_dir + os.sep) or not os.path.isfile(path):
            return self.send_error(404)
        with open(path, "rb") as handle:
            body = handle.read()
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
            ctype += "; charset=utf-8"
        if path.endswith(".js"):
            ctype = "text/javascript; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _events(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        self.studio.client_connected()
        last = -1
        try:
            while self.studio.running:
                state_id, data = self.studio.wait_state(last, 1.0)
                if state_id != last:
                    self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
                    last = state_id
                else:
                    self.wfile.write(b": ping\n\n")
                self.wfile.flush()
        except _DISCONNECTS:
            pass
        finally:
            self.studio.client_disconnected()
            self.close_connection = True

    def _video(self):
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        last = 0
        try:
            while self.studio.running:
                vision = self.studio.vision
                if vision is None:
                    time.sleep(0.2)
                    continue
                frame_id, jpeg = vision.wait_jpeg(last, 1.0)
                if jpeg is None or frame_id == last:
                    continue
                last = frame_id
                self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                 + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n")
                self.wfile.flush()
        except _DISCONNECTS:
            pass
        self.close_connection = True

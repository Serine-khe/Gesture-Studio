"""`python run.py --check`: tests Python, packages, camera and speakers."""

import platform
import sys
import time


def run_checks(camera_index=0):
    print("=" * 60)
    print("Gesture Studio - setup check")
    print("=" * 60)
    print(f"Python      : {platform.python_version()} ({sys.executable})")
    print(f"System      : {platform.system()} {platform.release()}")

    import cv2
    import mediapipe
    import numpy
    import pygame
    import scipy
    print(f"numpy       : {numpy.__version__}")
    print(f"scipy       : {scipy.__version__}")
    print(f"opencv      : {cv2.__version__}")
    print(f"mediapipe   : {mediapipe.__version__}")
    print(f"pygame      : {pygame.version.ver}")

    all_ok = True

    from .gestures import HandTracker
    try:
        HandTracker().close()
        print("Hand model  : OK (tracks up to 2 hands)")
    except Exception as exc:
        all_ok = False
        print(f"Hand model  : FAILED - {exc}")

    from .camera import CAMERA_HELP, Camera
    camera = Camera(camera_index)
    if camera.open():
        ok, frame = camera.read()
        size = f"{frame.shape[1]}x{frame.shape[0]}" if ok else "no frame"
        print(f"Camera      : OK (camera {camera.active_index} via {camera.backend_name}, {size})")
        camera.release()
    else:
        all_ok = False
        print(f"Camera      : FAILED - {camera.error}")
        for line in CAMERA_HELP:
            print("              " + line)

    from .audio import AudioEngine
    from .music import diatonic_chord, voice_chord
    audio = AudioEngine()
    if audio.wait_ready():
        print("Audio       : OK - playing a test chord on each sound...")
        notes = voice_chord(*diatonic_chord(1, "major", 1), "root", 3)
        for preset in ("warm", "retro", "bright", "pad", "pluck"):
            audio.preset(preset)
            audio.notes("chord", notes)
            time.sleep(0.8)
        audio.notes("chord", [])
        time.sleep(0.8)
    else:
        all_ok = False
        print(f"Audio       : FAILED - {audio.error}")
        print("              Check that speakers/headphones are connected and not used exclusively")
        print("              by another app. Gesture Studio still runs without sound (visuals only).")
    audio.close()

    print("-" * 60)
    print("All good! Start Gesture Studio with:  python run.py" if all_ok
          else "Some checks failed - see README.md > Troubleshooting.")
    return 0 if all_ok else 1

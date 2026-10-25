"""Start Gesture Studio.

    python run.py              start the app (opens its window)
    python run.py --check      test camera, speakers and packages
    python run.py --camera 1   use a different webcam
    python run.py --no-window  don't open a window; visit the printed address yourself
"""

import os
import sys

# Quieter startup: hide pygame's banner and MediaPipe/TensorFlow info logs.
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("GLOG_minloglevel", "2")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")


def main():
    from gesture_synth.deps import check_dependencies
    if not check_dependencies():
        return 1
    from gesture_synth.app import main as app_main
    return app_main(sys.argv[1:])


if __name__ == "__main__":  # required: the sound engine starts in a separate process
    sys.exit(main())

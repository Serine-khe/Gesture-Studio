"""Allows `python -m gesture_synth`."""

import os
import sys

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("GLOG_minloglevel", "2")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

if __name__ == "__main__":  # required: the sound engine starts in a separate process
    from gesture_synth.deps import check_dependencies

    if not check_dependencies():
        sys.exit(1)

    from gesture_synth.app import main

    sys.exit(main())

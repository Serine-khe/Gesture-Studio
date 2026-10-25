"""Friendly checks for the Python version and required packages.

Only standard-library imports at module level, so this works even when the
packages are missing.
"""

import importlib
import sys

REQUIRED = [
    ("numpy", "numpy"),
    ("scipy", "scipy"),
    ("cv2", "opencv-contrib-python"),
    ("pygame", "pygame"),
    ("mediapipe", "mediapipe"),
]
SUPPORTED = ((3, 9), (3, 12))
RECOMMENDED = "3.11"


def _version(v):
    return f"{v[0]}.{v[1]}"


def check_dependencies():
    """Print helpful instructions and return False if something is missing."""
    major_minor = sys.version_info[:2]
    if major_minor < SUPPORTED[0]:
        print(f"\nPython {_version(major_minor)} is too old for this app.")
        print(f"Please install Python {RECOMMENDED} from https://www.python.org/downloads/ "
              f"and follow README.md > Setup.\n")
        return False

    missing = []
    for module, package in REQUIRED:
        try:
            importlib.import_module(module)
        except Exception as exc:  # ImportError, or a broken binary install
            missing.append((package, exc))

    if missing:
        print("\nSome required packages are missing or broken:")
        for package, exc in missing:
            print(f"  - {package}: {exc}")
        if major_minor > SUPPORTED[1] and any(p == "mediapipe" for p, _ in missing):
            print(f"\nYou are running Python {_version(major_minor)}. The MediaPipe version this app "
                  f"uses (0.10.21) only supports Python {_version(SUPPORTED[0])} to "
                  f"{_version(SUPPORTED[1])}, so pip cannot install it here.")
            print(f"Fix: install Python {RECOMMENDED} alongside your current Python, then re-create the "
                  f"virtual environment with it (see README.md > Python version).")
        else:
            print("\nFix: activate the virtual environment and install the requirements:")
            if sys.platform.startswith("win"):
                print("    .venv\\Scripts\\activate")
            else:
                print("    source .venv/bin/activate")
            print("    python -m pip install -r requirements.txt")
            print("(Or just run the setup script: setup_windows.bat / ./setup_mac_linux.sh)")
        print()
        return False

    import mediapipe
    if not hasattr(mediapipe, "solutions"):
        version = getattr(mediapipe, "__version__", "?")
        print(f"\nYour MediaPipe version ({version}) no longer includes the hand-tracking API this app "
              f"uses.\nFix:  python -m pip install mediapipe==0.10.21\n")
        return False
    return True

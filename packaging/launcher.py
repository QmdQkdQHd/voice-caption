"""Frozen entry point: dispatch spawned workers before importing Qt."""
import multiprocessing
import os
import sys

if __name__ == "__main__":
    # Windowed PyInstaller applications have no stdout/stderr.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    multiprocessing.freeze_support()
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test-report":
        from voice_caption.diagnostics import run
        raise SystemExit(run(sys.argv[2]))
    from voice_caption.app import main
    raise SystemExit(main())

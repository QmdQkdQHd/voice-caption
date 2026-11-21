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
    if sys.argv[1:2] == ["--integration-test-report"]:
        import argparse
        from voice_caption.integration_check import run
        parser = argparse.ArgumentParser()
        parser.add_argument("--integration-test-report", required=True)
        parser.add_argument("--audio-fixture", required=True)
        args = parser.parse_args()
        raise SystemExit(run(args.integration_test_report, args.audio_fixture))
    from voice_caption.app import main
    raise SystemExit(main())

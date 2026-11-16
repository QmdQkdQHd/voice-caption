"""Spawn supervision kept independent of Qt for real process lifecycle tests."""
import multiprocessing
from queue import Empty
import time


def supervise(target, arguments, requested_stop, dispatch, grace=1.5):
    context = multiprocessing.get_context("spawn")
    stop = context.Event()
    events = context.Queue(maxsize=64)
    process = context.Process(target=target, args=(*arguments, stop, events), daemon=True)
    started = False
    try:
        if requested_stop.is_set():
            return
        process.start()
        started = True
        deadline = None
        while process.is_alive():
            if requested_stop.is_set():
                stop.set()
                if deadline is None:
                    deadline = time.monotonic() + grace
                if time.monotonic() >= deadline:
                    break
            try:
                kind, values = events.get(timeout=0.05)
            except Empty:
                continue
            if not requested_stop.is_set():
                dispatch(kind, values)
        if not requested_stop.is_set():
            # The child normally flushes errors before exiting.
            while True:
                try:
                    kind, values = events.get(timeout=0.05)
                    dispatch(kind, values)
                except Empty:
                    break
            if process.exitcode not in (0, None):
                dispatch("error", (f"음성 처리 프로세스가 종료되었습니다 (코드 {process.exitcode}).",))
    finally:
        stop.set()
        if started:
            if process.is_alive():
                process.terminate()
            process.join(timeout=1)
            if process.is_alive():
                process.kill()
                process.join(timeout=1)
            if process.is_alive():
                raise RuntimeError("음성 처리 프로세스를 종료하지 못했습니다.")
            process.close()
        events.close()
        events.cancel_join_thread()

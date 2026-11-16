from queue import Queue
import multiprocessing
import os
import threading
import time
import unittest

from voice_caption.core import CaptionHistory, Settings, UtteranceBuffer
from voice_caption.pipeline import translate_pending
from voice_caption.runtime import supervise


def stuck_worker(stop, events):
    events.put(("status", ("ready",)))
    while True:
        time.sleep(1)


def final_error_worker(stop, events):
    events.put(("error", ("device disconnected",)))


def crashed_worker(stop, events):
    os._exit(7)


class PipelineTests(unittest.TestCase):
    def test_short_utterance_ends_after_silence_with_preroll(self):
        buffer = UtteranceBuffer(max_frames=30, silence_frames=3)
        for value in range(5):
            self.assertIsNone(buffer.feed(value, False))
        self.assertIsNone(buffer.feed(5, True))
        self.assertIsNone(buffer.feed(6, True))
        self.assertIsNone(buffer.feed(7, False))
        self.assertIsNone(buffer.feed(8, False))
        self.assertEqual(buffer.feed(9, False), list(range(3, 10)))
        self.assertIsNone(buffer.feed(10, False))

    def test_continuous_audio_is_bounded_and_silence_emits_nothing(self):
        buffer = UtteranceBuffer(max_frames=3)
        self.assertIsNone(buffer.feed(0, True))
        self.assertIsNone(buffer.feed(1, True))
        self.assertEqual(buffer.feed(2, True), [0, 1, 2])
        for value in range(100):
            self.assertIsNone(buffer.feed(value, False))

    def test_caption_history_has_individual_lifetimes_and_bounded_size(self):
        history = CaptionHistory()
        history.add("A", "", "x" * 120, 0, 3)
        history.add("B", "", "short", 1, 3)
        history.prune(5)
        self.assertEqual([x[1] for x in history.items], ["A"])
        for name in ["C", "D", "E"]:
            history.add(name, "", "hello", 6, 3)
        self.assertEqual([x[1] for x in history.items], ["C", "D", "E"])
        history.prune(30)
        self.assertFalse(history.items)

    def test_slow_translation_does_not_hold_up_enqueue_and_cancel_hides_result(self):
        entered, release, stop = threading.Event(), threading.Event(), threading.Event()
        pending = Queue(maxsize=3)
        pending.put((time.monotonic(), "A", "hello"))
        events = []

        class SlowTranslator:
            def __init__(self, settings):
                pass

            def translate(self, text):
                entered.set()
                release.wait(2)
                return "안녕", "fake"

        worker = threading.Thread(target=translate_pending, args=(Settings(), stop, pending,
                                  lambda *x: events.append(x), SlowTranslator))
        worker.start()
        try:
            self.assertTrue(entered.wait(1))
            pending.put_nowait((time.monotonic(), "B", "next speech"))
            stop.set()
        finally:
            release.set()
            worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertFalse(any(x[0] == "caption" for x in events))

    def test_late_api_response_is_not_displayed(self):
        stop, pending = threading.Event(), Queue()
        pending.put((0, "A", "hello"))
        clock = [0]
        events = []

        class Translator:
            def __init__(self, settings):
                pass

            def translate(self, text):
                clock[0] = 13
                return "late", "fake"

        def emit(*event):
            events.append(event)
            stop.set()

        translate_pending(Settings(), stop, pending, emit, Translator, lambda: clock[0])
        self.assertEqual(events[0][0], "status")
        self.assertFalse(any(x[0] == "caption" for x in events))

    def test_error_does_not_prevent_original_caption_delivery(self):
        stop, pending = threading.Event(), Queue()
        pending.put((0, "A", "hello"))
        events = []

        class BrokenTranslator:
            def __init__(self, settings):
                pass

            def translate(self, text):
                raise RuntimeError("quota exceeded")

        def emit(*event):
            events.append(event)
            if event[0] == "caption":
                stop.set()

        translate_pending(Settings(), stop, pending, emit, BrokenTranslator, lambda: 0)
        self.assertEqual(events[0][0], "error")
        self.assertEqual(events[1], ("caption", "A", "hello", "[번역 실패] hello"))

    def test_stuck_native_worker_is_terminated_on_stop(self):
        stop = threading.Event()
        events = []

        def dispatch(kind, values):
            events.append((kind, values))
            stop.set()

        started = time.monotonic()
        supervise(stuck_worker, (), stop, dispatch, grace=0.15)
        self.assertLess(time.monotonic() - started, 4)
        self.assertEqual(events, [("status", ("ready",))])

    def test_last_error_survives_child_exit(self):
        events = []
        supervise(final_error_worker, (), threading.Event(), lambda *event: events.append(event))
        self.assertIn(("error", ("device disconnected",)), events)

    def test_restart_after_forced_stop_leaves_no_child_process(self):
        before = {p.pid for p in multiprocessing.active_children()}
        for _ in range(3):
            stop = threading.Event()
            supervise(stuck_worker, (), stop, lambda *_: stop.set(), grace=0.05)
        self.assertEqual({p.pid for p in multiprocessing.active_children()}, before)
        events = []
        supervise(final_error_worker, (), threading.Event(), lambda *event: events.append(event))
        self.assertIn(("error", ("device disconnected",)), events)

    def test_native_crash_is_reported(self):
        events = []
        supervise(crashed_worker, (), threading.Event(), lambda *event: events.append(event))
        self.assertTrue(any(kind == "error" and "7" in values[0] for kind, values in events))


if __name__ == "__main__":
    unittest.main()

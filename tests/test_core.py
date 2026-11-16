from pathlib import Path
from queue import Queue
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from voice_caption.core import Settings, SpeakerTimeline, parse_roi, put_latest
from voice_caption.models import route


class CoreTests(unittest.TestCase):
    def test_backlog_discards_oldest_and_retains_recent_audio(self):
        queue = Queue(maxsize=2)
        self.assertFalse(put_latest(queue, "old"))
        put_latest(queue, "recent")
        self.assertTrue(put_latest(queue, "newest"))
        self.assertEqual([queue.get(), queue.get()], ["recent", "newest"])

    def test_repeated_speaker_evidence_is_required(self):
        timeline = SpeakerTimeline()
        timeline.add(1, {"Alice"})
        self.assertEqual(timeline.resolve(0, 2), "화자 미확인")
        timeline.add(1.5, {"Alice"})
        self.assertEqual(timeline.resolve(0.5, 2), "Alice (화면 추정)")
        self.assertEqual(timeline.resolve(3, 4), "화자 미확인")

    def test_sparse_screen_observations_do_not_cover_long_speech(self):
        timeline = SpeakerTimeline()
        timeline.add(1, {"Alice"})
        timeline.add(4, {"Alice"})
        self.assertEqual(timeline.resolve(1, 4), "화자 미확인")

    def test_conflicting_overlap_or_missing_names_are_not_attributed(self):
        for uncertain in [{"Bob"}, {"Alice", "Bob"}, set()]:
            with self.subTest(uncertain=uncertain):
                timeline = SpeakerTimeline()
                timeline.add(1, {"Alice"})
                timeline.add(2, uncertain)
                self.assertEqual(timeline.resolve(0, 3), "화자 미확인")

    def test_translation_route_can_pivot_and_handles_cycles(self):
        edges = [SimpleNamespace(from_code=a, to_code=b) for a, b in
                 [("ja", "en"), ("en", "ja"), ("en", "ko")]]
        self.assertEqual([p.to_code for p in route(edges, "ja", "ko")], ["en", "ko"])
        self.assertEqual(route(edges, "en", "en"), [])
        with self.assertRaises(ValueError):
            route(edges, "ja", "de")

    def test_configuration_roundtrip_clamps_sizes_and_ignores_unknown(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            settings = Settings(font="맑은 고딕", width=20)
            settings.save(path)
            actual = Settings.load(path)
            self.assertEqual(actual.font, "맑은 고딕")
            self.assertEqual(actual.width, 300)
            path.write_text('{"future_field": true, "opacity": 120}', encoding="utf-8")
            self.assertEqual(Settings.load(path).opacity, 100)
            path.write_text('{"width": "bad"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                Settings.load(path)

    def test_roi_accepts_negative_monitor_coordinates_but_limits_area(self):
        self.assertEqual(parse_roi("-1920, 20, 400, 200")["left"], -1920)
        for value in ["0,0,0,10", "0,0,4000,2000", "0,0,400", "abc"]:
            with self.assertRaises(ValueError):
                parse_roi(value)


if __name__ == "__main__":
    unittest.main()

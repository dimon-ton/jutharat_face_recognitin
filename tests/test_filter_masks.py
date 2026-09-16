import csv
from pathlib import Path
import tempfile
import unittest

from filter_masks import filter_masks
from filter_album import filter_album
from test_filter_album import FakeEngine


class FakeMaskDetector:
    def detections(self, path):
        if path.name == "broken.jpg":
            raise ValueError("Unreadable image")
        return [dict(label="cloth", confidence=0.9, box=[0, 0, 10, 10])] if path.name == "group.jpg" else []


class MaskTests(unittest.TestCase):
    def test_separation_errors_and_originals(self):
        with tempfile.TemporaryDirectory() as temp:
            album, output = Path(temp) / "album", Path(temp) / "out"
            (album / "nested").mkdir(parents=True)
            for name in ("group.jpg", "other.jpg", "broken.jpg"):
                (album / "nested" / name).touch()
            counts = filter_masks(album, output, FakeMaskDetector())
            self.assertEqual(counts, dict(masked=1, no_mask_detected=1, error=1))
            self.assertTrue((output / "masked/nested/group.jpg").exists())
            self.assertTrue((output / "no_mask_detected/nested/other.jpg").exists())
            self.assertEqual(len(list(album.rglob("*.jpg"))), 3)
            with (output / "report.csv").open(encoding="utf-8-sig") as report:
                self.assertEqual(len(list(csv.DictReader(report))), 3)
            with self.assertRaisesRegex(ValueError, "already exists"):
                filter_masks(album, output, FakeMaskDetector())
            with self.assertRaisesRegex(ValueError, "separate"):
                filter_masks(album, album / "out", FakeMaskDetector())

    def test_masked_group_excluded_from_face_matches(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            refs, album, output = root / "refs", root / "album", root / "out"
            refs.mkdir()
            album.mkdir()
            (refs / "ref.jpg").touch()
            (album / "group.jpg").touch()
            counts = filter_album(refs, album, output, FakeEngine(), mask_detector=FakeMaskDetector())
            self.assertEqual(counts["masked"], 1)
            self.assertFalse((output / "matches/group.jpg").exists())


if __name__ == "__main__":
    unittest.main()

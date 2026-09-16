import csv
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from filter_masks import filter_masks
from filter_album import filter_album
from test_filter_album import FakeEngine
from mask_detector import MaskDetector


class FakeMaskDetector:
    def detections(self, path):
        if path.name == "broken.jpg":
            raise ValueError("Unreadable image")
        return [dict(label="cloth", confidence=0.9, box=[0, 0, 10, 10])] if path.name == "group.jpg" else []


class MaskTests(unittest.TestCase):
    def test_official_checkpoint_label_aliases(self):
        model = SimpleNamespace(names=["none", "surgical", "cloth", "respirator", "valve"])
        torch = SimpleNamespace(hub=SimpleNamespace(load=lambda *args, **kwargs: model))
        pillow = SimpleNamespace(Image=object(), ImageOps=object())
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "weights.pt").touch()
            (root / "hubconf.py").touch()
            with patch.dict("sys.modules", {"torch": torch, "PIL": pillow}):
                detector = MaskDetector(root / "weights.pt", root)
            self.assertEqual(detector.names[0], "unmasked")
            self.assertEqual(detector.names[4], "valved")
            model.names = ["person"]
            with patch.dict("sys.modules", {"torch": torch, "PIL": pillow}):
                with self.assertRaisesRegex(ValueError, "Expected TFM"):
                    MaskDetector(root / "weights.pt", root)

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

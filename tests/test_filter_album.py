from pathlib import Path
import csv
import tempfile
import unittest

from filter_album import filter_album


class FakeEngine:
    def encodings(self, path):
        return {"ref.jpg": [0], "group.jpg": [0.8, 0.4], "other.jpg": [0.7],
                "empty.jpg": [], "badref.jpg": [0, 1],
                "eight.jpg": [0.4] * 8, "nine.jpg": [0.4] * 9}[path.name]

    def distance(self, references, face):
        return face


class FilterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.reference, self.album, self.output = root / "refs", root / "album", root / "out"
        self.reference.mkdir()
        self.album.mkdir()
        (self.reference / "ref.jpg").touch()

    def run_filter(self, **kwargs):
        return filter_album(self.reference, self.album, self.output, FakeEngine(), **kwargs)

    def test_group_match_and_report(self):
        for name in ("group.jpg", "other.jpg", "empty.jpg", "broken.jpg"):
            (self.album / name).touch()
        counts = self.run_filter()
        self.assertEqual(counts, dict(match=1, no_match=1, no_face=1, too_many_faces=0, error=1))
        self.assertTrue((self.output / "matches/group.jpg").exists())
        self.assertTrue((self.album / "group.jpg").exists())
        with (self.output / "report.csv").open(encoding="utf-8-sig", newline="") as f:
            self.assertEqual(len(list(csv.DictReader(f))), 4)

    def test_stricter_threshold(self):
        (self.album / "group.jpg").touch()
        self.assertEqual(self.run_filter(tolerance=0.3)["match"], 0)

    def test_face_count_limit(self):
        for name in ("eight.jpg", "nine.jpg"):
            (self.album / name).write_bytes(b"original photo")
        counts = self.run_filter()
        self.assertEqual(counts["match"], 1)
        self.assertEqual(counts["too_many_faces"], 1)
        self.assertTrue((self.output / "matches/eight.jpg").exists())
        self.assertFalse((self.output / "matches/nine.jpg").exists())
        for name in ("eight.jpg", "nine.jpg"):
            self.assertEqual((self.album / name).read_bytes(), b"original photo")
        with (self.output / "report.csv").open(encoding="utf-8-sig", newline="") as f:
            rows = {row["photo"]: row for row in csv.DictReader(f)}
        self.assertEqual(rows["nine.jpg"]["status"], "too_many_faces")
        self.assertEqual(rows["nine.jpg"]["faces"], "9")
        self.assertEqual(rows["nine.jpg"]["best_distance"], "")
        self.assertEqual(rows["nine.jpg"]["copied_to"], "")

    def test_ambiguous_reference(self):
        (self.reference / "badref.jpg").touch()
        with self.assertRaisesRegex(ValueError, "exactly one face"):
            self.run_filter()
        self.assertFalse(self.output.exists())

    def test_existing_output_refused(self):
        self.output.mkdir()
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.run_filter()

    def test_nested_output_refused(self):
        self.output = self.album / "out"
        with self.assertRaisesRegex(ValueError, "separate"):
            self.run_filter()

    def test_duplicate_names_in_subfolders(self):
        for name in ("one", "two"):
            folder = self.album / name
            folder.mkdir()
            (folder / "group.jpg").touch()
        self.assertEqual(self.run_filter()["match"], 2)
        for name in ("one", "two"):
            self.assertTrue((self.output / "matches" / name / "group.jpg").exists())


if __name__ == "__main__":
    unittest.main()

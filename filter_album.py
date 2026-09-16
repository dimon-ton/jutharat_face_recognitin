"""Find candidate photos of one consenting person in a downloaded album."""
import argparse
import csv
import math
from pathlib import Path
import shutil
import sys

EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def image_files(folder):
    return sorted(p for p in folder.rglob("*")
                  if p.is_file() and not p.is_symlink() and p.suffix.lower() in EXTENSIONS)


def validate_paths(reference, album, output):
    for folder in (reference, album):
        if not folder.is_dir():
            raise ValueError(f"Folder does not exist: {folder}")
    if reference == album or reference in album.parents or album in reference.parents:
        raise ValueError("Reference and album folders must be separate, not nested.")
    for source in (reference, album):
        if output == source or source in output.parents or output in source.parents:
            raise ValueError("Output must be separate from reference and album folders.")
    if output.exists():
        raise ValueError("Output already exists. Choose a new folder to avoid overwriting files.")


class FaceEngine:
    def __init__(self, upsample):
        import face_recognition
        import numpy
        from PIL import Image, ImageOps
        self.fr = face_recognition
        self.np = numpy
        self.Image = Image
        self.ImageOps = ImageOps
        self.upsample = upsample

    def encodings(self, path):
        with self.Image.open(path) as source:
            image = self.np.array(self.ImageOps.exif_transpose(source).convert("RGB"))
        locations = self.fr.face_locations(image, number_of_times_to_upsample=self.upsample)
        return self.fr.face_encodings(image, known_face_locations=locations)

    def distance(self, references, face):
        return float(min(self.fr.face_distance(references, face)))


def filter_album(reference, album, output, engine, tolerance=0.5, mask_detector=None):
    validate_paths(reference, album, output)
    references = []
    # Reject ambiguous references instead of silently learning the wrong person.
    for path in image_files(reference):
        if mask_detector is not None and mask_detector.detections(path):
            raise ValueError(f"Reference contains a detected masked face: {path}")
        faces = engine.encodings(path)
        if len(faces) != 1:
            raise ValueError(f"Reference must contain exactly one face: {path} ({len(faces)} found)")
        references.append(faces[0])
    if not references:
        raise ValueError("No reference images found. Add clear photos of only Kru Jutharat.")
    photos = image_files(album)
    if not photos:
        raise ValueError("No supported album images found.")
    output.mkdir(parents=True, exist_ok=False)
    matches = output / "matches"
    matches.mkdir()
    counts = {"match": 0, "no_match": 0, "no_face": 0, "error": 0}
    if mask_detector is not None:
        counts["masked"] = 0
    with (output / "report.csv").open("w", newline="", encoding="utf-8-sig") as report:
        writer = csv.DictWriter(report, fieldnames=["photo", "status", "faces", "best_distance", "copied_to", "error"])
        writer.writeheader()
        for index, path in enumerate(photos, 1):
            relative = path.relative_to(album)
            row = dict(photo=str(relative), status="error", faces="", best_distance="", copied_to="", error="")
            try:
                if mask_detector is not None and mask_detector.detections(path):
                    row["status"] = "masked"
                    counts["masked"] += 1
                    writer.writerow(row)
                    report.flush()
                    print(f"[{index}/{len(photos)}] masked: {relative}")
                    continue
                faces = engine.encodings(path)
                row["faces"] = len(faces)
                distance = min((engine.distance(references, face) for face in faces), default=None)
                if distance is not None and not math.isfinite(distance):
                    raise ValueError("Invalid face distance")
                row["best_distance"] = "" if distance is None else f"{distance:.6f}"
                row["status"] = "no_face" if distance is None else "match" if distance <= tolerance else "no_match"
                if row["status"] == "match":
                    destination = matches / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, destination)
                    row["copied_to"] = str(destination.relative_to(output))
            except Exception as exc:
                row.update(status="error", error=str(exc))
            counts[row["status"]] += 1
            writer.writerow(row)
            report.flush()
            print(f"[{index}/{len(photos)}] {row['status']}: {relative}")
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True, help="Photos containing only Kru Jutharat")
    parser.add_argument("--album", type=Path, required=True, help="Downloaded LINE album folder (searched recursively)")
    parser.add_argument("--output", type=Path, required=True, help="New output folder; must not already exist")
    parser.add_argument("--tolerance", type=float, default=0.5, help="Lower is stricter; default 0.5 (not a confidence percentage)")
    parser.add_argument("--upsample", type=int, choices=(0, 1, 2), default=1, help="2 may detect smaller faces, but is slower")
    parser.add_argument("--mask-weights", type=Path, help="TFM YOLOv5 weights; enables exclusion of any masked face")
    parser.add_argument("--yolo-repo", type=Path, help="Local YOLOv5 v7.0 checkout")
    parser.add_argument("--mask-confidence", type=float, default=0.5)
    args = parser.parse_args()
    if bool(args.mask_weights) != bool(args.yolo_repo):
        parser.error("Use --mask-weights and --yolo-repo together.")
    if not 0 < args.tolerance <= 1:
        parser.error("Tolerance must be greater than 0 and at most 1.")
    try:
        paths = [p.resolve() for p in (args.reference, args.album, args.output)]
        validate_paths(*paths)
        detector = None
        if args.mask_weights:
            from mask_detector import MaskDetector
            detector = MaskDetector(args.mask_weights, args.yolo_repo, args.mask_confidence)
        counts = filter_album(*paths, engine=FaceEngine(args.upsample), tolerance=args.tolerance,
                              mask_detector=detector)
    except ImportError as exc:
        print(f"Missing dependency: {exc}. See README.md for installation.", file=sys.stderr)
        return 1
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Finished: {counts}. Review candidate photos in {paths[2] / 'matches'}")
    return 1 if counts["error"] else 0


if __name__ == "__main__":
    sys.exit(main())

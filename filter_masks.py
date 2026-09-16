"""Separate images containing any detected masked face; preserve originals."""
import argparse
import csv
import json
from pathlib import Path
import shutil
import sys

from filter_album import image_files
from mask_detector import MaskDetector


def filter_masks(album, output, detector):
    album, output = Path(album).resolve(), Path(output).resolve()
    if not album.is_dir():
        raise ValueError(f"Folder does not exist: {album}")
    if output == album or album in output.parents or output in album.parents:
        raise ValueError("Output must be separate from the album.")
    if output.exists():
        raise ValueError("Output already exists. Choose a new folder.")
    photos = image_files(album)
    if not photos:
        raise ValueError("No supported album images found.")
    output.mkdir(parents=True)
    counts = dict(masked=0, no_mask_detected=0, error=0)
    with (output / "report.csv").open("w", newline="", encoding="utf-8-sig") as report:
        writer = csv.DictWriter(report, fieldnames=["photo", "status", "detections", "copied_to", "error"])
        writer.writeheader()
        for index, path in enumerate(photos, 1):
            relative = path.relative_to(album)
            row = dict(photo=str(relative), status="error", detections="", copied_to="", error="")
            try:
                masks = detector.detections(path)
                row["detections"] = json.dumps(masks)
                row["status"] = "masked" if masks else "no_mask_detected"
                destination = output / row["status"] / relative
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
    parser.add_argument("--album", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mask-weights", type=Path, required=True)
    parser.add_argument("--yolo-repo", type=Path, required=True)
    parser.add_argument("--mask-confidence", type=float, default=0.5)
    parser.add_argument("--mask-size", type=int, default=640)
    parser.add_argument("--mask-device", default="cpu")
    args = parser.parse_args()
    try:
        detector = MaskDetector(args.mask_weights, args.yolo_repo, args.mask_confidence,
                                args.mask_size, args.mask_device)
        counts = filter_masks(args.album, args.output, detector)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Finished: {counts}. Results: {args.output}")
    return 1 if counts["error"] else 0


if __name__ == "__main__":
    sys.exit(main())

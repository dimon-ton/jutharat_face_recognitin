# Repository Guidelines

## Project Structure & Module Organization

This is a local Python CLI for finding candidate photos of Kru Jutharat in downloaded LINE albums and optionally filtering masked faces.

- `filter_album.py`: face matching, input validation, image discovery, copying, and CSV reports.
- `filter_masks.py`: standalone mask filtering and reporting.
- `mask_detector.py`: local TFM YOLOv5 model adapter.
- `tests/`: standard-library unit tests using fake recognition engines and detectors.
- `README.md`: installation, model setup, and CLI usage; `requirements.txt`: core dependencies.

Local assets belong in ignored directories: `jutharat_face/` for references, `data/album/` for photos, `models/` for weights, and `vendor/yolov5/` for the optional detector checkout. Generated output uses `results*/`.

## Build, Test, and Development Commands

Run commands from the repository root:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe filter_album.py --reference jutharat_face --album data/album --output results
```

These create an environment, install core dependencies, run tests, and filter an album. Follow the README's native-build prerequisites for dlib on Windows. There is no separate build step. Mask filtering additionally requires the documented YOLOv5 checkout, dependencies, and TFM weights; inspect `filter_masks.py --help` for options.

## Coding Style & Naming Conventions

Use four-space indentation, `snake_case` functions and variables, `PascalCase` classes, and uppercase constants. Follow existing double-quoted strings, short module docstrings, and `pathlib.Path` filesystem handling. Keep heavyweight ML imports inside engine initialization so unit tests remain dependency-light. No formatter or linter is configured.

## Testing Guidelines

Use `unittest`, with files named `tests/test_*.py` and methods named `test_*`. Use temporary directories and injected fakes. Cover matching thresholds, CSV results, path validation, error handling, and preservation of originals when changing these behaviors. No numeric coverage target is configured. Real recognition and detector accuracy require separate manual checks with authorized photos.

## Commit & Pull Request Guidelines

History uses short imperative subjects, such as `Add direct YOLO face-mask filtering`. Keep commits focused. Pull requests should describe behavior changes, link relevant issues, report test results, and document CLI or dependency changes. Distinguish fake-engine tests from real-model validation.

## Privacy & Output Safety

Process only authorized photos with the reference subject's consent. Keep photos, model weights, and results out of Git. Preserve originals and album subfolders, require new output folders separate from inputs, and keep face encodings in memory.

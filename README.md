# Kru Jutharat — LINE album photo filter

Local Python tool based on [ageitgey/face_recognition](https://github.com/ageitgey/face_recognition).
It finds **candidate whole photos containing Kru Jutharat**, including group photos.
It does not crop out other people or access your LINE account.

## Prepare photos

1. Obtain Kru Jutharat's consent and use only album photos you are authorized to process.
2. Download the photos from your LINE album using LINE's own save/download controls. Extract any ZIP first.
3. Use the supplied photos in `jutharat_face` as the reference images. Every reference must contain exactly one detectable face of Kru Jutharat. If any photo includes other people, prepare a crop containing only her before running. Different angles and lighting help.
4. Place album photos in `data/album`. Subfolders are supported. Supported extensions: JPG, JPEG, PNG, WEBP, BMP. Convert HEIC images first.

All image processing stays on your machine. Face encodings are held in memory, not saved.
Protect both the source photos and output, which may contain other people's images.

## Install

This machine has Python 3.13.15 (64-bit) installed for this project. The project environment is `.venv`; use `.\.venv\Scripts\python.exe` to avoid the Windows Store Python shortcut. You do not need to activate it or change PowerShell's execution policy.

The local environment includes face-recognition 1.3.0, dlib 20.0.1 (built from source), NumPy 2.5.3, Pillow 12.3.0, face-recognition-models 0.3.0, and setuptools 80.10.2. Dependency consistency and the real face-recognition import were verified. The older model package emits a pkg_resources deprecation warning; the setuptools constraint keeps its import working.

Python is required. The upstream library uses dlib and does **not officially support Windows**.
Windows installation may require CMake and Visual Studio C++ build tools. If dlib will not build, use Linux/WSL instead of installing untrusted binary packages.

With Python and the required native build tools installed, in PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
$env:PYTHONUTF8 = "1"
$env:PATH = (Join-Path (Get-Location) '.venv\Scripts') + ';' + $env:PATH
.\.venv\Scripts\python.exe -m pip install "setuptools>=80,<81" wheel cmake
.\.venv\Scripts\python.exe -m pip install dlib --no-build-isolation
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The UTF-8 setting avoids a dlib source-installation error on Thai-locale Windows. These environment-variable changes apply only to the current terminal. Install the Visual Studio 2022 Build Tools C++ workload before building dlib.

Alternative in an Ubuntu/WSL terminal, inside this project folder:

```bash
sudo apt update
sudo apt install python3-venv python3-dev build-essential cmake
python3 -m venv .venv-linux
.venv-linux/bin/python -m pip install --upgrade pip
.venv-linux/bin/python -m pip install -r requirements.txt
```

## Run

```powershell
.\.venv\Scripts\python.exe filter_album.py --reference jutharat_face --album data/album --output results
```

For WSL, replace `.\.venv\Scripts\python.exe` with `.venv-linux/bin/python`.
Output must be a **new folder**, separate from both input folders. For another run use `--output results-2`.

- `results/matches/`: copies of candidate photos, preserving album subfolders and original files.
- `results/report.csv`: one row per album photo, with match status, detected face count, best distance, copied path, and any error. Open in Excel with UTF-8 support.

The default threshold is `--tolerance 0.5`. Lower it (for example `0.45`) if incorrect people are included. Raise it cautiously if known photos are missed. A distance is **not a confidence percentage**. Any one detected face matching any reference makes the photo a candidate.
Try `--upsample 2` for small faces in group photos; this is slower. Blur, occlusion, lighting, and pose can cause missed or incorrect matches. Manually review results and some rejected photos before relying on them.

Invalid reference photos stop the run before creating output. Unreadable album photos are recorded as errors and processing continues. Exit status is nonzero if errors occurred; completed results remain available. The tool never deletes source photos and refuses to reuse an existing output folder.

## Tests

```powershell
python -m unittest discover -s tests -v
```

Tests use a fake recognition engine, so they do not require dlib. Real recognition accuracy must be tested separately with your consenting reference subject and representative album photos.

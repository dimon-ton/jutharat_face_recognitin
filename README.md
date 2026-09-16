# Kru Jutharat — LINE album photo filter

Local Python tool based on [ageitgey/face_recognition](https://github.com/ageitgey/face_recognition).
It finds **candidate whole photos containing Kru Jutharat**, including group photos.
It does not crop out other people or access your LINE account.

Albums can also be downloaded from Google Drive using `download_drive.py`,
including on a VM before running face recognition. See the Google Drive section below.

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

Photos with more than eight detected faces are excluded, even if Kru Jutharat matches. The report marks them `too_many_faces` and records the face count. Photos with exactly eight faces remain eligible.

The default threshold is `--tolerance 0.5`. Lower it (for example `0.45`) if incorrect people are included. Raise it cautiously if known photos are missed. A distance is **not a confidence percentage**. Within the eight-face limit, any one detected face matching any reference makes the photo a candidate.
Try `--upsample 2` for small faces in group photos; this is slower. Blur, occlusion, lighting, and pose can cause missed or incorrect matches. Manually review results and some rejected photos before relying on them.

Invalid reference photos stop the run before creating output. Unreadable album photos are recorded as errors and processing continues. Exit status is nonzero if errors occurred; completed results remain available. The tool never deletes source photos and refuses to reuse an existing output folder.

## Tests

```powershell
python -m unittest discover -s tests -v
```

Tests use a fake recognition engine, so they do not require dlib. Real recognition accuracy must be tested separately with your consenting reference subject and representative album photos.

## Filter out face masks with direct YOLO detection

`filter_masks.py` runs a detector on each whole image. Any detected cloth,
surgical, respirator, or valved mask excludes that image, including masks on
other people in group photos. It uses the five-class pretrained
[TFM YOLOv5 model](https://github.com/GibranBenitez/TFM_dataset).
Ordinary YOLO weights do not detect face masks; the tool checks the model's
class names and refuses a model with different classes.

Set up a local [YOLOv5 v7.0](https://github.com/ultralytics/yolov5/tree/v7.0)
checkout and its dependencies in your Python environment:

```bash
git clone --branch v7.0 --depth 1 https://github.com/ultralytics/yolov5.git vendor/yolov5
python -m pip install -r vendor/yolov5/requirements.txt
```

Download the [authors' YOLOv5 weights](https://drive.google.com/file/d/1uAZioqd4Pvurl7eEiDawidve8FU0dFXA/view)
from the TFM benchmark table. Extract the download if necessary and place the
checkpoint at `models/tfm-yolo.pt`. Use the same Python environment for setup
and execution (on Windows, replace `python` with `.\.venv\Scripts\python.exe`).
The legacy TFM checkpoint's compatibility with this checkout and your installed
PyTorch version must be checked with a real run; it has not been verified here.

To filter masks independently of face recognition:

```bash
python filter_masks.py --album data/album --output results-masks --mask-weights models/tfm-yolo.pt --yolo-repo vendor/yolov5
```

- `results-masks/masked/`: copies of images containing any detected masked face.
- `results-masks/no_mask_detected/`: copies of the remaining images.
- `results-masks/report.csv`: status, mask labels, confidence scores, bounding boxes, and errors.

Original photos remain untouched and subfolders are preserved. Errors are
reported and excluded from both output categories. Output must be a new folder
separate from the album. `no_mask_detected` means the detector found no mask;
small, blurred, or occluded faces can still be missed. Review representative
results and tune `--mask-confidence 0.5` (lower catches more candidates, higher
reduces false positives). `--mask-size 1280` can help with small faces at a cost
in speed. The standalone command defaults to CPU; use `--mask-device cuda:0`
with a supported CUDA environment.

To exclude masked photos before matching Kru Jutharat:

```bash
python filter_album.py --reference jutharat_face --album data/album --output results-unmasked --mask-weights models/tfm-yolo.pt --yolo-repo vendor/yolov5
```

The face-match report marks excluded photos `masked`. Masked reference photos
stop the run before output is created. Without the two model arguments,
`filter_album.py` retains its existing behavior. Tests cover filtering and
error handling with fake detectors; real detection accuracy is not tested.

## Download Google Drive albums on a VM

`download_drive.py` accepts a Drive folder URL or ID and downloads JPG, JPEG,
PNG, WEBP, and BMP images recursively. It supports private folders accessible
to the signed-in account and publicly shared folders. The Google API is used
only to read Drive files; face recognition runs locally on the VM.

### Google sign-in: authorize once, then run without a browser

1. In a Google Cloud project, enable the **Google Drive API**, configure the
   OAuth consent screen, and create an OAuth client with type **Desktop app**.
   For an external app in Testing, add your Google account as a test user.
   Follow [Google's setup guide](https://developers.google.com/workspace/drive/api/quickstart/python).
2. Save the downloaded client JSON as `.secrets/drive-credentials.json` on
   a trusted computer with a browser. Install the downloader dependencies and sign in:

   ```bash
   python -m pip install -r requirements-drive.txt
   python download_drive.py --authorize-only
   ```

   On Windows, use your Python environment's executable, such as
   `.\.venv\Scripts\python.exe`, in place of `python`.
   This step does not download photos. The requested `drive.readonly` scope
   permits reading all Drive files the account can access; the command retrieves
   only the selected folder tree. A metadata-only scope cannot download images.
3. Securely transfer `.secrets/drive-token.json` to the same relative path in
   the VM checkout (for example, using SCP). The VM needs this token, not the
   desktop client JSON. Protect it as a credential: it contains a refresh token.
   On Linux, use `chmod 700 .secrets` and `chmod 600 .secrets/drive-token.json`.
   The directory is ignored by Git.

Normal runs refresh access automatically without opening a browser. If access
is revoked or expires, repeat `--authorize-only` locally and transfer the new token.
External OAuth apps in **Testing** receive refresh tokens that expire after
seven days for this scope. For ongoing VM operation, configure an appropriate
production/internal OAuth app or use the service-account option below.
See [Google's refresh-token expiration rules](https://developers.google.com/identity/protocols/oauth2#expiration).

### Install and run on a Linux VM

From the repository root, install the native build prerequisites and both sets
of Python dependencies (the downloader alone does not require dlib):

```bash
sudo apt update
sudo apt install python3-venv python3-dev build-essential cmake
python3 -m venv .venv-linux
.venv-linux/bin/python -m pip install --upgrade pip
.venv-linux/bin/python -m pip install -r requirements.txt -r requirements-drive.txt
```

Place the consenting subject's reference photos in `jutharat_face/`, then run:

```bash
.venv-linux/bin/python download_drive.py \
  --folder "https://drive.google.com/drive/folders/FOLDER_ID" \
  --output data/album && \
.venv-linux/bin/python filter_album.py \
  --reference jutharat_face --album data/album --output results
```

The `&&` starts recognition only if the download completes without reported errors.
Use new album and results directories for every run, including scheduled jobs;
existing destinations are refused. This is a snapshot download, not incremental
synchronization. For cron/systemd, use absolute paths and set the working directory
to the repository root. `--token` can point to a credential outside the checkout.

Subfolders are preserved. Names incompatible with local filesystems are sanitized;
duplicate names receive numeric suffixes. `download_report.csv` records original
Drive names and IDs, local paths, skipped items, and errors. Non-image files,
unsupported image formats such as HEIC, and Drive shortcuts are skipped. Known
image MIME types supply an extension when the name lacks a supported one. Use
`--no-recursive` to restrict downloads to the selected folder's immediate files.
An empty folder produces an empty report. Failed downloads remove partial files,
keep completed images, and return a nonzero exit status. Review the report before
using partial results; retry with a fresh output directory.

### Alternative: service-account authentication

For an unattended VM, create a service account in a project with the Drive API
enabled. Share the album folder with its email address as **Viewer**, with downloads
allowed. Organization sharing restrictions may require administrator assistance.
Google documents [direct folder sharing with service accounts](https://developers.google.com/workspace/guides/create-credentials).

```bash
.venv-linux/bin/python download_drive.py --auth service-account \
  --credentials .secrets/service-account.json \
  --folder "FOLDER_ID" --output data/album
```

Without `--credentials`, this mode uses Application Default Credentials, including
`GOOGLE_APPLICATION_CREDENTIALS` or a configured attached VM identity. That identity
must have Drive read scope and access to the folder; default Google Cloud scopes
alone may not include Drive. See [ADC setup](https://cloud.google.com/docs/authentication/application-default-credentials).
Keep JSON keys out of Git and restrict them to the VM user.

### Downloader tests

Run `python -m unittest discover -s tests -v`. Fake Drive responses exercise folder
traversal, pagination, filenames, reports, and failure handling without network
access. Real Google authorization and downloading require your credentials and
an accessible Drive folder; they are not validated by those tests.

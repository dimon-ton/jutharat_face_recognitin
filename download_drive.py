"""Download supported album images from a Google Drive folder."""
import argparse
import csv
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import parse_qs, urlparse

from filter_album import EXTENSIONS

FOLDER_MIME = "application/vnd.google-apps.folder"
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
IMAGE_SUFFIXES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
                  "image/bmp": ".bmp", "image/x-ms-bmp": ".bmp"}


def parse_folder(value):
    value = value.strip()
    if re.fullmatch(r"[\w-]+", value, flags=re.ASCII):
        return value, None
    url = urlparse(value)
    if url.scheme != "https" or url.hostname != "drive.google.com":
        raise ValueError("Use a Google Drive folder ID or an https://drive.google.com folder link.")
    query = parse_qs(url.query)
    match = re.fullmatch(r"/drive/(?:u/\d+/)?folders/([\w-]+)/?", url.path, flags=re.ASCII)
    folder_id = ""
    if match:
        folder_id = match.group(1)
    elif url.path == "/open":
        folder_id = query.get("id", [""])[0]
    resource_key = query.get("resourcekey", [None])[0]
    if not re.fullmatch(r"[\w-]+", folder_id, flags=re.ASCII):
        raise ValueError("The link must identify a Google Drive folder.")
    if resource_key and not re.fullmatch(r"[\w-]+", resource_key, flags=re.ASCII):
        raise ValueError("Invalid Drive resource key.")
    return folder_id, resource_key


def local_name(name, used):
    """Allocate one portable filename, including on case-insensitive filesystems."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', "_", name).strip().rstrip(". ")
    if not name or name in {".", ".."}:
        name = "unnamed"
    if re.fullmatch(r"CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³]", name.split(".")[0], re.I):
        name = "_" + name
    suffix = Path(name).suffix[:16]
    stem = (name[:-len(suffix)] if suffix else name)[:100]
    candidate = stem + suffix
    number = 2
    while candidate.casefold() in used:
        candidate = f"{stem}-{number}{suffix}"
        number += 1
    used.add(candidate.casefold())
    return candidate


def image_name(item):
    mime = item.get("mimeType", "")
    if mime.startswith("application/vnd.google-apps."):
        return None
    name = item["name"]
    if Path(name).suffix.lower() in EXTENSIONS:
        return name
    if mime in IMAGE_SUFFIXES:
        return name + IMAGE_SUFFIXES[mime]
    return None


class DriveClient:
    def __init__(self, service):
        self.service = service

    @staticmethod
    def with_key(request, file_id, resource_key):
        if resource_key:
            request.headers["X-Goog-Drive-Resource-Keys"] = f"{file_id}/{resource_key}"
        return request

    def folder(self, folder_id, resource_key):
        request = self.service.files().get(fileId=folder_id, supportsAllDrives=True,
                                          fields="id,name,mimeType,resourceKey,trashed")
        return self.with_key(request, folder_id, resource_key).execute(num_retries=3)

    def children(self, folder_id, resource_key):
        token = None
        while True:
            request = self.service.files().list(
                q=f"'{folder_id}' in parents and trashed = false", pageSize=1000,
                pageToken=token, supportsAllDrives=True, includeItemsFromAllDrives=True,
                fields="nextPageToken,incompleteSearch,files(id,name,mimeType,resourceKey)")
            page = self.with_key(request, folder_id, resource_key).execute(num_retries=3)
            if page.get("incompleteSearch"):
                raise ValueError("Drive returned an incomplete folder listing. Try again.")
            yield from page.get("files", [])
            token = page.get("nextPageToken")
            if not token:
                break

    def download(self, item, stream):
        from googleapiclient.http import MediaIoBaseDownload
        request = self.service.files().get_media(fileId=item["id"], supportsAllDrives=True)
        self.with_key(request, item["id"], item.get("resourceKey"))
        downloader = MediaIoBaseDownload(stream, request)
        done = False
        while not done:
            _, done = downloader.next_chunk(num_retries=3)


def connect(credentials_path=None):
    import google.auth
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    if credentials_path is not None:
        credentials = Credentials.from_service_account_file(str(credentials_path), scopes=SCOPES)
    else:
        credentials, _ = google.auth.default(scopes=SCOPES)
    return DriveClient(build("drive", "v3", credentials=credentials, cache_discovery=False))


def connect_oauth(credentials_path, token_path, authorize=False):
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    if credentials_path.resolve() == token_path.resolve():
        raise ValueError("Credentials and token must use different files.")
    credentials = None
    if token_path.exists() and not authorize:
        credentials = Credentials.from_authorized_user_file(str(token_path))
        if not credentials.has_scopes(SCOPES):
            raise ValueError("Token lacks Drive read access. Run again with --authorize on a computer with a browser.")
        if not credentials.valid and credentials.refresh_token:
            try:
                credentials.refresh(Request())
            except RefreshError as exc:
                raise ValueError("Google sign-in expired or was revoked. Run --authorize-only on a computer "
                                 "with a browser and transfer the new token to the VM.") from exc
    if authorize:
        flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
        credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    if not credentials or not credentials.valid:
        raise ValueError("No valid Google sign-in token. Run with --authorize on a computer with a browser, "
                         "then securely copy the token to the VM. See README.md.")
    if not credentials.has_scopes(SCOPES) or not credentials.refresh_token:
        raise ValueError("Google sign-in requires Drive read access and an offline refresh token. "
                         "Run --authorize-only again and grant the requested access.")
    token_path.parent.mkdir(parents=True, exist_ok=True)
    # Temporary files are owner-only on POSIX; replace atomically after writing.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=token_path.parent,
                                         delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(credentials.to_json())
        os.replace(temporary, token_path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return DriveClient(build("drive", "v3", credentials=credentials, cache_discovery=False))


def download_album(client, folder_id, output, resource_key=None, recursive=True):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("Output already exists. Choose a new folder to avoid overwriting files.")
    root = client.folder(folder_id, resource_key)
    if root["mimeType"] != FOLDER_MIME or root.get("trashed"):
        raise ValueError("The selected Drive item must be a non-trashed folder.")
    output.mkdir(parents=True, exist_ok=False)
    counts = dict(downloaded=0, skipped=0, error=0)
    pending = [(folder_id, resource_key or root.get("resourceKey"), output)]
    visited = {folder_id}
    with (output / "download_report.csv").open("x", newline="", encoding="utf-8-sig") as report:
        writer = csv.DictWriter(report, fieldnames=["file_id", "name", "status", "local_path", "error"])
        writer.writeheader()

        def record(item, status, path="", error=""):
            counts[status] += 1
            writer.writerow(dict(file_id=item["id"], name=item["name"], status=status,
                                 local_path=str(path), error=error))
            report.flush()
            print(f"{status}: {item['name']}")

        while pending:
            parent_id, key, directory = pending.pop()
            try:
                entries = sorted(client.children(parent_id, key), key=lambda item: (item["name"], item["id"]))
            except Exception as exc:
                record(dict(id=parent_id, name=str(directory.relative_to(output))), "error", error=str(exc))
                continue
            used = {"download_report.csv"} if directory == output else set()
            for item in entries:
                if item["mimeType"] == FOLDER_MIME:
                    if not recursive or item["id"] in visited:
                        record(item, "skipped")
                        continue
                    destination = directory / local_name(item["name"], used)
                    try:
                        destination.mkdir()
                        visited.add(item["id"])
                        pending.append((item["id"], item.get("resourceKey"), destination))
                    except OSError as exc:
                        record(item, "error", error=str(exc))
                    continue
                name = image_name(item)
                if name is None:
                    record(item, "skipped")
                    continue
                destination = directory / local_name(name, used)
                created = False
                try:
                    with destination.open("xb") as stream:
                        created = True
                        client.download(item, stream)
                except BaseException as exc:
                    if created:
                        destination.unlink(missing_ok=True)
                    if not isinstance(exc, Exception):
                        raise
                    record(item, "error", error=str(exc))
                    continue
                record(item, "downloaded", destination.relative_to(output))
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", help="Google Drive folder link or ID")
    parser.add_argument("--output", type=Path, default=Path("data/album"), help="New local folder (default: data/album)")
    parser.add_argument("--credentials", type=Path,
                        help="OAuth desktop client JSON or service-account key (depends on --auth)")
    parser.add_argument("--auth", choices=("oauth", "service-account"), default="oauth")
    parser.add_argument("--token", type=Path, default=Path(".secrets/drive-token.json"))
    parser.add_argument("--authorize", action="store_true", help="Open a browser for initial Google sign-in")
    parser.add_argument("--authorize-only", action="store_true", help="Save a Google sign-in token without downloading")
    parser.add_argument("--no-recursive", action="store_true", help="Download only images directly in this folder")
    args = parser.parse_args()
    if not args.authorize_only and not args.folder:
        parser.error("--folder is required unless using --authorize-only.")
    if args.auth != "oauth" and (args.authorize or args.authorize_only):
        parser.error("Authorization flags are only available with --auth oauth.")
    try:
        if args.authorize_only:
            connect_oauth(args.credentials or Path(".secrets/drive-credentials.json"), args.token, True)
            print(f"Authorization saved to {args.token}. Keep this file private when transferring it to the VM.")
            return 0
        folder_id, key = parse_folder(args.folder)
        if args.output.exists():
            raise ValueError("Output already exists. Choose a new folder to avoid overwriting files.")
        if args.auth == "oauth":
            client = connect_oauth(args.credentials or Path(".secrets/drive-credentials.json"),
                                   args.token, args.authorize)
        else:
            client = connect(args.credentials)
        counts = download_album(client, folder_id, args.output, key, not args.no_recursive)
    except ImportError as exc:
        print(f"Missing dependency: {exc}. Install requirements-drive.txt.", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Finished: {counts}. Report: {args.output / 'download_report.csv'}")
    return 1 if counts["error"] else 0


if __name__ == "__main__":
    sys.exit(main())

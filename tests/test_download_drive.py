import csv
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from download_drive import DriveClient, FOLDER_MIME, SCOPES, connect, connect_oauth, download_album, main, parse_folder

try:
    import google_auth_oauthlib.flow
    import googleapiclient.discovery
    from google.auth.exceptions import RefreshError
except ImportError:
    DRIVE_DEPENDENCIES = False
else:
    DRIVE_DEPENDENCIES = True


def item(file_id, name, mime="image/jpeg", **kwargs):
    return dict(id=file_id, name=name, mimeType=mime, **kwargs)


class FakeDrive:
    def __init__(self, tree):
        self.tree = tree
        self.downloads = []

    def folder(self, folder_id, resource_key):
        return item(folder_id, "Album", FOLDER_MIME)

    def children(self, folder_id, resource_key):
        entries = self.tree[folder_id]
        if isinstance(entries, Exception):
            raise entries
        return entries

    def download(self, entry, stream):
        stream.write(entry["id"].encode())
        if entry["id"] == "broken":
            raise OSError("Download interrupted")
        self.downloads.append(entry["id"])


class DownloadTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.output = Path(temporary.name) / "album"

    def test_folder_links_and_invalid_inputs(self):
        for value in ("abc-123", "https://drive.google.com/drive/folders/abc-123",
                      "https://drive.google.com/drive/u/0/folders/abc-123?usp=sharing",
                      "https://drive.google.com/open?id=abc-123"):
            self.assertEqual(parse_folder(value), ("abc-123", None))
        self.assertEqual(parse_folder("https://drive.google.com/drive/folders/abc?resourcekey=key"),
                         ("abc", "key"))
        for value in ("https://example.com/drive/folders/abc", "abc' or trashed = true",
                      "https://drive.google.com/file/d/abc/view", ""):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_folder(value)

    def test_recursive_images_and_report(self):
        client = FakeDrive({"root": [item("one", "photo.JPG"), item("sub", "Trip", FOLDER_MIME),
                                     item("pdf", "notes.pdf", "application/pdf"),
                                     item("shortcut", "link.jpg", "application/vnd.google-apps.shortcut")],
                            "sub": [item("two", "ภาพ", "image/png")]})
        counts = download_album(client, "root", self.output)
        self.assertEqual(counts, dict(downloaded=2, skipped=2, error=0))
        self.assertEqual((self.output / "photo.JPG").read_bytes(), b"one")
        self.assertEqual((self.output / "Trip/ภาพ.png").read_bytes(), b"two")
        with (self.output / "download_report.csv").open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 4)
        self.assertEqual({row["file_id"] for row in rows}, {"one", "two", "pdf", "shortcut"})

    def test_duplicates_and_unsafe_names_remain_separate(self):
        names = ["photo.jpg", "photo.jpg", "PHOTO.jpg", "../escape.jpg", "CON.jpg", "a:b.jpg", "a?b.jpg"]
        client = FakeDrive({"root": [item(str(i), name) for i, name in enumerate(names)]})
        counts = download_album(client, "root", self.output)
        files = list(self.output.glob("*.jpg"))
        self.assertEqual(counts["downloaded"], len(names))
        self.assertEqual(len(files), len(names))
        self.assertEqual({path.read_bytes() for path in files}, {str(i).encode() for i in range(len(names))})
        self.assertTrue((self.output / "_CON.jpg").exists())
        self.assertFalse((self.output.parent / "escape.jpg").exists())

    def test_failure_removes_partial_file_and_continues(self):
        client = FakeDrive({"root": [item("broken", "bad.jpg"), item("ok", "good.png")]})
        self.assertEqual(download_album(client, "root", self.output), dict(downloaded=1, skipped=0, error=1))
        self.assertFalse((self.output / "bad.jpg").exists())
        self.assertTrue((self.output / "good.png").exists())

    def test_folder_listing_failure_is_reported(self):
        client = FakeDrive({"root": [item("sub", "Private", FOLDER_MIME), item("ok", "ok.jpg")],
                            "sub": PermissionError("Access denied")})
        self.assertEqual(download_album(client, "root", self.output), dict(downloaded=1, skipped=0, error=1))

    def test_existing_output_and_nonfolder_rejected(self):
        client = FakeDrive({"root": []})
        client.folder = Mock(return_value=item("root", "photo.jpg"))
        with self.assertRaisesRegex(ValueError, "folder"):
            download_album(client, "root", self.output)
        self.assertFalse(self.output.exists())
        self.output.mkdir()
        with self.assertRaisesRegex(ValueError, "already exists"):
            download_album(client, "root", self.output)

    def test_nonrecursive_and_empty_folder(self):
        client = FakeDrive({"root": [item("sub", "Trip", FOLDER_MIME)]})
        self.assertEqual(download_album(client, "root", self.output, recursive=False),
                         dict(downloaded=0, skipped=1, error=0))
        self.assertFalse((self.output / "Trip").exists())

    def test_pagination_and_resource_key(self):
        request = Mock(headers={})
        request.execute.side_effect = [dict(files=[item("a", "a.jpg")], nextPageToken="next"),
                                       dict(files=[item("b", "b.jpg")])]
        service = Mock()
        service.files.return_value.list.return_value = request
        client = DriveClient(service)
        self.assertEqual(len(list(client.children("root", "secret-key"))), 2)
        calls = service.files.return_value.list.call_args_list
        self.assertIsNone(calls[0].kwargs["pageToken"])
        self.assertEqual(calls[1].kwargs["pageToken"], "next")
        self.assertTrue(calls[0].kwargs["includeItemsFromAllDrives"])
        self.assertEqual(request.headers["X-Goog-Drive-Resource-Keys"], "root/secret-key")

    def test_incomplete_listing_is_not_silent_success(self):
        service = Mock()
        service.files.return_value.list.return_value.execute.return_value = dict(incompleteSearch=True)
        with self.assertRaisesRegex(ValueError, "incomplete"):
            list(DriveClient(service).children("root", None))

    def test_cli_failure_exit_status(self):
        with patch("sys.argv", ["download_drive.py", "--folder", "root", "--output", str(self.output)]), \
                patch("download_drive.connect_oauth", return_value=FakeDrive({"root": [item("broken", "bad.jpg")]})):
            self.assertEqual(main(), 1)

    def test_authorize_only_does_not_download(self):
        with patch("sys.argv", ["download_drive.py", "--authorize-only"]), \
                patch("download_drive.connect_oauth") as connect, \
                patch("download_drive.download_album") as download:
            self.assertEqual(main(), 0)
            self.assertTrue(connect.call_args.args[2])
            download.assert_not_called()


@unittest.skipUnless(DRIVE_DEPENDENCIES, "Install requirements-drive.txt for authentication adapter tests")
class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.token = self.root / "token.json"
        self.client_json = self.root / "client.json"

    def test_vm_without_token_never_opens_browser(self):
        with patch("google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file") as flow:
            with self.assertRaisesRegex(ValueError, "No valid Google sign-in token"):
                connect_oauth(self.client_json, self.token)
            flow.assert_not_called()

    def test_browser_authorization_saves_offline_token(self):
        credentials = Mock(valid=True, refresh_token="fake-refresh")
        credentials.to_json.return_value = '{"refresh_token": "fake-refresh"}'
        with patch("google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file") as flow, \
                patch("googleapiclient.discovery.build"):
            flow.return_value.run_local_server.return_value = credentials
            connect_oauth(self.client_json, self.token, authorize=True)
            flow.return_value.run_local_server.assert_called_once_with(
                port=0, access_type="offline", prompt="consent")
            self.assertIn("fake-refresh", self.token.read_text())
            self.assertEqual(list(self.root.iterdir()), [self.token])

    def test_vm_refreshes_cached_token_without_desktop_credentials(self):
        self.token.write_text("{}")
        credentials = Mock(valid=False, refresh_token="fake-refresh")
        credentials.to_json.return_value = '{"token": "new-fake-token"}'

        def refresh(request):
            credentials.valid = True

        credentials.refresh.side_effect = refresh
        with patch("google.oauth2.credentials.Credentials.from_authorized_user_file", return_value=credentials), \
                patch("google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file") as flow, \
                patch("googleapiclient.discovery.build"):
            connect_oauth(self.client_json, self.token)
            credentials.refresh.assert_called_once()
            flow.assert_not_called()
            self.assertIn("new-fake-token", self.token.read_text())

    def test_revoked_token_is_preserved_and_requires_reauthorization(self):
        self.token.write_text("{}")
        credentials = Mock(valid=False, refresh_token="fake-refresh")
        credentials.refresh.side_effect = RefreshError("revoked")
        with patch("google.oauth2.credentials.Credentials.from_authorized_user_file", return_value=credentials):
            with self.assertRaisesRegex(ValueError, "revoked"):
                connect_oauth(self.client_json, self.token)
        self.assertEqual(self.token.read_text(), "{}")

    def test_service_account_key_and_adc(self):
        with patch("google.oauth2.service_account.Credentials.from_service_account_file") as from_file, \
                patch("google.auth.default", return_value=(Mock(), "project")) as default, \
                patch("googleapiclient.discovery.build"):
            connect(self.client_json)
            from_file.assert_called_once_with(str(self.client_json), scopes=SCOPES)
            default.assert_not_called()
            connect()
            default.assert_called_once_with(scopes=SCOPES)


if __name__ == "__main__":
    unittest.main()

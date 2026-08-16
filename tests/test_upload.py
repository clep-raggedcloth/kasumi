import asyncio
import io
import unittest
from urllib.parse import parse_qs, urlparse

from fastapi import UploadFile
from starlette.requests import Request

from app.routers.upload import _decode_statement_csv, upload_statement


class UnusedSession:
    def add(self, _value):
        raise AssertionError("デコード失敗時にDBへアクセスしてはいけません")


def make_request() -> Request:
    return Request({
        "type": "http",
        "scheme": "http",
        "server": ("testserver", 80),
        "root_path": "",
        "path": "/upload",
        "query_string": b"",
        "headers": [],
    })


class DecodeStatementCsvTests(unittest.TestCase):
    def test_decodes_cp932(self):
        content = "利用者　様,4980-****,カード\r\n2026/07/01,日経ＩＤ決済,4800,１,１,4800,\r\n"

        self.assertEqual(_decode_statement_csv(content.encode("cp932")), content)

    def test_decodes_utf8_with_bom(self):
        content = "利用者　様,4980-****,カード\n"

        self.assertEqual(_decode_statement_csv(content.encode("utf-8-sig")), content)

    def test_rejects_unsupported_encoding(self):
        with self.assertRaisesRegex(ValueError, "UTF-8またはShift_JIS"):
            _decode_statement_csv(b"\x81")

    def test_upload_redirects_decode_error_without_touching_database(self):
        upload = UploadFile(filename="invalid.csv", file=io.BytesIO(b"\x81"))

        response = asyncio.run(upload_statement(
            request=make_request(),
            file=upload,
            year=2026,
            month=8,
            db=UnusedSession(),
        ))

        self.assertEqual(response.status_code, 303)
        params = parse_qs(urlparse(response.headers["location"]).query)
        self.assertIn("UTF-8またはShift_JIS", params["error"][0])


if __name__ == "__main__":
    unittest.main()

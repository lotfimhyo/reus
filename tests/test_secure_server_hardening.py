"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

Regression tests for a hardening fix found via direct code review of the
mTLS RPC server (infrastructure/cluster_network/secure_server.py), not by
running existing tests -- this is exactly the kind of gap that a targeted
operational/security review of code paths with no dedicated tests is meant
to catch. `_read_body` previously did `int(Content-Length)` with no
validation (a malformed header raised an uncaught ValueError instead of a
clean 400) and had no cap on body size (a peer -- even one already
mTLS-authenticated -- could force an unbounded `rfile.read()`).

These tests exercise `_Handler._read_body` directly, without a real TLS
socket: BaseHTTPRequestHandler normally requires a live connection in
`__init__`, so a handler instance is built via `__new__` and given just the
attributes `_read_body` actually touches (`headers`, `rfile`).
"""
from __future__ import annotations

import io
import json
import unittest

from infrastructure.cluster_network.secure_server import _MAX_BODY_BYTES, _BadRequestBody, _Handler


def _make_handler(headers: dict, body_bytes: bytes) -> _Handler:
    handler = _Handler.__new__(_Handler)
    handler.headers = headers
    handler.rfile = io.BytesIO(body_bytes)
    return handler


class TestReadBodyHardening(unittest.TestCase):
    def test_valid_request_parses_normally(self):
        payload = {"term": 5, "candidate_id": "node-b"}
        body_bytes = json.dumps(payload).encode("utf-8")
        handler = _make_handler({"Content-Length": str(len(body_bytes))}, body_bytes)

        result = handler._read_body()

        self.assertEqual(result, payload)

    def test_malformed_content_length_raises_bad_request_not_uncaught_valueerror(self):
        handler = _make_handler({"Content-Length": "not-a-number"}, b"{}")

        with self.assertRaises(_BadRequestBody):
            handler._read_body()

    def test_negative_content_length_is_rejected(self):
        handler = _make_handler({"Content-Length": "-5"}, b"{}")

        with self.assertRaises(_BadRequestBody):
            handler._read_body()

    def test_oversized_content_length_is_rejected_before_reading(self):
        """الاختبار الحرج: يجب أن يُرفَض الطلب **قبل** أي محاولة قراءة فعلية
        بحجم ضخم -- لا فقط أن القراءة تفشل لاحقًا بعد استهلاك الذاكرة."""
        handler = _make_handler({"Content-Length": str(_MAX_BODY_BYTES + 1)}, b"{}")

        with self.assertRaises(_BadRequestBody):
            handler._read_body()

    def test_missing_content_length_defaults_to_zero_not_error(self):
        handler = _make_handler({}, b"")
        with self.assertRaises(json.JSONDecodeError):
            handler._read_body()  # لا محتوى فعليًا لتحليله كـJSON، لكن ليس _BadRequestBody


if __name__ == "__main__":
    unittest.main()

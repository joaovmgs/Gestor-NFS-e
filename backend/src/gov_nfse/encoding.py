from __future__ import annotations

import base64
import gzip


def gzip_base64_decode(value: str) -> bytes:
    return gzip.decompress(base64.b64decode(value))


def gzip_base64_decode_text(value: str, encoding: str = "utf-8") -> str:
    return gzip_base64_decode(value).decode(encoding)


def gzip_base64_encode(data: bytes) -> str:
    return base64.b64encode(gzip.compress(data)).decode("ascii")

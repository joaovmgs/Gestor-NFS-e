import base64

from danfse_brasil.logo import NFSE_LOGO_DATA_URI


def test_official_logo_is_embedded_as_png() -> None:
    prefix = "data:image/png;base64,"
    assert NFSE_LOGO_DATA_URI.startswith(prefix)
    content = base64.b64decode(NFSE_LOGO_DATA_URI.removeprefix(prefix))
    assert content.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(content) > 1_000

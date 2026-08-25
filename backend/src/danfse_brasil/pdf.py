"""PDF renderer for DANFSe documents."""

from __future__ import annotations

import os
from functools import cache
from pathlib import Path

from .html import render_danfse_html, render_header_html
from .models import DanfseData, HeaderData


def _configure_windows_dll_search_path() -> None:
    if not hasattr(os, "add_dll_directory"):
        return

    dll_directories = os.getenv("WEASYPRINT_DLL_DIRECTORIES", r"C:\msys64\mingw64\bin")
    for entry in dll_directories.split(os.pathsep):
        directory = Path(entry.strip())
        if directory.exists():
            os.add_dll_directory(str(directory))


_configure_windows_dll_search_path()


@cache
def _weasyprint_runtime():
    try:
        from weasyprint import HTML
        from weasyprint.text.fonts import FontConfiguration
    except ImportError as exc:
        raise RuntimeError("Dependencia weasyprint nao instalada. Execute: uv sync") from exc
    return HTML, FontConfiguration()


def render_header_pdf(data: HeaderData, output: str | Path) -> Path:
    """Render the implemented DANFSe header to a PDF file."""

    html_class, font_config = _weasyprint_runtime()
    output_path = Path(output)
    html = render_header_html(data)
    html_class(string=html, base_url=str(output_path.parent.resolve())).write_pdf(
        output_path,
        font_config=font_config,
    )
    return output_path


def render_danfse_pdf(data: DanfseData, output: str | Path) -> Path:
    """Render the implemented DANFSe blocks to a PDF file."""

    html_class, font_config = _weasyprint_runtime()
    output_path = Path(output)
    html = render_danfse_html(data)
    html_class(string=html, base_url=str(output_path.parent.resolve())).write_pdf(
        output_path,
        font_config=font_config,
    )
    return output_path

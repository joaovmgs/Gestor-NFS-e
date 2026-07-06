from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    default_notes_dir: Path
    api_token: str

    @classmethod
    def from_environment(cls) -> "Settings":
        data_dir = Path(os.environ.get("NFSE_DATA_DIR", "data")).resolve()
        return cls(
            data_dir=data_dir,
            default_notes_dir=Path(
                os.environ.get("NFSE_DEFAULT_NOTES_DIR", data_dir / "documents")
            ).resolve(),
            api_token=os.environ.get("NFSE_API_TOKEN", ""),
        )

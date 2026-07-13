from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Iterator
from xml.etree import ElementTree as ET


SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
  cnpj TEXT PRIMARY KEY,
  legal_name TEXT NOT NULL,
  certificate_source TEXT NOT NULL CHECK(certificate_source IN ('pfx', 'windows')),
  certificate_cnpj TEXT,
  remember_certificate INTEGER NOT NULL DEFAULT 0,
  certificate_reference TEXT,
  certificate_expires_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sync_state (
  company_cnpj TEXT PRIMARY KEY REFERENCES companies(cnpj) ON DELETE CASCADE,
  last_nsu INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'idle',
  diagnostic TEXT,
  started_at TEXT,
  finished_at TEXT,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  company_cnpj TEXT NOT NULL REFERENCES companies(cnpj) ON DELETE CASCADE,
  nsu INTEGER NOT NULL,
  access_key TEXT NOT NULL,
  note_number TEXT,
  document_type TEXT NOT NULL,
  event_type TEXT,
  direction TEXT NOT NULL,
  issued_at TEXT,
  issuer_name TEXT,
  customer_name TEXT,
  service_amount REAL,
  net_amount REAL,
  status TEXT NOT NULL DEFAULT '',
  xml_path TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(company_cnpj, nsu, access_key, document_type)
);

CREATE INDEX IF NOT EXISTS idx_documents_company_issued
  ON documents(company_cnpj, issued_at DESC);

CREATE TABLE IF NOT EXISTS sync_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  company_cnpj TEXT NOT NULL REFERENCES companies(cnpj) ON DELETE CASCADE,
  level TEXT NOT NULL,
  message TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sync_logs_company_created
  ON sync_logs(company_cnpj, id DESC);

CREATE TABLE IF NOT EXISTS app_settings (
  setting_key TEXT PRIMARY KEY,
  setting_value TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            document_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(documents)").fetchall()
            }
            if "event_type" not in document_columns:
                connection.execute("ALTER TABLE documents ADD COLUMN event_type TEXT")
            if "note_number" not in document_columns:
                connection.execute("ALTER TABLE documents ADD COLUMN note_number TEXT")
            company_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(companies)").fetchall()
            }
            if "certificate_cnpj" not in company_columns:
                connection.execute("ALTER TABLE companies ADD COLUMN certificate_cnpj TEXT")
                connection.execute(
                    """
                    UPDATE companies
                    SET certificate_cnpj = cnpj
                    WHERE certificate_cnpj IS NULL OR certificate_cnpj = ''
                    """
                )
            connection.execute(
                """
                DELETE FROM sync_logs
                WHERE id IN (
                  SELECT older.id
                  FROM sync_logs AS older
                  WHERE (
                    SELECT COUNT(*)
                    FROM sync_logs AS newer
                    WHERE newer.company_cnpj = older.company_cnpj
                      AND newer.id > older.id
                  ) >= 20
                )
                """
            )

    def backfill_note_numbers(self, batch_size: int = 200) -> int:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, xml_path
                FROM documents
                WHERE document_type = 'NFSE' AND note_number IS NULL
                """
            ).fetchall()
        updates: list[tuple[str, int]] = []
        updated = 0
        for row in rows:
            try:
                root = ET.parse(row["xml_path"]).getroot()
                number = next(
                    (
                        element.text.strip()
                        for element in root.iter()
                        if element.tag.rsplit("}", 1)[-1] == "nNFSe" and element.text
                    ),
                    None,
                )
                if number:
                    updates.append((number, row["id"]))
                    if len(updates) >= batch_size:
                        self._save_note_number_batch(updates)
                        updated += len(updates)
                        updates.clear()
            except (OSError, ET.ParseError):
                continue
        if updates:
            self._save_note_number_batch(updates)
            updated += len(updates)
        return updated

    def _save_note_number_batch(self, updates: list[tuple[str, int]]) -> None:
        with self.connect() as connection:
            connection.executemany(
                "UPDATE documents SET note_number = ? WHERE id = ?",
                updates,
            )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

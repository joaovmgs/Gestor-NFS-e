from __future__ import annotations

from typing import Any

from .database import Database


class Repository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list_companies(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT c.*, s.last_nsu, s.status AS sync_status, s.diagnostic
                FROM companies c
                JOIN sync_state s ON s.company_cnpj = c.cnpj
                ORDER BY c.legal_name COLLATE NOCASE
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def initialize_settings(self, default_notes_dir: str) -> None:
        with self.database.connect() as connection:
            connection.executemany(
                """
                INSERT OR IGNORE INTO app_settings (setting_key, setting_value)
                VALUES (?, ?)
                """,
                (
                    ("notes_directory", default_notes_dir),
                    ("notifications_enabled", "1"),
                ),
            )

    def get_settings(self) -> dict[str, Any]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT setting_key, setting_value FROM app_settings"
            ).fetchall()
        values = {row["setting_key"]: row["setting_value"] for row in rows}
        return {
            "notes_directory": values.get("notes_directory", ""),
            "notifications_enabled": values.get("notifications_enabled", "1") == "1",
        }

    def update_settings(self, notes_directory: str, notifications_enabled: bool) -> dict[str, Any]:
        with self.database.connect() as connection:
            connection.executemany(
                """
                INSERT INTO app_settings (setting_key, setting_value)
                VALUES (?, ?)
                ON CONFLICT(setting_key) DO UPDATE SET
                  setting_value=excluded.setting_value,
                  updated_at=CURRENT_TIMESTAMP
                """,
                (
                    ("notes_directory", notes_directory),
                    ("notifications_enabled", "1" if notifications_enabled else "0"),
                ),
            )
        return self.get_settings()

    def get_company(self, cnpj: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT c.*, s.last_nsu, s.status AS sync_status, s.diagnostic
                FROM companies c
                JOIN sync_state s ON s.company_cnpj = c.cnpj
                WHERE c.cnpj = ?
                """,
                (cnpj,),
            ).fetchone()
        return dict(row) if row else None

    def save_company(self, company: dict[str, Any]) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO companies (
                  cnpj, legal_name, certificate_source, remember_certificate,
                  certificate_reference, certificate_expires_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(cnpj) DO UPDATE SET
                  legal_name=excluded.legal_name,
                  certificate_source=excluded.certificate_source,
                  remember_certificate=excluded.remember_certificate,
                  certificate_reference=excluded.certificate_reference,
                  certificate_expires_at=excluded.certificate_expires_at,
                  updated_at=CURRENT_TIMESTAMP
                """,
                (
                    company["cnpj"],
                    company["legal_name"],
                    company["certificate_source"],
                    int(company["remember_certificate"]),
                    company.get("certificate_reference"),
                    company.get("certificate_expires_at"),
                ),
            )
            connection.execute(
                "INSERT OR IGNORE INTO sync_state (company_cnpj) VALUES (?)",
                (company["cnpj"],),
            )

    def list_documents(
        self,
        cnpj: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        direction: str | None = None,
        search: str | None = None,
        status: str | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> dict[str, Any]:
        filters = ["company_cnpj = ?"]
        parameters: list[Any] = [cnpj]
        if start_date:
            filters.append("date(issued_at) >= date(?)")
            parameters.append(start_date)
        if end_date:
            filters.append("date(issued_at) <= date(?)")
            parameters.append(end_date)
        if direction:
            filters.append("direction = ?")
            parameters.append(direction)
        if search:
            normalized_search = search.strip().replace(",", ".")
            filters.append(
                """
                (
                  note_number LIKE ? OR access_key LIKE ? OR issuer_name LIKE ?
                  OR customer_name LIKE ? OR printf('%.2f', service_amount) LIKE ?
                )
                """
            )
            pattern = f"%{normalized_search}%"
            parameters.extend([pattern] * 5)
        if status == "autorizada":
            filters.append("lower(COALESCE(status, '')) IN ('', 'autorizada')")
        elif status == "cancelada":
            filters.append("lower(COALESCE(status, '')) = 'cancelada'")
        where_clause = " AND ".join(filters)
        offset = (page - 1) * per_page

        with self.database.connect() as connection:
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM documents WHERE {where_clause}",
                    parameters,
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""
                SELECT * FROM documents
                WHERE {where_clause}
                ORDER BY COALESCE(issued_at, created_at) DESC, nsu DESC
                LIMIT ? OFFSET ?
                """,
                (*parameters, per_page, offset),
            ).fetchall()
        return {
            "items": [dict(row) for row in rows],
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": max(1, (total + per_page - 1) // per_page),
        }

    def list_documents_for_export(
        self,
        cnpj: str,
        *,
        start_date: str,
        end_date: str,
        direction: str,
    ) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM documents
                WHERE company_cnpj = ?
                  AND document_type = 'NFSE'
                  AND direction = ?
                  AND date(issued_at) >= date(?)
                  AND date(issued_at) <= date(?)
                ORDER BY issued_at, nsu
                """,
                (cnpj, direction, start_date, end_date),
            ).fetchall()
        return [dict(row) for row in rows]

    def set_sync_state(
        self,
        cnpj: str,
        *,
        status: str,
        diagnostic: str,
        last_nsu: int | None = None,
    ) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE sync_state SET
                  status = ?,
                  diagnostic = ?,
                  last_nsu = COALESCE(?, last_nsu),
                  started_at = CASE WHEN ? = 'syncing' THEN CURRENT_TIMESTAMP ELSE started_at END,
                  finished_at = CASE WHEN ? != 'syncing' THEN CURRENT_TIMESTAMP ELSE finished_at END,
                  updated_at = CURRENT_TIMESTAMP
                WHERE company_cnpj = ?
                """,
                (status, diagnostic[:600], last_nsu, status, status, cnpj),
            )
            level = "error" if status == "error" else ("warning" if status == "waiting" else "info")
            connection.execute(
                """
                INSERT INTO sync_logs (company_cnpj, level, message)
                VALUES (?, ?, ?)
                """,
                (cnpj, level, diagnostic[:1000]),
            )
            self._prune_sync_logs(connection, cnpj)

    def list_sync_logs(self, cnpj: str, limit: int = 50) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, level, message, created_at
                FROM sync_logs
                WHERE company_cnpj = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (cnpj, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def add_sync_log(self, cnpj: str, level: str, message: str) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO sync_logs (company_cnpj, level, message)
                VALUES (?, ?, ?)
                """,
                (cnpj, level, message[:1000]),
            )
            self._prune_sync_logs(connection, cnpj)

    @staticmethod
    def _prune_sync_logs(connection: Any, cnpj: str) -> None:
        connection.execute(
            """
            DELETE FROM sync_logs
            WHERE company_cnpj = ?
              AND id NOT IN (
                SELECT id
                FROM sync_logs
                WHERE company_cnpj = ?
                ORDER BY id DESC
                LIMIT 20
              )
            """,
            (cnpj, cnpj),
        )

    def save_document(self, document: dict[str, Any]) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO documents (
                  company_cnpj, nsu, access_key, note_number, document_type, event_type, direction, issued_at,
                  issuer_name, customer_name, service_amount, net_amount, status, xml_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(company_cnpj, nsu, access_key, document_type) DO UPDATE SET
                  event_type=excluded.event_type,
                  note_number=COALESCE(excluded.note_number, documents.note_number),
                  direction=excluded.direction,
                  issued_at=excluded.issued_at,
                  issuer_name=excluded.issuer_name,
                  customer_name=excluded.customer_name,
                  service_amount=excluded.service_amount,
                  net_amount=excluded.net_amount,
                  status=excluded.status,
                  xml_path=excluded.xml_path
                """,
                (
                    document["company_cnpj"],
                    document["nsu"],
                    document["access_key"],
                    document.get("note_number"),
                    document["document_type"],
                    document.get("event_type"),
                    document["direction"],
                    document.get("issued_at"),
                    document.get("issuer_name"),
                    document.get("customer_name"),
                    document.get("service_amount"),
                    document.get("net_amount"),
                    document.get("status", ""),
                    document["xml_path"],
                ),
            )
            event_type = str(document.get("event_type") or "").upper()
            if "CANCELAMENTO" in event_type:
                connection.execute(
                    """
                    UPDATE documents
                    SET status = 'Cancelada'
                    WHERE company_cnpj = ?
                      AND access_key = ?
                      AND document_type = 'NFSE'
                    """,
                    (document["company_cnpj"], document["access_key"]),
                )
            elif document["document_type"] == "NFSE":
                cancellation = connection.execute(
                    """
                    SELECT 1
                    FROM documents
                    WHERE company_cnpj = ?
                      AND access_key = ?
                      AND upper(COALESCE(event_type, '')) LIKE '%CANCELAMENTO%'
                    LIMIT 1
                    """,
                    (document["company_cnpj"], document["access_key"]),
                ).fetchone()
                if cancellation:
                    connection.execute(
                        """
                        UPDATE documents
                        SET status = 'Cancelada'
                        WHERE company_cnpj = ?
                          AND access_key = ?
                          AND document_type = 'NFSE'
                        """,
                        (document["company_cnpj"], document["access_key"]),
                    )

from __future__ import annotations

import filecmp
import re
import shutil
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from threading import Lock, Thread
from typing import Any

INVALID_WINDOWS_COMPONENT = re.compile(r'[<>:"/\\|?*]|[\x00-\x1f]')


def validate_dominio_configuration(
    code: str | None,
    alias: str | None,
    *,
    cnpj: str,
) -> tuple[str, str]:
    """Return the effective Domínio folder parts, applying safe placeholders."""
    normalized_code = (code or "").strip()
    normalized_alias = (alias or "").strip()
    if normalized_code and not normalized_code.isdigit():
        raise ValueError("O código da empresa no Domínio deve conter somente números.")
    if normalized_alias and INVALID_WINDOWS_COMPONENT.search(normalized_alias):
        raise ValueError('O apelido no Domínio não pode conter < > : " / \\ | ? *.')
    if normalized_alias.endswith((" ", ".")):
        raise ValueError("O apelido no Domínio não pode terminar com espaço ou ponto.")

    effective_code = normalized_code or "XX"
    safe_cnpj = re.sub(r"[^0-9A-Za-z]", "", cnpj).upper() or "SEM-CNPJ"
    effective_alias = normalized_alias or f"EMPRESA-{safe_cnpj}"
    if len(f"{effective_code}-{effective_alias}") > 180:
        raise ValueError("O código e o apelido no Domínio são muito longos.")
    return effective_code, effective_alias


def parse_issued_at(issued_at: str | None) -> datetime | None:
    if not issued_at:
        return None
    try:
        return datetime.fromisoformat(issued_at.replace("Z", "+00:00"))
    except ValueError:
        return None


def dominio_competence(
    issued_at: str | None,
    *,
    fallback_at: datetime | None = None,
) -> str:
    parsed = parse_issued_at(issued_at) or fallback_at or datetime.now().astimezone()
    return parsed.strftime("%m%Y")


def document_xml_path(
    notes_directory: str,
    *,
    cnpj: str,
    nsu: int,
    access_key: str,
    document_type: str,
    issued_at: str | None,
    dominio_enabled: bool,
    dominio_code: str | None,
    dominio_alias: str | None,
    fallback_at: datetime | None = None,
) -> Path:
    root = Path(notes_directory)
    filename = f"{nsu:012d}-{access_key}.xml"
    if dominio_enabled and document_type == "NFSE":
        code, alias = validate_dominio_configuration(
            dominio_code,
            dominio_alias,
            cnpj=cnpj,
        )
        return root / f"{code}-{alias}" / dominio_competence(
            issued_at,
            fallback_at=fallback_at,
        ) / filename
    return root / cnpj / "xml" / filename


ProgressCallback = Callable[[dict[str, Any]], None]
REORGANIZATION_BATCH_SIZE = 250


def reorganize_company_xmls(
    repository: Any,
    cnpj: str,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    settings = repository.get_settings()
    if not settings["dominio_folder_layout_enabled"]:
        raise ValueError("Ative a organização de pastas para o Domínio nas configurações.")
    company = repository.get_company(cnpj)
    if not company:
        raise ValueError("Empresa não encontrada.")

    documents = repository.list_company_nfse_documents(cnpj)
    result: dict[str, Any] = {
        "state": "running",
        "total": len(documents),
        "processed": 0,
        "moved": 0,
        "skipped": 0,
        "errors": 0,
        "details": [],
    }
    pending: list[tuple[int, Path, Path, str]] = []

    def publish() -> None:
        if progress_callback:
            progress_callback({**result, "details": list(result["details"])})

    def add_error(exc: Exception, count: int = 1) -> None:
        result["errors"] += count
        if len(result["details"]) < 20:
            result["details"].append(str(exc))

    def flush_pending() -> None:
        if not pending:
            return
        try:
            repository.update_document_xml_paths(
                [(str(destination), document_id) for document_id, _, destination, _ in pending]
            )
        except Exception as exc:
            for _, source, destination, action in reversed(pending):
                try:
                    if action == "moved" and destination.exists():
                        source.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(destination), str(source))
                    elif action == "deduplicated" and destination.exists():
                        source.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(destination, source)
                except OSError as rollback_error:
                    add_error(rollback_error)
            add_error(exc, len(pending))
        else:
            result["moved"] += len(pending)
        pending.clear()
        publish()

    publish()
    for document in documents:
        source = Path(document["xml_path"])
        destination = document_xml_path(
            settings["notes_directory"],
            cnpj=cnpj,
            nsu=int(document["nsu"]),
            access_key=str(document["access_key"]),
            document_type="NFSE",
            issued_at=document.get("issued_at"),
            dominio_enabled=True,
            dominio_code=company.get("dominio_code"),
            dominio_alias=company.get("dominio_alias"),
        )
        try:
            if source.resolve() == destination.resolve():
                result["skipped"] += 1
            elif not source.is_file():
                if destination.is_file():
                    pending.append((int(document["id"]), source, destination, "reconciled"))
                else:
                    raise FileNotFoundError(f"Arquivo não encontrado: {source}")
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    if not filecmp.cmp(source, destination, shallow=False):
                        raise FileExistsError(
                            f"Já existe um arquivo diferente em: {destination}"
                        )
                    source.unlink()
                    action = "deduplicated"
                else:
                    shutil.move(str(source), str(destination))
                    action = "moved"
                pending.append((int(document["id"]), source, destination, action))
        except Exception as exc:  # Cada arquivo deve falhar sem interromper os demais.
            add_error(exc)
        result["processed"] += 1
        if len(pending) >= REORGANIZATION_BATCH_SIZE:
            flush_pending()
        elif result["processed"] % REORGANIZATION_BATCH_SIZE == 0:
            publish()
    flush_pending()
    result["state"] = "completed"
    publish()
    return result


class ReorganizationManager:
    def __init__(self, repository: Any) -> None:
        self.repository = repository
        self._lock = Lock()
        self._jobs: dict[str, dict[str, Any]] = {}

    def start(self, cnpj: str) -> dict[str, Any]:
        settings = self.repository.get_settings()
        if not settings["dominio_folder_layout_enabled"]:
            raise ValueError("Ative a organização de pastas para o Domínio nas configurações.")
        if not self.repository.get_company(cnpj):
            raise ValueError("Empresa não encontrada.")
        with self._lock:
            current = self._jobs.get(cnpj)
            if current and current["state"] == "running":
                return self._copy(current)
            status: dict[str, Any] = {
                "state": "running",
                "total": 0,
                "processed": 0,
                "moved": 0,
                "skipped": 0,
                "errors": 0,
                "details": [],
            }
            self._jobs[cnpj] = status
        Thread(
            target=self._run,
            args=(cnpj,),
            name=f"dominio-reorganization-{cnpj}",
            daemon=True,
        ).start()
        return self._copy(status)

    def status(self, cnpj: str) -> dict[str, Any]:
        with self._lock:
            current = self._jobs.get(cnpj)
            if not current:
                raise ValueError("Nenhuma reorganização foi iniciada para esta empresa.")
            return self._copy(current)

    def _run(self, cnpj: str) -> None:
        try:
            result = reorganize_company_xmls(self.repository, cnpj, self._update(cnpj))
            self._set(cnpj, result)
        except Exception as exc:
            with self._lock:
                current = self._jobs[cnpj]
                current.update(
                    {
                        "state": "failed",
                        "message": str(exc),
                    }
                )

    def _update(self, cnpj: str) -> ProgressCallback:
        def callback(status: dict[str, Any]) -> None:
            self._set(cnpj, status)

        return callback

    def _set(self, cnpj: str, status: dict[str, Any]) -> None:
        with self._lock:
            self._jobs[cnpj] = self._copy(status)

    @staticmethod
    def _copy(status: dict[str, Any]) -> dict[str, Any]:
        return {**status, "details": list(status.get("details", []))}

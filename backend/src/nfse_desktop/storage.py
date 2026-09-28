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
    direction: str | None = None,
    fallback_at: datetime | None = None,
) -> Path:
    root = Path(notes_directory)
    filename = f"{nsu:012d}-{access_key}.xml"
    if dominio_enabled and document_type == "NFSE":
        if direction not in {"emitida", "recebida"}:
            return root / cnpj / "xml" / filename
        if not dominio_code or not dominio_alias:
            dominio_code = dominio_alias = None
        code, alias = validate_dominio_configuration(
            dominio_code,
            dominio_alias,
            cnpj=cnpj,
        )
        direction_folder = {"emitida": "Emitidas", "recebida": "Recebidas"}.get(
            direction or ""
        )
        path = root
        if direction_folder:
            path /= direction_folder
        path /= f"{code}-{alias}"
        path /= dominio_competence(
            issued_at,
            fallback_at=fallback_at,
        )
        return path / filename
    return root / cnpj / "xml" / filename


ProgressCallback = Callable[[dict[str, Any]], None]
REORGANIZATION_BATCH_SIZE = 250


def reorganize_company_xmls(
    repository: Any,
    cnpj: str,
    progress_callback: ProgressCallback | None = None,
    *,
    provisional_only: bool = False,
) -> dict[str, Any]:
    settings = repository.get_settings()
    if not settings["dominio_folder_layout_enabled"]:
        raise ValueError("Ative a organização de pastas para o Domínio nas configurações.")
    company = repository.get_company(cnpj)
    if not company:
        raise ValueError("Empresa não encontrada.")
    if not company.get("dominio_code") or not company.get("dominio_alias"):
        raise ValueError("Atualize a conexão Domínio e resolva o vínculo desta empresa pelo CNPJ.")

    documents = repository.list_company_nfse_documents(cnpj)
    if provisional_only:
        root = Path(settings["notes_directory"])
        provisional_roots = [root / kind / f"XX-EMPRESA-{cnpj}"
                             for kind in ("Emitidas", "Recebidas")]
        documents = [document for document in documents if any(
            Path(document["xml_path"]).is_relative_to(folder) for folder in provisional_roots
        )]
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
                    if action == "copied" and source.exists() and destination.exists():
                        destination.unlink()
                except OSError as rollback_error:
                    add_error(rollback_error)
            add_error(exc, len(pending))
        else:
            result["moved"] += len(pending)
            # Commit paths before removing originals. An interrupted batch can be
            # retried without losing files or leaving the database pointing nowhere.
            for _, source, destination, action in pending:
                if action in {"copied", "deduplicated"}:
                    try:
                        if filecmp.cmp(source, destination, shallow=False):
                            source.unlink()
                    except OSError as exc:
                        add_error(exc)
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
            direction=document.get("direction"),
        )
        try:
            if document.get("direction") not in {"emitida", "recebida"}:
                raise ValueError(f"XML sem direção reconhecida: {source.name}")
            if not source.is_file() and not destination.is_file():
                # Recover paths left by the earlier experimental month/type layout.
                root = Path(settings["notes_directory"]).resolve()
                if source.resolve().is_relative_to(root):
                    candidates = [source.parent / kind / source.name
                                  for kind in ("Emitidas", "Recebidas")]
                    found = [item for item in candidates if item.is_file()]
                    if len(found) == 1:
                        source = found[0]
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
                    action = "deduplicated"
                else:
                    shutil.copy2(source, destination)
                    action = "copied"
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

    def start(self, cnpj: str, *, provisional_only: bool = False) -> dict[str, Any]:
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
            args=(cnpj, provisional_only),
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

    def _run(self, cnpj: str, provisional_only: bool = False) -> None:
        try:
            result = reorganize_company_xmls(
                self.repository, cnpj, self._update(cnpj), provisional_only=provisional_only,
            )
            self._set(cnpj, result)
            if provisional_only and result["errors"]:
                self.repository.add_sync_log(
                    cnpj, "warning", "Alguns XMLs provisórios não puderam ser reorganizados. "
                    "Confira a opção Reorganizar XMLs existentes nas configurações da empresa.",
                )
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

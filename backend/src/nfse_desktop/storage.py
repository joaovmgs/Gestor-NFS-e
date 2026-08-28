from __future__ import annotations

import filecmp
import re
import shutil
from datetime import datetime
from pathlib import Path
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


def reorganize_company_xmls(repository: Any, cnpj: str) -> dict[str, Any]:
    settings = repository.get_settings()
    if not settings["dominio_folder_layout_enabled"]:
        raise ValueError("Ative a organização de pastas para o Domínio nas configurações.")
    company = repository.get_company(cnpj)
    if not company:
        raise ValueError("Empresa não encontrada.")

    result: dict[str, Any] = {"moved": 0, "skipped": 0, "errors": 0, "details": []}
    for document in repository.list_company_nfse_documents(cnpj):
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
                continue
            if not source.is_file():
                raise FileNotFoundError(f"Arquivo não encontrado: {source}")

            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                if not filecmp.cmp(source, destination, shallow=False):
                    raise FileExistsError(f"Já existe um arquivo diferente em: {destination}")
                source.unlink()
            else:
                shutil.move(str(source), str(destination))
            try:
                repository.update_document_xml_path(int(document["id"]), str(destination))
            except Exception:
                if destination.exists() and not source.exists():
                    source.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(destination), str(source))
                raise
            result["moved"] += 1
        except Exception as exc:  # Cada arquivo deve falhar sem interromper os demais.
            result["errors"] += 1
            if len(result["details"]) < 20:
                result["details"].append(str(exc))
    return result

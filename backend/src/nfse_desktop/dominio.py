from __future__ import annotations

from collections import defaultdict
from contextlib import closing

import pyodbc

from gov_nfse.xml_utils import normalize_cnpj

from .storage import validate_dominio_configuration


def connection_string(config: dict[str, str]) -> str:
    parts = []
    for field, parameter in (
        ("driver", "DRIVER"), ("server", "ENG"), ("database", "DBN"),
        ("uid", "UID"), ("pwd", "PWD"), ("host", "HOST"),
    ):
        value = config.get(field, "")
        if not isinstance(value, str) or not value or len(value) > 512:
            raise ValueError(f"Preencha o campo {field} da conexão Domínio.")
        # SQL Anywhere does not unescape ODBC braces for password values.
        # Reject delimiters rather than allowing extra connection parameters.
        if any(char in value for char in ";\r\n\0\"'") or value != value.strip():
            raise ValueError(f"O campo {field} contém delimitadores não suportados.")
        if field == "driver":
            if value not in pyodbc.drivers() or not value.startswith("SQL Anywhere "):
                raise ValueError("Instale o driver ODBC SQL Anywhere de 64 bits informado.")
            value = "{" + value + "}"
        parts.append(f"{parameter}={value}")
    return ";".join(parts) + ";CS=UTF-8;READONLY=YES;CON=GestorNFSe;"


def read_company_mappings(config: dict[str, str], cnpjs: list[str]) -> dict:
    connection = connection_string(config)
    try:
        with closing(pyodbc.connect(connection, timeout=8, readonly=True)) as db:
            with closing(db.cursor()) as cursor:
                # Only cadastral data is read; the external database is never modified.
                cursor.execute("SELECT cgce_emp, codi_emp, apel_emp FROM bethadba.geempre")
                requested = {normalize_cnpj(cnpj) for cnpj in cnpjs}
                candidates: dict[str, set[tuple[str, str]]] = defaultdict(set)
                for cnpj, code, alias in cursor:
                    key = normalize_cnpj(cnpj)
                    if key in requested:
                        candidates[key].add((str(code), str(alias or "").strip()))
    except pyodbc.Error as exc:
        state = str(exc.args[0]) if exc.args else ""
        if state == "28000":
            message = "Usuário ou senha do Domínio não foram aceitos."
        elif state in {"42S02", "42000", "42501"}:
            message = "O usuário precisa de permissão de leitura em bethadba.geempre."
        else:
            message = "Não foi possível consultar o Domínio. Confira a rede, o host e o servidor."
        raise ValueError(message) from None

    matched = []
    issues = []
    for cnpj in cnpjs:
        options = candidates.get(normalize_cnpj(cnpj), set())
        if len(options) != 1:
            issues.append({"cnpj": cnpj, "message": (
                "CNPJ não encontrado no Domínio." if not options
                else "CNPJ com mais de um código/apelido no Domínio. Verifique o cadastro."
            )})
            continue
        code, alias = next(iter(options))
        try:
            if not code or not alias:
                raise ValueError("Código ou apelido vazio no cadastro do Domínio.")
            validate_dominio_configuration(code, alias, cnpj=cnpj)
        except ValueError as exc:
            issues.append({"cnpj": cnpj, "message": str(exc)})
            continue
        matched.append({"cnpj": cnpj, "dominio_code": code, "dominio_alias": alias})
    return {"matched": matched, "issues": issues}

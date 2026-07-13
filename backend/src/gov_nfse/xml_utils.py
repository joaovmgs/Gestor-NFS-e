from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from xml.etree import ElementTree as ET


@dataclass(frozen=True)
class NfseSummary:
    chave_acesso: str | None
    numero: str | None
    competencia: date | None
    geracao: datetime | None
    emitente_cnpj: str | None
    emitente_nome: str | None
    tomador_cnpj: str | None
    tomador_nome: str | None
    valor_servico: float | None
    valor_liquido: float | None

    def classificar_para_cnpj(self, cnpj: str) -> str:
        cnpj_identifier = normalize_cnpj(cnpj)
        if self.emitente_cnpj == cnpj_identifier:
            return "emitida"
        if self.tomador_cnpj == cnpj_identifier:
            return "recebida"
        return "outro"


def summarize_nfse_xml(xml: str) -> NfseSummary:
    root = ET.fromstring(xml)
    return NfseSummary(
        chave_acesso=_text(root, "chaveAcesso"),
        numero=_text(root, "nNFSe"),
        competencia=_date(_text(root, "dCompet")),
        geracao=_datetime(_text(root, "dhEmi") or _text(root, "dhProc")),
        emitente_cnpj=normalize_cnpj(_section_text(root, "emit", "CNPJ")),
        emitente_nome=_section_text(root, "emit", "xNome"),
        tomador_cnpj=normalize_cnpj(_section_text(root, "toma", "CNPJ")),
        tomador_nome=_section_text(root, "toma", "xNome"),
        valor_servico=_float(_text(root, "vServ")),
        valor_liquido=_float(_text(root, "vLiq")),
    )


def normalize_cnpj(value: str | None) -> str:
    return "".join(char for char in str(value or "").upper() if char.isalnum())


def _text(root: ET.Element, tag: str) -> str | None:
    for elem in root.iter():
        if _local_name(elem.tag) == tag and elem.text:
            return elem.text.strip()
    return None


def _section_text(root: ET.Element, section: str, tag: str) -> str | None:
    for elem in root.iter():
        if _local_name(elem.tag) != section:
            continue
        for child in elem.iter():
            if _local_name(child.tag) == tag and child.text:
                return child.text.strip()
    return None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _date(value: str | None) -> date | None:
    dt = _datetime(value)
    return dt.date() if dt else None


def _datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None

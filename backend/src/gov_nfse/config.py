from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Ambiente(StrEnum):
    PRODUCAO = "producao"
    PRODUCAO_RESTRITA = "producao_restrita"


@dataclass(frozen=True)
class Endpoints:
    sefin: str
    adn: str
    danfse: str
    parametros: str


ENDPOINTS: dict[Ambiente, Endpoints] = {
    Ambiente.PRODUCAO: Endpoints(
        sefin="https://sefin.nfse.gov.br/SefinNacional",
        adn="https://adn.nfse.gov.br/contribuintes",
        danfse="https://adn.nfse.gov.br/danfse",
        parametros="https://adn.nfse.gov.br/parametrizacao",
    ),
    Ambiente.PRODUCAO_RESTRITA: Endpoints(
        sefin="https://sefin.producaorestrita.nfse.gov.br/SefinNacional",
        adn="https://adn.producaorestrita.nfse.gov.br/contribuintes",
        danfse="https://adn.producaorestrita.nfse.gov.br/danfse",
        parametros="https://adn.producaorestrita.nfse.gov.br/parametrizacao",
    ),
}

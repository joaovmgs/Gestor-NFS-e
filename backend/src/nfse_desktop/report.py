from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tempfile import NamedTemporaryFile
from xml.etree import ElementTree as ET

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from danfse_brasil import parse_danfse
from danfse_brasil.exceptions import InvalidNFSeXmlError
from danfse_brasil.models import MISSING_VALUE

MONEY_FORMAT = 'R$ #,##0.00;[Red]-R$ #,##0.00'
PERCENT_FORMAT = "0.00%"
DATE_FORMAT = "dd/mm/yyyy"
TEXT_COLOR = "172033"
MUTED_COLOR = "64748B"
TITLE_COLOR = "0F172A"
ACCENT_COLOR = "0F766E"
ACCENT_LIGHT = "CCFBF1"
ROW_ALT_COLOR = "F0FDFA"
CANCELLED_COLOR = "B91C1C"
CANCELLED_LIGHT = "FEE2E2"


@dataclass(frozen=True)
class ReportRow:
    numero: str
    situacao: str
    chave_acesso: str
    data_emissao: datetime | None
    prestador_cnpj: str
    prestador_razao_social: str
    tomador_cnpj: str
    tomador_razao_social: str
    codigo_tributacao_nacional: str
    codigo_tributacao_municipal: str
    descricao_tributacao: str
    descricao_servico: str
    codigo_nbs: str
    valor_servicos: Decimal | None
    aliquota_iss: Decimal | None
    base_calculo_iss: Decimal | None
    valor_iss: Decimal | None
    retencao_iss: str
    irrf_retido: Decimal | None
    csll_retida: Decimal | None
    contribuicao_previdenciaria_retida: Decimal | None
    aliquota_ibs_uf: Decimal | None
    aliquota_ibs_municipal: Decimal | None
    aliquota_cbs: Decimal | None
    valor_ibs: Decimal | None
    valor_cbs: Decimal | None
    ajuste_ibs: Decimal | None
    ajuste_cbs: Decimal | None
    pis_debito: Decimal | None
    cofins_debito: Decimal | None
    valor_liquido: Decimal | None
    finalidade_nfse: str
    tipo_debito: str
    tipo_credito: str


@dataclass(frozen=True)
class ReportColumn:
    title: str
    field: str
    kind: str = "text"
    width: float = 18


@dataclass(frozen=True)
class SummaryMetric:
    label: str
    value: object
    kind: str = "count"


COMMON_COLUMNS = (
    ReportColumn("Número da NFS-e", "numero", width=18),
    ReportColumn("Situação", "situacao", width=16),
    ReportColumn("Chave de acesso da NFS-e", "chave_acesso", width=48),
    ReportColumn("Data de emissão", "data_emissao", "date", 16),
)

TOMADOS_COLUMNS = COMMON_COLUMNS + (
    ReportColumn("CNPJ do prestador", "prestador_cnpj", width=22),
    ReportColumn("Razão social do prestador", "prestador_razao_social", width=38),
    ReportColumn("Código de Tributação Nacional", "codigo_tributacao_nacional", width=25),
    ReportColumn("Código de Tributação Municipal", "codigo_tributacao_municipal", width=25),
    ReportColumn("Descrição da tributação", "descricao_tributacao", width=48),
    ReportColumn("Descrição do serviço", "descricao_servico", width=52),
    ReportColumn("Valor dos serviços", "valor_servicos", "currency", 20),
    ReportColumn("Alíquota do ISS", "aliquota_iss", "percent", 17),
    ReportColumn("Base de cálculo do ISS", "base_calculo_iss", "currency", 22),
    ReportColumn("Valor do ISS", "valor_iss", "currency", 18),
    ReportColumn("Retenção do ISS", "retencao_iss", width=24),
    ReportColumn("IRRF retido", "irrf_retido", "currency", 18),
    ReportColumn("CSLL retida", "csll_retida", "currency", 18),
    ReportColumn(
        "Contribuição previdenciária retida",
        "contribuicao_previdenciaria_retida",
        "currency",
        30,
    ),
    ReportColumn("Valor IBS", "valor_ibs", "currency", 18),
    ReportColumn("Valor CBS", "valor_cbs", "currency", 18),
    ReportColumn("Ajuste IBS", "ajuste_ibs", "currency", 18),
    ReportColumn("Ajuste CBS", "ajuste_cbs", "currency", 18),
    ReportColumn("Valor líquido", "valor_liquido", "currency", 20),
    ReportColumn("Finalidade da NFS-e", "finalidade_nfse", width=28),
    ReportColumn("Tipo de débito", "tipo_debito", width=30),
    ReportColumn("Tipo de crédito", "tipo_credito", width=30),
)

PRESTADOS_COLUMNS = COMMON_COLUMNS + (
    ReportColumn("CNPJ/CPF do tomador", "tomador_cnpj", width=22),
    ReportColumn("Razão social/nome do tomador", "tomador_razao_social", width=38),
    ReportColumn("Código de Tributação Nacional", "codigo_tributacao_nacional", width=25),
    ReportColumn("Código de Tributação Municipal", "codigo_tributacao_municipal", width=25),
    ReportColumn("Descrição da tributação", "descricao_tributacao", width=48),
    ReportColumn("Descrição do serviço", "descricao_servico", width=52),
    ReportColumn("Código NBS", "codigo_nbs", width=20),
    ReportColumn("Valor dos serviços", "valor_servicos", "currency", 20),
    ReportColumn("Alíquota do ISS", "aliquota_iss", "percent", 17),
    ReportColumn("Base de cálculo do ISS", "base_calculo_iss", "currency", 22),
    ReportColumn("Valor do ISS", "valor_iss", "currency", 18),
    ReportColumn("Retenção do ISS", "retencao_iss", width=24),
    ReportColumn("Alíquota IBS UF", "aliquota_ibs_uf", "percent", 18),
    ReportColumn("Alíquota IBS Municipal", "aliquota_ibs_municipal", "percent", 22),
    ReportColumn("Alíquota CBS", "aliquota_cbs", "percent", 18),
    ReportColumn("Valor IBS", "valor_ibs", "currency", 18),
    ReportColumn("Valor CBS", "valor_cbs", "currency", 18),
    ReportColumn("Valor do PIS – débito/apuração própria", "pis_debito", "currency", 32),
    ReportColumn(
        "Valor da COFINS – débito/apuração própria",
        "cofins_debito",
        "currency",
        34,
    ),
    ReportColumn("Valor líquido", "valor_liquido", "currency", 20),
    ReportColumn("Finalidade da NFS-e", "finalidade_nfse", width=28),
    ReportColumn("Tipo de débito", "tipo_debito", width=30),
    ReportColumn("Tipo de crédito", "tipo_credito", width=30),
)


def generate_nfse_report_xlsx(
    *,
    company: dict[str, object],
    tipo: str,
    data_inicial: str,
    data_final: str,
    situacao: str | None,
    query: str | None,
    documents: list[dict[str, object]],
) -> Path:
    has_rows = bool(documents)
    is_prestados = tipo == "emitidas"
    columns = PRESTADOS_COLUMNS if is_prestados else TOMADOS_COLUMNS
    report_label = "SERVIÇOS PRESTADOS" if is_prestados else "SERVIÇOS TOMADOS"
    sheet_name = "Serviços Prestados" if is_prestados else "Serviços Tomados"

    temp_file = NamedTemporaryFile(delete=False, suffix=".xlsx")
    temp_file.close()
    output_path = Path(temp_file.name)

    workbook = Workbook(write_only=True)
    workbook.calculation.calcMode = "auto"
    workbook.calculation.calcOnSave = True
    workbook.calculation.forceFullCalc = True

    summary_sheet = workbook.create_sheet("Resumo")
    sheet = workbook.create_sheet(sheet_name)
    sheet.sheet_view.showGridLines = False
    sheet.freeze_panes = "E9"
    sheet.sheet_properties.tabColor = ACCENT_COLOR

    for index, column in enumerate(columns, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = column.width
    sheet.row_dimensions[1].height = 32
    sheet.row_dimensions[2].height = 22
    sheet.row_dimensions[4].height = 21
    sheet.row_dimensions[5].height = 30
    sheet.row_dimensions[6].height = 22
    sheet.row_dimensions[8].height = 42

    header_row = 8
    first_data_row = header_row + 1
    last_data_row = header_row + max(1, len(documents))
    last_column = get_column_letter(len(columns))
    service_amount_column = _column_letter(columns, "valor_servicos")
    iss_amount_column = _column_letter(columns, "valor_iss")

    company_name = str(company.get("legal_name") or "Empresa")
    company_cnpj = _format_tax_id(str(company.get("cnpj") or ""))
    filters = [
        f"Período: {_format_date(data_inicial)} a {_format_date(data_final)}",
        f"Tipo: {'Prestados' if is_prestados else 'Tomados'}",
    ]
    if situacao and situacao != "todas":
        filters.append(f"Situação: {situacao.capitalize()}")
    if query:
        filters.append(f"Pesquisa: {query}")

    _append_dashboard(
        summary_sheet,
        company_name=company_name,
        company_cnpj=company_cnpj,
        report_label=report_label,
        filters=filters,
        detail_sheet_name=sheet_name,
        columns=columns,
        first_data_row=first_data_row,
        last_data_row=last_data_row,
        has_rows=has_rows,
        is_prestados=is_prestados,
    )

    _append_title_row(sheet, len(columns), f"RELATÓRIO DE {report_label}")
    _append_info_row(sheet, len(columns), f"{company_name}  •  CNPJ {company_cnpj}")
    sheet.append([None] * len(columns))

    summary_labels = ["Notas", "Autorizadas", "Canceladas", "Valor dos serviços", "Valor do ISS"]
    summary_values: list[object] = [
        _summary_formula(f'=SUBTOTAL(103,A{first_data_row}:A{last_data_row})', has_rows),
        _summary_formula(
            f'=COUNTIF(B{first_data_row}:B{last_data_row},"Autorizada")',
            has_rows,
        ),
        _summary_formula(
            f'=COUNTIF(B{first_data_row}:B{last_data_row},"Cancelada")',
            has_rows,
        ),
        _summary_formula(
            f"=SUBTOTAL(109,{service_amount_column}{first_data_row}:"
            f"{service_amount_column}{last_data_row})",
            has_rows,
        ),
        _summary_formula(
            f"=SUBTOTAL(109,{iss_amount_column}{first_data_row}:"
            f"{iss_amount_column}{last_data_row})",
            has_rows,
        ),
    ]
    _append_summary_row(sheet, len(columns), summary_labels, values=False)
    _append_summary_row(sheet, len(columns), summary_values, values=True)

    _append_filter_row(sheet, len(columns), "  •  ".join(filters))
    sheet.append([None] * len(columns))
    _append_header_row(sheet, columns)

    if has_rows:
        for row_index, document in enumerate(documents, start=first_data_row):
            item = _report_row(document)
            _append_data_row(sheet, columns, item, alternate=(row_index % 2 == 0))
    else:
        _append_empty_row(sheet, len(columns))

    _append_total_row(sheet, columns, first_data_row, last_data_row, has_rows)

    sheet.auto_filter.ref = f"A{header_row}:{last_column}{last_data_row}"
    sheet.print_title_rows = f"{header_row}:{header_row}"
    sheet.print_options.horizontalCentered = False
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToWidth = 3
    sheet.page_setup.fitToHeight = 0
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.oddFooter.center.text = "Página &P de &N"
    sheet.oddFooter.right.text = datetime.now().strftime("Gerado em %d/%m/%Y %H:%M")

    workbook.save(output_path)
    return output_path


def _report_row(document: dict[str, object]) -> ReportRow:
    fallback = _fallback_row(document)
    xml_path = document.get("xml_path")
    if not isinstance(xml_path, str) or not Path(xml_path).is_file():
        return fallback
    try:
        data = parse_danfse(xml_path)
    except (ET.ParseError, InvalidNFSeXmlError, OSError, ValueError):
        return fallback

    national_code, municipal_code = _split_taxation_code(data.service.taxation_code)
    ibs_uf_rate, ibs_municipal_rate = _split_rates(data.ibs_cbs_taxation.ibs_rates)
    return ReportRow(
        numero=_present(data.header.nfse_number, fallback.numero),
        situacao=fallback.situacao,
        chave_acesso=_present(data.header.access_key, fallback.chave_acesso),
        data_emissao=fallback.data_emissao or _parse_datetime(data.header.dps_issued_at),
        prestador_cnpj=_blank_if_missing(data.provider.tax_id),
        prestador_razao_social=_blank_if_missing(data.provider.name),
        tomador_cnpj=_blank_if_missing(data.customer.tax_id),
        tomador_razao_social=_blank_if_missing(data.customer.name),
        codigo_tributacao_nacional=national_code,
        codigo_tributacao_municipal=municipal_code,
        descricao_tributacao=_blank_if_missing(data.service.taxation_description),
        descricao_servico=_blank_if_missing(data.service.service_description),
        codigo_nbs=_blank_if_missing(data.service.nbs_code),
        valor_servicos=_decimal_with_fallback(
            data.total.service_amount,
            fallback.valor_servicos,
        ),
        aliquota_iss=_percentage_or_none(data.municipal_taxation.applied_rate),
        base_calculo_iss=_decimal_or_none(data.municipal_taxation.issqn_base),
        valor_iss=_decimal_or_none(data.municipal_taxation.issqn_amount),
        retencao_iss=_blank_if_missing(data.municipal_taxation.retention),
        irrf_retido=_decimal_or_none(data.federal_taxation.irrf),
        csll_retida=_decimal_or_none(data.federal_taxation.sociais_retidas),
        contribuicao_previdenciaria_retida=_decimal_or_none(
            data.federal_taxation.previdenciaria_retida
        ),
        aliquota_ibs_uf=_percentage_or_none(ibs_uf_rate),
        aliquota_ibs_municipal=_percentage_or_none(ibs_municipal_rate),
        aliquota_cbs=_percentage_or_none(data.ibs_cbs_taxation.cbs_rate),
        valor_ibs=_decimal_or_none(data.ibs_cbs_taxation.ibs_total),
        valor_cbs=_decimal_or_none(data.ibs_cbs_taxation.cbs_total),
        ajuste_ibs=_decimal_or_none(data.ibs_cbs_taxation.adjustment_ibs),
        ajuste_cbs=_decimal_or_none(data.ibs_cbs_taxation.adjustment_cbs),
        pis_debito=_decimal_or_none(data.federal_taxation.pis_debito),
        cofins_debito=_decimal_or_none(data.federal_taxation.cofins_debito),
        valor_liquido=_decimal_with_fallback(
            data.total.nfse_net_amount,
            fallback.valor_liquido,
        ),
        finalidade_nfse=_blank_if_missing(data.header.purpose),
        tipo_debito=_blank_if_missing(data.header.debit_note_type),
        tipo_credito=_blank_if_missing(data.header.credit_note_type),
    )


def _fallback_row(document: dict[str, object]) -> ReportRow:
    return ReportRow(
        numero=str(document.get("note_number") or document.get("access_key") or "-"),
        situacao=str(document.get("status") or "Autorizada"),
        chave_acesso=str(document.get("access_key") or "-"),
        data_emissao=_parse_datetime(document.get("issued_at")),
        prestador_cnpj="",
        prestador_razao_social=str(document.get("issuer_name") or ""),
        tomador_cnpj="",
        tomador_razao_social=str(document.get("customer_name") or ""),
        codigo_tributacao_nacional="",
        codigo_tributacao_municipal="",
        descricao_tributacao="",
        descricao_servico="",
        codigo_nbs="",
        valor_servicos=_decimal_or_none(document.get("service_amount")),
        aliquota_iss=None,
        base_calculo_iss=None,
        valor_iss=None,
        retencao_iss="",
        irrf_retido=None,
        csll_retida=None,
        contribuicao_previdenciaria_retida=None,
        aliquota_ibs_uf=None,
        aliquota_ibs_municipal=None,
        aliquota_cbs=None,
        valor_ibs=None,
        valor_cbs=None,
        ajuste_ibs=None,
        ajuste_cbs=None,
        pis_debito=None,
        cofins_debito=None,
        valor_liquido=_decimal_or_none(document.get("net_amount")),
        finalidade_nfse="",
        tipo_debito="",
        tipo_credito="",
    )


def _append_dashboard(
    sheet,
    *,
    company_name: str,
    company_cnpj: str,
    report_label: str,
    filters: list[str],
    detail_sheet_name: str,
    columns: tuple[ReportColumn, ...],
    first_data_row: int,
    last_data_row: int,
    has_rows: bool,
    is_prestados: bool,
) -> None:
    sheet.sheet_view.showGridLines = False
    sheet.sheet_view.zoomScale = 90
    sheet.freeze_panes = "A6"
    sheet.sheet_properties.tabColor = TITLE_COLOR
    for column in ("A", "B", "C"):
        sheet.column_dimensions[column].width = 30
    sheet.row_dimensions[1].height = 34
    sheet.row_dimensions[2].height = 23
    sheet.row_dimensions[4].height = 24
    for row in (6, 10, 14, 18):
        sheet.row_dimensions[row].height = 24
    for row in (8, 12, 16, 20):
        sheet.row_dimensions[row].height = 31
    sheet.row_dimensions[22].height = 46

    _append_title_row(sheet, 3, f"RESUMO DE {report_label}")
    _append_info_row(sheet, 3, f"{company_name}  •  CNPJ {company_cnpj}")
    sheet.append([None, None, None])
    _append_filter_row(sheet, 3, "  •  ".join(filters))
    sheet.append([None, None, None])

    _append_dashboard_section(sheet, "DOCUMENTOS")
    _append_dashboard_metrics(
        sheet,
        [
            SummaryMetric(
                "Notas no relatório",
                _detail_formula(
                    f"COUNTA('{detail_sheet_name}'!A{first_data_row}:A{last_data_row})",
                    has_rows,
                ),
            ),
            SummaryMetric(
                "Autorizadas",
                _detail_formula(
                    f'COUNTIF(\'{detail_sheet_name}\'!B{first_data_row}:B{last_data_row},'
                    '"Autorizada")',
                    has_rows,
                ),
            ),
            SummaryMetric(
                "Canceladas",
                _detail_formula(
                    f'COUNTIF(\'{detail_sheet_name}\'!B{first_data_row}:B{last_data_row},'
                    '"Cancelada")',
                    has_rows,
                ),
            ),
        ],
    )
    sheet.append([None, None, None])

    _append_dashboard_section(sheet, "VALORES DA NFS-e")
    _append_dashboard_metrics(
        sheet,
        [
            _sum_metric(
                "Valor dos serviços",
                detail_sheet_name,
                columns,
                "valor_servicos",
                first_data_row,
                last_data_row,
                has_rows,
            ),
            _sum_metric(
                "Base de cálculo do ISS",
                detail_sheet_name,
                columns,
                "base_calculo_iss",
                first_data_row,
                last_data_row,
                has_rows,
            ),
            _sum_metric(
                "Valor líquido",
                detail_sheet_name,
                columns,
                "valor_liquido",
                first_data_row,
                last_data_row,
                has_rows,
            ),
        ],
    )
    sheet.append([None, None, None])

    _append_dashboard_section(sheet, "TRIBUTOS")
    _append_dashboard_metrics(
        sheet,
        [
            _sum_metric(
                "Valor do ISS",
                detail_sheet_name,
                columns,
                "valor_iss",
                first_data_row,
                last_data_row,
                has_rows,
            ),
            _sum_metric(
                "Valor IBS",
                detail_sheet_name,
                columns,
                "valor_ibs",
                first_data_row,
                last_data_row,
                has_rows,
            ),
            _sum_metric(
                "Valor CBS",
                detail_sheet_name,
                columns,
                "valor_cbs",
                first_data_row,
                last_data_row,
                has_rows,
            ),
        ],
    )
    sheet.append([None, None, None])

    _append_dashboard_section(
        sheet,
        "APURAÇÃO PRÓPRIA" if is_prestados else "RETENÇÕES FEDERAIS",
    )
    if is_prestados:
        extra_metrics = [
            _sum_metric(
                "PIS – débito/apuração própria",
                detail_sheet_name,
                columns,
                "pis_debito",
                first_data_row,
                last_data_row,
                has_rows,
            ),
            _sum_metric(
                "COFINS – débito/apuração própria",
                detail_sheet_name,
                columns,
                "cofins_debito",
                first_data_row,
                last_data_row,
                has_rows,
            ),
            SummaryMetric(
                "Total PIS + COFINS",
                "=SUM(A20:B20)" if has_rows else 0,
                "currency",
            ),
        ]
    else:
        extra_metrics = [
            _sum_metric(
                label,
                detail_sheet_name,
                columns,
                field,
                first_data_row,
                last_data_row,
                has_rows,
            )
            for label, field in (
                ("IRRF retido", "irrf_retido"),
                ("CSLL retida", "csll_retida"),
                (
                    "Contribuição previdenciária retida",
                    "contribuicao_previdenciaria_retida",
                ),
            )
        ]
    _append_dashboard_metrics(sheet, extra_metrics)
    sheet.append([None, None, None])

    detail_notes = (
        [
            "Abra a aba Serviços Prestados para consultar cada NFS-e.",
            "Códigos nacional/municipal, descrição do serviço e NBS.",
            "Alíquotas e valores de ISS, IBS, CBS, PIS e COFINS.",
        ]
        if is_prestados
        else [
            "Abra a aba Serviços Tomados para consultar cada NFS-e.",
            "Chave, CNPJ, razão social do prestador e data de emissão.",
            "Códigos tributários, descrição do serviço, valores e retenções.",
        ]
    )
    _append_dashboard_note(sheet, detail_notes)

    sheet.print_area = "A1:C26"
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 1
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.oddFooter.center.text = "Página &P de &N"
    sheet.oddFooter.right.text = datetime.now().strftime("Gerado em %d/%m/%Y %H:%M")


def _append_dashboard_section(sheet, title: str) -> None:
    cells = []
    for index in range(3):
        cell = WriteOnlyCell(sheet, value=title if index == 0 else None)
        cell.fill = PatternFill("solid", fgColor=ACCENT_COLOR)
        cell.font = Font(name="Aptos", size=10, bold=True, color="FFFFFF")
        cell.alignment = Alignment(vertical="center")
        cells.append(cell)
    sheet.append(cells)


def _append_dashboard_metrics(sheet, metrics: list[SummaryMetric]) -> None:
    labels = []
    values = []
    border_color = Side(style="thin", color="99F6E4")
    for index in range(3):
        metric = metrics[index] if index < len(metrics) else None
        label_cell = WriteOnlyCell(sheet, value=metric.label if metric else None)
        value_cell = WriteOnlyCell(sheet, value=metric.value if metric else None)
        if metric:
            label_cell.fill = PatternFill("solid", fgColor="F0FDFA")
            label_cell.border = Border(top=border_color)
            label_cell.font = Font(name="Aptos", size=9, bold=True, color=MUTED_COLOR)
            label_cell.alignment = Alignment(vertical="center", wrap_text=True)

            value_cell.fill = PatternFill("solid", fgColor=ACCENT_LIGHT)
            value_cell.border = Border(bottom=border_color)
            value_cell.font = Font(name="Aptos Display", size=16, bold=True, color=ACCENT_COLOR)
            value_cell.alignment = Alignment(vertical="center")
            value_cell.number_format = MONEY_FORMAT if metric.kind == "currency" else "#,##0"
        labels.append(label_cell)
        values.append(value_cell)
    sheet.append(labels)
    sheet.append(values)


def _append_dashboard_note(sheet, notes: list[str]) -> None:
    cells = []
    for index in range(3):
        cell = WriteOnlyCell(sheet, value=notes[index])
        cell.fill = PatternFill("solid", fgColor="E2E8F0")
        cell.font = Font(name="Aptos", size=9, italic=True, color=TEXT_COLOR)
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        cells.append(cell)
    sheet.append(cells)


def _sum_metric(
    label: str,
    sheet_name: str,
    columns: tuple[ReportColumn, ...],
    field: str,
    first_data_row: int,
    last_data_row: int,
    has_rows: bool,
) -> SummaryMetric:
    column = _column_letter(columns, field)
    return SummaryMetric(
        label,
        _detail_formula(
            f"SUM('{sheet_name}'!{column}{first_data_row}:{column}{last_data_row})",
            has_rows,
        ),
        "currency",
    )


def _detail_formula(expression: str, has_rows: bool) -> object:
    return f"={expression}" if has_rows else 0


def _append_title_row(sheet, column_count: int, title: str) -> None:
    cells = []
    for index in range(column_count):
        cell = WriteOnlyCell(sheet, value=title if index == 0 else None)
        cell.fill = PatternFill("solid", fgColor=TITLE_COLOR)
        cell.font = Font(
            name="Aptos Display",
            size=17 if index == 0 else 11,
            bold=True,
            color="FFFFFF",
        )
        cell.alignment = Alignment(vertical="center")
        cells.append(cell)
    sheet.append(cells)


def _append_info_row(sheet, column_count: int, text: str) -> None:
    cells = []
    for index in range(column_count):
        cell = WriteOnlyCell(sheet, value=text if index == 0 else None)
        cell.fill = PatternFill("solid", fgColor="E2E8F0")
        cell.font = Font(name="Aptos", size=10, bold=index == 0, color=TEXT_COLOR)
        cell.alignment = Alignment(vertical="center")
        cells.append(cell)
    sheet.append(cells)


def _append_summary_row(sheet, column_count: int, items: list[object], *, values: bool) -> None:
    cells = []
    thin = Side(style="thin", color="99F6E4")
    for index in range(column_count):
        item_index = index
        value = items[item_index] if item_index < len(items) else None
        cell = WriteOnlyCell(sheet, value=value)
        if index < len(items):
            cell.fill = PatternFill("solid", fgColor=ACCENT_LIGHT if values else "F0FDFA")
            cell.border = Border(
                top=thin if not values else Side(style=None),
                bottom=thin if values else Side(style=None),
            )
        cell.font = Font(
            name="Aptos",
            size=10 if values else 9,
            bold=True,
            color=ACCENT_COLOR if values else MUTED_COLOR,
        )
        cell.alignment = Alignment(vertical="center")
        if values and item_index >= 3:
            cell.number_format = MONEY_FORMAT
        cells.append(cell)
    sheet.append(cells)


def _append_filter_row(sheet, column_count: int, text: str) -> None:
    cells = []
    for index in range(column_count):
        cell = WriteOnlyCell(sheet, value=text if index == 0 else None)
        cell.font = Font(name="Aptos", size=9, italic=True, color=MUTED_COLOR)
        cell.alignment = Alignment(vertical="center")
        cells.append(cell)
    sheet.append(cells)


def _append_header_row(sheet, columns: tuple[ReportColumn, ...]) -> None:
    cells = []
    border = Border(bottom=Side(style="medium", color="134E4A"))
    for column in columns:
        cell = WriteOnlyCell(sheet, value=column.title)
        cell.fill = PatternFill("solid", fgColor=ACCENT_COLOR)
        cell.font = Font(name="Aptos", size=9, bold=True, color="FFFFFF")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border
        cells.append(cell)
    sheet.append(cells)


def _append_data_row(
    sheet,
    columns: tuple[ReportColumn, ...],
    item: ReportRow,
    *,
    alternate: bool,
) -> None:
    cells = []
    cancelled = item.situacao.lower() == "cancelada"
    for column in columns:
        value = getattr(item, column.field)
        if isinstance(value, Decimal):
            value = float(value)
        cell = WriteOnlyCell(sheet, value=value)
        cell.font = Font(
            name="Aptos",
            size=9,
            color=CANCELLED_COLOR if cancelled and column.field == "situacao" else TEXT_COLOR,
            bold=cancelled and column.field == "situacao",
        )
        if cancelled and column.field == "situacao":
            cell.fill = PatternFill("solid", fgColor=CANCELLED_LIGHT)
        elif alternate:
            cell.fill = PatternFill("solid", fgColor=ROW_ALT_COLOR)
        cell.alignment = Alignment(
            horizontal="right" if column.kind in {"currency", "percent"} else "left",
            vertical="center",
        )
        if column.kind == "currency":
            cell.number_format = MONEY_FORMAT
        elif column.kind == "percent":
            cell.number_format = PERCENT_FORMAT
        elif column.kind == "date":
            cell.number_format = DATE_FORMAT
        cells.append(cell)
    sheet.append(cells)


def _append_empty_row(sheet, column_count: int) -> None:
    cells = []
    for index in range(column_count):
        cell = WriteOnlyCell(
            sheet,
            value="Nenhuma nota encontrada para os filtros informados." if index == 0 else None,
        )
        cell.font = Font(name="Aptos", size=10, italic=True, color=MUTED_COLOR)
        cells.append(cell)
    sheet.append(cells)


def _append_total_row(
    sheet,
    columns: tuple[ReportColumn, ...],
    first_data_row: int,
    last_data_row: int,
    has_rows: bool,
) -> None:
    cells = []
    border = Border(top=Side(style="medium", color=ACCENT_COLOR))
    for index, column in enumerate(columns, start=1):
        if index == 1:
            value: object = "TOTAL GERAL"
        elif column.kind == "currency":
            letter = get_column_letter(index)
            value = (
                f"=SUBTOTAL(109,{letter}{first_data_row}:{letter}{last_data_row})"
                if has_rows
                else 0
            )
        else:
            value = None
        cell = WriteOnlyCell(sheet, value=value)
        cell.fill = PatternFill("solid", fgColor=ACCENT_LIGHT)
        cell.font = Font(name="Aptos", size=9, bold=True, color="134E4A")
        cell.border = border
        cell.alignment = Alignment(
            horizontal="right" if column.kind == "currency" else "left",
            vertical="center",
        )
        if column.kind == "currency":
            cell.number_format = MONEY_FORMAT
        cells.append(cell)
    sheet.append(cells)


def _split_taxation_code(value: str) -> tuple[str, str]:
    if not value or value == MISSING_VALUE:
        return "", ""
    national, separator, municipal = value.partition(" / ")
    return national, municipal if separator else ""


def _split_rates(value: str) -> tuple[str, str]:
    if not value or value == MISSING_VALUE:
        return "", ""
    state, separator, municipal = value.partition(" / ")
    return state, municipal if separator else ""


def _present(value: str, fallback: str) -> str:
    return fallback if not value or value == MISSING_VALUE else value


def _blank_if_missing(value: str) -> str:
    return "" if not value or value == MISSING_VALUE else value


def _decimal_or_none(value: object) -> Decimal | None:
    if value is None or value == "" or value == MISSING_VALUE:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _percentage_or_none(value: object) -> Decimal | None:
    decimal = _decimal_or_none(value)
    return decimal / Decimal("100") if decimal is not None else None


def _decimal_with_fallback(value: object, fallback: Decimal | None) -> Decimal | None:
    decimal = _decimal_or_none(value)
    return fallback if decimal is None else decimal


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if not value:
        return None
    normalized = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).replace(tzinfo=None)
    except ValueError:
        try:
            return datetime.strptime(normalized, "%d/%m/%Y %H:%M:%S")
        except ValueError:
            return None


def _format_date(value: str) -> str:
    return datetime.strptime(value, "%Y-%m-%d").strftime("%d/%m/%Y")


def _format_tax_id(value: str) -> str:
    identifier = "".join(character for character in value if character.isalnum()).upper()
    if len(identifier) != 14 or not identifier.isdigit():
        return identifier or "-"
    return (
        f"{identifier[:2]}.{identifier[2:5]}.{identifier[5:8]}/"
        f"{identifier[8:12]}-{identifier[12:]}"
    )


def _column_letter(columns: tuple[ReportColumn, ...], field: str) -> str:
    index = next(index for index, column in enumerate(columns, start=1) if column.field == field)
    return get_column_letter(index)


def _summary_formula(formula: str, has_rows: bool) -> object:
    return formula if has_rows else 0

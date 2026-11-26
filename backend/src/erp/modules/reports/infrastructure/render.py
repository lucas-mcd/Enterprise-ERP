import csv
import io
from importlib.resources import files
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from collections.abc import Iterator
from decimal import Decimal
from typing import Any
from xml.sax.saxutils import escape
from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

pdfmetrics.registerFont(TTFont("ERP", str(files("reportlab") / "fonts" / "Vera.ttf")))
pdfmetrics.registerFont(
    TTFont("ERP-Bold", str(files("reportlab") / "fonts" / "VeraBd.ttf"))
)

COLUMNS = [
    "Descrição",
    "Contraparte",
    "Categoria",
    "Tipo",
    "Status",
    "Data de caixa",
    "Valor BRL",
]


def safe(value: str) -> str:
    # Prevent spreadsheet formula injection, including whitespace-prefixed cells.
    return (
        "'" + value
        if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r"))
        else value
    )


def cells(row: dict[str, Any]) -> list[str]:
    return [
        str(row[k] or "")
        for k in (
            "description",
            "counterparty",
            "category",
            "kind",
            "status",
            "effective_on",
            "amount",
        )
    ]


def csv_chunks(rows: list[dict[str, Any]]) -> Iterator[bytes]:
    yield b"\xef\xbb\xbf"
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    for values in [COLUMNS, *[cells(row) for row in rows]]:
        buffer.seek(0)
        buffer.truncate(0)
        writer.writerow([safe(v) for v in values])
        yield buffer.getvalue().encode("utf-8")


def xlsx_file(rows: list[dict[str, Any]]) -> bytes:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = "Fluxo de caixa"
    sheet.append(COLUMNS)
    for row in rows:
        sheet.append([safe(v) for v in cells(row)])
        sheet.cell(sheet.max_row, 7, Decimal(str(row["amount"])))
        sheet.cell(sheet.max_row, 7).number_format = "#,##0.00"
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for col in ("A", "B"):
        sheet.column_dimensions[col].width = 36
    for col in ("C", "D", "E", "F", "G"):
        sheet.column_dimensions[col].width = 21
    target = io.BytesIO()
    book.save(target)
    return target.getvalue()


def brl(value: str) -> str:
    return "R$ " + f"{Decimal(value):,.2f}".replace(",", "_").replace(".", ",").replace(
        "_", "."
    )


def pdf_file(
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
    logs: list[dict[str, Any]],
    metadata: str,
) -> bytes:
    stream = io.BytesIO()
    styles = getSampleStyleSheet()
    for name in ("BodyText", "Normal"):
        styles[name].fontName = "ERP"
        styles[name].fontSize = 9
        styles[name].leading = 13
    for name in ("Title", "Heading2"):
        styles[name].fontName = "ERP-Bold"
    doc = SimpleDocTemplate(
        stream,
        pagesize=(21 * cm, 29.7 * cm),
        rightMargin=1.4 * cm,
        leftMargin=1.4 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    def text(value: str) -> Paragraph:
        return Paragraph(escape(value), styles["BodyText"])

    content: list[Any] = [
        Paragraph("Enterprise ERP | Fluxo de caixa", styles["Title"]),
        text(metadata),
        Spacer(1, 12),
    ]
    for title, key in [
        ("Receitas realizadas", "income"),
        ("Despesas realizadas", "expense"),
        ("Resultado (sem saldo inicial)", "net"),
        ("A receber", "pending_income"),
        ("A pagar", "pending_expense"),
    ]:
        content.append(text(title + ": " + brl(str(summary[key]))))
    content.extend(
        [
            Spacer(1, 12),
            text(
                f"Lançamentos: {len(rows)}. Valores em reais. Previsto usa "
                f"vencimento; realizado usa liquidação."
            ),
            Spacer(1, 12),
        ]
    )
    table = [
        [text(v) for v in ["Descrição / contraparte", "Data", "Tipo / status", "Valor"]]
    ]
    for row in rows:
        table.append(
            [
                text(str(row["description"]) + " / " + str(row["counterparty"])),
                text(str(row["effective_on"])),
                text(str(row["kind"]) + " / " + str(row["status"])),
                text(brl(str(row["amount"]))),
            ]
        )
    grid = Table(
        table,
        colWidths=[7.5 * cm, 2.5 * cm, 4.2 * cm, 3.8 * cm],
        repeatRows=1,
        hAlign="LEFT",
    )
    grid.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0e7ff")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    content.append(grid)
    if logs:
        content.extend(
            [
                Spacer(1, 18),
                Paragraph("Auditoria dos lançamentos selecionados", styles["Heading2"]),
                text(
                    "Até 100 eventos mais recentes; metadados apenas, sem "
                    "payloads sensíveis."
                ),
            ]
        )
        for log in logs:
            content.append(
                text(
                    f"{log['occurred_at']} | {log['operation']} | "
                    f"{log['entity_id']} | autor {log['actor_id']}"
                )
            )

    def footer(canvas: Any, document: Any) -> None:
        canvas.setFont("ERP", 8)
        canvas.drawString(1.4 * cm, 0.8 * cm, "Enterprise ERP - relatório gerencial")
        canvas.drawRightString(19.6 * cm, 0.8 * cm, str(document.page))

    doc.build(content, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()


def grid_file(
    headers: list[str],
    rows: list[list[str]],
    format: str,
    numeric_columns: set[int] | None = None,
) -> bytes:
    """Bounded tabular export; all untrusted cells stay text, never formulas."""
    if format == "csv":
        stream = io.StringIO()
        writer = csv.writer(stream, delimiter=";")
        writer.writerows([[safe(value) for value in row] for row in [headers, *rows]])
        return b"\xef\xbb\xbf" + stream.getvalue().encode("utf-8")
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append(headers)
    for row in rows:
        sheet.append([safe(value) for value in row])
        for index in numeric_columns or set():
            sheet.cell(sheet.max_row, index + 1, Decimal(row[index]))
            sheet.cell(sheet.max_row, index + 1).number_format = "#,##0.00"
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    stream_bytes = io.BytesIO()
    book.save(stream_bytes)
    return stream_bytes.getvalue()

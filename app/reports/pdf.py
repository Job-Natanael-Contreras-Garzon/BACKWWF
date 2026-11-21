"""PDF del reporte (§11) con reportlab (D9): portada, totales, barras de las 15 especies, géneros y
familias principales, tablas y pie con página y ``request_id``.

El diseño (colores, fuentes, logo) sale de ``brand.BRAND``; acá solo está la estructura.
"""

import io
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from reportlab.graphics.charts.barcharts import HorizontalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.flowables import Flowable

from app.reports.brand import ASSETS, BRAND, Brand

MARGIN = 2 * cm
TOP = 15


@dataclass
class PdfContent:
    """Lo que el servicio arma para el PDF; el diseño se aplica acá."""

    scope_line: str
    filters_line: str
    generated_line: str
    model_line: str
    totals: list[tuple[str, str]]
    effort_line: str | None
    species: list[tuple[str, int]]
    genera: list[tuple[str, int]]
    families: list[tuple[str, int]]
    species_table: list[list[str]] = field(default_factory=list)
    family_table: list[list[str]] = field(default_factory=list)


def _register_fonts(brand: Brand) -> None:
    for name, file_name in brand.font_files:
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(ASSETS / file_name)))


def _styles(brand: Brand) -> dict[str, ParagraphStyle]:
    text = colors.HexColor(brand.text)
    muted = colors.HexColor(brand.muted)
    return {
        "title": ParagraphStyle(
            "title",
            fontName=brand.font_bold,
            fontSize=22,
            leading=27,
            textColor=text,
            spaceAfter=10,
        ),
        "subtitle": ParagraphStyle(
            "subtitle", fontName=brand.font, fontSize=14, leading=18, textColor=text, spaceAfter=6
        ),
        "meta": ParagraphStyle(
            "meta", fontName=brand.font, fontSize=10.5, leading=14, textColor=muted
        ),
        "h2": ParagraphStyle(
            "h2",
            fontName=brand.font_bold,
            fontSize=14,
            leading=18,
            textColor=text,
            spaceBefore=12,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "body", fontName=brand.font, fontSize=10, leading=13, textColor=text
        ),
    }


def _table(
    headers: Sequence[str], rows: Sequence[Sequence[str]], widths: list[float], brand: Brand
) -> Table:
    table = Table([list(headers), *[list(r) for r in rows]], colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, 0), brand.font_bold, 9),
                ("FONT", (0, 1), (-1, -1), brand.font, 8.5),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(brand.primary_light)),
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor(brand.primary)),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def _bars(items: list[tuple[str, int]], brand: Brand) -> Drawing:
    """Barras horizontales medidas desde cero, la más grande arriba."""
    width = A4[0] - 2 * MARGIN
    row = 16
    height = row * len(items) + 20
    drawing = Drawing(width, height)
    chart = HorizontalBarChart()
    chart.x, chart.y = 150, 10
    chart.width, chart.height = width - 190, row * len(items)
    chart.data = [[v for _, v in reversed(items)]]
    chart.categoryAxis.categoryNames = [label[:32] for label, _ in reversed(items)]
    chart.categoryAxis.labels.fontName = brand.font
    chart.categoryAxis.labels.fontSize = 8
    chart.categoryAxis.labels.dx = -4
    chart.categoryAxis.labels.textAnchor = "end"
    chart.valueAxis.valueMin = 0
    chart.valueAxis.labels.fontName = brand.font
    chart.valueAxis.labels.fontSize = 7
    chart.bars[0].fillColor = colors.HexColor(brand.primary)
    chart.bars[0].strokeColor = None
    chart.barLabelFormat = "%d"
    chart.barLabels.fontName = brand.font
    chart.barLabels.fontSize = 7
    chart.barLabels.boxAnchor = "w"
    chart.barLabels.dx = 3
    drawing.add(chart)
    return drawing


def _numbered_canvas(footer: str, brand: Brand) -> type[Canvas]:
    """Canvas que conoce el total de páginas para escribir "Página n de N"."""

    class NumberedCanvas(Canvas):  # type: ignore[misc]  # reportlab no publica tipos
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self._pages: list[dict[str, Any]] = []

        def showPage(self) -> None:  # noqa: N802 - API de reportlab
            self._pages.append(dict(self.__dict__))
            self._startPage()

        def save(self) -> None:
            total = len(self._pages)
            for state in self._pages:
                self.__dict__.update(state)
                self.setFont(brand.font, 8)
                self.setFillColor(colors.HexColor(brand.muted))
                parts = [f"Página {self._pageNumber} de {total}", footer]
                if brand.organization:
                    parts.append(brand.organization)
                self.drawString(MARGIN, 1.2 * cm, " · ".join(p for p in parts if p))
                super().showPage()
            super().save()

    return NumberedCanvas


def build(content: PdfContent, footer: str, brand: Brand = BRAND) -> bytes:
    _register_fonts(brand)
    st = _styles(brand)
    story: list[Flowable] = []
    logo = brand.logo_path
    if logo is not None:
        image = Image(str(logo))
        ratio = image.imageHeight / image.imageWidth
        image.drawWidth = brand.logo_width_cm * cm
        image.drawHeight = brand.logo_width_cm * cm * ratio
        image.hAlign = "LEFT"
        story += [image, Spacer(1, 1.5 * cm)]
    else:
        story.append(Spacer(1, 4 * cm))
    story += [
        Paragraph(brand.title, st["title"]),
        Paragraph(content.scope_line, st["subtitle"]),
        Paragraph(content.filters_line, st["meta"]),
        Paragraph(content.generated_line, st["meta"]),
        Paragraph(content.model_line, st["meta"]),
        Spacer(1, 1 * cm),
        Paragraph("Totales", st["h2"]),
        _table(
            ["Indicador", "Valor"], [[k, v] for k, v in content.totals], [9 * cm, 4 * cm], brand
        ),
    ]
    if content.effort_line:
        story += [Spacer(1, 6), Paragraph(content.effort_line, st["body"])]
    story.append(PageBreak())
    for title, items in (
        (f"Especies con más avistamientos (top {TOP})", content.species),
        (f"Géneros (top {TOP})", content.genera),
        (f"Familias (top {TOP})", content.families),
    ):
        if items:
            story += [Paragraph(title, st["h2"]), _bars(items[:TOP], brand)]
    story += [
        Paragraph("Por especie", st["h2"]),
        _table(
            ["Especie", "Nombre común", "Avist.", "%", "Valid."],
            content.species_table,
            [5.2 * cm, 5.2 * cm, 1.8 * cm, 1.6 * cm, 1.6 * cm],
            brand,
        ),
        Paragraph("Por familia", st["h2"]),
        _table(
            ["Familia", "Avist.", "%"], content.family_table, [8 * cm, 2.5 * cm, 2.5 * cm], brand
        ),
    ]
    out = io.BytesIO()
    doc = SimpleDocTemplate(
        out,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        title=brand.title,
        author=brand.organization or "WWM",
    )
    doc.build(story, canvasmaker=_numbered_canvas(footer, brand))
    return out.getvalue()

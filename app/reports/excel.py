"""Excel de 5 hojas (§11) con ``openpyxl``.

S4 (inyección de fórmulas): todo texto que empiece con ``= + - @``, tabulación o retorno de carro
se escribe con un apóstrofo delante, así Excel lo muestra como texto y no lo ejecuta.
"""

import io
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

_DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def safe(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(_DANGEROUS):
        return "'" + value
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)  # Excel no admite zonas: va en UTC
    return value


def _sheet(wb: Workbook, title: str, headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> None:
    ws = wb.create_sheet(title)
    ws.append(list(headers))
    for cell in ws[1]:
        cell.font = Font(bold=True)
    widths = [len(h) for h in headers]
    for row in rows:
        values = [safe(v) for v in row]
        ws.append(values)
        for i, v in enumerate(values):
            widths[i] = max(widths[i], min(len(str(v)) if v is not None else 0, 60))
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width + 2
    ws.freeze_panes = "A2"


def build(sheets: Sequence[tuple[str, Sequence[str], Sequence[Sequence[Any]]]]) -> bytes:
    wb = Workbook()
    if wb.active is not None:
        wb.remove(wb.active)
    for title, headers, rows in sheets:
        _sheet(wb, title, headers, rows)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()

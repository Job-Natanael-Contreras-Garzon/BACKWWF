"""PDF mínimo escrito a mano (PDF 1.4, fuentes estándar Helvetica, sin dependencias).

Solo lo que pide §11: texto, tablas simples y barras horizontales. Las fuentes estándar usan
``WinAnsiEncoding``, así que las tildes y la ñ salen bien; lo que no entra en Latin-1 se reemplaza
por ``?``.
"""

from dataclasses import dataclass, field

PAGE_W, PAGE_H = 595.0, 842.0  # A4 en puntos
MARGIN = 50.0
_CHAR_W = 0.5  # ancho medio de Helvetica en "em": alcanza para recortar textos largos


def _escape(text: str) -> str:
    safe = text.encode("latin-1", "replace").decode("latin-1")
    return safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def fit(text: str, width: float, size: float) -> str:
    """Recorta con "…" lo que no entra en ``width`` puntos."""
    max_chars = int(width / (size * _CHAR_W))
    return text if len(text) <= max_chars else text[: max(max_chars - 1, 1)] + "..."


@dataclass
class Pdf:
    footer: str = ""
    pages: list[list[str]] = field(default_factory=list)
    y: float = 0.0

    def new_page(self) -> None:
        self.pages.append([])
        self.y = PAGE_H - MARGIN

    def _ops(self) -> list[str]:
        if not self.pages:
            self.new_page()
        return self.pages[-1]

    def ensure(self, height: float) -> None:
        """Salta de página si no quedan ``height`` puntos sobre el pie."""
        if not self.pages or self.y - height < MARGIN + 20:
            self.new_page()

    def text(
        self,
        x: float,
        y: float,
        value: str,
        size: float = 10,
        *,
        bold: bool = False,
        gray: float = 0.0,
    ) -> None:
        font = "F2" if bold else "F1"
        self._ops().append(
            f"{gray:.2f} g BT /{font} {size:g} Tf {x:.1f} {y:.1f} Td ({_escape(value)}) Tj ET"
        )

    def rect(self, x: float, y: float, w: float, h: float, gray: float) -> None:
        self._ops().append(f"{gray:.2f} g {x:.1f} {y:.1f} {w:.1f} {h:.1f} re f")

    def line(self, x1: float, y1: float, x2: float, y2: float, gray: float = 0.8) -> None:
        self._ops().append(f"{gray:.2f} G 0.5 w {x1:.1f} {y1:.1f} m {x2:.1f} {y2:.1f} l S")

    # --- bloques de alto nivel ---------------------------------------------------------------

    def heading(self, value: str, size: float = 14) -> None:
        self.ensure(size + 16)
        self.y -= size + 6
        self.text(MARGIN, self.y, value, size, bold=True)
        self.y -= 8

    def paragraph(self, value: str, size: float = 10, gray: float = 0.0) -> None:
        self.ensure(size + 6)
        self.y -= size + 4
        self.text(MARGIN, self.y, fit(value, PAGE_W - 2 * MARGIN, size), size, gray=gray)

    def table(self, headers: list[str], rows: list[list[str]], widths: list[float]) -> None:
        size, row_h = 8.5, 13.0

        def draw(cells: list[str], *, bold: bool) -> None:
            x = MARGIN
            for cell, width in zip(cells, widths, strict=True):
                self.text(x + 2, self.y + 3, fit(cell, width - 4, size), size, bold=bold)
                x += width

        self.ensure(row_h * 2)
        self.y -= row_h
        draw(headers, bold=True)
        self.line(MARGIN, self.y, MARGIN + sum(widths), self.y, gray=0.4)
        for cells in rows:
            if self.y - row_h < MARGIN + 20:
                self.new_page()
                self.y -= row_h
                draw(headers, bold=True)
                self.line(MARGIN, self.y, MARGIN + sum(widths), self.y, gray=0.4)
            self.y -= row_h
            draw(cells, bold=False)
        self.y -= 6

    def bars(self, title: str, items: list[tuple[str, int]]) -> None:
        """Barras horizontales: el largo es proporcional al valor, medido desde cero."""
        if not items:
            return
        row_h, label_w, value_w = 14.0, 170.0, 40.0
        self.heading(title, 11)
        self.ensure(row_h * min(len(items), 3))
        peak = max(v for _, v in items) or 1
        bar_max = PAGE_W - 2 * MARGIN - label_w - value_w
        for label, value in items:
            self.ensure(row_h)
            self.y -= row_h
            self.text(MARGIN, self.y + 3, fit(label, label_w - 6, 8.5), 8.5)
            self.rect(MARGIN + label_w, self.y + 1, max(bar_max * value / peak, 1), 9, 0.45)
            self.text(MARGIN + label_w + bar_max + 6, self.y + 3, str(value), 8.5)
        self.y -= 8

    def render(self) -> bytes:
        if not self.pages:
            self.new_page()
        total = len(self.pages)
        objects: list[bytes] = []
        # 1 catálogo, 2 páginas, 3 y 4 fuentes, luego (página, contenido) por cada hoja.
        kids = " ".join(f"{5 + 2 * i} 0 R" for i in range(total))
        objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
        objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {total} >>".encode())
        for base in ("Helvetica", "Helvetica-Bold"):
            objects.append(
                f"<< /Type /Font /Subtype /Type1 /BaseFont /{base} "
                "/Encoding /WinAnsiEncoding >>".encode()
            )
        for i, ops in enumerate(self.pages):
            footer = f"Página {i + 1} de {total}" + (f" · {self.footer}" if self.footer else "")
            stream_ops = [
                *ops,
                f"0.40 g BT /F1 8 Tf {MARGIN:.1f} 28 Td ({_escape(footer)}) Tj ET",
            ]
            stream = "\n".join(stream_ops).encode("latin-1")
            objects.append(
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W:g} {PAGE_H:g}] "
                f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
                f"/Contents {6 + 2 * i} 0 R >>".encode()
            )
            objects.append(
                b"<< /Length "
                + str(len(stream)).encode()
                + b" >>\nstream\n"
                + stream
                + b"\nendstream"
            )
        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for n, body in enumerate(objects, start=1):
            offsets.append(len(out))
            out += f"{n} 0 obj\n".encode() + body + b"\nendobj\n"
        xref = len(out)
        out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
        for off in offsets:
            out += f"{off:010d} 00000 n \n".encode()
        out += (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
        ).encode()
        return bytes(out)

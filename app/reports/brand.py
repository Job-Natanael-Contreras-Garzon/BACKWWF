"""Identidad visual de los reportes (D9). Es el único lugar que hay que tocar para aplicar el
diseño de WWF: colores, tipografía, logo y textos fijos. Ver la sección "Reportes: diseño de WWF"
del README.
"""

from dataclasses import dataclass
from pathlib import Path

ASSETS = Path(__file__).resolve().parent / "assets"


@dataclass(frozen=True)
class Brand:
    # Colores en hex: barras y encabezados usan ``primary``; el texto secundario, ``muted``.
    primary: str = "#4A4A4A"
    primary_light: str = "#E6E6E6"
    text: str = "#111111"
    muted: str = "#666666"
    # Fuentes estándar de PDF (no hace falta archivo). Para una propia, ver ``font_files``.
    font: str = "Helvetica"
    font_bold: str = "Helvetica-Bold"
    # Fuente propia: (("WWFSans", "WWFSans.ttf"), ("WWFSans-Bold", "WWFSans-Bold.ttf")), en assets/.
    font_files: tuple[tuple[str, str], ...] = ()
    # Logo (PNG o JPG) dentro de assets/. Si no existe, la portada sale sin logo.
    logo_file: str = "wwf_logo.png"
    logo_width_cm: float = 4.0
    title: str = "Reporte de monitoreo de fauna"
    organization: str = ""  # p. ej. "WWF Bolivia"; aparece en la portada y en el pie

    @property
    def logo_path(self) -> Path | None:
        path = ASSETS / self.logo_file
        return path if path.is_file() else None


BRAND = Brand()

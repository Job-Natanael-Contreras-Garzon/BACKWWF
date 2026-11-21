"""Reportes Excel y PDF (HU-14, FL-12, §11). Los números salen de ``stats_service.compute``:
pantalla, Excel y PDF nunca pueden discrepar (§10.3).
"""

import asyncio
import re
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.core.enums import ClassificationSource, ValidationStatus
from app.core.errors import BusinessRuleError, NotFoundError
from app.core.logging import log_step, request_id_var
from app.db.uow import UnitOfWork
from app.models.classification import Classification
from app.reports import excel, pdf
from app.reports.pdf import PdfContent
from app.schemas.stats import Stats, StatsFilters
from app.services.policies import Owner, serialize_location
from app.services.stats_service import Scope as BaseScope
from app.services.stats_service import compute, date_bounds, effective, is_sighting, load_scope


@dataclass(frozen=True, slots=True)
class Scope(BaseScope):
    """El alcance de stats más las filas: el Excel lista cada clasificación."""

    rows: list[Classification]


_SCOPE_LABEL = {"camera_station": "Cámara", "project": "Proyecto"}
_VALIDATION_LABEL = {
    ValidationStatus.UNVALIDATED: "sin validar",
    ValidationStatus.CONFIRMED: "confirmada",
    ValidationStatus.CORRECTED: "corregida",
    ValidationStatus.CORRECTED_UNLISTED: "corregida (fuera del catálogo)",
    ValidationStatus.REJECTED: "rechazada",
    ValidationStatus.DISCARDED_REPEAT: "repetida (descartada)",
}
_SOURCE_LABEL = {ClassificationSource.WEB: "web", ClassificationSource.DESKTOP: "escritorio"}


async def _load(
    uow: UnitOfWork,
    viewer: Owner | None,
    filters: StatsFilters,
    camera_id: uuid.UUID | None,
    project_id: uuid.UUID | None,
) -> tuple[Scope, Stats]:
    if (camera_id is None) == (project_id is None):
        raise BusinessRuleError(
            "VALIDATION_ERROR",
            "Indica una cámara o un proyecto (solo uno).",
            details=[{"field": "camera_station_id"}],
        )
    base = await load_scope(uow, viewer, filters, camera_id=camera_id, project_id=project_id)
    start, end = date_bounds(filters)
    rows = await uow.classifications.for_stats(
        [c.id for c in base.cameras], start=start, end=end, source=filters.source
    )
    if not rows:
        raise NotFoundError("REPORT_EMPTY", "No hay clasificaciones para esos filtros.")
    scope = Scope(base.kind, base.id, base.name, base.cameras, rows)
    stats = await compute(
        uow,
        scope.cameras,
        filters,
        scope=scope.kind,
        scope_id=scope.id,
        scope_name=scope.name,
    )
    return scope, stats


def file_name(scope: Scope, ext: str, now: datetime) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", scope.name).strip("-")[:40] or "reporte"
    return f"WWM_{slug}_{now:%Y%m%d}.{ext}"


def _filters_text(filters: StatsFilters) -> str:
    parts = [
        f"desde {filters.from_}" if filters.from_ else None,
        f"hasta {filters.to}" if filters.to else None,
        "solo validadas" if filters.only_validated else None,
        f"origen {_SOURCE_LABEL[filters.source]}" if filters.source else None,
    ]
    return ", ".join(p for p in parts if p) or "sin filtros"


def _model_version(rows: list[Classification]) -> str:
    versions = Counter(
        f"{r.model_classifier or '?'} / pipeline {r.pipeline_version or '?'}"
        for r in rows
        if r.model_classifier or r.pipeline_version
    )
    return versions.most_common(1)[0][0] if versions else "—"


def _mmss(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    whole = int(seconds)
    return f"{whole // 60:02d}:{whole % 60:02d}"


def _summary_rows(scope: Scope, stats: Stats, filters: StatsFilters) -> list[list[Any]]:
    t, r, n = stats.totals, stats.richness, stats.non_animal
    if t is None or r is None or n is None:  # pragma: no cover - compute() las llena siempre
        return []
    return [
        ["Alcance", _SCOPE_LABEL[scope.kind]],
        ["Nombre", scope.name],
        ["Filtros", _filters_text(filters)],
        ["Generado", stats.generated_at.strftime("%Y-%m-%d %H:%M UTC")],
        ["request_id", request_id_var.get()],
        ["Versión del modelo", _model_version(scope.rows)],
        ["Archivos procesados", t.files_processed],
        ["Con fauna", t.files_with_fauna],
        ["Sin fauna", t.files_without_fauna],
        ["Con error", t.files_error],
        ["Avistamientos", t.sightings],
        ["Validados", t.validated],
        ["Corregidos", t.corrected],
        ["Rechazados", t.rejected],
        ["Repetidos descartados", t.discarded_repeat],
        ["Pendientes de validar", t.pending_validation],
        ["Riqueza: especies", r.species],
        ["Riqueza: géneros", r.genera],
        ["Riqueza: familias", r.families],
        ["Personas", n.person],
        ["Vehículos", n.vehicle],
        ["Vacías", n.blank],
    ]


def _classification_rows(scope: Scope, viewer: Owner | None) -> list[list[Any]]:
    cameras = {c.id: c for c in scope.cameras}
    names = {r.id: r.file_name for r in scope.rows}
    rows = []
    for row in scope.rows:
        camera = cameras[row.camera_station_id]
        lat, lng, _ = serialize_location(camera, viewer)  # DD-17: redondeadas a terceros
        corrected = (
            effective(row)
            if row.validation_status
            in (ValidationStatus.CORRECTED, ValidationStatus.CORRECTED_UNLISTED)
            else None
        )
        rows.append(
            [
                row.file_name,
                camera.code,
                lat,
                lng,
                row.captured_at,
                row.captured_at_source.value if row.captured_at_source else None,
                _mmss(row.evidence_timestamp_seconds),
                "sí" if is_sighting(row) else "no",
                names.get(row.repeat_of) if row.repeat_of else None,
                row.category.value if row.category else row.status.value,
                row.scientific_name if row.species else None,
                row.genus,
                row.family,
                float(row.confidence) if row.confidence is not None else None,
                _VALIDATION_LABEL[row.validation_status],
                (corrected.scientific_name if corrected else None) or row.suggested_name,
                corrected.genus if corrected else None,
                corrected.family if corrected else None,
                row.validation_notes,
                _SOURCE_LABEL[row.source],
                row.model_classifier,
            ]
        )
    return rows


def _build_excel(scope: Scope, stats: Stats, filters: StatsFilters, viewer: Owner | None) -> bytes:
    return excel.build(
        [
            ("Resumen", ["Campo", "Valor"], _summary_rows(scope, stats, filters)),
            (
                "Por especie",
                [
                    "Nombre científico",
                    "Nombre común",
                    "Género",
                    "Familia",
                    "Avistamientos",
                    "%",
                    "Validados",
                    "Confianza media",
                    "Primera fecha",
                    "Última fecha",
                    "N.º de cámaras",
                ],
                [
                    [
                        s.scientific_name,
                        s.common_name,
                        s.genus,
                        s.family,
                        s.count,
                        s.pct,
                        s.validated,
                        s.mean_confidence,
                        s.first_seen,
                        s.last_seen,
                        s.camera_stations,
                    ]
                    for s in stats.by_species or []
                ],
            ),
            (
                "Por género",
                ["Género", "Familia", "Avistamientos", "%"],
                [[g.name, g.family, g.count, g.pct] for g in stats.by_genus or []],
            ),
            (
                "Por familia",
                ["Familia", "Avistamientos", "%"],
                [[f.name, f.count, f.pct] for f in stats.by_family or []],
            ),
            (
                "Clasificaciones",
                [
                    "Archivo",
                    "Código de cámara",
                    "Latitud",
                    "Longitud",
                    "Fecha de captura",
                    "Fuente de la fecha",
                    "Fotograma (mm:ss)",
                    "Cuenta como avistamiento",
                    "Repetido de (archivo)",
                    "Categoría",
                    "Especie (IA)",
                    "Género (IA)",
                    "Familia (IA)",
                    "Confianza",
                    "Estado de validación",
                    "Especie validada",
                    "Género validado",
                    "Familia validada",
                    "Notas",
                    "Origen",
                    "Modelo",
                ],
                _classification_rows(scope, viewer),
            ),
        ]
    )


def _build_pdf(scope: Scope, stats: Stats, filters: StatsFilters) -> bytes:
    species = stats.by_species or []
    families = stats.by_family or []
    effort = stats.effort
    content = PdfContent(
        scope_line=f"{_SCOPE_LABEL[scope.kind]}: {scope.name}",
        filters_line=f"Filtros: {_filters_text(filters)}",
        generated_line=f"Generado: {stats.generated_at.strftime('%Y-%m-%d %H:%M UTC')}",
        model_line=f"Modelo: {_model_version(scope.rows)}",
        totals=[(str(k), str(v)) for k, v in _summary_rows(scope, stats, filters)[6:]],
        effort_line=(
            f"Esfuerzo: {effort.trap_days:g} días-trampa · "
            f"{effort.sightings_per_100_trap_days or 0:g} avistamientos por 100 días-trampa"
            if effort
            else None
        ),
        species=[(s.scientific_name or "?", s.count) for s in species],
        genera=[(g.name, g.count) for g in stats.by_genus or []],
        families=[(f.name, f.count) for f in families],
        species_table=[
            [
                s.scientific_name or "",
                s.common_name or "",
                str(s.count),
                f"{s.pct:g}",
                str(s.validated),
            ]
            for s in species
        ],
        family_table=[[f.name, str(f.count), f"{f.pct:g}"] for f in families],
    )
    return pdf.build(content, footer=f"request_id {request_id_var.get()}")


async def build_report(
    uow: UnitOfWork,
    viewer: Owner | None,
    filters: StatsFilters,
    *,
    kind: str,
    camera_id: uuid.UUID | None,
    project_id: uuid.UUID | None,
) -> tuple[bytes, str]:
    """Devuelve (binario, nombre de archivo). openpyxl y el PDF corren en un hilo."""
    with log_step(f"report.{kind}"):
        scope, stats = await _load(uow, viewer, filters, camera_id, project_id)
        now = datetime.now(UTC)
        if kind == "excel":
            data = await asyncio.to_thread(_build_excel, scope, stats, filters, viewer)
            return data, file_name(scope, "xlsx", now)
        data = await asyncio.to_thread(_build_pdf, scope, stats, filters)
        return data, file_name(scope, "pdf", now)

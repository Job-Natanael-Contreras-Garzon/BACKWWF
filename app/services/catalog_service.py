"""Catálogo de especies SpeciesNet en RAM (HU-13, #30).

Se carga una sola vez desde ``CATALOG_PATH`` (copia de ``catalog/speciesnet_catalog.json`` de la
IA, 3538 taxones). ``sync_from_ai`` lo actualiza desde ``GET /api/v1/catalog`` con ``ETag``/``304``.
``common_name`` queda en inglés, como lo entrega la IA (decisión abierta del backlog, opción a).
"""

import asyncio
import json
import os
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings
from app.core.errors import NotFoundError
from app.integrations.ia_contract.enums import RANK_ORDER, Rank

# Las especies primero (RANK_ORDER va de clase a especie).
_RANK_WEIGHT = {rank: i for i, rank in enumerate(RANK_ORDER)}


def normalize(text: str) -> str:
    """Minúsculas y sin tildes: "Jaguár" y "jaguar" son la misma búsqueda (CA-2)."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).strip()


@dataclass(frozen=True, slots=True)
class Taxon:
    label_id: str
    rank: Rank
    class_: str | None
    order: str | None
    family: str | None
    genus: str | None
    species: str | None
    scientific_name: str
    common_name: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "label_id": self.label_id,
            "rank": self.rank.value,
            "class": self.class_,
            "order": self.order,
            "family": self.family,
            "genus": self.genus,
            "species": self.species,
            "scientific_name": self.scientific_name,
            "common_name": self.common_name,
        }


class Catalog:
    def __init__(self, raw: dict[str, Any]) -> None:
        self.classifier: str = raw.get("classifier", "")
        self.sha256: str = raw["sha256"]
        self.taxa = [
            Taxon(
                label_id=t["label_id"],
                rank=Rank(t["rank"]),
                class_=t.get("class"),
                order=t.get("order"),
                family=t.get("family"),
                genus=t.get("genus"),
                species=t.get("species"),
                scientific_name=t["scientific_name"],
                common_name=t.get("common_name"),
            )
            for t in raw["taxa"]
        ]
        self.by_id = {t.label_id: t for t in self.taxa}
        # (rango, nombre) → taxón: para dar label_id a los grupos de género y familia en stats.
        self.by_rank_name: dict[tuple[Rank, str], Taxon] = {
            (t.rank, normalize(t.scientific_name)): t for t in self.taxa if t.rank != Rank.SPECIES
        }
        self._haystack = [
            (
                t,
                [normalize(v) for v in (t.common_name, t.scientific_name, t.genus, t.family) if v],
            )
            for t in self.taxa
        ]

    def get(self, label_id: str) -> Taxon:
        taxon = self.by_id.get(label_id)
        if taxon is None:
            raise NotFoundError("CATALOG_TAXON_NOT_FOUND", "Ese taxón no está en el catálogo.")
        return taxon

    def group(self, rank: Rank, name: str | None) -> Taxon | None:
        return self.by_rank_name.get((rank, normalize(name))) if name else None

    def search(self, q: str, rank: Rank | None = None, limit: int = 20) -> list[Taxon]:
        """Ordena por coincidencia (exacta, prefijo, contiene) y luego por rango (§9.1)."""
        needle = normalize(q)
        scored: list[tuple[int, int, str, Taxon]] = []
        for taxon, fields in self._haystack:
            if rank is not None and taxon.rank != rank:
                continue
            best = 3
            for value in fields:
                if value == needle:
                    best = 0
                    break
                if value.startswith(needle) or f" {needle}" in value:
                    best = min(best, 1)
                elif needle in value:
                    best = min(best, 2)
            if best < 3:
                scored.append((best, -_RANK_WEIGHT[taxon.rank], taxon.scientific_name, taxon))
        scored.sort(key=lambda s: (s[0], s[1], s[2]))
        return [s[3] for s in scored[:limit]]


_catalog: Catalog | None = None


def get_catalog() -> Catalog:
    """Se lee una vez por proceso (~1 MB); los tests pueden reemplazarlo con ``set_catalog``."""
    global _catalog
    if _catalog is None:
        _catalog = Catalog(json.loads(Path(settings.CATALOG_PATH).read_text(encoding="utf-8")))
    return _catalog


def set_catalog(catalog: Catalog | None) -> None:
    global _catalog
    _catalog = catalog


async def sync_from_ai(client: httpx.AsyncClient | None = None) -> str:
    """Descarga el catálogo de la IA si cambió. Devuelve ``updated`` o ``not_modified``."""
    path = Path(settings.CATALOG_PATH)
    current = await asyncio.to_thread(_read_json, path)
    headers = {"X-API-Key": settings.AI_API_KEY}
    if current:
        headers["If-None-Match"] = f'"{current["sha256"]}"'
    url = f"{settings.AI_SERVICE_URL.rstrip('/')}/api/v1/catalog"
    if client is not None:
        response = await client.get(url, headers=headers)
    else:
        async with httpx.AsyncClient(timeout=30) as http:
            response = await http.get(url, headers=headers)
    if response.status_code == 304:
        return "not_modified"
    response.raise_for_status()
    data = response.json()["data"]
    Catalog(data)  # valida la forma antes de reemplazar el archivo
    await asyncio.to_thread(_write_json, path, data)
    set_catalog(None)
    return "updated"


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _write_json(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)

import time
import tracemalloc
from typing import List
from pydantic import BaseModel
import pytest

from app.schemas.response_wrapper import StandardErrorResponse, StandardResponse


class SampleItem(BaseModel):
    id: int
    name: str
    species: str
    confidence: float
    is_active: bool


class TestResponseWrapperEfficiency:
    """Pruebas de eficiencia, sobrecarga de serialización y rendimiento de esquemas de respuesta."""

    def test_standard_response_structure(self):
        resp = StandardResponse[str](
            status="success",
            data="Operación completada",
            message="OK",
        )
        data_dict = resp.model_dump()
        assert data_dict["status"] == "success"
        assert data_dict["data"] == "Operación completada"
        assert data_dict["message"] == "OK"

    def test_standard_error_response_structure(self):
        err = StandardErrorResponse(
            status="error",
            data=None,
            message="Recurso no encontrado",
        )
        err_dict = err.model_dump()
        assert err_dict["status"] == "error"
        assert err_dict["data"] is None
        assert err_dict["message"] == "Recurso no encontrado"

    def test_large_payload_serialization_efficiency(self):
        """
        Evalúa el tiempo de empaquetado y serialización JSON de una lista masiva
        de 10,000 objetos dentro de StandardResponse[List[SampleItem]].
        """
        item_count = 10000
        items = [
            SampleItem(
                id=i,
                name=f"Camera_Trap_{i}",
                species="Panthera onca",
                confidence=0.985,
                is_active=True,
            )
            for i in range(item_count)
        ]

        t0 = time.perf_counter()
        wrapped_response = StandardResponse[List[SampleItem]](
            status="success",
            data=items,
            message=f"Se retornaron {item_count} registros",
        )
        t1 = time.perf_counter()
        json_output = wrapped_response.model_dump_json()
        t2 = time.perf_counter()

        wrap_time_ms = (t1 - t0) * 1000
        json_time_ms = (t2 - t1) * 1000
        total_time_ms = (t2 - t0) * 1000

        print(f"\n[SERIALIZATION EFFICIENCY] {item_count} registros:")
        print(f"   Empaquetado Pydantic: {wrap_time_ms:.2f}ms")
        print(f"   Serialización JSON:   {json_time_ms:.2f}ms")
        print(f"   Tiempo Total:         {total_time_ms:.2f}ms")

        # Serialización de 10k modelos debe tomar menos de 250ms en total
        assert total_time_ms < 250.0, f"Serialización demasiado lenta: {total_time_ms}ms"
        assert len(json_output) > 100000

    def test_memory_allocation_under_serialization_stress(self):
        """
        Monitorea el uso de memoria durante múltiples ciclos de serialización JSON.
        """
        tracemalloc.start()
        snapshot_start = tracemalloc.take_snapshot()

        for _ in range(50):
            items = [
                SampleItem(
                    id=i,
                    name=f"Station_{i}",
                    species="Tapirus bairdii",
                    confidence=0.92,
                    is_active=True,
                )
                for i in range(1000)
            ]
            resp = StandardResponse[List[SampleItem]](data=items)
            _ = resp.model_dump_json()

        snapshot_end = tracemalloc.take_snapshot()
        tracemalloc.stop()

        stats = snapshot_end.compare_to(snapshot_start, "lineno")
        growth_kb = sum(s.size_diff for s in stats) / 1024

        print(f"\n[WRAPPER MEMORY] Crecimiento de memoria en 50 ciclos (1,000 items c/u): {growth_kb:.2f} KB")
        assert growth_kb < 5000, f"Sobrecarga de memoria de serialización excesiva: {growth_kb:.2f} KB"

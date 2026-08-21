import asyncio
import time
from httpx import AsyncClient, ASGITransport
import pytest
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.main import app

# Router de prueba para validar excepciones y estrés
dummy_test_router = APIRouter(prefix="/api/v1/test-handlers", tags=["Testing"])


def percentile(data: list[float], p: float) -> float:
    """Calcula el percentil p (0..100) en una lista de números."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_data) - 1)
    d = k - f
    return sorted_data[f] + d * (sorted_data[c] - sorted_data[f])


class PayloadModel(BaseModel):
    name: str
    age: int


@dummy_test_router.post("/validation-test")
async def validation_test_endpoint(payload: PayloadModel):
    return {"status": "success", "data": payload.model_dump(), "message": "OK"}


@dummy_test_router.get("/http-error")
async def http_error_endpoint():
    raise HTTPException(status_code=403, detail="Acceso denegado a recurso restringido")


@dummy_test_router.get("/internal-error")
async def internal_error_endpoint():
    raise RuntimeError("Falla critica simulada en servicio de base de datos")


app.include_router(dummy_test_router)


class TestExceptionHandlersAndStress:
    """Pruebas de Exception Handlers y Throughput HTTP bajo concurrencia."""

    @pytest.mark.asyncio
    async def test_404_not_found_standard_error(self, async_client: AsyncClient):
        response = await async_client.get("/api/v1/non-existent-route-endpoint")
        assert response.status_code == 404
        data = response.json()
        assert data["status"] == "error"
        assert data["data"] is None
        assert "message" in data
        assert "Not Found" in data["message"]

    @pytest.mark.asyncio
    async def test_403_http_exception_standard_error(self, async_client: AsyncClient):
        response = await async_client.get("/api/v1/test-handlers/http-error")
        assert response.status_code == 403
        data = response.json()
        assert data["status"] == "error"
        assert data["data"] is None
        assert data["message"] == "Acceso denegado a recurso restringido"

    @pytest.mark.asyncio
    async def test_422_validation_error_standard_error(self, async_client: AsyncClient):
        # Enviar payload malformado (age como string no convertible / campo faltante)
        response = await async_client.post(
            "/api/v1/test-handlers/validation-test",
            json={"name": "Test User", "age": "not-an-integer"},
        )
        assert response.status_code == 422
        data = response.json()
        assert data["status"] == "error"
        assert data["data"] is None
        assert "Validación fallida" in data["message"]

    @pytest.mark.asyncio
    async def test_500_internal_error_standard_error(self, async_client: AsyncClient):
        response = await async_client.get("/api/v1/test-handlers/internal-error")
        assert response.status_code == 500
        data = response.json()
        assert data["status"] == "error"
        assert data["data"] is None
        assert "Error interno del servidor" in data["message"]
        assert "Falla critica simulada" in data["message"]

    @pytest.mark.asyncio
    async def test_concurrent_http_stress_on_exception_handlers(self):
        """
        Prueba de Carga y Concurrencia HTTP:
        Envío masivo de 1,000 peticiones concurrentes combinando errores 404, 422 y 500.
        Evalúa Throughput (RPS) y estabilidad de formato de error del bucle de eventos.
        """
        request_count = 1000
        transport = ASGITransport(app=app, raise_app_exceptions=False)

        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            latencies = []

            async def fire_request(i: int):
                t0 = time.perf_counter()
                if i % 3 == 0:
                    resp = await client.get(f"/api/v1/not-found-{i}")
                    expected_status = 404
                elif i % 3 == 1:
                    resp = await client.post(
                        "/api/v1/test-handlers/validation-test",
                        json={"invalid": True},
                    )
                    expected_status = 422
                else:
                    resp = await client.get("/api/v1/test-handlers/http-error")
                    expected_status = 403

                t1 = time.perf_counter()
                latency_ms = (t1 - t0) * 1000
                return resp, latency_ms, expected_status

            start_total = time.perf_counter()
            tasks = [fire_request(i) for i in range(request_count)]
            results = await asyncio.gather(*tasks)
            total_time = time.perf_counter() - start_total

            # Validar todas las respuestas
            for resp, lat, exp_status in results:
                latencies.append(lat)
                assert resp.status_code == exp_status
                body = resp.json()
                assert body["status"] == "error"
                assert body["data"] is None
                assert isinstance(body["message"], str)

            rps = request_count / total_time
            p50 = percentile(latencies, 50)
            p95 = percentile(latencies, 95)
            p99 = percentile(latencies, 99)

            print(f"\n[HTTP CONCURRENCY STRESS] {request_count} peticiones concurrentes de error:")
            print(f"   Throughput (RPS): {rps:.2f} req/seg")
            print(f"   Latencias: p50={p50:.3f}ms | p95={p95:.3f}ms | p99={p99:.3f}ms")
            print(f"   Tiempo total de ráfaga: {total_time:.3f}s")

            # Aserciones de rendimiento
            assert rps > 50.0, f"Throughput RPS insuficiente: {rps}"
            assert p99 < 150.0, f"Latencia p99 excedida: {p99}ms"

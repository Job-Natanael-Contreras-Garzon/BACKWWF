import asyncio
import io
import time
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio(loop_scope="session")
class TestPhase5HealthAndOpenAPI:
    """Valida los endpoints de salud del sistema, metadatos y conformidad con OpenAPI/Swagger UI."""

    async def test_health_check_endpoint(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            res = await ac.get("/health")
            assert res.status_code == 200
            json_data = res.json()
            assert json_data["status"] == "success"
            assert json_data["data"]["status"] == "healthy"
            assert json_data["data"]["database"] == "connected"
            assert json_data["data"]["version"] == "4.0.0"

    async def test_root_endpoint_metadata(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            res = await ac.get("/")
            assert res.status_code == 200
            json_data = res.json()
            assert json_data["status"] == "success"
            assert json_data["data"]["docs_url"] == "/docs"
            assert json_data["data"]["version"] == "4.0.0"
            assert json_data["data"]["environment"] == "production"

    async def test_openapi_schema_and_bearer_security(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            res = await ac.get("/openapi.json")
            assert res.status_code == 200
            schema = res.json()
            assert "components" in schema
            assert "securitySchemes" in schema["components"]
            assert "BearerAuth" in schema["components"]["securitySchemes"]
            bearer_sec = schema["components"]["securitySchemes"]["BearerAuth"]
            assert bearer_sec["type"] == "http"
            assert bearer_sec["scheme"] == "bearer"
            assert bearer_sec["bearerFormat"] == "JWT"


@pytest.mark.asyncio(loop_scope="session")
class TestPhase5E2ELifecycle:
    """Valida el ciclo de vida completo de extremo a extremo: Anónimo -> Claim -> Soft Delete -> Taxonomía."""

    async def test_full_system_lifecycle_e2e(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            # 1. Creación Anónima
            st_code = f"ST-E2E-{uuid.uuid4().hex[:6]}"
            st_res = await ac.post("/camera-stations/", json={
                "station_code": st_code,
                "location_name": "Sendero E2E Anónimo",
            })
            assert st_res.status_code == 201
            st_data = st_res.json()["data"]
            station_id = st_data["id"]
            anon_session_id = st_res.headers.get("X-Anon-Session-ID")
            assert anon_session_id is not None

            proj_res = await ac.post("/projects/", json={
                "title": f"Proyecto E2E {uuid.uuid4().hex[:4]}",
                "description": "Estudio integral de fauna",
            }, headers={"X-Anon-Session-ID": anon_session_id})
            assert proj_res.status_code == 201
            project_id = proj_res.json()["data"]["id"]

            # 2. Asociación N:M en modo anónimo
            assoc_res = await ac.post(f"/projects/{project_id}/stations", json={"station_id": station_id}, headers={"X-Anon-Session-ID": anon_session_id})
            assert assoc_res.status_code == 200

            # 3. Intentar Soft Delete Anónimo sin token (Debe retornar 401 Unauthorized)
            del_st_no_auth = await ac.delete(f"/camera-stations/{station_id}")
            assert del_st_no_auth.status_code == 401

            # 4. Registro y Autenticación JWT de Usuario
            email = f"e2e_biologist_{uuid.uuid4().hex[:6]}@wwf.org"
            reg_res = await ac.post("/auth/register", json={
                "email": email,
                "password": "Password123!",
                "full_name": "Dr. Biólogo E2E",
                "role": "investigator",
            })
            assert reg_res.status_code == 201
            token = reg_res.json()["data"]["tokens"]["access_token"]
            auth_headers = {"Authorization": f"Bearer {token}"}

            # 5. Intentar Soft Delete con token antes de reclamar (Debe retornar 403 Forbidden)
            del_st_anon = await ac.delete(f"/camera-stations/{station_id}", headers=auth_headers)
            assert del_st_anon.status_code == 403
            assert del_st_anon.json()["status"] == "error"
            assert "No se pueden eliminar elementos anónimos" in del_st_anon.json()["message"]

            del_proj_anon = await ac.delete(f"/projects/{project_id}", headers=auth_headers)
            assert del_proj_anon.status_code == 403
            assert "No se pueden eliminar proyectos anónimos" in del_proj_anon.json()["message"]

            # 6. Reclamo de Recursos Anónimos
            claim_res = await ac.post("/users/me/claim", json={"anon_session_id": anon_session_id}, headers=auth_headers)
            assert claim_res.status_code == 200
            claim_data = claim_res.json()["data"]
            assert claim_data["claimed_stations_count"] >= 1
            assert claim_data["claimed_projects_count"] >= 1

            # 7. Ingesta Multimedia y Parseo Taxonómico
            fake_bytes = b"\xFF\xD8\xFF\xE0" + b"\x00" * 200
            file_data = {"file": ("puma_e2e.jpg", io.BytesIO(fake_bytes), "image/jpeg")}
            up_res = await ac.post(f"/camera-stations/{station_id}/files", files=file_data, headers=auth_headers)
            assert up_res.status_code == 201
            assert up_res.json()["data"]["detections_count"] >= 1

            # 8. Consulta de Resumen Taxonómico
            st_sum = await ac.get(f"/camera-stations/{station_id}/summary")
            assert st_sum.status_code == 200
            assert st_sum.json()["data"]["total_detections_count"] >= 1

            p_sum = await ac.get(f"/projects/{project_id}/summary")
            assert p_sum.status_code == 200
            assert p_sum.json()["data"]["total_detections_count"] >= 1

            # 9. Soft Delete Autorizado como Dueño Legítimo
            del_st_auth = await ac.delete(f"/camera-stations/{station_id}", headers=auth_headers)
            assert del_st_auth.status_code == 200
            assert del_st_auth.json()["status"] == "success"

            del_proj_auth = await ac.delete(f"/projects/{project_id}", headers=auth_headers)
            assert del_proj_auth.status_code == 200

            # 10. Verificación de Filtrado Soft Delete
            get_st = await ac.get(f"/camera-stations/{station_id}")
            assert get_st.status_code == 404

            get_proj = await ac.get(f"/projects/{project_id}")
            assert get_proj.status_code == 404


@pytest.mark.asyncio(loop_scope="session")
class TestPhase5SystemStabilityStress:
    """Valida la estabilidad global del sistema bajo concurrencia y consultas simultáneas."""

    async def test_concurrent_health_and_system_benchmark(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            concurrency_n = 20

            async def do_health_check():
                start = time.perf_counter()
                res = await ac.get("/health")
                elapsed = (time.perf_counter() - start) * 1000
                return res.status_code, elapsed

            t0 = time.perf_counter()
            tasks = [do_health_check() for _ in range(concurrency_n)]
            results = await asyncio.gather(*tasks)
            total_duration = time.perf_counter() - t0

            status_codes = [r[0] for r in results]
            latencies = sorted([r[1] for r in results])

            for code in status_codes:
                assert code == 200

            p50 = latencies[len(latencies) // 2]
            p95 = latencies[int(len(latencies) * 0.95)]
            p99 = latencies[int(len(latencies) * 0.99)]
            rps = round(concurrency_n / total_duration, 2)

            print(f"\n[PHASE 5 STABILITY BENCHMARK] {concurrency_n} peticiones concurrentes a /health:")
            print(f"   Throughput (RPS): {rps} op/seg")
            print(f"   Latencias: p50={p50:.3f}ms | p95={p95:.3f}ms | p99={p99:.3f}ms")
            print(f"   Tiempo total: {total_duration:.3f}s")

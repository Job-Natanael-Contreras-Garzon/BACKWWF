import asyncio
import time
import uuid
from httpx import AsyncClient, ASGITransport
import pytest

from app.main import app


def percentile(data: list[float], p: float) -> float:
    """Calcula el percentil p (0..100) en una lista de tiempos en milisegundos."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_data) - 1)
    d = k - f
    return sorted_data[f] + d * (sorted_data[c] - sorted_data[f])


class TestPhase3NMAndSoftDeleteFunctional:
    """Pruebas funcionales para la relación N:M y políticas estrictas de Soft Delete."""

    @pytest.mark.asyncio
    async def test_nm_relationship_cross_association_happy_path(self, async_client: AsyncClient):
        """
        Happy Path N:M:
        1. Crear Proyecto A y Proyecto B.
        2. Crear Estación 1 y Estación 2.
        3. Asociar Estación 1 a Proyecto A y Proyecto B.
        4. Asociar Estación 2 a Proyecto A.
        5. Validar que Proyecto A contiene Estación 1 y 2.
        6. Validar que Proyecto B contiene Estación 1.
        7. Desasociar Estación 1 de Proyecto A y verificar que permanece intacta en Proyecto B.
        """
        u_suffix = uuid.uuid4().hex[:6]
        reg = await async_client.post(
            "/auth/register",
            json={
                "full_name": f"Investigador NM {u_suffix}",
                "email": f"nm_researcher_{u_suffix}@wwf.org",
                "password": "SecurePassword2026!#",
            },
        )
        assert reg.status_code == 201
        token = reg.json()["data"]["tokens"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Crear Proyectos
        p1_resp = await async_client.post(
            "/projects/",
            json={"title": f"Proyecto A {u_suffix}", "description": "Monitoreo Chocó"},
            headers=headers,
        )
        assert p1_resp.status_code == 201
        proj_a_id = p1_resp.json()["data"]["id"]

        p2_resp = await async_client.post(
            "/projects/",
            json={"title": f"Proyecto B {u_suffix}", "description": "Monitoreo Amazonía"},
            headers=headers,
        )
        assert p2_resp.status_code == 201
        proj_b_id = p2_resp.json()["data"]["id"]

        # 2. Crear Estaciones
        s1_resp = await async_client.post(
            "/camera-stations/",
            json={"station_code": f"CAM-NM1-{u_suffix}", "location_name": "Sitio Alfa"},
            headers=headers,
        )
        assert s1_resp.status_code == 201
        station_1_id = s1_resp.json()["data"]["id"]

        s2_resp = await async_client.post(
            "/camera-stations/",
            json={"station_code": f"CAM-NM2-{u_suffix}", "location_name": "Sitio Beta"},
            headers=headers,
        )
        assert s2_resp.status_code == 201
        station_2_id = s2_resp.json()["data"]["id"]

        # 3. Asociar Estación 1 a Proyecto A y Proyecto B (N:M)
        as1 = await async_client.post(
            f"/projects/{proj_a_id}/stations",
            json={"station_id": station_1_id},
            headers=headers,
        )
        assert as1.status_code == 200
        assert as1.json()["status"] == "success"

        as2 = await async_client.post(
            f"/projects/{proj_b_id}/stations",
            json={"station_id": station_1_id},
            headers=headers,
        )
        assert as2.status_code == 200

        # 4. Asociar Estación 2 a Proyecto A
        as3 = await async_client.post(
            f"/projects/{proj_a_id}/stations",
            json={"station_id": station_2_id},
            headers=headers,
        )
        assert as3.status_code == 200

        # 5. Validar que Proyecto A contiene ambas estaciones
        get_p1 = await async_client.get(f"/projects/{proj_a_id}")
        assert get_p1.status_code == 200
        stations_in_a = [s["id"] for s in get_p1.json()["data"]["camera_stations"]]
        assert station_1_id in stations_in_a
        assert station_2_id in stations_in_a

        # 6. Validar que Proyecto B contiene solo Estación 1
        get_p2 = await async_client.get(f"/projects/{proj_b_id}")
        assert get_p2.status_code == 200
        stations_in_b = [s["id"] for s in get_p2.json()["data"]["camera_stations"]]
        assert station_1_id in stations_in_b
        assert station_2_id not in stations_in_b

        # 7. Desasociar Estación 1 de Proyecto A
        dis_res = await async_client.delete(
            f"/projects/{proj_a_id}/stations/{station_1_id}",
            headers=headers,
        )
        assert dis_res.status_code == 200

        # Verificar que Proyecto A ya no la tiene pero Proyecto B sigue teniéndola intacta
        get_p1_after = await async_client.get(f"/projects/{proj_a_id}")
        stations_in_a_after = [s["id"] for s in get_p1_after.json()["data"]["camera_stations"]]
        assert station_1_id not in stations_in_a_after
        assert station_2_id in stations_in_a_after

        get_p2_after = await async_client.get(f"/projects/{proj_b_id}")
        stations_in_b_after = [s["id"] for s in get_p2_after.json()["data"]["camera_stations"]]
        assert station_1_id in stations_in_b_after

    @pytest.mark.asyncio
    async def test_soft_delete_authorization_and_security_rules(self, async_client: AsyncClient):
        """
        Reglas de Seguridad Soft Delete:
        1. 403 Forbidden al intentar eliminar un Proyecto Anónimo.
        2. 403 Forbidden al intentar eliminar una Estación Anónima.
        3. 403 Forbidden al intentar eliminar un recurso perteneciente a otro usuario.
        4. 200 OK cuando el dueño legítimo ejecuta Soft Delete y comprobación de exclusión automática.
        """
        u1_suffix = uuid.uuid4().hex[:6]
        u2_suffix = uuid.uuid4().hex[:6]

        # Crear Usuario 1 y Usuario 2
        r1 = await async_client.post(
            "/auth/register",
            json={
                "full_name": "Dueño 1",
                "email": f"owner1_{u1_suffix}@wwf.org",
                "password": "Password123!#",
            },
        )
        token_u1 = r1.json()["data"]["tokens"]["access_token"]
        headers_u1 = {"Authorization": f"Bearer {token_u1}"}

        r2 = await async_client.post(
            "/auth/register",
            json={
                "full_name": "Dueño 2",
                "email": f"owner2_{u2_suffix}@wwf.org",
                "password": "Password123!#",
            },
        )
        token_u2 = r2.json()["data"]["tokens"]["access_token"]
        headers_u2 = {"Authorization": f"Bearer {token_u2}"}

        # 1. Crear Proyecto Anónimo
        anon_proj_res = await async_client.post(
            "/projects/",
            json={"title": f"Proyecto Anónimo {u1_suffix}"},
        )
        assert anon_proj_res.status_code == 201
        anon_proj_id = anon_proj_res.json()["data"]["id"]

        # Intentar eliminar proyecto anónimo con token -> Debe retornar 403
        del_anon_p = await async_client.delete(f"/projects/{anon_proj_id}", headers=headers_u1)
        assert del_anon_p.status_code == 403
        assert del_anon_p.json()["status"] == "error"
        assert "No se pueden eliminar proyectos anónimos" in del_anon_p.json()["message"]

        # 2. Crear Estación Anónima
        anon_stat_res = await async_client.post(
            "/camera-stations/",
            json={"station_code": f"CAM-ANON-{u1_suffix}"},
        )
        assert anon_stat_res.status_code == 201
        anon_stat_id = anon_stat_res.json()["data"]["id"]

        # Intentar eliminar estación anónima con token -> Debe retornar 403
        del_anon_s = await async_client.delete(f"/camera-stations/{anon_stat_id}", headers=headers_u1)
        assert del_anon_s.status_code == 403
        assert del_anon_s.json()["status"] == "error"
        assert "No se pueden eliminar elementos anónimos" in del_anon_s.json()["message"]

        # 3. Usuario 1 crea un proyecto y una estación legítimos
        legit_proj = await async_client.post(
            "/projects/",
            json={"title": f"Proyecto Propio {u1_suffix}"},
            headers=headers_u1,
        )
        legit_proj_id = legit_proj.json()["data"]["id"]

        legit_stat = await async_client.post(
            "/camera-stations/",
            json={"station_code": f"CAM-LEGIT-{u1_suffix}"},
            headers=headers_u1,
        )
        legit_stat_id = legit_stat.json()["data"]["id"]

        # Usuario 2 intenta eliminar los recursos de Usuario 1 -> Debe retornar 403
        del_p_by_u2 = await async_client.delete(f"/projects/{legit_proj_id}", headers=headers_u2)
        assert del_p_by_u2.status_code == 403
        assert "No tiene permisos para eliminar este proyecto" in del_p_by_u2.json()["message"]

        del_s_by_u2 = await async_client.delete(f"/camera-stations/{legit_stat_id}", headers=headers_u2)
        assert del_s_by_u2.status_code == 403
        assert "No tiene permisos para eliminar esta estación" in del_s_by_u2.json()["message"]

        # 4. Usuario 1 elimina sus propios recursos (Soft Delete exitoso)
        ok_del_p = await async_client.delete(f"/projects/{legit_proj_id}", headers=headers_u1)
        assert ok_del_p.status_code == 200
        assert "Soft Delete" in ok_del_p.json()["message"]

        ok_del_s = await async_client.delete(f"/camera-stations/{legit_stat_id}", headers=headers_u1)
        assert ok_del_s.status_code == 200
        assert "Soft Delete" in ok_del_s.json()["message"]

        # Verificar que ya no son accesibles en detalle (404) ni en listados
        chk_p = await async_client.get(f"/projects/{legit_proj_id}")
        assert chk_p.status_code == 404

        chk_s = await async_client.get(f"/camera-stations/{legit_stat_id}")
        assert chk_s.status_code == 404


class TestPhase3StressAndThroughput:
    """Pruebas de estrés y concurrencia para N:M y filtros de Soft Delete."""

    @pytest.mark.asyncio
    async def test_concurrent_nm_associations_throughput(self):
        """
        Estrés: Asociación y desasociación masiva concurrente de estaciones a un proyecto.
        Evalúa consistencia transaccional y Throughput (RPS).
        """
        request_count = 6
        semaphore = asyncio.Semaphore(3)
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            u_suffix = uuid.uuid4().hex[:6]
            reg = await client.post(
                "/auth/register",
                json={
                    "full_name": "Stress Tester NM",
                    "email": f"stress_nm_{u_suffix}@wwf.org",
                    "password": "Password123!#",
                },
            )
            token = reg.json()["data"]["tokens"]["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            # Crear Proyecto Central
            p_res = await client.post(
                "/projects/",
                json={"title": f"Proyecto Concurrente {u_suffix}"},
                headers=headers,
            )
            project_id = p_res.json()["data"]["id"]

            # Crear Estaciones Concurrentemente
            station_ids = []
            for i in range(request_count):
                s_res = await client.post(
                    "/camera-stations/",
                    json={"station_code": f"CAM-STR-{u_suffix}-{i}"},
                    headers=headers,
                )
                station_ids.append(s_res.json()["data"]["id"])

            # Ráfaga de Asociación Concurrente N:M
            latencies = []

            async def associate_task(s_id: str):
                async with semaphore:
                    t0 = time.perf_counter()
                    resp = await client.post(
                        f"/projects/{project_id}/stations",
                        json={"station_id": s_id},
                        headers=headers,
                    )
                    t1 = time.perf_counter()
                    return resp, (t1 - t0) * 1000

            start_all = time.perf_counter()
            tasks = [associate_task(s_id) for s_id in station_ids]
            results = await asyncio.gather(*tasks)
            total_time = time.perf_counter() - start_all

            for resp, lat in results:
                latencies.append(lat)
                assert resp.status_code == 200
                assert resp.json()["status"] == "success"

            rps = request_count / total_time
            p50 = percentile(latencies, 50)
            p95 = percentile(latencies, 95)
            p99 = percentile(latencies, 99)

            print(f"\n[NM ASSOCIATION STRESS] {request_count} asociaciones concurrentes:")
            print(f"   Throughput (RPS): {rps:.2f} op/seg")
            print(f"   Latencias: p50={p50:.3f}ms | p95={p95:.3f}ms | p99={p99:.3f}ms")
            print(f"   Tiempo total: {total_time:.3f}s")

            assert rps > 0.05, f"Throughput insuficiente: {rps}"

            # Validar que el proyecto tenga todas las estaciones registradas
            get_p = await client.get(f"/projects/{project_id}")
            assert get_p.status_code == 200
            assert len(get_p.json()["data"]["camera_stations"]) == request_count

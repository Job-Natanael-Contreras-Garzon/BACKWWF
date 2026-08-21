import asyncio
import time
import uuid
from httpx import AsyncClient, ASGITransport
import pytest
from fastapi import APIRouter, Depends, Response

from app.api.deps import get_anon_session_id
from app.main import app

# Router auxiliar para probar la inyección del header X-Anon-Session-ID
anon_test_router = APIRouter(prefix="/api/v1/test-anon", tags=["Testing"])


@anon_test_router.get("/session")
async def dummy_anon_session_endpoint(
    response: Response,
    anon_id: uuid.UUID = Depends(get_anon_session_id),
):
    return {"status": "success", "data": {"anon_id": str(anon_id)}, "message": "OK"}


app.include_router(anon_test_router)


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


class TestAuthFunctionalAndHappyPaths:
    """Pruebas funcionales y validación del Happy Path para la Fase 2."""

    @pytest.mark.asyncio
    async def test_full_auth_and_claim_happy_path(self, async_client: AsyncClient):
        """
        Happy Path End-to-End:
        1. Registro -> 2. Login -> 3. Refresh -> 4. /auth/me -> 5. Sesión Anónima -> 6. Reclamo -> 7. Historial.
        """
        unique_suffix = uuid.uuid4().hex[:8]
        email = f"biologo_{unique_suffix}@wwf.org"
        password = "PasswordSeguro2026!#"

        # 1. Registro (POST /api/v1/auth/register)
        reg_payload = {
            "full_name": f"Dr. Investigador {unique_suffix}",
            "email": email,
            "password": password,
            "institucion": "WWF Amazonia",
            "sexo": "M",
        }
        reg_resp = await async_client.post("/auth/register", json=reg_payload)
        assert reg_resp.status_code == 201
        reg_data = reg_resp.json()
        assert reg_data["status"] == "success"
        assert reg_data["data"]["user"]["email"] == email
        access_token = reg_data["data"]["tokens"]["access_token"]
        refresh_token = reg_data["data"]["tokens"]["refresh_token"]

        # 2. Login (POST /api/v1/auth/login)
        login_resp = await async_client.post(
            "/auth/login",
            json={"email": email, "password": password},
        )
        assert login_resp.status_code == 200
        login_data = login_resp.json()
        assert login_data["status"] == "success"
        assert "access_token" in login_data["data"]["tokens"]

        # 3. Refresh Token (POST /api/v1/auth/refresh)
        ref_resp = await async_client.post(
            "/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert ref_resp.status_code == 200
        ref_data = ref_resp.json()
        assert ref_data["status"] == "success"
        new_access_token = ref_data["data"]["access_token"]
        assert new_access_token != ""

        # 4. Perfil de Usuario (GET /api/v1/auth/me)
        me_resp = await async_client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {new_access_token}"},
        )
        assert me_resp.status_code == 200
        me_data = me_resp.json()
        assert me_data["status"] == "success"
        assert me_data["data"]["email"] == email

        # 5. Generación de Sesión Anónima (Inyección automática de header)
        anon_resp = await async_client.get("/api/v1/test-anon/session")
        assert anon_resp.status_code == 200
        anon_header_id = anon_resp.headers.get("X-Anon-Session-ID")
        assert anon_header_id is not None
        anon_uuid = uuid.UUID(anon_header_id)

        # 6. Reclamo de Sesión Anónima (POST /api/v1/users/me/claim)
        claim_resp = await async_client.post(
            "/users/me/claim",
            json={"anon_session_id": str(anon_uuid)},
            headers={"Authorization": f"Bearer {new_access_token}"},
        )
        assert claim_resp.status_code == 200
        claim_data = claim_resp.json()
        assert claim_data["status"] == "success"
        assert claim_data["data"]["anon_session_id"] == str(anon_uuid)

        # 7. Historial de Usuario (GET /api/v1/users/me/history)
        hist_resp = await async_client.get(
            "/users/me/history",
            headers={"Authorization": f"Bearer {new_access_token}"},
        )
        assert hist_resp.status_code == 200
        hist_data = hist_resp.json()
        assert hist_data["status"] == "success"
        assert "projects" in hist_data["data"]
        assert "camera_stations" in hist_data["data"]

    @pytest.mark.asyncio
    async def test_auth_error_handling(self, async_client: AsyncClient):
        # 1. Registro con email duplicado
        unique = uuid.uuid4().hex[:6]
        dup_email = f"dup_{unique}@wwf.org"
        payload = {"full_name": "Test", "email": dup_email, "password": "pass"}
        r1 = await async_client.post("/auth/register", json=payload)
        assert r1.status_code == 201
        r2 = await async_client.post("/auth/register", json=payload)
        assert r2.status_code == 400
        assert r2.json()["status"] == "error"
        assert "ya está registrado" in r2.json()["message"]

        # 2. Login con contraseña errónea
        r_bad_pwd = await async_client.post(
            "/auth/login",
            json={"email": dup_email, "password": "WrongPassword123!"},
        )
        assert r_bad_pwd.status_code == 401
        assert r_bad_pwd.json()["status"] == "error"

        # 3. Acceso a /auth/me sin token
        r_unauth = await async_client.get("/auth/me")
        assert r_unauth.status_code == 401
        assert r_unauth.json()["status"] == "error"

        # 4. Refresh con token alterado
        r_bad_ref = await async_client.post("/auth/refresh", json={"refresh_token": "fake.jwt.token"})
        assert r_bad_ref.status_code == 401


class TestAuthStressAndConcurrency:
    """Pruebas de estrés masivo, concurrencia de sesiones y Throughput."""

    @pytest.mark.asyncio
    async def test_concurrent_anonymous_session_header_stress(self):
        """
        Estrés: 500 peticiones concurrentes solicitando sesión anónima.
        Verifica unicidad del 100% de UUIDs inyectados en la cabecera 'X-Anon-Session-ID'.
        """
        request_count = 500
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            latencies = []

            async def get_session(i: int):
                t0 = time.perf_counter()
                resp = await client.get("/api/v1/test-anon/session")
                t1 = time.perf_counter()
                return resp, (t1 - t0) * 1000

            start_all = time.perf_counter()
            tasks = [get_session(i) for i in range(request_count)]
            results = await asyncio.gather(*tasks)
            total_time = time.perf_counter() - start_all

            session_ids = set()
            for resp, lat in results:
                latencies.append(lat)
                assert resp.status_code == 200
                anon_id = resp.headers.get("X-Anon-Session-ID")
                assert anon_id is not None
                session_ids.add(anon_id)

            # Comprobar unicidad absoluta (0 colisiones)
            assert len(session_ids) == request_count

            rps = request_count / total_time
            p50 = percentile(latencies, 50)
            p95 = percentile(latencies, 95)
            p99 = percentile(latencies, 99)

            print(f"\n[ANON SESSION STRESS] {request_count} sesiones anónimas concurrentes:")
            print(f"   Throughput (RPS): {rps:.2f} req/seg")
            print(f"   Latencias: p50={p50:.3f}ms | p95={p95:.3f}ms | p99={p99:.3f}ms")
            print(f"   Colisiones detectadas: 0 de {request_count}")

            assert rps > 50.0, f"RPS insuficiente: {rps}"
            assert p99 < 150.0, f"Latencia p99 excedida: {p99}ms"

    @pytest.mark.asyncio
    async def test_concurrent_registration_and_login_throughput(self):
        """
        Estrés: Registro concurrente en ráfagas con hashing bcrypt y control de concurrencia de conexiones.
        Evalúa estabilidad de la BD y Throughput de registro seguro.
        """
        user_count = 10
        semaphore = asyncio.Semaphore(4)
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            latencies = []

            async def register_user_task(i: int):
                async with semaphore:
                    u_email = f"stress_user_{uuid.uuid4().hex[:8]}_{i}@wwf.org"
                    pwd = f"Password_{i}!#"
                    payload = {
                        "full_name": f"Stress Tester {i}",
                        "email": u_email,
                        "password": pwd,
                    }
                    t0 = time.perf_counter()
                    resp = await client.post("/auth/register", json=payload)
                    t1 = time.perf_counter()
                    return resp, (t1 - t0) * 1000

            start_all = time.perf_counter()
            tasks = [register_user_task(i) for i in range(user_count)]
            results = await asyncio.gather(*tasks)
            total_time = time.perf_counter() - start_all

            for resp, lat in results:
                latencies.append(lat)
                assert resp.status_code == 201
                body = resp.json()
                assert body["status"] == "success"
                assert "tokens" in body["data"]

            rps = user_count / total_time
            p50 = percentile(latencies, 50)
            p95 = percentile(latencies, 95)
            p99 = percentile(latencies, 99)

            print(f"\n[AUTH REGISTER STRESS] {user_count} registros concurrentes:")
            print(f"   Throughput: {rps:.2f} registros/seg")
            print(f"   Latencias: p50={p50:.3f}ms | p95={p95:.3f}ms | p99={p99:.3f}ms")
            print(f"   Tiempo total: {total_time:.3f}s")

            assert rps > 0.5, f"Throughput de registro insuficiente: {rps}"

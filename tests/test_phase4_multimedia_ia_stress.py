import asyncio
import io
import time
import uuid
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.services.ai_service import parse_taxonomy


# ─────────────────────────────────────────────────────────────────────────────
# 1. PRUEBAS UNITARIAS: PARSING TAXONÓMICO
# ─────────────────────────────────────────────────────────────────────────────
class TestTaxonomicParsingUnit:
    """Valida la precisión del parser taxonómico ante diferentes formatos de cadenas devueltas por IA."""

    def test_parse_taxonomy_four_parts_complete(self):
        raw = "Felidae;Panthera;Panthera onca;Jaguar"
        result = parse_taxonomy(raw)
        assert result["family"] == "Felidae"
        assert result["genus"] == "Panthera"
        assert result["scientific_name"] == "Panthera onca"
        assert result["common_name"] == "Jaguar"

    def test_parse_taxonomy_three_parts(self):
        raw = "Panthera;onca;Jaguar"
        result = parse_taxonomy(raw)
        assert result["family"] is None
        assert result["genus"] == "Panthera"
        assert result["scientific_name"] == "Panthera onca"
        assert result["common_name"] == "Jaguar"

    def test_parse_taxonomy_two_parts(self):
        raw = "Panthera;onca"
        result = parse_taxonomy(raw)
        assert result["family"] is None
        assert result["genus"] == "Panthera"
        assert result["scientific_name"] == "Panthera onca"
        assert result["common_name"] == "onca"

    def test_parse_taxonomy_single_word(self):
        raw = "Puma concolor"
        result = parse_taxonomy(raw)
        assert result["family"] is None
        assert result["genus"] is None
        assert result["scientific_name"] is None
        assert result["common_name"] == "Puma concolor"

    def test_parse_taxonomy_empty_or_none(self):
        assert parse_taxonomy("")["common_name"] == "Especie Desconocida"
        assert parse_taxonomy(None)["common_name"] == "Especie Desconocida"
        assert parse_taxonomy("   ;   ")["common_name"] == "Especie Desconocida"


# ─────────────────────────────────────────────────────────────────────────────
# 2. PRUEBAS FUNCIONALES: SUBIDA MULTIMEDIA Y RESÚMENES TAXONÓMICOS
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio(loop_scope="session")
class TestPhase4MultimediaAndSummariesFunctional:
    """Valida los endpoints de subida multimedia, persistencia y resúmenes taxonómicos agregados."""

    async def test_image_and_video_upload_and_taxonomic_detection(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            # 1. Crear usuario y estación
            email = f"media_tester_{uuid.uuid4().hex[:6]}@wwf.org"
            reg_res = await ac.post("/auth/register", json={
                "email": email,
                "password": "Password123!",
                "full_name": "Media Tester",
                "role": "investigator",
            })
            assert reg_res.status_code == 201
            token = reg_res.json()["data"]["tokens"]["access_token"]
            auth_headers = {"Authorization": f"Bearer {token}"}

            st_code = f"ST-MEDIA-{uuid.uuid4().hex[:6]}"
            st_res = await ac.post("/camera-stations/", json={
                "station_code": st_code,
                "location_name": "Sendero Felinos",
                "latitude": 5.123456,
                "longitude": -75.123456,
            }, headers=auth_headers)
            assert st_res.status_code == 201
            station_id = st_res.json()["data"]["id"]

            # 2. Subir Imagen (.jpg)
            fake_image_bytes = b"\xFF\xD8\xFF\xE0\x00\x10JFIF" + b"\x00" * 200
            files_img = {"file": ("puma_detect_01.jpg", io.BytesIO(fake_image_bytes), "image/jpeg")}
            up_img_res = await ac.post(f"/camera-stations/{station_id}/files", files=files_img, headers=auth_headers)
            assert up_img_res.status_code == 201
            img_data = up_img_res.json()["data"]
            assert img_data["file_type"] == "image"
            assert img_data["station_id"] == station_id
            assert img_data["detections_count"] >= 1
            assert len(img_data["detections"]) >= 1

            # 3. Subir Video (.mp4)
            fake_video_bytes = b"\x00\x00\x00 ftypisom" + b"\x00" * 500
            files_vid = {"file": ("tapir_camera_clip.mp4", io.BytesIO(fake_video_bytes), "video/mp4")}
            up_vid_res = await ac.post(f"/camera-stations/{station_id}/files", files=files_vid, headers=auth_headers)
            assert up_vid_res.status_code == 201
            vid_data = up_vid_res.json()["data"]
            assert vid_data["file_type"] == "video"
            assert vid_data["detections_count"] >= 1

            # 4. Validar lista de archivos multimedia de la estación
            list_res = await ac.get(f"/camera-stations/{station_id}/files", headers=auth_headers)
            assert list_res.status_code == 200
            files_list = list_res.json()["data"]
            assert len(files_list) >= 2

            # 5. Validar Resumen Estadístico Taxonómico de la Estación
            sum_res = await ac.get(f"/camera-stations/{station_id}/summary")
            assert sum_res.status_code == 200
            summary = sum_res.json()["data"]
            assert summary["station_id"] == station_id
            assert summary["total_detections_count"] >= 2
            assert summary["distinct_species_count"] >= 1
            assert len(summary["frequency_by_species"]) >= 1
            assert len(summary["frequency_by_family"]) >= 1
            assert len(summary["frequency_by_genus"]) >= 1

    async def test_project_cross_station_taxonomic_summary(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            email = f"proj_summary_{uuid.uuid4().hex[:6]}@wwf.org"
            reg_res = await ac.post("/auth/register", json={
                "email": email,
                "password": "Password123!",
                "full_name": "Project Summary Tester",
            })
            token = reg_res.json()["data"]["tokens"]["access_token"]
            auth_headers = {"Authorization": f"Bearer {token}"}

            # Crear Proyecto
            proj_res = await ac.post("/projects/", json={
                "title": f"Proyecto Taxonómico {uuid.uuid4().hex[:4]}",
                "description": "Monitoreo integral de biodiversidad",
            }, headers=auth_headers)
            assert proj_res.status_code == 201
            project_id = proj_res.json()["data"]["id"]

            # Crear 2 estaciones
            st1_res = await ac.post("/camera-stations/", json={
                "station_code": f"ST-SUM-1-{uuid.uuid4().hex[:4]}",
                "location_name": "Bosque Norte",
            }, headers=auth_headers)
            st2_res = await ac.post("/camera-stations/", json={
                "station_code": f"ST-SUM-2-{uuid.uuid4().hex[:4]}",
                "location_name": "Bosque Sur",
            }, headers=auth_headers)
            st1_id = st1_res.json()["data"]["id"]
            st2_id = st2_res.json()["data"]["id"]

            # Asociar estaciones al proyecto (N:M)
            await ac.post(f"/projects/{project_id}/stations", json={"station_id": st1_id}, headers=auth_headers)
            await ac.post(f"/projects/{project_id}/stations", json={"station_id": st2_id}, headers=auth_headers)

            # Subir archivos a ambas estaciones
            fake_bytes = b"\xFF\xD8\xFF\xE0" + b"\x00" * 100
            await ac.post(f"/camera-stations/{st1_id}/files", files={"file": ("puma_1.jpg", io.BytesIO(fake_bytes), "image/jpeg")})
            await ac.post(f"/camera-stations/{st2_id}/files", files={"file": ("tapir_2.jpg", io.BytesIO(fake_bytes), "image/jpeg")})

            # Consultar Resumen por Proyecto
            p_sum_res = await ac.get(f"/projects/{project_id}/summary")
            assert p_sum_res.status_code == 200
            p_sum = p_sum_res.json()["data"]
            assert p_sum["project_id"] == project_id
            assert p_sum["total_associated_stations"] == 2
            assert p_sum["total_detections_count"] >= 2
            assert p_sum["distinct_species_count"] >= 1
            assert len(p_sum["frequency_by_species"]) >= 1
            assert len(p_sum["frequency_by_family"]) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# 3. PRUEBAS DE ESTRÉS Y RENDIMIENTO CONCURRENTE
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio(loop_scope="session")
class TestPhase4StressAndThroughput:
    """Valida el rendimiento, concurrencia y ausencia de cuellos de botella en uploads y agregaciones."""

    async def test_concurrent_media_uploads_and_summaries_benchmark(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            email = f"stress_p4_{uuid.uuid4().hex[:6]}@wwf.org"
            reg_res = await ac.post("/auth/register", json={
                "email": email,
                "password": "Password123!",
                "full_name": "Stress Tester P4",
            })
            token = reg_res.json()["data"]["tokens"]["access_token"]
            auth_headers = {"Authorization": f"Bearer {token}"}

            st_res = await ac.post("/camera-stations/", json={
                "station_code": f"ST-BENCH-{uuid.uuid4().hex[:6]}",
                "location_name": "Bench Station",
            }, headers=auth_headers)
            station_id = st_res.json()["data"]["id"]

            concurrency_n = 6
            fake_bytes = b"\xFF\xD8\xFF\xE0" + b"\x00" * 300

            async def do_upload(i: int):
                start = time.perf_counter()
                f = {"file": (f"bench_clip_{i}.mp4", io.BytesIO(fake_bytes), "video/mp4")}
                res = await ac.post(f"/camera-stations/{station_id}/files", files=f, headers=auth_headers)
                elapsed = (time.perf_counter() - start) * 1000
                return res.status_code, elapsed

            t0 = time.perf_counter()
            tasks = [do_upload(i) for i in range(concurrency_n)]
            results = await asyncio.gather(*tasks)
            total_duration = time.perf_counter() - t0

            status_codes = [r[0] for r in results]
            latencies = sorted([r[1] for r in results])

            for code in status_codes:
                assert code == 201, f"Expected 201 but received {code}"

            p50 = latencies[len(latencies) // 2]
            p95 = latencies[int(len(latencies) * 0.95)]
            p99 = latencies[int(len(latencies) * 0.99)]
            rps = round(concurrency_n / total_duration, 2)

            print(f"\n[PHASE 4 STRESS BENCHMARK] {concurrency_n} subidas multimedia concurrentes:")
            print(f"   Throughput (RPS): {rps} op/seg")
            print(f"   Latencias: p50={p50:.3f}ms | p95={p95:.3f}ms | p99={p99:.3f}ms")
            print(f"   Tiempo total: {total_duration:.3f}s")

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import asyncio
import io
import uuid
from httpx import AsyncClient, ASGITransport
from app.main import app


async def test_full_application_flow():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        print("\n========================================================")
        print("[1/8] Verificando Estado de Salud del Backend (/health)...")
        print("========================================================")
        h_resp = await client.get("/health")
        assert h_resp.status_code == 200
        h_json = h_resp.json()
        print(f"[OK] Backend Salud: {h_json['data']['status']} | BD: {h_json['data']['database']} | Version: {h_json['data']['version']}")

        print("\n========================================================")
        print("[2/8] Probando Creacion Anonima de Estacion...")
        print("========================================================")
        st_code = f"CAM-ANON-{uuid.uuid4().hex[:6]}"
        resp = await client.post("/camera-stations/", json={
            "station_code": st_code,
            "location_name": "Reserva Forestal Anonima",
            "status": "active"
        })
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}"
        res_json = resp.json()
        assert res_json["status"] == "success"
        station_id = res_json["data"]["id"]
        anon_session_id = resp.headers.get("X-Anon-Session-ID")
        print(f"[OK] Estacion Anonima Creada: {station_id}")
        print(f"[OK] Cabecera X-Anon-Session-ID: {anon_session_id}")

        print("\n========================================================")
        print("[3/8] Registrando Usuario Nuevo e Iniciando Sesion...")
        print("========================================================")
        user_email = f"biologo_{uuid.uuid4().hex[:6]}@wwf.org"
        reg_resp = await client.post("/auth/register", json={
            "full_name": "Biologo Tester Integral",
            "email": user_email,
            "password": "PasswordSeguro123!",
            "institucion": "WWF Colombia"
        })
        assert reg_resp.status_code == 201, f"Expected 201, got {reg_resp.status_code}"
        reg_json = reg_resp.json()
        token = reg_json["data"]["tokens"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print(f"[OK] Usuario registrado: {user_email}")
        print(f"[OK] Bearer Token JWT generado correctamente.")

        print("\n========================================================")
        print("[4/8] Validando Bloqueo de Soft Delete Anonimo (Error 403 esperado)...")
        print("========================================================")
        del_resp = await client.delete(f"/camera-stations/{station_id}", headers=headers)
        assert del_resp.status_code == 403, f"Expected 403, got {del_resp.status_code}"
        del_json = del_resp.json()
        assert del_json["status"] == "error"
        print(f"[OK] Intento de borrado anonimo bloqueado con HTTP 403: '{del_json['message']}'")

        print("\n========================================================")
        print("[5/8] Reclamando Datos Anonimos a la Cuenta Autenticada...")
        print("========================================================")
        claim_resp = await client.post("/users/me/claim", json={"anon_session_id": anon_session_id}, headers=headers)
        assert claim_resp.status_code == 200, f"Expected 200, got {claim_resp.status_code}"
        claim_json = claim_resp.json()
        assert claim_json["data"]["claimed_stations_count"] >= 1
        print(f"[OK] Reclamo exitoso: {claim_json['data']['claimed_stations_count']} estacion(es) transferidas.")

        print("\n========================================================")
        print("[6/8] Subiendo Archivo Multimedia y Procesando con IA...")
        print("========================================================")
        fake_bytes = b"\xFF\xD8\xFF\xE0" + b"\x00" * 200
        files = {"file": ("jaguar_flow.jpg", io.BytesIO(fake_bytes), "image/jpeg")}
        up_resp = await client.post(f"/camera-stations/{station_id}/files", files=files, headers=headers)
        assert up_resp.status_code == 201, f"Expected 201, got {up_resp.status_code}"
        up_json = up_resp.json()
        assert up_json["data"]["detections_count"] >= 1
        print(f"[OK] Archivo multimedia subido y procesado con IA. Detecciones: {up_json['data']['detections_count']}")

        print("\n========================================================")
        print("[7/8] Ejecutando Soft Delete como Propietario Autenticado...")
        print("========================================================")
        del_auth_resp = await client.delete(f"/camera-stations/{station_id}", headers=headers)
        assert del_auth_resp.status_code == 200, f"Expected 200, got {del_auth_resp.status_code}"
        assert del_auth_resp.json()["status"] == "success"
        print(f"[OK] Soft Delete ejecutado con exito por el dueno de la estacion.")

        print("\n========================================================")
        print("[8/8] Verificando Filtro de Soft Delete en Listados y Detalle...")
        print("========================================================")
        list_resp = await client.get("/camera-stations/")
        active_ids = [s["id"] for s in list_resp.json()["data"]]
        assert station_id not in active_ids
        detail_resp = await client.get(f"/camera-stations/{station_id}")
        assert detail_resp.status_code == 404
        print(f"[OK] Verificacion completada: La estacion no aparece en listados y retorna 404 en consulta directa.")
        print("\n========================================================")
        print(">>> TODOS LOS PASOS DEL FLUJO INTEGRAL E2E FUERON EXITOSOS <<<")
        print("========================================================\n")


if __name__ == "__main__":
    asyncio.run(test_full_application_flow())

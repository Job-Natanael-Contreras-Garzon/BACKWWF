# 📘 Fase 5: Verificación, Pruebas Integrales y Despliegue

## 🎯 Objetivo de la Fase
Ejecutar la suite de pruebas integrales para validar que todo el flujo (Navegación Anónima -> Registro/Login JWT -> Reclamo de Datos -> Soft Delete con control de permisos -> Resúmenes Taxonómicos) opere según los requisitos técnicos, verificar la estandarización OpenAPI/Swagger UI y asegurar la preparación para el despliegue en Docker/Koyeb.

---

## 🧪 1. Script de Pruebas Integrales (`scratch/test_flow.py`)

Crear un script de prueba de flujo completo en la carpeta `scratch/` o suite de `pytest` para verificar el contrato de la API:

```python
import asyncio
import httpx

BASE_URL = "http://localhost:8000/api/v1"

async def test_full_application_flow():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        print("\n🚀 [1/6] Probando Creación Anónima...")
        # 1. Crear estación en modo anónimo (Sin Token JWT)
        resp = await client.post("/camera-stations/", json={
            "station_code": "CAM-ANON-01",
            "location_name": "Reserva Forestal Anónima",
            "status": "active"
        })
        assert resp.status_code == 201
        res_json = resp.json()
        assert res_json["status"] == "success"
        station_id = res_json["data"]["id"]
        anon_session_id = resp.headers.get("X-Anon-Session-ID")
        print(f"✅ Estación Anónima Creada: {station_id} | Session ID: {anon_session_id}")

        # 2. Intentar Soft Delete de recurso anónimo -> Debe retornar HTTP 403 Forbidden
        print("\n🚀 [2/6] Validando Bloqueo de Soft Delete Anónimo (Error 403 esperado)...")
        del_resp = await client.delete(f"/camera-stations/{station_id}")
        assert del_resp.status_code == 403
        del_json = del_resp.json()
        assert del_json["status"] == "error"
        print(f"✅ Intento de borrado anónimo bloqueado correctamente: {del_json['message']}")

        # 3. Registrar un usuario nuevo
        print("\n🚀 [3/6] Registrando Usuario Nuevo...")
        reg_resp = await client.post("/auth/register", json={
            "full_name": "Biólogo Tester",
            "email": f"tester_{station_id[:6]}@wwf.org",
            "password": "PasswordSeguro123!",
            "institucion": "WWF Test"
        })
        assert reg_resp.status_code == 201
        reg_json = reg_resp.json()
        token = reg_json["data"]["tokens"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("✅ Usuario registrado exitosamente y Token JWT obtenido.")

        # 4. Reclamar datos anónimos
        print("\n🚀 [4/6] Reclamando Datos Anónimos a la Cuenta...")
        claim_resp = await client.post("/users/me/claim", json={"anon_session_id": anon_session_id}, headers=headers)
        assert claim_resp.status_code == 200
        claim_json = claim_resp.json()
        assert claim_json["data"]["claimed_stations_count"] >= 1
        print("✅ Reclamo exitoso: Estación transferida al usuario autenticado.")

        # 5. Intentar Soft Delete ahora como dueño autenticado -> Debe ser Exitoso
        print("\n🚀 [5/6] Ejecutando Soft Delete como Propietario Autenticado...")
        del_auth_resp = await client.delete(f"/camera-stations/{station_id}", headers=headers)
        assert del_auth_resp.status_code == 200
        assert del_auth_resp.json()["status"] == "success"
        print("✅ Soft Delete ejecutado con éxito.")

        # 6. Validar que la estación ya no aparece en los listados (is_deleted = True)
        print("\n🚀 [6/6] Verificando Filtro de Soft Delete en Listados...")
        list_resp = await client.get("/camera-stations/")
        active_ids = [s["id"] for s in list_resp.json()["data"]]
        assert station_id not in active_ids
        print("✅ Verificación completada: La estación fue borrada lógicamente.")

if __name__ == "__main__":
    asyncio.run(test_full_application_flow())
```

---

## 🔍 2. Checklist de Verificación Swagger UI / OpenAPI

1. Acceder a `http://localhost:8000/docs`.
2. Verificar que aparezca el botón **Authorize** en la esquina superior derecha para ingresar `Bearer <token>`.
3. Validar que todos los schemas de respuesta muestren la envoltura:
   ```json
   {
     "status": "success",
     "data": { ... },
     "message": "string"
   }
   ```
4. Confirmar que los endpoints usen estrictamente nombres en **inglés** (`/auth`, `/users`, `/projects`, `/camera-stations`, `/species`).

---

## 📦 3. Verificación de Despliegue (Docker / Koyeb)

1. **Variables de Entorno Mínimas en Producción:**
   - `DATABASE_URL`
   - `SECRET_KEY`
   - `REFRESH_SECRET_KEY`
   - `ACCESS_TOKEN_EXPIRE_MINUTES`
   - `REFRESH_TOKEN_EXPIRE_DAYS`
   - `AI_SERVICE_URL`
2. **Construcción de Imagen Docker:**
   ```bash
   docker build -t fauna-backend:v4.0 .
   docker run -p 8000:8000 --env-file .env fauna-backend:v4.0
   ```

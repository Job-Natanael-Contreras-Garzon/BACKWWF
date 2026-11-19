---

kanban-plugin: board

---

## 📋 Backlog (S1 - Fundaciones)

- [x] **STD-07** · Settings pydantic validado al arrancar + `.env.example` (PR #1 `BUG-01`) @Job #p0 📅 2026-11-09
- [x] **BE-51** · [SEGURIDAD P0] Cerrar exposición `GET /users` y proteger endpoints (PR #2 `BUG-02`; falta migrar gestión admin a `/admin/users`) @Job #p0 📅 2026-11-09
- [ ] **STD-01** · Envoltura estándar `ApiResponse[T]` en `core/responses.py` @Job #p0 📅 2026-11-10
- [ ] **STD-03** · Jerarquía `AppError`, catálogo de códigos y handlers globales @Job #p0 📅 2026-11-11
- [ ] **BE-14** · Autenticación JWT con rotación de refresh tokens y detección de reutilización @Job #p0 📅 2026-11-12
- [ ] **BE-02** · Inyección de dependencia `get_owner` (usuario o sesión anónima) @Job #p0 📅 2026-11-13
- [ ] **BE-03** · Cliente HTTP de IA real (`httpx`), timeout 180s y eliminación de fallback falso *(🚧 v0 `SPIKE-01` en PR #4; falta alinear `ai_contract.py` al `contract.py` final `:8001` sin `geofence` y conectar pipeline real)* @Job #p0 📅 2026-11-14


## ⚙️ Sprint S2 (Sesiones, Colas y Multimedia)

- [ ] **BE-11** · Prefijo global `/api/v1` en todos los routers @Job #p0 📅 2026-11-16
- [ ] **BE-01** · Sesión anónima con hash del token y reclamo atómico `/anon-sessions/claim` @Job #p0 📅 2026-11-17
- [ ] **BE-60** · Infraestructura de cola con Redis + `arq` + servicio worker @Job #p0 📅 2026-11-18
- [ ] **BE-13** · Lotes y subida archivo por archivo (`BatchItem`) con respuesta 202 `queued` @Job #p0 📅 2026-11-19
- [ ] **BE-05** · Procesamiento efímero en temporal + `LocalStorage` de fotogramas evidencia @Job #p0 📅 2026-11-20
- [ ] **BE-21** · Validador de medios (formatos `formats.py`, lectura duración `ffprobe` para warning `VIDEO_TRUNCATED` > 15s `F1-D10`, MIME binario, 100 MP) @Job #p0 📅 2026-11-21


## 🚀 En Progreso

- [ ] Creación de plantillas de Historias de Usuario (`HU-STD-07`, `HU-BE-51`)
- [ ] Configuración de entorno local con Docker Compose (`db`, `redis`, `backend`, `ia-fake`)


## 🔍 En Revisión / QA

- [ ] Validación de contratos `API_BACK_FRONT.md` y `API_IA_BACK.md` con Diego y Miguel


## ✅ Terminado (Hitos Alcanzados)

- [x] Análisis integral de arquitectura y requerimientos WWF (TDR)
- [x] Instalación de Obsidian y configuración de bóveda con Dataview, Kanban, Canvas, Excalidraw, Tasks y Templater


%% kanban:settings
```
{"kanban-plugin":"board","list-collapse":[false,false,false,false,false]}
```
%%

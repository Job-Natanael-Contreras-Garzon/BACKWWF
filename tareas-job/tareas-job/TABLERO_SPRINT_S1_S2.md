---

kanban-plugin: board

---

## 📋 Backlog (S1 - Fundaciones)

- [ ] **STD-07** · Settings pydantic validado al arrancar + `.env.example` @Job #p0 📅 2026-11-09
- [ ] **BE-51** · [SEGURIDAD P0] Cerrar exposición `GET /users` y proteger endpoints @Job #p0 📅 2026-11-09
- [ ] **STD-01** · Envoltura estándar `ApiResponse[T]` en `core/responses.py` @Job #p0 📅 2026-11-10
- [ ] **STD-03** · Jerarquía `AppError`, catálogo de códigos y handlers globales @Job #p0 📅 2026-11-11
- [ ] **BE-14** · Autenticación JWT con rotación de refresh tokens y detección de reutilización @Job #p0 📅 2026-11-12
- [ ] **BE-02** · Inyección de dependencia `get_owner` (usuario o sesión anónima) @Job #p0 📅 2026-11-13
- [ ] **BE-03** · Cliente HTTP de IA real (`httpx`), timeout 180s y eliminación de fallback falso @Job #p0 📅 2026-11-14


## ⚙️ Sprint S2 (Sesiones, Colas y Multimedia)

- [ ] **BE-11** · Prefijo global `/api/v1` en todos los routers @Job #p0 📅 2026-11-16
- [ ] **BE-01** · Sesión anónima con hash del token y reclamo atómico `/anon-sessions/claim` @Job #p0 📅 2026-11-17
- [ ] **BE-60** · Infraestructura de cola con Redis + `arq` + servicio worker @Job #p0 📅 2026-11-18
- [ ] **BE-13** · Lotes y subida archivo por archivo (`BatchItem`) con respuesta 202 `queued` @Job #p0 📅 2026-11-19
- [ ] **BE-05** · Procesamiento efímero en temporal + `LocalStorage` de fotogramas evidencia @Job #p0 📅 2026-11-20
- [ ] **BE-21** · Validador de medios (duración ≤ 15s con tolerancia +0.5s, MIME binario) @Job #p0 📅 2026-11-21


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

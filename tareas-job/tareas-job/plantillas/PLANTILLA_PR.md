<!-- Copiar a .github/pull_request_template.md en cada repo -->
## Qué hace este PR
<!-- 1–3 líneas -->

**HU:** `docs/specs/HU-<ID>-<slug>.md` · **Tarea:** <BE-xx / FE-xx / IA-xx / DS-xx> · **UT incluidas:** UT-… · **Flujos:** FL-… · **Casos borde:** CB-…

## Criterios de aceptación cubiertos
| CA | Test |
|---|---|
| CA-1 | `test_…` |

## ¿Cambia el contrato, el catálogo de errores o algo de seguridad?
- [ ] No
- [ ] Sí → requiere la aprobación de **Diego** y aviso a la contraparte. Detalle: …

## Cómo probarlo
<!-- Pasos para el revisor: comandos, datos semilla, capturas o un GIF si es de UI -->

## Lista de revisión (la marca el autor; la verifica el revisor)
**Funcional**
- [ ] Cumple todos los CA de la HU y cada uno tiene su test
- [ ] Respeta el contrato (nombres, tipos, códigos, envoltura)
- [ ] Cubre los CB-xx asignados

**Código**
- [ ] Capas respetadas; sin lógica de negocio en el router o el componente
- [ ] Nombres claros, funciones cortas, sin duplicación ni código comentado
- [ ] Errores con su código del catálogo; sin `except` ni `catch` vacíos
- [ ] Sin N+1; listados paginados
- [ ] Logs con `flow` y `event`, sin datos sensibles

**Seguridad**
- [ ] Permisos verificados en el back; ubicación según DD-17
- [ ] Ninguna entrada del usuario llega a SQL, a la *shell* ni a rutas de archivo
- [ ] Sin secretos en el código ni en los logs

**Entrega**
- [ ] CI en verde (lint, tipos, tests, build, auditoría)
- [ ] Cobertura dentro de los mínimos
- [ ] `.env.example`, migración y documentación actualizados (si aplica)

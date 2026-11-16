# HU-<ID> · <Título corto>

> **Estado:** Borrador | Aprobada | En curso | En revisión | Terminada
> **Responsable:** <nombre> · **Revisor de la spec:** Diego · **Semana / hito:** S<n> / H<n>
> **PR(s):** <enlaces cuando existan>

## 1. Historia
**Como** <rol: investigador | visitante anónimo | administrador | investigador de campo | equipo de desarrollo>,
**quiero** <acción>,
**para** <beneficio>.

## 2. Origen
- **Tarea del plan:** <BE-xx / FE-xx / IA-xx / DS-xx / STD-xx>
- **Flujos:** <FL-xx> · <FD Xn>
- **Casos borde:** <CB-xx, …>
- **Contrato:** <API §n / IA §n / PKG §n>
- **Decisiones relacionadas:** <DD-xx>

## 3. Alcance
**Incluye:**
- …

**No incluye** (explícito):
- …

## 4. Dependencias
| Tipo | Qué | Tarea / dueño | Estado |
|---|---|---|---|
| ⛔ Necesita | <endpoint, función de la IA, archivo…> | <BE-xx · Job> | Disponible / Pendiente |
| 🔁 Mientras tanto | <ia-fake / MSW / fixture> | <IA-22 · Diego> | |
| ➡️ Desbloquea | <qué espera esta HU> | <FE-xx · Miguel> | |

## 5. Criterios de aceptación
> Uno por comportamiento, con datos concretos. Cubren: el camino feliz, cada error del contrato, cada CB asignado, los permisos y lo no funcional. **Cada CA tiene al menos un test (§8).**

```gherkin
CA-1 · <nombre>
  Dado <contexto con datos concretos>
  Cuando <acción>
  Entonces <resultado observable>
    Y <otro resultado>

CA-2 · <nombre>
  Dado …
  Cuando …
  Entonces …
```

## 6. Diseño técnico
- **Archivos o módulos nuevos o modificados:**
  - `app/services/xxx.py`: `XxxService.metodo(owner, …) -> …`
  - `src/features/xxx/Componente.jsx`
- **Base de datos** (migración): <tablas, columnas, índices o "ninguno">
- **Configuración** (variables nuevas en `.env.example`): <o "ninguna">
- **Códigos de error usados:** <del catálogo STD §6>
- **Eventos de log:** <`dominio.accion.resultado`>
- **Decisiones de diseño y alternativas descartadas:** …

## 7. Unidades de trabajo
| UT | Descripción | CA que cubre | Estimación | Estado |
|---|---|---|---|---|
| UT-1 | … | CA-… | <h> | ☐ |
| UT-2 | … | CA-… | <h> | ☐ |

## 8. Plan de pruebas
| CA | Nivel (unit / integración / contrato / e2e) | Nombre del test | Archivo |
|---|---|---|---|
| CA-1 | integración | `test_…` | `tests/api/test_xxx.py` |
| CA-2 | unit | `test_…` | `tests/services/test_xxx.py` |
| CA-n | e2e | `…` | `e2e/x.spec.ts` |

## 9. Riesgos y preguntas abiertas
| # | Pregunta o riesgo | Responsable de resolverlo | Resolución |
|---|---|---|---|
| 1 | … | … | … |

## 10. Cierre (DoD)
- [ ] Todos los CA pasan con tests automatizados
- [ ] PR fusionado en `develop` con CI en verde y revisión aprobada
- [ ] Verificado contra lo real en el hito H<n>
- [ ] Contrato y documentos actualizados (si hubo cambios) y la contraparte avisada

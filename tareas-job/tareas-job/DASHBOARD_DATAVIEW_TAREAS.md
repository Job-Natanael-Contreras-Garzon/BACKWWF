# 📊 Panel de Control y Consultas (Dataview & Tasks)

> [!TIP] Este archivo utiliza **Dataview** y **Tasks** para consultar automáticamente el estado de las especificaciones, flujos y tareas del proyecto CETERIS404 / WWF.

---

## 📌 1. Estado de Tareas Pendientes (Plugin Tasks)

Consulta en vivo de todas las tareas pendientes del proyecto clasificadas por prioridad:

```tasks
not done
short mode
```

---

## 📋 2. Tareas Críticas de Backend (Prioridad P0)

```tasks
not done
description includes #p0
```

---

## 📑 3. Mapa de Especificaciones y Documentos Clave (Dataview)

Consulta de todos los documentos Markdown de la bóveda con su tamaño y fecha de modificación:

```dataview
TABLE file.size AS "Tamaño (Bytes)", file.mtime AS "Última Edición"
FROM ""
WHERE file.name != "DASHBOARD_DATAVIEW_TAREAS"
SORT file.mtime desc
LIMIT 15
```

---

## 🔍 4. Contratos de Integración

```dataview
TABLE file.folder AS "Ubicación", file.name AS "Documento de Contrato"
FROM "contratos"
SORT file.name asc
```

---

## 🏷️ 5. Flujos del Sistema y Casos Borde

```dataview
LIST
FROM "flujos"
SORT file.name asc
```

---

## 💡 Ejemplos de Consultas Útiles para tu Día a Día

### Ver todas las Historias de Usuario terminadas
```markdown
​```dataview
TABLE estado, sprint, responsable
FROM "docs/specs"
WHERE estado = "Terminada"
​```
```

### Contar tareas pendientes por responsable
```markdown
​```dataviewjs
let tasks = dv.pages().file.tasks.where(t => !t.completed);
let byAssignee = {};
for (let t of tasks) {
    let match = t.text.match(/@(\w+)/);
    let name = match ? match[1] : "Sin asignar";
    byAssignee[name] = (byAssignee[name] || 0) + 1;
}
dv.table(["Responsable", "Tareas Pendientes"], Object.entries(byAssignee));
​```
```

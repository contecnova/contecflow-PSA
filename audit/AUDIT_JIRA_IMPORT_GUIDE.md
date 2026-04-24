# AUDIT Jira CSV Import Guide

## 1) Pasos para importar en Jira (CSV)
1. Ve a **Jira Settings** (icono de engranaje).
2. Entra en **System**.
3. En la sección **Import and Export**, selecciona **External System Import**.
4. Elige **CSV**.
5. Sube `AUDIT_JIRA_IMPORT_READY.csv`.
6. Configura el mapeo de columnas (ver sección 2).
7. Ejecuta una importación de prueba si está disponible y luego confirma la importación final.

## 2) Mapeo recomendado de columnas
- `Project Key` -> **Project Key**
- `Issue Type` -> **Issue Type**
- `Summary` -> **Summary**
- `Description` -> **Description**
- `Priority` -> **Priority**
- `Story Points` -> **Story Points**
- `Epic Name` -> **Epic Name**
- `Epic Link` -> **Epic Link**
- `Labels` -> **Labels**
- `Component/s` -> **Components**
- `Sprint` -> **Sprint**
- `Assignee` -> **Assignee**

## 3) Nota sobre Story Points (company-managed)
En proyectos **company-managed**, verifica que el campo **Story Points** esté habilitado en las pantallas de creación/edición y en el issue layout. Si no está visible, añádelo antes de importar para evitar que el valor se descarte.

## 4) Si Jira exige Epic Link por issue key
Si tu instancia no acepta valores de Epic Link por nombre/código funcional:
1. Importa primero solo las filas de tipo **Epic**.
2. Obtén las **issue keys** reales generadas (por ejemplo `PSA-123`).
3. Sustituye en las filas Story/Task el valor de `Epic Link` por esas issue keys.
4. Importa Stories/Tasks en una segunda pasada.

## 5) Checklist post-import
- Verificar filtros por sprint:
  - `Sprint = S1-Audit-Remediation`
  - `Sprint = S2-Backend-Refactor`
  - `Sprint = S3-Frontend-Debt`
- Revisar distribución por prioridad (Highest/High/Medium, etc.).
- Ejecutar sanity check manual de 5 issues:
  - Tipo correcto
  - Summary/Description correctos
  - Story Points presentes cuando aplica
  - Labels y Components coherentes
  - Enlace a Epic correcto

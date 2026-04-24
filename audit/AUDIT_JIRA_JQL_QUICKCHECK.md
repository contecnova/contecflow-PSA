# AUDIT JIRA Import - JQL Quickcheck

Consultas listas para copiar/pegar después del import.

## 12 queries JQL

### 1) Total Story importadas
```jql
project = PSA AND issuetype = Story
```

### 2) Total Task importadas
```jql
project = PSA AND issuetype = Task
```

### 3) Total Epic importadas
```jql
project = PSA AND issuetype = Epic
```

### 4) Prioridad Highest
```jql
project = PSA AND issuetype in (Story, Task) AND priority = Highest
```

### 5) Prioridad High
```jql
project = PSA AND issuetype in (Story, Task) AND priority = High
```

### 6) Prioridad Medium
```jql
project = PSA AND issuetype in (Story, Task) AND priority = Medium
```

### 7) Prioridad Low
```jql
project = PSA AND issuetype in (Story, Task) AND priority = Low
```

### 8) Issues por sprint (con sprint)
```jql
project = PSA AND issuetype in (Story, Task) AND Sprint is not EMPTY ORDER BY Sprint ASC
```

### 9) Issues sin sprint
```jql
project = PSA AND issuetype in (Story, Task) AND Sprint is EMPTY
```

### 10) Huérfanas sin Epic Link
```jql
project = PSA AND issuetype in (Story, Task) AND "Epic Link" is EMPTY
```

### 11) Story/Task sin Story Points
```jql
project = PSA AND issuetype in (Story, Task) AND "Story Points" is EMPTY
```

### 12) Issues sin labels
```jql
project = PSA AND issuetype in (Story, Task) AND labels is EMPTY
```

## Mini checklist post-import (8 pasos)
- 1. Confirmar que el total de Epics importadas coincide con el template de mapeo.
- 2. Confirmar que el total de Stories y Tasks coincide con el CSV PHASE2.
- 3. Revisar que no existan Stories/Tasks huérfanas sin Epic Link.
- 4. Validar distribución de prioridades esperada (Highest/High/Medium/Low).
- 5. Verificar que los sprints esperados tengan issues asignadas.
- 6. Revisar issues sin Story Points y completar estimaciones faltantes.
- 7. Revisar issues sin labels y aplicar etiquetado mínimo.
- 8. Tomar muestra aleatoria de issues para validar descripción, assignee y componentes.

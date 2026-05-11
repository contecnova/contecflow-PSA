#!/usr/bin/env bash
set -euo pipefail

MATRIX="DELETE_ENDPOINTS_MATRIX.csv"
FILES_LIST="/tmp/delete_files_from_matrix.txt"
OUT="DELETE_SOFT_DELETE_ABAC_MASTER_PLAN.md"

build_file_context() {
  local f="$1"
  local p="app/api/v1/${f}"
  local ep_models ep_services mods model_candidates=""

  ep_models=$(grep -E "^from app\.models|^import app\.models" "$p" 2>/dev/null || true)
  ep_services=$(grep -E "^from app\.services|^import app\.services" "$p" 2>/dev/null || true)

  mods=$(printf "%s\n" "$ep_services" | \
    sed -E 's/#.*$//' | \
    sed -E 's/[[:space:]]+as[[:space:]]+[A-Za-z_][A-Za-z0-9_]*//g' | \
    awk '
      /^from app\.services import / {
        sub(/^from app\.services import /, "")
        gsub(/[()]/, "")
        n=split($0,a,",")
        for(i=1;i<=n;i++){gsub(/^[[:space:]]+|[[:space:]]+$/, "", a[i]); if(length(a[i])) print a[i]}
      }
      /^from app\.services\./ {
        s=$0
        sub(/^from app\.services\./, "", s)
        sub(/[[:space:]]+import.*/, "", s)
        if(length(s)) print s
      }
      /^import app\.services\./ {
        s=$0
        sub(/^import app\.services\./, "", s)
        sub(/[[:space:]].*$/, "", s)
        if(length(s)) print s
      }
    ' | sort -u)

  model_candidates=$(printf "%s\n" "$ep_models" | sed -E 's/^[[:space:]]*//' || true)

  while IFS= read -r mod; do
    [[ -z "$mod" ]] && continue
    local sp1="app/services/${mod}.py"
    local sp2="app/services/${mod}/__init__.py"
    if [[ -f "$sp1" ]]; then
      model_candidates+=$'\n'"$(grep -E '^from app\.models|^import app\.models' "$sp1" 2>/dev/null || true)"
    elif [[ -f "$sp2" ]]; then
      model_candidates+=$'\n'"$(grep -E '^from app\.models|^import app\.models' "$sp2" 2>/dev/null || true)"
    fi
  done <<< "$mods"

  printf "%s\n" "$model_candidates" | \
    sed -E 's/#.*$//' | \
    sed -E 's/^[[:space:]]*from app\.models\.[A-Za-z0-9_\.]+ import[[:space:]]*//' | \
    sed -E 's/^[[:space:]]*import app\.models\.[A-Za-z0-9_\.]+.*$//' | \
    tr ',' '\n' | sed -E 's/[()]/ /g' | \
    sed -E 's/[[:space:]]+as[[:space:]]+[A-Za-z_][A-Za-z0-9_]*//g' | \
    sed -E 's/^[[:space:]]+|[[:space:]]+$//g' | \
    awk 'length($0)>0 && $0!="*" {print}' | sort -u | paste -sd ';' -
}

cat > "$OUT" <<'MD'
# Plan Maestro Exhaustivo - Soft-Delete + ABAC (182 DELETE endpoints)

Fecha: 9 de mayo de 2026  
Scope baseline: DELETE_ENDPOINTS_MATRIX.csv (182 endpoints)

## Metodologia y baseline
- Fuente principal: DELETE_ENDPOINTS_MATRIX.csv (182 endpoints, 83 archivos con DELETE).
- Validacion adicional: escaneo de decoradores @router.delete en codigo (detecta 187).  
  Para este plan se usa el baseline contractual de 182 endpoints ya auditados.
- Criterios por endpoint: ABAC, SoftDelete, Validacion de dependencias, Response OK, FilterActive.

## 1) Archivos con DELETE endpoints (endpoints + routers)
MD

while IFS= read -r f; do
  echo "- app/api/v1/${f}" >> "$OUT"
done < "$FILES_LIST"

cat >> "$OUT" <<'MD'

## 2) Tabla por archivo (TODOS los endpoints DELETE)

Columnas:
- Current Pattern: resumen operativo del endpoint.
- Needs is_active?: YES si SoftDelete=False.
- Needs enforce_abac?: YES si ABAC=False.
- Needs service fix?: YES si falla cualquiera de los 5 criterios.

MD

while IFS= read -r f; do
  models=$(build_file_context "$f")
  [[ -z "$models" ]] && models="(por definir en servicio de dominio)"

  echo "### [FILE] ${f}" >> "$OUT"
  echo "" >> "$OUT"
  echo "| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |" >> "$OUT"
  echo "|---|---|---|---|---|---|---|" >> "$OUT"

  awk -F',' -v ff="$f" -v mdl="$models" '
    function q(s){gsub(/^"|"$/, "", s); return s}
    NR>1 && $1==ff {
      ep=q($3); ab=$4; sd=$5; va=$6; ro=$7; fa=$8; pr=$10;
      if (sd=="False" && ab=="False") pat="Hard-delete + No ABAC";
      else if (sd=="False") pat="Hard-delete";
      else if (ab=="False") pat="Soft-delete + No ABAC";
      else pat="Soft-delete + ABAC";
      if (va=="False") pat=pat" + No dependency validation";
      if (ro=="False") pat=pat" + Bad response";
      needs_service=((ab=="False")||(sd=="False")||(va=="False")||(ro=="False")||(fa=="False"))?"YES":"NO";
      needs_active=(sd=="False")?"YES":"NO";
      needs_abac=(ab=="False")?"YES":"NO";
      printf("| %s (L%s) | %s | %s | %s | %s | %s | %s |\n", ep, $2, pat, needs_active, needs_abac, needs_service, mdl, pr);
    }
  ' "$MATRIX" >> "$OUT"
  echo "" >> "$OUT"
done < "$FILES_LIST"

awk -F',' 'NR>1{crit[$1]+=($4=="False"||$5=="False"); score[$1]+=($4=="False")+($5=="False")+($6=="False")+($7=="False")+($8=="False")} END{for(f in crit) if(crit[f]>0) printf "%s,%d,%d\n",f,crit[f],score[f]}' "$MATRIX" | sort -t',' -k2,2nr -k3,3nr -k1,1 | head -50 > /tmp/delete_top50_critical.csv

cat >> "$OUT" <<'MD'
## 3) Archivos criticos (40-50) con problemas
Seleccionados: Top 50 por cantidad de endpoints con gap en ABAC o soft-delete (desempate por score total de gaps).

MD

awk -F',' '{printf "%d. app/api/v1/%s (critical_endpoints=%s, score=%s)\n", NR, $1, $2, $3}' /tmp/delete_top50_critical.csv >> "$OUT"

cat >> "$OUT" <<'MD'

## 4) Detalle por archivo critico
Formato:
- Import enforce_abac
- Endpoints to fix (lineas)
- Service changes
- Model changes
- Migration needed
- Priority

MD

while IFS=',' read -r f crit score; do
  models=$(build_file_context "$f")
  [[ -z "$models" ]] && models="(por definir en servicio de dominio)"

  eps=$(awk -F',' -v ff="$f" 'NR>1 && $1==ff && ($4=="False"||$5=="False"||$6=="False"||$7=="False"||$8=="False") {gsub(/^"|"$/, "", $3); printf "%s (L%s); ", $3, $2}' "$MATRIX")
  [[ -z "$eps" ]] && eps="(sin endpoints con gap)"

  spath="app/api/v1/${f}"
  svc_lines=$( (grep -E "^from app\.services|^import app\.services" "$spath" 2>/dev/null || true) | sed 's/^[[:space:]]*//' | paste -sd '; ' - )
  [[ -z "$svc_lines" ]] && svc_lines="(endpoint realiza logica inline; crear/usar servicio de dominio)"

  mig="No"
  pr="P1"
  if awk -F',' -v ff="$f" 'NR>1 && $1==ff && $5=="False"{found=1} END{exit(found?0:1)}' "$MATRIX"; then
    mig="Yes"
    pr="P0"
  fi
  if awk -F',' -v ff="$f" 'NR>1 && $1==ff && $4=="False"{found=1} END{exit(found?0:1)}' "$MATRIX"; then
    pr="P0"
  fi

  {
    echo "[FILE] ${f}"
    echo "- Import: from app.core.abac_enforce import enforce_abac"
    echo "- Endpoints to fix: ${eps}"
    echo "- Service changes: ${svc_lines}; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {\"ok\": true, \"message\": \"...\"}"
    echo "- Model changes: ${models}"
    echo "- Migration needed: ${mig}"
    echo "- Priority: ${pr}"
    echo ""
  } >> "$OUT"
done < /tmp/delete_top50_critical.csv

cat >> "$OUT" <<'MD'
## 5) Checklist de dependencias y orden de migracion

### Checklist global (aplicar a todos los dominios)
- [ ] Inventariar modelos realmente persistidos por cada DELETE endpoint.
- [ ] Confirmar si el recurso es archivado (soft-delete) o revocado/purge legitimo.
- [ ] Agregar columna is_active BOOLEAN NOT NULL DEFAULT TRUE a cada modelo persistido que hoy hace hard-delete.
- [ ] Crear indices compuestos para unicidad con is_active cuando exista UNIQUE funcional.
- [ ] Actualizar servicios: reemplazar db.delete() por is_active=False + commit.
- [ ] Actualizar lecturas/listados con filtro is_active=True.
- [ ] Insertar enforce_abac() en todos los DELETE antes de mutar.
- [ ] Implementar validacion de dependencias activas antes de eliminar.
- [ ] Normalizar respuestas DELETE al contrato {"ok": true, "message": "..."}.
- [ ] Actualizar tests unitarios, API y regresion para soft-delete + ABAC.

### Orden recomendado de migracion (dependencias)
1. Core identity y acceso: users, abac, auth routers, mfa.
2. Configuracion transversal: settings, advanced_config, enterprise.
3. Estructura de proyectos: projects, clients, pipeline, tasks, epics, sprints, milestones.
4. Gobernanza y aprobaciones: approvals, grc, ai_governance.
5. Operacion y service desk: service_desk/*, bookings, capacity, changes.
6. Datos empresariales: cmdb, alm, contracts, profitability, revenue.
7. BI/Analytics: bi_* y report_builder, billing_reports.
8. Colaboracion e integraciones: collaboration/*, integrations, m365, scim, jira.

## 6) Top 10 + plan de ejecucion + LOC estimadas

### Top 10 archivos por numero de endpoints rotos
MD

awk -F',' 'NR>1{bad[$1]+=($4=="False"||$5=="False"||$6=="False"||$7=="False"||$8=="False")} END{for(f in bad) print f","bad[f]}' "$MATRIX" | sort -t',' -k2,2nr -k1,1 | head -10 | awk -F',' '{printf "%d. app/api/v1/%s -> %s endpoints rotos\n", NR, $1, $2}' >> "$OUT"

cat >> "$OUT" <<'MD'

### Top 10 modelos/dominios que mas requieren is_active
(estimado por endpoints con SoftDelete=False agrupados por archivo de endpoint)
MD

awk -F',' 'NR>1 && $5=="False"{c[$1]++} END{for(f in c) print f","c[f]}' "$MATRIX" | sort -t',' -k2,2nr -k1,1 | head -10 | awk -F',' '{printf "%d. %s -> %s endpoints sin is_active\n", NR, $1, $2}' >> "$OUT"

cat >> "$OUT" <<'MD'

### Plan de ejecucion por prioridad
- P0 (bloqueante): cualquier endpoint con Hard-delete o sin ABAC.
- P1 (alto): endpoint con soft-delete+ABAC pero sin validacion/filter/response.
- P2 (normalizacion): consistencia de respuesta y filtros globales, deuda de tests.

Batch sugeridos:
1. Batch A (P0-config): advanced_config, settings, enterprise, users, auth routers.
2. Batch B (P0-core work): projects, clients, pipeline, tasks, epics, sprints, milestones.
3. Batch C (P0-ops): service_desk/*, bookings, capacity, changes, approvals.
4. Batch D (P0-data): cmdb, alm, contracts, revenue, profitability.
5. Batch E (P1/P2-analytics): bi_*, report_builder, billing_reports.
6. Batch F (P1/P2-collab/integrations): collaboration/*, integrations, m365, scim, jira.

### LOC estimadas por archivo (heuristica)
Formula: 14 LOC por endpoint roto + 8 LOC por archivo para imports/helpers.
MD

awk -F',' 'NR>1{bad[$1]+=($4=="False"||$5=="False"||$6=="False"||$7=="False"||$8=="False")} END{for(f in bad){loc=bad[f]*14+8; print f","bad[f]","loc}}' "$MATRIX" | sort -t',' -k3,3nr -k2,2nr -k1,1 | awk -F',' '{printf "- app/api/v1/%s: ~%s LOC (%s endpoints rotos)\n",$1,$3,$2}' >> "$OUT"

cat >> "$OUT" <<'MD'

## Anexo: discrepancia 182 vs 187
- Escaneo directo de decoradores detecta 187 @router.delete.
- Baseline contractual auditado (matriz) contiene 182.
- Recomendacion: ejecutar reconciliacion final antes de cerrar QA para incluir/excluir explicitamente los 5 extras.
MD

echo "Generated ${OUT}"

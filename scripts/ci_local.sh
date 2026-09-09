#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# Contecflow PSA — verificación local de calidad
# Uso: ./scripts/ci_local.sh            (todo)
#      ./scripts/ci_local.sh --fast     (omite pytest y cobertura, ~2 min)
#      ./scripts/ci_local.sh --info     (solo los gates informativos)
#
# Este proyecto no usa CI/CD por decisión de diseño: los gates se pasan aquí, a
# mano, antes de commitear. Este script es el único sitio donde están reunidos.
#
# ── Bloqueantes vs informativos ───────────────────────────────────────────────
# BLOQUEANTES: verdes a fecha de la auditoría 2026-08. Si uno falla, es una
#   regresión que acabas de introducir.
# INFORMATIVOS: rojos hoy por deuda ya medida y documentada. No bloquean; cada
#   uno lleva el nº de hallazgo de la auditoría que hay que cerrar para
#   promoverlo. Promover = mover su llamada de `info` a `blocking`.
#
# ── Nota sobre el fallo que tenía la versión anterior ─────────────────────────
# Usaba `if cmd | tail -3; then ok; fi`, que evalúa el estado de salida de
# `tail`, NO el del comando: un pytest en rojo reportaba "✅ Backend tests".
# Aquí el estado se captura del propio comando (ver `run_gate`).
# ══════════════════════════════════════════════════════════════════════════════
set -uo pipefail   # sin -e: queremos seguir y dar el resumen completo al final

cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
PASS=0; FAIL=0; WARN=0
FAILED_GATES=()

# ── Intérprete Python ─────────────────────────────────────────────────────────
# Busca primero el venv del repo. La versión anterior solo probaba
# "$VIRTUAL_ENV/bin/python" (layout POSIX), así que en Windows caía al python
# del sistema — sin las dependencias instaladas.
PY_BIN=""
for candidate in \
  "${VIRTUAL_ENV:-}/bin/python" "${VIRTUAL_ENV:-}/Scripts/python.exe" \
  ".venv/bin/python" ".venv/Scripts/python.exe" \
  "venv/bin/python" "venv/Scripts/python.exe"; do
  if [[ -n "$candidate" && -x "$candidate" ]]; then PY_BIN="$candidate"; break; fi
done
if [[ -z "$PY_BIN" ]]; then
  PY_BIN="$(command -v python3 || command -v python || true)"
  [[ -n "$PY_BIN" ]] && echo -e "${YELLOW}⚠ Sin venv detectado; usando $PY_BIN${NC}"
fi
if [[ -z "$PY_BIN" ]]; then
  echo -e "${RED}No se encontró intérprete Python.${NC}"; exit 1
fi

step() { echo -e "\n${CYAN}══ $1 ══${NC}"; }

# run_gate <bloqueante|informativo> <nombre> <comando...>
# Captura la salida y el estado de salida REAL del comando.
run_gate() {
  local kind="$1"; local name="$2"; shift 2
  local out status
  out="$("$@" 2>&1)"; status=$?
  if [[ $status -eq 0 ]]; then
    echo -e "${GREEN}✅ $name${NC}"
    PASS=$((PASS+1))
  elif [[ "$kind" == "informativo" ]]; then
    echo -e "${YELLOW}⚠  $name — deuda conocida, no bloquea${NC}"
    echo "$out" | tail -4 | sed 's/^/     /'
    WARN=$((WARN+1))
  else
    echo -e "${RED}✗  $name${NC}"
    echo "$out" | tail -15 | sed 's/^/     /'
    FAIL=$((FAIL+1)); FAILED_GATES+=("$name")
  fi
}

MODE="${1:-all}"

# ── Gates bloqueantes ─────────────────────────────────────────────────────────
if [[ "$MODE" != "--info" ]]; then
  step "Bloqueantes"
  run_gate bloqueante "ruff (app + tests)"          "$PY_BIN" -m ruff check app tests
  run_gate bloqueante "árbol de dependencias"       "$PY_BIN" -m pip check
  # Los 2 CVEs ignorados no tienen remediación disponible hoy; están listados uno
  # a uno (no se desactiva el gate) para que un CVE NUEVO sí salga en rojo.
  #   PYSEC-2026-3447 setuptools — torch 2.11 exige setuptools<82.
  #   PYSEC-2026-1325 ecdsa      — sin versión corregida publicada; su único
  #     camino alcanzable ya se migró de python-jose a PyJWT.
  run_gate bloqueante "pip-audit" \
    "$PY_BIN" -m pip_audit -r requirements.txt \
      --ignore-vuln PYSEC-2026-3447 --ignore-vuln PYSEC-2026-1325

  if [[ "$MODE" != "--fast" ]]; then
    run_gate bloqueante "pytest (suite completa)" \
      "$PY_BIN" -m pytest tests -q --no-header -p no:cacheprovider -n auto
  else
    echo -e "${YELLOW}⚠  pytest omitido (--fast)${NC}"
  fi

  step "Bloqueantes — frontend"
  run_gate bloqueante "tsc (configuración base)" \
    bash -c 'cd frontend && npx tsc -p tsconfig.json --noEmit'
  run_gate bloqueante "vitest" \
    bash -c 'cd frontend && npx vitest run'
  run_gate bloqueante "build" \
    bash -c 'cd frontend && npm run build --silent'

  # eslint promovido a BLOQUEANTE (auditoría 2026-08, hallazgo 6). Al instalar
  # @typescript-eslint/parser aparecieron 80 errores que nunca se habían visto;
  # están todos corregidos, así que un error nuevo es una regresión.
  #
  # El tope de warnings es la línea base MEDIDA (1.966: sobre todo etiquetas de
  # accesibilidad y reglas del sistema de diseño, que el proyecto configuró como
  # avisos a propósito). Fijarlo así permite que baje y no que suba. Al reducir
  # la deuda, bajar este número — nunca subirlo.
  run_gate bloqueante "eslint (0 errores, warnings ≤ 1966)" \
    bash -c 'cd frontend && npx eslint src --ext .js,.jsx,.ts,.tsx --max-warnings 1966'

  # tsc estricto promovido a BLOQUEANTE (auditoría 2026-08, hallazgo 10). Se usa
  # el gate real (scripts/check_strict.mjs), no `tsc -p tsconfig.strict.json` a
  # secas: ese config comprueba también los ficheros IMPORTADOS por la whitelist,
  # y sus errores pertenecen a la migración pendiente, no a este gate.
  #
  # Corrección al informe de auditoría: dije "392 errores dentro de su propia
  # whitelist" y era falso — el gate reportaba 3. Los 389 restantes eran de
  # ficheros no incluidos, que el script descarta a propósito. También dije que
  # la estrategia de whitelist "no puede funcionar" por el grafo de imports: sí
  # funciona, porque el script filtra por fichero. Los 3 están corregidos.
  #
  # Para avanzar: añadir ficheros al `include` de tsconfig.strict.json y dejar
  # este gate en verde. Cuando cubra todo src/, activar `strict` en la base.
  run_gate bloqueante "tsc estricto (whitelist de tsconfig.strict.json)" \
    bash -c 'cd frontend && node scripts/check_strict.mjs'

  # npm audit promovido a bloqueante en nivel high (auditoría 2026-08, hallazgo
  # 17): nanoid era el único high y ya está corregido, así que un high nuevo es
  # una regresión.
  run_gate bloqueante "npm audit (0 high)" \
    bash -c 'cd frontend && npm audit --audit-level=high'

  # Cobertura de traducción (hallazgo 16). Se venden tres idiomas —castellano,
  # inglés y chino— y el suelo está en la cobertura MEDIDA, así que sólo puede
  # subir. Sin este gate, añadir claves al castellano sin traducirlas diluye los
  # otros dos en silencio y se vuelve al punto de partida: siete idiomas a
  # medias y ninguno completo.
  run_gate bloqueante "cobertura i18n (es/en/zh, no puede bajar)" \
    bash -c 'cd frontend && node scripts/check_i18n_coverage.mjs'

  # Claves duplicadas en los ficheros de idioma (hallazgo 16). Encontrado al
  # intentar cerrar la traducción: `en.mjs` tenía el namespace `client_portal`
  # declarado DOS VECES, y en JavaScript gana la última — así que 73 traducciones
  # escritas y presentes en el repositorio no llegaban al usuario. 204 en total.
  # Y en castellano `alm.subtitle` estaba declarada 13 veces, así que la pantalla
  # de Licencias y Activos mostraba el subtítulo de imputaciones.
  #
  # El gate de cobertura NO lo detecta: compara el objeto ya colapsado, donde el
  # duplicado es invisible. Éste lee el fichero como texto y sigue las llaves.
  run_gate bloqueante "sin claves i18n duplicadas" \
    bash -c 'cd frontend && node scripts/check_i18n_duplicates.mjs'

  # Dependencias estaticas de vendors grandes (hallazgo 19). El troceo por vendor
  # ya estaba bien hecho; el problema era QUIEN los importa: `route-misc` tenia un
  # import estatico de `vendor-plotly` (4.633 kB, el 38 % de todo el JS) porque
  # CMDBPage importaba la topologia de forma estatica. Abrir cualquier pagina de
  # ese chunk descargaba plotly entero.
  #
  # Necesita un build previo, asi que solo corre si existe dist/. En --fast no se
  # construye y el gate se salta: es correcto, no se puede medir lo que no hay.
  if [[ -d frontend/dist/assets ]]; then
    run_gate bloqueante "sin vendors grandes en dependencias estaticas" \
      bash -c 'cd frontend && node scripts/check_heavy_chunks.mjs'
  else
    echo "  (omitido: sin frontend/dist — ejecuta npm run build para medirlo)"
  fi
fi

# ── Gates informativos ────────────────────────────────────────────────────────
if [[ "$MODE" != "--fast" ]]; then
  step "Informativos (deuda medida, no bloquean)"

  # Deriva del entorno respecto a requirements.txt (hallazgo 22). `pip check`
  # sólo detecta CONFLICTOS declarados; no ve que lo instalado sea simplemente
  # distinto de lo fijado. Esa deriva silenciosa costó una sesión: pytest 8 en
  # lugar del 9 fijado dejaba a pytest sin arrancar, y fastapi 0.139 en lugar del
  # 0.135 volvió `include_router` perezoso, así que 2.051 rutas se veían como 9 y
  # 19 tests culpaban al producto de un fallo que no existía.
  #
  # INFORMATIVO a propósito PARA EL RESTO: quedan 16 paquetes con versión
  # distinta de la fijada, algunos con salto de versión MAYOR (numpy 1.26→2.5,
  # urllib3 2.7→1.26, pillow 12.3→10.4, redis 6.4→5.2). Forzarlos de golpe con
  # `pip install -r requirements.txt` puede romper la suite, y decidir cuál de
  # las dos versiones es la correcta exige probar cada una. Se deja MEDIDO.
  # Para promoverlo a bloqueante: alinear los 16 y verificar la suite.
  # BLOQUEANTE, y sólo para los tres del ejecutor de tests. La distinción es la
  # que importa: con `pytest` desalineado la suite no da otro resultado, es que
  # NO SE PUEDE EJECUTAR — `schemathesis` importa `_pytest.subtests`, que sólo
  # existe en pytest 9, así que con pytest 8 falla la carga de plugins y ningún
  # test llega a correr.
  #
  # Ha pasado DOS VECES, la segunda a mitad de una sesión de trabajo y después
  # de que la suite ya hubiera salido verde. Los tres no tienen salto de versión
  # mayor pendiente, así que alinearlos es seguro y no hay excusa para dejarlo
  # informativo.
  run_gate bloqueante "entorno: ejecutor de tests alineado" \
    "$PY_BIN" scripts/check_pinned_versions.py --solo-criticos

  run_gate informativo "entorno == requirements.txt (16 paquetes con deriva)" \
    "$PY_BIN" scripts/check_pinned_versions.py

  run_gate informativo "ruff scripts/ — hallazgo 17" \
    "$PY_BIN" -m ruff check scripts

  # Informativo aquí porque el gate que BLOQUEA es un test
  # (`tests/test_complejidad_no_empeora.py`, dentro de la suite de arriba). Esto
  # es el informe legible: el reparto de las funciones que quedan por encima de
  # 10, para poder elegir la siguiente sin tener que ir a buscarla.
  run_gate informativo "complejidad de app/ — hallazgo 18" \
    "$PY_BIN" scripts/audit_complejidad.py
  # lint:a11y ya vale algo: hasta la auditoría 2026-08 informaba "0 findings"
  # porque no podía parsear 304 de 343 ficheros. Con el parser instalado sus
  # números son reales (1.480 avisos de etiquetas), y son deuda de marcado que
  # requiere decidir la etiqueta correcta caso por caso.
  run_gate informativo "auditoría de accesibilidad (deuda de marcado)" \
    bash -c 'cd frontend && npm run --silent lint:a11y:report'
  # Informativo, no bloqueante: detecta literales sueltos sin traducir en el
  # marcado. El gate que SÍ bloquea es el de cobertura, arriba.
  run_gate informativo "check i18n (literales sueltos por traducir)" \
    bash -c 'cd frontend && npm run --silent check:i18n'
  # Los 3 moderate que quedan exigen saltos de versión MAYOR (echarts 5→6,
  # react-router-dom 6→7). Cada uno es una migración con riesgo real sobre las
  # 119 rutas lazy, así que se dejan medidos y no forzados. El gate bloqueante
  # en nivel high está entre los de arriba.
  run_gate informativo "npm audit (3 moderate: echarts 6, react-router 7)" \
    bash -c 'cd frontend && npm audit --audit-level=moderate'
fi

# ── Resumen ───────────────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════════════"
echo -e "  ${GREEN}✅ $PASS OK${NC}   ${YELLOW}⚠ $WARN deuda conocida${NC}   ${RED}✗ $FAIL fallos${NC}"
echo "══════════════════════════════════════════════════════════════"
if [[ $FAIL -eq 0 ]]; then
  echo -e "${GREEN}Gates bloqueantes: VERDE ✅${NC}"
  exit 0
fi
echo -e "${RED}Gates bloqueantes: ROJO ✗${NC}"
for g in "${FAILED_GATES[@]}"; do echo -e "${RED}  · $g${NC}"; done
exit 1

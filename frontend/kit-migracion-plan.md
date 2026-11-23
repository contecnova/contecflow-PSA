# Migración al kit — plan de la fase 2

> Generado por `node scripts/kit_pendientes.mjs` a partir de `kit-pendientes.json`. No se edita a mano:
> al terminar un fichero, se vuelve a ejecutar el script (encoge la lista y rehace este plan).

Cada fichero tiene un cupo de incumplimientos por regla (lo que tenía al crear la lista). ESLint y el test
`kitCssSinRestos` fallan si un fichero supera su cupo o si aparece en un fichero que no está en la lista.
Objetivo: dejar cada fichero a 0 y que salga de la lista. Piezas y cuándo usarlas: `src/components/ui/DESIGN_SYSTEM.md`, «Migración al kit».

## Recuento total

| Regla | Incumplimientos | Ficheros |
|---|---:|---:|
| `contec/sin-boton-nativo` | 0 | 0 |
| `contec/sin-tabla-propia` | 0 | 0 |
| `contec/sin-select-nativo` | 0 | 0 |
| `contec/sin-casilla-suelta` | 0 | 0 |
| `contec/sin-input-nativo` | 0 | 0 |
| `contec/sin-fieldset-propio` | 0 | 0 |
| CSS `mayusculas` | 0 | 0 |
| CSS `monoespaciada` | 0 | 0 |
| CSS `colorLiteral` | 0 | 0 |
| CSS `altoFijoControl` | 0 | 0 |
| **Total** | **0** | **0** |

## Reparto

| Bloque | Ficheros | Incumplimientos |
|---|---:|---:|
| A. Operador A–L | 0 | 0 |
| B. Operador M–Z (incluido service desk) | 0 | 0 |
| C. Portal de clientes, componentes compartidos y Ajustes | 0 | 0 |

Columnas: botón = `<button>`, tabla = `<table>`, select = `<select>`, casilla = checkbox/radio suelto,
fieldset = `<fieldset>` propio, MAYÚS = text-transform, mono = letra monoespaciada, color = hex/rgb literal,
alto px = `height` fijo en un control.

## Bloque A. Operador A–L — 0 ficheros, 0 incumplimientos

| Área | Fichero | botón | tabla | select | casilla | input | fieldset | MAYÚS | mono | color | alto px | Total |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|

## Bloque B. Operador M–Z (incluido service desk) — 0 ficheros, 0 incumplimientos

| Área | Fichero | botón | tabla | select | casilla | input | fieldset | MAYÚS | mono | color | alto px | Total |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|

## Bloque C. Portal de clientes, componentes compartidos y Ajustes — 0 ficheros, 0 incumplimientos

| Área | Fichero | botón | tabla | select | casilla | input | fieldset | MAYÚS | mono | color | alto px | Total |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|

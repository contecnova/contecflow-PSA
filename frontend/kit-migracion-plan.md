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
| `contec/sin-boton-de-icono-propio` | 0 | 0 |
| `contec/sin-tabla-propia` | 0 | 0 |
| `contec/sin-select-nativo` | 0 | 0 |
| `contec/sin-casilla-suelta` | 0 | 0 |
| `contec/sin-input-nativo` | 0 | 0 |
| `contec/sin-fieldset-propio` | 0 | 0 |
| CSS `mayusculas` | 0 | 0 |
| CSS `monoespaciada` | 0 | 0 |
| CSS `colorLiteral` | 0 | 0 |
| CSS `altoFijoControl` | 0 | 0 |
| CSS `minAltoCampo` | 9 | 7 |
| CSS `selectorDsInput` | 8 | 3 |
| CSS `botonDeIcono` | 0 | 0 |
| **Total** | **17** | **10** |

## Campos con etiqueta del kit (vigilante `campos`)

Un campo con etiqueta se escribe SIEMPRE con la prop del componente del kit (`<Select label=… />`, `<Input label=… />`…); el selector de
contexto de una pantalla (proyecto, cliente, sprint, unidad…) va SIEMPRE en `<SelectorDeContexto>`. Cupo que solo puede bajar:

| Regla | Incumplimientos | Ficheros |
|---|---:|---:|
| `campoConEtiquetaPropia` | 14 | 4 |
| `selectorDeContextoAMano` | 6 | 6 |

## Reparto

| Bloque | Ficheros | Incumplimientos |
|---|---:|---:|
| A. Operador A–L | 5 | 8 |
| B. Operador M–Z (incluido service desk) | 4 | 4 |
| C. Portal de clientes, componentes compartidos y Ajustes | 1 | 5 |

Columnas: botón = `<button>`, tabla = `<table>`, select = `<select>`, casilla = checkbox/radio suelto,
fieldset = `<fieldset>` propio, MAYÚS = text-transform, mono = letra monoespaciada, color = hex/rgb literal,
alto px = `height` fijo en un control.

## Bloque A. Operador A–L — 5 ficheros, 8 incumplimientos

| Área | Fichero | botón | botón icono | tabla | select | casilla | input | fieldset | MAYÚS | mono | color | alto px | min alto campo | .ds-input | botón icono CSS | Total |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| components/alm | `components/alm/almIntegracion.css` |  |  |  |  |  |  |  |  |  |  |  |  | 2 |  | 2 |
| pages/Documents | `pages/DocumentsPage.css` |  |  |  |  |  |  |  |  |  |  |  | 2 |  |  | 2 |
| pages/Epics | `pages/EpicsPage.css` |  |  |  |  |  |  |  |  |  |  |  | 1 |  |  | 1 |
| pages/Imputar | `pages/ImputarPage.css` |  |  |  |  |  |  |  |  |  |  |  | 2 |  |  | 2 |
| pages/IssueTypes | `pages/IssueTypesPage.css` |  |  |  |  |  |  |  |  |  |  |  | 1 |  |  | 1 |

## Bloque B. Operador M–Z (incluido service desk) — 4 ficheros, 4 incumplimientos

| Área | Fichero | botón | botón icono | tabla | select | casilla | input | fieldset | MAYÚS | mono | color | alto px | min alto campo | .ds-input | botón icono CSS | Total |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| pages/Profitability | `pages/ProfitabilityPage.css` |  |  |  |  |  |  |  |  |  |  |  | 1 |  |  | 1 |
| pages/Reports | `pages/ReportsPage.css` |  |  |  |  |  |  |  |  |  |  |  | 1 |  |  | 1 |
| pages/ResetPassword | `pages/ResetPasswordPage.css` |  |  |  |  |  |  |  |  |  |  |  | 1 |  |  | 1 |
| pages/Timesheets | `pages/TimesheetsPage.css` |  |  |  |  |  |  |  |  |  |  |  |  | 1 |  | 1 |

## Bloque C. Portal de clientes, componentes compartidos y Ajustes — 1 ficheros, 5 incumplimientos

| Área | Fichero | botón | botón icono | tabla | select | casilla | input | fieldset | MAYÚS | mono | color | alto px | min alto campo | .ds-input | botón icono CSS | Total |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| components/planificador | `components/planificador/planificador.css` |  |  |  |  |  |  |  |  |  |  |  |  | 5 |  | 5 |

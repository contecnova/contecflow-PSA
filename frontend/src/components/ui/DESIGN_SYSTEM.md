# Design System v2 — guía rápida

> La guía completa, medida y pensada para reutilizar en otras soluciones, es
> [docs/GUIA_DE_DISENO.md](../../../../docs/GUIA_DE_DISENO.md). Incluye lo que
> no se debe copiar y el contraste medido de cada tema.

**Objetivo**: una sola identidad visual y experiencia consistente en todas las
pantallas. Cuando construyas una página nueva o toques una existente, **usa
estos primitivos y clases** en lugar de re-inventar con estilos inline.

---

## Estándar visual (pasada de diseño 16-11-2026)

Lo que todas las pantallas cumplen (referencia: /projects, /absences, /cmdb, /m365):

- **Cabecera**: `<Page>` o `PageShell` + `PageHeader`, siempre con icono lucide (18), título = etiqueta del menú (`nav.*`), subtítulo. La acción principal va en la cabecera: `<Button icon={<Plus size={14} />}>`. Filtros en una barra bajo la cabecera (`ds-toolbar`), nunca en la cabecera. Contenido a todo el ancho.
- **Pestañas**: `Tabs`. Son siempre pastilla `md`: `variant` y `size` se aceptan pero **se ignoran**. Los emojis de una etiqueta de texto se quitan; el icono va en `icon` (lucide).
- **KPIs**: `KpiCard` dentro de `.ds-grid-stats`. Forma única: cifra grande sin monoespaciado, etiqueta `ds-eyebrow` debajo, línea `sub` opcional, icono lucide pequeño y apagado (un icono de texto/emoji se ignora). `accent/danger/warning` colorean solo la cifra. `onClick` (+ `ariaLabel`) la convierte en botón.
- **Vacíos**: `EmptyState` con icono lucide (`icon={<Folder size={28} />}`) o una clave (`folder`, `tasks`, `search`, `users`, `docs`, `chart`, `inbox`). Un emoji u otro texto **ya no se pinta**: sale el icono neutro (`inbox`) y en desarrollo avisa por consola. El `ctaLabel` sale como `Button` primario con `Plus`. `DataTable.emptyIcon` por defecto es `inbox`.
- **Botones**: `Button` con `primary | secondary | ghost | danger` (danger solo para destruir). `subtle` se pinta como `secondary`. Red de seguridad: un texto que empieza por «+ » pasa a icono `Plus` y los emojis del texto se quitan. Reenvía `aria-label`, `aria-expanded`, `aria-pressed`, `aria-controls` y `data-*`. Mismo alto que `Input`/`Select` en cada tamaño (`md` = 38 px).
- **Formularios**: `Input` acepta `maxLength`, `autoFocus`, `inputMode`, `disabled`, `min/max/step`. `Select` acepta `disabled`, `required`, `aria-label` y `placeholder` (`false` quita la opción vacía inicial). `FormField` marca el error con el icono `AlertTriangle`.
- **Iconos**: lucide siempre; nunca emojis (código ni diccionarios). `ViewToggle`, `Buscador` y `IconFR`/`IconCR` ya usan lucide.
- **Colores**: solo tokens de `index.css`; activo/seleccionado = `--accent` / `--accent-muted`; nada de `--surface-*` como color de texto.
- **Fechas**: `fmtDate`, `fmtDateTime`, `fmtMonth`, `formateadorDeFecha` (utils/helpers). Para editarlas, `CampoFecha`/`DateInput` (nunca el input nativo); para el periodo de un informe, `SelectorDePeriodo` + `usePeriodo`. El campo de fecha mide lo mismo que `Input`/`Select`/`Button md` (38 px) con cualquier clase; en una tabla densa se baja con `--uifecha-alto`.
- **Personas × días/semanas**: siempre `RejillaPersonaDia` + `NavegadorDeMes` (ver abajo).

Tests que lo vigilan: `__tests__/kitDiseno.test.tsx`, `__tests__/disenoSinEmojis.test.ts` (A–L, chat, kit) y `__tests__/disenoMZSinEmojis.test.ts` (M–Z).

---

## Migración al kit (16-11-2026) — una pieza para cada cosa

Fuera de `components/ui` no se escribe marcado propio para lo que resuelve el kit. ESLint lo exige (`contec/sin-*`, al final de esta guía) y el test `kitCssSinRestos` vigila las hojas de estilo. Lo que hoy incumple está en `frontend/kit-pendientes.json` (cupo por fichero que solo encoge) y su reparto en `frontend/kit-migracion-plan.md`.

| Necesitas… | Usa | No |
|---|---|---|
| Una acción con aspecto de botón | `Button` (`primary` la principal, `secondary`, `ghost`, `danger` solo para destruir) | `<button className="…">` |
| Un enlace que hace una acción («Ver todo», «Limpiar») | `Button variant="link"` | `<button className="link">` |
| Solo un icono | `IconButton ariaLabel="…"`; en tarjetas, filas y cabeceras, `IconButton variante="caja"` dentro de `.ui-acciones` (ver «Acciones de solo icono») | `<button><X/></button>`, `<Pulsable><Pencil/></Pulsable>`, `<Button icon={<X/>} />` sin texto, clases `*-icon-btn` |
| Tarjeta, elemento de lista o zona entera pulsable | `Pulsable className="tu-clase"` (botón sin aspecto, foco visible) | `<div onClick>` / `<button>` con reset propio |
| Elegir entre 2–5 vistas o modos | `Segmentado` (`ds-segmented`); con contenido por pestaña, `Tabs` | botones sueltos con `aria-pressed` |
| Filtro rápido conmutable o quitable | `Chip` (`activo`, `onClick`, `onQuitar`, `cuenta`, `color`) | `<button className="pill">` |
| Barra de filtros bajo la cabecera | `BarraDeFiltros acciones={…}` (`ds-toolbar`) | `<div className="mi-toolbar">` |
| Desplegable | `Select` (con `label` en formularios; `suelto` en barras y celdas; `tamano="sm"`; opciones por `options` o como hijos) | `<select>` (tampoco `<select className="ds-input">`) |
| Casilla / interruptor | `Checkbox` (`indeterminado`, `ayuda`, `tarjeta`), `Switch` (ajuste que se aplica al momento) | `<input type="checkbox">` |
| Varias opciones con leyenda | `GrupoDeOpciones` (`tipo` `radio` o `checkbox`; `forma` `tarjetas`, `lista` o `fila`) | `<fieldset>` + `<input type="radio">` |
| Estado / etiqueta | `StatusBadge kind="…"`, o `Badge label="approved"` / `<Badge tono="warning">…</Badge>` (la misma pastilla `ds-pill`) | `.mi-badge`, `.pill`, `.chip` propios |
| Tabla de datos | `Tabla` | `<table>` |
| Tabla con celdas combinadas o grupos de filas | `TablaSimple` (mismo estilo; dentro, `<thead>/<tbody>/<tr>/<td>`) + `CeldaEditable` si se edita | `<table className="contecflow-table">` |

### `<Tabla>` — la tabla común

Su estilo es `contecflow-table` (index.css) + `Tabla.css`. `DataTable` y `Table` son `Tabla` con su API de siempre.

```jsx
<Tabla etiqueta="Facturas" filas={facturas} claveDeFila={f => f.id}
  ordenable ordenInicial={{ col: 'fecha', dir: 'desc' }}          // o orden + onOrden (orden del servidor)
  columnas={[
    { key: 'numero', label: t('x.numero'), cabeceraDeFila: true },
    { key: 'cliente', label: t('x.cliente'), render: (_, f) => f.cliente.nombre, valorOrden: f => f.cliente.nombre },
    { key: 'importe', label: t('x.importe'), alinear: 'derecha', render: v => fmtMoney(v), pie: fmtMoney(total) },
    { key: 'estado', label: t('x.estado'), render: v => <Badge label={v} />,
      editar: { tipo: 'lista', valor: f => f.estado, opciones: ESTADOS, onGuardar: (f, v) => guardar(f.id, { estado: v }) } },
  ]}
  seleccion={sel} onSeleccion={setSel}      // casillas + «seleccionar todas»
  onFila={abrir} filaActiva={actual?.id}     // fila pulsable (Intro / Espacio)
  cargando={isLoading} vacio={{ icono: <Inbox size={28} />, titulo: t('x.vacio'), accion: <Button>…</Button> }}
  densidad="compacta" cabeceraFija />
```

- **Edición en el sitio** (`columna.editar`, tipos `texto`, `numero`, `lista`, `fecha`): clic, Intro o F2 abren el editor; Escape cancela; Intro o salir guardan; el foco vuelve a la celda. `onGuardar` solo se llama si el valor cambia. Es la de las vistas de trabajo del planificador, que ya la toman del kit.
- **Densidad**: `compacta` (listas largas, rejillas de edición), `normal`, `comoda`.
- **Pie**: `columna.pie` pinta una fila de totales; `pie` admite filas propias.
- Los clics en botones, enlaces y campos dentro de una fila no disparan `onFila`.

### `<Select>`

Un solo desplegable: `<select>` nativo con el estilo del kit, 38 px como `Input` y `Button md` (32 px con `tamano="sm"`). Mientras quede algún `<select className="ds-input">`, index.css le da el mismo alto.

```jsx
<Select label="Estado" value={v} onChange={e => setV(e.target.value)} options={[{ value: 'a', label: 'A' }]} />
<Select suelto aria-label="Estado" value={v} onChange={…} placeholder={t('x.todos')}>   {/* barra de filtros */}
  <optgroup label="…"><option value="a">A</option></optgroup>
</Select>
```

### Casillas y opciones

```jsx
<Checkbox checked={c} onChange={setC} label="Facturable" ayuda="Se incluye en la factura del mes" />
<Checkbox checked={todas} indeterminado={algunas} onChange={alternar} aria-label="Seleccionar todas" />
<Switch checked={activo} onChange={setActivo} label="Notificaciones por correo" />
<GrupoDeOpciones leyenda="Modo de facturación" valor={modo} onChange={setModo}
  opciones={[{ valor: 'hito', titulo: 'Por hito', ayuda: '…' }, { valor: 'tm', titulo: 'T&M' }]} />
<GrupoDeOpciones tipo="checkbox" forma="lista" leyenda="Canales" valor={canales} onChange={setCanales} opciones={…} />
```

`onChange` de `Checkbox`/`Switch` recibe `(marcado, evento)`.

### Barra de filtros, chips y segmentado

```jsx
<BarraDeFiltros acciones={<Button variant="link" onClick={limpiar}>{t('uikit.limpiar_todo')}</Button>}>
  <Buscador value={q} onChange={setQ} />
  <Select suelto aria-label="Estado" … />
  <Chip activo={soloMias} onClick={() => setSoloMias(v => !v)} cuenta={n}>Mías</Chip>
  <Segmentado aria-label="Vista" valor={vista} onChange={setVista} opciones={[{ valor: 'lista', etiqueta: 'Lista', icon: <List size={14} /> }, …]} />
</BarraDeFiltros>
```

### Alturas, campos con icono y filas de filtros (23-11-2026)

**Alturas.** Un solo alto por tamaño, en tokens de `index.css`: `--alto-control` (38 px), `--alto-control-sm` (32), `--alto-control-xs` (26), `--alto-control-lg` (44). `Input` y `Select` de una línea tienen alto **fijo** (no mínimo), igual que `SelectRico`, `CampoFecha`, `Segmentado`, `EntitySelect`, `FilterSelect` y `Button md`: en una fila miden lo mismo aunque la página les cambie el relleno. Las pantallas no fijan `height`/`min-height` de un campo (lo vigila `kitCssSinRestos`: `altoFijoControl`, `minAltoCampo`). Una tabla densa baja el alto con `tamano="sm"` o `--uifecha-alto`.

**Iconos dentro de un campo.** Nunca un icono absoluto a mano junto a un `Input` (al migrar a `Input`, el `<input>` dejó de llevar `ds-input` y las reglas `.x .ds-input { padding-left }` dejaron la lupa encima del texto). El kit lo hace:

```jsx
<Buscador value={q} onChange={setQ} placeholder={t('x.buscar')} />   // lupa + X para vaciar; onChange recibe el texto
<Buscador value={q} onChange={setQ} retardo={300} />                   // consulta al servidor: avisa al dejar de escribir
<Input icono={<Mail />} … />   <Input iconoFinal="%" … />   <Input onLimpiar={() => set('')} … />
```

El icono va centrado, a `--campo-icono` (14 px), `aria-hidden`, y el texto empieza en `--campo-pad-icono`. La X es un botón con nombre («Borrar la búsqueda») que devuelve el foco al campo. Excepción: la cabecera de una paleta (búsqueda global, buscar mensajes en el chat) lleva el icono junto a un campo sin caja.

**Selectores CSS.** El `Input`/`Textarea`/`Select` del kit no llevan `ds-input`: una regla `.ds-input.x` o `.zona .ds-input` no se aplica. El estilo propio de un campo va en la clase de `inputClassName` (el `<input>`) o de `className` (el contenedor `ui-field`: anchos y `flex`). `kitCssSinRestos` marca cualquier selector nuevo con `.ds-input` (`selectorDsInput`).

**Iconos de botón.** El tamaño lo pone el botón: xs 12 px, sm y md 14 px, lg 16 px, venga el `size` que venga en el icono.

**Filas de filtros anchas** (`BarraDeFiltros` / `ds-toolbar`, bajo la cabecera): el `Buscador` crece (240–480 px); cada desplegable mide lo que su opción más larga y no crece ni se encoge por debajo; la fila salta de línea antes que recortar. Si algún campo de la fila lleva etiqueta encima, toda la fila se alinea por abajo (las cajas quedan en la misma línea).

**Filtros en una columna o panel estrecho:** `FiltrosDeLista`. Buscador a todo el ancho; un filtro de 2–4 opciones cortas como `Segmentado` a todo el ancho con botones iguales; el resto, `SelectRico` en una rejilla de 2 columnas iguales. Nunca 3 o más desplegables en una fila que no tenga ancho para su texto más largo (referencia: Clientes).

```jsx
<FiltrosDeLista
  buscador={<Buscador value={q} onChange={setQ} placeholder={t('clients.buscar…')} />}
  segmentado={<Segmentado aria-label={t('x.tipo')} valor={tipo} onChange={setTipo} opciones={[…]} />}>
  <SelectRico aria-label={t('x.estado')} valor={estado} onChange={setEstado} opciones={[…]} />
  <SelectRico aria-label={t('x.orden')} valor={orden} onChange={setOrden} opciones={[…]} />
</FiltrosDeLista>
```

**Lista de un `<select>` nativo.** Sigue el tema: `color-scheme` (oscuro en `:root` y en los temas oscuros, claro en `light`) y las `option` con `--surface-2`/`--text-1`. Antes `:root` no declaraba `color-scheme` y el tema por defecto (oscuro) abría la lista blanca y azul del sistema. Para una lista con iconos, marcas o descripción, `SelectRico`.

### Acciones de solo icono: `IconButton variante="caja"` (23-11-2026)

Editar, borrar, más, copiar, historial o cerrar en una **tarjeta, fila o cabecera** son siempre el mismo botón, en toda la aplicación. Origen: en Licencias y activos → Proveedores, el botón de editar y el de borrar de cada tarjeta se estiraban en alto cuando el nombre ocupaba dos líneas (la cabecera era `display: flex` con `align-items: stretch` y el botón no tenía alto fijo).

```tsx
<div className="ui-acciones">
  <IconButton variante="caja" ariaLabel={t('alm.aria_edit_vendor', { name })} onClick={editar}><Pencil /></IconButton>
  <IconButton variante="caja" tono="peligro" ariaLabel={t('common.delete')} onClick={borrar}><Trash2 /></IconButton>
</div>
```

- **Caja:** cuadrado de tamaño fijo (ancho = alto), borde fino `--surface-4`, radio `--radius-md`, fondo transparente, icono `--text-2` centrado. Hover `--surface-3`; foco visible (anillo `--accent`); deshabilitado a opacidad 0,45. `aria-pressed="true"` lo pinta en acento.
- **Tono:** `neutro` (por defecto) · `peligro` (icono `--danger`, borde `--danger-border`; borrar, quitar, revocar) · `acento` (icono y borde de acento; guardar en línea, IA, asignar).
- **Tamaño:** `xs` 26 px con icono 12 · **`sm` 32 px con icono 16 (por defecto)** · `md` 38 px con icono 16 (`--alto-control-*`). El icono lo fija el CSS: el `size` del icono de lucide no cambia nada.
- **Por qué `sm`:** el título de una tarjeta (`--text-md`, ~20 px por línea) más su línea secundaria mide ~36 px; un botón de 32 px queda alineado arriba con el título sin dominar la tarjeta y coincide con `Button size="sm"`. `md` (38 px) solo junto a controles de 38 px (barras de herramientas); `xs` no se usa en tarjetas ni filas.
- **No se estira nunca:** `flex: none` y `align-self: flex-start`; las clases propias que se le sumen pueden colocarlo (`margin-left: auto`), no cambiar su tamaño.
- **Contenedor:** `.ui-acciones` (en `IconButton.css`): `display: flex`, `align-items: flex-start`, separación de 6 px, arriba a la derecha (`margin-left: auto` en un padre flex; `justify-content: flex-end` en un bloque o celda). La cabecera de la tarjeta lleva `align-items: flex-start`.
- `ariaLabel` es obligatorio (nombre accesible y tooltip).

**Excepciones justificadas** (con `/* eslint-disable-line contec/sin-boton-de-icono-propio -- excepción: motivo */` en la etiqueta): aspa dentro de un chip, casillas de selección, opciones de un segmentado, interruptores de palanca, estrellas y votos, lanzadores flotantes, botón de envío relleno del compositor, cromo de navegación del portal, controles del lienzo (Gantt), la barra del cuaderno (`cdn-boton`) y la videollamada (paleta `--call-*` propia).

**Lo vigilan:** la regla `contec/sin-boton-de-icono-propio` (`<button>`, `<Pulsable>` o `<Button>` con un icono de lucide como único hijo, o `<Button icon>` sin texto) y la comprobación CSS `botonDeIcono` (clases propias `*-icon-btn`, `*-btn-icon`, `*-boton-icono`… o retoques de `.icon-button--caja` fuera del kit). Cupo 0 en `kit-pendientes.json`.

### Hojas de estilo de las pantallas

Fuera de `components/ui` e `index.css` (lo comprueba `src/__tests__/kitCssSinRestos.test.ts`):

- Sin `text-transform: uppercase` ni `capitalize`: el texto va como se escribe. Un rótulo pequeño es `ds-eyebrow` (del kit).
- Sin letra monoespaciada en el CSS de las pantallas: cifras alineadas con `font-variant-numeric: tabular-nums`. El código que el usuario lee o copia (rutas de API, variables, comandos) usa la clase del kit `ds-codigo` (`ds-codigo--bloque` para bloques), la única con monoespaciada.
- Sin colores literales (`#hex`, `rgb()/rgba()/hsl()` con números): `var(--token)`; mezclas con `color-mix(in srgb, var(--x) 20%, transparent)`.
- Sin `height: NNpx` en botones, campos y selects, ni `min-height: NNpx` en campos: los controles del kit ya miden `--alto-control` (38) / `--alto-control-sm` (32).
- Sin selectores con `.ds-input` (los controles del kit no la llevan): la clase propia del campo.
- Sin clases propias de botón de icono (`*-icon-btn`, `*-btn-icon`, `*-boton-icono`…) ni retoques de `.icon-button--caja`: `IconButton variante="caja"` (comprobación `botonDeIcono`).

### Excepciones temporales

`kit-pendientes.json` da a cada fichero que hoy incumple un cupo por regla. ESLint (`eslint.config.js` pasa el cupo como opción de cada regla) y el test de CSS fallan si un fichero supera su cupo o si el incumplimiento aparece en un fichero fuera de la lista: nada nuevo puede incumplir y lo migrado no puede volver atrás. Tras migrar, `node scripts/kit_pendientes.mjs` encoge los cupos, saca los ficheros limpios y rehace el plan (nunca sube un cupo; si encuentra incumplimientos nuevos, los lista y sale con error). `--comprobar` solo comprueba; `--regenerar` rehace la lista desde cero (solo para crearla).

---

## Cuándo usar primitivos vs clases CSS

- **Primitivos** (`<Page>`, `<Section>`, `<Card>`, `<Button>`, `<StatusBadge>`,
  `<Modal>`, `<EmptyState>`, etc.) son la primera opción. Ya tienen estilos,
  comportamiento, accesibilidad y motion.
- **Clases CSS `.ds-*`** son para componer sin escribir un componente —
  útiles dentro de páginas para layout y elementos puntuales.
- **`style={{...}}` inline** sólo cuando lo anterior no aplica (un caso
  particular). Si ves que repites el mismo `style` en 3+ sitios, eso pide una
  utility class o un primitivo nuevo.

---

## Primitivos clave

```jsx
import {
  Page, Section, Card, Button, Input, Select, Spinner, Modal,
  StatusBadge, EmptyState, DataTable, Tabs, Toolbar, FormField,
  Avatar, Badge, KpiCard, IconButton,
} from '../../components/ui'
```

### `<Page>` — wrapper de página

Compone `PageShell` + `PageHeader` + body con stack. Sustituye al patrón:

```jsx
<PageShell>
  <PageHeader title="..." subtitle="..." />
  <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>...</div>
</PageShell>
```

por:

```jsx
<Page icon={<Icon size={20} />} title="..." subtitle="..." rightActions={<Button>...</Button>}>
  ...
</Page>
```

### `<Section>` — bloque dentro de página

```jsx
<Section title="Miembros" subtitle="3 activos" actions={<Button size="sm">Añadir</Button>}>
  ...contenido...
</Section>
```

`eyebrow={true}` para usar como eyebrow label (caption pequeña).

### `<Card>` — superficie

`<Card>` con `accent`, `onClick`, `style` props.  Para listas grandes prefiere
la clase `.ds-card` directamente — mismo aspecto, sin overhead de componente.

### `<StatusBadge>` — pill semántica

```jsx
<StatusBadge kind="success">Publicado</StatusBadge>   {/* verde */}
<StatusBadge kind="warning" dot>Pendiente</StatusBadge>
<StatusBadge kind="accent">Premium</StatusBadge>
```

Kinds: `neutral` (def), `success`, `warning`, `danger`, `info`, `accent`, `purple`.

### `<EmptyState>` — vacío

```jsx
<EmptyState
  icon={<GitBranch size={28} />}
  title="No hay datos"
  description="Crea uno desde cero o parte de una plantilla."
  action={<Button>Crear</Button>}
/>
```

### `<Modal>` — diálogo

Cierra con Esc + click-outside.  Soporta `width`, `subtitle`, header/footer.

### Modal / Drawer / PortalModal — cambios sin guardar (23-11-2026)

Incidencia de usuario: «al editar, si haces clic fuera del formulario, se cierra sin preguntar y se pierden los cambios». **Estándar:** si el usuario ha tocado algo, cerrar con **clic fuera, Escape o la X** pregunta «Tienes cambios sin guardar. ¿Descartarlos?» (**Descartar** / **Seguir editando**, diálogo único de `ConfirmContext`); sin cambios, cierra al momento. **Navegar fuera** (enlace interno) y **cerrar o recargar la pestaña** (`beforeunload`) también preguntan.

- **Automático, sin tocar pantallas.** `Modal`, `Drawer`, `PortalModal` y todo diálogo con `useDialogo`/`useDialogoEditable` vigilan su contenido (`useCambiosSinGuardar`): eventos `input`/`change` en captura; el valor de cada campo se apunta al enfocarlo y, si vuelve a su valor, deja de contar. `SelectRico` y `CampoFecha` (no nativos) avisan con `avisarCambio()` (evento `ui:cambio`). Cada apertura empieza limpia.
- **No cuentan:** `type="search"`, `role="searchbox"`, lo marcado con `data-sin-guardar="ignorar"` (filtro de `DataTable`, ajustes que se aplican al momento) y lo escrito en un diálogo anidado (solo cuenta el de arriba).
- **Cierre programático no pregunta:** guardar y llamar al `onClose` de la pantalla, o poner `open={false}`. Solo preguntan los gestos de cierre que pasan por el kit. El botón **Cancelar** del pie es descarte explícito y no pregunta.
- **Props:** `avisarSinGuardar={false}` en modales de solo lectura o de confirmación (el propio `ConfirmContext` lo lleva); `cambiosSinGuardar={bool}` cuando la pantalla sabe mejor si hay cambios (selecciones sin `<input>`, archivo arrastrado…): manda sobre la detección.
- **Drawer:** la X la pone quien lo usa → añadir `data-cierra-dialogo=""` a ese botón (sirve en cualquier diálogo con `useDialogo`).
- **Diálogo propio:** `const { ref, pedirCierre } = useDialogoEditable(abierto, cerrar, opciones)`; el fondo y la X llaman a `pedirCierre`, nunca a `onClose`. No duplicar Esc con `onKeyDown` (lo hace el hook y pregunta).
- **Guardar sin cerrar** (paneles por secciones): `cambiosGuardados()` en el `onSuccess`, o `useSinGuardarDelDialogo().reiniciar()` desde el contenido. Cierres a mano de una pantalla (clic fuera de un popover propio): `await confirmarDescarte()`.
- **Navegación:** la app usa `BrowserRouter` (sin data router) y `useBlocker` no está disponible. Se interceptan en captura los clics en `<a href>` internos (`Link`, `NavLink`) mientras haya un diálogo sucio; si se descarta, se repite el clic. **Limitación:** no se intercepta `navigate()` programático ni atrás/adelante del navegador (`popstate`); el diálogo se desmonta con la ruta.
- **Textos:** `sin_guardar.*` en `i18n/langs/{es,en,zh}.mjs` y en `i18n/portal/*.ts` (8 idiomas; en el portal llegan por `TextosDeInterfazProvider`).
- **GRC:** solo interfaz; no guarda nada ni cambia permisos, así que no hay auditoría de servidor ni efecto RGPD/retención.
- Tests: `src/__tests__/CambiosSinGuardar.test.tsx`.

### `<DataTable>` — tabla con sort/empty/loading (es `Tabla` + filtro y paginación en cliente)

```jsx
<DataTable
  columns={[{ key: 'name', label: 'Nombre' }, ...]}
  data={rows}
  loading={isLoading}
  emptyTitle="Sin resultados"
/>
```

---

### `<CampoFecha>` / `<CampoRangoDeFechas>` / `<DateInput>` — fechas (16-11-2026)

Nunca `<input type="date|datetime-local|time">`: pintan el formato de la región del navegador. El selector propio escribe y muestra con el formato del idioma de la app (es `dd/mm/aaaa`, en `mm/dd/yyyy`, zh `aaaa年m月d日`), con máscara y validación al teclear, calendario desplegable (mes/año, Hoy, flechas, Re Pág/Av Pág ±mes, con Mayús ±año, Inicio/Fin de semana, Intro, Escape; patrón ARIA grid), primer día de semana por idioma, `min`/`max`, hora 24 h y `zona`.

```jsx
<CampoFecha value="2026-11-16" onChange={v => …} />                     // 'YYYY-MM-DD'
<CampoFecha modo="fechaHora" value={f.inicio} onChange={…} />           // 'YYYY-MM-DDTHH:MM'
<CampoFecha modo="hora" value="08:30" onChange={…} />                   // 'HH:MM'
<CampoFecha modo="fechaHora" zona="Europe/Madrid" value={iso} … />      // ISO con desfase
<CampoRangoDeFechas desde={d} hasta={h} onChange={({ desde, hasta }) => …} />
<DateInput value={f.desde} onChange={e => set(e.target.value)} className="ds-input" />  // API de siempre
<Input type="date" label="…" value={…} onChange={e => …} />            // delega en CampoFecha
```

`onChange` solo recibe valores completos y válidos (`''` al vaciar). La clase que se pase (p. ej. `ds-input`) va al contenedor, que hace de caja. El panel sale en un portal con posición fija (no lo corta un modal). En el portal: `idioma` y `textos={textosDeFechaDelPortal(idioma)}`.

### `<SelectorDePeriodo>` — periodo de un informe (16-11-2026)

```jsx
const periodo = usePeriodo({ defecto: '30d', granularidades: SIN_HORA })   // horizontes: sentido: 'futuro'
<SelectorDePeriodo {...periodo.selector} />            // sinGranularidad si no hay serie
useQuery({ queryKey: ['x', periodo.params], queryFn: () => api.get('/x', { params: periodo.params }) })
<XAxis dataKey="t" tickFormatter={t => formatearTramo(t, periodo.granularidad)} />
```

Accesos rápidos (hoy, 24 h, 7/30/90 días, este mes, trimestre, año; en horizontes, próximos 7 a 365 días), «Personalizado» con `CampoRangoDeFechas` (fecha y hora si el dato tiene hora; si no, fecha con fin incluido), agrupación auto/hora/día/semana/mes con las no admitidas desactivadas y explicadas, «comparar con el periodo anterior» (`comparable`). El periodo vive en la URL (`periodo`, `desde`, `hasta`, `granularidad`, `comparar`; `prefijo` si hay varios). Valida con los límites de `GET /periodo/limites`. Uso en el README, §33.

### `<RejillaPersonaDia>` — rejilla única fila × día / semana (16-11-2026)

La única forma de pintar «personas (u otras filas) × días o semanas». La usan el calendario y la cobertura de ausencias, el cuadrante de turnos, el mapa de calor de /resources, la previsión de recursos, la capacidad y la carga por persona de Tareas. **No se hace otra tabla propia para esto.**

- Filas: avatar + nombre + `sub` (rol, media…); `marca` sustituye al avatar (muestra de color de un turno). `onFila` + `filaActiva` para seleccionar.
- Columnas: `columnasDeDias(desde, hasta, { festivos })` (día de la semana + número, fin de semana/festivo atenuado, hoy resaltado, fecha larga en el tooltip) o `columnasDeSemanas(lunes[], etiqueta?)` con `unidad="semana"`.
- Celda: `celda(fila, columna) => { estado | tono | color, contenido, detalle, tentativa, marcada, boton }`. `estado` es la clave de la `leyenda`, que da el tono del tema (`success/warning/danger/info/accent/purple/orange/neutral/vacio`) o el `color` de un dato (tipo de ausencia, turno; fondo y borde derivados con `color-mix`). `tentativa` = borde discontinuo (pendiente). `detalle` va al tooltip y al lector de pantalla.
- Interacción: `onCelda` (o `boton` con eventos propios: pintar, soltar) convierte las celdas en botones con foco itinerante (una sola parada de Tab; flechas, Inicio, Fin).
- Scroll horizontal y vertical dentro de su contenedor (`--rpd-alto-max`, 70vh), cabecera y primera columna fijas. Leyenda debajo (`leyenda`, `notaLeyenda`).
- `NavegadorDeMes` (`mes`, `onCambiar`): el navegador de mes común (anterior / mes con `fmtMonth` / siguiente / Hoy). Un solo navegador por pantalla.

```jsx
<NavegadorDeMes mes={mes} onCambiar={setMes} />
<RejillaPersonaDia titulo="Calendario del equipo" cabeceraFilas="Persona"
  filas={personas.map(p => ({ id: p.id, nombre: p.nombre }))}
  columnas={columnasDeDias(desde, hasta, { festivos })}
  celda={(p, d) => { const a = buscar(p, d.clave); return a && { estado: a.tipo, tentativa: a.pendiente, detalle: a.texto } }}
  leyenda={tipos.map(t => ({ clave: t.id, etiqueta: t.nombre, color: t.color }))}
  onCelda={(p, d) => abrir(p, d)} />
```

Fuera de la rejilla quedan, a propósito, el planificador visual (`ResourceSchedulerPage`: reservas que abarcan varias semanas y se arrastran, es una línea de tiempo), la imputación semanal (proyectos × días de una persona, con edición) y los calendarios de mes (`CalendarPage`, vista Calendario de Tareas).

### Menú lateral: categoría con panel y editor del menú (23-11-2026)

- **Categoría con panel** (`PANEL_DE_CATEGORIA` en `components/layout/menuLateral.tsx`): dos controles en la misma fila, el nombre (`NavLink` al panel, `.nav-cat__enlace`) y la flecha (`IconButton` con `aria-expanded`/`aria-controls`, `.nav-cat__flecha`). Sin panel, la cabecera entera despliega, como siempre. Menú contraído: un icono por categoría (`.nav-cat-plegada__icono`) con `aria-haspopup`; el desplegable (portal) sale con el ratón **y con el foco**, y se recorre con flechas.
- **Reordenar una lista** (`EditorDeMenu`): arrastre HTML5 para el ratón **y siempre** botones `IconButton` subir/bajar (teclado y táctil), con el anuncio en una región `aria-live` (`.u-sr-only`) y el foco que sigue al elemento movido. Ocultar = `Checkbox` del kit. Nunca solo arrastre.
- Solo tokens (`--surface-*`, `--text-*`, `--accent`): vale en todos los temas. En móvil (≤ 640 px) los botones crecen a 40 px de alto y se quita la cuenta «n de m visibles».

### Editor de texto rico del cuaderno (23-11-2026)

«Mi cuaderno» (`components/cuaderno/`, docs/CUADERNO.md) usa TipTap 3 (ProseMirror + Yjs), cargado en diferido.
Reglas para reutilizarlo o ampliarlo:

- Botones de la barra: `IconButton` con `ariaLabel` y `aria-pressed` (activo = `--accent` / `--accent-muted`);
  menús desplegables con `cuaderno/Menu.tsx` (`Pulsable role="menuitem"`, Esc y clic fuera cierran).
- Nodos propios con vista React (`ReactNodeViewRenderer`): chips vivos (`ChipVivo`, `Pulsable` si enlaza) y
  etiquetas (`EtiquetaEnLinea`). Colores de sección y etiqueta por clase `cdn-color--<color>` → `--cdn-color`
  (solo tokens). Iconos lucide (nunca emojis).
- El JSON del editor es la fuente de verdad y lo valida el servidor: un nodo o atributo nuevo se añade también
  en `app/services/cuaderno/contenido.py`.
- Orden libre: arrastrar y, siempre, la alternativa con botones (Subir, Bajar, subpágina) en el menú del elemento.
- Paneles: el rápido es `Drawer variant="borde"` con `avisarSinGuardar={false}` (se guarda solo).

## Utility classes `.ds-*`

Composición de layout y atomic styling.  Equivalente a Tailwind pero ya
ajustado al sistema de tokens.

### Layout

- `.ds-page` — stack vertical de página (gap 20px)
- `.ds-section` — stack vertical de sección (gap 12px)
- `.ds-stack` / `.ds-stack-sm` / `.ds-stack-lg` — flex column
- `.ds-row` — flex row, align-center
- `.ds-row-between` — flex row, space-between
- `.ds-row-wrap` — flex row + wrap
- `.ds-grid-cards` — grid auto-fill 280px+
- `.ds-grid-stats` — grid auto-fill 180px+ (para KPIs)

### Surfaces

- `.ds-card` — card estándar
- `.ds-card--inset` — variante para listas dentro de cards
- `.ds-card--accent` — borde acento
- `.ds-card--clickable` — cursor pointer + hover/focus visibles

### Form

- `.ds-input` — input/textarea/select base
- `.ds-field` — wrapper label+control
- `.ds-field__label`
- `.ds-field__hint` / `.ds-field__error`

### Toolbar

- `.ds-toolbar` — fila de acciones, wrap automático
- `.ds-toolbar__spacer` — separador flex 1
- `.ds-toolbar__title` — título + subtítulo

### Estados

- `.ds-empty` — empty state centrado
- `.ds-empty__icon` / `.ds-empty__title` / `.ds-empty__desc`
- `.ds-pill` + `.ds-pill--success/warning/danger/info/accent/purple`
- `.ds-status-dot` + variantes de color

### Tipografía

- `.ds-eyebrow` — label uppercase pequeño
- `.ds-muted` — texto secundario
- `.ds-text-1/2/3` — colores de texto explícitos

### Otros

- `.ds-divider` — hr fina
- `.ds-segmented` — pill segmented control (para tabs simples)

---

## Tokens

Los tokens están en `index.css` como variables CSS. **Nunca hardcodees** un
valor que ya existe como token.

### Color

| Uso | Token |
|---|---|
| Fondo base | `var(--surface-0)` |
| Cards | `var(--surface-2)` |
| Cards elevadas / hover | `var(--surface-3)` |
| Bordes | `var(--surface-4)` |
| Texto principal | `var(--text-1)` |
| Texto secundario | `var(--text-2)` |
| Texto terciario | `var(--text-3)` |
| Acento (CTA, links) | `var(--accent)` |
| Texto sobre el acento (botón principal) | `var(--on-accent)` — nunca `#fff` |
| Éxito / Advertencia / Error / Info | `var(--success/warning/danger/info)` |
| Fondo y borde de un estado | `var(--success-bg)` / `var(--success-border)` (igual para el resto) |
| Color con opacidad desde JS | `alpha(color, '20')` de `constants/theme` — nunca `color + '20'` |

### Tipografía

| Uso | Token |
|---|---|
| Body principal | `var(--text-base)` (13px) |
| Body secundario | `var(--text-sm)` |
| Caption / labels | `var(--text-xs)` |
| Heading 3 | `var(--text-md)` |
| Heading 2 | `var(--text-lg)` |
| Heading 1 | `var(--text-xl)` |
| Display | `var(--text-2xl)`+ |

### Espaciado (4pt scale)

`--space-1` (4) · `--space-2` (8) · `--space-3` (12) · `--space-4` (16) ·
`--space-5` (20) · `--space-6` (24) · `--space-8` (32) · `--space-10` (40) · `--space-12` (48)

### Radios

`--radius-sm` (6) · `--radius-md` (10) · `--radius-lg` (14) · `--radius-xl` (18)
· `--radius-full` (9999)

### Shadows / motion

`--shadow-sm/md/lg` · `--shadow-accent`
`--easing` = `cubic-bezier(0.4, 0, 0.2, 1)`, la curva de toda transición

### Densidad

El perfil escribe `data-density` en `<html>` (`compact`, `normal`, `comfortable`)
y `index.css` mueve `--text-xs/sm/base/md` y `--page-pad-x/y`. Sólo cambia lo
que usa el token: un `fontSize` escrito como número no se entera.

### Foco

`:focus-visible` pinta un contorno de 2 px en el acento en todo lo enfocable, y
sólo con teclado. No hay que quitarlo con `outline: none`.

---

## Patrones recomendados

### Página de listado

```jsx
<Page icon={...} title="..." subtitle="...">
  {/* Toolbar (search + filters + actions) */}
  <BarraDeFiltros acciones={<Button>Nuevo</Button>}>
    <Buscador value={q} onChange={setQ} />
    <Select suelto aria-label="Estado" value={estado} onChange={…} options={…} />
  </BarraDeFiltros>

  {/* Grid o tabla */}
  {loading ? <Spinner /> : items.length === 0 ? (
    <div className="ds-empty">...</div>
  ) : (
    <div className="ds-grid-cards">
      {items.map(it => <Card key={it.id}>...</Card>)}
    </div>
  )}
</Page>
```

### Página detalle / editor

```jsx
<Page title={item.name} rightActions={<><Button variant="secondary">Cancelar</Button><Button>Guardar</Button></>}>
  <Section title="General">
    <Input label="Nombre" value={nombre} onChange={e => setNombre(e.target.value)} />
    ...
  </Section>
  <Section title="Permisos">
    ...
  </Section>
</Page>
```

### Empty state inline

```jsx
<div className="ds-empty">
  <Icon size={36} className="ds-empty__icon" />
  <div className="ds-empty__title">Sin resultados</div>
  <div className="ds-empty__desc">Prueba con otros términos.</div>
</div>
```

---

## Anti-patrones (lo que NO se debe hacer)

- ❌ `style={{ background: '#0d1220' }}` — usa `var(--surface-1)` o `.ds-card`
- ❌ `style={{ fontSize: 13 }}` — usa `var(--text-base)` o ya viene del componente
- ❌ Re-implementar un Card con `<div style={{...}}>` — usa `<Card>` o `.ds-card`
- ❌ Modal local con `position: fixed; z-index: 200` — usa `<Modal>`
- ❌ Mezclar `var(--accent)` con `#3b82f6` — son el mismo color, usa el token

---

## Aplicación progresiva

Esta v2 está pensada para **adopción gradual** sin romper páginas existentes:

1. Las páginas viejas siguen funcionando — los tokens no han cambiado.
2. Cuando toques una página, migra a `.ds-*` o primitivos.
3. La página `WorkflowDesignerPage` ya es referencia migrada — léela para ver
   el patrón en acción.

### Páginas ya migradas (referencia visual)

Las siguientes páginas usan el sistema completo y son intercambiables como
"plantilla viva" cuando empieces una migración:

| Página | Tipo | Patrones que aplica |
|---|---|---|
| `WorkflowDesignerPage` | Listado + editor visual | Page, Card, EmptyState, Modal, Section, StatusBadge |
| `WorkDashboardPage` | Dashboard | Page, .ds-grid-stats, .ds-card, KpiIcon, gauges |
| 5 Dashboards (Projects/Team/Finance/Agent/Support) | Dashboard | Mismo patrón vía DashKit + KpiIcon Lucide |
| `TasksPage` | Listado grande | .ds-segmented, .ds-toolbar, .ds-pill (filter chips), bulk bar |
| `ProjectsPage` | Listado + cards | .ds-grid-cards, ProjectCard con .ds-card |
| `ApprovalsPage` | Inbox + workflows | .ds-grid-stats, .ds-pill (entity types), .ds-empty |
| `DocumentsPage` | Listado + grid/list toggle | .ds-segmented, .ds-toolbar, .ds-pill toggle (tags) |
| `TicketListTab` | Listado interno | .ds-toolbar, .ds-card padding 0 (tabla) |
| `SettingsPage` + 17 secciones | Configuración | .ds-card vía Section, .ds-eyebrow para grupos de tabs |
| `ClientPortalPage` | Portal admin | Page, .ds-segmented (tabs), .ds-input |
| `BPMPage` | Editor visual | Page, sidebar como .ds-card |
| `AIHubPage` | Hub de proveedores | Page, .ds-status-dot--success/warning/danger |
| `AutomationsPage` | Reglas + workflows | .ds-grid-stats, .ds-toolbar, .ds-segmented |

## Reglas ESLint activas

`eslint.config.js` aplica estas reglas para evitar regresiones:

1. **Hex literales obsoletos** (`#00d4ff`/`#0ea5e9`/`#7c3aed`) → usar tokens.
2. **`fontSize` numérico** (e.g. `fontSize: 13`) → usar `var(--text-base)` etc.
3. **"Card armada inline"** — cuando ves `background: var(--surface-2)` seguido
   de `borderRadius` en el mismo `style={{}}`, ESLint sugiere `className="ds-card"`
   o el componente `<Card>`. Se ha demostrado que esta combinación detecta el
   anti-patrón principal de "cada página reinventa cómo se ve un card".

Las violaciones son `warn`, no `error` — adopción gradual.
4. **Migración al kit (16-11-2026), nivel `error`** fuera de `components/ui` y de las pruebas, con el cupo por fichero de `kit-pendientes.json`:
   `contec/sin-boton-nativo` (`<button>`), `contec/sin-tabla-propia` (`<table>`), `contec/sin-select-nativo` (`<select>`),
   `contec/sin-casilla-suelta` (`<input type="checkbox|radio">`), `contec/sin-fieldset-propio` (`<fieldset>` sin `ds-grupo-opciones`).
   Reglas en `scripts/eslint/kit-sin-marcado-propio.mjs`, pruebas en `src/__tests__/reglasDelKit.test.ts`.

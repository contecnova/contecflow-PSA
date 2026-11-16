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
- **Iconos**: lucide siempre; nunca emojis (código ni diccionarios). `ViewToggle`, `SearchInput` y `IconFR`/`IconCR` ya usan lucide.
- **Colores**: solo tokens de `index.css`; activo/seleccionado = `--accent` / `--accent-muted`; nada de `--surface-*` como color de texto.
- **Fechas**: `fmtDate`, `fmtDateTime`, `fmtMonth`, `formateadorDeFecha` (utils/helpers). Para editarlas, `CampoFecha`/`DateInput` (nunca el input nativo); para el periodo de un informe, `SelectorDePeriodo` + `usePeriodo`. El campo de fecha mide lo mismo que `Input`/`Select`/`Button md` (38 px) con cualquier clase; en una tabla densa se baja con `--uifecha-alto`.
- **Personas × días/semanas**: siempre `RejillaPersonaDia` + `NavegadorDeMes` (ver abajo).

Tests que lo vigilan: `__tests__/kitDiseno.test.tsx`, `__tests__/disenoSinEmojis.test.ts` (A–L, chat, kit) y `__tests__/disenoMZSinEmojis.test.ts` (M–Z).

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

### `<DataTable>` — tabla con sort/empty/loading

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

Accesos rápidos (hoy, 24 h, 7/30/90 días, este mes, trimestre, año; en horizontes, próximos 7 a 365 días), «Personalizado» con `CampoRangoDeFechas` (fecha y hora si el dato tiene hora; si no, fecha con fin incluido), agrupación auto/hora/día/semana/mes con las no admitidas desactivadas y explicadas, «comparar con el periodo anterior» (`comparable`). El periodo vive en la URL (`periodo`, `desde`, `hasta`, `granularidad`, `comparar`; `prefijo` si hay varios). Valida con los límites de `GET /periodo/limites`. Contrato completo en DOCS.md, «Periodo libre en informes».

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
  <div className="ds-toolbar">
    <SearchInput value={q} onChange={setQ} />
    <select className="ds-input">...</select>
    <div className="ds-toolbar__spacer" />
    <Button>Nuevo</Button>
  </div>

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
    <FormField label="Nombre"><input className="ds-input" /></FormField>
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

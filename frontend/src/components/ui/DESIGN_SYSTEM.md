# Design System v2 — guía rápida

> La guía completa, medida y pensada para reutilizar en otras soluciones, es
> [docs/GUIA_DE_DISENO.md](../../../../docs/GUIA_DE_DISENO.md). Incluye lo que
> no se debe copiar (contraste, foco, densidad) y los arreglos medidos.

**Objetivo**: una sola identidad visual y experiencia consistente en todas las
pantallas. Cuando construyas una página nueva o toques una existente, **usa
estos primitivos y clases** en lugar de re-inventar con estilos inline.

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
  icon={<GitBranch size={36} />}
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
| Éxito / Advertencia / Error / Info | `var(--success/warning/danger/info)` |

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
`--easing` se usa en `.ds-card` y `.ds-input` pero **no está definida** (véase la guía completa, apartado 15)

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

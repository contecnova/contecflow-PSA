# Guía de diseño de contecflow

Esta guía describe el sistema visual de contecflow tal como está en el código,
para poder construir otras soluciones de la casa con el mismo aspecto y el
mismo comportamiento.

- **Fuente:** el propio código. `frontend/src/index.css` (tokens y temas),
  `frontend/src/constants/theme.ts` (colores para gráficas), `frontend/src/components/ui/`
  (componentes) y `frontend/eslint.config.js` (reglas).
- **Fecha de la medición:** 02-11-2026. Todas las cifras de uso, contraste y
  tamaño salen de ejecutar algo contra el repositorio ese día. Cuando el código
  cambie, se vuelven a medir; no se copian de aquí.
- **Cómo leerla:** cada apartado dice qué hay y cómo usarlo. El apartado 15
  reúne lo que contecflow hace mal y **no se debe copiar**, con el arreglo
  propuesto y medido.
- **La guía corta** de los componentes sigue en
  `frontend/src/components/ui/DESIGN_SYSTEM.md`. Esta la amplía y la corrige
  donde no coincide con el código.

---

## 1. Principios

La cabecera de `index.css` los resume en cinco: **calma visual, densidad de
información elegante, precisión, velocidad percibida y sin fricción**. En la
práctica se traducen en siete reglas:

1. **Oscuro por defecto y denso.** Es una herramienta de trabajo de jornada
   completa: superficies oscuras de poco contraste entre sí, texto base de
   13 px y mucha información por pantalla.
2. **El color significa algo.** El acento marca la acción principal y lo
   activo. Verde, ámbar, rojo y azul se reservan para estados (bien, aviso,
   error, información). El violeta marca IA y funciones premium.
3. **Nada a mano.** Ni un color, ni un tamaño de letra, ni un radio escrito
   como literal: todo sale de un token. Lo vigila ESLint (apartado 14).
4. **Lo mismo se ve igual.** Dos pantallas que muestran el mismo tipo de
   registro lo colocan igual. Si el registro es el mismo, es la misma pantalla.
5. **Tres estados siempre.** Toda lista o panel que carga datos tiene
   *cargando*, *vacío* y *error*, y los tres están diseñados.
6. **Toda acción responde.** Guardar avisa; borrar pide confirmación; un botón
   que espera no se puede volver a pulsar.
7. **Ningún texto en el código.** Todo pasa por las traducciones (es, en, zh).

---

## 2. Color

### 2.1 Superficies

Cinco escalones, del fondo hacia el primer plano. Valores del tema base
(`:root`, que la aplicación llama *Oscuro clásico* o `dark`):

| Token | Valor | Uso |
|---|---|---|
| `--surface-0` | `#080c14` | Fondo de la aplicación (`--bg` es su alias) |
| `--surface-1` | `#0d1220` | Barra lateral, paneles, fondo de los avisos |
| `--surface-2` | `#111827` | Tarjetas y modales |
| `--surface-3` | `#172133` | Tarjeta elevada, hover, **fondo de los campos** |
| `--surface-4` | `#1e2d45` | Bordes y separadores |
| `--surface-5` | `#253550` | Borde en hover |

La jerarquía se construye con el escalón, no con sombras: una tarjeta
(`surface-2`) sobre el fondo (`surface-0`) con borde `surface-4`. Las sombras
se reservan para lo que flota (modales, menús, avisos).

### 2.2 Texto

| Token | Valor | Uso | Contraste sobre `surface-2` |
|---|---|---|---|
| `--text-1` | `#f0f4ff` | Títulos, valores, texto principal | 16,1:1 |
| `--text-2` | `#a8b8d4` | Etiquetas, descripciones | 8,8:1 |
| `--text-3` | `#7689a8` | Secundario, pistas, fechas | 5,0:1 |
| `--text-4` | `#4a5a78` | **Decorativo**: líneas, deshabilitado. Nunca texto que haya que leer | — |

### 2.3 Acento

| Token | Valor (base) | Uso |
|---|---|---|
| `--accent` | `#4f8ef7` | Botón principal, enlaces, elemento activo |
| `--accent-dim` | `#2d5fd4` | Variante oscura (hover, degradados) |
| `--accent-muted` | `rgba(79,142,247,.08)` | Fondo de lo seleccionado, botón `subtle` |
| `--accent-glow` | `rgba(79,142,247,.15)` | Halo |
| `--accent-border-soft` / `--accent-border` / `--accent-border-strong` | 20 % / 30 % / 40 % | Bordes con acento |

Cada usuario puede cambiar el acento en su perfil. La aplicación sobreescribe
`--accent`, `--accent-muted` y `--accent-glow` en `<html>`. Por eso **todo lo
que use el acento tiene que leer la variable**, nunca su valor.

### 2.4 Semánticos

Cada color semántico tiene tres tokens: el color, un fondo al 8 % (`-bg`) y un
borde al 20 % (`-border`).

| Familia | Color base | Significado |
|---|---|---|
| `--success` | `#34d399` | Hecho, en plazo, operativo |
| `--warning` | `#f59e0b` | En riesgo, pendiente, atención |
| `--danger` | `#f87171` | Error, incumplido, destructivo |
| `--info` | `#60a5fa` | Información neutra |
| `--purple` | `#a78bfa` | IA y funciones premium |
| `--orange` | `#fb923c` | Severidad alta (P2), distinta del aviso |
| `--coral` | `#f43f5e` | Sólo para el selector de color |

**El patrón de una etiqueta de estado:** texto en el color, fondo `-bg` y
borde `-border`. Es lo que hacen `StatusBadge` y `.ds-pill--*`.

### 2.5 Colores en JavaScript

Las gráficas (Recharts, SVG, canvas) no pueden leer variables CSS directamente.
Para ellas existen:

- `getCSSVar('--accent')` y `getAccent()`, que leen el valor **del tema activo**;
- el hook `useChartTheme()` (en `src/charts/`), que da los tokens resueltos y se
  actualiza al cambiar `data-theme`;
- `CHART_COLORS`, la paleta de series en orden fijo: acento, verde, ámbar,
  violeta, turquesa, rojo, naranja, rosa, lima, cielo. `CHART_COLORS_EXTENDED`
  la alarga a 12.

`COLOR.*` (en `theme.ts`) son literales del tema oscuro y **no siguen al tema
activo** (véase el apartado 15).

---

## 3. Temas

El tema se fija con `data-theme` en `<html>`. Hay seis, más `system`:

| `data-theme` | Nombre en pantalla | Carácter | Acento |
|---|---|---|---|
| `freight` | Freight Pro | **Por defecto** (servidor y cliente). ERP industrial, grises cálidos, fuente Geist | `#caa34c` (dorado) |
| `dark` | Oscuro clásico | El de `:root`: azul pizarra. No tiene selector propio; cae en `:root` | `#4f8ef7` |
| `midnight` | Midnight | Casi negro | `#5b9cf6` |
| `slate` | Slate | Gris neutro estilo GitHub | `#4493f8` |
| `light` | Claro | Fondo blanco | `#2563eb` |
| `high-contrast` | Alto contraste | Negro puro, bordes forzados | `#60a5fa` |
| `system` | Sistema | Escribe `dark` o `light` según el sistema operativo | — |

Un tema nuevo sólo redefine tokens: superficies, texto, acento, semánticos,
`--bg` y `color-scheme`. Ningún componente pregunta en qué tema está.

### 3.1 Contraste medido por tema

Medido con la fórmula WCAG 2.x sobre `--surface-2` (tarjetas). AA pide 4,5:1
para texto normal.

| Tema | text-1 | text-2 | text-3 | accent | success | warning | danger |
|---|---|---|---|---|---|---|---|
| dark (`:root`) | 16,1 | 8,8 | 5,0 | 5,5 | 9,2 | 8,3 | 6,4 |
| freight | 14,2 | 9,4 | 5,4 | 6,7 | 7,1 | 7,0 | 5,1 |
| light | 17,9 | 7,6 | **2,6** | 5,2 | **3,3** | **3,2** | 4,8 |
| high-contrast | 18,9 | 15,0 | 8,1 | 7,4 | 10,8 | 11,3 | 6,8 |
| midnight | 16,7 | 6,0 | **2,3** | 6,9 | 10,0 | 8,9 | 6,9 |
| slate | 13,7 | **4,3** | **2,0** | 5,2 | 8,4 | 7,5 | 5,9 |

Texto blanco del botón principal sobre el acento: dark 3,21 · freight **2,37** ·
light 5,17 · high-contrast **2,54** · midnight 2,79 · slate 3,10. Sólo el tema
claro llega a AA. Los valores en negrita no llegan a AA. Los arreglos están en
el apartado 15.

---

## 4. Tipografía

### 4.1 Familias

- **Texto:** `--font-sans` = DM Sans, luego Geist y la del sistema. El tema
  `freight` invierte el orden (Geist primero).
- **Monoespaciada:** `--font-mono` = Geist Mono, luego Space Mono. Para
  números de registro, código, horas y claves.
- Se cargan de Google Fonts desde `index.css` (DM Sans 400–800, Geist 300–800,
  Geist Mono 400–500 y Space Mono 400/700).

### 4.2 Escala

La escala tiene muchos escalones (con medios píxeles), pero el uso real se
concentra en estos:

| Token | Tamaño | Uso |
|---|---|---|
| `--text-2xs` | 10 px | Micro: contadores, etiquetas de bloque en mayúsculas |
| `--text-xs` | 11 px | **Etiquetas de campo** (mayúsculas), pies, pistas |
| `--text-sm` | 12 px | Texto secundario, descripciones, campos `.ds-input` |
| `--text-base` | 13 px | **Texto de trabajo por defecto**, botones, campos de los formularios |
| `--text-md` | 14 px | Título de tarjeta o de grupo |
| `--text-lg` | 16 px | Título de modal y de sección (h2) |
| `--text-xl` | 20 px | Título de página (h1) |
| `--text-2xl` | 24 px | Valor de KPI |
| `--text-3xl` | 28 px | Número destacado |

El `body` está a 14 px con `line-height: 1.5`, pero los componentes fijan
13 px (`--text-base`). Una solución nueva debería poner el `body` también a
13 px y ahorrarse la diferencia.

**Pesos:** 400 en el cuerpo; 600 (`--font-semibold`) en etiquetas, botones y
títulos de tarjeta; 700 en títulos de modal y de página; 800 sólo en cifras.

### 4.3 La etiqueta de campo

Es el patrón tipográfico más repetido de la aplicación:

```css
font-size: var(--text-xs); font-weight: 600; color: var(--text-2);
text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 5px;
```

`.ds-eyebrow` es la misma idea para encabezar bloques.

---

## 5. Espacio, radios, sombras y capas

**Espaciado (escala de 4):** `--space-1` 4 · `--space-2` 8 · `--space-3` 12 ·
`--space-4` 16 · `--space-5` 20 · `--space-6` 24 · `--space-8` 32 ·
`--space-10` 40 · `--space-12` 48. No hay `--space-7`.

Separaciones habituales: 8 entre controles de una fila, 10–12 entre campos de
un formulario, 14–18 entre bloques de un panel, 20 de relleno de tarjeta y 28
de relleno de modal.

**Página:** `--page-pad-x` y `--page-pad-y` (32 px) y `--page-max-w` (1400 px).
Los aplica `PageShell`.

**Radios:** `--radius-sm` 6 (chips, botón pequeño) · `--radius-md` 10 (botón y
campo) · `--radius-lg` 14 (tarjeta) · `--radius-xl` 18 (modal) ·
`--radius-full` (píldora, punto).

**Sombras:** `--shadow-sm` · `--shadow-md` · `--shadow-lg` · `--shadow-accent`.
No hay `--shadow-xl`. El modal usa `0 24px 64px rgba(0,0,0,.7)`.

**Capas (`z-index`):** orden estricto, siempre por token:

| Token | Valor | Para |
|---|---|---|
| `--z-sticky` | 50 | Cabeceras de tabla y barras fijas |
| `--z-sidebar` | 90 | Barra lateral en móvil |
| `--z-mobile-nav` | 100 | Hamburguesa y botones flotantes |
| `--z-dropdown` | 200 | Desplegables |
| `--z-popover` | 400 | Menús contextuales |
| `--z-drawer` | 800 | Paneles laterales |
| `--z-modal` | 1000 | Modales |
| `--z-drag` | 9999 | Lo que se arrastra |
| `--z-tour*` | 99990–99992 | Recorrido guiado |
| `--z-search` | 99998 | Búsqueda global (Cmd+K) |
| `--z-banner` / `--z-toast` | 99999 | Avisos de sistema y emergentes |

---

## 6. Movimiento

- Curva por defecto en todo: `cubic-bezier(0.4, 0, 0.2, 1)`.
- Duraciones: 0,15 s para hover y bordes; 0,2 s para la entrada del modal
  (`fadeUp`); 0,25 s para avisos y para la barra lateral móvil.
- Pulsar un botón lo escala a 0,97.
- Animaciones disponibles: `fadeUp`, `fadeIn`, `slideIn`, `spin`, `shimmer`
  (esqueletos), `pulse-dot` y `progress-indeterminate`.
- Con `prefers-reduced-motion: reduce` todas las animaciones y transiciones
  pasan a 0,01 ms. Se respeta sin excepciones.

---

## 7. Estructura de la aplicación

- **Barra lateral** de 222 px, que se pliega a 46 px. A 1024 px o menos pasa a
  ser un panel superpuesto con hamburguesa y velo.
- **Barra superior** con migas de pan, búsqueda (Cmd+K), creación rápida,
  cronómetro, avisos y perfil.
- **Página:** `PageShell` (relleno y ancho máximo) más `PageHeader` (título,
  subtítulo, migas, acciones y exportar). Es el par más usado: 87 y 89
  ficheros. `<Page>` los combina en uno y lo usan 13 páginas.
- **Pestañas** para dividir una página grande (`Tabs`, 24 ficheros). La pestaña
  activa se puede enlazar con `?tab=` (lo hace Ajustes).
- **Configuración:** por bloques. Cada bloque tiene una explicación de una línea
  arriba, a la derecha el botón «+ Nuevo», y debajo la lista o el estado vacío.

**Puntos de corte medidos:** 480, 600, 768, 900, 1024 y 1200 px. Incluye
márgenes seguros (`--safe-*`) para el notch y la PWA instalada.

---

## 8. Componentes

Se importan de `src/components/ui`. Entre paréntesis, en cuántos ficheros
`.tsx` se usan (de 254).

### 8.1 Button (107 ficheros, 708 usos)

- **Variantes:** `primary` (acento con texto blanco) · `secondary` (`surface-3`
  con borde) · `danger` (fondo y borde de error) · `ghost` (transparente con
  borde de acento) · `subtle` (`accent-muted`).
- **Tamaños:** `xs` 11 px · `sm` 12 px · `md` 13 px (por defecto) · `lg` 14 px.
- **Comportamiento:** con `loading` muestra un indicador **y se deshabilita**,
  así no se envía dos veces. Al deshabilitarse queda a opacidad 0,5 y con
  `aria-disabled`. Por defecto es `type="button"`, para que no envíe
  formularios sin querer.
- **Reglas:** un solo botón principal por zona. Cancelar va a la izquierda y la
  acción a la derecha. Borrar es `danger`, o `secondary` con el texto en rojo
  si va en una fila de una lista.

### 8.2 Modal (76 ficheros)

- **Anchos:** `sm` 400 · `md` 520 (por defecto) · `lg` 760 · `xl` 1040, o
  `width` libre.
- Atrapa el foco, cierra con Esc y al pulsar fuera, y devuelve el foco al
  elemento que lo abrió. Lleva `role="dialog"` y `aria-modal`.
- **Estructura:** título (16 px, 700), subtítulo opcional y el contenido. Los
  botones van al final, alineados a la derecha.
- **Para qué se usa:** crear y editar registros cortos. Si un formulario no
  cabe en `lg`, es una página.

### 8.3 Confirmación (64 ficheros) y avisos (123 ficheros)

- **Confirmación:** `openConfirmGlobal({ message, onConfirm, danger: true })`
  antes de cualquier acción que destruya algo. Nunca `window.confirm` (quedan 4
  usos antiguos en 3 ficheros).
- **Avisos:** `useToast()` con `success`, `error`, `warning` o `info`. Salen
  abajo a la derecha sobre `surface-1`, con un borde izquierdo del color del
  tipo, y se cierran solos a los 4 segundos.
- **Error del servidor:** `toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))`.
  Se muestra el mensaje del servidor, porque dice qué ha pasado de verdad.

### 8.4 Estados: Spinner (105), EmptyState (92), esqueletos

- **Cargando:** `<Spinner />`. Para listas largas, mejor esqueletos
  (`Skeletons.tsx`, `.skeleton-*`).
- **Vacío:** `<EmptyState icon title description action />`. El título dice qué
  falta («Aún no hay componentes»), la descripción explica para qué sirve y la
  acción ofrece crear el primero.
- **Error:** un aviso más el estado vacío o el contenido anterior. Una pantalla
  nunca se queda en blanco.

### 8.5 Superficies: Card, `.ds-card` y Section

- `.ds-card`: `surface-2`, borde `surface-4`, radio 14, relleno 20, columna con
  separación 12. Variantes `--inset`, `--accent` y `--clickable` (esta con foco
  visible).
- **Lista dentro de tarjeta:** `.ds-card` con `padding: 0` y filas de
  `10px 14px`, separadas por `border-top: 1px solid var(--surface-4)` salvo la
  primera.
- `<Section title subtitle actions>`: bloque con título dentro de una página.

### 8.6 Datos: StatusBadge, KpiCard, DataTable y TableControls

- `<StatusBadge kind>`: `neutral`, `success`, `warning`, `danger`, `info`,
  `accent` y `purple`, con punto opcional (`dot`).
- `<KpiCard icon label value sub trend>` para cifras de panel, en una rejilla
  `.ds-grid-stats` (columnas de 180 px o más).
- **Tablas:** `TableControls` da ordenación (`useSort`, `SortableTH`),
  búsqueda, filtros y alternar entre tabla y tarjetas. `DataTable` existe, pero
  apenas se usa (2 ficheros). Las cabeceras fijas usan `--z-sticky`.
- `ColVisibility` deja al usuario elegir las columnas.

### 8.7 Selectores de entidad

`ClientSelect`, `UserSelect`, `ProjectSelect`, `ContractSelect` y otros diez.
Todos los módulos comparten la misma consulta y su caché, así que un cambio de
nombre se ve en todas partes; muestran el nombre, guardan el identificador y no
admiten texto libre. Son un `<select>` con la lista entera. Para entidades que
pueden tener cientos de registros, en una solución nueva, mejor un selector con
búsqueda en el servidor.

### 8.8 Pestañas

`<Tabs items active onChange variant="pill|underline" size>`. Cada pestaña
admite contador e icono. Marca la activa con `aria-pressed`, no con el patrón
ARIA de pestañas (véase el apartado 15).

---

## 9. Formularios

El patrón que siguen las pantallas de configuración, en código:

```tsx
const IS: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
  borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: 'var(--text-base)',
  outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const LS: CSSProperties = { fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--text-2)',
  display: 'block', marginBottom: 5, textTransform: 'uppercase', letterSpacing: '0.06em' }

<div>
  <label style={LS} htmlFor="grp-ola">{t('sd_cfg.ola_hours')}</label>
  <input id="grp-ola" type="number" style={IS} aria-invalid={!valido} aria-describedby="grp-ola-hint" … />
  <div id="grp-ola-hint" style={{ fontSize: 'var(--text-xs)', color: valido ? 'var(--text-3)' : COLOR.danger }}>…</div>
</div>
```

En una solución nueva, esos dos objetos son las clases `.ds-input` y
`.ds-field__label`. No hay que repetirlos en cada fichero (véase el apartado 15).

**Reglas:**

1. Toda etiqueta va unida a su campo (`htmlFor` e `id`). Si no hay etiqueta
   visible, `aria-label`.
2. Un campo obligatorio lleva `*` en la etiqueta y **el botón de guardar se
   deshabilita** mientras falte o sea inválido. No se deja enviar para mostrar
   el error después.
3. La pista va debajo del campo, en `--text-xs` y `--text-3`. Si el valor es
   inválido, la pista se pone en rojo y el campo lleva `aria-invalid`.
4. Un campo opcional vacío se envía como `null`, no como cadena vacía. La pista
   dice qué significa dejarlo vacío («Vacío: sin OLA»).
5. Dos o tres campos cortos van en rejilla (`2fr 1fr`); los largos y los de
   texto ocupan toda la fila.
6. Lo que valida el cliente lo vuelve a validar el servidor (422 con un mensaje
   legible).

---

## 10. Texto e idiomas

- **Tres idiomas:** español (el de referencia y el de respaldo), inglés y chino.
  Ficheros `src/i18n/langs/{es,en,zh}.mjs`, unas 6.000 líneas cada uno.
- **Uso:** `const t = useAppT()` y `t('espacio.clave')` (151 ficheros). Las
  variables se escriben `{nombre}`: `t('sd_cfg.ola_of_queue', { group })`.
- Cada pantalla nueva añade sus claves en **los tres** idiomas en el mismo
  cambio, en un espacio con nombre propio (`sd_cfg`, `service_desk`…).
- **Tono:** español de España, frases cortas y concretas. Se dice qué pasa y
  qué hacer («Rechazar pide el motivo: es lo que recibe el solicitante»), no
  «Error de validación».
- Mayúscula sólo al principio de la frase, en títulos y botones también.
- Los botones son verbos: Guardar, Declarar, Añadir. El de crear lleva «+».
- **Fechas y números:** siempre con un formateador, nunca la cadena ISO cruda.
  El de contecflow (`fmtDate`) tiene un defecto (apartado 15).

---

## 11. Iconos e imagen

- **Iconos:** `lucide-react` (140 ficheros), a 14–20 px. El icono decorativo
  lleva `aria-hidden`.
- Hay emojis como icono en estados vacíos y en algunas listas. Funcionan, pero
  se ven distintos en cada sistema; en una solución nueva, mejor Lucide en todo.
- **Punto de estado:** círculo de 8–10 px (`.ds-status-dot--*`) delante del
  nombre, con el texto del estado al lado: el color nunca va solo.

---

## 12. Gráficas

- **Biblioteca principal:** Recharts (18 ficheros). En `src/charts/` hay además
  tipos especiales (embudo, mapa de calor, indicador, red, Plotly).
- **Colores:** `CHART_COLORS` en orden, siempre el mismo color para la misma
  serie entre gráficas, y los tokens del tema con `useChartTheme()` para ejes,
  rejilla y tooltip.
- Se aplican las mismas reglas de estados: cargando, vacío («sin datos en el
  periodo») y error.

---

## 13. Accesibilidad

**Lo que está bien:**

- texto principal y secundario por encima de AA en los temas oscuros;
- `prefers-reduced-motion` respetado;
- enlace «saltar al contenido» (`.skip-nav`);
- modal con trampa de foco;
- botones con `aria-busy` y `aria-disabled`;
- campos con foco visible (contorno de 2 px en acento);
- 450 `aria-label` en 100 ficheros;
- `jsx-a11y` activo en ESLint;
- un tema de alto contraste.

**Lo que falta** está en el apartado 15. La auditoría completa es
`docs/A11Y_WCAG_AUDIT.md`.

---

## 14. Reglas de ESLint para llevarse

`frontend/eslint.config.js` avisa (como aviso, no como error) de:

1. **Hex de marca obsoletos** (`#00d4ff`, `#0ea5e9`, `#7c3aed`): hay que usar el
   token.
2. **`fontSize` numérico** (`fontSize: 13`): hay que usar `var(--text-*)`.
3. **Tarjeta montada en línea** (`background: var(--surface-2)` más
   `borderRadius` en el mismo `style`): hay que usar `.ds-card` o `<Card>`.
4. **`jsx-a11y`**: etiquetas de controles, atributos ARIA válidos y demás.

En una solución nueva conviene ponerlas como **error** desde el primer día:
convertir 11.500 estilos en línea después cuesta mucho más que no escribirlos.

---

## 15. Lo que no se debe copiar

Medido el 02-11-2026. Cada fila dice qué pasa, cuánto y qué hacer en una
solución nueva.

| # | Qué pasa en contecflow | Medida | En una solución nueva |
|---|---|---|---|
| 1 | El texto blanco del botón principal no llega a AA | 2,37:1 en `freight` (el tema por defecto), 2,54:1 en alto contraste; sólo el claro pasa (5,17) | Un token `--on-accent`: `--surface-0` en los temas oscuros (6,1–8,3:1) y `#ffffff` en el claro (5,17:1). El botón usa `color: var(--on-accent)` |
| 2 | `--text-3` no llega a AA en tres temas | light 2,6 · midnight 2,3 · slate 2,0 | Probados: light `#64748b` (4,76), midnight `#7689a8` (5,39), slate `#8b949e` (5,26); y `--text-2` de slate `#9da7b3` (6,64) |
| 3 | En el tema claro, éxito y aviso no llegan a AA como texto | 3,3 y 3,2 | `#15803d` y `#b45309` (5,02 cada uno) |
| 4 | Se quita el indicador de foco a botones, enlaces y pestañas (`outline: 0 !important`) | Sólo los campos y `.ds-card--clickable` muestran foco | Rompe WCAG 2.4.7: con teclado no se sabe dónde se está. Usar `:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px }` en todo lo que se pueda enfocar; con `:focus-visible` el anillo no aparece al hacer clic |
| 5 | Las pestañas no siguen el patrón ARIA (`role="tab"`, flechas) | Se dejó a propósito para evitar el contorno al cargar | Con el punto 4 bien resuelto el motivo desaparece: `role="tablist"`/`tab`, `aria-selected` y navegación con flechas |
| 6 | Los avisos emergentes no se anuncian | Sin `aria-live` ni `role` en el contenedor; el botón de cerrar sin `aria-label` | Contenedor con `role="status" aria-live="polite"` (`role="alert"` para los errores) y `aria-label` en cerrar |
| 7 | El color con opacidad se arma pegando texto a una variable (`'var(--success)' + '20'`) | Da CSS inválido: el fondo y el borde del aviso se descartan | Usar los tokens `-bg` y `-border`, o `color-mix(in srgb, var(--success) 12%, transparent)` |
| 8 | `--easing` se usa y no está definida | 3 transiciones inválidas (`.ds-card`, `.ds-input`): no animan | Definirla en `:root`: `--easing: cubic-bezier(0.4, 0, 0.2, 1)` |
| 9 | La guía corta cita tokens que no existen | `--space-7`, `--shadow-xl`, `--easing-spring` | Lo que no está en `:root` no existe; la lista de tokens sale del CSS |
| 10 | La densidad del perfil no cambia nada | Escribe `--space-item` y `--font-size-base`, con 0 usos; se aplica desde dos sitios | O los componentes leen la variable, o no se ofrece el interruptor. Un ajuste que no hace nada es peor que no tenerlo |
| 11 | `COLOR.*` en JavaScript son literales del tema oscuro | `COLOR.text2` y `COLOR.text3` además conservan los valores viejos (`#8899bb`, `#4a5a78`) que el CSS corrigió para AA | En JSX, `var(--token)` siempre. En gráficas, `getCSSVar` o `useChartTheme`. Ninguna copia de la paleta en JS |
| 12 | P1 y P2 tienen el mismo rojo | `TICKET_PRIORITY` usa `danger` en los dos, aunque `--orange` existe para P2 | Una severidad, un color: P1 `danger`, P2 `orange`, P3 `warning`, P4 `text-2` |
| 13 | Casi todo el estilo va en línea | 11.508 `style={{` en 220 ficheros, frente a unos 135 usos de `.ds-card` y `.ds-input` | Componentes y clases desde el principio; el estilo en línea sólo para lo realmente único |
| 14 | Cada pantalla redefine sus `IS` y `LS` | El mismo objeto copiado en decenas de ficheros | `.ds-input` y `.ds-field__label`, o un `<Field>` |
| 15 | Tres capas de alias de color (`--bg`, `--surface`, `--color-background-primary`…) | Heredadas de versiones anteriores | Un solo nombre por token |
| 16 | Las fechas salen siempre en formato español | `fmtDate` fija `dd/MM/yyyy` y el locale `es`, con la zona del navegador, aunque la aplicación esté en inglés o en chino | Formatear con `Intl.DateTimeFormat` en el idioma activo y la zona de la organización |
| 17 | Cuatro familias de fuente cargadas | DM Sans, Geist, Geist Mono y Space Mono, con varios pesos | Una familia de texto y una monoespaciada, sólo con los pesos usados (400, 600, 700) |

Los puntos 1 a 8, el 10 y el 16 son defectos de la propia contecflow. Arreglarlos
cambia el aspecto de toda la aplicación, y queda pendiente de decidir.

---

## 16. Arranque de una solución nueva

1. **Copiar los tokens** de `:root` de `frontend/src/index.css` (color, texto,
   escala, espacio, radios, sombras y capas), sin las capas de alias. Añadir
   `--easing` y `--on-accent`.
2. **Copiar los temas** que se vayan a ofrecer, con los arreglos de contraste
   de los puntos 1 a 3 del apartado 15. Si sólo se ofrece uno, `freight` es la
   identidad por defecto de la casa.
3. **Copiar el foco** del punto 4: `:focus-visible` con contorno de 2 px en el
   acento en todo lo que se pueda enfocar.
4. **Copiar los componentes** de `src/components/ui`: `Button`, `Modal`,
   `EmptyState`, `Spinner`, `Card`, `StatusBadge`, `KpiCard`, `Tabs`, `Section`
   y `TableControls`, más `PageShell` y `PageHeader` de `components/layout`.
   Llevarse también `ToastContext` (con el punto 6) y `ConfirmContext`.
5. **Copiar las clases `.ds-*`** del final de `index.css`.
6. **Poner las reglas de ESLint** del apartado 14 como error.
7. **Montar la i18n** con los tres idiomas desde la primera pantalla.
8. **Repasar cada pantalla** con esta lista: ¿tiene cargando, vacío y error?
   ¿Guardar avisa y se deshabilita mientras espera? ¿Borrar confirma? ¿Cada
   campo tiene etiqueta? ¿Ningún color ni tamaño literal? ¿Se usa con teclado?

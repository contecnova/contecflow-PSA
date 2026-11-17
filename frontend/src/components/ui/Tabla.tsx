/**
 * Tabla común del kit (16-11-2026, migración al kit, fase 1).
 *
 * La única forma de pintar una tabla de datos. Su estilo es `contecflow-table`
 * (index.css) más los modificadores `ui-tabla--*` de Tabla.css. Dos piezas:
 *
 *  · `<Tabla>`: columnas declarativas, ordenación, selección con casillas,
 *    fila clicable (ratón y teclado), celdas editables en el sitio, estado de
 *    carga y vacío, densidad, cabecera fija y pie.
 *  · `<TablaSimple>`: el envoltorio con el mismo estilo para las tablas que no
 *    encajan en columnas declarativas (celdas combinadas, grupos de filas…).
 *    Dentro va el `<thead>/<tbody>/<tr>/<td>` de siempre.
 *
 * La edición en el sitio es la de las vistas de trabajo del planificador
 * (clic, Intro o F2 abren el editor; Escape cancela; Intro o salir guardan y el
 * foco vuelve a la celda). `CeldaEditable` y los editores se exportan para
 * usarlos dentro de una `TablaSimple`.
 */
import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { ArrowDown, ArrowUp, ChevronsUpDown } from 'lucide-react'
import { CampoFecha } from './SelectorDeFecha'
import { Checkbox } from './Opciones'
import { conParametros, useTextoUi } from './useTextoUi'
import './Tabla.css'

export type ClaveDeFila = string | number
export type DensidadDeTabla = 'compacta' | 'normal' | 'comoda'
export type DireccionDeOrden = 'asc' | 'desc'
export interface OrdenDeTabla { col: string | null; dir: DireccionDeOrden }

/** Edición en el sitio de una columna. */
export interface EdicionDeCelda<T> {
  tipo: 'texto' | 'numero' | 'lista' | 'fecha'
  /** Valor actual como texto (lo que recibe el editor). */
  valor: (fila: T) => string
  /** Se llama solo si el valor cambia. */
  onGuardar: (fila: T, valor: string) => void
  /** Opciones del editor `lista`. */
  opciones?: Array<{ valor: string; etiqueta: string }> | ((fila: T) => Array<{ valor: string; etiqueta: string }>)
  min?: number
  max?: number
  /** `false` deja la celda en solo lectura para esa fila. */
  puede?: (fila: T) => boolean
  /** Texto del valor para el lector de pantalla (por defecto, `valor`). */
  texto?: (fila: T) => string
}

/** Columna de `Tabla`. Compatible con `ColumnaDeTabla` de `Table`/`DataTable`. */
export interface ColumnaTabla<T> {
  key: string
  label: ReactNode
  /** `true` la hace ordenable; con `ordenable` en la tabla, `false` la excluye. */
  sortable?: boolean
  /** Valor con el que se ordena (por defecto `fila[key]`). */
  valorOrden?: (fila: T) => string | number | boolean | null | undefined
  render?: (valor: never, fila: T) => ReactNode
  alinear?: 'izquierda' | 'centro' | 'derecha'
  /** Ancho CSS de la columna (`'120px'`, `'20%'`). */
  ancho?: string
  /** Primera celda como cabecera de fila (`<th scope="row">`). */
  cabeceraDeFila?: boolean
  className?: string
  /** Variables CSS de la celda (compatibilidad con `ColumnaDeTabla`). */
  style?: CSSProperties
  editar?: EdicionDeCelda<T>
  /** Contenido de esta columna en la fila del pie. */
  pie?: ReactNode
}

export interface VacioDeTabla { icono?: ReactNode; titulo?: ReactNode; descripcion?: ReactNode; accion?: ReactNode }

export interface TablaProps<T> {
  columnas: Array<ColumnaTabla<T>>
  filas: T[]
  /** Nombre accesible de la tabla (va a `aria-label`). */
  etiqueta?: string
  /** Clave de cada fila; por defecto `fila.id` o el índice. */
  claveDeFila?: (fila: T, indice: number) => ClaveDeFila
  /** Todas las columnas ordenables salvo las de `sortable: false`. */
  ordenable?: boolean
  ordenInicial?: OrdenDeTabla
  /** Orden controlado (p. ej. del servidor): la tabla no reordena las filas. */
  orden?: OrdenDeTabla
  onOrden?: (orden: OrdenDeTabla) => void
  /** Selección con casillas: claves elegidas y cambio. */
  seleccion?: ClaveDeFila[]
  onSeleccion?: (claves: ClaveDeFila[]) => void
  /** Fila pulsable con ratón y teclado (Intro / Espacio). */
  onFila?: (fila: T) => void
  filaActiva?: ClaveDeFila | null
  claseDeFila?: (fila: T) => string | undefined
  cargando?: boolean
  vacio?: VacioDeTabla
  densidad?: DensidadDeTabla
  /** Cabecera pegada arriba al hacer scroll dentro de la tabla. */
  cabeceraFija?: boolean
  /** Filas propias del pie; si no, se pinta la fila con `columna.pie`. */
  pie?: ReactNode
  className?: string
}

function claseAlinear(a?: ColumnaTabla<unknown>['alinear']) {
  return a === 'derecha' ? ' ui-tabla__num' : a === 'centro' ? ' ui-tabla__centro' : ''
}

function valorCrudo<T>(fila: T, key: string): unknown {
  return (fila as Record<string, unknown>)[key]
}

function contenido<T>(col: ColumnaTabla<T>, fila: T): ReactNode {
  const v = valorCrudo(fila, col.key)
  if (col.render) return (col.render as unknown as (v: unknown, f: T) => ReactNode)(v, fila)
  return (v ?? '—') as ReactNode
}

function comparar(a: unknown, b: unknown): number {
  if (a == null && b == null) return 0
  if (a == null) return 1
  if (b == null) return -1
  if (typeof a === 'number' && typeof b === 'number') return a - b
  return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: 'base' })
}

const ES_INTERACTIVO = 'button, a, input, select, textarea, label, [role="button"], [role="checkbox"], [role="switch"]'

export function Tabla<T>({
  columnas, filas, etiqueta, claveDeFila, ordenable = false, ordenInicial, orden, onOrden,
  seleccion, onSeleccion, onFila, filaActiva, claseDeFila, cargando = false, vacio,
  densidad = 'normal', cabeceraFija = false, pie, className,
}: TablaProps<T>) {
  const t = useTextoUi()
  const [ordenInterno, setOrdenInterno] = useState<OrdenDeTabla>(ordenInicial ?? { col: null, dir: 'asc' })
  const ordenActual = orden ?? ordenInterno
  const clave = useCallback((f: T, i: number): ClaveDeFila =>
    claveDeFila ? claveDeFila(f, i) : ((f as { id?: ClaveDeFila }).id ?? i), [claveDeFila])

  const esOrdenable = (c: ColumnaTabla<T>) => (ordenable ? c.sortable !== false : c.sortable === true)

  const filasOrdenadas = useMemo(() => {
    if (orden || !ordenActual.col) return filas
    const col = columnas.find(c => c.key === ordenActual.col)
    if (!col) return filas
    const valor = (f: T) => (col.valorOrden ? col.valorOrden(f) : valorCrudo(f, col.key))
    const r = [...filas].sort((a, b) => comparar(valor(a), valor(b)))
    return ordenActual.dir === 'desc' ? r.reverse() : r
  }, [filas, columnas, orden, ordenActual.col, ordenActual.dir])

  const cambiarOrden = (key: string) => {
    const nuevo: OrdenDeTabla = ordenActual.col === key
      ? { col: key, dir: ordenActual.dir === 'asc' ? 'desc' : 'asc' }
      : { col: key, dir: 'asc' }
    if (!orden) setOrdenInterno(nuevo)
    onOrden?.(nuevo)
  }

  const conSeleccion = !!onSeleccion
  const elegidas = useMemo(() => new Set(seleccion ?? []), [seleccion])
  const claves = filasOrdenadas.map((f, i) => clave(f, i))
  const nElegidas = claves.filter(k => elegidas.has(k)).length
  const todas = claves.length > 0 && nElegidas === claves.length
  const alternarTodas = () => {
    if (!onSeleccion) return
    if (todas) onSeleccion((seleccion ?? []).filter(k => !claves.includes(k)))
    else onSeleccion([...new Set([...(seleccion ?? []), ...claves])])
  }
  const alternar = (k: ClaveDeFila) => {
    if (!onSeleccion) return
    onSeleccion(elegidas.has(k) ? (seleccion ?? []).filter(x => x !== k) : [...(seleccion ?? []), k])
  }

  const nCols = columnas.length + (conSeleccion ? 1 : 0)
  const hayPieDeColumnas = columnas.some(c => c.pie !== undefined)

  const clases = ['contecflow-table', 'ui-tabla', `ui-tabla--${densidad}`, cabeceraFija ? 'ui-tabla--cabecera-fija' : '', onFila ? 'ui-tabla--clicable' : '']
    .filter(Boolean).join(' ')

  return (
    <div className={`ui-tabla-marco${className ? ` ${className}` : ''}`}>
      <table className={clases} aria-label={etiqueta} aria-busy={cargando || undefined}>
        <thead>
          <tr>
            {conSeleccion && (
              <th scope="col" className="ui-tabla__sel">
                <Checkbox checked={todas} indeterminado={nElegidas > 0 && !todas} onChange={alternarTodas}
                  aria-label={t('uikit.seleccionar_todas')} disabled={!claves.length} />
              </th>
            )}
            {columnas.map(c => {
              const activa = ordenActual.col === c.key
              const ariaSort = activa ? (ordenActual.dir === 'asc' ? 'ascending' : 'descending') : undefined
              return (
                <th key={c.key} scope="col" aria-sort={esOrdenable(c) ? (ariaSort ?? 'none') : undefined}
                  className={`${c.ancho ? 'ui-tabla__ancho' : ''}${claseAlinear(c.alinear)}${c.className ? ` ${c.className}` : ''}`.trim() || undefined}
                  style={c.ancho ? ({ '--tabla-ancho-col': c.ancho } as CSSProperties) : undefined}>
                  {esOrdenable(c) ? (
                    <button type="button" className={`ui-tabla__orden${activa ? ' ui-tabla__orden--activa' : ''}`} onClick={() => cambiarOrden(c.key)}>
                      {c.label}
                      {activa
                        ? (ordenActual.dir === 'asc' ? <ArrowUp size={12} aria-hidden /> : <ArrowDown size={12} aria-hidden />)
                        : <ChevronsUpDown size={12} aria-hidden className="ui-tabla__orden-icono" />}
                    </button>
                  ) : c.label}
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {cargando ? (
            <tr><td colSpan={nCols} className="ui-tabla__estado">
              <span className="ui-tabla__cargando" role="status"><span className="ui-tabla__spinner" aria-hidden />{t('uikit.cargando')}</span>
            </td></tr>
          ) : filasOrdenadas.length === 0 ? (
            <tr><td colSpan={nCols} className="ui-tabla__estado">
              <div className="ui-tabla__vacio">
                {vacio?.icono && <span className="ui-tabla__vacio-icono" aria-hidden>{vacio.icono}</span>}
                <span className="ui-tabla__vacio-titulo">{vacio?.titulo ?? t('uikit.sin_datos')}</span>
                {vacio?.descripcion && <span className="ui-tabla__vacio-desc">{vacio.descripcion}</span>}
                {vacio?.accion}
              </div>
            </td></tr>
          ) : filasOrdenadas.map((f, i) => {
            const k = claves[i]
            const elegida = elegidas.has(k)
            const extra = claseDeFila?.(f)
            const cls = [elegida ? 'ui-tabla__fila--elegida' : '', filaActiva != null && filaActiva === k ? 'ui-tabla__fila--activa' : '', extra ?? ''].filter(Boolean).join(' ')
            return (
              <tr key={k} className={cls || undefined}
                aria-selected={conSeleccion ? elegida : (filaActiva != null ? filaActiva === k : undefined)}
                tabIndex={onFila ? 0 : undefined}
                onClick={onFila ? (e => { if (!(e.target as HTMLElement).closest(ES_INTERACTIVO)) onFila(f) }) : undefined}
                onKeyDown={onFila ? (e => {
                  if (e.target !== e.currentTarget) return
                  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onFila(f) }
                }) : undefined}>
                {conSeleccion && (
                  <td className="ui-tabla__sel">
                    <Checkbox checked={elegida} onChange={() => alternar(k)} aria-label={conParametros(t('uikit.seleccionar_fila', { n: i + 1 }), { n: i + 1 })} />
                  </td>
                )}
                {columnas.map(c => {
                  const clase = `${claseAlinear(c.alinear)}${c.className ? ` ${c.className}` : ''}`.trim() || undefined
                  const ed = c.editar
                  if (ed && (!ed.puede || ed.puede(f))) {
                    return (
                      <CeldaEditable key={c.key} className={clase} columna={typeof c.label === 'string' ? c.label : c.key}
                        valorTexto={ed.texto ? ed.texto(f) : ed.valor(f)} editable
                        editor={cerrar => <EditorDeColumna edicion={ed} fila={f} etiqueta={typeof c.label === 'string' ? c.label : c.key} cerrar={cerrar} />}>
                        {contenido(c, f)}
                      </CeldaEditable>
                    )
                  }
                  return c.cabeceraDeFila
                    ? <th key={c.key} scope="row" className={clase} style={c.style}>{contenido(c, f)}</th>
                    : <td key={c.key} className={clase} style={c.style}>{contenido(c, f)}</td>
                })}
              </tr>
            )
          })}
        </tbody>
        {(pie || hayPieDeColumnas) && !cargando && filasOrdenadas.length > 0 && (
          <tfoot>
            {pie ?? (
              <tr>
                {/* Con selección, la primera celda del pie ocupa también la columna de casillas. */}
                {columnas.map((c, i) => <td key={c.key} colSpan={conSeleccion && i === 0 ? 2 : undefined} className={claseAlinear(c.alinear).trim() || undefined}>{c.pie}</td>)}
              </tr>
            )}
          </tfoot>
        )}
      </table>
    </div>
  )
}

function EditorDeColumna<T>({ edicion, fila, etiqueta, cerrar }: { edicion: EdicionDeCelda<T>; fila: T; etiqueta: string; cerrar: CerrarEditor }) {
  const valor = edicion.valor(fila)
  const guardar = (v: string) => { if (v !== valor) edicion.onGuardar(fila, v) }
  if (edicion.tipo === 'lista') {
    const opciones = typeof edicion.opciones === 'function' ? edicion.opciones(fila) : (edicion.opciones ?? [])
    return <EditorLista etiqueta={etiqueta} valor={valor} opciones={opciones} cerrar={cerrar} onGuardar={guardar} />
  }
  if (edicion.tipo === 'fecha') return <EditorFecha etiqueta={etiqueta} valor={valor} cerrar={cerrar} onGuardar={guardar} />
  return <EditorTexto etiqueta={etiqueta} valor={valor} numero={edicion.tipo === 'numero'} min={edicion.min} max={edicion.max} cerrar={cerrar} onGuardar={guardar} />
}

// ── Tabla simple ─────────────────────────────────────────────────────────────

export interface TablaSimpleProps {
  children: ReactNode
  etiqueta?: string
  densidad?: DensidadDeTabla
  cabeceraFija?: boolean
  /** Clases del `<table>` (p. ej. las de una pantalla para anchos de columna). */
  claseTabla?: string
  /** Clases del contenedor con scroll. */
  className?: string
}

/** Mismo estilo que `Tabla`, con el marcado de filas y celdas que se pase. */
export function TablaSimple({ children, etiqueta, densidad = 'normal', cabeceraFija = false, claseTabla, className }: TablaSimpleProps) {
  const clases = ['contecflow-table', 'ui-tabla', `ui-tabla--${densidad}`, cabeceraFija ? 'ui-tabla--cabecera-fija' : '', claseTabla ?? '']
    .filter(Boolean).join(' ')
  return (
    <div className={`ui-tabla-marco${className ? ` ${className}` : ''}`}>
      <table className={clases} aria-label={etiqueta}>{children}</table>
    </div>
  )
}

// ── Celda editable (de VistasDeTrabajo) ──────────────────────────────────────

/** Cierra el editor; devuelve `false` si ya estaba cerrado (para no guardar dos veces). */
export type CerrarEditor = (devolverFoco: boolean) => boolean

/**
 * Celda que muestra su valor y, si es editable, se edita en el sitio: clic,
 * Intro o F2 abren el editor (con la misma altura de fila); Escape cancela,
 * Intro o salir del campo guardan, y el foco vuelve a la celda.
 */
export function CeldaEditable({ columna, valorTexto, editable, className, extra, children, editor }: {
  columna: string; valorTexto: string; editable: boolean; className?: string
  /** Contenido fijo bajo el valor. */
  extra?: ReactNode
  children: ReactNode
  editor: (cerrar: CerrarEditor) => ReactNode
}) {
  const t = useTextoUi()
  const [editando, setEditando] = useState(false)
  const abierto = useRef(false)
  const volverFoco = useRef(false)
  const boton = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!editando && volverFoco.current) { volverFoco.current = false; boton.current?.focus() }
  }, [editando])

  const abrir = () => { abierto.current = true; setEditando(true) }
  const cerrar = useCallback<CerrarEditor>(foco => {
    if (!abierto.current) return false
    abierto.current = false
    volverFoco.current = foco
    setEditando(false)
    return true
  }, [])

  if (!editable) return <td className={className}>{children}{extra}</td>
  return (
    <td className={`ui-celda-ed${className ? ` ${className}` : ''}`}>
      {editando ? <div className="ui-celda-ed__editor">{editor(cerrar)}</div> : (
        <button ref={boton} type="button" className="ui-celda-ed__ver"
          aria-label={conParametros(t('uikit.editar_celda', { columna, valor: valorTexto }), { columna, valor: valorTexto })}
          onClick={abrir}
          onKeyDown={e => { if (e.key === 'F2') { e.preventDefault(); abrir() } }}>
          {children}
        </button>
      )}
      {extra}
    </td>
  )
}

export function EditorTexto({ etiqueta, valor, numero, min, max, cerrar, onGuardar }: {
  etiqueta: string; valor: string; numero?: boolean; min?: number; max?: number
  cerrar: CerrarEditor; onGuardar: (v: string) => void
}) {
  const terminar = (v: string, foco: boolean) => { if (cerrar(foco)) onGuardar(v) }
  return (
    <input className={`ds-input ui-celda-ed__campo${numero ? ' ui-celda-ed__campo--num' : ''}`} autoFocus aria-label={etiqueta}
      type={numero ? 'number' : 'text'} min={min} max={max} defaultValue={valor}
      onFocus={e => e.currentTarget.select()}
      onKeyDown={e => {
        if (e.key === 'Enter') { e.preventDefault(); terminar(e.currentTarget.value, true) }
        else if (e.key === 'Escape') { e.preventDefault(); cerrar(true) }
      }}
      onBlur={e => terminar(e.currentTarget.value, false)} />
  )
}

export function EditorLista({ etiqueta, valor, opciones, cerrar, onGuardar }: {
  etiqueta: string; valor: string; opciones: { valor: string; etiqueta: string }[]
  cerrar: CerrarEditor; onGuardar: (v: string) => void
}) {
  return (
    <select className="ds-input ui-celda-ed__campo" autoFocus aria-label={etiqueta} value={valor}
      onChange={e => { const v = e.target.value; if (cerrar(true) && v !== valor) onGuardar(v) }}
      onKeyDown={e => { if (e.key === 'Escape') { e.preventDefault(); cerrar(true) } }}
      onBlur={() => cerrar(false)}>
      {opciones.map(o => <option key={o.valor} value={o.valor}>{o.etiqueta}</option>)}
    </select>
  )
}

export function EditorFecha({ etiqueta, valor, cerrar, onGuardar }: {
  etiqueta: string; valor: string; cerrar: CerrarEditor; onGuardar: (v: string) => void
}) {
  const raiz = useRef<HTMLDivElement>(null)
  const pendiente = useRef(valor)
  const id = useId()
  const terminar = useCallback((foco: boolean) => { if (cerrar(foco)) onGuardar(pendiente.current) }, [cerrar, onGuardar])
  // ¿El foco o el clic siguen en el campo o en su calendario (que sale en un portal)?
  const dentro = useCallback((n: Node | null) =>
    !!n && (!!raiz.current?.contains(n) || !!document.getElementById(`${id}-panel`)?.contains(n)), [id])

  // Escuchas en `document` (después de las del campo): si el campo ya usó la
  // tecla (Escape con el calendario abierto) llega con defaultPrevented.
  useEffect(() => {
    const fuera = (e: Event) => { if (!dentro(e.target as Node)) terminar(false) }
    const teclas = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement
      if (e.defaultPrevented || !raiz.current?.contains(el)) return
      if (e.key === 'Escape') { e.preventDefault(); cerrar(true) }
      else if (e.key === 'Enter' && el.tagName === 'INPUT') { e.preventDefault(); terminar(true) }
    }
    document.addEventListener('mousedown', fuera)
    document.addEventListener('focusin', fuera)
    document.addEventListener('keydown', teclas)
    return () => {
      document.removeEventListener('mousedown', fuera)
      document.removeEventListener('focusin', fuera)
      document.removeEventListener('keydown', teclas)
    }
  }, [dentro, terminar, cerrar])

  return (
    <div ref={raiz} className="ui-celda-ed__fecha">
      <CampoFecha id={id} className="ds-input ui-celda-ed__campo" autoFocus aria-label={etiqueta} value={valor}
        onChange={v => { pendiente.current = v; if (v) terminar(true) }} />
    </div>
  )
}

export default Tabla

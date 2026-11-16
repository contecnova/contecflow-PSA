/**
 * RejillaPersonaDia — la rejilla única «fila × día» (o «fila × semana») de la
 * app (16-11-2026). Una sola forma para el calendario y la cobertura de
 * ausencias, el cuadrante de turnos, el mapa de calor de recursos, la
 * previsión, la capacidad y la carga por persona del planificador.
 *
 *  · Filas: personas (avatar + nombre + línea secundaria) u otra cosa con su
 *    propia `marca` (un turno con su color).
 *  · Columnas: días (día de la semana + número; fin de semana y festivo
 *    atenuados; hoy resaltado) o semanas. `columnasDeDias` / `columnasDeSemanas`
 *    las construyen con el formato de fecha del idioma activo.
 *  · Celdas: estado coloreado con un tono del tema o con el color del dato
 *    (tipo de ausencia, turno), leyenda debajo, detalle en el tooltip y para
 *    el lector de pantalla.
 *  · Scroll horizontal y vertical dentro de su contenedor, con la cabecera y
 *    la primera columna fijas.
 *  · Accesible: tabla con caption, cabeceras con scope; si las celdas se
 *    pulsan, son botones con foco itinerante (flechas, Inicio/Fin) y una sola
 *    parada de tabulador.
 *
 * `NavegadorDeMes` es el navegador de mes común de estas vistas.
 */
import { useCallback, useState } from 'react'
import type { ButtonHTMLAttributes, CSSProperties, KeyboardEvent, ReactNode } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { Avatar, Button } from './index'
import { useTextoUi } from './useTextoUi'
import { fmtMonth, formateadorDeFecha } from '../../utils/helpers'
import './RejillaPersonaDia.css'

export type TonoDeRejilla = 'success' | 'warning' | 'danger' | 'info' | 'accent' | 'purple' | 'orange' | 'neutral' | 'vacio'

export interface EntradaDeLeyenda {
  clave: string
  etiqueta: string
  /** Tono del tema. Si hay `color`, manda el color. */
  tono?: TonoDeRejilla
  /** Color que viene de un dato (tipo de ausencia, turno). */
  color?: string | null
  /** Muestra con borde discontinuo (pendiente, tentativa). */
  tentativa?: boolean
}

export interface FilaDeRejilla {
  id: string
  nombre: string
  /** Segunda línea (rol, departamento, media…). */
  sub?: ReactNode
  avatarUrl?: string | null
  /** Sustituye al avatar (p. ej. la muestra de color de un turno). */
  marca?: ReactNode
  sinAvatar?: boolean
}

export interface ColumnaDeRejilla {
  clave: string
  etiqueta: ReactNode
  /** Línea pequeña encima de la etiqueta (día de la semana). */
  sub?: ReactNode
  /** Fin de semana, festivo, semana fuera de plazo… */
  atenuada?: boolean
  hoy?: boolean
  /** Tooltip de la cabecera (fecha larga, nombre del festivo). */
  titulo?: string
}

export interface CeldaDeRejilla {
  /** Clave de la leyenda: toma de ella el tono o el color. */
  estado?: string
  tono?: TonoDeRejilla
  color?: string | null
  /** Pendiente / tentativa: borde discontinuo. */
  tentativa?: boolean
  marcada?: boolean
  contenido?: ReactNode
  /** Detalle para el tooltip y el lector de pantalla. */
  detalle?: string
  /** Eventos de la celda: la convierten en botón (pintar, soltar…). */
  boton?: ButtonHTMLAttributes<HTMLButtonElement>
}

export interface RejillaPersonaDiaProps<F extends FilaDeRejilla = FilaDeRejilla> {
  /** Caption accesible de la tabla. */
  titulo: string
  /** Cabecera de la primera columna («Persona», «Turno»). */
  cabeceraFilas: string
  filas: F[]
  columnas: ColumnaDeRejilla[]
  celda: (fila: F, columna: ColumnaDeRejilla) => CeldaDeRejilla | null | undefined
  leyenda?: EntradaDeLeyenda[]
  /** Texto de ayuda al final de la leyenda. */
  notaLeyenda?: ReactNode
  /** Pulsar una celda (todas pasan a ser botones). */
  onCelda?: (fila: F, columna: ColumnaDeRejilla) => void
  /** Pulsar el nombre de la fila (seleccionar). */
  onFila?: (fila: F) => void
  filaActiva?: string | null
  /** `semana` ensancha las columnas. */
  unidad?: 'dia' | 'semana'
  className?: string
}

const TONOS = new Set<TonoDeRejilla>(['success', 'warning', 'danger', 'info', 'accent', 'purple', 'orange', 'neutral', 'vacio'])


function clasesDeTono(tono?: TonoDeRejilla, color?: string | null): string {
  if (color) return ' rpd-tono--color'
  return tono && TONOS.has(tono) ? ` rpd-tono--${tono}` : ''
}

/** La muestra de color de una entrada de la leyenda o de un estado. */
export function MuestraDeRejilla({ tono, color, tentativa }: { tono?: TonoDeRejilla; color?: string | null; tentativa?: boolean }) {
  return <span aria-hidden className={`rpd-muestra${clasesDeTono(tono, color)}${tentativa ? ' rpd-celda--tentativa' : ''}`} style={color ? { '--rpd-color': color } as CSSProperties : undefined} />
}

export default function RejillaPersonaDia<F extends FilaDeRejilla = FilaDeRejilla>({
  titulo, cabeceraFilas, filas, columnas, celda, leyenda, notaLeyenda, onCelda, onFila, filaActiva,
  unidad = 'dia', className,
}: RejillaPersonaDiaProps<F>) {
  const t = useTextoUi()
  const [foco, setFoco] = useState<string | null>(null)
  const porClave = new Map((leyenda ?? []).map(l => [l.clave, l]))

  // Flechas, Inicio y Fin entre las celdas pulsables (foco itinerante).
  const teclas = useCallback((e: KeyboardEvent<HTMLTableElement>) => {
    const el = e.target as HTMLElement
    const f = Number(el.dataset.rpdF), c = Number(el.dataset.rpdC)
    if (Number.isNaN(f) || Number.isNaN(c)) return
    const mov: Record<string, [number, number]> = { ArrowRight: [0, 1], ArrowLeft: [0, -1], ArrowDown: [1, 0], ArrowUp: [-1, 0] }
    const tabla = e.currentTarget
    const en = (fi: number, ci: number) => tabla.querySelector<HTMLElement>(`[data-rpd-f="${fi}"][data-rpd-c="${ci}"]`)
    let sig: HTMLElement | null = null
    if (mov[e.key]) {
      // Salta las celdas que no se pulsan (rejillas dispersas, como un calendario).
      const [df, dc] = mov[e.key]
      for (let fi = f + df, ci = c + dc; fi >= 0 && fi < filas.length && ci >= 0 && ci < columnas.length && !sig; fi += df, ci += dc) sig = en(fi, ci)
    } else if (e.key === 'Home' || e.key === 'End') {
      const fila = [...tabla.querySelectorAll<HTMLElement>(`[data-rpd-f="${f}"]`)]
      sig = (e.key === 'Home' ? fila[0] : fila[fila.length - 1]) ?? null
    }
    if (sig) { e.preventDefault(); sig.focus() }
  }, [columnas.length, filas.length])

  // Las celdas se calculan una vez: así se sabe cuál es la primera pulsable (la que recibe el Tab).
  const matriz = filas.map(f => columnas.map(c => celda(f, c) ?? {}))
  const esPulsable = (c: CeldaDeRejilla) => !!onCelda || !!c.boton
  let primera: string | null = null
  for (let fi = 0; fi < matriz.length && primera == null; fi++) {
    const ci = matriz[fi].findIndex(esPulsable)
    if (ci >= 0) primera = `${fi}:${ci}`
  }
  const [ff, fc] = (foco ?? '').split(':').map(Number)
  const enFoco = foco != null ? matriz[ff]?.[fc] : undefined
  const conTab = enFoco && esPulsable(enFoco) ? foco : primera

  return (
    <div className={`rpd${className ? ` ${className}` : ''}`}>
      <div className="rpd-scroll" role="region" aria-label={titulo} tabIndex={0}>
        <table className={`rpd-tabla rpd-tabla--${unidad}`} onKeyDown={teclas}>
          <caption className="rpd-oculto">{titulo}</caption>
          <thead>
            <tr>
              <th scope="col" className="rpd-esquina">{cabeceraFilas}</th>
              {columnas.map(col => (
                <th key={col.clave} scope="col" title={col.titulo} aria-current={col.hoy ? 'date' : undefined}
                  className={`rpd-cab${col.atenuada ? ' rpd-col--atenuada' : ''}${col.hoy ? ' rpd-col--hoy' : ''}`}>
                  {col.sub != null && <span className="rpd-cab-sub">{col.sub}</span>}
                  <span className="rpd-cab-etq">{col.etiqueta}</span>
                  {col.titulo && <span className="rpd-oculto">{col.titulo}</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filas.map((fila, fi) => (
              <tr key={fila.id} className={filaActiva === fila.id ? 'rpd-fila--activa' : undefined}>
                <th scope="row" className="rpd-fila">
                  {(() => {
                    const persona = (
                      <>
                        {fila.marca ?? (!fila.sinAvatar && <Avatar name={fila.nombre} size={24} url={fila.avatarUrl ?? undefined} />)}
                        <span className="rpd-fila-texto">
                          <span className="rpd-fila-nombre">{fila.nombre}</span>
                          {fila.sub != null && <span className="rpd-fila-sub">{fila.sub}</span>}
                        </span>
                      </>
                    )
                    return onFila
                      ? <button type="button" className="rpd-fila-boton" aria-pressed={filaActiva === fila.id} onClick={() => onFila(fila)}>{persona}</button>
                      : <span className="rpd-fila-boton rpd-fila-boton--fijo">{persona}</span>
                  })()}
                </th>
                {columnas.map((col, ci) => {
                  const c = matriz[fi][ci]
                  const ley = c.estado ? porClave.get(c.estado) : undefined
                  const color = c.color ?? ley?.color ?? null
                  const tono = c.tono ?? ley?.tono
                  const clases = `rpd-celda${clasesDeTono(tono, color)}${c.tentativa ? ' rpd-celda--tentativa' : ''}${c.marcada ? ' rpd-celda--marcada' : ''}`
                  const detalle = c.detalle
                  const tdClase = `rpd-td${col.atenuada ? ' rpd-col--atenuada' : ''}${col.hoy ? ' rpd-col--hoy' : ''}`
                  if (!esPulsable(c)) {
                    return (
                      <td key={col.clave} className={tdClase} title={detalle}>
                        <div className={clases} style={color ? { '--rpd-color': color } as CSSProperties : undefined}>
                          {c.contenido}
                          {detalle && <span className="rpd-oculto">{detalle}</span>}
                        </div>
                      </td>
                    )
                  }
                  const clave = `${fi}:${ci}`
                  // Foco itinerante: una sola celda en el orden de tabulación (la última enfocada, o la primera pulsable).
                  const recibeTab = conTab === clave
                  const { onClick, onFocus, className: claseExtra, ...resto } = c.boton ?? {}
                  return (
                    <td key={col.clave} className={tdClase}>
                      <button type="button" {...resto} data-rpd-f={fi} data-rpd-c={ci}
                        tabIndex={recibeTab ? 0 : -1}
                        className={`${clases} rpd-celda--boton${claseExtra ? ` ${claseExtra}` : ''}`}
                        style={color ? { '--rpd-color': color } as CSSProperties : undefined} title={detalle} aria-label={detalle}
                        onFocus={e => { setFoco(clave); onFocus?.(e) }}
                        onClick={e => { onClick?.(e); onCelda?.(fila, col) }}>
                        {c.contenido}
                      </button>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {(leyenda?.length || notaLeyenda) && (
        <ul className="rpd-leyenda" aria-label={t('uikit.leyenda')}>
          {(leyenda ?? []).map(l => (
            <li key={l.clave}><MuestraDeRejilla tono={l.tono} color={l.color} tentativa={l.tentativa} />{l.etiqueta}</li>
          ))}
          {notaLeyenda && <li className="rpd-leyenda-nota">{notaLeyenda}</li>}
        </ul>
      )}
    </div>
  )
}

// ── Columnas ─────────────────────────────────────────────────────────────────

/** 'YYYY-MM-DD' de una fecha en hora local. */
export function isoLocal(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** Primer y último día del mes de `ref`. */
export function rangoDelMes(ref: Date): { desde: string; hasta: string } {
  return { desde: isoLocal(new Date(ref.getFullYear(), ref.getMonth(), 1)), hasta: isoLocal(new Date(ref.getFullYear(), ref.getMonth() + 1, 0)) }
}

/** Una columna por día entre `desde` y `hasta` (incluidos). Festivos: fecha → nombre. */
export function columnasDeDias(desde: string, hasta: string, opciones: { festivos?: Map<string, string> } = {}): ColumnaDeRejilla[] {
  const hoy = isoLocal(new Date())
  const corto = formateadorDeFecha({ weekday: 'short' })
  const largo = formateadorDeFecha({ weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
  const fuera: ColumnaDeRejilla[] = []
  for (let d = new Date(`${desde}T00:00:00`); isoLocal(d) <= hasta; d.setDate(d.getDate() + 1)) {
    const iso = isoLocal(d)
    const festivo = opciones.festivos?.get(iso)
    fuera.push({
      clave: iso,
      etiqueta: d.getDate(),
      sub: corto.format(d),
      atenuada: d.getDay() === 0 || d.getDay() === 6 || festivo != null,
      hoy: iso === hoy,
      titulo: festivo ? `${largo.format(d)} · ${festivo}` : largo.format(d),
    })
  }
  return fuera
}

/** Una columna por semana a partir de su lunes ('YYYY-MM-DD'). `etiqueta` sustituye a la fecha corta. */
export function columnasDeSemanas(lunes: string[], etiqueta?: (lunes: string, i: number) => ReactNode): ColumnaDeRejilla[] {
  const hoy = isoLocal(new Date())
  const corta = formateadorDeFecha({ day: 'numeric', month: 'short' })
  const larga = formateadorDeFecha({ day: 'numeric', month: 'long', year: 'numeric' })
  return lunes.map((l, i) => {
    const ini = new Date(`${l.slice(0, 10)}T00:00:00`)
    const fin = new Date(ini); fin.setDate(fin.getDate() + 6)
    return {
      clave: l,
      etiqueta: etiqueta ? etiqueta(l, i) : corta.format(ini),
      hoy: Number.isNaN(ini.getTime()) ? false : isoLocal(ini) <= hoy && hoy <= isoLocal(fin),
      titulo: Number.isNaN(ini.getTime()) ? undefined : `${larga.format(ini)} – ${larga.format(fin)}`,
    }
  })
}

// ── Navegador de mes ─────────────────────────────────────────────────────────

/** Mes anterior / mes / siguiente / hoy, con el formato de mes de la app. */
export function NavegadorDeMes({ mes, onCambiar }: { mes: Date; onCambiar: (mes: Date) => void }) {
  const t = useTextoUi()
  const mover = (n: number) => onCambiar(new Date(mes.getFullYear(), mes.getMonth() + n, 1))
  const ahora = new Date()
  const esEste = ahora.getFullYear() === mes.getFullYear() && ahora.getMonth() === mes.getMonth()
  return (
    <div className="rpd-nav" role="group" aria-label={t('uikit.mes')}>
      <Button size="sm" variant="ghost" icon={<ChevronLeft size={14} />} title={t('uikit.mes_anterior')} aria-label={t('uikit.mes_anterior')} onClick={() => mover(-1)} />
      <span className="rpd-nav-mes" aria-live="polite">{fmtMonth(mes)}</span>
      <Button size="sm" variant="ghost" icon={<ChevronRight size={14} />} title={t('uikit.mes_siguiente')} aria-label={t('uikit.mes_siguiente')} onClick={() => mover(1)} />
      <Button size="sm" variant="secondary" disabled={esEste} onClick={() => onCambiar(new Date(ahora.getFullYear(), ahora.getMonth(), 1))}>{t('uikit.hoy')}</Button>
    </div>
  )
}

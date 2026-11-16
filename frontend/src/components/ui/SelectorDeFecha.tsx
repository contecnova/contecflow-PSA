import React, { useCallback, useEffect, useId, useImperativeHandle, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties, FocusEvent, KeyboardEvent, ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Calendar, ChevronLeft, ChevronRight, Clock } from 'lucide-react'
import { useIdiomaUi, useTextoUi } from './useTextoUi'
import {
  ahoraEnZona, comparar, enmascarar, etiquetaDeDia, instanteEnZona, isoEnZona, leerTexto, leerValor,
  marcadorDe, moverFecha, nombresDeDias, nombresDeMeses, paredEnZona, patronDeFecha, primerDiaDeSemana,
  rejillaDelMes, textoDe, valorDe, zonaDelNavegador, diaDeSemana,
  type ModoFecha, type Pared,
} from '../../utils/fechas'
import './SelectorDeFecha.css'

/**
 * CampoFecha — el selector de fecha propio del kit (16-11-2026).
 *
 * Nada de `<input type="date|datetime-local|time">`: el nativo pinta el formato
 * de la región del navegador. Aquí la fecha se escribe y se ve con el formato
 * del idioma de la app (es dd/mm/aaaa, en el del inglés de la app, zh
 * aaaa年m月d日), sale del formateador de fechas de la app y es igual en
 * cualquier navegador.
 *
 *   <CampoFecha value="2026-11-16" onChange={v => …} />                 fecha
 *   <CampoFecha modo="fechaHora" value="2026-11-16T08:30" onChange={…} /> fecha y hora
 *   <CampoFecha modo="hora" value="08:30" onChange={…} />                 hora
 *   <CampoRangoDeFechas desde={…} hasta={…} onChange={({desde, hasta}) => …} />
 *
 * - Campo escribible con máscara (los separadores salen solos) y validación al
 *   escribir; `onChange` solo recibe valores completos y válidos ('' al vaciar).
 * - Calendario desplegable propio: mes/año, «Hoy», teclado completo (flechas,
 *   Re Pág/Av Pág ±1 mes, con Mayús ±1 año, Inicio/Fin de semana, Intro/Espacio
 *   elige, Escape cierra) y patrón ARIA de grid. Primer día de la semana según
 *   el idioma.
 * - `min`/`max` en el mismo formato que `value`.
 * - `zona` (solo `fechaHora`): `value` es un instante ISO y se edita en esa
 *   zona; `onChange` devuelve ISO con el desfase de la zona. «Hoy» y «Ahora»
 *   son siempre los de la zona del usuario (`zona` o la del navegador).
 */
export interface CampoFechaProps {
  value?: string | null
  onChange?: (valor: string) => void
  modo?: ModoFecha
  min?: string
  max?: string
  zona?: string
  /** Pinta un rango en el calendario (los días entre ambos). */
  rango?: { desde?: string | null; hasta?: string | null }
  /** Paso del selector de minutos (por defecto 1). */
  pasoMinutos?: number
  id?: string
  name?: string
  className?: string
  style?: CSSProperties
  placeholder?: string
  disabled?: boolean
  required?: boolean
  readOnly?: boolean
  autoFocus?: boolean
  title?: string
  onBlur?: (e: FocusEvent<HTMLInputElement>) => void
  onFocus?: (e: FocusEvent<HTMLInputElement>) => void
  'aria-label'?: string
  'aria-labelledby'?: string
  'aria-describedby'?: string
  'aria-invalid'?: boolean | 'true' | 'false'
  'aria-required'?: boolean | 'true' | 'false'
  /** Ref del `<input>` de texto (lo usa `DateInput`). */
  refCampo?: React.Ref<HTMLInputElement>
  /** Idioma del formato y de los nombres (por defecto el de la app). El portal pasa el suyo. */
  idioma?: string
  /** Textos propios (el portal, con sus 8 idiomas); lo que falte sale del kit. */
  textos?: TextosDeFecha
  [atributoData: `data-${string}`]: string | undefined
}

const dos = (n: number) => String(n).padStart(2, '0')

export type ClaveTextoFecha =
  | 'abrir_calendario' | 'abrir_hora' | 'elegir_fecha' | 'elegir_hora' | 'mes_anterior' | 'mes_siguiente'
  | 'mes' | 'anio' | 'hora' | 'horas' | 'minutos' | 'hoy' | 'ahora' | 'listo' | 'invalida' | 'min' | 'max'
  | 'rango' | 'desde' | 'hasta'
export type TextosDeFecha = Partial<Record<ClaveTextoFecha, string>>

/** Texto del kit (`fecha.<clave>`) o el propio que se haya pasado. */
function useTextosDeFecha(textos?: TextosDeFecha): (k: ClaveTextoFecha) => string {
  const t = useTextoUi()
  return useCallback((k: ClaveTextoFecha) => textos?.[k] ?? t(`fecha.${k}`), [t, textos])
}

function interpolar(texto: string, params: Record<string, string | number>): string {
  return texto.replace(/\{(\w+)\}/g, (_, k) => (k in params ? String(params[k]) : `{${k}}`))
}

/** Valor externo → pared que se edita (con `zona`, el instante en esa zona). */
function aPared(v: string | null | undefined, modo: ModoFecha, zona?: string): Pared | null {
  if (!v) return null
  if (zona && modo === 'fechaHora' && /[zZ]|[+-]\d{2}:?\d{2}$/.test(v)) {
    const d = new Date(v)
    return isNaN(d.getTime()) ? null : paredEnZona(d, zona)
  }
  return leerValor(v, modo)
}

function deParedAValor(p: Pared, modo: ModoFecha, zona?: string): string {
  if (zona && modo === 'fechaHora') return isoEnZona(instanteEnZona(p, zona), zona)
  return valorDe(p, modo)
}

export function CampoFecha(props: CampoFechaProps) {
  const {
    value, onChange, modo = 'fecha', min, max, zona, rango, pasoMinutos = 1,
    id, name, className, style, placeholder, disabled, required, readOnly, autoFocus, title,
    onBlur, onFocus, idioma, textos, refCampo, ...resto
  } = props
  const tx = useTextosDeFecha(textos)
  const langApp = useIdiomaUi()
  const lang = idioma || langApp
  const patron = useMemo(() => patronDeFecha(lang), [lang])
  const generado = useId()
  const base = id || `fecha-${generado}`
  const idPanel = `${base}-panel`
  const idError = `${base}-error`

  const actual = useMemo(() => aPared(value, modo, zona), [value, modo, zona])
  const pMin = useMemo(() => aPared(min, modo, zona), [min, modo, zona])
  const pMax = useMemo(() => aPared(max, modo, zona), [max, modo, zona])

  const [texto, setTexto] = useState(() => textoDe(actual, modo, patron))
  const [error, setError] = useState<string | null>(null)
  const [abierto, setAbierto] = useState(false)
  const raiz = useRef<HTMLDivElement>(null)
  const campo = useRef<HTMLInputElement>(null)
  useImperativeHandle(refCampo, () => campo.current as HTMLInputElement)

  // El valor de fuera manda cuando cambia (y al cambiar de idioma).
  useEffect(() => {
    setTexto(textoDe(actual, modo, patron))
    setError(null)
  }, [actual, modo, patron])

  const fueraDeLimites = useCallback((p: Pared) =>
    (pMin && comparar(p, pMin, modo) < 0) || (pMax && comparar(p, pMax, modo) > 0), [pMin, pMax, modo])

  const emitir = useCallback((p: Pared | null) => {
    if (!p) { onChange?.(''); return }
    onChange?.(deParedAValor(p, modo, zona))
  }, [onChange, modo, zona])

  const errorDeLimites = useCallback((p: Pared) => {
    if (pMin && comparar(p, pMin, modo) < 0) return interpolar(tx('min'), { fecha: textoDe(pMin, modo, patron) })
    if (pMax && comparar(p, pMax, modo) > 0) return interpolar(tx('max'), { fecha: textoDe(pMax, modo, patron) })
    return null
  }, [pMin, pMax, modo, patron, tx])

  const alEscribir = (bruto: string) => {
    const enmascarado = enmascarar(bruto, modo, patron)
    setTexto(enmascarado)
    if (!enmascarado) { setError(null); if (value) emitir(null); return }
    const p = leerTexto(enmascarado, modo, patron)
    const completo = enmascarado.replace(/\D/g, '').length >= (modo === 'hora' ? 4 : modo === 'fecha' ? 8 : 12)
    if (!p) { setError(completo ? tx('invalida') : null); return }
    const e = errorDeLimites(p)
    setError(e)
    if (!e) emitir(p)
  }

  const alSalir = (e: FocusEvent<HTMLInputElement>) => {
    const p = leerTexto(texto, modo, patron)
    if (texto && !p) setError(tx('invalida'))
    else if (p && !errorDeLimites(p)) setTexto(textoDe(p, modo, patron))
    onBlur?.(e)
  }

  const alTeclear = (e: KeyboardEvent<HTMLInputElement>) => {
    if ((e.key === 'ArrowDown' && e.altKey) || (e.key === 'ArrowDown' && !texto)) {
      e.preventDefault(); setAbierto(true)
    } else if (e.key === 'Escape' && abierto) {
      e.preventDefault(); setAbierto(false)
    }
  }

  const cerrar = useCallback((devolverFoco = true) => {
    setAbierto(false)
    if (devolverFoco) campo.current?.focus()
  }, [])

  const elegir = (elegida: Pared, cerrarTras: boolean) => {
    let p = elegida
    if (fueraDeLimites(p)) {
      // Un día fuera de límites no se elige; con hora, se ajusta al límite del mismo día.
      if (modo !== 'fechaHora') return
      if (pMin && comparar(p, pMin, 'fecha') === 0) p = { ...pMin }
      else if (pMax && comparar(p, pMax, 'fecha') === 0) p = { ...pMax }
      else return
    }
    setTexto(textoDe(p, modo, patron))
    setError(null)
    emitir(p)
    if (cerrarTras) cerrar()
  }

  const invalido = !!error || props['aria-invalid'] === true || props['aria-invalid'] === 'true'
  const describedBy = [props['aria-describedby'], error ? idError : null].filter(Boolean).join(' ') || undefined
  const Icono = modo === 'hora' ? Clock : Calendar
  const etiquetaBoton = modo === 'hora' ? tx('abrir_hora') : tx('abrir_calendario')
  const datos = Object.fromEntries(Object.entries(resto).filter(([k]) => k.startsWith('data-')))

  return (
    <div ref={raiz} className={`uifecha${className ? ` ${className}` : ' uifecha--caja'}${invalido ? ' uifecha--error' : ''}${disabled ? ' uifecha--off' : ''}`} style={style} {...datos}>
      <input
        ref={campo}
        id={base}
        name={name}
        type="text"
        inputMode="numeric"
        autoComplete="off"
        className="uifecha-campo"
        value={texto}
        placeholder={placeholder ?? marcadorDe(modo, patron)}
        disabled={disabled}
        readOnly={readOnly}
        required={required || undefined}
        autoFocus={autoFocus}
        title={title}
        aria-label={props['aria-label']}
        aria-labelledby={props['aria-labelledby']}
        aria-describedby={describedBy}
        aria-invalid={invalido || undefined}
        aria-required={props['aria-required']}
        onChange={e => alEscribir(e.target.value)}
        onBlur={alSalir}
        onFocus={onFocus}
        onKeyDown={alTeclear}
      />
      {!readOnly && (
        <button
          type="button"
          className="uifecha-boton"
          aria-label={etiquetaBoton}
          title={etiquetaBoton}
          aria-haspopup="dialog"
          aria-expanded={abierto}
          aria-controls={abierto ? idPanel : undefined}
          disabled={disabled}
          onClick={() => setAbierto(a => !a)}
        >
          <Icono size={14} aria-hidden />
        </button>
      )}
      {error && <span id={idError} role="alert" className="uifecha-error">{error}</span>}
      {abierto && (
        <Panel
          ancla={raiz}
          id={idPanel}
          modo={modo}
          actual={actual}
          pMin={pMin}
          pMax={pMax}
          zona={zona || zonaDelNavegador()}
          rango={rango}
          pasoMinutos={pasoMinutos}
          lang={lang}
          textos={textos}
          fueraDeLimites={fueraDeLimites}
          onElegir={elegir}
          onCerrar={cerrar}
        />
      )}
    </div>
  )
}

// ── Panel desplegable ────────────────────────────────────────────────────────
interface PanelProps {
  ancla: React.RefObject<HTMLDivElement | null>
  id: string
  modo: ModoFecha
  actual: Pared | null
  pMin: Pared | null
  pMax: Pared | null
  zona: string
  rango?: { desde?: string | null; hasta?: string | null }
  pasoMinutos: number
  lang: string
  textos?: TextosDeFecha
  fueraDeLimites: (p: Pared) => boolean | null
  onElegir: (p: Pared, cerrar: boolean) => void
  onCerrar: (devolverFoco?: boolean) => void
}

function Panel({ ancla, id, modo, actual, pMin, pMax, zona, rango, pasoMinutos, lang, textos, fueraDeLimites, onElegir, onCerrar }: PanelProps) {
  const tx = useTextosDeFecha(textos)
  const panel = useRef<HTMLDivElement>(null)
  const rejilla = useRef<HTMLTableElement>(null)
  const ahora = ahoraEnZona(zona)
  const inicial = actual ?? { ...ahora, h: modo === 'fechaHora' ? ahora.h : 0, mi: modo === 'fechaHora' ? ahora.mi : 0 }
  const [foco, setFoco] = useState<Pared>(inicial)
  const [hora, setHora] = useState({ h: inicial.h, mi: inicial.mi })
  const [pos, setPos] = useState<{ top: number; left: number; arriba: boolean }>({ top: 0, left: 0, arriba: false })
  const [moverFoco, setMoverFoco] = useState(true)

  const primerDia = useMemo(() => primerDiaDeSemana(lang), [lang])
  const dias = useMemo(() => nombresDeDias(primerDia, lang, 'short'), [primerDia, lang])
  const diasLargos = useMemo(() => nombresDeDias(primerDia, lang, 'long'), [primerDia, lang])
  const meses = useMemo(() => nombresDeMeses(lang), [lang])
  const semanas = useMemo(() => rejillaDelMes(foco.y, foco.m, primerDia), [foco.y, foco.m, primerDia])
  const rDesde = rango?.desde ? leerValor(rango.desde, modo === 'hora' ? 'fecha' : modo) : null
  const rHasta = rango?.hasta ? leerValor(rango.hasta, modo === 'hora' ? 'fecha' : modo) : null

  // Posición fija junto al campo (en portal: un modal con overflow no lo corta).
  useLayoutEffect(() => {
    const colocar = () => {
      const r = ancla.current?.getBoundingClientRect()
      const alto = panel.current?.offsetHeight ?? 340
      const ancho = panel.current?.offsetWidth ?? 300
      if (!r) return
      const vh = window.innerHeight, vw = window.innerWidth
      const arriba = r.bottom + alto + 8 > vh && r.top - alto - 8 > 0
      const top = arriba ? r.top - alto - 4 : r.bottom + 4
      const left = Math.max(8, Math.min(r.left, vw - ancho - 8))
      setPos({ top, left, arriba })
    }
    colocar()
    window.addEventListener('resize', colocar)
    window.addEventListener('scroll', colocar, true)
    return () => { window.removeEventListener('resize', colocar); window.removeEventListener('scroll', colocar, true) }
  }, [ancla])

  // Clic fuera cierra (sin robar el foco a donde se ha hecho clic).
  useEffect(() => {
    const fuera = (e: MouseEvent) => {
      const n = e.target as Node
      if (panel.current?.contains(n) || ancla.current?.contains(n)) return
      onCerrar(false)
    }
    document.addEventListener('mousedown', fuera)
    return () => document.removeEventListener('mousedown', fuera)
  }, [ancla, onCerrar])

  // El foco va al día enfocado (roving tabindex del grid).
  useEffect(() => {
    if (!moverFoco || modo === 'hora') return
    rejilla.current?.querySelector<HTMLButtonElement>('button[tabindex="0"]')?.focus()
  }, [foco, moverFoco, modo])

  useEffect(() => {
    if (modo === 'hora') panel.current?.querySelector<HTMLSelectElement>('select')?.focus()
  }, [modo])

  const conHora = (p: Pared): Pared => ({ ...p, h: modo === 'fechaHora' ? hora.h : 0, mi: modo === 'fechaHora' ? hora.mi : 0 })

  const teclaDia = (e: KeyboardEvent<HTMLTableElement>) => {
    let n: Pared | null = null
    switch (e.key) {
      case 'ArrowLeft': n = moverFecha(foco, 'dia', -1); break
      case 'ArrowRight': n = moverFecha(foco, 'dia', 1); break
      case 'ArrowUp': n = moverFecha(foco, 'dia', -7); break
      case 'ArrowDown': n = moverFecha(foco, 'dia', 7); break
      case 'PageUp': n = moverFecha(foco, e.shiftKey ? 'anio' : 'mes', -1); break
      case 'PageDown': n = moverFecha(foco, e.shiftKey ? 'anio' : 'mes', 1); break
      case 'Home': n = moverFecha(foco, 'dia', -((diaDeSemana(foco) - primerDia + 7) % 7)); break
      case 'End': n = moverFecha(foco, 'dia', 6 - ((diaDeSemana(foco) - primerDia + 7) % 7)); break
      case 'Enter':
      case ' ':
        e.preventDefault()
        onElegir(conHora(foco), modo === 'fecha')
        return
      default: return
    }
    e.preventDefault()
    setMoverFoco(true)
    setFoco(n)
  }

  const teclaPanel = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); onCerrar(true) }
  }

  const cambiarHora = (h: number, mi: number) => {
    setHora({ h, mi })
    const p = { ...(actual ?? foco), h, mi }
    if (modo === 'hora' || actual) onElegir(p, false)
  }

  const anioActual = ahora.y
  const anioMin = pMin && modo !== 'hora' ? pMin.y : Math.min(foco.y, anioActual) - 100
  const anioMax = pMax && modo !== 'hora' ? pMax.y : Math.max(foco.y, anioActual) + 50
  const anios = Array.from({ length: anioMax - anioMin + 1 }, (_, i) => anioMin + i)
  const horas = Array.from({ length: 24 }, (_, i) => i)
  const paso = Math.max(1, pasoMinutos)
  const minutos = Array.from({ length: Math.ceil(60 / paso) }, (_, i) => i * paso)
  if (!minutos.includes(hora.mi)) { minutos.push(hora.mi); minutos.sort((a, b) => a - b) }

  const enRango = (c: Pared) => rDesde && rHasta && comparar(c, rDesde, 'fecha') >= 0 && comparar(c, rHasta, 'fecha') <= 0
  const mesAnterior = moverFecha({ ...foco, d: 1 }, 'mes', -1)
  const mesSiguiente = moverFecha({ ...foco, d: 1 }, 'mes', 1)
  const sinAnterior = !!pMin && modo !== 'hora' && mesAnterior.y * 12 + mesAnterior.m < pMin.y * 12 + pMin.m
  const sinSiguiente = !!pMax && modo !== 'hora' && mesSiguiente.y * 12 + mesSiguiente.m > pMax.y * 12 + pMax.m
  const etiquetaMes = `${meses[foco.m - 1]} ${foco.y}`
  const idTitulo = `${id}-titulo`

  const selectorDeHora = (
    <div className="uifecha-hora" role="group" aria-label={tx('hora')}>
      <Clock size={14} aria-hidden className="uifecha-hora-icono" />
      <select className="uifecha-select" aria-label={tx('horas')} value={hora.h}
        onChange={e => cambiarHora(+e.target.value, hora.mi)}>
        {horas.map(h => <option key={h} value={h}>{dos(h)}</option>)}
      </select>
      <span aria-hidden>:</span>
      <select className="uifecha-select" aria-label={tx('minutos')} value={hora.mi}
        onChange={e => cambiarHora(hora.h, +e.target.value)}>
        {minutos.map(m => <option key={m} value={m}>{dos(m)}</option>)}
      </select>
    </div>
  )

  const contenido: ReactNode = modo === 'hora' ? (
    <>
      {selectorDeHora}
      <div className="uifecha-pie">
        <button type="button" className="uifecha-enlace" onClick={() => { setHora({ h: ahora.h, mi: ahora.mi }); onElegir({ ...ahora }, true) }}>{tx('ahora')}</button>
        <button type="button" className="uifecha-listo" onClick={() => onCerrar(true)}>{tx('listo')}</button>
      </div>
    </>
  ) : (
    <>
      <div className="uifecha-cabecera">
        <button type="button" className="uifecha-nav" aria-label={tx('mes_anterior')} title={tx('mes_anterior')}
          disabled={sinAnterior} onClick={() => { setMoverFoco(false); setFoco(moverFecha(foco, 'mes', -1)) }}>
          <ChevronLeft size={16} aria-hidden />
        </button>
        <select className="uifecha-select" aria-label={tx('mes')} value={foco.m}
          onChange={e => { setMoverFoco(false); setFoco({ ...foco, m: +e.target.value, d: Math.min(foco.d, new Date(Date.UTC(foco.y, +e.target.value, 0)).getUTCDate()) }) }}>
          {meses.map((n, i) => <option key={n} value={i + 1}>{n}</option>)}
        </select>
        <select className="uifecha-select" aria-label={tx('anio')} value={foco.y}
          onChange={e => { setMoverFoco(false); setFoco(moverFecha(foco, 'anio', +e.target.value - foco.y)) }}>
          {anios.map(a => <option key={a} value={a}>{a}</option>)}
        </select>
        <button type="button" className="uifecha-nav" aria-label={tx('mes_siguiente')} title={tx('mes_siguiente')}
          disabled={sinSiguiente} onClick={() => { setMoverFoco(false); setFoco(moverFecha(foco, 'mes', 1)) }}>
          <ChevronRight size={16} aria-hidden />
        </button>
      </div>
      <span id={idTitulo} className="uifecha-oculto" aria-live="polite">{etiquetaMes}</span>
      <table ref={rejilla} role="grid" aria-labelledby={idTitulo} className="uifecha-rejilla" onKeyDown={teclaDia}>
        <thead>
          <tr>
            {dias.map((d, i) => <th key={d + i} scope="col" abbr={diasLargos[i]}>{d}</th>)}
          </tr>
        </thead>
        <tbody>
          {semanas.map((s, i) => (
            <tr key={i}>
              {s.map(c => {
                const p: Pared = { ...c, h: 0, mi: 0 }
                const enfocado = c.y === foco.y && c.m === foco.m && c.d === foco.d
                const elegido = !!actual && c.y === actual.y && c.m === actual.m && c.d === actual.d
                const esHoy = c.y === ahora.y && c.m === ahora.m && c.d === ahora.d
                const fuera = (!!pMin && comparar(p, pMin, 'fecha') < 0) || (!!pMax && comparar(p, pMax, 'fecha') > 0)
                const clases = ['uifecha-dia',
                  c.delMes ? '' : 'uifecha-dia--fuera',
                  elegido ? 'uifecha-dia--elegido' : '',
                  esHoy ? 'uifecha-dia--hoy' : '',
                  enRango(p) ? 'uifecha-dia--rango' : ''].filter(Boolean).join(' ')
                return (
                  <td key={`${c.y}-${c.m}-${c.d}`} role="gridcell" aria-selected={elegido}>
                    <button
                      type="button"
                      className={clases}
                      tabIndex={enfocado ? 0 : -1}
                      aria-label={etiquetaDeDia(c, lang)}
                      aria-current={esHoy ? 'date' : undefined}
                      aria-disabled={fuera || undefined}
                      onClick={() => { if (fuera) return; setFoco(p); onElegir(conHora(p), modo === 'fecha') }}
                    >
                      {c.d}
                    </button>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {modo === 'fechaHora' && selectorDeHora}
      <div className="uifecha-pie">
        <button type="button" className="uifecha-enlace"
          disabled={!!fueraDeLimites(modo === 'fechaHora' ? ahora : { ...ahora, h: 0, mi: 0 })}
          onClick={() => { const hoy = modo === 'fechaHora' ? { ...ahora } : { ...ahora, h: 0, mi: 0 }; setHora({ h: hoy.h, mi: hoy.mi }); setFoco(hoy); onElegir(hoy, modo === 'fecha') }}>
          {modo === 'fechaHora' ? tx('ahora') : tx('hoy')}
        </button>
        {modo === 'fechaHora' && (
          <button type="button" className="uifecha-listo" onClick={() => onCerrar(true)}>{tx('listo')}</button>
        )}
      </div>
    </>
  )

  return createPortal(
    <div
      ref={panel}
      id={id}
      role="dialog"
      aria-modal="false"
      aria-label={modo === 'hora' ? tx('elegir_hora') : tx('elegir_fecha')}
      className={`uifecha-panel${pos.arriba ? ' uifecha-panel--arriba' : ''}`}
      style={{ '--uifecha-top': `${pos.top}px`, '--uifecha-left': `${pos.left}px` } as CSSProperties}
      onKeyDown={teclaPanel}
      onBlur={e => {
        // Salir del panel con el tabulador lo cierra (no atrapa el foco: no es modal).
        const destino = e.relatedTarget as Node | null
        if (destino && !panel.current?.contains(destino) && !ancla.current?.contains(destino)) onCerrar(false)
      }}
    >
      {contenido}
    </div>,
    document.body,
  )
}

// ── Rango ─────────────────────────────────────────────────────────────────────
export interface CampoRangoDeFechasProps {
  desde?: string | null
  hasta?: string | null
  onChange?: (r: { desde: string; hasta: string }) => void
  modo?: Exclude<ModoFecha, 'hora'>
  min?: string
  max?: string
  zona?: string
  /** Etiquetas visibles; por defecto «Desde»/«Hasta» del kit. */
  etiquetaDesde?: string
  etiquetaHasta?: string
  disabled?: boolean
  className?: string
  id?: string
  idioma?: string
  textos?: TextosDeFecha
}

/** Dos campos enlazados: «hasta» no puede ser anterior a «desde» (y al revés). */
export function CampoRangoDeFechas({
  desde, hasta, onChange, modo = 'fecha', min, max, zona, etiquetaDesde, etiquetaHasta, disabled, className, id, idioma, textos,
}: CampoRangoDeFechasProps) {
  const tx = useTextosDeFecha(textos)
  const generado = useId()
  const base = id || `rango-${generado}`
  const rango = { desde, hasta }
  return (
    <div className={`uifecha-rangos${className ? ` ${className}` : ''}`} role="group" aria-label={tx('rango')}>
      <div className="uifecha-rango-campo">
        <label htmlFor={`${base}-desde`} className="uifecha-etiqueta">{etiquetaDesde ?? tx('desde')}</label>
        <CampoFecha id={`${base}-desde`} modo={modo} zona={zona} value={desde ?? ''} min={min} max={hasta || max}
          rango={rango} disabled={disabled} idioma={idioma} textos={textos} onChange={v => onChange?.({ desde: v, hasta: hasta ?? '' })} />
      </div>
      <div className="uifecha-rango-campo">
        <label htmlFor={`${base}-hasta`} className="uifecha-etiqueta">{etiquetaHasta ?? tx('hasta')}</label>
        <CampoFecha id={`${base}-hasta`} modo={modo} zona={zona} value={hasta ?? ''} min={desde || min} max={max}
          rango={rango} disabled={disabled} idioma={idioma} textos={textos} onChange={v => onChange?.({ desde: desde ?? '', hasta: v })} />
      </div>
    </div>
  )
}

export default CampoFecha

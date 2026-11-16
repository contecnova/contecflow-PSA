import { useEffect, useId, useMemo, useState } from 'react'
import { CalendarRange, Info } from 'lucide-react'
import { Button, Select } from './index'
import { CampoRangoDeFechas } from './SelectorDeFecha'
import { useTextoUi } from './useTextoUi'
import {
  GRANULARIDADES, LIMITES_POR_DEFECTO, PRESETS, aInputFecha, aInputFechaHora, deInput, isoConDesfase, puntos,
  rangoDe, resolverGranularidad, validarPeriodo, zonaDelUsuario,
  type ClavePreset, type ErrorDeValidacion, type Granularidad, type GranularidadPedida, type LimitesPeriodo,
  type ValorPeriodo,
} from '../../utils/periodo'
import './SelectorDePeriodo.css'

/**
 * SelectorDePeriodo — el periodo de un informe (periodo libre, 16-11-2026).
 *
 *   const periodo = usePeriodo({ defecto: '30d', granularidades: SIN_HORA })
 *   <SelectorDePeriodo {...periodo.selector} />
 *
 * Accesos rápidos (hoy, 24 h, 7/30/90 días, este mes, trimestre, año),
 * «Personalizado» con inicio y fin (fecha y hora si el dato tiene hora; si no,
 * solo fecha, fin incluido) en la zona del usuario, agrupación
 * (auto/hora/día/semana/mes) con las no admitidas desactivadas y explicadas, y
 * «comparar con el periodo anterior» donde el informe lo soporta. Las fechas
 * usan el selector propio del kit (`CampoRangoDeFechas`), el mismo de todos
 * los formularios. Valida con las mismas reglas y límites que la API.
 */
export interface SelectorDePeriodoProps {
  valor: ValorPeriodo
  onChange: (v: ValorPeriodo) => void
  /** Granularidades que admite el dato del informe. */
  granularidades?: Granularidad[]
  /** Muestra «comparar con el periodo anterior». */
  comparable?: boolean
  /** Límites de la API (`usePeriodo` los trae de /periodo/limites). */
  limites?: LimitesPeriodo
  /** Oculta la agrupación (informes sin serie temporal). */
  sinGranularidad?: boolean
  /** Accesos rápidos que se ofrecen (por defecto todos). */
  presets?: Exclude<ClavePreset, 'custom'>[]
  className?: string
}

const CLAVE_PRESET: Record<Exclude<ClavePreset, 'custom'>, string> = {
  hoy: 'periodo.hoy', '24h': 'periodo.p24h', '7d': 'periodo.p7d', '30d': 'periodo.p30d', '90d': 'periodo.p90d',
  mes: 'periodo.mes', trimestre: 'periodo.trimestre', anio: 'periodo.anio',
  prox7d: 'periodo.prox7d', prox30d: 'periodo.prox30d', prox90d: 'periodo.prox90d', prox180d: 'periodo.prox180d', prox365d: 'periodo.prox365d',
}

function interpolar(texto: string, params: Record<string, string | number>): string {
  return texto.replace(/\{(\w+)\}/g, (_, k) => (k in params ? String(params[k]) : `{${k}}`))
}

export default function SelectorDePeriodo({
  valor, onChange, granularidades = GRANULARIDADES, comparable = false, limites = LIMITES_POR_DEFECTO,
  sinGranularidad = false, presets = PRESETS, className,
}: SelectorDePeriodoProps) {
  const t = useTextoUi()
  const id = useId()
  const admitidas = useMemo(() => GRANULARIDADES.filter(g => granularidades.includes(g)), [granularidades])
  const conHora = admitidas.includes('hour')
  const zona = zonaDelUsuario()

  // «Personalizado» se edita aquí y se aplica con el botón (no a cada tecla).
  const [editando, setEditando] = useState(valor.preset === 'custom')
  const borradorDe = (v: ValorPeriodo) => {
    const { desde, hasta } = rangoDe(v)
    return conHora
      ? { desde: aInputFechaHora(desde), hasta: aInputFechaHora(hasta) }
      : { desde: aInputFecha(desde), hasta: aInputFecha(new Date(hasta.getTime() - 1)) }
  }
  const [borrador, setBorrador] = useState(() => borradorDe(valor))
  const [error, setError] = useState<ErrorDeValidacion | null>(null)

  useEffect(() => {
    setEditando(valor.preset === 'custom')
    if (valor.preset === 'custom') setBorrador(borradorDe(valor))
    setError(null)
  }, [valor.preset, valor.desde, valor.hasta, conHora]) // eslint-disable-line react-hooks/exhaustive-deps

  const { desde: rDesde, hasta: rHasta } = rangoDe(valor)
  const efectiva = resolverGranularidad(rDesde, rHasta, valor.granularidad, admitidas, limites)

  const mensaje = (e: ErrorDeValidacion) => interpolar(t(`periodo_err.${e.codigo}`), e as unknown as Record<string, string | number>)

  const emitir = (v: ValorPeriodo) => {
    const e = validarPeriodo(v, admitidas, limites)
    setError(e)
    if (!e) onChange(v)
  }

  const alElegirPreset = (p: string) => {
    if (p === 'custom') {
      setBorrador(borradorDe(valor))
      setEditando(true)
      return
    }
    setEditando(false)
    emitir({ ...valor, preset: p as ClavePreset, desde: undefined, hasta: undefined })
  }

  const aplicar = () => {
    const d = deInput(borrador.desde)
    let h = deInput(borrador.hasta)
    if (!d || !h) { setError({ codigo: 'fecha_invalida' }); return }
    if (!conHora) h = new Date(h.getFullYear(), h.getMonth(), h.getDate() + 1) // fin incluido
    emitir({ ...valor, preset: 'custom', desde: isoConDesfase(d), hasta: isoConDesfase(h) })
  }

  const nombreG = (g: Granularidad) => t(`periodo.g_${g}`)
  const opcionesG = [
    { value: 'auto', label: interpolar(t('periodo.g_auto_es'), { g: nombreG(efectiva) }) },
    ...GRANULARIDADES.map(g => {
      const admitida = admitidas.includes(g)
      const excede = admitida && puntos(rDesde, rHasta, g) > (limites.max_puntos[g] ?? Infinity)
      const motivo = !admitida ? t('periodo.no_disponible') : excede ? t('periodo.demasiados_puntos_corto') : ''
      return { value: g, label: motivo ? `${nombreG(g)} — ${motivo}` : nombreG(g), disabled: !admitida || excede }
    }),
  ]
  const explicacion = sinGranularidad ? null
    : admitidas.length === 1 && admitidas[0] === 'month' ? t('periodo.solo_mes')
      : !conHora ? t('periodo.hora_no_disponible') : null
  const idExplicacion = `${id}-explica`
  const idError = `${id}-error`

  const opcionesPreset = [
    ...presets.map(p => ({ value: p, label: t(CLAVE_PRESET[p]) })),
    { value: 'custom', label: t('periodo.custom') },
  ]

  return (
    <div className={`uiper${className ? ` ${className}` : ''}`} role="group" aria-label={t('periodo.titulo')}
      title={interpolar(t('periodo.zona'), { zona })}>
      <div className="uiper-fila">
        <CalendarRange size={16} aria-hidden className="uiper-icono" />
        <Select
          className="uiper-preset"
          aria-label={t('periodo.periodo')}
          value={editando ? 'custom' : valor.preset}
          onChange={e => alElegirPreset(e.target.value)}
          options={opcionesPreset}
          placeholder={false}
        />
        {!sinGranularidad && (
          <Select
            className="uiper-gran"
            aria-label={t('periodo.granularidad')}
            value={valor.granularidad}
            onChange={e => emitir({ ...valor, granularidad: e.target.value as GranularidadPedida })}
            options={opcionesG}
            placeholder={false}
          />
        )}
        {comparable && (
          <label className="uiper-comparar">
            <input type="checkbox" checked={valor.comparar} onChange={e => emitir({ ...valor, comparar: e.target.checked })} />
            <span>{t('periodo.comparar')}</span>
          </label>
        )}
      </div>
      {editando && (
        <div className="uiper-fila uiper-custom">
          <CampoRangoDeFechas
            className="uiper-rango"
            modo={conHora ? 'fechaHora' : 'fecha'}
            desde={borrador.desde}
            hasta={borrador.hasta}
            etiquetaDesde={t('periodo.desde')}
            etiquetaHasta={conHora ? t('periodo.hasta') : t('periodo.hasta_incluido')}
            onChange={r => { setBorrador(r); setError(null) }}
          />
          <Button size="md" variant="primary" onClick={aplicar} disabled={!borrador.desde || !borrador.hasta}>
            {t('periodo.aplicar')}
          </Button>
        </div>
      )}
      {explicacion && (
        <p id={idExplicacion} className="uiper-explica"><Info size={12} aria-hidden /> {explicacion}</p>
      )}
      {error && <p id={idError} role="alert" className="u-field-error uiper-error">{mensaje(error)}</p>}
    </div>
  )
}

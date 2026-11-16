/**
 * usePeriodo — el periodo de un informe, leído de y escrito en la URL
 * (periodo libre, 16-11-2026).
 *
 *   const periodo = usePeriodo({ defecto: '30d', granularidades: SIN_HORA })
 *   <SelectorDePeriodo {...periodo.selector} />
 *   useQuery({ queryKey: [RUTA, periodo.params], queryFn: () => api.get(RUTA, { params: periodo.params }) })
 *
 * La query string (`periodo`, `desde`, `hasta`, `granularidad`, `comparar`, con
 * `prefijo` si hay más de un selector en la pantalla) es la fuente de verdad:
 * el enlace se comparte o se guarda con el periodo puesto. Se escribe con
 * `replace` para no llenar el historial.
 */
import { useCallback, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { periodoApi } from '../services/api/periodo'
import {
  aUrl, deUrl, fechasDe, GRANULARIDADES, LIMITES_POR_DEFECTO, paramsDeApi, PRESETS, PRESETS_FUTURO, rangoDe, resolverGranularidad,
  type ClavePreset, type Granularidad, type GranularidadPedida, type LimitesPeriodo, type ParamsPeriodoApi,
  type SentidoPeriodo, type ValorPeriodo,
} from '../utils/periodo'

export interface OpcionesPeriodo {
  /** Acceso rápido inicial (por defecto `30d`). */
  defecto?: ClavePreset
  /** Granularidades que admite el dato del informe (por defecto todas). */
  granularidades?: Granularidad[]
  /** El informe sabe comparar con el periodo anterior. */
  comparable?: boolean
  /** Prefijo de los parámetros en la URL (varios selectores en una pantalla). */
  prefijo?: string
  /** Granularidad inicial (por defecto `auto`). */
  granularidadPorDefecto?: GranularidadPedida
  /** `futuro` para horizontes (próximos N días: vencimientos, renovaciones). */
  sentido?: SentidoPeriodo
}

export interface ResultadoPeriodo {
  valor: ValorPeriodo
  cambiar: (v: ValorPeriodo) => void
  /** Parámetros para la API (estables: sirven de clave de consulta). */
  params: ParamsPeriodoApi
  /** Rango efectivo ahora mismo. */
  rango: { desde: Date; hasta: Date }
  /** Días `YYYY-MM-DD` (ambos incluidos) para APIs que filtran por fecha. */
  fechas: { desde: string; hasta: string }
  /** Granularidad que aplicará la API (resuelve `auto` igual que el servidor). */
  granularidad: Granularidad
  granularidades: Granularidad[]
  limites: LimitesPeriodo
  /** Props listas para `<SelectorDePeriodo {...selector} />`. */
  selector: {
    valor: ValorPeriodo
    onChange: (v: ValorPeriodo) => void
    granularidades: Granularidad[]
    comparable: boolean
    limites: LimitesPeriodo
    presets: Exclude<ClavePreset, 'custom'>[]
  }
}

/** Límites de la API (una consulta compartida por toda la app). */
export function useLimitesDePeriodo(): LimitesPeriodo {
  const { data } = useQuery({
    queryKey: ['periodo', 'limites'],
    queryFn: periodoApi.limites,
    staleTime: 5 * 60_000,
    retry: false,
  })
  return data && data.max_puntos ? data : LIMITES_POR_DEFECTO
}

export function usePeriodo(op: OpcionesPeriodo = {}): ResultadoPeriodo {
  const { sentido = 'pasado', granularidades = GRANULARIDADES, comparable = false, prefijo = '', granularidadPorDefecto = 'auto' } = op
  const defecto: ClavePreset = op.defecto ?? (sentido === 'futuro' ? 'prox90d' : '30d')
  const presets = sentido === 'futuro' ? PRESETS_FUTURO : PRESETS
  const [sp, setSp] = useSearchParams()
  const limites = useLimitesDePeriodo()
  const claveGr = granularidades.join(',')
  const admitidas = useMemo(() => GRANULARIDADES.filter(g => claveGr.split(',').includes(g)), [claveGr])

  const porDefecto = useMemo<ValorPeriodo>(() => ({
    preset: defecto,
    granularidad: granularidadPorDefecto === 'auto' || admitidas.includes(granularidadPorDefecto) ? granularidadPorDefecto : 'auto',
    comparar: false,
  }), [defecto, granularidadPorDefecto, admitidas])

  const leido = deUrl(sp, porDefecto, prefijo)
  // Una granularidad que el informe no admite (enlace copiado de otro) cae a auto.
  const granularidadValida: GranularidadPedida = leido.granularidad === 'auto' || admitidas.includes(leido.granularidad) ? leido.granularidad : 'auto'
  const clave = `${leido.preset}|${leido.desde ?? ''}|${leido.hasta ?? ''}|${granularidadValida}|${comparable && leido.comparar ? 1 : 0}`

  const valor = useMemo<ValorPeriodo>(
    () => ({ ...leido, granularidad: granularidadValida, comparar: comparable && leido.comparar }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [clave],
  )
  // El día cuenta para los accesos de calendario («hoy», «este mes»…).
  const hoy = new Date().toDateString()
  const params = useMemo(() => paramsDeApi(valor), [valor, hoy]) // eslint-disable-line react-hooks/exhaustive-deps
  const rango = useMemo(() => rangoDe(valor), [valor, hoy]) // eslint-disable-line react-hooks/exhaustive-deps
  const fechas = useMemo(() => fechasDe(valor), [valor, hoy]) // eslint-disable-line react-hooks/exhaustive-deps
  const granularidad = resolverGranularidad(rango.desde, rango.hasta, valor.granularidad, admitidas, limites)

  const cambiar = useCallback((v: ValorPeriodo) => {
    setSp(prev => aUrl(prev, v, porDefecto, prefijo), { replace: true })
  }, [setSp, porDefecto, prefijo])

  return {
    valor, cambiar, params, rango, fechas, granularidad, granularidades: admitidas, limites,
    selector: { valor, onChange: cambiar, granularidades: admitidas, comparable, limites, presets },
  }
}

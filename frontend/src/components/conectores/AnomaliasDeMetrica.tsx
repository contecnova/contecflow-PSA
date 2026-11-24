/**
 * Anomalías de una métrica certificada de contecintelligence (23-11-2026).
 *
 * `POST /conectores/contecintelligence/metricas/anomalias`: contecintelligence
 * calcula la serie de la métrica en el periodo y marca los puntos que se apartan
 * de su propia historia (con lo esperado y la desviación). Sin historia
 * suficiente responde 400 con el motivo, y aquí se enseña tal cual.
 * Se usa en «Preguntar a la empresa» → Métricas certificadas.
 */
import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { conectoresApi, mensajeDeConector } from '../../services/api'
import type { Metrica } from '../../services/api'
import { Button, Select, TablaSimple, Input } from '../ui'
import DateInput from '../ui/DateInput'
import { useAppT } from '../../i18n/AppLangContext'
import { localeActivo } from '../../utils/helpers'
import { TOOLTIP_SUPERFICIE_2 } from '../../constants/estilosGrafico'

type Granularidad = 'hour' | 'day' | 'week' | 'month'
const GRANOS: Granularidad[] = ['day', 'week', 'month', 'hour']
const num = (v: number | null | undefined) => v == null ? '—' : v.toLocaleString(localeActivo(), { maximumFractionDigits: 2 })

export default function AnomaliasDeMetrica({ m, columnaInicial = '' }: { m: Metrica; columnaInicial?: string }) {
  const t = useAppT()
  const hoy = new Date()
  const iso = (d: Date) => d.toISOString().slice(0, 10)
  const [col, setCol] = useState(columnaInicial)
  const [inicio, setInicio] = useState(iso(new Date(hoy.getFullYear(), hoy.getMonth() - 3, hoy.getDate())))
  const [fin, setFin] = useState(iso(hoy))
  const [grano, setGrano] = useState<Granularidad>((m.grain as Granularidad) || 'day')
  const detectar = useMutation({
    mutationFn: () => conectoresApi.anomalias({ source_id: m.source_id, metric: m.name, time_column: col, start: inicio, end: fin, granularity: grano }),
  })
  const r = detectar.data
  const serie = (r?.puntos ?? []).map(p => ({ etiqueta: p.etiqueta, valor: p.valor, esperado: p.esperado }))
  const raras = (r?.puntos ?? []).filter(p => p.es_anomalia)
  return (
    <div className="pae-stack-3">
      <strong className="u-sm">{t('ci_extra.anomalias')}</strong>
      <div className="pae-sub">{t('ci_extra.anomalias_ayuda')}</div>
      <div className="u-wrap-center-8">
        <Input inputClassName="pae-campo" aria-label={t('ci.columna_fecha')} placeholder={t('ci.columna_fecha')} value={col} onChange={e => setCol(e.target.value)} />
        <DateInput aria-label={t('ci_extra.desde')} value={inicio} onChange={e => setInicio(e.target.value)} className="pae-campo" />
        <DateInput aria-label={t('ci_extra.hasta')} value={fin} onChange={e => setFin(e.target.value)} className="pae-campo" />
        <Select suelto placeholder={false} className="pae-campo" aria-label={t('ci_extra.granularidad')} value={grano} onChange={e => setGrano(e.target.value as Granularidad)}>
          {GRANOS.map(g => <option key={g} value={g}>{t(`ci_extra.grano_${g}`)}</option>)}
        </Select>
        <Button size="sm" variant="secondary" disabled={!col || !inicio || !fin} loading={detectar.isPending} onClick={() => detectar.mutate()}>{t('ci_extra.detectar')}</Button>
      </div>
      {detectar.isError && <div className="pae-text-danger-sm" role="alert">{mensajeDeConector(detectar.error, t('ci.error'))}</div>}
      {r && (
        <div className="u-stack-8">
          <div className="u-sm" role="status">
            {raras.length ? t('ci_extra.n_anomalias', { n: raras.length }) : t('ci_extra.sin_anomalias')}
            <span className="pae-sub"> · {t('ci_extra.metodo')}: {r.metodo}</span>
          </div>
          {serie.length > 1 && (
            <div aria-hidden="true">
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={serie}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="etiqueta" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip contentStyle={TOOLTIP_SUPERFICIE_2} />
                  <Line type="monotone" dataKey="valor" name={t('ci_extra.valor')} stroke="var(--accent)" dot={false} />
                  <Line type="monotone" dataKey="esperado" name={t('ci_extra.esperado')} stroke="var(--text-3)" strokeDasharray="4 4" dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
          {raras.length > 0 && (
            <TablaSimple>
              <thead><tr><th>{t('ci_extra.periodo')}</th><th>{t('ci_extra.valor')}</th><th>{t('ci_extra.esperado')}</th><th>{t('ci_extra.desviacion')}</th></tr></thead>
              <tbody>{raras.map(p => (
                <tr key={p.etiqueta}><td>{p.etiqueta}</td><td>{num(p.valor)}</td><td>{num(p.esperado)}</td><td>{num(p.desviacion)}</td></tr>
              ))}</tbody>
            </TablaSimple>
          )}
          {r.sql && <details><summary className="pae-sub">{t('ci_extra.como_se_calculo')}</summary><pre className="pae-sub">{r.sql}</pre></details>}
        </div>
      )}
    </div>
  )
}

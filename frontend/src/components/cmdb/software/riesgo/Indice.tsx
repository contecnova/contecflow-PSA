/**
 * Pestaña Riesgo → Índice (22-11-2026): cifra 0-100 con nivel, riesgo aceptado
 * aparte, objetivo de la empresa, última evaluación y «Recalcular»; desglose por
 * factor, tendencia (recharts) y comparación entre clientes, unidades
 * (clientes internos), servicios, máquinas y aplicaciones.
 *
 * Diseño: docs/CMDB_SOFTWARE_Y_VULNERABILIDADES.md §11.3 y §11.4.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Activity, RefreshCw, ShieldAlert } from 'lucide-react'
import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useAppT } from '../../../../i18n/AppLangContext'
import { useToast } from '../../../../context/ToastContext'
import { useAuth } from '../../../../context/AuthContext'
import { fmtDate, fmtDateTime } from '../../../../utils/helpers'
import { useChartTheme } from '../../../../charts/useChartTheme'
import { LEYENDA_XS, tooltipDelTemaConBorde } from '../../../../constants/estilosGrafico'
import { cmdbRiesgoApi } from '../../../../services/api/cmdbRiesgo'
import type { Ambito, TipoDeAmbito } from '../../../../services/api/cmdbRiesgo'
import { Button, EmptyState, KpiCard, Section, Segmentado, Spinner, TablaSimple } from '../../../ui'
import { useErr } from '../comun'
import { BarraPct, NivelBadge, redondeo, useEtiquetaSwr } from './comunRiesgo'

type Comparacion = 'client' | 'unit' | 'service' | 'machine' | 'application'
const COMPARACIONES: Comparacion[] = ['client', 'unit', 'service', 'machine', 'application']
const DIAS = [30, 90, 180, 365]

export default function Indice({ ambito, onElegirAmbito }: { ambito: Ambito; onElegirAmbito: (a: Ambito) => void }) {
  const t = useAppT()
  const e = useEtiquetaSwr()
  const toast = useToast()
  const qc = useQueryClient()
  const err = useErr()
  const { puede } = useAuth()
  const { tokens } = useChartTheme()
  const [dias, setDias] = useState(90)
  const [comparar, setComparar] = useState<Comparacion>('client')
  const indice = useQuery({ queryKey: ['swr', 'indice', ambito.scope_type, ambito.scope_id ?? ''], queryFn: () => cmdbRiesgoApi.indice(ambito) })
  const historico = useQuery({ queryKey: ['swr', 'historico', ambito.scope_type, ambito.scope_id ?? '', dias], queryFn: () => cmdbRiesgoApi.historico(ambito, dias) })
  const tipoComparado: Exclude<TipoDeAmbito, 'org'> = comparar === 'unit' ? 'client' : comparar
  const comparacion = useQuery({
    queryKey: ['swr', 'comparar', comparar],
    queryFn: () => cmdbRiesgoApi.comparar({ scope_type: tipoComparado, internal: comparar === 'unit' ? true : comparar === 'client' ? false : undefined, limit: 50 }),
  })
  const recalcular = useMutation({
    mutationFn: cmdbRiesgoApi.recalcular,
    onSuccess: r => { toast.success(t('swr.recalculado', { n: r.scopes, indice: Math.round(r.org_score) })); qc.invalidateQueries({ queryKey: ['swr'] }) },
    onError: err,
  })
  const x = indice.data
  const puntos = (historico.data ?? []).map(p => ({ dia: fmtDate(p.day), indice: Math.round(p.score * 10) / 10, aceptado: Math.round(p.accepted_score * 10) / 10 }))
  const filas = [...(comparacion.data ?? [])].sort((a, b) => b.score - a.score)

  return (
    <div className="u-stack-20">
      {indice.isLoading ? <Spinner /> : !x ? <EmptyState icon={<Activity size={28} />} title={t('swr.sin_indice')} /> : <>
        <div className="swr-cabecera">
          <div className="swr-cifra">
            <div className="ds-eyebrow">{x.scope_name ?? e('ambito', x.scope_type)}</div>
            <div className={`swr-cifra__valor swr-tono--${x.level}`} aria-label={t('swr.indice_aria', { n: Math.round(x.score) })}>{Math.round(x.score)}</div>
            <div className="swr-cifra__pie">
              <NivelBadge nivel={x.level} />
              {x.delta_7d != null && <span>{t(x.delta_7d > 0 ? 'swr.delta_sube' : x.delta_7d < 0 ? 'swr.delta_baja' : 'swr.delta_igual', { n: Math.abs(Math.round(x.delta_7d * 10) / 10) })}</span>}
            </div>
            <div className="swr-cifra__pie">
              <span>{t('swr.aceptado')}: <strong>{Math.round(x.accepted_score)}</strong></span>
              <span>· {t('swr.objetivo')}: <strong>{Math.round(x.target)}</strong></span>
            </div>
            <div className="swr-cifra__pie">{t('swr.evaluado')}: {x.evaluated_at ? fmtDateTime(x.evaluated_at) : t('swr.nunca_evaluado')}</div>
            {puede('software.gestionar') && (
              <div><Button size="sm" variant="secondary" icon={<RefreshCw size={14} />} loading={recalcular.isPending} onClick={() => recalcular.mutate()}>{t('swr.recalcular')}</Button></div>
            )}
          </div>
          <Section title={t('swr.factores')} subtitle={t('swr.factores_desc')}>
            <ul className="swr-factores">
              {x.factors.map(f => (
                <li key={f.key} className="swr-factor">
                  <span>{e('factor', f.key)}</span>
                  <BarraPct pct={f.score} etiqueta={t('swr.factor_aria', { factor: e('factor', f.key), n: Math.round(f.score) })} />
                  <span className="swr-factor__datos">{t('swr.factor_datos', { puntos: redondeo(f.points, 1), peso: Math.round(f.weight * 100), aporte: redondeo(f.contribution, 1) })}</span>
                </li>
              ))}
            </ul>
          </Section>
        </div>

        <div className="ds-grid-stats">
          <KpiCard label={t('swr.c_findings_live')} value={x.counts.findings_live} icon={<ShieldAlert size={14} />} danger={x.counts.findings_live > 0} sub={t('swr.c_aceptados', { n: x.counts.findings_accepted })} />
          <KpiCard label={t('swr.c_kev')} value={x.counts.kev} danger={x.counts.kev > 0} sub={t('swr.c_explotados', { n: x.counts.exploited })} />
          <KpiCard label={t('swr.c_internet')} value={x.counts.internet_assets} warning={x.counts.internet_assets > 0} />
          <KpiCard label={t('swr.c_configuracion')} value={x.counts.drift + x.counts.violations} warning={x.counts.drift + x.counts.violations > 0} sub={t('swr.c_deriva', { deriva: x.counts.drift, incumplimientos: x.counts.violations })} />
          <KpiCard label={t('swr.c_eol')} value={x.counts.eol} warning={x.counts.eol > 0} />
          <KpiCard label={t('swr.c_intentos')} value={x.counts.exploit_events} danger={x.counts.exploit_events > 0} />
          <KpiCard label={t('swr.c_controles')} value={x.counts.controls_active} accent />
        </div>
      </>}

      <Section title={t('swr.tendencia')} subtitle={t('swr.tendencia_desc')}
        actions={<Segmentado aria-label={t('swr.periodo')} valor={String(dias)} onChange={v => setDias(Number(v))}
          opciones={DIAS.map(d => ({ valor: String(d), etiqueta: t('swr.n_dias', { n: d }) }))} />}>
        {historico.isLoading ? <Spinner size={16} /> : puntos.length < 2 ? <div className="u-text3-xs">{t('swr.sin_historico')}</div> : (
          <div className="swr-grafico" role="img" aria-label={t('swr.tendencia')}>
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={puntos} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
                <CartesianGrid stroke={tokens.surface3} strokeDasharray="3 3" />
                <XAxis dataKey="dia" tick={{ fill: tokens.text3, fontSize: 11 }} minTickGap={24} />
                <YAxis domain={[0, 100]} width={36} tick={{ fill: tokens.text3, fontSize: 11 }} />
                <Tooltip contentStyle={tooltipDelTemaConBorde(tokens)} />
                <Legend wrapperStyle={LEYENDA_XS} />
                {x && <ReferenceLine y={x.target} stroke={tokens.success} strokeDasharray="6 4" label={{ value: t('swr.objetivo'), fill: tokens.text3, fontSize: 11, position: 'insideTopRight' }} />}
                <Line type="monotone" dataKey="indice" name={t('swr.indice')} stroke={tokens.danger} strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="aceptado" name={t('swr.aceptado')} stroke={tokens.accent} strokeWidth={1.5} strokeDasharray="4 3" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </Section>

      <Section title={t('swr.comparacion')} subtitle={t('swr.comparacion_desc')}
        actions={<Segmentado aria-label={t('swr.comparar_por')} valor={comparar} onChange={v => setComparar(v as Comparacion)}
          opciones={COMPARACIONES.map(c => ({ valor: c, etiqueta: t(`swr.comparar_${c}`) }))} />}>
        {comparacion.isLoading ? <Spinner size={16} /> : filas.length === 0 ? <div className="u-text3-xs">{t('swr.sin_comparacion')}</div> : (
          <TablaSimple etiqueta={t('swr.comparacion')} densidad="compacta">
            <thead><tr>
              <th>{t('swr.col_nombre')}</th><th>{t('swr.col_nivel')}</th><th>{t('swr.indice')}</th>
              <th className="sw-num">{t('swr.aceptado')}</th><th className="sw-num">{t('swr.col_hallazgos')}</th><th>{t('swr.evaluado')}</th>
            </tr></thead>
            <tbody>{filas.map(f => (
              <tr key={`${f.scope_type}-${f.scope_id}`}>
                <td><Button variant="link" className="sw-enlace" onClick={() => onElegirAmbito({ scope_type: f.scope_type, scope_id: f.scope_id })}>{f.name}</Button></td>
                <td><NivelBadge nivel={f.level} /></td>
                <td><span className="swr-barra-celda"><BarraPct pct={f.score} nivel={f.level} /><span className="sw-num">{Math.round(f.score)}</span></span></td>
                <td className="sw-num">{Math.round(f.accepted_score)}</td>
                <td className="sw-num">{f.findings_live}</td>
                <td className="u-text3-xs">{f.evaluated_at ? fmtDateTime(f.evaluated_at) : '—'}</td>
              </tr>
            ))}</tbody>
          </TablaSimple>
        )}
      </Section>
    </div>
  )
}

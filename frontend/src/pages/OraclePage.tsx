import { type CSSProperties, useState } from 'react'
import { extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { oracleApi } from '../services/api'
import type { AnalisisDelOraculo, PrediccionDelOraculo } from '../services/api/tipos-finanzas'
import { Button, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Brain } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, PieChart, Pie, Legend } from 'recharts'
import { useAppT } from '../i18n/AppLangContext'
import { alpha } from '../constants/theme'
import useMediaQuery from '../hooks/useMediaQuery'
import './OraclePage.css'
import { LEYENDA_XS, TOOLTIP_SUPERFICIE_3_SM } from '../constants/estilosGrafico'




interface SevCfg { label: string; color: string; bg: string }
interface TypeIcon { icon: string; label: string }

const card = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12 }
const SEV: Record<string, SevCfg> = {
  critical: { label: 'pagina_orcl.critico', color: 'var(--danger)', bg: 'var(--danger-bg)' },
  high:     { label: 'pagina_orcl.alto',    color: 'var(--warning)', bg: 'var(--warning-bg)' },
  medium:   { label: 'pagina_orcl.medio',   color: 'var(--accent)', bg: 'var(--accent-muted)' },
  low:      { label: 'pagina_orcl.bajo',    color: 'var(--text-2)', bg: 'color-mix(in srgb, var(--text-2) 9%, transparent)' },
}
const TYPE_ICONS: Record<string, TypeIcon> = {
  project_delay:  { icon: '📅', label: 'pagina_orcl.retraso_en_proyecto' },
  sla_breach:     { icon: '⏱', label: 'pagina_orcl.incumplimiento_sla' },
  burnout:        { icon: '🔥', label: 'pagina_orcl.riesgo_de_burnout' },
  budget_overrun: { icon: '💸', label: 'pagina_orcl.exceso_de_presupuesto' },
  anomaly:        { icon: '⚠️', label: 'pagina_orcl.anomalia_detectada' },
  resource_gap:   { icon: '👥', label: 'pagina_orcl.falta_de_recursos' },
  quality_risk:   { icon: '🎯', label: 'pagina_orcl.riesgo_de_calidad' },
}
const _PALETTE = ['var(--danger)','var(--warning)','var(--accent)','var(--text-2)','var(--success)','var(--purple)']


// ─────────────────────────────────────────────────────────────────────────────
// Las formas que esta pagina consume
//
// Auditoria 2026-09 (modo estricto): el cliente de API devuelve `any`, asi que
// nada de lo que se pinta aqui estaba comprobado. Se declara lo que **esta
// pagina lee**; los campos van opcionales porque este fichero no puede prometer
// que el backend los mande siempre.
// ─────────────────────────────────────────────────────────────────────────────

/** Una prediccion del oraculo sobre una entidad del sistema (services/api/tipos-finanzas.ts). */
type Prediccion = PrediccionDelOraculo

export default function OraclePage() {
  const isNarrow = useMediaQuery('(max-width: 900px)')
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [filter, setFilter] = useState('all')
  const [analysis, setAnalysis] = useState<AnalisisDelOraculo | null>(null)

  const { data: preds = [], isLoading } = useQuery<Prediccion[]>({
    queryKey: ['oracle-preds'],
    queryFn: () => oracleApi.predictions({ only_unacked: false }).then(r => r.data),
  })

  const { mutate: runOracle, isPending: running } = useMutation({
    mutationFn: () => oracleApi.run().then(r => r.data),
    onSuccess: data => {
      qc.invalidateQueries({ queryKey: ['oracle-preds'] })
      setAnalysis(data)
    },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: ack } = useMutation({
    mutationFn: (id: string) => oracleApi.acknowledge(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['oracle-preds'] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  })

  const filtered = filter === 'all' ? preds : preds.filter(p => p.severity === filter)
  const byType = preds.reduce<Record<string, number>>((acc, p) => {
    const tipo = p.type ?? 'desconocido'
    acc[tipo] = (acc[tipo] || 0) + 1
    return acc
  }, {})
  const bySev  = Object.entries(SEV).map(([k,v]) => ({ name: t(v.label), value: preds.filter(p=>p.severity===k).length, color: v.color })).filter(x=>x.value>0)
  const typeData = Object.entries(byType).map(([k,v]) => ({ name: TYPE_ICONS[k] ? t(TYPE_ICONS[k].label) : k, count: v }))

  return (
    <PageShell>
      <PageHeader
        icon={<Brain size={18} />}
        title={t('ai.oracle_title')}
        subtitle={t('pagina_orcl.detecta_riesgos_y_anomalias_en_tus')}
        actions={
          <div className="u-row-center-10">
            <Button onClick={() => runOracle()} disabled={running}>
              {running ? t('pagina_orcl.analizando') : t('pagina_orcl.ejecutar_analisis')}
            </Button>
          </div>
        }
      showListExport={false}
      />

      {/* Analysis result banner */}
      {analysis && (
        <div className="oracle-page-e1">
          <div className="orcl-row">
            <div className="u-min0">
              <div className="orcl-box">{t('oracle.analisis_completado')}</div>
              <div className="u-text2-sm">
                {/* Backend devuelve {alerts_generated, methodology, run_at} no {predictions_generated, projects_analyzed} */}
                {analysis.alerts_generated || 0}{' '}{t('pagina_orcl.alertas_generadas')}
                {analysis.methodology && <span> {t('oracle.metodo')} <em>{analysis.methodology}</em></span>}
              </div>
            </div>
            <button onClick={() => setAnalysis(null)} className="orcl-btn">×</button>
          </div>
          {(analysis.alerts || []).length > 0 && (
            <div className="orcl-card">
              {(analysis.alerts ?? []).slice(0, 5).map((a, i) => (
                <div key={i}>• {a.type}: {a.entity} ({Math.round((a.probability || 0) * 100)}%)</div>
              ))}
              {(analysis.alerts?.length ?? 0) > 5 && <div className="u-text3">… {(analysis.alerts?.length ?? 0) - 5} {t('oracle.mas')}</div>}
            </div>
          )}
        </div>
      )}

      {/* KPIs */}
      <div className="orcl-grid">
        {[
          { label: t('pagina_orcl.total'), value: preds.length, color: 'var(--accent)' },
          { label: t('pagina_orcl.critico'), value: preds.filter(p=>p.severity==='critical').length, color: 'var(--danger)' },
          { label: t('pagina_orcl.alto'), value: preds.filter(p=>p.severity==='high').length, color: 'var(--warning)' },
          { label: t('pagina_orcl.medio'), value: preds.filter(p=>p.severity==='medium').length, color: 'var(--accent)' },
          { label: t('pagina_orcl.reconocidas'), value: preds.filter(p=>p.is_acknowledged).length, color: 'var(--success)' },
        ].map(k => (
          <div key={k.label} className="oracle-page-e2">
            <div className="orcl-box-2 oracle-page-e3" style={{ '--oracle-page-color': k.color } as CSSProperties}>{k.value}</div>
            <div className="u-text2-xs-mt2">{k.label}</div>
          </div>
        ))}
      </div>

      {/* Charts row */}
      {preds.length > 0 && (
        <div className={`orcl-grid-2 ${isNarrow ? 'oraclepa-sx1' : 'oraclepa-sx2'}`}>
          <div className="oracle-page-e4">
            <div className="orcl-box-3">{t('oracle.predicciones_por_tipo')}</div>
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={typeData} layout="vertical" margin={{ left: 10 }}>
                <XAxis type="number" tick={{ fontSize: "var(--text-2xs)", fill: 'var(--text-2)' }} />
                <YAxis type="category" dataKey="name" tick={{ fontSize: "var(--text-xs)", fill: 'var(--text-2)' }} width={130} />
                <Tooltip contentStyle={TOOLTIP_SUPERFICIE_3_SM} />
                <Bar dataKey="count" fill="var(--accent)" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="oracle-page-e5">
            <div className="orcl-box-3">{t('oracle.por_severidad')}</div>
            <ResponsiveContainer width="100%" height={160}>
              <PieChart>
                <Pie data={bySev} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={60} label={false}>
                  {bySev.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                </Pie>
                <Tooltip contentStyle={TOOLTIP_SUPERFICIE_3_SM} />
                <Legend wrapperStyle={LEYENDA_XS} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="orcl-row-2">
        {['all', 'critical', 'high', 'medium', 'low'].map(s => (
          <button key={s} onClick={() => setFilter(s)}
            className={`orcl-btn-2 oraclepa-sx3 ${filter===s ? 'oraclepa-sx4' : 'oraclepa-sx5'} oracle-page-e6`} style={{ '--oracle-page-border': `1px solid ${filter===s ? alpha(SEV[s]?.color, '60') || 'var(--accent)' : 'var(--surface-4)'}`, '--oracle-page-background': filter===s ? (SEV[s]?.bg || 'var(--accent-muted)') : 'transparent', '--oracle-page-color': filter===s ? (SEV[s]?.color || 'var(--accent)') : 'var(--text-2)' } as CSSProperties}>
            {s === 'all' ? t('pagina_orcl.todos', { length: preds.length }) : `${SEV[s] ? t(SEV[s].label) : s} (${preds.filter(p=>p.severity===s).length})`}
          </button>
        ))}
      </div>

      {/* Predictions list */}
      {isLoading ? <Spinner /> : filtered.length === 0 ? (
        <EmptyState icon="🔮" title={t('oracle.sin_predicciones_disponibles')} description={preds.length ? t('pagina_orcl.no_hay_predicciones_con_este_filtro') : t('pagina_orcl.ejecuta_el_analisis_para_detectar_riesgos')} />
      ) : (
        <div className="u-stack-10">
          {filtered.map(p => {
            const sv = (p.severity && SEV[p.severity]) || SEV.low
            const ti = (p.type && TYPE_ICONS[p.type]) || { icon: '⚡', label: p.type }
            return (
              <div key={p.id} className={`oracle-page-e7 ${p.is_acknowledged ? 'oracle-page-m8' : 'oracle-page-m9'}`} style={{ '--oracle-page-border-left': `3px solid ${sv.color}` } as CSSProperties}>
                <div className="orcl-row-3">
                  <div className="orcl-row-4">
                    <span className="orcl-label">{ti.icon}</span>
                    <div>
                      <div className="u-md-700">{p.title}</div>
                      <div className="u-text2-xs-mt2">
                        {p.type && TYPE_ICONS[p.type] ? t(ti.label) : ti.label} · {p.entity_type} {p.entity_name ? `— ${p.entity_name}` : ''}
                      </div>
                    </div>
                  </div>
                  <div className="orcl-row-5">
                    <span className="orcl-label-2 oracle-page-e10" style={{ '--oracle-page-background': sv.bg, '--oracle-page-color': sv.color } as CSSProperties}>{t(sv.label)}</span>
                    {p.probability && (
                      <span className="u-text2-sm">{Math.round(p.probability * 100)}{t('pagina_orcl.prob')}</span>
                    )}
                    {!p.is_acknowledged && (
                      <button onClick={() => p.id && ack(p.id)}
                        className="orcl-btn-3">
                        {t('pagina_orcl.reconocer')}
                      </button>
                    )}
                  </div>
                </div>
                <div className={`orcl-box-4 ${p.recommended_action ? 'oraclepa-sx6' : 'oraclepa-sx7'}`}>
                  {p.explanation}
                </div>
                {p.recommended_action && (
                  <div className="orcl-card-2">
                    💡 <strong>{t('oracle.accion_recomendada')}</strong> {p.recommended_action}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </PageShell>
  )
}

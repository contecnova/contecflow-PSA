/**
 * OraclePage — NexusOracle: riesgos y anomalías detectados por reglas.
 *
 * 16-11-2026: título = el del menú (icono del menú); botón principal con icono
 * lucide (antes emojis); KPIs con KpiCard en .ds-grid-stats; filtros de
 * severidad con Tabs (antes botones coloreados propios); tipos con iconos
 * lucide (antes emojis); severidad con StatusBadge; vacío con EmptyState e
 * icono lucide; valores crudos del backend (rules_based, project, ticket,
 * user, tipos de alerta) traducidos.
 */
import { useState } from 'react'
import type { ReactNode } from 'react'
import { extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { oracleApi } from '../services/api'
import type { AnalisisDelOraculo, PrediccionDelOraculo } from '../services/api/tipos-finanzas'
import { Button, Card, EmptyState, IconButton, KpiCard, Section, Spinner, Tabs } from '../components/ui'
import StatusBadge from '../components/ui/StatusBadge'
import type { StatusBadgeKind } from '../components/ui/StatusBadge'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import {
  AlertOctagon, AlertTriangle, CalendarClock, CheckCircle2, Eye, Flame, Gauge, Layers, Lightbulb, ShieldCheck,
  Sparkles, Target, Timer, Users, Wallet, X, Zap,
} from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, PieChart, Pie, Legend } from 'recharts'
import { useAppT } from '../i18n/AppLangContext'
import useMediaQuery from '../hooks/useMediaQuery'
import './OraclePage.css'
import { LEYENDA_XS, TOOLTIP_SUPERFICIE_3_SM } from '../constants/estilosGrafico'

interface SevCfg { label: string; color: string; kind: StatusBadgeKind }
interface TypeIcon { icon: ReactNode; label: string }

const SEV: Record<string, SevCfg> = {
  critical: { label: 'pagina_orcl.critico', color: 'var(--danger)',  kind: 'danger' },
  high:     { label: 'pagina_orcl.alto',    color: 'var(--warning)', kind: 'warning' },
  medium:   { label: 'pagina_orcl.medio',   color: 'var(--accent)',  kind: 'accent' },
  low:      { label: 'pagina_orcl.bajo',    color: 'var(--text-3)',  kind: 'neutral' },
}
const TYPE_ICONS: Record<string, TypeIcon> = {
  project_delay:  { icon: <CalendarClock size={16} />, label: 'pagina_orcl.retraso_en_proyecto' },
  sla_breach:     { icon: <Timer size={16} />,         label: 'pagina_orcl.incumplimiento_sla' },
  burnout:        { icon: <Flame size={16} />,         label: 'pagina_orcl.riesgo_de_burnout' },
  budget_overrun: { icon: <Wallet size={16} />,        label: 'pagina_orcl.exceso_de_presupuesto' },
  anomaly:        { icon: <AlertTriangle size={16} />, label: 'pagina_orcl.anomalia_detectada' },
  resource_gap:   { icon: <Users size={16} />,         label: 'pagina_orcl.falta_de_recursos' },
  quality_risk:   { icon: <Target size={16} />,        label: 'pagina_orcl.riesgo_de_calidad' },
}
/** Tipos de entidad que manda el backend (oracle.py) → etiqueta traducida. */
const ENTIDADES: Record<string, string> = {
  project: 'pagina_orcl.entidad_proyecto',
  ticket: 'pagina_orcl.entidad_ticket',
  user: 'pagina_orcl.entidad_persona',
}
/** Métodos de análisis que manda el backend → etiqueta traducida. */
const METODOS: Record<string, string> = {
  rules_based: 'pagina_orcl.metodo_reglas',
}

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

  const etiquetaTipo = (tipo?: string | null) => (tipo && TYPE_ICONS[tipo] ? t(TYPE_ICONS[tipo].label) : (tipo ?? ''))
  const etiquetaEntidad = (e?: string | null) => (e && ENTIDADES[e] ? t(ENTIDADES[e]) : (e ?? ''))
  const cuenta = (sev: string) => preds.filter(p => p.severity === sev).length

  const filtered = filter === 'all' ? preds : preds.filter(p => p.severity === filter)
  const byType = preds.reduce<Record<string, number>>((acc, p) => {
    const tipo = p.type ?? 'desconocido'
    acc[tipo] = (acc[tipo] || 0) + 1
    return acc
  }, {})
  const bySev  = Object.entries(SEV).map(([k,v]) => ({ name: t(v.label), value: cuenta(k), color: v.color })).filter(x=>x.value>0)
  const typeData = Object.entries(byType).map(([k,v]) => ({ name: etiquetaTipo(k), count: v }))

  return (
    <PageShell>
      <PageHeader
        icon={<Eye size={18} />}
        title={t('nav.oracle')}
        subtitle={t('pagina_orcl.detecta_riesgos_y_anomalias_en_tus')}
        actions={
          <Button icon={<Sparkles size={14} />} onClick={() => runOracle()} loading={running}>
            {running ? t('pagina_orcl.analizando') : t('pagina_orcl.ejecutar_analisis')}
          </Button>
        }
        showListExport={false}
      />

      <div className="u-stack-16">
        {/* Resultado del análisis */}
        {analysis && (
          <Card>
            <div className="orcl-aviso">
              <CheckCircle2 size={18} aria-hidden className="orcl-aviso__icono" />
              <div className="u-flex1-min0">
                <div className="orcl-aviso__titulo">{t('oracle.analisis_completado')}</div>
                <div className="orcl-aviso__texto">
                  {/* Backend devuelve {alerts_generated, methodology, run_at} no {predictions_generated, projects_analyzed} */}
                  {analysis.alerts_generated || 0}{' '}{t('pagina_orcl.alertas_generadas')}
                  {analysis.methodology && <> {t('oracle.metodo')} {METODOS[analysis.methodology] ? t(METODOS[analysis.methodology]) : analysis.methodology}</>}
                </div>
                {(analysis.alerts || []).length > 0 && (
                  <ul className="orcl-aviso__lista">
                    {(analysis.alerts ?? []).slice(0, 5).map((a, i) => (
                      <li key={i}>{etiquetaTipo(a.type)}: {a.entity} ({Math.round((a.probability || 0) * 100)}%)</li>
                    ))}
                    {(analysis.alerts?.length ?? 0) > 5 && <li className="orcl-aviso__mas">… {(analysis.alerts?.length ?? 0) - 5} {t('oracle.mas')}</li>}
                  </ul>
                )}
              </div>
              <IconButton ariaLabel={t('common.close')} onClick={() => setAnalysis(null)}><X size={16} /></IconButton>
            </div>
          </Card>
        )}

        {/* KPIs */}
        <div className="ds-grid-stats">
          <KpiCard icon={<Layers size={16} />} label={t('pagina_orcl.total')} value={preds.length} />
          <KpiCard icon={<AlertOctagon size={16} />} label={t('pagina_orcl.critico')} value={cuenta('critical')} danger={cuenta('critical') > 0} />
          <KpiCard icon={<AlertTriangle size={16} />} label={t('pagina_orcl.alto')} value={cuenta('high')} warning={cuenta('high') > 0} />
          <KpiCard icon={<Gauge size={16} />} label={t('pagina_orcl.medio')} value={cuenta('medium')} />
          <KpiCard icon={<ShieldCheck size={16} />} label={t('pagina_orcl.reconocidas')} value={preds.filter(p => p.is_acknowledged).length} />
        </div>

        {/* Gráficos */}
        {preds.length > 0 && (
          <div className={`orcl-graficos${isNarrow ? ' orcl-graficos--estrecho' : ''}`}>
            <Card>
              <Section title={t('oracle.predicciones_por_tipo')}>
                <ResponsiveContainer width="100%" height={160}>
                  <BarChart data={typeData} layout="vertical" margin={{ left: 10 }}>
                    <XAxis type="number" tick={{ fontSize: 'var(--text-2xs)', fill: 'var(--text-2)' }} />
                    <YAxis type="category" dataKey="name" tick={{ fontSize: 'var(--text-xs)', fill: 'var(--text-2)' }} width={130} />
                    <Tooltip contentStyle={TOOLTIP_SUPERFICIE_3_SM} />
                    <Bar dataKey="count" fill="var(--accent)" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </Section>
            </Card>
            <Card>
              <Section title={t('oracle.por_severidad')}>
                <ResponsiveContainer width="100%" height={160}>
                  <PieChart>
                    <Pie data={bySev} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={60} label={false}>
                      {bySev.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                    </Pie>
                    <Tooltip contentStyle={TOOLTIP_SUPERFICIE_3_SM} />
                    <Legend wrapperStyle={LEYENDA_XS} />
                  </PieChart>
                </ResponsiveContainer>
              </Section>
            </Card>
          </div>
        )}

        {/* Filtro por severidad */}
        <Tabs
          ariaLabel={t('oracle.por_severidad')}
          active={filter}
          onChange={setFilter}
          items={[
            { id: 'all', label: t('pagina_orcl.todas'), count: preds.length },
            ...(['critical', 'high', 'medium', 'low'] as const).map(s => ({ id: s, label: t(SEV[s].label), count: cuenta(s) })),
          ]}
        />

        {/* Lista de predicciones */}
        {isLoading ? <Spinner /> : filtered.length === 0 ? (
          <Card>
            <EmptyState icon={<Eye size={28} />} title={t('oracle.sin_predicciones_disponibles')}
              description={preds.length ? t('pagina_orcl.no_hay_predicciones_con_este_filtro') : t('pagina_orcl.ejecuta_el_analisis_para_detectar_riesgos')}
              action={preds.length ? undefined : <Button icon={<Sparkles size={14} />} onClick={() => runOracle()} loading={running}>{t('pagina_orcl.ejecutar_analisis')}</Button>} />
          </Card>
        ) : (
          <div className="u-stack-10">
            {filtered.map(p => {
              const sv = (p.severity && SEV[p.severity]) || SEV.low
              const icono = (p.type && TYPE_ICONS[p.type]?.icon) || <Zap size={16} />
              return (
                <Card key={p.id} className={`orcl-pred${p.is_acknowledged ? ' orcl-pred--reconocida' : ''}`}>
                  <div className="orcl-pred__cab">
                    <div className="orcl-pred__titulo">
                      <span className="orcl-pred__icono" aria-hidden>{icono}</span>
                      <div className="u-min0">
                        <div className="orcl-pred__nombre">{p.title}</div>
                        <div className="orcl-pred__meta">
                          {etiquetaTipo(p.type)}
                          {p.entity_type && <> · {etiquetaEntidad(p.entity_type)}</>}
                          {p.entity_name && <> — {p.entity_name}</>}
                        </div>
                      </div>
                    </div>
                    <div className="orcl-pred__acciones">
                      <StatusBadge kind={sv.kind} caps={false}>{t(sv.label)}</StatusBadge>
                      {p.probability ? (
                        <span className="orcl-pred__prob">{Math.round(p.probability * 100)}{t('pagina_orcl.prob')}</span>
                      ) : null}
                      {!p.is_acknowledged && (
                        <Button size="sm" variant="secondary" icon={<CheckCircle2 size={13} />} onClick={() => p.id && ack(p.id)}>
                          {t('pagina_orcl.reconocer')}
                        </Button>
                      )}
                    </div>
                  </div>
                  {p.explanation && <p className="orcl-pred__texto">{p.explanation}</p>}
                  {p.recommended_action && (
                    <div className="orcl-pred__accion">
                      <Lightbulb size={14} aria-hidden />
                      <span><strong>{t('oracle.accion_recomendada')}</strong> {p.recommended_action}</span>
                    </div>
                  )}
                </Card>
              )
            })}
          </div>
        )}
      </div>
    </PageShell>
  )
}

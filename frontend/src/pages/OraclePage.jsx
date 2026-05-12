import { useState } from 'react'
import { extractErr } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { oracleApi, aiProvidersApi } from '../services/api'
import { Button, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Brain } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, PieChart, Pie, Legend } from 'recharts'
import { useAppT } from '../i18n/AppLangContext'

const card = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12 }
const SEV = {
  critical: { label: 'Crítico', color: 'var(--danger)', bg: 'var(--danger-bg)' },
  high:     { label: 'Alto',    color: 'var(--warning)', bg: 'var(--warning-bg)' },
  medium:   { label: 'Medio',   color: 'var(--accent)', bg: 'var(--accent-muted)' },
  low:      { label: 'Bajo',    color: 'var(--text-2)', bg: 'rgba(120,138,170,0.09)' },
}
const TYPE_ICONS = {
  project_delay:  { icon: '📅', label: 'Retraso en proyecto' },
  sla_breach:     { icon: '⏱', label: 'Incumplimiento SLA' },
  burnout:        { icon: '🔥', label: 'Riesgo de burnout' },
  budget_overrun: { icon: '💸', label: 'Exceso de presupuesto' },
  anomaly:        { icon: '⚠️', label: 'Anomalía detectada' },
  resource_gap:   { icon: '👥', label: 'Falta de recursos' },
  quality_risk:   { icon: '🎯', label: 'Riesgo de calidad' },
}
const _PALETTE = ['var(--danger)','var(--warning)','var(--accent)','var(--text-2)','var(--success)','var(--purple)']

export default function OraclePage() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [filter, setFilter] = useState('all')
  const [analysis, setAnalysis] = useState(null)

  const { data: preds = [], isLoading } = useQuery({
    queryKey: ['oracle-preds'],
    queryFn: () => oracleApi.predictions({ only_unacked: false }).then(r => r.data),
  })
  const { data: providers = [] } = useQuery({
    queryKey: ['ai-providers'],
    queryFn: () => aiProvidersApi.list().then(r => r.data),
  })
  const defaultProvider = providers.find(p => p.is_default) || providers[0]

  const { mutate: runOracle, isPending: running } = useMutation({
    mutationFn: () => oracleApi.run().then(r => r.data),
    onSuccess: data => {
      qc.invalidateQueries(['oracle-preds'])
      setAnalysis(data)
    },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: ack } = useMutation({
    mutationFn: id => oracleApi.acknowledge(id),
    onSuccess: () => qc.invalidateQueries(['oracle-preds']),
    onError: e => toast.error(extractErr(e, 'Error'))
  })

  const filtered = filter === 'all' ? preds : preds.filter(p => p.severity === filter)
  const byType = preds.reduce((acc, p) => { acc[p.type] = (acc[p.type]||0)+1; return acc }, {})
  const bySev  = Object.entries(SEV).map(([k,v]) => ({ name: v.label, value: preds.filter(p=>p.severity===k).length, color: v.color })).filter(x=>x.value>0)
  const typeData = Object.entries(byType).map(([k,v]) => ({ name: TYPE_ICONS[k]?.label || k, count: v }))

  return (
    <PageShell>
      <PageHeader
        icon={<Brain size={18} />}
        title={t('ai.oracle_title')}
        subtitle="Detecta riesgos y anomalías en tus proyectos con reglas de negocio multi-factor (retraso · SLA · burnout · presupuesto)"
        actions={
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            {defaultProvider && (
              <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
                {defaultProvider.name}
              </span>
            )}
            <Button onClick={() => runOracle()} disabled={running}>
              {running ? '🔄 Analizando...' : '🔮 Ejecutar análisis'}
            </Button>
          </div>
        }
      showListExport={false}
      />

      {/* Analysis result banner */}
      {analysis && (
        <div style={{ ...card, padding: '16px 20px', marginBottom: 20, borderColor: 'rgba(52,211,153,0.25)', background: 'var(--success-bg)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontSize: "var(--text-md)", fontWeight: 700, color: 'var(--success)', marginBottom: 4 }}>✅ Análisis completado</div>
              <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
                {/* Backend devuelve {alerts_generated, methodology, run_at} no {predictions_generated, projects_analyzed} */}
                {analysis.alerts_generated || 0} alertas generadas
                {analysis.methodology && <span> · Método: <em>{analysis.methodology}</em></span>}
              </div>
            </div>
            <button onClick={() => setAnalysis(null)} style={{ background: 'none', border: 'none', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-lg-em)" }}>×</button>
          </div>
          {(analysis.alerts || []).length > 0 && (
            <div style={{ marginTop: 10, fontSize: "var(--text-base)", color: 'var(--text-2)', lineHeight: 1.6, padding: '10px 12px', background: 'var(--surface-1)', borderRadius: 8 }}>
              {analysis.alerts.slice(0, 5).map((a, i) => (
                <div key={i}>• {a.type}: {a.entity} ({Math.round((a.probability || 0) * 100)}%)</div>
              ))}
              {analysis.alerts.length > 5 && <div style={{ color: 'var(--text-3)' }}>… {analysis.alerts.length - 5} más</div>}
            </div>
          )}
        </div>
      )}

      {/* KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12, marginBottom: 24 }}>
        {[
          { label: 'Total', value: preds.length, color: 'var(--accent)' },
          { label: 'Crítico', value: preds.filter(p=>p.severity==='critical').length, color: 'var(--danger)' },
          { label: 'Alto', value: preds.filter(p=>p.severity==='high').length, color: 'var(--warning)' },
          { label: 'Medio', value: preds.filter(p=>p.severity==='medium').length, color: 'var(--accent)' },
          { label: 'Reconocidas', value: preds.filter(p=>p.is_acknowledged).length, color: 'var(--success)' },
        ].map(k => (
          <div key={k.label} style={{ ...card, padding: '14px 18px' }}>
            <div style={{ fontSize: "var(--text-2xl-em)", fontWeight: 800, color: k.color }}>{k.value}</div>
            <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginTop: 2 }}>{k.label}</div>
          </div>
        ))}
      </div>

      {/* Charts row */}
      {preds.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 280px', gap: 16, marginBottom: 24 }}>
          <div style={{ ...card, padding: '16px 20px' }}>
            <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 14 }}>Predicciones por tipo</div>
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={typeData} layout="vertical" margin={{ left: 10 }}>
                <XAxis type="number" tick={{ fontSize: "var(--text-2xs)", fill: 'var(--text-2)' }} />
                <YAxis type="category" dataKey="name" tick={{ fontSize: "var(--text-xs)", fill: 'var(--text-2)' }} width={130} />
                <Tooltip contentStyle={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', fontSize: "var(--text-sm)" }} />
                <Bar dataKey="count" fill="#4f8ef7" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div style={{ ...card, padding: '16px 20px' }}>
            <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 14 }}>Por severidad</div>
            <ResponsiveContainer width="100%" height={160}>
              <PieChart>
                <Pie data={bySev} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={60} label={false}>
                  {bySev.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                </Pie>
                <Tooltip contentStyle={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', fontSize: "var(--text-sm)" }} />
                <Legend wrapperStyle={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Filters */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 20 , borderBottom: '1px solid var(--surface-4)', paddingBottom: 12 }}>
        {['all', 'critical', 'high', 'medium', 'low'].map(s => (
          <button key={s} onClick={() => setFilter(s)}
            style={{ padding: '5px 14px', borderRadius: 6, border: `1px solid ${filter===s ? SEV[s]?.color+'60' || 'var(--accent)' : 'var(--surface-4)'}`, background: filter===s ? (SEV[s]?.bg || 'var(--accent-muted)') : 'transparent', color: filter===s ? (SEV[s]?.color || 'var(--accent)') : 'var(--text-2)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit', fontWeight: filter===s ? 700 : 400, textTransform: 'capitalize' }}>
            {s === 'all' ? `Todos (${preds.length})` : `${SEV[s]?.label} (${preds.filter(p=>p.severity===s).length})`}
          </button>
        ))}
      </div>

      {/* Predictions list */}
      {isLoading ? <Spinner /> : filtered.length === 0 ? (
        <EmptyState icon="🔮" title="Sin predicciones disponibles" description={preds.length ? "No hay predicciones con este filtro" : "Ejecuta el análisis para detectar riesgos con IA"} />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {filtered.map(p => {
            const sv = SEV[p.severity] || SEV.low
            const ti = TYPE_ICONS[p.type] || { icon: '⚡', label: p.type }
            return (
              <div key={p.id} style={{ ...card, padding: '16px 20px', borderLeft: `3px solid ${sv.color}`, opacity: p.is_acknowledged ? 0.6 : 1 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
                  <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                    <span style={{ fontSize: "var(--text-xl-em)" }}>{ti.icon}</span>
                    <div>
                      <div style={{ fontSize: "var(--text-md)", fontWeight: 700 }}>{p.title}</div>
                      <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginTop: 2 }}>
                        {ti.label} · {p.entity_type} {p.entity_name ? `— ${p.entity_name}` : ''}
                      </div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexShrink: 0 }}>
                    <span style={{ fontSize: "var(--text-xs)", padding: '3px 10px', borderRadius: 20, background: sv.bg, color: sv.color, fontWeight: 700 }}>{sv.label}</span>
                    {p.probability && (
                      <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{Math.round(p.probability * 100)}% prob.</span>
                    )}
                    {!p.is_acknowledged && (
                      <button onClick={() => ack(p.id)}
                        style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '3px 10px', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit', color: 'var(--text-2)' }}>
                        ✓ Reconocer
                      </button>
                    )}
                  </div>
                </div>
                <div style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', lineHeight: 1.6, marginBottom: p.recommended_action ? 10 : 0 }}>
                  {p.explanation}
                </div>
                {p.recommended_action && (
                  <div style={{ padding: '8px 12px', background: 'var(--accent-muted)', border: '1px solid var(--accent-border-soft)', borderRadius: 8, fontSize: "var(--text-sm)", color: 'var(--accent)', lineHeight: 1.5 }}>
                    💡 <strong>Acción recomendada:</strong> {p.recommended_action}
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

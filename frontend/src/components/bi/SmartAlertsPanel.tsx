/**
 * SmartAlertsPanel — Reglas + historial de alertas BI inteligentes
 * (forecasting, anomaly trends, threshold). Reutilizable.
 */
import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { biSmartAlertsApi } from '../../services/api'
import { COLOR, alpha } from '../../constants/theme'
import { useAppLang } from '../../i18n/AppLangContext'

// TODO type: biSmartAlertsApi payloads — needs shared types
interface AlertRule {
  id: string | number
  name: string
  metric_key: string
  condition: string
  severity: string
  [k: string]: unknown
}

interface CorrelatedMetric {
  metric_key?: string
  [k: string]: unknown
}

interface AlertHistoryEntry {
  id: string | number
  rule_id?: string | number
  fired_at?: string
  severity?: string
  message?: string
  acknowledged?: boolean
  rule_name?: string
  metric_key?: string
  condition?: string
  triggered_at?: string
  correlated?: CorrelatedMetric[]
  [k: string]: unknown
}

interface SupportedMetric {
  key: string
  label: string
}

interface SupportedMetrics {
  metrics?: SupportedMetric[]
  conditions?: string[]
}

const S: Record<string, React.CSSProperties> = {
  card:        { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 14, overflow: 'hidden' },
  cardPad:     { padding: '20px 24px' },
  input:       { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', color: 'var(--text-1)', borderRadius: 8, padding: '9px 13px', fontSize: 'var(--text-base)', fontFamily: 'inherit', outline: 'none', width: '100%' },
  btnPrimary:  { padding: '7px 16px', borderRadius: 8, background: COLOR.accent, color: '#fff', border: 'none', cursor: 'pointer', fontSize: 'var(--text-sm)', fontWeight: 600, fontFamily: 'inherit' },
  btnSecondary:{ padding: '7px 16px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-2)', cursor: 'pointer', fontSize: 'var(--text-sm)', fontFamily: 'inherit' },
}

export default function SmartAlertsPanel() {
  const { t } = useAppLang()
  const [tick, setTick] = useState<number>(0)
  const [name, setName] = useState<string>('')
  const [metric, setMetric] = useState<string>('revenue')
  const [condition, setCondition] = useState<string>('trend_down')
  const [severity, setSeverity] = useState<string>('warning')
  const isMobile = typeof window !== 'undefined' && window.matchMedia('(max-width: 900px)').matches

  const { data: rules } = useQuery<{ items?: AlertRule[] }>({
    queryKey: ['bi-alert-rules', tick],
    queryFn: () => biSmartAlertsApi.listRules().then(r => r.data).catch(() => ({ items: [] })),
    staleTime: 30_000,
  })
  const { data: history } = useQuery<{ items?: AlertHistoryEntry[] }>({
    queryKey: ['bi-alert-history', tick],
    queryFn: () => biSmartAlertsApi.getHistory(50).then(r => r.data).catch(() => ({ items: [] })),
    staleTime: 30_000,
  })
  const { data: supported } = useQuery<SupportedMetrics>({
    queryKey: ['bi-alert-supported-metrics'],
    queryFn: () => biSmartAlertsApi.supportedMetrics().then(r => r.data).catch(() => ({ metrics: [], conditions: [] })),
    staleTime: 600_000,
  })

  async function evaluateNow() {
    try { await biSmartAlertsApi.evaluate(); setTick(x => x + 1) } catch (_) { /* ignore */ }
  }
  async function createRule() {
    if (!name.trim()) return
    try {
      await biSmartAlertsApi.createRule({ name, metric_key: metric, condition, severity })
      setName('')
      setTick(x => x + 1)
    } catch (_) { /* ignore */ }
  }
  async function deleteRule(id: AlertRule['id']) {
    try { await biSmartAlertsApi.deleteRule(id); setTick(x => x + 1) } catch (_) { /* ignore */ }
  }
  async function seedDefaults() {
    try { await biSmartAlertsApi.seedDefaults(); setTick(x => x + 1) } catch (_) { /* ignore */ }
  }
  async function ack(id: AlertHistoryEntry['id']) {
    try { await biSmartAlertsApi.acknowledge(id); setTick(x => x + 1) } catch (_) { /* ignore */ }
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 14 }}>

      {/* Reglas */}
      <div style={S.card}>
        <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>{t('smartalerts.reglas_de_alerta')}</span>
          <button onClick={evaluateNow} style={{ ...S.btnPrimary, padding: '5px 14px', fontSize: 'var(--text-xs)' }}>Evaluar ahora</button>
        </div>
        <div style={S.cardPad}>
          <div style={{ display: 'flex', gap: 8, marginBottom: 14, flexWrap: 'wrap' }}>
            <input value={name} onChange={e => setName(e.target.value)} placeholder={t('smartalerts.nombre_de_la_regla')}
              style={{ ...S.input, flex: 1, minWidth: 120 }} />
            <select value={metric} onChange={e => setMetric(e.target.value)} style={{ ...S.input, width: 'auto' }}>
              {(supported?.metrics || [{ key: 'revenue', label: 'Revenue' }]).map(m => <option key={m.key} value={m.key}>{m.label}</option>)}
            </select>
            <select value={condition} onChange={e => setCondition(e.target.value)} style={{ ...S.input, width: 'auto' }}>
              {(supported?.conditions || ['trend_down', 'trend_up', 'anomaly', 'threshold_above', 'threshold_below']).map(c => <option key={c} value={c}>{c.replace(/_/g, ' ')}</option>)}
            </select>
            <select value={severity} onChange={e => setSeverity(e.target.value)} style={{ ...S.input, width: 'auto' }}>
              {['info', 'warning', 'critical'].map(s => <option key={s} value={s}>{s}</option>)}
            </select>
            <button onClick={createRule} style={S.btnPrimary}>+ Crear</button>
          </div>
          {(rules?.items || []).map(rule => (
            <div key={rule.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', borderBottom: '1px solid var(--surface-4)' }}>
              <div style={{ width: 8, height: 8, borderRadius: '50%', background: rule.severity === 'critical' ? COLOR.danger : rule.severity === 'warning' ? COLOR.warning : COLOR.success, flexShrink: 0 }} />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-1)' }}>{rule.name}</div>
                <div style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-3)' }}>{rule.metric_key} · {String(rule.condition || '').replace(/_/g, ' ')}</div>
              </div>
              <span style={{ fontSize: 'var(--text-2xs)', padding: '2px 8px', borderRadius: 10, background: rule.enabled ? alpha(COLOR.success, '18') : 'var(--surface-4)', color: rule.enabled ? COLOR.success : 'var(--text-3)', fontWeight: 700 }}>
                {rule.enabled ? 'activa' : 'pausada'}
              </span>
              <button onClick={() => deleteRule(rule.id)}
                style={{ ...S.btnSecondary, padding: '3px 10px', fontSize: 'var(--text-xs)' }}>✕</button>
            </div>
          ))}
          {!(rules?.items || []).length && (
            <div style={{ textAlign: 'center', color: 'var(--text-3)', fontSize: 'var(--text-sm)', padding: '16px 0' }}>
              {t('smartalerts.sin_reglas')}{' '}
              <button onClick={seedDefaults}
                style={{ background: 'none', border: 'none', color: COLOR.accent, cursor: 'pointer', fontSize: 'var(--text-sm)', fontWeight: 600, fontFamily: 'inherit' }}>
                {t('smartalerts.cargar_por_defecto')}
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Historial */}
      <div style={S.card}>
        <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}>
          <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>{t('smartalerts.historial_de_alertas')}</span>
        </div>
        <div style={{ ...S.cardPad, maxHeight: 320, overflowY: 'auto' }}>
          {!(history?.items || []).length && <div style={{ textAlign: 'center', color: 'var(--text-3)', fontSize: 'var(--text-sm)', padding: '16px 0' }}>{t('smartalerts.sin_alertas_disparadas')}</div>}
          {[...(history?.items || [])].reverse().map(entry => (
            <div key={entry.id} style={{ padding: '10px 0', borderBottom: '1px solid var(--surface-4)', display: 'flex', gap: 10, alignItems: 'flex-start' }}>
              <div style={{ width: 8, height: 8, borderRadius: '50%', marginTop: 4, background: entry.severity === 'critical' ? COLOR.danger : entry.severity === 'warning' ? COLOR.warning : COLOR.success, flexShrink: 0 }} />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-1)' }}>{entry.rule_name}</div>
                <div style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-3)' }}>
                  {entry.metric_key} · {String(entry.condition || '').replace(/_/g, ' ')} · {entry.triggered_at ? new Date(entry.triggered_at).toLocaleDateString('es-ES') : '—'}
                </div>
                {entry.correlated && entry.correlated.length > 0 && (
                  <div style={{ fontSize: 'var(--text-2xs)', color: COLOR.warning, marginTop: 2 }}>
                    {t('smartalerts.correlada_con')} {entry.correlated.map(c => c.metric_key).join(', ')}
                  </div>
                )}
              </div>
              {!entry.acknowledged
                ? <button onClick={() => ack(entry.id)}
                    style={{ padding: '3px 10px', borderRadius: 6, border: `1px solid ${COLOR.accent}`, background: 'transparent', color: COLOR.accent, cursor: 'pointer', fontSize: 'var(--text-2xs)', fontWeight: 600, flexShrink: 0, fontFamily: 'inherit' }}>ACK</button>
                : <span style={{ fontSize: 'var(--text-2xs)', color: COLOR.success, fontWeight: 600, flexShrink: 0 }}>✓</span>
              }
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

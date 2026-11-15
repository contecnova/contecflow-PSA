/**
 * SmartAlertsPanel — Reglas + historial de alertas BI inteligentes
 * (forecasting, anomaly trends, threshold). Reutilizable.
 */
import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { biSmartAlertsApi } from '../../services/api'
import type { AlertaDisparadaBi, ReglaDeAlertaBi } from '../../services/api/tipos-bi'
import { COLOR, alpha } from '../../constants/theme'
import { useAppLang } from '../../i18n/AppLangContext'
import { localeActivo } from '../../utils/helpers'
import { STALE_10_MIN_MS, STALE_SHORT_MS } from '../../constants/timings'
import './SmartAlertsPanel.css'

const S: Record<string, React.CSSProperties> = {
  card:        { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' },
  cardPad:     { padding: '20px 24px' },
  input:       { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', color: 'var(--text-1)', borderRadius: 8, padding: '9px 13px', fontSize: 'var(--text-base)', fontFamily: 'inherit', outline: 'none', width: '100%' },
  btnPrimary:  { padding: '7px 16px', borderRadius: 8, background: COLOR.accent, color: 'var(--on-accent-light)', border: 'none', cursor: 'pointer', fontSize: 'var(--text-sm)', fontWeight: 600, fontFamily: 'inherit' },
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

  const { data: rules } = useQuery({
    queryKey: ['bi-alert-rules', tick],
    queryFn: () => biSmartAlertsApi.listRules().then(r => r.data).catch(() => ({ items: [] as ReglaDeAlertaBi[], count: 0 })),
    staleTime: STALE_SHORT_MS,
  })
  const { data: history } = useQuery({
    queryKey: ['bi-alert-history', tick],
    queryFn: () => biSmartAlertsApi.getHistory(50).then(r => r.data).catch(() => ({ items: [] as AlertaDisparadaBi[], count: 0 })),
    staleTime: STALE_SHORT_MS,
  })
  const { data: supported } = useQuery({
    queryKey: ['bi-alert-supported-metrics'],
    queryFn: () => biSmartAlertsApi.supportedMetrics().then(r => r.data).catch(() => null),
    staleTime: STALE_10_MIN_MS,
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
  async function deleteRule(id: ReglaDeAlertaBi['id']) {
    try { await biSmartAlertsApi.deleteRule(id); setTick(x => x + 1) } catch (_) { /* ignore */ }
  }
  async function seedDefaults() {
    try { await biSmartAlertsApi.seedDefaults(); setTick(x => x + 1) } catch (_) { /* ignore */ }
  }
  async function ack(id: AlertaDisparadaBi['id']) {
    try { await biSmartAlertsApi.acknowledge(id); setTick(x => x + 1) } catch (_) { /* ignore */ }
  }

  return (
    <div className="smalpa-grid-1" style={{ gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr' }}>

      {/* Reglas */}
      <div style={S.card}>
        <div className="smalpa-cardpad">
          <span className="smalpa-txt-1">{t('smartalerts.reglas_de_alerta')}</span>
          <button onClick={evaluateNow} style={{ ...S.btnPrimary, padding: '5px 14px', fontSize: 'var(--text-xs)' }}>Evaluar ahora</button>
        </div>
        <div style={S.cardPad}>
          <div className="smalpa-row-1">
            <input aria-label={t('smartalerts.nombre_de_la_regla')} value={name} onChange={e => setName(e.target.value)} placeholder={t('smartalerts.nombre_de_la_regla')}
              className="smalpa-input" />
            <select value={metric} onChange={e => setMetric(e.target.value)} className="smalpa-input2">
              {(supported?.metrics || [{ key: 'revenue', label: 'Revenue' }]).map(m => <option key={m.key} value={m.key}>{m.label}</option>)}
            </select>
            <select value={condition} onChange={e => setCondition(e.target.value)} className="smalpa-input2">
              {/* Sin campo de umbral: las condiciones `threshold_*` se crean desde Configuración (el servidor exige `threshold`). */}
              {(supported?.conditions ?? ['trend_down', 'trend_up', 'anomaly']).filter(c => !c.startsWith('threshold_')).map(c => <option key={c} value={c}>{c.replace(/_/g, ' ')}</option>)}
            </select>
            <select value={severity} onChange={e => setSeverity(e.target.value)} className="smalpa-input2">
              {['info', 'warning', 'critical'].map(s => <option key={s} value={s}>{s}</option>)}
            </select>
            <button onClick={createRule} style={S.btnPrimary}>+ Crear</button>
          </div>
          {(rules?.items || []).map(rule => (
            <div key={rule.id} className="smalpa-row-2">
              <div className="smalpa-box-2" style={{ background: rule.severity === 'critical' ? COLOR.danger : rule.severity === 'warning' ? COLOR.warning : COLOR.success }} />
              <div className="u-flex1">
                <div className="u-text1-sm-600">{rule.name}</div>
                <div className="u-text3-2xs">{rule.metric_key} · {rule.condition.replace(/_/g, ' ')}</div>
              </div>
              <span className="smalpa-box-3" style={{ background: rule.enabled ? alpha(COLOR.success, '18') : 'var(--surface-4)', color: rule.enabled ? COLOR.success : 'var(--text-3)' }}>
                {rule.enabled ? 'activa' : 'pausada'}
              </span>
              <button onClick={() => deleteRule(rule.id)}
                className="smalpa-btnsecondary">✕</button>
            </div>
          ))}
          {!(rules?.items || []).length && (
            <div className="smalpa-box-1">
              {t('smartalerts.sin_reglas')}{' '}
              <button className="smalpa-box-4" onClick={seedDefaults}
                style={{ color: COLOR.accent }}>
                {t('smartalerts.cargar_por_defecto')}
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Historial */}
      <div style={S.card}>
        <div className="smalpa-cardpad2">
          <span className="smalpa-txt-1">{t('smartalerts.historial_de_alertas')}</span>
        </div>
        <div className="smalpa-cardpad3">
          {!(history?.items || []).length && <div className="smalpa-box-1">{t('smartalerts.sin_alertas_disparadas')}</div>}
          {[...(history?.items || [])].reverse().map(entry => (
            <div key={entry.id} className="smalpa-row-3">
              <div className="smalpa-box-5" style={{ background: entry.severity === 'critical' ? COLOR.danger : entry.severity === 'warning' ? COLOR.warning : COLOR.success }} />
              <div className="u-flex1">
                <div className="u-text1-sm-600">{entry.rule_name}</div>
                <div className="u-text3-2xs">
                  {entry.metric_key} · {entry.condition.replace(/_/g, ' ')} · {entry.triggered_at ? new Date(entry.triggered_at).toLocaleDateString(localeActivo()) : '—'}
                </div>
                {entry.correlated && entry.correlated.length > 0 && (
                  <div className="smalpa-box-6" style={{ color: COLOR.warning }}>
                    {t('smartalerts.correlada_con')} {entry.correlated.map(c => c.metric_key).join(', ')}
                  </div>
                )}
              </div>
              {!entry.acknowledged
                ? <button className="smalpa-box-7" onClick={() => ack(entry.id)}
                    style={{ borderRadius: 'var(--radius-sm)', border: `1px solid ${COLOR.accent}`, color: COLOR.accent }}>ACK</button>
                : <span className="smalpa-box-8" style={{ color: COLOR.success }}>✓</span>
              }
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

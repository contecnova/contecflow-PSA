/**
 * SmartAlertsPanel — Reglas + historial de alertas BI inteligentes
 * (forecasting, anomaly trends, threshold). Reutilizable.
 */
import { type CSSProperties, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { biSmartAlertsApi } from '../../services/api'
import type { AlertaDisparadaBi, ReglaDeAlertaBi } from '../../services/api/tipos-bi'
import { COLOR, alpha } from '../../constants/theme'
import { useAppLang } from '../../i18n/AppLangContext'
import { etiquetaMetricaBi } from '../../i18n/catalogoMetricas'
import { useFormatoMoneda } from '../../hooks/useFormatoMoneda'
import { localeActivo } from '../../utils/helpers'
import { STALE_10_MIN_MS, STALE_SHORT_MS } from '../../constants/timings'
import './SmartAlertsPanel.css'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'


export default function SmartAlertsPanel() {
  const { t } = useAppLang()
  const fmtMoneda = useFormatoMoneda()
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

  /** Las métricas propias de la empresa traen su etiqueta; las del sistema se traducen por código. */
  const etiquetaDeMetrica = (clave: string): string => {
    const m = supported?.metrics?.find(x => x.key === clave)
    return m?.is_custom ? m.label : etiquetaMetricaBi(t, clave, m?.label ?? clave, fmtMoneda.simbolo)
  }

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
    <div className={`smalpa-grid-1 ${isMobile ? 'smart-alerts-panel-m1' : 'smart-alerts-panel-m2'}`}>

      {/* Reglas */}
      <div className="smart-alerts-panel-e7">
        <div className="smalpa-cardpad">
          <span className="smalpa-txt-1">{t('smartalerts.reglas_de_alerta')}</span>
          <button onClick={evaluateNow} className="smart-alerts-panel-btn smart-alerts-panel-btn--sm">{t('biconditionaldelivery.evaluar_ahora')}</button>
        </div>
        <div className="smart-alerts-panel-e8">
          <div className="smalpa-row-1">
            <input aria-label={t('smartalerts.nombre_de_la_regla')} value={name} onChange={e => setName(e.target.value)} placeholder={t('smartalerts.nombre_de_la_regla')}
              className="smalpa-input" />
            <select value={metric} onChange={e => setMetric(e.target.value)} className="smalpa-input2">
              {(supported?.metrics || [{ key: 'revenue', label: 'Revenue', is_custom: false }]).map(m => <option key={m.key} value={m.key}>{etiquetaDeMetrica(m.key)}</option>)}
            </select>
            <select value={condition} onChange={e => setCondition(e.target.value)} className="smalpa-input2">
              {/* Sin campo de umbral: las condiciones `threshold_*` se crean desde Configuración (el servidor exige `threshold`). */}
              {(supported?.conditions ?? ['trend_down', 'trend_up', 'anomaly']).filter(c => !c.startsWith('threshold_')).map(c => <option key={c} value={c}>{etiquetaCodigo(t, 'condicion_alerta', c)}</option>)}
            </select>
            <select value={severity} onChange={e => setSeverity(e.target.value)} className="smalpa-input2">
              {['info', 'warning', 'critical'].map(s => <option key={s} value={s}>{s}</option>)}
            </select>
            <button onClick={createRule} className="smart-alerts-panel-btn">{t('smartalerts.crear')}</button>
          </div>
          {(rules?.items || []).map(rule => (
            <div key={rule.id} className="smalpa-row-2">
              <div className="smalpa-box-2 smart-alerts-panel-e3" style={{ '--smart-alerts-panel-background': rule.severity === 'critical' ? COLOR.danger : rule.severity === 'warning' ? COLOR.warning : COLOR.success } as CSSProperties} />
              <div className="u-flex1">
                <div className="u-text1-sm-600">{rule.name}</div>
                <div className="u-text3-2xs">{etiquetaDeMetrica(rule.metric_key)} · {etiquetaCodigo(t, 'condicion_alerta', rule.condition)}</div>
              </div>
              <span className="smalpa-box-3 smart-alerts-panel-e4" style={{ '--smart-alerts-panel-background': rule.enabled ? alpha(COLOR.success, '18') : 'var(--surface-4)', '--smart-alerts-panel-color': rule.enabled ? COLOR.success : 'var(--text-3)' } as CSSProperties}>
                {rule.enabled ? 'activa' : 'pausada'}
              </span>
              <button onClick={() => deleteRule(rule.id)}
                className="smalpa-btnsecondary">✕</button>
            </div>
          ))}
          {!(rules?.items || []).length && (
            <div className="smalpa-box-1">
              {t('smartalerts.sin_reglas')}{' '}
              <button className="smalpa-box-4 smart-alerts-panel-e5" onClick={seedDefaults}
                style={{ '--smart-alerts-panel-color': COLOR.accent } as CSSProperties}>
                {t('smartalerts.cargar_por_defecto')}
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Historial */}
      <div className="smart-alerts-panel-e7">
        <div className="smalpa-cardpad2">
          <span className="smalpa-txt-1">{t('smartalerts.historial_de_alertas')}</span>
        </div>
        <div className="smalpa-cardpad3">
          {!(history?.items || []).length && <div className="smalpa-box-1">{t('smartalerts.sin_alertas_disparadas')}</div>}
          {[...(history?.items || [])].reverse().map(entry => (
            <div key={entry.id} className="smalpa-row-3">
              <div className="smalpa-box-5 smart-alerts-panel-e3" style={{ '--smart-alerts-panel-background': entry.severity === 'critical' ? COLOR.danger : entry.severity === 'warning' ? COLOR.warning : COLOR.success } as CSSProperties} />
              <div className="u-flex1">
                <div className="u-text1-sm-600">{entry.rule_name}</div>
                <div className="u-text3-2xs">
                  {etiquetaDeMetrica(entry.metric_key)} · {etiquetaCodigo(t, 'condicion_alerta', entry.condition)} ·{entry.triggered_at ? new Date(entry.triggered_at).toLocaleDateString(localeActivo()) : '—'}
                </div>
                {entry.correlated && entry.correlated.length > 0 && (
                  <div className="smalpa-box-6 smart-alerts-panel-e5" style={{ '--smart-alerts-panel-color': COLOR.warning } as CSSProperties}>
                    {t('smartalerts.correlada_con')} {entry.correlated.map(c => etiquetaDeMetrica(c.metric_key)).join(', ')}
                  </div>
                )}
              </div>
              {!entry.acknowledged
                ? <button className="smalpa-box-7 smartale-sx1 smart-alerts-panel-e6" onClick={() => ack(entry.id)}
                    style={{ '--smart-alerts-panel-border': `1px solid ${COLOR.accent}`, '--smart-alerts-panel-color': COLOR.accent } as CSSProperties}>ACK</button>
                : <span className="smalpa-box-8 smart-alerts-panel-e5" style={{ '--smart-alerts-panel-color': COLOR.success } as CSSProperties}>✓</span>
              }
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

/**
 * SmartAlertsPanel — Reglas + historial de alertas BI inteligentes
 * (forecasting, anomaly trends, threshold). Reutilizable.
 *
 * 16-11-2026 (pasada de diseño): botones, insignias y vacíos del kit; fechas con
 * fmtDate; severidades y estados traducidos; sin emojis ni «ACK».
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Bell, Check, Plus, Play, Trash2, ListChecks, Link2 } from 'lucide-react'
import { biSmartAlertsApi } from '../../services/api'
import type { AlertaDisparadaBi, ReglaDeAlertaBi } from '../../services/api/tipos-bi'
import { Button, EmptyState, IconButton, StatusBadge, Select } from '../ui'
import { useAppLang } from '../../i18n/AppLangContext'
import { etiquetaMetricaBi } from '../../i18n/catalogoMetricas'
import { useFormatoMoneda } from '../../hooks/useFormatoMoneda'
import { extractErr, fmtDate } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { useToast } from '../../context/ToastContext'
import { confirmar } from '../../context/ConfirmContext'
import { STALE_10_MIN_MS, STALE_SHORT_MS } from '../../constants/timings'
import './SmartAlertsPanel.css'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { Input } from '../ui'

const SEVERIDADES = ['info', 'warning', 'critical'] as const
const tonoSeveridad = (s?: string | null) => (s === 'critical' ? 'danger' : s === 'warning' ? 'warning' : 'accent')

export default function SmartAlertsPanel() {
  const { t } = useAppLang()
  const fmtMoneda = useFormatoMoneda()
  const toast = useToast()
  const [tick, setTick] = useState<number>(0)
  const [name, setName] = useState<string>('')
  const [metric, setMetric] = useState<string>('revenue')
  const [condition, setCondition] = useState<string>('trend_down')
  const [severity, setSeverity] = useState<string>('warning')

  const { data: rules } = useQuery({
    queryKey: ['bi-alert-rules', tick],
    queryFn: () => biSmartAlertsApi.listRules().then(r => r.data),
    staleTime: STALE_SHORT_MS,
  })
  const { data: history } = useQuery({
    queryKey: ['bi-alert-history', tick],
    queryFn: () => biSmartAlertsApi.getHistory(50).then(r => r.data),
    staleTime: STALE_SHORT_MS,
  })
  const { data: supported } = useQuery({
    queryKey: ['bi-alert-supported-metrics'],
    queryFn: () => biSmartAlertsApi.supportedMetrics().then(r => r.data),
    staleTime: STALE_10_MIN_MS,
  })

  /** Las métricas propias de la empresa traen su etiqueta; las del sistema se traducen por código. */
  const etiquetaDeMetrica = (clave: string): string => {
    const m = supported?.metrics?.find(x => x.key === clave)
    return m?.is_custom ? m.label : etiquetaMetricaBi(t, clave, m?.label ?? clave, fmtMoneda.simbolo)
  }
  const etiquetaSeveridad = (s?: string | null) => (s && (SEVERIDADES as readonly string[]).includes(s) ? t(`alerts.severity_${s}`) : (s || ''))

  // 23-11-2026: antes cada acción tragaba el error; ahora avisa con el mensaje del servidor.
  const alFallar = (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  async function evaluateNow() {
    try { await biSmartAlertsApi.evaluate(); setTick(x => x + 1) } catch (e) { alFallar(e) }
  }
  async function createRule() {
    if (!name.trim()) return
    try {
      await biSmartAlertsApi.createRule({ name, metric_key: metric, condition, severity })
      setName('')
      setTick(x => x + 1)
    } catch (e) { alFallar(e) }
  }
  async function deleteRule(id: ReglaDeAlertaBi['id']) {
    // 23-11-2026: borrar una regla de alerta pide confirmación.
    if (!(await confirmar({ message: t('smartalerts.confirmar_eliminar_regla'), danger: true, confirmLabel: t('common.delete') }))) return
    try { await biSmartAlertsApi.deleteRule(id); setTick(x => x + 1) } catch (e) { alFallar(e) }
  }
  async function seedDefaults() {
    try { await biSmartAlertsApi.seedDefaults(); setTick(x => x + 1) } catch (e) { alFallar(e) }
  }
  async function ack(id: AlertaDisparadaBi['id']) {
    try { await biSmartAlertsApi.acknowledge(id); setTick(x => x + 1) } catch (e) { alFallar(e) }
  }

  const reglas = rules?.items || []
  const historial = [...(history?.items || [])].reverse()

  return (
    <div className="smalpa-grid">

      {/* Reglas */}
      <div className="ds-card smalpa-card">
        <div className="smalpa-head">
          <span className="smalpa-title">{t('smartalerts.reglas_de_alerta')}</span>
          <Button variant="secondary" size="sm" icon={<Play size={14} />} onClick={() => { void evaluateNow() }}>
            {t('biconditionaldelivery.evaluar_ahora')}
          </Button>
        </div>
        <div className="smalpa-body">
          <div className="smalpa-form">
            <Input aria-label={t('smartalerts.nombre_de_la_regla')} value={name} onChange={e => setName(e.target.value)} placeholder={t('smartalerts.nombre_de_la_regla')} className="smalpa-form-name" />
            <Select suelto aria-label={t('smartalerts.metrica')} value={metric} onChange={e => setMetric(e.target.value)} className="ds-input smalpa-form-select" placeholder={false}>
              {(supported?.metrics || [{ key: 'revenue', label: 'revenue', is_custom: false }]).map(m => <option key={m.key} value={m.key}>{etiquetaDeMetrica(m.key)}</option>)}
            </Select>
            <Select suelto aria-label={t('smartalerts.condicion')} value={condition} onChange={e => setCondition(e.target.value)} className="ds-input smalpa-form-select" placeholder={false}>
              {/* Sin campo de umbral: las condiciones `threshold_*` se crean desde Configuración (el servidor exige `threshold`). */}
              {(supported?.conditions ?? ['trend_down', 'trend_up', 'anomaly']).filter(c => !c.startsWith('threshold_')).map(c => <option key={c} value={c}>{etiquetaCodigo(t, 'condicion_alerta', c)}</option>)}
            </Select>
            <Select suelto aria-label={t('smartalerts.severidad')} value={severity} onChange={e => setSeverity(e.target.value)} className="ds-input smalpa-form-select" placeholder={false}>
              {SEVERIDADES.map(s => <option key={s} value={s}>{etiquetaSeveridad(s)}</option>)}
            </Select>
            <Button icon={<Plus size={14} />} onClick={() => { void createRule() }} disabled={!name.trim()}>{t('smartalerts.crear')}</Button>
          </div>
          {reglas.map(rule => (
            <div key={rule.id} className="smalpa-row">
              <span className={`ds-status-dot ds-status-dot--${tonoSeveridad(rule.severity)}`} aria-hidden="true" />
              <div className="smalpa-row-main">
                <div className="u-text1-sm-600">{rule.name}</div>
                <div className="u-text3-2xs">{etiquetaDeMetrica(rule.metric_key)} · {etiquetaCodigo(t, 'condicion_alerta', rule.condition)} · {etiquetaSeveridad(rule.severity)}</div>
              </div>
              <StatusBadge kind={rule.enabled ? 'success' : 'neutral'}>
                {rule.enabled ? t('smartalerts.activa') : t('smartalerts.pausada')}
              </StatusBadge>
              <IconButton variante="caja" tono="peligro" ariaLabel={t('smartalerts.eliminar_regla', { name: rule.name })} onClick={() => { void deleteRule(rule.id) }}>
                <Trash2 size={14} aria-hidden="true" />
              </IconButton>
            </div>
          ))}
          {!reglas.length && (
            <EmptyState
              icon={<ListChecks size={28} />}
              title={t('smartalerts.sin_reglas')}
              description={t('smartalerts.sin_reglas_desc')}
              action={<Button variant="secondary" onClick={() => { void seedDefaults() }}>{t('smartalerts.cargar_por_defecto')}</Button>}
            />
          )}
        </div>
      </div>

      {/* Historial */}
      <div className="ds-card smalpa-card">
        <div className="smalpa-head">
          <span className="smalpa-title">{t('smartalerts.historial_de_alertas')}</span>
        </div>
        <div className="smalpa-body smalpa-body--scroll">
          {!historial.length && (
            <EmptyState icon={<Bell size={28} />} title={t('smartalerts.sin_alertas_disparadas')} description={t('smartalerts.sin_alertas_desc')} />
          )}
          {historial.map(entry => (
            <div key={entry.id} className="smalpa-row smalpa-row--top">
              <span className={`ds-status-dot ds-status-dot--${tonoSeveridad(entry.severity)} smalpa-dot-top`} aria-hidden="true" />
              <div className="smalpa-row-main">
                <div className="u-text1-sm-600">{entry.rule_name}</div>
                <div className="u-text3-2xs">
                  {etiquetaDeMetrica(entry.metric_key)} · {etiquetaCodigo(t, 'condicion_alerta', entry.condition)} · {fmtDate(entry.triggered_at)}
                </div>
                {entry.correlated && entry.correlated.length > 0 && (
                  <div className="smalpa-correlated">
                    <Link2 size={12} aria-hidden="true" /> {t('smartalerts.correlada_con')} {entry.correlated.map(c => etiquetaDeMetrica(c.metric_key)).join(', ')}
                  </div>
                )}
              </div>
              {!entry.acknowledged
                ? <Button variant="secondary" size="xs" onClick={() => { void ack(entry.id) }}>{t('smartalerts.reconocer')}</Button>
                : <StatusBadge kind="success"><Check size={11} aria-hidden="true" /> {t('smartalerts.reconocida')}</StatusBadge>}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

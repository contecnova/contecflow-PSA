/**
 * Secciones de configuración de alertas y de métricas.
 * Troceado de SettingsPageSections.tsx sin cambio de comportamiento (23-11-2026).
 */
import React, { useState, type CSSProperties, type SetStateAction } from 'react'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { useToast } from '../../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { advancedConfigApi } from '../../services/settingsApi'
import { biSmartAlertsApi } from '../../services/api'
import type { MetricasDeAlertaBi } from '../../services/api/tipos-bi'
import { Button, Checkbox, Input, Modal, Select, Spinner } from '../../components/ui'
import { Plus, Bell, BarChart3 } from 'lucide-react'
import { useAppLang } from '../../i18n/AppLangContext'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import SeccionDeAjustes from './SeccionDeAjustes'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { type AlertConfig, type InputChange, type MetricForm, type NotifyKey, type RuleForm } from './tiposDeAjustes'

// ── Alert configs section ─────────────────────────────────────────────────────
// Códigos de condición; la etiqueta sale de `condicion_alerta.<código>` (etiquetaCodigo).
const CONDITION_CODES = ['threshold_above', 'threshold_below', 'trend_up', 'trend_down', 'anomaly'] as const

const THRESHOLD_CONDITIONS = ['threshold_above', 'threshold_below']

const NOTIFY_FIELDS: ReadonlyArray<readonly [NotifyKey, string]> = [['notify_admin', 'settings_sections.notif_admin'], ['notify_pm', 'settings_sections.notif_pm'], ['notify_hr', 'settings_sections.notif_rrhh'], ['notify_employee', 'settings_sections.notif_empleado'], ['notify_email', 'settings_sections.notif_email']]

export function AlertConfigSection() {
  const idCampo = React.useId()
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const SEV_CFG: Record<string, string> = { info: 'var(--accent)', warning: 'var(--warning)', critical: 'var(--danger)' }

  // — system alert configs (fixed 8 types) —
  const { data: configs = [], isLoading } = useQuery<AlertConfig[]>({ queryKey: ['alert-configs'], queryFn: () => advancedConfigApi.getAlertConfigs().then(r => r.data) })
  const { mutate: update } = useMutation({ mutationFn: ({ type, data }: { type: string; data: Partial<AlertConfig> }) => advancedConfigApi.updateAlertConfig(type, data), onSuccess: () => qc.invalidateQueries({ queryKey: ['alert-configs'] }), onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })

  // — BI custom alert rules —
  const { data: rulesData } = useQuery({ queryKey: ['bi-alert-rules'], queryFn: () => biSmartAlertsApi.listRules().then(r => r.data) })
  const { data: metricsData } = useQuery<MetricasDeAlertaBi>({ queryKey: ['bi-alert-metrics'], queryFn: () => biSmartAlertsApi.supportedMetrics().then(r => r.data) })
  const rules = rulesData?.items ?? []
  const metrics = metricsData?.metrics ?? []

  const { mutate: createRule, isPending: isCreating } = useMutation({
    mutationFn: biSmartAlertsApi.createRule,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['bi-alert-rules'] }); setShowCreate(false); setRuleForm(EMPTY_RULE) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: toggleRule } = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) => biSmartAlertsApi.updateRule(id, { enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bi-alert-rules'] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: deleteRule } = useMutation({
    mutationFn: biSmartAlertsApi.deleteRule,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bi-alert-rules'] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const EMPTY_RULE: RuleForm = { name: '', metric_key: '', condition: 'threshold_above', threshold: '', severity: 'warning', cooldown_minutes: 60 }
  const [ui, setUi] = useState<{ showCreate: boolean; ruleForm: RuleForm }>({ showCreate: false, ruleForm: EMPTY_RULE })
  const { showCreate, ruleForm } = ui
  const setShowCreate = (v: SetStateAction<boolean>) => setUi(s => ({ ...s, showCreate: typeof v === 'function' ? v(s.showCreate) : v }))
  const setRuleForm = (v: SetStateAction<RuleForm>) => setUi(s => ({ ...s, ruleForm: typeof v === 'function' ? v(s.ruleForm) : v }))
  const setR = (k: keyof RuleForm) => (e: InputChange) => setRuleForm(f => ({ ...f, [k]: e.target.value }))
  const condLabel = (c: string) => etiquetaCodigo(t, 'condicion_alerta', c)

  const submitRule = () => {
    if (!ruleForm.name.trim() || !ruleForm.metric_key) { toast.error(t('settings_sections.err_nombre_metrica')); return }
    const payload = { ...ruleForm, cooldown_minutes: +ruleForm.cooldown_minutes }
    if (THRESHOLD_CONDITIONS.includes(ruleForm.condition)) payload.threshold = +ruleForm.threshold
    else delete payload.threshold
    createRule(payload)
  }

  return (
    <SeccionDeAjustes icon={<Bell size={18} />} title={t('settings_sections.alertas_titulo')} description={t('settings_sections.alertas_desc')}>
      {isLoading ? <Spinner /> : (
        <div className="u-stack-10">
          {configs.map(cfg => (
            <div key={cfg.alert_type} className={`set-alert-card ${cfg.is_enabled ? 'set-alert-card--on' : 'set-alert-card--off'}`} style={{ '--set-color': SEV_CFG[cfg.severity] } as CSSProperties}>
              <div className="set-alert-head">
                <div>
                  <div className="set-alert-title">
                    <span className="u-base-700">{cfg.label}</span>
                    <span className="set-sev">{cfg.severity}</span>
                  </div>
                  {cfg.description && <div className="u-text2-sm">{cfg.description}</div>}
                </div>
                <Checkbox className="set-toggle" aria-label={cfg.label} label={<span className="u-text2-sm">{cfg.is_enabled ? t('settings_sections.activa') : t('settings_sections.inactiva')}</span>} checked={cfg.is_enabled} onChange={m => update({ type: cfg.alert_type, data: { is_enabled: m } })} />
              </div>
              {cfg.is_enabled && (
                <div className="set-alert-body">
                  {cfg.threshold_value !== null && (
                    <div className="u-row-center-8">
                      <label id={`${idCampo}-${cfg.alert_type}-etc723`} htmlFor={`${idCampo}-${cfg.alert_type}-c723`} className="u-text2-xs">{t('settings_sections.umbral')}:</label>
                      <Input id={`${idCampo}-${cfg.alert_type}-c723`} aria-labelledby={`${idCampo}-${cfg.alert_type}-etc723`} type="number" defaultValue={cfg.threshold_value ?? undefined} onBlur={e => update({ type: cfg.alert_type, data: { threshold_value: +e.target.value } })}
                        inputClassName="set-threshold" />
                      <span className="u-text2-xs">{cfg.threshold_unit}</span>
                    </div>
                  )}
                  <div className="u-wrap-10" role="group" aria-label={t('settings_sections.notificar_a')}>
                    {NOTIFY_FIELDS.map(([key, labelKey]) => (
                      <Checkbox key={key} className={`set-notify${cfg[key] ? ' set-notify--on' : ''}`} label={t(labelKey)} checked={!!cfg[key]} onChange={m => update({ type: cfg.alert_type, data: { [key]: m } })} />
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* ── Custom BI alert rules ─────────────────── */}
      <div className="set-block-top">
        <div className="u-row-between u-mb-12">
          <div>
            <div className="u-base-700">{t('settings_sections.reglas_personalizadas')}</div>
            <div className="u-text2-sm">{t('settings.alertas_basadas_en_metricas_del_sistema')}</div>
          </div>
          <Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{t('settings.nueva_alerta')}</Button>
        </div>
        {rules.length === 0 ? (
          <div className="set-empty-row">{t('settings.no_hay_reglas_personalizadas_crea_la_primera')}</div>
        ) : (
          <div className="u-stack-8">
            {rules.map(rule => (
              <div key={rule.id} className={`set-rule ${rule.enabled ? 'set-rule--on' : 'set-rule--off'}`} style={{ '--set-color': SEV_CFG[rule.severity] } as CSSProperties}>
                <div className="u-flex1-min0">
                  <div className="set-rule-title">
                    <span className="u-base-600">{rule.name}</span>
                    <span className="set-sev">{rule.severity}</span>
                  </div>
                  <div className="u-text2-xs">
                    {metrics.find(m => m.key === rule.metric_key)?.label ?? rule.metric_key} · {condLabel(rule.condition)}{rule.threshold != null ? ` · ${t('settings_sections.umbral_valor', { valor: rule.threshold })}` : ''}
                  </div>
                </div>
                <div className="set-rule-actions">
                  <Checkbox className="set-notify" aria-label={rule.name} label={rule.enabled ? t('settings_sections.activa') : t('settings_sections.inactiva')} checked={!!rule.enabled} onChange={m => toggleRule({ id: rule.id, enabled: m })} />
                  <Button variant="danger" size="xs" onClick={() => openConfirmGlobal({ title: t('settings_sections.eliminar_regla'), message: t('settings_sections.confirmar_eliminar_x', { nombre: rule.name }), onConfirm: () => deleteRule(rule.id) })}>{t('common.delete')}</Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {showCreate && (
        <Modal open title={t('settings.nueva_regla_de_alerta')} onClose={() => { setShowCreate(false); setRuleForm(EMPTY_RULE) }} width={480}>
          <div className="u-stack-14">
            <div>
              <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="set-label">{t('common.name')}</label>
              <Input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={ruleForm.name} onChange={setR('name')} placeholder={t('settings.ej_ingresos_por_debajo_del_objetivo')} inputClassName="set-input" />
            </div>
            <div>
              <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="set-label">{t('settings.metrica')}</label>
              <Select suelto placeholder={t('settings.selecciona_una_metrica')} id={`${idCampo}-2`} value={ruleForm.metric_key} onChange={setR('metric_key')} className="set-input">
                {metrics.map(m => <option key={m.key} value={m.key}>{m.label}</option>)}
              </Select>
            </div>
            <div className="u-grid2-12">
              <div>
                <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="set-label">{t('settings.condicion')}</label>
                <Select suelto placeholder={false} id={`${idCampo}-3`} value={ruleForm.condition} onChange={setR('condition')} className="set-input">
                  {CONDITION_CODES.map(k => <option key={k} value={k}>{condLabel(k)}</option>)}
                </Select>
              </div>
              {THRESHOLD_CONDITIONS.includes(ruleForm.condition) && (
                <div>
                  <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="set-label">{t('settings_sections.umbral')}</label>
                  <Input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} type="number" value={ruleForm.threshold} onChange={setR('threshold')} placeholder="0" inputClassName="set-input" />
                </div>
              )}
            </div>
            <div className="u-grid2-12">
              <div>
                <label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="set-label">{t('settings_sections.severidad')}</label>
                <Select suelto placeholder={false} id={`${idCampo}-5`} value={ruleForm.severity} onChange={setR('severity')} className="set-input">
                  <option value="info">{t('settings_sections.sev_info')}</option>
                  <option value="warning">{t('settings_sections.sev_warning')}</option>
                  <option value="critical">{t('settings_sections.sev_critical')}</option>
                </Select>
              </div>
              <div>
                <label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} className="set-label">{t('settings_sections.cooldown_minutos')}</label>
                <Input id={`${idCampo}-6`} aria-labelledby={`${idCampo}-et6`} type="number" value={ruleForm.cooldown_minutes} onChange={setR('cooldown_minutes')} min={5} inputClassName="set-input" />
              </div>
            </div>
            <div className="u-actions-10 set-mt4">
              <Button variant="secondary" onClick={() => { setShowCreate(false); setRuleForm(EMPTY_RULE) }}>{t('common.cancel')}</Button>
              <Button onClick={submitRule} disabled={isCreating}>{isCreating ? t('settings_sections.creando') : t('settings_sections.crear_alerta')}</Button>
            </div>
          </div>
        </Modal>
      )}
    </SeccionDeAjustes>
  )
}

// ── Metrics section ───────────────────────────────────────────────────────────
const OPERATOR_KEYS: Record<string, string> = { '+': 'settings_sections.op_suma', '-': 'settings_sections.op_resta', '*': 'settings_sections.op_multiplica', '/': 'settings_sections.op_divide' }

const EMPTY_METRIC: MetricForm = { label: '', description: '', operand_a: '', operator: '/', operand_b_type: 'metric', operand_b: '', scale: 1 }

export function MetricsSection() {
  const idCampo = React.useId()
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()

  const { data: metricsData } = useQuery<MetricasDeAlertaBi>({ queryKey: ['bi-alert-metrics'], queryFn: () => biSmartAlertsApi.supportedMetrics().then(r => r.data) })
  const { data: customData } = useQuery({ queryKey: ['bi-custom-metrics'], queryFn: () => biSmartAlertsApi.listCustomMetrics().then(r => r.data) })
  const builtinMetrics = (metricsData?.metrics ?? []).filter(m => !m.is_custom)
  const customMetrics = customData?.items ?? []

  const { mutate: createMetric, isPending: isCreating } = useMutation({
    mutationFn: biSmartAlertsApi.createCustomMetric,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['bi-custom-metrics'] }); qc.invalidateQueries({ queryKey: ['bi-alert-metrics'] }); setShowCreate(false); setForm(EMPTY_METRIC) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: deleteMetric } = useMutation({
    mutationFn: biSmartAlertsApi.deleteCustomMetric,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['bi-custom-metrics'] }); qc.invalidateQueries({ queryKey: ['bi-alert-metrics'] }) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const [ui, setUi] = useState<{ showCreate: boolean; form: MetricForm }>({ showCreate: false, form: EMPTY_METRIC })
  const { showCreate, form } = ui
  const setShowCreate = (v: SetStateAction<boolean>) => setUi(s => ({ ...s, showCreate: typeof v === 'function' ? v(s.showCreate) : v }))
  const setForm = (v: SetStateAction<MetricForm>) => setUi(s => ({ ...s, form: typeof v === 'function' ? v(s.form) : v }))
  const setF = (k: keyof MetricForm) => (e: InputChange) => setForm(f => ({ ...f, [k]: e.target.value }))

  const preview = (() => {
    const la = builtinMetrics.find(m => m.key === form.operand_a)?.label ?? form.operand_a
    const lb = form.operand_b_type === 'metric'
      ? (builtinMetrics.find(m => m.key === form.operand_b)?.label ?? form.operand_b)
      : form.operand_b
    if (!form.operand_a) return ''
    const scaled = parseFloat(String(form.scale)) !== 1 ? ` × ${form.scale}` : ''
    return `(${la} ${form.operator} ${lb})${scaled}`
  })()

  const submit = () => {
    if (!form.label.trim() || !form.operand_a) { toast.error(t('settings_sections.err_nombre_operando')); return }
    if (form.operand_b_type === 'metric' && !form.operand_b) { toast.error(t('settings_sections.err_selecciona_metrica_b')); return }
    createMetric({ ...form, scale: parseFloat(String(form.scale)) || 1 })
  }

  return (
    <SeccionDeAjustes icon={<BarChart3 size={18} />} title={t('settings.metricas')} description={t('settings_sections.metricas_desc')}>
      {/* Built-in metrics */}
      <div className="set-mb24">
        <div className="set-section-title set-section-title--mb">{t('settings.metricas_del_sistema')}{builtinMetrics.length})</div>
        <div className="set-metrics-grid">
          {builtinMetrics.map(m => (
            <div key={m.key} className="set-metric-tile">
              <div className="u-text1-sm-600">{m.label}</div>
              <div className="ds-codigo set-metric-key">{m.key}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Custom metrics */}
      <div>
        <div className="u-row-between u-mb-10">
          <div className="set-section-title">{t('settings.metricas_personalizadas')}{customMetrics.length})</div>
          <Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{t('settings.nueva_metrica')}</Button>
        </div>
        {customMetrics.length === 0 ? (
          <div className="set-empty-row set-empty-row--sm">{t('settings.no_hay_metricas_personalizadas_crea_la_primera')}</div>
        ) : (
          <div className="u-stack-8">
            {customMetrics.map(cm => {
              const f = cm.formula
              const la = builtinMetrics.find(m => m.key === f.operand_a)?.label ?? f.operand_a
              const lb = f.operand_b_type === 'metric'
                ? (builtinMetrics.find(m => m.key === f.operand_b)?.label ?? f.operand_b)
                : f.operand_b
              const scale = f.scale !== 1 ? ` × ${f.scale}` : ''
              return (
                <div key={cm.key} className="set-rule">
                  <div className="u-flex1-min0">
                    <div className="set-metric-name">{cm.label}</div>
                    <div className="ds-codigo set-metric-formula">({la} {f.operator} {lb}){scale}</div>
                    {cm.description && <div className="u-text3-xs-mt2">{cm.description}</div>}
                  </div>
                  <div className="set-rule-actions set-rule-actions--8">
                    <span className="ds-codigo set-metric-id">{cm.key}</span>
                    <Button variant="danger" size="xs" onClick={() => openConfirmGlobal({ title: t('settings_sections.eliminar_metrica'), message: t('settings_sections.confirmar_eliminar_metrica', { nombre: cm.label }), onConfirm: () => deleteMetric(cm.key) })}>{t('common.delete')}</Button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {showCreate && (
        <Modal open title={t('settings.nueva_metrica_personalizada')} onClose={() => { setShowCreate(false); setForm(EMPTY_METRIC) }} width={500}>
          <div className="u-stack-14">
            <div>
              <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="set-label">{t('common.name')}</label>
              <Input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.label} onChange={setF('label')} placeholder={t('settings_sections.ej_ratio')} inputClassName="set-input" />
            </div>
            <div>
              <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="set-label">{t('settings.descripcion_opcional')}</label>
              <Input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.description} onChange={setF('description')} placeholder={t('settings.para_que_sirve_esta_metrica')} inputClassName="set-input" />
            </div>
            <div className="set-formula-box">
              <div className="set-formula-title">{t('settings.formula_a_operador_b_escala')}</div>
              <div className="set-formula-grid">
                <div>
                  <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="set-label">{t('settings.metrica_a')}</label>
                  <Select suelto placeholder={t('settings_sections.selecciona')} id={`${idCampo}-3`} value={form.operand_a} onChange={setF('operand_a')} className="set-input">
                    {builtinMetrics.map(m => <option key={m.key} value={m.key}>{m.label}</option>)}
                  </Select>
                </div>
                <div>
                  <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="set-label" title={t('settings_sections.operador')}>{t('settings_sections.op')}</label>
                  <Select suelto placeholder={false} id={`${idCampo}-4`} value={form.operator} onChange={setF('operator')} className="set-input set-input--w70">
                    {Object.entries(OPERATOR_KEYS).map(([k, v]) => <option key={k} value={k}>{k} ({t(v)})</option>)}
                  </Select>
                </div>
                <div>
                  <label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="set-label">{t('settings_sections.tipo_b')}</label>
                  <Select suelto placeholder={false} id={`${idCampo}-5`} value={form.operand_b_type} onChange={setF('operand_b_type')} className="set-input">
                    <option value="metric">{t('settings.otra_metrica')}</option>
                    <option value="constant">{t('settings_sections.constante')}</option>
                  </Select>
                </div>
              </div>
              <div className="u-grid2-10">
                <div>
                  <label id={`${idCampo}-etopb`} htmlFor={`${idCampo}-opb`} className="set-label">{form.operand_b_type === 'metric' ? t('settings_sections.metrica_b') : t('settings_sections.valor_constante')}</label>
                  {form.operand_b_type === 'metric' ? (
                    <Select suelto placeholder={t('settings_sections.selecciona')} id={`${idCampo}-opb`} value={form.operand_b} onChange={setF('operand_b')} className="set-input">
                      {builtinMetrics.filter(m => m.key !== form.operand_a).map(m => <option key={m.key} value={m.key}>{m.label}</option>)}
                    </Select>
                  ) : (
                    <Input id={`${idCampo}-opb`} aria-labelledby={`${idCampo}-etopb`} type="number" value={form.operand_b} onChange={setF('operand_b')} placeholder="0" inputClassName="set-input" />
                  )}
                </div>
                <div>
                  <label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} className="set-label">{t('settings_sections.escala')}</label>
                  <Input id={`${idCampo}-6`} aria-labelledby={`${idCampo}-et6`} type="number" value={form.scale} onChange={setF('scale')} placeholder="1" step="any" inputClassName="set-input" />
                </div>
              </div>
              {preview && (
                <div className="set-preview">
                  {t('settings_sections.vista_previa', { formula: preview })}
                </div>
              )}
            </div>
            <div className="u-actions-10">
              <Button variant="secondary" onClick={() => { setShowCreate(false); setForm(EMPTY_METRIC) }}>{t('common.cancel')}</Button>
              <Button onClick={submit} disabled={isCreating}>{isCreating ? t('settings_sections.creando') : t('settings_sections.crear_metrica')}</Button>
            </div>
          </div>
        </Modal>
      )}
    </SeccionDeAjustes>
  )
}

// Pestañas de segregacion de funciones (reglas SoD) y violaciones de GRC. 23-11-2026: troceado de GrcPage sin cambio de comportamiento.
import { useAppLang, useAppT } from '../i18n/AppLangContext'
import { useState, useId } from 'react'
import type { CSSProperties } from 'react'
import { openConfirmGlobal, pedirTexto } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useToast } from '../context/ToastContext'
import { grcApi, approvalsApi } from '../services/api'
import type { ReglaSod as SodRule, ConflictoSod as SodViolation, ViolacionSod as ViolationRecord } from '../services/api/tipos-grc'
import { AlertOctagon, Check, CheckCircle2, Pause, Pencil, Play, Plus, RefreshCw, Search, ShieldAlert, ShieldCheck, Trash2 } from 'lucide-react'
import { Button, Spinner, EmptyState, Modal, KpiCard, StatusBadge, IconButton, Select, useErroresDeCampo, Input } from '../components/ui'
import { extractErr, fmtDateTime } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { alpha } from '../constants/theme'
import { POLL_DEFAULT_MS, STALE_SHORT_MS } from '../constants/timings'
import { ACTIONS, MODULE_LABELS, RIESGOS, RISK_COLOR, type Role, accionDe, moduleInfo, rolesDeReserva, usePermisos } from './GrcComun'

// ═══════════════════════════════════════════════════════════════════════════════
// 2. SEGREGACIÓN SoD (wired to API + CRUD)
// ═══════════════════════════════════════════════════════════════════════════════
export type Workflow = {
  [k: string]: unknown
  id: string
  name?: string
  entity_type?: string
  is_active?: boolean
  steps?: { id: string; name?: string; approver_role?: string; approver_user_name?: string }[]
}

function SodRuleModal({ rule, workflows, onClose, roles }: { rule: SodRule | null; workflows: Workflow[]; onClose: () => void; roles: Role[] }) {
  const idCampo = useId()
  const traducir = useAppT()
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const isEdit = !!rule
  const { data: permisos } = usePermisos()
  const MODULES = (permisos?.modules || Object.keys(MODULE_LABELS)).map(moduleInfo(t))
  const acciones = permisos?.actions || ACTIONS
  // Revisión GRC 16-11-2026: sólo los roles que gobierna la matriz (la API rechaza otros con 422).
  const rolesDeLaMatriz: Role[] = (permisos?.roles || roles.map(r => r.id)).map(id =>
    roles.find(r => r.id === id) || rolesDeReserva(t).find(r => r.id === id) || { id, label: id, color: 'var(--text-2)' })
  const [form, setForm] = useState<{
    module_a: string; action_a: string; module_b: string; action_b: string;
    risk: string; description: string; roles_conflict: string[]; mitigated_by_workflow_id: string | null;
  }>({
    module_a: rule?.module_a || 'invoices',
    action_a: rule?.action_a || 'crear',
    module_b: rule?.module_b || 'invoices',
    action_b: rule?.action_b || 'aprobar',
    risk: rule?.risk || 'high',
    description: rule?.description || '',
    roles_conflict: rule?.roles_conflict || [],
    mitigated_by_workflow_id: rule?.mitigated_by_workflow_id || '',
  })

  const camposB = useErroresDeCampo()
  const msgB = (k: string) => camposB.de(k) ? <div className="u-field-error">{camposB.de(k)}</div> : null
  const { mutate, isPending } = useMutation({
    onMutate: () => camposB.limpiar(),
    mutationFn: (d: typeof form) => isEdit ? grcApi.updateSodRule(rule!.id, d) : grcApi.createSodRule(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['grc-sod-rules'] }); qc.invalidateQueries({ queryKey: ['grc-sod-check'] }); onClose() },
    onError: (e: unknown) => { if (!camposB.recoger(e)) toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) },
  })

  const toggleRole = (r: string) => setForm(f => ({
    ...f,
    roles_conflict: f.roles_conflict.includes(r) ? f.roles_conflict.filter((x: string) => x !== r) : [...f.roles_conflict, r],
  }))

  return (
    <Modal open title={isEdit ? t('grc.edit_sod_rule') : t('grc.new_sod_rule')} onClose={onClose} width={580}>
      <div className="u-stack-14">
        <div className="grc-card">
          {t('grc.sod_rule_desc1')} <strong className="u-text1">{t('grc.sod_rule_desc2')}</strong>. {t('grc.sod_rule_desc3')}
        </div>

        <div className="grc-grid">
          <div>
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="grc-page-e18">{t('grc.module_a')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-1`} value={form.module_a} onChange={e => { camposB.limpiar('module_a'); setForm(f => ({ ...f, module_a: e.target.value })) }} className="grc-page-e19">
              {MODULES.map(m => <option key={m.id} value={m.id}>{m.label}</option>)}
            </Select>{msgB('module_a')}
          </div>
          <div>
            <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="grc-page-e18">{t('grc.action_a')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-2`} value={form.action_a} onChange={e => { camposB.limpiar('action_a'); setForm(f => ({ ...f, action_a: e.target.value })) }} className="grc-page-e19">
              {acciones.map(a => <option key={a} value={a}>{accionDe(t)(a)}</option>)}
            </Select>{msgB('action_a')}
          </div>
        </div>
        <div className="grc-box">{traducir('grc.en_conflicto_con')}</div>
        <div className="grc-grid-2">
          <div>
            <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="grc-page-e18">{t('grc.module_b')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-3`} value={form.module_b} onChange={e => { camposB.limpiar('module_b'); setForm(f => ({ ...f, module_b: e.target.value })) }} className="grc-page-e19">
              {MODULES.map(m => <option key={m.id} value={m.id}>{m.label}</option>)}
            </Select>{msgB('module_b')}
          </div>
          <div>
            <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="grc-page-e18">{t('grc.action_b')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-4`} value={form.action_b} onChange={e => { camposB.limpiar('action_b'); setForm(f => ({ ...f, action_b: e.target.value })) }} className="grc-page-e19">
              {acciones.map(a => <option key={a} value={a}>{accionDe(t)(a)}</option>)}
            </Select>{msgB('action_b')}
          </div>
        </div>

        <div className="u-grid2-10">
          <div>
            <label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="grc-page-e18">{t('grc.risk_level')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-5`} value={form.risk} onChange={e => { camposB.limpiar('risk'); setForm(f => ({ ...f, risk: e.target.value })) }} className="grc-page-e19">
              {RIESGOS.map(r => <option key={r} value={r}>{t(`grc.riesgo_${r}`)}</option>)}
            </Select>{msgB('risk')}
          </div>
          <div>
            <label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} className="grc-page-e18">{t('grc.mitigation_flow')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-6`} value={form.mitigated_by_workflow_id || ''} onChange={e => { camposB.limpiar('mitigated_by_workflow_id'); setForm(f => ({ ...f, mitigated_by_workflow_id: e.target.value })) }} className="grc-page-e19">
              <option value="">{t('grc.no_mitigation')}</option>
              {(workflows || []).map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
            </Select>{msgB('mitigated_by_workflow_id')}
          </div>
        </div>

        <div>
          <label className="grc-page-e18">{t('grc.risk_description')}</label>
          <Input value={form.description} onChange={e => { camposB.limpiar('description'); setForm(f => ({ ...f, description: e.target.value })) }} placeholder={traducir('grc.descripcion_de_la_regla_sod')} aria-label={traducir('grc.descripcion_de_la_regla_sod')} inputClassName="grc-page-e19" />{msgB('description')}
        </div>

        <div>
          <label className="grc-page-e18">{t('grc.conflicting_roles')}</label>
          <div className="grc-row-6">
            {rolesDeLaMatriz.map(r => (
              <Button key={r.id} size="sm" variant={form.roles_conflict.includes(r.id) ? 'primary' : 'secondary'}
                icon={form.roles_conflict.includes(r.id) ? <Check size={13} /> : undefined} onClick={() => toggleRole(r.id)}>
                {r.label}
              </Button>
            ))}
          </div>
        </div>

        <div className="u-actions-10">
          <Button variant="secondary" onClick={onClose}>{t('grc.cancel')}</Button>
          <Button onClick={() => mutate({ ...form, mitigated_by_workflow_id: form.mitigated_by_workflow_id || null })} loading={isPending} disabled={isPending || !form.description}>
            {isPending ? t('grc.saving') : isEdit ? t('grc.save_changes') : t('grc.create_rule')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export function SodTab({ roles }: { roles: Role[] }) {
  const traducir = useAppT()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [showModal, setShowModal] = useState(false)
  const [editingRule, setEditingRule] = useState<SodRule | null>(null)

  const { data: rules = [], isLoading } = useQuery<SodRule[]>({
    queryKey: ['grc-sod-rules'],
    queryFn: () => grcApi.sodRules().then(r => r.data),
  })
  const { data: checkData } = useQuery<{ violations: SodViolation[]; not_evaluable_rule_ids?: string[] }>({
    queryKey: ['grc-sod-check'],
    queryFn: () => grcApi.sodCheck().then(r => r.data),
    staleTime: STALE_SHORT_MS,
  })
  const { data: workflows = [] } = useQuery<Workflow[]>({
    queryKey: ['approval-workflows-grc'],
    queryFn: () => approvalsApi.listWorkflows(undefined).then(r => r.data),
  })

  const { mutate: del } = useMutation({
    mutationFn: (id: string) => grcApi.deleteSodRule(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['grc-sod-rules'] }); qc.invalidateQueries({ queryKey: ['grc-sod-check'] }) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: toggle } = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) => grcApi.updateSodRule(id, { is_active: active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['grc-sod-rules'] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const violations = checkData?.violations || []
  const criticalCount = violations.filter((v: SodViolation) => v.risk === 'critical').length

  return (
    <div>
      <div className="ds-grid-stats grc-mb">
        <KpiCard icon={<ShieldCheck size={14} />} label={t('grc.active_sod_rules')} value={rules.filter((r: SodRule) => r.is_active).length} />
        <KpiCard icon={<Search size={14} />} label={t('grc.detected_conflicts')} value={violations.length} warning={violations.length > 0} />
        <KpiCard icon={<ShieldAlert size={14} />} label={t('grc.critical_conflicts')} value={criticalCount} danger={criticalCount > 0} />
      </div>

      {violations.length > 0 && (
        <div className="grc-card-2">
          <div className="grc-box-5"><AlertOctagon size={15} aria-hidden /> {t('grc.sod_conflicts_detected')}</div>
          <div className="u-stack-6">
            {violations.map((v: SodViolation, i: number) => (
              <div key={i} className="grc-row-7">
                <span className="grc-label-5 grc-page-e6" style={{ '--grc-page-background': alpha(RISK_COLOR[v.risk || ''], '20'), '--grc-page-color': RISK_COLOR[v.risk || ''] } as CSSProperties}>{t(`grc.riesgo_${v.risk}`)}</span>
                <span className="u-text1"><strong>{roles.find(r => r.id === v.conflicting_role)?.label || v.conflicting_role}</strong> {t('grc.can')} {accionDe(t)(v.action_a)} <em>{moduleInfo(t)(v.module_a).label}</em> {t('grc.and')} {accionDe(t)(v.action_b)} <em>{moduleInfo(t)(v.module_b).label}</em></span>
                {v.mitigated && <StatusBadge kind="success" caps={false}>{t('grc.mitigated')}</StatusBadge>}
              </div>
            ))}
          </div>
        </div>
      )}

      {(checkData?.not_evaluable_rule_ids?.length ?? 0) > 0 && (
        <div className="u-text3-sm">{t('grc.sod_no_evaluables', { n: checkData?.not_evaluable_rule_ids?.length ?? 0 })}</div>
      )}

      <div className="grc-row-8">
        <Button icon={<Plus size={14} />} onClick={() => setShowModal(true)}>{t('grc.new_sod_rule')}</Button>
      </div>

      {isLoading ? <Spinner /> : rules.length === 0 ? (
        <EmptyState icon={<ShieldCheck size={28} />} title={traducir('grc.sin_reglas_sod')} description={t('pagina_grc.crea_reglas_para_detectar_conflictos_de')}
          action={<Button icon={<Plus size={14} />} onClick={() => setShowModal(true)}>{t('grc.new_sod_rule')}</Button>} />
      ) : (
        <div className="u-stack-10">
          {rules.map((rule: SodRule) => {
            const rc = RISK_COLOR[rule.risk || ''] || 'var(--text-3)'
            const modA = moduleInfo(t)(rule.module_a)
            const modB = moduleInfo(t)(rule.module_b)
            return (
              <div key={rule.id} className={`grc-page-e7 ${rule.is_active ? 'grc-page-m8' : 'grc-page-m9'}`} style={{ '--grc-page-border-left': `4px solid ${rc}` } as CSSProperties}>
                <div className="grc-row-9">
                  <div className="u-wrap-center-8">
                    <span className="grc-label-6 grc-page-e6" style={{ '--grc-page-background': alpha(rc, '20'), '--grc-page-color': rc } as CSSProperties}>{t(`grc.riesgo_${rule.risk}`)}</span>
                    <span className="u-text1-base-600">{modA?.label} · {accionDe(t)(rule.action_a)}</span>
                    <span className="u-text3-sm">{traducir('grc.conflicto_con')}</span>
                    <span className="u-text1-base-600">{modB?.label} · {accionDe(t)(rule.action_b)}</span>
                    {rule.mitigated_by_workflow_id && <span className="grc-card-4">{t('pagina_grc.mitigado')}</span>}
                    {!rule.is_active && <span className="grc-card-5">{t('pagina_grc.inactiva')}</span>}
                    {checkData?.not_evaluable_rule_ids?.includes(rule.id) && <span className="grc-card-5">{t('grc.sod_no_evaluable')}</span>}
                  </div>
                  <div className="u-row-6">
                    <IconButton onClick={() => toggle({ id: rule.id, active: !rule.is_active })}
                      ariaLabel={rule.is_active ? t('pagina_grc.desactivar_regla_sod') : t('pagina_grc.activar_regla_sod')}>
                      {rule.is_active ? <Pause size={14} /> : <Play size={14} />}
                    </IconButton>
                    <IconButton variante="caja" onClick={() => setEditingRule(rule)} ariaLabel={t('pagina_grc.editar_regla_sod')}>
                      <Pencil size={14} />
                    </IconButton>
                    <IconButton variante="caja" tono="peligro" onClick={() => { openConfirmGlobal({ message: t('pagina_grc.eliminar_esta_regla_sod'), onConfirm: () => del(rule.id), danger: true }) }}
                      ariaLabel={t('pagina_grc.eliminar_regla_sod')}>
                      <Trash2 size={14} />
                    </IconButton>
                  </div>
                </div>
                <div className={`u-text2-sm ${(rule.roles_conflict?.length ?? 0) > 0 ? 'grcpage-sx8' : 'grcpage-sx9'}`}>{rule.description}</div>
                {(rule.roles_conflict?.length ?? 0) > 0 && (
                  <div className="grc-row-10">
                    <span className="u-text3-xs">{traducir('grc.roles_con_conflicto')}</span>
                    {rule.roles_conflict?.map((r: string) => {
                      const role = roles.find((x: Role) => x.id === r)
                      return role ? <span key={r} className="grc-label-7 grc-page-e6" style={{ '--grc-page-background': alpha(role.color, '20'), '--grc-page-color': role.color } as CSSProperties}>{role.label}</span> : <span key={r} className="grc-card-6">{r}</span>
                    })}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {(showModal || editingRule) && (
        <SodRuleModal rule={editingRule} workflows={workflows} roles={roles} onClose={() => { setShowModal(false); setEditingRule(null) }} />
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// 3. VIOLACIONES SoD
// ═══════════════════════════════════════════════════════════════════════════════
export function ViolationsTab({ roles }: { roles: Role[] }) {
  const { t } = useAppLang()
  const traducir = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [filter, setFilter] = useState<boolean | null>(false)

  const { data: violations = [], isLoading, refetch } = useQuery<ViolationRecord[]>({
    queryKey: ['grc-violations', filter],
    queryFn: () => grcApi.violations(filter === null ? {} : { resolved: filter }).then(r => r.data),
    refetchInterval: POLL_DEFAULT_MS,
  })

  const { mutate: resolve } = useMutation({
    mutationFn: ({ id, note }: { id: string; note: string }) => grcApi.resolveViolation(id, { resolution_note: note }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['grc-violations'] }); toast.success(t('pagina_grc.violacion_marcada_como_resuelta')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  return (
    <div>
      <div className="grc-card-7">
        <strong className="u-danger">{t('pagina_grc.violaciones_sod_en_tiempo_real')}</strong> {traducir('grc.registradas_cuando_el_mismo_usuario_intenta_realizar')}
      </div>

      <div className="grc-row-11">
        {([[false, t('pagina_grc.pendientes')], [null, t('pagina_grc.todas')], [true, t('pagina_grc.resueltas')]] as [boolean | null, string][]).map(([val, label]) => (
          <Button key={String(val)} size="sm" variant={filter === val ? 'primary' : 'secondary'} onClick={() => setFilter(val)}>
            {label}
          </Button>
        ))}
        <IconButton onClick={() => refetch()} ariaLabel={t('pagina_grc.refrescar_violaciones_sod')}><RefreshCw size={14} /></IconButton>
      </div>

      {isLoading ? <Spinner /> : violations.length === 0 ? (
        <EmptyState icon={filter === false ? <CheckCircle2 size={28} /> : <Search size={28} />} title={filter === false ? t('pagina_grc.sin_violaciones_pendientes') : t('pagina_grc.sin_violaciones_registradas')} description={filter === false ? t('pagina_grc.no_hay_violaciones_sod_pendientes_de') : t('pagina_grc.no_hay_violaciones_registradas')} />
      ) : (
        <div className="u-stack-10">
          {violations.map(v => (
            <div key={v.id} className="grc-page-e10" style={{ '--grc-page-border-left': `3px solid ${v.resolved ? 'var(--success)' : 'var(--danger)'}` } as CSSProperties}>
              <div className="grc-row-12">
                <div>
                  <div className="grc-row-13">
                    <span className={`u-sm-700 ${v.resolved ? 'grcpage-sx10' : 'grcpage-sx11'}`}>{v.resolved ? t('pagina_grc.resuelta') : t('pagina_grc.pendiente')}</span>
                    {v.role && <span className="grc-card-8">{roles.find(r => r.id === v.role)?.label || v.role}</span>}
                  </div>
                  <div className="grc-box-6">
                    {t('pagina_grc.usuario')}{' '}<strong>{v.user_name || v.user_id || '—'}</strong>{' '}{t('pagina_grc.contexto')}{' '}{v.context_type === 'approval_request' ? t('pagina_grc.aprobaciones') : moduleInfo(traducir)(v.context_type || '').label} ({v.context_id})
                  </div>
                  <div className="u-text3-xs-mt2">{t('pagina_grc.detectada')}{' '}{fmtDateTime(v.detected_at)}</div>
                  {v.resolution_note && <div className="grc-box-7">{traducir('grc.resolucion')} {v.resolution_note}</div>}
                </div>
                {!v.resolved && (
                  <Button size="sm" variant="secondary" icon={<Check size={14} />} onClick={async () => {
                    const note = await pedirTexto({ title: t('pagina_grc.resolver_violacion'), message: t('pagina_grc.puedes_anadir_una_nota_de_resolucion'), label: t('pagina_grc.nota_de_resolucion_opcional'), multiline: true, confirmLabel: t('pagina_grc.resolver') })
                    if (note === null) return
                    resolve({ id: v.id, note })
                  }}>
                    {t('pagina_grc.resolver_2')}
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/**
 * Pestaña de flujos y plantillas de aprobación.
 * Troceado de ApprovalsPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import { useId, useState } from 'react'
import { extractErr } from '../../utils/helpers'
import { useToast } from '../../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { approvalsApi } from '../../services/api'
import { settingsApi } from '../../services/settingsApi'
import { Trash2, Sparkles, Plus } from 'lucide-react'
import { Button, Modal, EmptyState, Select, Checkbox, Input } from '../../components/ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useRolesReales } from '../../hooks/useRolesReales'
import { CATEGORIAS_DE_DOCUMENTO, entityLabels, type WorkflowTemplate } from './compartido'

// ── Plantillas y creación desde cero ─────────────────────────────────────────
type PasoBorrador = {
  name: string; approver_type: string; approver_role: string; approver_department: string
  timeout_hours: number | string; on_timeout: string; is_optional: boolean
}

const pasoNuevo = (name: string): PasoBorrador => ({
  name, approver_type: 'role', approver_role: 'pm', approver_department: '', timeout_hours: 48, on_timeout: 'escalate', is_optional: false,
})

export function WorkflowTemplatesTab() {
  const t = useAppT()
  // 19-11-2026: roles reales del backend (`GET /auth/roles`); la lista local tenía roles inexistentes.
  const roles = useRolesReales({ soloInternos: true })
  const toast = useToast()
  const idPrefix = useId()
  const qc = useQueryClient()
  const borradorVacio = () => ({
    name: '', description: '', entity_type: 'document', is_default: false, document_category: '',
    steps: [pasoNuevo(t('approvals.aprobacion_inicial'))],
  })
  const [showCreateScratch, setShowCreateScratch] = useState(false)
  const [scratch, setScratch] = useState(borradorVacio)

  const { data: templates = [], isLoading } = useQuery<WorkflowTemplate[]>({
    queryKey: ['approval-workflow-templates'],
    queryFn: () => approvalsApi.listTemplates().then(r => r.data || []),
  })
  const { data: depts = [] } = useQuery({
    queryKey: ['departments-select'],
    queryFn: () => settingsApi.getDepartments().then(r => r.data),
  })
  const { mutate: createFromTemplate, isPending } = useMutation({
    mutationFn: (payload: { template_id: string }) => approvalsApi.createFromTemplate(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['approval-workflows'] })
      toast.success(t('approvals.flujo_creado_plantilla'))
    },
    onError: e => toast.error(extractErr(e, t('approvals.error_crear_plantilla'))),
  })

  const { mutate: createScratchWorkflow, isPending: isCreatingScratch } = useMutation({
    mutationFn: async (payload: typeof scratch) => {
      const triggerConditions = payload.entity_type === 'document' && payload.document_category
        ? JSON.stringify({ category: payload.document_category })
        : '{}'

      const created = await approvalsApi.createWorkflow({
        name: payload.name,
        description: payload.description || null,
        entity_type: payload.entity_type,
        is_default: !!payload.is_default,
        trigger_conditions: triggerConditions,
      })

      const workflowId = created?.data?.id
      const normalizedSteps = (payload.steps || [])
        .filter(s => (s.name || '').trim())
        .map((s, idx) => ({
          step_order: idx + 1,
          name: s.name.trim(),
          approver_type: s.approver_type,
          approver_role: s.approver_type === 'role' ? (s.approver_role || null) : null,
          approver_department: s.approver_type === 'any_in_department' ? (s.approver_department || null) : null,
          timeout_hours: Number(s.timeout_hours || 48),
          on_timeout: s.on_timeout || 'escalate',
          is_optional: !!s.is_optional,
        }))

      for (const step of normalizedSteps) {
        await approvalsApi.addStep(workflowId, step)
      }

      return created
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['approval-workflows'] })
      setShowCreateScratch(false)
      setScratch(borradorVacio())
      toast.success(t('approvals.flujo_creado_cero'))
    },
    onError: e => toast.error(extractErr(e, t('approvals.error_crear_cero'))),
  })

  const addScratchStep = () => setScratch(s => ({ ...s, steps: [...s.steps, pasoNuevo(t('approvals.paso_n_nombre', { n: s.steps.length + 1 }))] }))
  const updateScratchStep = (index: number, field: keyof PasoBorrador, value: string) => {
    setScratch(s => ({ ...s, steps: s.steps.map((step, idx) => (idx === index ? { ...step, [field]: value } : step)) }))
  }
  const removeScratchStep = (index: number) => setScratch(s => ({ ...s, steps: s.steps.filter((_, idx) => idx !== index) }))

  const canCreateScratch = (scratch.name || '').trim().length > 0 && (scratch.steps || []).some(s => (s.name || '').trim().length > 0)
  const id = (k: string) => `${idPrefix}-${k}`

  return (
    <>
      <div className="apv-fin apv-fin--12">
        <Button icon={<Plus size={14} />} onClick={() => setShowCreateScratch(true)}>{t('approvals.crear_desde_cero')}</Button>
      </div>

      {isLoading && <div className="apv-cargando apv-cargando--compacto" role="status">{t('approvals.cargando_plantillas')}</div>}

      {!isLoading && !templates.length && (
        <div className="ds-card">
          <EmptyState icon={<Sparkles size={28} />} title={t('approvals.sin_plantillas')} description={t('approvals.no_hay_plantillas')}
            action={<Button icon={<Plus size={14} />} onClick={() => setShowCreateScratch(true)}>{t('approvals.crear_desde_cero')}</Button>} />
        </div>
      )}

      {!isLoading && templates.length > 0 && (
        <div className="apv-rejilla-tarjetas">
          {templates.map(tpl => (
            <div key={tpl.id} className="ds-card apv-tarjeta">
              <div className="apv-tarjeta__titulo">{tpl.name}</div>
              <div className="apv-tarjeta__texto">{tpl.description || t('approvals.plantilla_lista')}</div>
              <div className="apv-tarjeta__nota">{t('approvals.plantilla_resumen', { entidad: entityLabels(t)[tpl.entity_type]?.label ?? tpl.entity_type, n: (tpl.steps || []).length })}</div>
              <Button size="sm" onClick={() => createFromTemplate({ template_id: tpl.id })} loading={isPending}>{t('approvals.usar_plantilla')}</Button>
            </div>
          ))}
        </div>
      )}

      {showCreateScratch && (
        <Modal open title={t('approvals.crear_flujo_desde_cero')} onClose={() => setShowCreateScratch(false)} width={760}>
          <div className="apv-rejilla-2">
            <div>
              <label htmlFor={id('scratch-name')} className="apv-label">{t('approvals.nombre')}</label>
              <Input id={id('scratch-name')} value={scratch.name} onChange={e => setScratch(s => ({ ...s, name: e.target.value }))} placeholder={t('approvals.nombre_ejemplo')} inputClassName="apv-input" />
            </div>
            <div>
              <label htmlFor={id('scratch-entity')} className="apv-label">{t('approvals.entidad')}</label>
              <Select suelto placeholder={false} id={id('scratch-entity')} value={scratch.entity_type} onChange={e => setScratch(s => ({ ...s, entity_type: e.target.value }))} className="apv-input">
                {Object.entries(entityLabels(t)).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
              </Select>
            </div>
            {scratch.entity_type === 'document' && (
              <div className="u-col-full">
                <label htmlFor={id('scratch-category')} className="apv-label">{t('approvals.categoria_documento_opcional')}</label>
                <Select suelto placeholder={false} id={id('scratch-category')} value={scratch.document_category} onChange={e => setScratch(s => ({ ...s, document_category: e.target.value }))} className="apv-input">
                  <option value="">{t('approvals.fallback_aplica_a_todos_los_documentos')}</option>
                  {CATEGORIAS_DE_DOCUMENTO.map(c => <option key={c} value={c}>{t(`approvals.doc_cat_${c}`, c)}</option>)}
                </Select>
              </div>
            )}
            <div className="u-col-full">
              <label htmlFor={id('scratch-description')} className="apv-label">{t('approvals.description')}</label>
              <Input id={id('scratch-description')} value={scratch.description} onChange={e => setScratch(s => ({ ...s, description: e.target.value }))} placeholder={t('approvals.descripcion_ejemplo')} inputClassName="apv-input" />
            </div>
            <label htmlFor={id('scratch-default')} className="apv-check apv-check--fila">
              <Checkbox id={id('scratch-default')} checked={scratch.is_default} onChange={(_, e) => setScratch(s => ({ ...s, is_default: e.target.checked }))} />
              {t('approvals.marcar_como_flujo_por_defecto')}
            </label>
          </div>

          <div className="apv-pasos-cabecera">
            <div className="u-sm-700">{t('approvals.pasos_de_aprobacion')}</div>
            <Button size="sm" variant="secondary" icon={<Plus size={14} />} onClick={addScratchStep}>{t('approvals.add_step')}</Button>
          </div>

          <div className="apv-pasos-lista">
            {scratch.steps.map((step, idx) => (
              <div key={idx} className="apv-paso-borrador">
                <div className="apv-paso-borrador__fila">
                  <div>
                    <label htmlFor={id(`step-name-${idx}`)} className="apv-label">{t('approvals.paso_n_nombre', { n: idx + 1 })}</label>
                    <Input id={id(`step-name-${idx}`)} value={step.name} onChange={e => updateScratchStep(idx, 'name', e.target.value)} placeholder={t('approvals.nombre_del_paso')} inputClassName="apv-input" />
                  </div>
                  <div>
                    <label htmlFor={id(`step-type-${idx}`)} className="apv-label">{t('approvals.aprobador')}</label>
                    <Select suelto placeholder={false} id={id(`step-type-${idx}`)} value={step.approver_type} onChange={e => updateScratchStep(idx, 'approver_type', e.target.value)} className="apv-input">
                      <option value="role">{t('approvals.approver_role')}</option>
                      <option value="manager">{t('approvals.approver_manager')}</option>
                      <option value="any_in_department">{t('approvals.department')}</option>
                    </Select>
                  </div>
                  <div>
                    <label htmlFor={id(`step-timeout-${idx}`)} className="apv-label">{t('approvals.timeout_hours')}</label>
                    <Input id={id(`step-timeout-${idx}`)} type="number" min="1" value={step.timeout_hours} onChange={e => updateScratchStep(idx, 'timeout_hours', e.target.value)} inputClassName="apv-input" />
                  </div>
                  <div>
                    <label htmlFor={id(`step-ontimeout-${idx}`)} className="apv-label">{t('approvals.on_timeout')}</label>
                    <Select suelto placeholder={false} id={id(`step-ontimeout-${idx}`)} value={step.on_timeout} onChange={e => updateScratchStep(idx, 'on_timeout', e.target.value)} className="apv-input">
                      <option value="escalate">{t('approvals.timeout_escalate')}</option>
                      <option value="auto_approve">{t('approvals.timeout_auto_approve')}</option>
                      <option value="reject">{t('approvals.timeout_reject')}</option>
                    </Select>
                  </div>
                  <Button size="sm" variant="ghost" icon={<Trash2 size={14} />} onClick={() => removeScratchStep(idx)} disabled={scratch.steps.length === 1}>{t('approvals.eliminar')}</Button>
                </div>

                {step.approver_type === 'role' && (
                  <div className="apv-mt-8">
                    <label htmlFor={id(`step-role-${idx}`)} className="apv-label">{t('approvals.required_role')}</label>
                    <Select suelto placeholder={false} id={id(`step-role-${idx}`)} value={step.approver_role || ''} onChange={e => updateScratchStep(idx, 'approver_role', e.target.value)} className="apv-input">
                      <option value="">{t('approvals.select_role')}</option>
                      {roles.map(r => <option key={r.id} value={r.id}>{r.etiqueta}</option>)}
                    </Select>
                  </div>
                )}

                {step.approver_type === 'any_in_department' && (
                  <div className="apv-mt-8">
                    <label htmlFor={id(`step-dept-${idx}`)} className="apv-label">{t('approvals.department')}</label>
                    <Select suelto placeholder={false} id={id(`step-dept-${idx}`)} value={step.approver_department || ''} onChange={e => updateScratchStep(idx, 'approver_department', e.target.value)} className="apv-input">
                      <option value="">{t('approvals.sin_departamento')}</option>
                      {depts.filter(d => d.is_active !== false).map(d => <option key={d.id} value={d.name}>{d.name}</option>)}
                    </Select>
                  </div>
                )}
              </div>
            ))}
          </div>

          <div className="apv-acciones">
            <Button variant="secondary" onClick={() => setShowCreateScratch(false)}>{t('common.cancel')}</Button>
            <Button onClick={() => createScratchWorkflow(scratch)} loading={isCreatingScratch} disabled={!canCreateScratch}>{t('approvals.create_workflow')}</Button>
          </div>
        </Modal>
      )}
    </>
  )
}

/**
 * Aprobaciones: bandeja (/approvals) y configuración de flujos (/settings/approval-workflows).
 *
 * Fase 2 (rev. 166): estilos en ApprovalsPage.css (los colores que son datos —entidad,
 * paso, porcentajes— llegan como propiedades personalizadas), todos los textos por i18n
 * (`approvals.*`) y, en vez de JSON escrito a mano, la condición de un paso y las reglas
 * de auto-aprobación se editan con controles (`components/aprobaciones/CondicionesSimples`).
 */
import { type CSSProperties, type MouseEvent, useId, useState } from 'react'
import { EditorDeReglasDeAutoaprobacion } from '../components/aprobaciones/CondicionesSimples'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useAuth } from '../context/AuthContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { approvalsApi } from '../services/api'
import { CheckCircle, CheckCircle2, Info, Trash2, Clock as ClockIcon, Workflow, Plus, X } from 'lucide-react'
import { Button, Modal, EmptyState, Tabs, Page, KpiCard, IconButton, StatusBadge, Select, Checkbox, Input } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'
import {
  type ApprovalStats,
  type ApprovalWorkflow,
  CATEGORIAS_DE_DOCUMENTO,
  ENTIDADES,
  type EntityConfig,
  entityLabels,
} from './aprobaciones/compartido'
import { WorkflowDetail } from './aprobaciones/PasosYDetalle'
import { MyPendingTab } from './aprobaciones/MisPendientes'
import { WorkflowTemplatesTab } from './aprobaciones/Plantillas'
import { WorkflowBottlenecksTab, WorkflowSimulatorTab } from './aprobaciones/SimuladorYCuellos'
import { ApprovalGroupsTab, ApprovalMatrixTab, ApproverLoadTab } from './aprobaciones/GruposYCarga'
import './ApprovalsPage.css'

// ── Página principal ──────────────────────────────────────────────────────────
interface ApprovalsPageProps {
  mode?: string
}

export default function ApprovalsPage({ mode = 'inbox' }: ApprovalsPageProps): JSX.Element {
  const createIdPrefix = useId()
  const t = useAppT()
  const { user, loading } = useAuth()
  const toast = useToast()
  const qc = useQueryClient()
  const isConfigMode = mode === 'config'
  const [tab, setTab]           = useState(isConfigMode ? 'workflows' : 'pending')
  const [selected, setSelected] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ name: '', description: '', entity_type: 'timesheet', is_default: false, document_category: '', chain_on_approval_workflow_id: '', sla_block_on_breach: false, auto_approval_rules: '' })
  const canQueryProtected = !loading && !!user

  const { data: workflows = [], isLoading } = useQuery<ApprovalWorkflow[]>({
    queryKey: ['approval-workflows'],
    queryFn: () => approvalsApi.listWorkflows(undefined).then(r => r.data),
    enabled: canQueryProtected && tab === 'workflows',
  })

  const { data: stats } = useQuery<ApprovalStats>({
    queryKey: ['approval-stats'],
    queryFn: () => approvalsApi.stats().then(r => r.data),
    enabled: canQueryProtected && tab === 'workflows',
  })

  const { mutate: create, isPending: creating } = useMutation({
    mutationFn: approvalsApi.createWorkflow,
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['approval-workflows'] })
      setShowCreate(false)
      setSelected(res.data.id)
      toast.success(t('approvals.workflow_created'))
    },
    onError: e => toast.error(extractErr(e, t('approvals.error_generic'))),
  })

  const { mutate: del } = useMutation({
    mutationFn: approvalsApi.deleteWorkflow,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['approval-workflows'] }); toast.success(t('approvals.workflow_deleted')) },
    onError: e => toast.error(extractErr(e, t('approvals.error_generic'))),
  })

  const runValidate = async (e: MouseEvent, workflowId: string) => {
    e.stopPropagation()
    try {
      const res = await approvalsApi.validateWorkflow(workflowId)
      if (res.data?.valid) {
        toast.success(t('approvals.flujo_valido'))
      } else {
        toast.error(t('approvals.flujo_no_valido', { motivos: (res.data?.issues || []).join(' | ') || t('approvals.revisar_configuracion') }))
      }
    } catch (err) {
      toast.error(extractErr(err, t('approvals.error_validar')))
    }
  }

  const runPublish = async (e: MouseEvent, workflowId: string) => {
    e.stopPropagation()
    try {
      await approvalsApi.publishWorkflow(workflowId)
      qc.invalidateQueries({ queryKey: ['approval-workflows'] })
      toast.success(t('approvals.flujo_publicado'))
    } catch (err) {
      toast.error(extractErr(err, t('approvals.error_publicar')))
    }
  }

  const runClone = async (e: MouseEvent, workflowId: string) => {
    e.stopPropagation()
    try {
      await approvalsApi.cloneVersion(workflowId, {})
      qc.invalidateQueries({ queryKey: ['approval-workflows'] })
      toast.success(t('approvals.version_clonada'))
    } catch (err) {
      toast.error(extractErr(err, t('approvals.error_clonar')))
    }
  }

  const tituloDePagina = isConfigMode ? t('approvals.page_title_config') : t('nav.approvals')
  const subtituloDePagina = isConfigMode ? t('approvals.page_subtitle_config') : t('approvals.page_subtitle_inbox')
  if (selected) return (
    <Page icon={<CheckCircle size={18} />} title={tituloDePagina} subtitle={subtituloDePagina}>
      <WorkflowDetail workflowId={selected} onBack={() => setSelected(null)} />
    </Page>
  )

  const tarjetaDeFlujo = (wf: ApprovalWorkflow, cfg: EntityConfig) => (
    <div key={wf.id}
      role="button"
      tabIndex={0}
      onClick={() => setSelected(wf.id)}
      onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelected(wf.id) } }}
      aria-label={t('approvals.workflow_open_aria', { name: wf.name })}
      className={`apv-flujo${wf.is_active ? '' : ' apv-flujo--inactivo'}`}
      style={{ '--apv-color': cfg.color, '--apv-borde': wf.is_active ? `color-mix(in srgb, ${cfg.color} 19%, transparent)` : undefined,
        '--apv-borde-activo': `color-mix(in srgb, ${cfg.color} 38%, transparent)` } as CSSProperties}
    >
      <div className="apv-flujo__cabecera">
        <div className="u-row-center-8">
          <span className="apv-flujo__icono" aria-hidden>{cfg.icon}</span>
          <div>
            <div className="u-md-700">{wf.name}</div>
            <div className="apv-flujo__entidad apv-color">{cfg.label}</div>
          </div>
        </div>
        <div className="apv-flujo__insignias">
          {wf.is_default && <StatusBadge kind="accent" caps={false}>{t('approvals.default_badge')}</StatusBadge>}
          {!wf.is_active && <StatusBadge kind="danger" caps={false}>{t('approvals.inactive_badge')}</StatusBadge>}
        </div>
      </div>
      <div className="apv-flujo__texto">
        {/* 23-11-2026 (B1 del 04b): singular/plural con su clave; el sufijo vacío en zh caía al inglés («3 步s»). */}
        {t(wf.step_count === 1 ? 'approvals.pasos_uno' : 'approvals.pasos_varios', { count: wf.step_count })}
        {wf.description && ` · ${wf.description}`}
      </div>
      <div className="apv-flujo__acciones">
        <Button size="xs" variant="secondary" onClick={(e) => { void runValidate(e as MouseEvent, wf.id) }}>{t('approvals.validar')}</Button>
        <Button size="xs" variant="secondary" onClick={(e) => { void runPublish(e as MouseEvent, wf.id) }}>{t('approvals.publicar')}</Button>
        <Button size="xs" variant="secondary" onClick={(e) => { void runClone(e as MouseEvent, wf.id) }}>{t('approvals.clonar_version')}</Button>
        <IconButton ariaLabel={t('approvals.workflow_delete_aria', { name: wf.name })}
          onClick={e => { e.stopPropagation(); openConfirmGlobal({ message: t('approvals.workflow_delete_confirm', { name: wf.name }), onConfirm: () => del(wf.id), danger: true }) }}>
          <Trash2 size={14} aria-hidden />
        </IconButton>
      </div>
    </div>
  )

  return (
    <Page
      icon={<CheckCircle size={18} />}
      title={tituloDePagina}
      subtitle={subtituloDePagina}
      rightActions={isConfigMode && tab === 'workflows'
        ? <Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{t('approvals.new_workflow')}</Button>
        : undefined}
    >
      <div className="ds-card--inset apv-info">
        <Info size={14} aria-hidden className="apv-info__icono" />
        <div className="u-text2-sm">
          {isConfigMode ? t('approvals.info_config') : t('approvals.info_inbox')}
        </div>
      </div>

      {stats && tab === 'workflows' && (
        <div className="ds-grid-stats">
          <KpiCard icon={<ClockIcon size={16} />} label={t('approvals.pending')} value={stats.pending} warning={stats.pending > 0} />
          <KpiCard icon={<CheckCircle2 size={16} />} label={t('approvals.approved')} value={stats.approved} />
          <KpiCard icon={<X size={16} />} label={t('approvals.rejected')} value={stats.rejected} />
          <KpiCard icon={<Workflow size={16} />} label={t('approvals.active_flows')} value={workflows.filter(w => w.is_active).length} accent />
        </div>
      )}

      {/* La bandeja solo tiene una sección: sin barra de pestañas. */}
      {isConfigMode && (
        <div className="apv-pestanas">
          <Tabs
            items={[
              { id: 'workflows',   label: t('approvals.tab_workflows') },
              { id: 'templates',   label: t('approvals.tab_plantillas') },
              { id: 'simulator',   label: t('approvals.tab_simulador') },
              { id: 'bottlenecks', label: t('approvals.tab_cuellos') },
              { id: 'groups',      label: t('approvals.tab_grupos') },
              { id: 'load',        label: t('approvals.tab_carga') },
              { id: 'matrix',      label: t('approvals.tab_matriz') },
            ]}
            active={tab}
            onChange={setTab}
            ariaLabel={t('approvals.sections_aria')}
          />
        </div>
      )}

      {tab === 'pending' && <MyPendingTab />}

      {tab === 'workflows' && (
        <div id="approvals-panel-workflows" role="tabpanel" aria-labelledby="approvals-tab-workflows">
          {isLoading ? (
            <div className="apv-cargando" role="status">{t('approvals.loading')}</div>
          ) : workflows.length === 0 ? (
            <div className="ds-card">
              <EmptyState icon={<Workflow size={28} />} title={t('approvals.no_workflows')}
                description={t('approvals.workflows_description')}
                action={<Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{t('approvals.new_workflow')}</Button>} />
            </div>
          ) : (
            <div data-export-table="approvals-export" className="apv-rejilla-tarjetas apv-rejilla-tarjetas--300">
              {Object.entries(entityLabels(t)).flatMap(([entityType, cfg]) =>
                workflows.filter(w => w.entity_type === entityType).map(wf => tarjetaDeFlujo(wf, cfg)))}
              {workflows.filter(w => !Object.keys(ENTIDADES).includes(w.entity_type)).map(wf => (
                <div key={wf.id} role="button" tabIndex={0} onClick={() => setSelected(wf.id)} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelected(wf.id) } }} aria-label={t('approvals.workflow_open_aria', { name: wf.name })}
                  className="apv-flujo">
                  <div className="u-md-700">{wf.name}</div>
                  <div className="u-text2-xs">{t(`approvals.entity_${wf.entity_type}`, wf.entity_type)} · {wf.step_count} {t('approvals.steps_word')}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === 'templates' && isConfigMode && <WorkflowTemplatesTab />}
      {tab === 'simulator' && isConfigMode && <WorkflowSimulatorTab />}
      {tab === 'bottlenecks' && isConfigMode && <WorkflowBottlenecksTab />}
      {tab === 'groups' && isConfigMode && <ApprovalGroupsTab />}
      {tab === 'load' && isConfigMode && <ApproverLoadTab />}
      {tab === 'matrix' && isConfigMode && <ApprovalMatrixTab workflows={workflows} />}

      {showCreate && (
        <Modal open title={t('approvals.new_workflow_title')} onClose={() => setShowCreate(false)} width={560}>
          <div className="apv-columna">
            <div>
              <label htmlFor={`${createIdPrefix}-name`} className="apv-label">{t('approvals.name_required')}</label>
              <Input id={`${createIdPrefix}-name`} value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder={t('approvals.workflow_name_placeholder')} inputClassName="apv-input" />
            </div>
            <div>
              <label htmlFor={`${createIdPrefix}-entity-type`} className="apv-label">{t('approvals.entity_type')}</label>
              <Select suelto placeholder={false} id={`${createIdPrefix}-entity-type`} value={form.entity_type} onChange={e => setForm(f => ({ ...f, entity_type: e.target.value }))} className="apv-input">
                {Object.entries(entityLabels(t)).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
              </Select>
            </div>
            {form.entity_type === 'document' && (
              <div>
                <label htmlFor={`${createIdPrefix}-doc-category`} className="apv-label">{t('approvals.categoria_del_documento')}</label>
                <Select suelto placeholder={false} id={`${createIdPrefix}-doc-category`} value={form.document_category} onChange={e => setForm(f => ({ ...f, document_category: e.target.value }))} className="apv-input"
                  aria-describedby={`${createIdPrefix}-doc-category-ayuda`}>
                  <option value="">{t('approvals.fallback_aplica_a_todos_los_documentos')}</option>
                  {CATEGORIAS_DE_DOCUMENTO.map(c => <option key={c} value={c}>{t(`approvals.doc_cat_${c}`, c)}</option>)}
                </Select>
                <div id={`${createIdPrefix}-doc-category-ayuda`} className="apv-ayuda apv-ayuda--2xs">{t('approvals.si_no_se_especifica_categoria_este_flujo')}</div>
              </div>
            )}
            <div>
              <label htmlFor={`${createIdPrefix}-description`} className="apv-label">{t('approvals.description')}</label>
              <Input id={`${createIdPrefix}-description`} value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} placeholder={t('approvals.description_placeholder')} inputClassName="apv-input" />
            </div>
            <label htmlFor={`${createIdPrefix}-is-default`} className="apv-check">
              <Checkbox id={`${createIdPrefix}-is-default`} checked={form.is_default} onChange={(_, e) => setForm(f => ({ ...f, is_default: e.target.checked }))} />
              {t('approvals.default_flow_label')}
            </label>
            <div>
              <label htmlFor={`${createIdPrefix}-chain`} className="apv-label">{t('approvals.encadenar_con_flujo_al_aprobar_opcional')}</label>
              <Select suelto placeholder={false} id={`${createIdPrefix}-chain`} value={form.chain_on_approval_workflow_id}
                onChange={e => setForm(f => ({ ...f, chain_on_approval_workflow_id: e.target.value }))} className="apv-input">
                <option value="">{t('approvals.sin_encadenamiento')}</option>
                {workflows.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
              </Select>
            </div>
            <label htmlFor={`${createIdPrefix}-sla`} className="apv-check">
              <Checkbox id={`${createIdPrefix}-sla`} checked={form.sla_block_on_breach} onChange={(_, e) => setForm(f => ({ ...f, sla_block_on_breach: e.target.checked }))} />
              {t('approvals.bloquear_entidad_si_se_supera_el_sla')}
            </label>
            <fieldset className="ds-grupo-opciones apr-regla">
              <legend className="apv-label">{t('approvals.reglas_de_auto_aprobacion')}</legend>
              <EditorDeReglasDeAutoaprobacion raw={form.auto_approval_rules} onChange={raw => setForm(f => ({ ...f, auto_approval_rules: raw }))} />
            </fieldset>
          </div>
          <div className="u-actions-8">
            <Button variant="secondary" onClick={() => setShowCreate(false)}>{t('common.cancel')}</Button>
            <Button onClick={() => {
              const { document_category, ...rest } = form
              const trigger_conditions = (form.entity_type === 'document' && document_category)
                ? JSON.stringify({ category: document_category })
                : '{}'
              create({ ...rest, trigger_conditions })
            }} loading={creating} disabled={!form.name || creating}>{t('approvals.create_workflow')}</Button>
          </div>
        </Modal>
      )}
    </Page>
  )
}

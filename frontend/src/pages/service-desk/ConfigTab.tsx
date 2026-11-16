/**
 * 16-11-2026 (pasada de diseño): subpestañas con <Tabs>; botones del kit con
 * iconos lucide (sin «+» ni emojis en el texto); vacíos con icono lucide;
 * formularios con `ds-input`; insignias con StatusBadge/PBadge; los avisos y
 * etiquetas que reutilizaban textos de otra cosa (un aviso que decía «Nueva
 * categoría», «Nombre de la regla» como categoría) pasan a claves `sd_cfg.cfg_*`.
 */
import { useState, useId } from 'react'
import type { ChangeEvent } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { extractErr, fmtDateTime } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { useToast } from '../../context/ToastContext'
import { useAppT } from '../../i18n/AppLangContext'
import { CalendarDays, Eye, FileText, Folder, Lock, Megaphone, MessageSquareText, Pencil, Plus, Star, Timer, Trash2, Users, X } from 'lucide-react'
import { Button, Spinner, EmptyState, Modal, StatusBadge, Tabs } from '../../components/ui'
import type { StatusBadgeKind } from '../../components/ui/StatusBadge'
import { COLOR_DATO_POR_DEFECTO } from '../../constants/theme'
import { sdCatalogApi, sdSlaPoliciesApi, sdGroupsApi, sdTemplatesApi, sdCannedApi, sdAnnouncementsApi, usersApi, approvalsApi, slaCalendarsApi, clientsApi, contractsApi, type SlaCalendar, type UserListItem } from '../../services/api'
import type { SdAnuncio, SdCategoriaDeCatalogo, SdGrupo, SdPlantillaDeTicket, SdPoliticaSla, SdRespuestaRapida, SdServicioDeCatalogo } from '../../services/api/tipos-sd'
import { EscalationConfig, NotificationsConfig } from './ConfigEscaladoYAvisos'
import { CiclosDeVida, ReglasSlaYOla } from './ConfigSlaYCiclos'
import ConfigCanales from './ConfigCanales'
import ConfigCorreoEntrante from './ConfigCorreoEntrante'
import { GuardiasConfig, MonitorizacionConfig } from './ConfigGuardiasYMonitor'
import ConfigPaginaDeEstado from './ConfigPaginaDeEstado'
import { PRIORITY_LABEL, PBadge, etiquetaSd } from './sdUtils'
import { RoutingRules } from './QueueAndRoutingSections'
import DateInput from '../../components/ui/DateInput'
import { SELECTOR_LIST_SIZE } from '../../constants/pagination'
import './ConfigTab.css'

// ── Local types ─────────────────────────────────────────────────────────────
/** El servicio del catalogo; `category_id` lo pone la pantalla al editar (el backend no lo envia). */
type Svc = SdServicioDeCatalogo & { category_id?: string }
type Cat = SdCategoriaDeCatalogo
type Policy = SdPoliticaSla
type Calendario = SlaCalendar
type Member = SdGrupo['members'][number]
type Group = SdGrupo
// #24b: la lista de usuarios ya llega tipada desde usersApi (UserPublic).
type User = UserListItem
/** Solo llegan las activas: desactivar una la saca de la lista (y no se puede reactivar). */
type Template = SdPlantillaDeTicket
type Canned = SdRespuestaRapida
type CannedForm = { title: string; body: string; category: string; shortcut: string }
type Ann = SdAnuncio
const PRIORITY_LABEL_MAP = PRIORITY_LABEL as Record<string, string>

/** Clases de los formularios: el campo del sistema de diseño (`ds-input`). */
const IS_BASE = 'ds-input sdcfg-input'
const LS_BASE = 'sdcfg-label'

// ── Catalog Config ────────────────────────────────────────────────────────────
function CatalogConfig() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [showNewCat, setShowNewCat] = useState(false)
  const [showNewSvc, setShowNewSvc] = useState(false)

  const { data: catalog = [], isLoading } = useQuery<Cat[]>({
    queryKey: ['sd-catalog'],
    queryFn: () => sdCatalogApi.list().then(r => r.data),
  })

  const [editingCat, setEditingCat] = useState<Cat | null>(null)
  const [editingSvc, setEditingSvc] = useState<Svc | null>(null)

  const { mutate: createCat, isPending: creatingCat } = useMutation({
    mutationFn: (d: Record<string, unknown>) => sdCatalogApi.createCategory(d),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-catalog']}); setShowNewCat(false); toast.success(t('sd_cfg.cfg_cat_created')) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  })
  const { mutate: updateCat } = useMutation({
    mutationFn: ({id, ...d}: { id: string } & Record<string, unknown>) => sdCatalogApi.updateCategory(id, d),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-catalog']}); setEditingCat(null); toast.success(t('sd_cfg.cfg_cat_updated')) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: deleteCat } = useMutation({
    mutationFn: (id: string) => sdCatalogApi.deleteCategory(id),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-catalog']}); toast.success(t('sd_cfg.cfg_cat_deleted')) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: createSvc, isPending: creatingSvc } = useMutation({
    mutationFn: (d: Record<string, unknown>) => sdCatalogApi.createService(d),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-catalog']}); setShowNewSvc(false); toast.success(t('sd_cfg.cfg_svc_created')) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  })
  const { mutate: updateSvc } = useMutation({
    mutationFn: ({id, ...d}: { id: string } & Record<string, unknown>) => sdCatalogApi.updateService(id, d),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-catalog']}); setEditingSvc(null); toast.success(t('sd_cfg.cfg_svc_updated')) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: deleteSvc } = useMutation({
    mutationFn: (id: string) => sdCatalogApi.deleteService(id),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-catalog']}); toast.success(t('sd_cfg.cfg_svc_deleted')) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const IS = IS_BASE
  const LS = LS_BASE

  return (
    <div>
      <div className="sdcfg-head">
        <div className="sdcfg-head__desc">{catalog.length > 0 && t('service_desk.catalog_empty_desc')}</div>
        <div className="sdcfg-head__actions">
          <Button variant="secondary" icon={<Plus size={14} />} onClick={() => setShowNewSvc(true)} disabled={catalog.length===0}>{t('sd_cfg.cfg_svc_new')}</Button>
          <Button icon={<Plus size={14} />} onClick={() => setShowNewCat(true)}>{t('sd_cfg.cfg_cat_new')}</Button>
        </div>
      </div>

      {isLoading ? <Spinner /> :
       catalog.length === 0 ? <EmptyState icon={<Folder size={28} />} title={t('service_desk.catalog_empty')} description={t('sd_cfg.cfg_catalog_empty_desc')} /> :
      <div className="u-stack-12">
        {catalog.map((cat: Cat) => (
          <div key={cat.id} className="ds-card ds-card--plano">
            <div className="sdcfg-cat-head">
              <span className="sdcfg-cat-icon" aria-hidden="true"><Folder size={16} /></span>
              <span className="sdcfg-name">{cat.name}</span>
              {cat.description && <span className="sdcfg-cat-desc">{cat.description}</span>}
              <span className="sdcfg-cat-count">{t('config.n_servicios', { n: cat.services?.length || 0 })}</span>
              <div className="sdcfg-cat-actions">
                <Button size="xs" variant="secondary" icon={<Pencil size={12} />} onClick={() => setEditingCat(cat)}>{t('common.edit')}</Button>
                <Button size="xs" variant="ghost" icon={<Trash2 size={12} />} onClick={() => { openConfirmGlobal({ message: t('config.confirmar_eliminar_categoria'), onConfirm: () => deleteCat(cat.id), danger: true }) }}>{t('common.delete')}</Button>
              </div>
            </div>
            {(cat.services?.length ?? 0) > 0 && (
              <div className="u-scroll-x"><table className="u-table">
                <tbody>
                  {(cat.services ?? []).map((svc: Svc) => (
                    <tr key={svc.id} className="u-border-b">
                      <td className="sdcfg-td--name">{svc.name}</td>
                      <td className="sdcfg-td sdcfg-td--xs2">{etiquetaSd('type', svc.ticket_type)}</td>
                      <td className="sdcfg-td"><PBadge v={svc.default_priority} /></td>
                      <td className="sdcfg-td sdcfg-td--xs2">{t('sd_cfg.cfg_resp_res', { r: svc.sla_response_hours, res: svc.sla_resolution_hours })}</td>
                      <td className="sdcfg-td sdcfg-td--xs2">{svc.requires_approval && <span className="u-row-center-6"><Lock size={12} aria-hidden="true" />{t('service_desk.svc_requires_approval')}</span>}</td>
                      <td className="sdcfg-td--actions">
                        <div className="sdcfg-row-actions">
                          <Button size="xs" variant="ghost" icon={<Pencil size={12} />} title={`${t('common.edit')} ${svc.name}`} onClick={() => setEditingSvc({...svc, category_id: cat.id})} />
                          <Button size="xs" variant="ghost" icon={<Trash2 size={12} />} title={`${t('common.delete')} ${svc.name}`} onClick={() => { openConfirmGlobal({ message: t('config.confirmar_eliminar_servicio'), onConfirm: () => deleteSvc(svc.id), danger: true }) }} />
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table></div>
            )}
          </div>
        ))}
      </div>}

      {showNewCat && (
        <NewCategoryModal onClose={() => setShowNewCat(false)}
          onSave={d => createCat(d)} isPending={creatingCat} IS={IS} LS={LS} />
      )}
      {editingCat && (
        <NewCategoryModal
          initial={editingCat}
          onClose={() => setEditingCat(null)}
          onSave={d => updateCat({id: editingCat.id, ...d})}
          isPending={false} IS={IS} LS={LS} />
      )}
      {showNewSvc && (
        <NewServiceModal catalog={catalog} onClose={() => setShowNewSvc(false)}
          onSave={d => createSvc(d)} isPending={creatingSvc} IS={IS} LS={LS} />
      )}
      {editingSvc && (
        <NewServiceModal
          catalog={catalog} initial={editingSvc}
          onClose={() => setEditingSvc(null)}
          onSave={d => updateSvc({id: editingSvc.id, ...d})}
          isPending={false} IS={IS} LS={LS} />
      )}
    </div>
  )
}

function NewCategoryModal({ onClose, onSave, isPending, IS, LS, initial }: { onClose: () => void; onSave: (d: Record<string, unknown>) => void; isPending: boolean; IS: string; LS: string; initial?: Cat | null }) {
  const idCampo = useId()
  const t = useAppT()
  const [form, setForm] = useState({
    name: initial?.name || '', description: initial?.description || '',
    icon: initial?.icon || '', color: initial?.color || '#4f8ef7'
  })
  const set = (k: string) => (e: ChangeEvent<HTMLInputElement>) => setForm(f => ({...f, [k]: e.target.value}))
  return (
    <Modal open title={initial ? t('sd_cfg.cfg_cat_edit') : t('sd_cfg.cfg_cat_new')} onClose={onClose}>
      <div className="u-stack-14">
        <div className="sdcfg-cat-grid">
          <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className={LS}>{t('common.name')} *</label><input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.name} onChange={set('name')} className={IS} /></div>
          <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className={LS}>{t('config.icono')}</label><input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.icon} onChange={set('icon')} className={`${IS} sdcfg-input--icon`} /></div>
          <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className={LS}>{t('config.color')}</label><input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} type="color" value={/^#[0-9a-fA-F]{6}$/.test(form.color) ? form.color : COLOR_DATO_POR_DEFECTO} onChange={set('color')} className={`${IS} sdcfg-input--color`} /></div>
        </div>
        <div className="u-actions-10">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => onSave(form)} disabled={isPending || !form.name} loading={isPending}>{initial ? t('common.save') : t('sd_cfg.cfg_cat_new')}</Button>
        </div>
      </div>
    </Modal>
  )
}

function NewServiceModal({ catalog, onClose, onSave, isPending, IS, LS, initial }: { catalog: Cat[]; onClose: () => void; onSave: (d: Record<string, unknown>) => void; isPending: boolean; IS: string; LS: string; initial?: Svc | null }) {
  const idCampo = useId()
  const t = useAppT()
  const { data: usuarios = [] } = useQuery<User[]>({
    queryKey: ['users'],
    queryFn: () => usersApi.list().then(r => r.data),
  })
  const [form, setForm] = useState({
    name: initial?.name || '',
    category_id: initial?.category_id || catalog[0]?.id || '',
    ticket_type: initial?.ticket_type || 'service_request',
    default_priority: initial?.default_priority || 'p3_medium',
    sla_response_hours: initial?.sla_response_hours || 4,
    sla_resolution_hours: initial?.sla_resolution_hours || 24,
    requires_approval: initial?.requires_approval || false,
    approval_user_id: initial?.approval_user_id || '',
    // Mejoras de mercado 16-11-2026: aprobación de un aprobador o del motor común (varios niveles y condiciones).
    approval_mode: initial?.approval_mode || 'single',
    approval_workflow_id: initial?.approval_workflow_id || '',
    is_visible_to_clients: initial?.is_visible_to_clients ?? true,
  })
  const faltaAprobador = form.requires_approval && form.approval_mode === 'single' && !form.approval_user_id
  type Tarea = { title: string; group_id: string; assignee_user_id?: string | null; sla_hours?: number | string | null; stage?: number | string; description?: string | null }
  const [tareas, setTareas] = useState<Tarea[]>(initial?.fulfillment_tasks ?? [])
  const { data: flujos = [] } = useQuery({
    queryKey: ['approval-workflows', 'catalog_request'],
    queryFn: () => approvalsApi.listWorkflows({ entity_type: 'catalog_request' }).then(r => r.data),
    enabled: form.requires_approval && form.approval_mode === 'engine',
  })
  const { data: colas = [] } = useQuery<{ id: string; name: string }[]>({
    queryKey: ['sd-groups'], queryFn: () => sdGroupsApi.list().then(r => r.data),
  })
  const tareasValidas = tareas.every(x => x.title.trim() && x.group_id)
  const set = (k: string) => (e: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setForm(f => ({...f, [k]: (e.target as HTMLInputElement).type==='checkbox' ? (e.target as HTMLInputElement).checked : e.target.value}))
  return (
    <Modal open title={initial ? t('sd_cfg.cfg_svc_edit') : t('sd_cfg.cfg_svc_new')} onClose={onClose}>
      <div className="u-grid2-14">
        <div className="u-col-full"><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className={LS}>{t('common.name')} *</label><input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.name} onChange={set('name')} className={IS} /></div>
        <div>
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className={LS}>{t('service_desk.tab_catalog')}</label>
          <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.category_id} onChange={set('category_id')} className={IS}>
            {catalog.map((c: Cat) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <div>
          <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className={LS}>{t('service_desk.svc_ticket_type')}</label>
          <select id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.ticket_type} onChange={set('ticket_type')} className={IS}>
            {['incident','service_request','change','question'].map(tk => <option key={tk} value={tk}>{etiquetaSd('type', tk)}</option>)}
          </select>
        </div>
        <div>
          <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className={LS}>{t('service_desk.svc_default_priority')}</label>
          <select id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.default_priority} onChange={set('default_priority')} className={IS}>
            {['p1_critical','p2_high','p3_medium','p4_low'].map(p => <option key={p} value={p}>{PRIORITY_LABEL_MAP[p]}</option>)}
          </select>
        </div>
        <div className="sdcfg-grid2-8">
          <div><label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className={LS}>{t('service_desk.sla_response_h')}</label><input id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} type="number" value={form.sla_response_hours} onChange={set('sla_response_hours')} className={IS} /></div>
          <div><label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} className={LS}>{t('service_desk.sla_resolution_h')}</label><input id={`${idCampo}-6`} aria-labelledby={`${idCampo}-et6`} type="number" value={form.sla_resolution_hours} onChange={set('sla_resolution_hours')} className={IS} /></div>
        </div>
        <div className="u-row-center-10">
          <input type="checkbox" id="svc_visible" aria-label={t('sd_cfg.svc_visible')} checked={form.is_visible_to_clients} onChange={set('is_visible_to_clients')} />
          <label htmlFor="svc_visible" className="sdcfg-check-label">{t('sd_cfg.svc_visible')}</label>
        </div>
        <div className="u-row-center-10">
          <input type="checkbox" id="req_appr" aria-labelledby="req_appr-et" checked={form.requires_approval} onChange={set('requires_approval')} />
          <label id="req_appr-et" htmlFor="req_appr" className="sdcfg-check-label">{t('service_desk.svc_requires_approval')}</label>
        </div>
        {form.requires_approval && (
          <div className="u-col-full">
            <label className={LS} htmlFor="svc_appr_mode">{t('sd_mercado.modo_aprobacion')}</label>
            <select id="svc_appr_mode" value={form.approval_mode} onChange={set('approval_mode')} className={IS}>
              <option value="single">{t('sd_mercado.aprobacion_single')}</option>
              <option value="engine">{t('sd_mercado.aprobacion_engine')}</option>
            </select>
            {form.approval_mode === 'engine' && <span className="u-text3-xs">{t('sd_mercado.aprobacion_engine_hint')}</span>}
          </div>
        )}
        {form.requires_approval && form.approval_mode === 'engine' && (
          <div className="u-col-full">
            <label className={LS} htmlFor="svc_appr_wf">{t('sd_mercado.flujo_aprobacion')}</label>
            <select id="svc_appr_wf" value={form.approval_workflow_id} onChange={set('approval_workflow_id')} className={IS}>
              <option value="">{t('sd_mercado.flujo_por_condiciones')}</option>
              {flujos.filter(f => f.is_active && f.entity_type === 'catalog_request').map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
            </select>
          </div>
        )}
        {form.requires_approval && (
          <div className="u-col-full">
            <label className={LS} htmlFor="svc_approver">{t(form.approval_mode === 'engine' ? 'sd_mercado.aprobador_respaldo' : 'sd_cfg.svc_approver')}{form.approval_mode === 'engine' ? '' : ' *'}</label>
            <select id="svc_approver" aria-label={t('sd_cfg.svc_approver')} value={form.approval_user_id} onChange={set('approval_user_id')} className={IS}>
              <option value="">—</option>
              {usuarios.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
            </select>
          </div>
        )}
        <div className="sdcfg-full-stack" role="group" aria-labelledby={`${idCampo}-ff-et`}>
          <span id={`${idCampo}-ff-et`} className={LS}>{t('sd_cfg.ff_tasks')}</span>
          <span className="u-text3-xs">{t('sd_cfg.ff_help')}</span>
          {tareas.map((tarea, i) => (
            <div key={i} className="u-wrap-8">
              <input aria-label={t('sd_cfg.ff_title')} placeholder={t('sd_cfg.ff_title')} value={tarea.title} className={`${IS} sdcfg-input--flex2`}
                onChange={e => setTareas(ts => ts.map((x, j) => j === i ? { ...x, title: e.target.value } : x))} />
              <select aria-label={t('sd_cfg.oc_queue')} value={tarea.group_id} className={`${IS} sdcfg-input--flex1`}
                onChange={e => setTareas(ts => ts.map((x, j) => j === i ? { ...x, group_id: e.target.value } : x))}>
                <option value="">—</option>
                {colas.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
              <select aria-label={t('sd_mercado.tarea_persona')} value={tarea.assignee_user_id || ''} className={`${IS} sdcfg-input--flex1`}
                onChange={e => setTareas(ts => ts.map((x, j) => j === i ? { ...x, assignee_user_id: e.target.value || null } : x))}>
                <option value="">{t('sd_mercado.tarea_persona_auto')}</option>
                {usuarios.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
              </select>
              <input type="number" min={0} step={0.5} aria-label={t('sd_mercado.tarea_sla')} placeholder={t('sd_mercado.tarea_sla')} value={tarea.sla_hours ?? ''} className={`${IS} sdcfg-input--flex1`}
                onChange={e => setTareas(ts => ts.map((x, j) => j === i ? { ...x, sla_hours: e.target.value } : x))} />
              <input type="number" min={1} aria-label={t('sd_mercado.tarea_etapa')} placeholder={t('sd_mercado.tarea_etapa')} value={tarea.stage ?? 1} className={`${IS} sdcfg-input--flex1`}
                onChange={e => setTareas(ts => ts.map((x, j) => j === i ? { ...x, stage: e.target.value } : x))} />
              <Button size="xs" variant="ghost" icon={<X size={14} />} title={t('common.delete')} onClick={() => setTareas(ts => ts.filter((_, j) => j !== i))} />
            </div>
          ))}
          <div><Button size="sm" variant="secondary" icon={<Plus size={14} />} onClick={() => setTareas(ts => [...ts, { title: '', group_id: '', stage: 1 }])}>{t('sd_cfg.ff_add')}</Button></div>
        </div>
        <div className="sdcfg-full-actions">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => onSave({
            ...form, approval_user_id: form.requires_approval && form.approval_user_id ? form.approval_user_id : null,
            approval_workflow_id: form.requires_approval && form.approval_mode === 'engine' && form.approval_workflow_id ? form.approval_workflow_id : null,
            fulfillment_tasks: tareas.map(x => ({ ...x, sla_hours: x.sla_hours === '' || x.sla_hours == null ? null : Number(x.sla_hours), stage: Number(x.stage || 1) })),
          })}
            disabled={isPending || !form.name || faltaAprobador || !tareasValidas} loading={isPending}>{initial ? t('common.save') : t('sd_cfg.cfg_svc_new')}</Button>
        </div>
      </div>
    </Modal>
  )
}

// ── SLA Config ────────────────────────────────────────────────────────────────
function SLAConfig() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [showNew, setShowNew] = useState(false)

  const { data: policies = [], isLoading } = useQuery<Policy[]>({
    queryKey: ['sd-sla-policies'],
    queryFn: () => sdSlaPoliciesApi.list().then(r => r.data),
  })
  const { data: calendarios = [] } = useQuery<Calendario[]>({
    queryKey: ['sla-calendars'],
    queryFn: () => slaCalendarsApi.list().then(r => r.data),
  })
  const [editing, setEditing] = useState<Policy | null>(null)
  const [asignando, setAsignando] = useState<Policy | null>(null)
  const { mutate: create, isPending } = useMutation({
    mutationFn: (d: Record<string, unknown>) => sdSlaPoliciesApi.create(d),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-sla-policies']}); setShowNew(false); toast.success(t('service_desk.sla_created')) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  })
  const { mutate: update } = useMutation({
    mutationFn: ({id, ...d}: { id: string } & Record<string, unknown>) => sdSlaPoliciesApi.update(id, d),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-sla-policies']}); setEditing(null); toast.success(t('service_desk.sla_updated')) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: remove } = useMutation({
    mutationFn: (id: string) => sdSlaPoliciesApi.delete(id),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-sla-policies']}); toast.success(t('service_desk.sla_deleted')) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const IS = IS_BASE
  const LS = LS_BASE

  return (
    <div>
      <div className="sdcfg-head">
        <div className="sdcfg-head__desc">{policies.length > 0 && t('service_desk.sla_empty_desc')}</div>
        <Button icon={<Plus size={14} />} onClick={() => setShowNew(true)}>{t('sd_cfg.cfg_sla_new')}</Button>
      </div>

      {isLoading ? <Spinner /> :
       policies.length === 0 ? <EmptyState icon={<Timer size={28} />} title={t('service_desk.sla_empty')} description={t('sd_cfg.cfg_sla_empty_desc')} /> :
      <div className="u-stack-12">
        {policies.map((p: Policy) => (
          <div key={p.id} className="ds-card">
            <div className="sdcfg-sla-head">
              <span className="sdcfg-name">{p.name}</span>
              {p.is_default && <StatusBadge kind="accent" caps={false}>{t('service_desk.sla_default_policy')}</StatusBadge>}
              <StatusBadge caps={false}>
                {p.business_hours_only === false ? t('config.horario_24x7')
                  : p.calendar_id ? <span className="u-row-center-6"><CalendarDays size={12} aria-hidden="true" />{calendarios.find(c => c.id === p.calendar_id)?.name ?? t('sd_cfg.schedule_calendars')}</span>
                  : `${p.business_start ?? ''}–${p.business_end ?? ''} h${p.timezone ? ` · ${p.timezone}` : ''}`}
              </StatusBadge>
              <div className="sdcfg-push-right">
                <Button size="xs" variant="secondary" icon={<Pencil size={12} />} onClick={() => setEditing(p)}>{t('common.edit')}</Button>
                <Button size="xs" variant="ghost" icon={<Trash2 size={12} />} onClick={() => { openConfirmGlobal({ message: t('config.confirmar_eliminar_sla'), onConfirm: () => remove(p.id), danger: true }) }}>{t('common.delete')}</Button>
              </div>
            </div>
            <div className="sdcfg-used-by">
              <span><strong>{t('sd_cfg.sla_used_by')}:</strong> {[...(p.clients ?? []), ...(p.contracts ?? [])].map(x => x.name).join(', ') || t('sd_cfg.sla_nobody')}</span>
              <Button size="xs" variant="secondary" onClick={() => setAsignando(p)}>{t('sd_cfg.sla_assign')}</Button>
            </div>
            <div className="sdcfg-prio-grid">
              {[['p1_critical', 'p1'], ['p2_high', 'p2'], ['p3_medium', 'p3'], ['p4_low', 'p4']].map(([prio, key]) => (
                <div key={key} className="sdcfg-prio">
                  <div className="sdcfg-prio__label"><PBadge v={prio} /></div>
                  <div className="u-text2-sm">
                    <div>{t('sd_cfg.cfg_response')} <strong className="u-text1">{p[`${key}_response_hours`] as number} h</strong></div>
                    <div>{t('sd_cfg.cfg_resolution')} <strong className="u-text1">{p[`${key}_resolution_hours`] as number} h</strong></div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>}

      {showNew && (
        <Modal open title={t('sd_cfg.cfg_sla_new')} onClose={() => setShowNew(false)} size="lg">
          <NewSLAForm IS={IS} LS={LS} onSave={d => create(d)} isPending={isPending} onClose={() => setShowNew(false)} />
        </Modal>
      )}
      {asignando && (
        <Modal open title={`${t('sd_cfg.sla_assign')} · ${asignando.name}`} onClose={() => setAsignando(null)}>
          <AsignarPolitica politica={asignando} IS={IS} LS={LS} onHecho={() => { qc.invalidateQueries({queryKey:['sd-sla-policies']}); setAsignando(null) }} />
        </Modal>
      )}
      {editing && (
        <Modal open title={t('sd_cfg.cfg_sla_edit')} onClose={() => setEditing(null)} size="lg">
          <NewSLAForm IS={IS} LS={LS} initial={editing}
            onSave={d => update({id: editing.id, ...d})}
            isPending={false} onClose={() => setEditing(null)} />
        </Modal>
      )}
    </div>
  )
}

function AsignarPolitica({ politica, IS, LS, onHecho }: { politica: Policy; IS: string; LS: string; onHecho: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const [tipo, setTipo] = useState<'client' | 'contract'>('client')
  const [destino, setDestino] = useState('')
  const { data: opciones = [] } = useQuery<{ id: string; name?: string; title?: string }[]>({
    queryKey: ['sla-assign-targets', tipo],
    queryFn: () => (tipo === 'client' ? clientsApi.list() : contractsApi.list({ page_size: SELECTOR_LIST_SIZE }))
      .then(r => r.data as { id: string; name?: string; title?: string }[]),
  })
  const asignar = useMutation({
    mutationFn: () => sdSlaPoliciesApi.assign(tipo, destino, politica.id),
    onSuccess: onHecho,
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  return (
    <div className="u-stack-12">
      <div><label className={LS} htmlFor="sla-asig-tipo">{t('sd_cfg.sla_target_type')}</label>
        <select id="sla-asig-tipo" aria-label={t('sd_cfg.sla_target_type')} value={tipo} onChange={e => { setTipo(e.target.value as 'client' | 'contract'); setDestino('') }} className={IS}>
          <option value="client">{t('sd_cfg.sla_target_client')}</option>
          <option value="contract">{t('sd_cfg.sla_target_contract')}</option>
        </select></div>
      <div><label className={LS} htmlFor="sla-asig-destino">{tipo === 'client' ? t('sd_cfg.sla_target_client') : t('sd_cfg.sla_target_contract')}</label>
        <select id="sla-asig-destino" aria-label={t('sd_cfg.sla_target_client')} value={destino} onChange={e => setDestino(e.target.value)} className={IS}>
          <option value="">—</option>
          {opciones.map(o => <option key={o.id} value={o.id}>{o.name ?? o.title ?? o.id}</option>)}
        </select></div>
      <div className="u-row-end">
        <Button disabled={!destino || asignar.isPending} loading={asignar.isPending} onClick={() => asignar.mutate()}>{t('common.save')}</Button>
      </div>
    </div>
  )
}

const ZONAS: string[] = (() => {
  try { return (Intl as unknown as { supportedValuesOf: (k: string) => string[] }).supportedValuesOf('timeZone') } catch { return [] }
})()

function horarioDe(p?: Policy | null): string {
  if (!p) return 'own'
  if (p.business_hours_only === false) return '247'
  return p.calendar_id ? `cal:${p.calendar_id}` : 'own'
}

function NewSLAForm({ IS, LS, onSave, isPending, onClose, initial }: { IS: string; LS: string; onSave: (d: Record<string, unknown>) => void; isPending: boolean; onClose: () => void; initial?: Policy | null }) {
  const idCampo = useId()
  const t = useAppT()
  const { data: calendarios = [] } = useQuery<Calendario[]>({
    queryKey: ['sla-calendars'],
    queryFn: () => slaCalendarsApi.list().then(r => r.data),
  })
  const [form, setForm] = useState({
    name: initial?.name || '', description: initial?.description || '',
    is_default: initial?.is_default || false,
    p1_response_hours: initial?.p1_response_hours ?? 1, p1_resolution_hours: initial?.p1_resolution_hours ?? 4,
    p2_response_hours: initial?.p2_response_hours ?? 4, p2_resolution_hours: initial?.p2_resolution_hours ?? 8,
    p3_response_hours: initial?.p3_response_hours ?? 8, p3_resolution_hours: initial?.p3_resolution_hours ?? 24,
    p4_response_hours: initial?.p4_response_hours ?? 24, p4_resolution_hours: initial?.p4_resolution_hours ?? 72,
    business_start: initial?.business_start ?? 9, business_end: initial?.business_end ?? 18,
    timezone: initial?.timezone || '',
  })
  const [horario, setHorario] = useState(horarioDe(initial))
  const [dias, setDias] = useState<number[]>(
    (initial?.business_days || '1,2,3,4,5').split(',').map(Number).filter(Boolean))
  const set = (k: string) => (e: ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm(f => ({...f, [k]: (e.target as HTMLInputElement).type==='checkbox' ? (e.target as HTMLInputElement).checked : e.target.value}))
  const formRec = form as Record<string, unknown>
  const nombresDias = t('sd_cfg.days_short').split(',')
  const propio = horario === 'own'
  const valido = !!form.name && (!propio || (dias.length > 0 && Number(form.business_end) > Number(form.business_start)))

  const enviar = () => {
    const horas = Object.fromEntries(['p1','p2','p3','p4'].flatMap(k => [
      [`${k}_response_hours`, Number(formRec[`${k}_response_hours`])],
      [`${k}_resolution_hours`, Number(formRec[`${k}_resolution_hours`])],
    ]))
    onSave({
      name: form.name, description: form.description, is_default: form.is_default, ...horas,
      business_hours_only: horario !== '247',
      calendar_id: horario.startsWith('cal:') ? horario.slice(4) : null,
      business_start: Number(form.business_start), business_end: Number(form.business_end),
      business_days: [...dias].sort().join(','), timezone: form.timezone || null,
    })
  }

  return (
    <div className="u-grid2-14">
      <div className="u-col-full"><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className={LS}>{t('common.name')} *</label><input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.name} onChange={set('name')} className={IS} /></div>
      {[['p1_critical', 'p1'], ['p2_high', 'p2'], ['p3_medium', 'p3'], ['p4_low', 'p4']].map(([prio, key]) => (
        <div key={key} className="sdcfg-box">
          <div className="sdcfg-box__title">{PRIORITY_LABEL_MAP[prio]}</div>
          <div className="sdcfg-grid2-8">
            <div><label id={`${idCampo}-et${key}-resp`} htmlFor={`${idCampo}-${key}-resp`} className={LS}>{t('service_desk.sla_response_h')}</label><input id={`${idCampo}-${key}-resp`} aria-labelledby={`${idCampo}-et${key}-resp`} type="number" min={0} step="0.25" value={formRec[`${key}_response_hours`] as number} onChange={set(`${key}_response_hours`)} className={IS} /></div>
            <div><label id={`${idCampo}-et${key}-resol`} htmlFor={`${idCampo}-${key}-resol`} className={LS}>{t('service_desk.sla_resolution_h')}</label><input id={`${idCampo}-${key}-resol`} aria-labelledby={`${idCampo}-et${key}-resol`} type="number" min={0} step="0.25" value={formRec[`${key}_resolution_hours`] as number} onChange={set(`${key}_resolution_hours`)} className={IS} /></div>
          </div>
        </div>
      ))}
      <div className="sdcfg-box sdcfg-box--full">
        <div>
          <label className={LS} htmlFor="sla-horario">{t('sd_cfg.schedule')}</label>
          <select id="sla-horario" value={horario} onChange={e => setHorario(e.target.value)} className={IS}>
            <option value="247">{t('sd_cfg.schedule_247')}</option>
            {calendarios.length > 0 && (
              <optgroup label={t('sd_cfg.schedule_calendars')}>
                {calendarios.map(c => <option key={c.id} value={`cal:${c.id}`}>{c.name} · {c.work_start}–{c.work_end} · {c.timezone}</option>)}
              </optgroup>
            )}
            <option value="own">{t('sd_cfg.schedule_own')}</option>
          </select>
          <div className="sdcfg-hint">
            {t('sd_cfg.schedule_hint')} <a href="/sla-calendars" className="u-accent">{t('sd_cfg.manage_calendars')}</a>
          </div>
        </div>
        {propio && (
          <div className="sdcfg-hours-grid">
            <div><label id="sla-ini-et" className={LS} htmlFor="sla-ini">{t('sd_cfg.start_hour')}</label>
              <input id="sla-ini" aria-labelledby="sla-ini-et" type="number" min={0} max={23} value={form.business_start} onChange={set('business_start')} className={IS} /></div>
            <div><label id="sla-fin-et" className={LS} htmlFor="sla-fin">{t('sd_cfg.end_hour')}</label>
              <input id="sla-fin" aria-labelledby="sla-fin-et" type="number" min={1} max={24} value={form.business_end} onChange={set('business_end')} className={IS} /></div>
            <div className="sdcfg-span2"><label id="sla-zona-et" className={LS} htmlFor="sla-zona">{t('sd_cfg.timezone')}</label>
              <input id="sla-zona" aria-labelledby="sla-zona-et" list="sla-zonas" value={form.timezone} placeholder={t('sd_cfg.timezone_org')} onChange={set('timezone')} className={IS} />
              <datalist id="sla-zonas">{ZONAS.map(z => <option key={z} value={z} aria-label={z} />)}</datalist></div>
            <div className="u-col-full" role="group" aria-labelledby="sla-dias-et">
              <span id="sla-dias-et" className={LS}>{t('sd_cfg.workdays')}</span>
              <div className="u-wrap-6">
                {nombresDias.map((nombre, i) => {
                  const d = i + 1
                  const on = dias.includes(d)
                  return (
                    <button key={d} type="button" aria-pressed={on}
                      onClick={() => setDias(on ? dias.filter(x => x !== d) : [...dias, d])}
                      className="sdcfg-day">{nombre}</button>
                  )
                })}
              </div>
            </div>
          </div>
        )}
      </div>
      <div className="sdcfg-full-row">
        <label className="sdcfg-check-row">
          <input type="checkbox" aria-label={t('service_desk.sla_default_policy')} checked={form.is_default} onChange={set('is_default')} />
          {t('service_desk.sla_default_policy')}
        </label>
      </div>
      <div className="sdcfg-full-actions">
        <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
        <Button onClick={enviar} disabled={isPending || !valido} loading={isPending}>{initial ? t('common.save') : t('sd_cfg.cfg_sla_new')}</Button>
      </div>
    </div>
  )
}

// ── Groups Config ─────────────────────────────────────────────────────────────
function GroupsConfig() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [showNew, setShowNew] = useState(false)

  const { data: groups = [], isLoading } = useQuery<Group[]>({
    queryKey: ['sd-groups'],
    queryFn: () => sdGroupsApi.list().then(r => r.data),
  })
  const { data: users = [] } = useQuery<User[]>({
    queryKey: ['users'],
    queryFn: () => usersApi.list().then(r => r.data),
  })
  const [editing, setEditing] = useState<Group | null>(null)
  const { mutate: createGroup, isPending } = useMutation({
    mutationFn: (d: Record<string, unknown>) => sdGroupsApi.create(d),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-groups']}); setShowNew(false); toast.success(t('service_desk.groups_created')) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  })
  const { mutate: updateGroup } = useMutation({
    mutationFn: ({id, ...d}: { id: string } & Record<string, unknown>) => sdGroupsApi.update(id, d),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-groups']}); setEditing(null); toast.success(t('service_desk.groups_updated')) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: deleteGroup } = useMutation({
    mutationFn: (id: string) => sdGroupsApi.delete(id),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-groups']}); toast.success(t('service_desk.groups_deleted')) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: addMember } = useMutation({
    mutationFn: ({gid, uid}: { gid: string; uid: string }) => sdGroupsApi.addMember(gid, uid),
    onSuccess: () => qc.invalidateQueries({queryKey:['sd-groups']}),
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  })
  const { mutate: removeMember } = useMutation({
    mutationFn: ({gid, uid}: { gid: string; uid: string }) => sdGroupsApi.removeMember(gid, uid),
    onSuccess: () => qc.invalidateQueries({queryKey:['sd-groups']}),
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  })

  const IS = IS_BASE
  const LS = LS_BASE

  return (
    <div>
      <div className="sdcfg-head">
        <div className="sdcfg-head__desc">{groups.length > 0 && t('service_desk.groups_empty_desc')}</div>
        <Button icon={<Plus size={14} />} onClick={() => setShowNew(true)}>{t('sd_cfg.cfg_group_new')}</Button>
      </div>

      {isLoading ? <Spinner /> :
       groups.length === 0 ? <EmptyState icon={<Users size={28} />} title={t('service_desk.groups_empty')} description={t('sd_cfg.cfg_groups_empty_desc')} /> :
      <div className="u-stack-12">
        {groups.map((g: Group) => {
          const memberIds = new Set((g.members || []).map((m: Member) => m.id))
          const available = (users || []).filter((u: User) => !memberIds.has(u.id))
          return (
            <div key={g.id} className="ds-card">
              <div className="sdcfg-group-head">
                <div className="sdcfg-group-title">
                  <span className="sdcfg-name">{g.name}</span>
                  <StatusBadge caps={false}>{t(`config.nivel_${g.support_level || 'l1'}`)}</StatusBadge>
                  {g.ola_hours != null && <StatusBadge caps={false}>{t('config.ola_horas', { n: g.ola_hours })}</StatusBadge>}
                </div>
                <div className="sdcfg-group-actions">
                  {available.length > 0 && (
                    <select defaultValue="" onChange={e => { if(e.target.value) addMember({gid:g.id, uid:e.target.value}); e.target.value='' }}
                      className={`${IS} sdcfg-input--auto`} aria-label={t('sd_cfg.cfg_add_member')}>
                      <option value="" disabled>{t('sd_cfg.cfg_add_member')}</option>
                      {available.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
                    </select>
                  )}
                  <Button size="xs" variant="secondary" icon={<Pencil size={12} />} onClick={() => setEditing(g)}>{t('common.edit')}</Button>
                  <Button size="xs" variant="ghost" icon={<Trash2 size={12} />} onClick={() => { openConfirmGlobal({ message: t('config.confirmar_eliminar_grupo', { name: g.name }), onConfirm: () => deleteGroup(g.id), danger: true }) }}>{t('common.delete')}</Button>
                </div>
              </div>
              {g.description && <div className="sdcfg-desc">{g.description}</div>}
              <div className="u-wrap-8">
                {(g.members || []).map((m: Member) => (
                  <div key={m.id} className="sdcfg-member">
                    <span className="sdcfg-member__name">{m.full_name}</span>
                    {m.is_lead && <span className="sdcfg-member__lead" role="img" aria-label={t('config.responsable')} title={t('config.responsable')}><Star size={12} aria-hidden="true" /></span>}
                    <button type="button" onClick={() => removeMember({gid:g.id, uid:m.id})} aria-label={t('config.quitar_miembro', { name: m.full_name ?? '' })}
                      title={t('config.quitar_miembro', { name: m.full_name ?? '' })} className="sdcfg-member__remove"><X size={12} aria-hidden="true" /></button>
                  </div>
                ))}
                {(!g.members || g.members.length === 0) &&
                  <span className="sdcfg-no-members">{t('service_desk.groups_no_members')}</span>}
              </div>
            </div>
          )
        })}
      </div>}

      {showNew && (
        <Modal open title={t('sd_cfg.cfg_group_new')} onClose={() => setShowNew(false)}>
          <div className="u-stack-14">
            <NewGroupForm IS={IS} LS={LS} onSave={createGroup} isPending={isPending} onClose={() => setShowNew(false)} />
          </div>
        </Modal>
      )}
      {editing && (
        <Modal open title={t('sd_cfg.cfg_group_edit')} onClose={() => setEditing(null)}>
          <div className="u-stack-14">
            <NewGroupForm IS={IS} LS={LS} initial={editing}
              onSave={d => updateGroup({id: editing.id, ...d})}
              isPending={false} onClose={() => setEditing(null)} />
          </div>
        </Modal>
      )}
    </div>
  )
}

function NewGroupForm({ IS, LS, onSave, isPending, onClose, initial }: { IS: string; LS: string; onSave: (d: Record<string, unknown>) => void; isPending: boolean; onClose: () => void; initial?: Group | null }) {
  const idCampo = useId()
  const t = useAppT()
  const [form, setForm] = useState({
    name: initial?.name || '', description: initial?.description || '',
    support_level: initial?.support_level || 'l1', ola_hours: initial?.ola_hours != null ? String(initial.ola_hours) : '',
  })
  const ola = form.ola_hours.trim() === '' ? null : Number(form.ola_hours)
  const olaValido = ola === null || (Number.isFinite(ola) && ola > 0)
  const set = (k: string) => (e: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setForm(f => ({...f, [k]: e.target.value}))
  return (
    <>
      <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className={LS}>{t('common.name')} *</label><input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.name} onChange={set('name')} className={IS} /></div>
      <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className={LS}>{t('service_desk.groups_support_level')}</label>
        <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.support_level} onChange={set('support_level')} className={IS}>
          {['l1','l2','l3'].map(v =>
            <option key={v} value={v}>{t(`config.nivel_${v}`)}</option>)}
        </select>
      </div>
      <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className={LS}>{t('common.description')}</label><input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.description} onChange={set('description')} className={IS} /></div>
      <div><label id="grp-ola-et" className={LS} htmlFor="grp-ola">{t('sd_cfg.ola_hours')}</label>
        <input id="grp-ola" aria-labelledby="grp-ola-et" type="number" min={0} step={0.5} value={form.ola_hours} onChange={set('ola_hours')} className={IS}
          aria-invalid={!olaValido} aria-describedby="grp-ola-hint" />
        <div id="grp-ola-hint" className={olaValido ? 'sdcfg-hint sdcfg-hint--tight' : 'sdcfg-hint sdcfg-hint--tight sdcfg-hint--error'}>{t('sd_cfg.ola_hint')}</div>
      </div>
      <div className="u-actions-10">
        <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
        <Button onClick={() => onSave({ ...form, ola_hours: ola })} disabled={isPending || !form.name || !olaValido} loading={isPending}>{initial ? t('common.save') : t('sd_cfg.cfg_group_new')}</Button>
      </div>
    </>
  )
}

// ── Templates Config ──────────────────────────────────────────────────────────
function TemplatesConfig() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [showNew, setShowNew] = useState(false)

  const { data: templates = [], isLoading } = useQuery<Template[]>({
    queryKey: ['sd-templates'],
    queryFn: () => sdTemplatesApi.list().then(r => r.data),
  })
  const [editing, setEditing] = useState<Template | null>(null)
  const { mutate: create, isPending } = useMutation({
    mutationFn: (d: Record<string, unknown>) => sdTemplatesApi.create(d),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-templates']}); setShowNew(false); toast.success(t('service_desk.templates_created')) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  })
  const { mutate: update } = useMutation({
    mutationFn: ({id, ...d}: { id: string } & Record<string, unknown>) => sdTemplatesApi.update(id, d),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-templates']}); setEditing(null); toast.success(t('service_desk.templates_updated')) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: toggle } = useMutation({
    mutationFn: ({id, is_active}: { id: string; is_active: boolean }) => sdTemplatesApi.update(id, {is_active}),
    onSuccess: () => qc.invalidateQueries({queryKey:['sd-templates']}),
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  })
  const { mutate: remove } = useMutation({
    mutationFn: (id: string) => sdTemplatesApi.delete(id),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-templates']}); toast.success(t('service_desk.templates_deleted')) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const IS = IS_BASE
  const LS = LS_BASE

  return (
    <div>
      <div className="sdcfg-head">
        <div className="sdcfg-head__desc">{templates.length > 0 && t('service_desk.templates_empty_desc')}</div>
        <Button icon={<Plus size={14} />} onClick={() => setShowNew(true)}>{t('sd_cfg.cfg_tmpl_new')}</Button>
      </div>

      {isLoading ? <Spinner /> :
       templates.length === 0 ? <EmptyState icon={<FileText size={28} />} title={t('service_desk.templates_empty')} description={t('sd_cfg.cfg_tmpl_empty_desc')} /> :
      <div className="sdcfg-tmpl-grid">
        {templates.map((tmpl: Template) => (
          <div key={tmpl.id} className="ds-card">
            <div className="sdcfg-tmpl-head">
              <div className="u-min0">
                <div className="sdcfg-tmpl-name">{tmpl.name}</div>
                <div className="u-wrap-6">
                  <StatusBadge caps={false}>{etiquetaSd('type', tmpl.ticket_type)}</StatusBadge>
                  <StatusBadge kind="success" caps={false}>{t('service_desk.templates_active')}</StatusBadge>
                </div>
              </div>
              <div className="sdcfg-row-actions">
                <Button size="xs" variant="ghost" icon={<Pencil size={12} />} title={`${t('common.edit')} ${tmpl.name}`} onClick={() => setEditing(tmpl)} />
                <Button size="xs" variant="ghost" icon={<Trash2 size={12} />} title={`${t('common.delete')} ${tmpl.name}`} onClick={() => { openConfirmGlobal({ message: t('config.confirmar_eliminar_plantilla'), onConfirm: () => remove(tmpl.id), danger: true }) }} />
              </div>
            </div>
            {tmpl.default_priority && <div className="sdcfg-tmpl-prio">
              {t('service_desk.templates_priority')}: <PBadge v={tmpl.default_priority} />
            </div>}
            {tmpl.description_template && (
              <div className="sdcfg-tmpl-desc">
                {tmpl.description_template.slice(0, 80)}{tmpl.description_template.length > 80 ? '…' : ''}
              </div>
            )}
            <div><Button size="xs" variant="secondary" onClick={() => toggle({id:tmpl.id, is_active:false})}>{t('sd_cfg.cfg_deactivate')}</Button></div>
          </div>
        ))}
      </div>}

      {showNew && (
        <Modal open title={t('sd_cfg.cfg_tmpl_new')} onClose={() => setShowNew(false)}>
          <NewTemplateForm IS={IS} LS={LS} onSave={create} isPending={isPending} onClose={() => setShowNew(false)} />
        </Modal>
      )}
      {editing && (
        <Modal open title={t('sd_cfg.cfg_tmpl_edit')} onClose={() => setEditing(null)}>
          <NewTemplateForm IS={IS} LS={LS} initial={editing}
            onSave={d => update({id: editing.id, ...d})}
            isPending={false} onClose={() => setEditing(null)} />
        </Modal>
      )}
    </div>
  )
}

function NewTemplateForm({ IS, LS, onSave, isPending, onClose, initial }: { IS: string; LS: string; onSave: (d: Record<string, unknown>) => void; isPending: boolean; onClose: () => void; initial?: Template | null }) {
  const idCampo = useId()
  const t = useAppT()
  const [form, setForm] = useState({
    name: initial?.name || '', ticket_type: initial?.ticket_type || 'service_request',
    default_priority: initial?.default_priority || 'p3_medium',
    description_template: initial?.description_template || '',
  })
  const set = (k: string) => (e: ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setForm(f => ({...f, [k]: e.target.value}))
  return (
    <div className="u-stack-14">
      <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className={LS}>{t('common.name')} *</label><input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.name} onChange={set('name')} className={IS} /></div>
      <div className="u-grid2-10">
        <div>
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className={LS}>{t('service_desk.svc_ticket_type')}</label>
          <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.ticket_type} onChange={set('ticket_type')} className={IS}>
            {['incident','service_request','change','question','problem'].map(tk =>
              <option key={tk} value={tk}>{etiquetaSd('type', tk)}</option>)}
          </select>
        </div>
        <div>
          <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className={LS}>{t('service_desk.templates_priority')}</label>
          <select id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.default_priority} onChange={set('default_priority')} className={IS}>
            {['p1_critical','p2_high','p3_medium','p4_low'].map(p =>
              <option key={p} value={p}>{PRIORITY_LABEL_MAP[p]}</option>)}
          </select>
        </div>
      </div>
      <div>
        <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className={LS}>{t('sd_cfg.cfg_tmpl_body')}</label>
        <textarea id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.description_template} onChange={set('description_template')} rows={4}
          className={IS} placeholder={t('config.texto_de_la_plantilla_de_descripcion')} />
      </div>
      <div className="u-actions-10">
        <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
        <Button onClick={() => onSave(form)} disabled={isPending || !form.name} loading={isPending}>{initial ? t('common.save') : t('sd_cfg.cfg_tmpl_new')}</Button>
      </div>
    </div>
  )
}

// ── Canned Responses Manager ──────────────────────────────────────────────────
function CannedResponsesManager() {
  const idCampo = useId()
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [form, setForm] = useState<CannedForm>({ title: '', body: '', category: '', shortcut: '' })
  const [editing, setEditing] = useState<string | null>(null)
  const [editForm, setEditForm] = useState<Partial<CannedForm>>({})

  const { data: responses = [], isLoading } = useQuery<Canned[]>({
    queryKey: ['canned-responses-all'],
    queryFn: () => sdCannedApi.list(undefined).then(r => r.data).catch(() => []),
  })
  const IS = IS_BASE
  const LS = LS_BASE

  const { mutate: create } = useMutation({
    mutationFn: (d: Record<string, unknown>) => sdCannedApi.create(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['canned-responses-all'] }); setForm({ title:'', body:'', category:'', shortcut:'' }) },
    onError: (e: unknown) => toast.error((e as {response?:{data?:{detail?:string}}})?.response?.data?.detail || t('config.error')),
  })
  const { mutate: update } = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<CannedForm> }) => sdCannedApi.update(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['canned-responses-all'] }); setEditing(null) },
    onError: (e: unknown) => toast.error((e as {response?:{data?:{detail?:string}}})?.response?.data?.detail || t('config.error')),
  })
  const { mutate: del } = useMutation({
    mutationFn: (id: string) => sdCannedApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['canned-responses-all'] }),
    onError: (e: unknown) => toast.error((e as {response?:{data?:{detail?:string}}})?.response?.data?.detail || t('config.error')),
  })

  return (
    <div>
      <div className="sdcfg-head">
        <div className="sdcfg-head__desc">{t('config.respuestas_predefinidas_reutilizables_por_los_agentes_al')}</div>
      </div>

      {isLoading ? <div className="sdcfg-loading"><Spinner /></div> : (
        <div className="sdcfg-canned-list">
          {responses.map((r: Canned) => editing === r.id ? (
            <div key={r.id} className="sdcfg-canned-edit">
              <div className="sdcfg-grid2-8 sdcfg-grid2-8--mb">
          <div><label id={`${idCampo}-${r.id}-etedit895`} htmlFor={`${idCampo}-${r.id}-edit895`} className={LS}>{t('common.name')} *</label>
            <input id={`${idCampo}-${r.id}-edit895`} aria-labelledby={`${idCampo}-${r.id}-etedit895`} value={editForm.title||''} onChange={e=>setEditForm(f=>({...f,title:e.target.value}))} className={IS} /></div>
          <div><label id={`${idCampo}-${r.id}-etedit897`} htmlFor={`${idCampo}-${r.id}-edit897`} className={LS}>{t('sd_cfg.cfg_category')}</label>
            <input id={`${idCampo}-${r.id}-edit897`} aria-labelledby={`${idCampo}-${r.id}-etedit897`} value={editForm.category||''} onChange={e=>setEditForm(f=>({...f,category:e.target.value}))} className={IS} /></div>
        </div>
        <div className="sdcfg-mb-8"><label id={`${idCampo}-${r.id}-etedit900`} htmlFor={`${idCampo}-${r.id}-edit900`} className={LS}>{t('sd_cfg.cfg_shortcut')}</label>
          <input id={`${idCampo}-${r.id}-edit900`} aria-labelledby={`${idCampo}-${r.id}-etedit900`} value={editForm.shortcut||''} onChange={e=>setEditForm(f=>({...f,shortcut:e.target.value}))} className={IS} /></div>
        <div className="u-mb-10"><label id={`${idCampo}-${r.id}-etedit902`} htmlFor={`${idCampo}-${r.id}-edit902`} className={LS}>{t('service_desk.canned_body_lbl')} *</label>
                <textarea id={`${idCampo}-${r.id}-edit902`} aria-labelledby={`${idCampo}-${r.id}-etedit902`} value={editForm.body||''} onChange={e=>setEditForm(f=>({...f,body:e.target.value}))} rows={4}
                  className={IS} /></div>
              <div className="u-row-8">
                <Button size="sm" onClick={() => update({ id:r.id, data:editForm })} disabled={!editForm.title||!editForm.body}>{t('common.save')}</Button>
                <Button size="sm" variant="secondary" onClick={() => setEditing(null)}>{t('common.cancel')}</Button>
              </div>
            </div>
          ) : (
            <div key={r.id} className="sdcfg-canned-row">
              <div className="u-flex1-min0">
                <div className="u-base-700">{r.title}
                  {r.shortcut && <span className="sdcfg-shortcut">{r.shortcut}</span>}
                  {r.category && <span className="sdcfg-category">{r.category}</span>}
                </div>
                <div className="sdcfg-canned-body">{r.body?.slice(0,100)}</div>
              </div>
              <div className="sdcfg-row-actions">
                <Button size="xs" variant="ghost" icon={<Pencil size={12} />} title={`${t('common.edit')} ${r.title}`} onClick={() => { setEditing(r.id); setEditForm({title:r.title,body:r.body,category:r.category||'',shortcut:r.shortcut||''}) }} />
                <Button size="xs" variant="ghost" icon={<Trash2 size={12} />} title={`${t('common.delete')} ${r.title}`} onClick={() => { openConfirmGlobal({ message: t('config.confirmar_eliminar_x', { title: r.title }), onConfirm: () => del(r.id), danger: true }) }} />
              </div>
            </div>
          ))}
          {responses.length === 0 && !isLoading && (
            <EmptyState icon={<MessageSquareText size={28} />} title={t('service_desk.canned_empty')} description={t('sd_cfg.cfg_canned_empty_desc')} />
          )}
        </div>
      )}

      <div className="ds-card">
        <div className="ds-eyebrow">{t('service_desk.canned_new_header')}</div>
        <div className="sdcfg-grid2-8 sdcfg-grid2-8--mb">
          <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className={LS}>{t('common.name')} *</label>
            <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.title} onChange={e=>setForm(f=>({...f,title:e.target.value}))} className={IS} /></div>
          <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className={LS}>{t('sd_cfg.cfg_category')}</label>
            <input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.category} onChange={e=>setForm(f=>({...f,category:e.target.value}))} className={IS} /></div>
        </div>
        <div className="sdcfg-mb-8"><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className={LS}>{t('sd_cfg.cfg_shortcut')}</label>
          <input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.shortcut} onChange={e=>setForm(f=>({...f,shortcut:e.target.value}))} className={IS} /></div>
        <div className="u-mb-12"><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className={LS}>{t('service_desk.canned_body_lbl')} *</label>
          <textarea id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.body} onChange={e=>setForm(f=>({...f,body:e.target.value}))} rows={4}
            className={IS} placeholder={t('config.texto_de_la_respuesta_enlatada')} /></div>
        <div><Button icon={<Plus size={14} />} onClick={() => create(form)} disabled={!form.title || !form.body}>{t('sd_cfg.cfg_canned_add')}</Button></div>
      </div>
    </div>
  )
}

// ── Announcements Config ──────────────────────────────────────────────────────
export function AnnouncementsConfig() {
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ title:'', body:'', type:'info', show_to_clients:true, starts_at:'', ends_at:'' })

  const IS = IS_BASE
  const LS = LS_BASE
  const TYPE_KIND: Record<string, StatusBadgeKind> = { info: 'accent', warning: 'warning', outage: 'danger', maintenance: 'purple' }
  const ANN_TYPES = ['info','warning','outage','maintenance']

  const { data: anns = [], isLoading } = useQuery<Ann[]>({
    queryKey: ['sd-announcements'],
    queryFn: () => sdAnnouncementsApi.list().then(r => r.data),
  })
  const { mutate: create, isPending: creating } = useMutation({
    mutationFn: (d: Record<string, unknown>) => sdAnnouncementsApi.create(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sd-announcements'] }); setShowCreate(false); setForm({ title:'', body:'', type:'info', show_to_clients:true, starts_at:'', ends_at:'' }); toast.success(t('service_desk.ann_published')) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: del } = useMutation({
    mutationFn: (id: string) => sdAnnouncementsApi.delete(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sd-announcements'] }); toast.success(t('service_desk.ann_deactivated')) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  return (
    <div>
      <div className="sdcfg-head">
        <div className="sdcfg-head__desc">{anns.length > 0 && t('sd_cfg.cfg_ann_desc')}</div>
        <Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{t('sd_cfg.cfg_ann_new')}</Button>
      </div>
      {isLoading ? <div className="sdcfg-loading sdcfg-loading--30"><Spinner /></div>
        : anns.length === 0
          ? <EmptyState icon={<Megaphone size={28} />} title={t('service_desk.ann_empty')} description={t('sd_cfg.cfg_ann_empty_desc')} />
          : (
            <div className="u-stack-10">
              {anns.map((a: Ann) => (
                <div key={a.id} className="ds-card sdcfg-ann">
                  <div className="u-flex1-min0">
                    <div className="sdcfg-ann__title">
                      <span>{a.title}</span>
                      <StatusBadge kind={TYPE_KIND[a.type || ''] ?? 'neutral'} caps={false}>{ANN_TYPES.includes(a.type ?? '') ? t(`config.ann_tipo_${a.type}`) : a.type}</StatusBadge>
                      {a.show_to_clients && <span className="sdcfg-ann__visible"><Eye size={12} aria-hidden="true" />{t('service_desk.ann_visible_clients')}</span>}
                    </div>
                    <div className="sdcfg-ann__body">{a.body}</div>
                    {(a.starts_at||a.ends_at) && (
                      <div className="sdcfg-hint">
                        {a.starts_at && `${t('service_desk.ann_starts')}: ${fmtDateTime(a.starts_at)}`}
                        {a.ends_at && ` · ${t('service_desk.ann_ends')}: ${fmtDateTime(a.ends_at)}`}
                      </div>
                    )}
                  </div>
                  <Button size="xs" variant="ghost" icon={<Trash2 size={12} />} title={t('config.desactivar_anuncio_x', { title: a.title })} onClick={() => { openConfirmGlobal({ message: t('config.confirmar_desactivar_anuncio'), onConfirm: () => del(a.id) }) }} />
                </div>
              ))}
            </div>
          )
      }
      {showCreate && (
        <Modal open title={t('sd_cfg.cfg_ann_new')} onClose={() => setShowCreate(false)}>
          <div className="sdcfg-ann-form">
            <div className="u-col-full"><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className={LS}>{t('sd_cfg.cfg_ann_title')} *</label><input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.title} onChange={e=>setForm(f=>({...f,title:e.target.value}))} className={IS} /></div>
            <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className={LS}>{t('sd_mercado.tipo')}</label>
              <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.type} onChange={e=>setForm(f=>({...f,type:e.target.value}))} className={IS}>
                {ANN_TYPES.map(tp=><option key={tp} value={tp}>{t(`config.ann_tipo_${tp}`)}</option>)}
              </select>
            </div>
            <div className="sdcfg-ann-check">
              <input type="checkbox" id="showCl" aria-labelledby="showCl-et" checked={form.show_to_clients} onChange={e=>setForm(f=>({...f,show_to_clients:e.target.checked}))} />
              <label id="showCl-et" htmlFor="showCl" className="sdcfg-check-label">{t('service_desk.ann_visible_clients')}</label>
            </div>
            <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className={LS}>{t('service_desk.ann_starts')}</label><DateInput id={`${idCampo}-3`} withTime value={form.starts_at} onChange={e=>setForm(f=>({...f,starts_at:e.target.value}))} className={IS} /></div>
            <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className={LS}>{t('service_desk.ann_ends')}</label><DateInput id={`${idCampo}-4`} withTime value={form.ends_at} onChange={e=>setForm(f=>({...f,ends_at:e.target.value}))} className={IS} /></div>
            <div className="u-col-full"><label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className={LS}>{t('service_desk.ann_message')} *</label><textarea id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={form.body} onChange={e=>setForm(f=>({...f,body:e.target.value}))} rows={4} className={IS} /></div>
          </div>
          <div className="u-actions-10">
            <Button variant="secondary" onClick={()=>setShowCreate(false)}>{t('common.cancel')}</Button>
            <Button onClick={()=>create(form)} loading={creating} disabled={!form.title||!form.body||creating}>{t('sd_cfg.cfg_ann_publish')}</Button>
          </div>
        </Modal>
      )}
    </div>
  )
}

// ── Config wrapper (tab nav) ──────────────────────────────────────────────────
export default function Config() {
  const t = useAppT()
  const [sub, setSub] = useState('catalog')
  const tabs = [
    {id:'catalog',  label:t('sd_cfg.cfg_tab_catalog')},
    {id:'sla',      label:t('sd_cfg.cfg_tab_sla')},
    {id:'sla_rules', label:t('sd_mercado.tab_sla_reglas')},
    {id:'lifecycles', label:t('sd_mercado.tab_ciclos')},
    {id:'channels', label:t('sd_mercado.tab_canales')},
    {id:'groups',   label:t('sd_cfg.cfg_tab_groups')},
    {id:'routing',  label:t('sd_cfg.cfg_tab_routing')},
    {id:'escalation', label:t('sd_cfg.tab_escalation')},
    {id:'notifications', label:t('sd_cfg.tab_notifications')},
    {id:'mail', label:t('sd_cfg.tab_mail')},
    {id:'monitoring', label:t('sd_cfg.tab_monitoring')},
    {id:'oncall', label:t('sd_cfg.tab_oncall')},
    {id:'status_page', label:t('sd_cfg.tab_status_page')},
    {id:'templates',label:t('sd_cfg.cfg_tab_templates')},
    {id:'canned',   label:t('sd_cfg.cfg_tab_canned')},
    {id:'announcements', label:t('service_desk.tab_announcements')},
  ]
  return (
    <div>
      <Tabs items={tabs} active={sub} onChange={setSub} ariaLabel={t('sd_cfg.cfg_nav')} />
      {sub === 'catalog'       && <CatalogConfig />}
      {sub === 'sla'           && <SLAConfig />}
      {sub === 'sla_rules'     && <ReglasSlaYOla />}
      {sub === 'lifecycles'    && <CiclosDeVida />}
      {sub === 'channels'      && <ConfigCanales />}
      {sub === 'groups'        && <GroupsConfig />}
      {sub === 'routing'       && <RoutingRules />}
      {sub === 'escalation'    && <EscalationConfig />}
      {sub === 'notifications' && <NotificationsConfig />}
      {sub === 'mail'          && <ConfigCorreoEntrante />}
      {sub === 'monitoring'    && <MonitorizacionConfig />}
      {sub === 'oncall'        && <GuardiasConfig />}
      {sub === 'status_page'   && <ConfigPaginaDeEstado />}
      {sub === 'templates'     && <TemplatesConfig />}
      {sub === 'canned'        && <CannedResponsesManager />}
      {sub === 'announcements' && <AnnouncementsConfig />}
    </div>
  )
}

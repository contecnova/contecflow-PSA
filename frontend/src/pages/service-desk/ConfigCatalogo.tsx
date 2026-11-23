// Configuracion del catalogo de servicios (categorias y servicios) del Service Desk. 23-11-2026: troceado de ConfigTab sin cambio de comportamiento.
import { useState, useId } from 'react'
import type { ChangeEvent } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { useListaDeUsuarios } from '../../hooks/useListas'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { useToast } from '../../context/ToastContext'
import { useAppT } from '../../i18n/AppLangContext'
import { Folder, Languages, Lock, Pencil, Plus, Trash2, X } from 'lucide-react'
import { Button, Spinner, EmptyState, Modal, Select, TablaSimple, Checkbox, Input, useErroresDeCampo } from '../../components/ui'
import { DialogoDeVersionesDeContenido } from '../../components/traduccion/VersionesDeContenidoPanel'
import { COLOR_CATEGORIA_POR_DEFECTO, COLOR_DATO_POR_DEFECTO } from '../../constants/theme'
import { sdCatalogApi, sdGroupsApi, approvalsApi } from '../../services/api'
import { PBadge, etiquetaSd } from './sdUtils'
import { type Cat, IS_BASE, LS_BASE, PRIORITY_LABEL_MAP, type Svc, type Traduciendo, useAvisoDeDesactualizadas } from './ConfigTabComun'

// ── Catalog Config ────────────────────────────────────────────────────────────
export function CatalogConfig() {
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
  const [traduciendo, setTraduciendo] = useState<Traduciendo | null>(null)
  // 17-11-2026: errores de validación del servidor junto a cada campo.
  const camposCat = useErroresDeCampo()
  const camposSvc = useErroresDeCampo()
  const avisarDesactualizadas = useAvisoDeDesactualizadas()

  const { mutate: createCat, isPending: creatingCat } = useMutation({
    mutationFn: (d: Record<string, unknown>) => sdCatalogApi.createCategory(d),
    onMutate: () => camposCat.limpiar(),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-catalog']}); setShowNewCat(false); toast.success(t('sd_cfg.cfg_cat_created')) },
    onError: (e: unknown) => { if (!camposCat.recoger(e)) toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) }
  })
  const { mutate: updateCat } = useMutation({
    mutationFn: ({id, ...d}: { id: string } & Record<string, unknown>) => sdCatalogApi.updateCategory(id, d),
    onMutate: () => camposCat.limpiar(),
    onSuccess: r => { qc.invalidateQueries({queryKey:['sd-catalog']}); setEditingCat(null); toast.success(t('sd_cfg.cfg_cat_updated')); avisarDesactualizadas(r.data?.translations_outdated) },
    onError: (e: unknown) => { if (!camposCat.recoger(e)) toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) },
  })
  const { mutate: deleteCat } = useMutation({
    mutationFn: (id: string) => sdCatalogApi.deleteCategory(id),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-catalog']}); toast.success(t('sd_cfg.cfg_cat_deleted')) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: createSvc, isPending: creatingSvc } = useMutation({
    mutationFn: (d: Record<string, unknown>) => sdCatalogApi.createService(d),
    onMutate: () => camposSvc.limpiar(),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-catalog']}); setShowNewSvc(false); toast.success(t('sd_cfg.cfg_svc_created')) },
    onError: (e: unknown) => { if (!camposSvc.recoger(e)) toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) }
  })
  const { mutate: updateSvc } = useMutation({
    mutationFn: ({id, ...d}: { id: string } & Record<string, unknown>) => sdCatalogApi.updateService(id, d),
    onMutate: () => camposSvc.limpiar(),
    onSuccess: r => { qc.invalidateQueries({queryKey:['sd-catalog']}); setEditingSvc(null); toast.success(t('sd_cfg.cfg_svc_updated')); avisarDesactualizadas(r.data?.translations_outdated) },
    onError: (e: unknown) => { if (!camposSvc.recoger(e)) toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) },
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
                <Button size="xs" variant="ghost" icon={<Languages size={12} />} title={t('traduccion_admin.portal_versiones_de', { nombre: cat.name })}
                  onClick={() => setTraduciendo({ tipo: 'catalog_category', id: cat.id, etiqueta: cat.name })}>{t('traduccion_admin.portal_idiomas')}</Button>
                <Button size="xs" variant="ghost" icon={<Trash2 size={12} />} onClick={() => { openConfirmGlobal({ message: t('config.confirmar_eliminar_categoria'), onConfirm: () => deleteCat(cat.id), danger: true }) }}>{t('common.delete')}</Button>
              </div>
            </div>
            {(cat.services?.length ?? 0) > 0 && (
              <div className="u-scroll-x"><TablaSimple claseTabla="u-table">
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
                          <Button size="xs" variant="ghost" icon={<Languages size={12} />} title={t('traduccion_admin.portal_versiones_de', { nombre: svc.name })}
                            onClick={() => setTraduciendo({ tipo: 'catalog_service', id: svc.id, etiqueta: svc.name })} />
                          <Button size="xs" variant="ghost" icon={<Trash2 size={12} />} title={`${t('common.delete')} ${svc.name}`} onClick={() => { openConfirmGlobal({ message: t('config.confirmar_eliminar_servicio'), onConfirm: () => deleteSvc(svc.id), danger: true }) }} />
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </TablaSimple></div>
            )}
          </div>
        ))}
      </div>}

      {showNewCat && (
        <NewCategoryModal onClose={() => { setShowNewCat(false); camposCat.limpiar() }}
          onSave={d => createCat(d)} isPending={creatingCat} IS={IS} LS={LS} errorDe={camposCat.de} />
      )}
      {editingCat && (
        <NewCategoryModal
          initial={editingCat}
          onClose={() => { setEditingCat(null); camposCat.limpiar() }}
          onSave={d => updateCat({id: editingCat.id, ...d})}
          isPending={false} IS={IS} LS={LS} errorDe={camposCat.de} />
      )}
      {showNewSvc && (
        <NewServiceModal catalog={catalog} onClose={() => { setShowNewSvc(false); camposSvc.limpiar() }}
          onSave={d => createSvc(d)} isPending={creatingSvc} LS={LS} errorDe={camposSvc.de} />
      )}
      {editingSvc && (
        <NewServiceModal
          catalog={catalog} initial={editingSvc}
          onClose={() => { setEditingSvc(null); camposSvc.limpiar() }}
          onSave={d => updateSvc({id: editingSvc.id, ...d})}
          isPending={false} LS={LS} errorDe={camposSvc.de} />
      )}
      {traduciendo && (
        <DialogoDeVersionesDeContenido tipo={traduciendo.tipo} id={traduciendo.id} etiqueta={traduciendo.etiqueta} onClose={() => setTraduciendo(null)} />
      )}
    </div>
  )
}

function NewCategoryModal({ onClose, onSave, isPending, IS, LS, initial, errorDe }: { onClose: () => void; onSave: (d: Record<string, unknown>) => void; isPending: boolean; IS: string; LS: string; initial?: Cat | null; errorDe?: (campo: string) => string | undefined }) {
  const idCampo = useId()
  const t = useAppT()
  const [form, setForm] = useState({
    name: initial?.name || '', description: initial?.description || '',
    icon: initial?.icon || '', color: initial?.color || COLOR_CATEGORIA_POR_DEFECTO
  })
  const set = (k: string) => (e: ChangeEvent<HTMLInputElement>) => setForm(f => ({...f, [k]: e.target.value}))
  return (
    <Modal open title={initial ? t('sd_cfg.cfg_cat_edit') : t('sd_cfg.cfg_cat_new')} onClose={onClose}>
      <div className="u-stack-14">
        <div className="sdcfg-cat-grid">
          <Input id={`${idCampo}-1`} label={t('common.name')} required value={form.name} onChange={set('name')} error={errorDe?.('name')} />
          <div><Input label={t('config.icono')} id={`${idCampo}-2`} value={form.icon} onChange={set('icon')} className="sdcfg-input--icon" /></div>
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

function NewServiceModal({ catalog, onClose, onSave, isPending, LS, initial, errorDe }: { catalog: Cat[]; onClose: () => void; onSave: (d: Record<string, unknown>) => void; isPending: boolean; LS: string; initial?: Svc | null; errorDe?: (campo: string) => string | undefined }) {
  const idCampo = useId()
  const t = useAppT()
  const { data: usuarios = [] } = useListaDeUsuarios()
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
    // Rev. 193 (clientes internos): precio interno por petición atendida; vacío = sin precio.
    internal_price: initial?.internal_price != null ? String(initial.internal_price) : '',
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
        <div className="u-col-full"><Input id={`${idCampo}-1`} label={t('common.name')} required value={form.name} onChange={set('name')} error={errorDe?.('name')} /></div>
        <div>
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className={LS}>{t('service_desk.tab_catalog')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-2`} value={form.category_id} onChange={set('category_id')} className="sdcfg-sel">
            {catalog.map((c: Cat) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
        </div>
        <div>
          <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className={LS}>{t('service_desk.svc_ticket_type')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-3`} value={form.ticket_type} onChange={set('ticket_type')} className="sdcfg-sel">
            {['incident','service_request','change','question'].map(tk => <option key={tk} value={tk}>{etiquetaSd('type', tk)}</option>)}
          </Select>
        </div>
        <div>
          <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className={LS}>{t('service_desk.svc_default_priority')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-4`} value={form.default_priority} onChange={set('default_priority')} className="sdcfg-sel">
            {['p1_critical','p2_high','p3_medium','p4_low'].map(p => <option key={p} value={p}>{PRIORITY_LABEL_MAP[p]}</option>)}
          </Select>
        </div>
        <div className="sdcfg-grid2-8">
          <Input id={`${idCampo}-5`} label={t('service_desk.sla_response_h')} type="number" value={form.sla_response_hours} onChange={set('sla_response_hours')} error={errorDe?.('sla_response_hours')} />
          <Input id={`${idCampo}-6`} label={t('service_desk.sla_resolution_h')} type="number" value={form.sla_resolution_hours} onChange={set('sla_resolution_hours')} error={errorDe?.('sla_resolution_hours')} />
        </div>
        <div>
          <Input id={`${idCampo}-7`} label={t('sd_cfg.svc_internal_price')} type="number" min={0} step="any" value={form.internal_price}
            onChange={set('internal_price')} error={errorDe?.('internal_price')} hint={t('sd_cfg.svc_internal_price_hint')} />
        </div>
        <div className="u-row-center-10">
          <Checkbox id="svc_visible" aria-label={t('sd_cfg.svc_visible')} checked={!!form.is_visible_to_clients} onChange={v => setForm(f => ({...f, is_visible_to_clients: v}))} label={t('sd_cfg.svc_visible')} />
        </div>
        <div className="u-row-center-10">
          <Checkbox id="req_appr" checked={!!form.requires_approval} onChange={v => setForm(f => ({...f, requires_approval: v}))} label={t('service_desk.svc_requires_approval')} />
        </div>
        {form.requires_approval && (
          <div className="u-col-full">
            <label className={LS} htmlFor="svc_appr_mode">{t('sd_mercado.modo_aprobacion')}</label>
            <Select suelto placeholder={false} id="svc_appr_mode" value={form.approval_mode} onChange={set('approval_mode')} className="sdcfg-sel">
              <option value="single">{t('sd_mercado.aprobacion_single')}</option>
              <option value="engine">{t('sd_mercado.aprobacion_engine')}</option>
            </Select>
            {form.approval_mode === 'engine' && <span className="u-text3-xs">{t('sd_mercado.aprobacion_engine_hint')}</span>}
          </div>
        )}
        {form.requires_approval && form.approval_mode === 'engine' && (
          <div className="u-col-full">
            <label className={LS} htmlFor="svc_appr_wf">{t('sd_mercado.flujo_aprobacion')}</label>
            <Select suelto placeholder={false} id="svc_appr_wf" value={form.approval_workflow_id} onChange={set('approval_workflow_id')} className="sdcfg-sel">
              <option value="">{t('sd_mercado.flujo_por_condiciones')}</option>
              {flujos.filter(f => f.is_active && f.entity_type === 'catalog_request').map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
            </Select>
          </div>
        )}
        {form.requires_approval && (
          <div className="u-col-full">
            <label className={LS} htmlFor="svc_approver">{t(form.approval_mode === 'engine' ? 'sd_mercado.aprobador_respaldo' : 'sd_cfg.svc_approver')}{form.approval_mode === 'engine' ? '' : ' *'}</label>
            <Select suelto placeholder={false} id="svc_approver" aria-label={t('sd_cfg.svc_approver')} value={form.approval_user_id} onChange={set('approval_user_id')} className="sdcfg-sel">
              <option value="">—</option>
              {usuarios.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
            </Select>
          </div>
        )}
        <div className="sdcfg-full-stack" role="group" aria-labelledby={`${idCampo}-ff-et`}>
          <span id={`${idCampo}-ff-et`} className={LS}>{t('sd_cfg.ff_tasks')}</span>
          <span className="u-text3-xs">{t('sd_cfg.ff_help')}</span>
          {tareas.map((tarea, i) => (
            <div key={i} className="u-wrap-8">
              <Input aria-label={t('sd_cfg.ff_title')} placeholder={t('sd_cfg.ff_title')} value={tarea.title} onChange={e => setTareas(ts => ts.map((x, j) => j === i ? { ...x, title: e.target.value } : x))} className="sdcfg-input--flex2" />
              <Select suelto placeholder={false} aria-label={t('sd_cfg.oc_queue')} value={tarea.group_id} className="sdcfg-input--flex1"
                onChange={e => setTareas(ts => ts.map((x, j) => j === i ? { ...x, group_id: e.target.value } : x))}>
                <option value="">—</option>
                {colas.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </Select>
              <Select suelto placeholder={false} aria-label={t('sd_mercado.tarea_persona')} value={tarea.assignee_user_id || ''} className="sdcfg-input--flex1"
                onChange={e => setTareas(ts => ts.map((x, j) => j === i ? { ...x, assignee_user_id: e.target.value || null } : x))}>
                <option value="">{t('sd_mercado.tarea_persona_auto')}</option>
                {usuarios.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
              </Select>
              <Input type="number" min={0} step={0.5} aria-label={t('sd_mercado.tarea_sla')} placeholder={t('sd_mercado.tarea_sla')} value={tarea.sla_hours ?? ''} onChange={e => setTareas(ts => ts.map((x, j) => j === i ? { ...x, sla_hours: e.target.value } : x))} className="sdcfg-input--flex1" />
              <Input type="number" min={1} aria-label={t('sd_mercado.tarea_etapa')} placeholder={t('sd_mercado.tarea_etapa')} value={tarea.stage ?? 1} onChange={e => setTareas(ts => ts.map((x, j) => j === i ? { ...x, stage: e.target.value } : x))} className="sdcfg-input--flex1" />
              <Button size="xs" variant="ghost" icon={<X size={14} />} title={t('common.delete')} onClick={() => setTareas(ts => ts.filter((_, j) => j !== i))} />
            </div>
          ))}
          <div><Button size="sm" variant="secondary" icon={<Plus size={14} />} onClick={() => setTareas(ts => [...ts, { title: '', group_id: '', stage: 1 }])}>{t('sd_cfg.ff_add')}</Button></div>
        </div>
        <div className="sdcfg-full-actions">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => onSave({
            ...form, approval_user_id: form.requires_approval && form.approval_user_id ? form.approval_user_id : null,
            internal_price: form.internal_price.trim() === '' ? null : Number(form.internal_price),
            approval_workflow_id: form.requires_approval && form.approval_mode === 'engine' && form.approval_workflow_id ? form.approval_workflow_id : null,
            fulfillment_tasks: tareas.map(x => ({ ...x, sla_hours: x.sla_hours === '' || x.sla_hours == null ? null : Number(x.sla_hours), stage: Number(x.stage || 1) })),
          })}
            disabled={isPending || !form.name || faltaAprobador || !tareasValidas} loading={isPending}>{initial ? t('common.save') : t('sd_cfg.cfg_svc_new')}</Button>
        </div>
      </div>
    </Modal>
  )
}

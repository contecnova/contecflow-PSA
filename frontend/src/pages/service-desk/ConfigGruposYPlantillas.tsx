// Grupos de agentes y plantillas de ticket del Service Desk. 23-11-2026: troceado de ConfigTab sin cambio de comportamiento.
import { useState, useId } from 'react'
import type { ChangeEvent } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { useListaDeUsuarios } from '../../hooks/useListas'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { useToast } from '../../context/ToastContext'
import { useAppT } from '../../i18n/AppLangContext'
import { FileText, Pencil, Plus, Star, Trash2, Users, X } from 'lucide-react'
import { Button, Spinner, EmptyState, Modal, StatusBadge, Pulsable, Select, Input, Textarea } from '../../components/ui'
import { sdGroupsApi, sdTemplatesApi } from '../../services/api'
import { PBadge, etiquetaSd } from './sdUtils'
import { type Group, LS_BASE, type Member, PRIORITY_LABEL_MAP, type Template, type User } from './ConfigTabComun'

// ── Groups Config ─────────────────────────────────────────────────────────────
export function GroupsConfig() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [showNew, setShowNew] = useState(false)

  const { data: groups = [], isLoading } = useQuery<Group[]>({
    queryKey: ['sd-groups'],
    queryFn: () => sdGroupsApi.list().then(r => r.data),
  })
  const { data: users = [] } = useListaDeUsuarios()
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
  // 23-11-2026 (04b M4): quitar a una persona de un grupo pide confirmación.
  const quitarMiembro = (gid: string, uid: string, nombre: string) => openConfirmGlobal({
    message: t('config.confirmar_quitar_miembro', { name: nombre }),
    confirmLabel: t('config.quitar_miembro_btn'),
    danger: true,
    onConfirm: () => removeMember({ gid, uid }),
  })

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
                    <Select suelto placeholder={false} value="" onChange={e => { if(e.target.value) addMember({gid:g.id, uid:e.target.value}) }}
                      className="sdcfg-input--auto" aria-label={t('sd_cfg.cfg_add_member')}>
                      <option value="" disabled>{t('sd_cfg.cfg_add_member')}</option>
                      {available.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
                    </Select>
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
                    <Pulsable onClick={() => quitarMiembro(g.id, m.id, m.full_name ?? '')} aria-label={t('config.quitar_miembro', { name: m.full_name ?? '' })}
                      title={t('config.quitar_miembro', { name: m.full_name ?? '' })} className="sdcfg-member__remove"><X size={12} aria-hidden="true" /></Pulsable>
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
            <NewGroupForm LS={LS} onSave={createGroup} isPending={isPending} onClose={() => setShowNew(false)} />
          </div>
        </Modal>
      )}
      {editing && (
        <Modal open title={t('sd_cfg.cfg_group_edit')} onClose={() => setEditing(null)}>
          <div className="u-stack-14">
            <NewGroupForm LS={LS} initial={editing}
              onSave={d => updateGroup({id: editing.id, ...d})}
              isPending={false} onClose={() => setEditing(null)} />
          </div>
        </Modal>
      )}
    </div>
  )
}

function NewGroupForm({ LS, onSave, isPending, onClose, initial }: { LS: string; onSave: (d: Record<string, unknown>) => void; isPending: boolean; onClose: () => void; initial?: Group | null }) {
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
      <div><Input label={<>{t('common.name')} *</>} id={`${idCampo}-1`} value={form.name} onChange={set('name')} /></div>
      <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className={LS}>{t('service_desk.groups_support_level')}</label>
        <Select suelto placeholder={false} id={`${idCampo}-2`} value={form.support_level} onChange={set('support_level')} className="sdcfg-sel">
          {['l1','l2','l3'].map(v =>
            <option key={v} value={v}>{t(`config.nivel_${v}`)}</option>)}
        </Select>
      </div>
      <div><Input label={t('common.description')} id={`${idCampo}-3`} value={form.description} onChange={set('description')} /></div>
      <div><Input label={t('sd_cfg.ola_hours')} id="grp-ola" type="number" min={0} step={0.5} value={form.ola_hours} onChange={set('ola_hours')} aria-invalid={!olaValido} aria-describedby="grp-ola-hint" />
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
export function TemplatesConfig() {
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
          <NewTemplateForm LS={LS} onSave={create} isPending={isPending} onClose={() => setShowNew(false)} />
        </Modal>
      )}
      {editing && (
        <Modal open title={t('sd_cfg.cfg_tmpl_edit')} onClose={() => setEditing(null)}>
          <NewTemplateForm LS={LS} initial={editing}
            onSave={d => update({id: editing.id, ...d})}
            isPending={false} onClose={() => setEditing(null)} />
        </Modal>
      )}
    </div>
  )
}

function NewTemplateForm({ LS, onSave, isPending, onClose, initial }: { LS: string; onSave: (d: Record<string, unknown>) => void; isPending: boolean; onClose: () => void; initial?: Template | null }) {
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
      <div><Input label={<>{t('common.name')} *</>} id={`${idCampo}-1`} value={form.name} onChange={set('name')} /></div>
      <div className="u-grid2-10">
        <div>
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className={LS}>{t('service_desk.svc_ticket_type')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-2`} value={form.ticket_type} onChange={set('ticket_type')} className="sdcfg-sel">
            {['incident','service_request','change','question','problem'].map(tk =>
              <option key={tk} value={tk}>{etiquetaSd('type', tk)}</option>)}
          </Select>
        </div>
        <div>
          <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className={LS}>{t('service_desk.templates_priority')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-3`} value={form.default_priority} onChange={set('default_priority')} className="sdcfg-sel">
            {['p1_critical','p2_high','p3_medium','p4_low'].map(p =>
              <option key={p} value={p}>{PRIORITY_LABEL_MAP[p]}</option>)}
          </Select>
        </div>
      </div>
      <div>
        <Textarea label={t('sd_cfg.cfg_tmpl_body')} id={`${idCampo}-4`} value={form.description_template} onChange={set('description_template')} rows={4} placeholder={t('config.texto_de_la_plantilla_de_descripcion')} />
      </div>
      <div className="u-actions-10">
        <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
        <Button onClick={() => onSave(form)} disabled={isPending || !form.name} loading={isPending}>{initial ? t('common.save') : t('sd_cfg.cfg_tmpl_new')}</Button>
      </div>
    </div>
  )
}

// Respuestas rapidas y anuncios del Service Desk. 23-11-2026: troceado de ConfigTab sin cambio de comportamiento.
import { useState, useId } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { extractErr, fmtDateTime } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { useToast } from '../../context/ToastContext'
import { useAppT } from '../../i18n/AppLangContext'
import { Eye, Languages, Megaphone, MessageSquareText, Pencil, Plus, Trash2 } from 'lucide-react'
import { Button, Spinner, EmptyState, Modal, StatusBadge, Select, Checkbox, Input, FormField, useErroresDeCampo, Textarea, IconButton } from '../../components/ui'
import { DialogoDeVersionesDeContenido } from '../../components/traduccion/VersionesDeContenidoPanel'
import type { StatusBadgeKind } from '../../components/ui/StatusBadge'
import { sdCannedApi, sdAnnouncementsApi } from '../../services/api'
import DateInput from '../../components/ui/DateInput'
import { type Ann, type Canned, type CannedForm, type Traduciendo, useAvisoDeDesactualizadas } from './ConfigTabComun'

// ── Canned Responses Manager ──────────────────────────────────────────────────
export function CannedResponsesManager() {
  const idCampo = useId()
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [form, setForm] = useState<CannedForm>({ title: '', body: '', category: '', shortcut: '' })
  const [editing, setEditing] = useState<string | null>(null)
  const [editForm, setEditForm] = useState<Partial<CannedForm>>({})

  const { data: responses = [], isLoading } = useQuery<Canned[]>({
    queryKey: ['canned-responses-all'],
    queryFn: () => sdCannedApi.list(undefined).then(r => r.data),
  })

  const { mutate: create } = useMutation({
    mutationFn: (d: Record<string, unknown>) => sdCannedApi.create(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['canned-responses-all'] }); setForm({ title:'', body:'', category:'', shortcut:'' }) },
    onError: (e: unknown) => toast.error(extractErr(e, t('config.error'))),
  })
  const { mutate: update } = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<CannedForm> }) => sdCannedApi.update(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['canned-responses-all'] }); setEditing(null) },
    onError: (e: unknown) => toast.error(extractErr(e, t('config.error'))),
  })
  const { mutate: del } = useMutation({
    mutationFn: (id: string) => sdCannedApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['canned-responses-all'] }),
    onError: (e: unknown) => toast.error(extractErr(e, t('config.error'))),
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
          <div><Input label={<>{t('common.name')} *</>} id={`${idCampo}-${r.id}-edit895`} value={editForm.title||''} onChange={e=>setEditForm(f=>({...f,title:e.target.value}))} /></div>
          <div><Input label={t('sd_cfg.cfg_category')} id={`${idCampo}-${r.id}-edit897`} value={editForm.category||''} onChange={e=>setEditForm(f=>({...f,category:e.target.value}))} /></div>
        </div>
        <div className="sdcfg-mb-8"><Input label={t('sd_cfg.cfg_shortcut')} id={`${idCampo}-${r.id}-edit900`} value={editForm.shortcut||''} onChange={e=>setEditForm(f=>({...f,shortcut:e.target.value}))} /></div>
        <div className="u-mb-10"><Textarea label={<>{t('service_desk.canned_body_lbl')} *</>} id={`${idCampo}-${r.id}-edit902`} value={editForm.body||''} onChange={e=>setEditForm(f=>({...f,body:e.target.value}))} rows={4} /></div>
              <div className="u-row-8">
                <Button size="sm" onClick={() => update({ id:r.id, data:editForm })} disabled={!editForm.title||!editForm.body}>{t('common.save')}</Button>
                <Button size="sm" variant="secondary" onClick={() => setEditing(null)}>{t('common.cancel')}</Button>
              </div>
            </div>
          ) : (
            <div key={r.id} className="sdcfg-canned-row">
              <div className="u-flex1-min0">
                <div className="u-base-700">{r.title}
                  {r.shortcut && <span className="ds-codigo sdcfg-shortcut">{r.shortcut}</span>}
                  {r.category && <span className="sdcfg-category">{r.category}</span>}
                </div>
                <div className="sdcfg-canned-body">{r.body?.slice(0,100)}</div>
              </div>
              <div className="sdcfg-row-actions">
                <IconButton variante="caja" ariaLabel={`${t('common.edit')} ${r.title}`} onClick={() => { setEditing(r.id); setEditForm({title:r.title,body:r.body,category:r.category||'',shortcut:r.shortcut||''}) }}><Pencil size={12} /></IconButton>
                <IconButton variante="caja" tono="peligro" ariaLabel={`${t('common.delete')} ${r.title}`} onClick={() => { openConfirmGlobal({ message: t('config.confirmar_eliminar_x', { title: r.title }), onConfirm: () => del(r.id), danger: true }) }}><Trash2 size={12} /></IconButton>
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
          <div><Input label={<>{t('common.name')} *</>} id={`${idCampo}-1`} value={form.title} onChange={e=>setForm(f=>({...f,title:e.target.value}))} /></div>
          <div><Input label={t('sd_cfg.cfg_category')} id={`${idCampo}-2`} value={form.category} onChange={e=>setForm(f=>({...f,category:e.target.value}))} /></div>
        </div>
        <div className="sdcfg-mb-8"><Input label={t('sd_cfg.cfg_shortcut')} id={`${idCampo}-3`} value={form.shortcut} onChange={e=>setForm(f=>({...f,shortcut:e.target.value}))} /></div>
        <div className="u-mb-12"><Textarea label={<>{t('service_desk.canned_body_lbl')} *</>} id={`${idCampo}-4`} value={form.body} onChange={e=>setForm(f=>({...f,body:e.target.value}))} rows={4} placeholder={t('config.texto_de_la_respuesta_enlatada')} /></div>
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
  const VACIO = { title:'', body:'', type:'info', show_to_clients:true, starts_at:'', ends_at:'' }
  const [form, setForm] = useState(VACIO)
  // 17-11-2026: un aviso se puede corregir (sus traducciones quedan desactualizadas) y traducir.
  const [editando, setEditando] = useState<string | null>(null)
  const [traduciendo, setTraduciendo] = useState<Traduciendo | null>(null)
  const campos = useErroresDeCampo()
  const avisarDesactualizadas = useAvisoDeDesactualizadas()
  const cerrar = () => { setShowCreate(false); setEditando(null); setForm(VACIO); campos.limpiar() }
  const editar = (a: Ann) => {
    setForm({ title: a.title, body: a.body, type: a.type || 'info', show_to_clients: a.show_to_clients, starts_at: (a.starts_at ?? '').replace(' ', 'T'), ends_at: (a.ends_at ?? '').replace(' ', 'T') })
    setEditando(a.id); setShowCreate(true)
  }

  const TYPE_KIND: Record<string, StatusBadgeKind> = { info: 'accent', warning: 'warning', outage: 'danger', maintenance: 'purple' }
  const ANN_TYPES = ['info','warning','outage','maintenance']

  const { data: anns = [], isLoading } = useQuery<Ann[]>({
    queryKey: ['sd-announcements'],
    queryFn: () => sdAnnouncementsApi.list().then(r => r.data),
  })
  const { mutate: create, isPending: creating } = useMutation({
    mutationFn: (d: Record<string, unknown>) => sdAnnouncementsApi.create(d),
    onMutate: () => campos.limpiar(),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sd-announcements'] }); cerrar(); toast.success(t('service_desk.ann_published')) },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) },
  })
  const { mutate: update, isPending: updating } = useMutation({
    mutationFn: ({ id, ...d }: { id: string } & Record<string, unknown>) => sdAnnouncementsApi.update(id, d),
    onMutate: () => campos.limpiar(),
    onSuccess: r => { qc.invalidateQueries({ queryKey: ['sd-announcements'] }); cerrar(); toast.success(t('traduccion_admin.portal_aviso_guardado')); avisarDesactualizadas(r.data?.translations_outdated) },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) },
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
                  <IconButton variante="caja" ariaLabel={`${t('common.edit')} ${a.title}`} onClick={() => editar(a)}><Pencil size={12} /></IconButton>
                  <IconButton variante="caja" ariaLabel={t('traduccion_admin.portal_versiones_de', { nombre: a.title })}
                    onClick={() => setTraduciendo({ tipo: 'announcement', id: a.id, etiqueta: a.title })}><Languages size={12} /></IconButton>
                  <IconButton variante="caja" tono="peligro" ariaLabel={t('config.desactivar_anuncio_x', { title: a.title })} onClick={() => { openConfirmGlobal({ message: t('config.confirmar_desactivar_anuncio'), onConfirm: () => del(a.id) }) }}><Trash2 size={12} /></IconButton>
                </div>
              ))}
            </div>
          )
      }
      {showCreate && (
        <Modal open title={editando ? t('traduccion_admin.portal_aviso_editar') : t('sd_cfg.cfg_ann_new')} onClose={cerrar}>
          <div className="sdcfg-ann-form">
            <div className="u-col-full"><Input id={`${idCampo}-1`} label={t('sd_cfg.cfg_ann_title')} required value={form.title} onChange={e=>{ campos.limpiar('title'); setForm(f=>({...f,title:e.target.value})) }} error={campos.de('title')} /></div>
            <Select label={t('sd_mercado.tipo')} placeholder={false} id={`${idCampo}-2`} value={form.type} onChange={e=>setForm(f=>({...f,type:e.target.value}))}>
                {ANN_TYPES.map(tp=><option key={tp} value={tp}>{t(`config.ann_tipo_${tp}`)}</option>)}
              </Select>
            <div className="sdcfg-ann-check">
              <Checkbox id="showCl" checked={form.show_to_clients} onChange={v=>setForm(f=>({...f,show_to_clients:v}))} label={t('service_desk.ann_visible_clients')} />
            </div>
            <DateInput label={t('service_desk.ann_starts')} id={`${idCampo}-3`} withTime value={form.starts_at} onChange={e=>setForm(f=>({...f,starts_at:e.target.value}))} />
            <DateInput label={t('service_desk.ann_ends')} id={`${idCampo}-4`} withTime value={form.ends_at} onChange={e=>setForm(f=>({...f,ends_at:e.target.value}))} />
            <div className="u-col-full"><FormField label={t('service_desk.ann_message')} required error={campos.de('body')}><Textarea id={`${idCampo}-5`} value={form.body} onChange={e=>{ campos.limpiar('body'); setForm(f=>({...f,body:e.target.value})) }} rows={4} /></FormField></div>
          </div>
          <div className="u-actions-10">
            <Button variant="secondary" onClick={cerrar}>{t('common.cancel')}</Button>
            {editando
              ? <Button onClick={()=>update({ id: editando, ...form, starts_at: form.starts_at || null, ends_at: form.ends_at || null })} loading={updating} disabled={!form.title||!form.body||updating}>{t('common.save')}</Button>
              : <Button onClick={()=>create(form)} loading={creating} disabled={!form.title||!form.body||creating}>{t('sd_cfg.cfg_ann_publish')}</Button>}
          </div>
        </Modal>
      )}
      {traduciendo && (
        <DialogoDeVersionesDeContenido tipo={traduciendo.tipo} id={traduciendo.id} etiqueta={traduciendo.etiqueta} onClose={() => setTraduciendo(null)} />
      )}
    </div>
  )
}

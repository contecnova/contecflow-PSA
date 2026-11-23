// Pestañas de webhooks, GDPR y email de Enterprise. 23-11-2026: troceado de EnterprisePage sin cambio de comportamiento.
import { useAppLang, useAppT } from '../i18n/AppLangContext'
import { useState, useId } from 'react'
import type { CSSProperties } from 'react'
import { openConfirmGlobal, pedirTexto } from '../context/ConfirmContext'
import { extractErr, downloadBlob, fmtDate, fmtDateTime } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useListaDeUsuarios } from '../hooks/useListas'
import { esFichaCompleta, webhooksApi, autoWorkflowsApi, gdprApi, emailApi, apiUrl } from '../services/api'
import type { SolicitudRgpd } from '../services/api/tipos'
import { Button, Modal, Spinner, EmptyState, IconButton, Select, Input, Textarea } from '../components/ui'
import Pagination from '../components/ui/Pagination'
import type { AxiosResponse } from 'axios'
import { History, Mail, Plus, ShieldCheck, Trash2, Webhook } from 'lucide-react'
import { type AltaProps, GDPR_POR_PAGINA, type GdprForm, type NewTemplateForm, type SendEmailForm, type WebhookForm, etiq } from './EnterpriseComun'

export function WebhooksTab({ showCreate, setShowCreate }: AltaProps) {
  const { t } = useAppLang()
  const idCampo = useId()
  const traducir = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [showLogs, setShowLogs] = useState<string|null>(null)
  const [form, setForm] = useState({ name:'', slug:'', workflow_id:'' })

  const { data: triggers = [], isLoading } = useQuery({ queryKey:['wh-triggers'], queryFn:() => webhooksApi.list().then(r => r.data) })
  const { data: workflows = [] } = useQuery({ queryKey:['workflows-ent'], queryFn:() => autoWorkflowsApi.list().then(r => r.data) })
  const { data: logs = [] } = useQuery({ queryKey:['wh-logs', showLogs], queryFn:() => webhooksApi.logs(showLogs).then(r => r.data), enabled:!!showLogs })

  const { mutate: create, isPending } = useMutation({
    mutationFn: (d: WebhookForm) => webhooksApi.create(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['wh-triggers'] }); setShowCreate(false) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: del } = useMutation({
    mutationFn: (id: string) => webhooksApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['wh-triggers'] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  return (
    <div>
      <div className="ent-card">
        {traducir('enterprise.los_webhooks_entrantes_permiten_que_sistemas_externos')}
      </div>
      {isLoading ? <Spinner /> : triggers.length === 0 ? (
        <EmptyState icon={<Webhook size={28} />} title={traducir('enterprise.sin_webhooks')} description={t('pagina_ent.crea_el_primer_webhook_entrante_para')}
          action={<Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{traducir('enterprise.nuevo_webhook')}</Button>} />
      ) : triggers.map(trg => (
        <div key={trg.id} className="enterprise-page-e1">
          <div className="ent-row-2">
            <div className="u-min0">
              <div className="ent-box">{trg.name}</div>
              <code className="ds-codigo ent-card-2">POST {apiUrl(trg.endpoint)}</code>
              <span className="ent-label">{t('pagina_ent.disparos', { n: trg.fire_count })}</span>
            </div>
            <div className="u-row-8">
              <Button size="sm" variant="secondary" icon={<History size={14} />} onClick={() => setShowLogs(showLogs === trg.id ? null : trg.id)}>
                {showLogs === trg.id ? t('pagina_ent.ocultar') : t('pagina_ent.logs')}
              </Button>
              <IconButton className="ent-borrar" onClick={() => { openConfirmGlobal({ message: t('pagina_ent.eliminar_webhook'), confirmLabel: t('pagina_ent.eliminar_boton'), onConfirm: () => del(trg.id), danger: true }) }} ariaLabel={t('pagina_ent.eliminar_webhook_aria', { name: trg.name })}><Trash2 size={14} aria-hidden /></IconButton>
            </div>
          </div>
          {showLogs === trg.id && (
            <div className="ent-box-2">
              {logs.length === 0 ? <div className="u-text3-sm">{traducir('enterprise.sin_llamadas_aun')}</div> :
                logs.slice(0,5).map(l => (
                  <div key={l.id} className="ent-row-3">
                    <span className={`${l.status === 'ok' ? 'enterpri-sx1' : 'enterpri-sx2'}`}>{l.status === 'ok' ? t('pagina_ent.llamada_ok') : t('pagina_ent.llamada_error')}</span>
                    <span className="u-text2">{fmtDateTime(l.received_at)}</span>
                    <span className="ent-label-2">{l.payload_preview}</span>
                  </div>
                ))
              }
            </div>
          )}
        </div>
      ))}
      {showCreate && (
        <Modal open title={traducir('enterprise.nuevo_webhook_2')} onClose={() => setShowCreate(false)} width={480}>
          <div className="u-stack-14">
            <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="enterprise-page-e16">{t('pagina_ent.nombre')}</label><Input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.name} onChange={e => setForm(f => ({...f, name:e.target.value}))} inputClassName="enterprise-page-e17" /></div>
            <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="enterprise-page-e16">{t('pagina_ent.slug_url')}</label><Input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.slug} onChange={e => setForm(f => ({...f, slug:e.target.value.toLowerCase().replace(/\s+/g,'-')}))} placeholder="mi-webhook" inputClassName="enterprise-page-e17" /></div>
            <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="enterprise-page-e16">{t('pagina_ent.workflow')}</label>
              <Select suelto placeholder={false} id={`${idCampo}-2`} value={form.workflow_id} onChange={e => setForm(f => ({...f, workflow_id:e.target.value}))} className="enterprise-page-e17">
                <option value="">{traducir('enterprise.sin_workflow')}</option>
                {workflows.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
              </Select>
            </div>
            <div className="ent-card-3">
              {t('pagina_ent.url')}{' '}<code className="ds-codigo">POST {apiUrl(`/webhooks/fire/${form.slug || 'tu-slug'}`)}</code>
            </div>
            <div className="u-actions-10">
              <Button variant="secondary" onClick={() => setShowCreate(false)}>{t('pagina_ent.cancelar')}</Button>
              <Button onClick={() => create(form)} disabled={isPending || !form.name || !form.slug}>{t('pagina_ent.crear')}</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

export function GDPRTab({ showCreate, setShowCreate }: AltaProps) {
  const { t } = useAppLang()
  const idCampo = useId()
  const traducir = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [form, setForm] = useState<GdprForm>({ request_type:'erasure', subject_user_id:'', subject_email:'', notes:'' })

  const [page, setPage] = useState(1)
  // Paginado en el servidor: el interceptor deja la lista en `data` y el total en `meta.total`.
  const { data: pagina, isLoading } = useQuery<{ items: SolicitudRgpd[]; total: number }>({
    queryKey: ['gdpr', page],
    queryFn: () => gdprApi.list({ page, page_size: GDPR_POR_PAGINA }).then((r: AxiosResponse<SolicitudRgpd[]> & { meta?: { total?: number } }) =>
      ({ items: r.data, total: Number(r.meta?.total ?? r.data.length) })),
  })
  const requests = pagina?.items ?? []
  const paginas = Math.max(1, Math.ceil((pagina?.total ?? 0) / GDPR_POR_PAGINA))
  // 23-11-2026 (04 A8): lista compartida de personas (antes `['users']` con respuesta cruda).
  const { data: users = [] } = useListaDeUsuarios()

  const { mutate: create, isPending } = useMutation({
    mutationFn: (d: GdprForm) => gdprApi.create(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['gdpr'] }); setShowCreate(false) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: process } = useMutation({
    mutationFn: (id: string) => gdprApi.process(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['gdpr'] }); toast.success(t('pagina_ent.rgpd_procesada')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  // Revisión GRC 16-11-2026: rechazo motivado (el estado existía y nada lo ponía)
  // y descarga de la copia de acceso/portabilidad (se generaba y no se veía).
  const { mutate: reject } = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) => gdprApi.reject(id, reason),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['gdpr'] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const rechazar = async (id: string) => {
    const reason = await pedirTexto({ title: t('pagina_ent.rgpd_rechazar'), message: t('pagina_ent.rgpd_motivo_rechazo'), label: t('pagina_ent.rgpd_motivo_rechazo'), multiline: true, confirmLabel: t('pagina_ent.rgpd_rechazar') })
    if (reason && reason.trim().length >= 3) reject({ id, reason: reason.trim() })
  }
  const descargar = async (id: string) => {
    try { downloadBlob((await gdprApi.exportFile(id)).data, `gdpr-${id}.json`) }
    catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) }
  }

  const TYPE_LABELS: Record<string,string> = { erasure:t('pagina_ent.derecho_al_olvido'), portability:t('pagina_ent.portabilidad'), access:t('pagina_ent.acceso'), rectification:t('pagina_ent.rectificacion') }
  const STATUS_COLORS: Record<string,string> = { pending:'var(--warning)', processing:'var(--accent)', completed:'var(--success)', rejected:'var(--danger)' }

  return (
    <div>
      <div className="ent-card-4">
        {traducir('enterprise.gestion_de_solicitudes_rgpd_plazo_maximo_de')}
      </div>
      {isLoading ? <Spinner /> : requests.length === 0 ? (
        <EmptyState icon={<ShieldCheck size={28} />} title={traducir('enterprise.sin_solicitudes_rgpd')} description={t('pagina_ent.no_hay_solicitudes_de_privacidad_registradas')}
          action={<Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{traducir('enterprise.nueva_solicitud')}</Button>} />
      ) : (
        <div className="enterprise-page-e2">
          {requests.map(r => (
            <div key={r.id} className="ent-grid">
              <span className="ent-label-3">{TYPE_LABELS[r.request_type] || r.request_type}</span>
              <span className="ent-label-3 enterprise-page-e3" style={{ '--enterprise-page-color': STATUS_COLORS[r.status] || 'var(--text-2)' } as CSSProperties}>{t(`pagina_ent.rgpd_estado_${r.status}`)}</span>
              <div>
                <div className="ent-box-3">{r.subject_deleted ? t('pagina_ent.rgpd_persona_eliminada') : r.subject_name}</div>
                {r.subject_email && <div className="u-text2-xs">{r.subject_email}</div>}
                {r.notes && <div className="u-text2-xs">{r.notes}</div>}
              </div>
              <span className="u-text2-sm">{fmtDate(r.deadline)}</span>
              {(r.status === 'pending' || r.status === 'processing') && (
                <div className="u-row-6">
                  <Button onClick={() => openConfirmGlobal({ message: t('pagina_ent.rgpd_confirmar_procesar'), onConfirm: () => process(r.id), danger: r.request_type === 'erasure' })}>{t('pagina_ent.procesar')}</Button>
                  <Button variant="secondary" onClick={() => rechazar(r.id)}>{t('pagina_ent.rgpd_rechazar')}</Button>
                </div>
              )}
              {r.has_export && <Button variant="secondary" onClick={() => descargar(r.id)}>{t('pagina_ent.rgpd_descargar')}</Button>}
            </div>
          ))}
        </div>
      )}
      {paginas > 1 && <Pagination page={page} totalPages={paginas} onChange={setPage} />}
      {showCreate && (
        <Modal open title={traducir('enterprise.nueva_solicitud_rgpd')} onClose={() => setShowCreate(false)} width={480}>
          <div className="u-stack-14">
            <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="enterprise-page-e16">{t('pagina_ent.tipo')}</label>
              <Select suelto placeholder={false} id={`${idCampo}-1`} value={form.request_type} onChange={e => setForm(f => ({...f, request_type:e.target.value}))} className="enterprise-page-e17">
                <option value="erasure">{traducir('enterprise.derecho_al_olvido_art_17')}</option>
                <option value="portability">{t('pagina_ent.portabilidad_art_20')}</option>
                <option value="access">{t('pagina_ent.acceso_art_15')}</option>
                <option value="rectification">{traducir('enterprise.rectificacion_art_16')}</option>
              </Select>
            </div>
            <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="enterprise-page-e16">{t('pagina_ent.usuario')}</label>
              <Select suelto placeholder={false} id={`${idCampo}-2`} value={form.subject_user_id} onChange={e => setForm(f => ({...f, subject_user_id:e.target.value}))} className="enterprise-page-e17">
                <option value="">{t('pagina_ent.seleccionar')}</option>
                {users.map(u => <option key={u.id} value={u.id}>{u.full_name}{esFichaCompleta(u) ? ` — ${u.email}` : ''}</option>)}
              </Select>
            </div>
            <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="enterprise-page-e16">{traducir('enterprise.email_si_ya_no_existe')}</label>
              <Input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.subject_email} onChange={e => setForm(f => ({...f, subject_email:e.target.value}))} inputClassName="enterprise-page-e17" />
            </div>
            <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="enterprise-page-e16">{t('pagina_ent.notas')}</label>
              <Textarea id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.notes} onChange={e => setForm(f => ({...f, notes:e.target.value}))} rows={3} inputClassName="enterprise-page-e4" />
            </div>
            <div className="u-actions-10">
              <Button variant="secondary" onClick={() => setShowCreate(false)}>{t('pagina_ent.cancelar')}</Button>
              <Button onClick={() => create(form)} disabled={isPending || (!form.subject_user_id && !form.subject_email)}>{t('pagina_ent.crear')}</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

export function EmailTab({ showSend, setShowSend, showCreate, setShowCreate }: AltaProps & { showSend: boolean; setShowSend: (v: boolean) => void }) {
  const { t } = useAppLang()
  const idCampo = useId()
  const traducir = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [sendForm, setSendForm] = useState<SendEmailForm>({ to:'', subject:'', body_html:'', template_id:'' })
  const [newTpl, setNewTpl] = useState<NewTemplateForm>({ name:'', subject:'', body_html:'', category:'automation' })

  const { data: catalog } = useQuery({ queryKey:['email-tpl'], queryFn:() => emailApi.catalog().then(r => r.data) })
  const { data: logs = [] } = useQuery({ queryKey:['email-logs'], queryFn:() => emailApi.logs().then(r => r.data) })

  const { mutate: send, isPending:sending } = useMutation({
    mutationFn: (d: SendEmailForm) => emailApi.send({...d, to:[d.to]}),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['email-logs'] }); setShowSend(false) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: createTpl } = useMutation({
    mutationFn: (d: NewTemplateForm) => emailApi.createTemplate(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['email-tpl'] }); setShowCreate(false) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const allTpl = [...(catalog?.system || []), ...(catalog?.custom || [])]

  return (
    <div>
      <div className="ent-grid-2">
        <div className="u-min0">
          <div className="ent-box-4">{t('pagina_ent.plantillas')}{allTpl.length})</div>
          {allTpl.map(tpl => (
            <div key={tpl.id} className="enterprise-page-e5">
              <div className="ent-row-5">
                <span className="ent-card-5">{etiq(t, 'pagina_ent.tpl_cat', tpl.category)}</span>
                {tpl.is_system && <span className="ent-card-6">{t('pagina_ent.sistema')}</span>}
              </div>
              <div className="ent-box-3">{tpl.name}</div>
              <div className="ent-box-5">{tpl.subject}</div>
            </div>
          ))}
        </div>
        <div>
          <div className="ent-box-4">{traducir('enterprise.historial_de_envios')}</div>
          {logs.length === 0 ? <EmptyState icon={<Mail size={28} />} title={traducir('enterprise.sin_historial_de_envios')} description={t('pagina_ent.todavia_no_se_han_enviado_correos')} /> : (
            <div className="enterprise-page-e6">
              {logs.slice(0,15).map(l => (
                <div key={l.id} className="ent-grid-3">
                  <span className={`ent-label-4 ${l.status === 'sent' ? 'enterpri-sx3' : 'enterpri-sx4'}`}>{etiq(t, 'pagina_ent.envio', l.status)}</span>
                  <div>
                    <div className="ent-label-4">{l.to}</div>
                    <div className="u-text2-xs">{l.subject}</div>
                  </div>
                  <span className="ent-label-5">{fmtDateTime(l.sent_at || l.created_at)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      {showSend && (
        <Modal open title={t('pagina_ent.enviar_email_2')} onClose={() => setShowSend(false)} width={500}>
          <div className="u-stack-14">
            <div><label id={`${idCampo}-et8`} htmlFor={`${idCampo}-8`} className="enterprise-page-e16">{traducir('enterprise.para')}</label><Input id={`${idCampo}-8`} aria-labelledby={`${idCampo}-et8`} value={sendForm.to} onChange={e => setSendForm(f => ({...f, to:e.target.value}))} placeholder={t('pagina_ent.destinatario_empresa_com')} inputClassName="enterprise-page-e17" /></div>
            <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="enterprise-page-e16">{t('pagina_ent.plantilla_2')}</label>
              <Select suelto placeholder={false} id={`${idCampo}-1`} value={sendForm.template_id} onChange={e => setSendForm(f => ({...f, template_id:e.target.value}))} className="enterprise-page-e17">
                <option value="">{traducir('enterprise.sin_plantilla')}</option>
                {allTpl.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
              </Select>
            </div>
            {!sendForm.template_id && <>
              <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="enterprise-page-e16">{t('pagina_ent.asunto')}</label><Input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={sendForm.subject} onChange={e => setSendForm(f => ({...f, subject:e.target.value}))} inputClassName="enterprise-page-e17" /></div>
              <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="enterprise-page-e16">HTML</label><Textarea id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={sendForm.body_html} onChange={e => setSendForm(f => ({...f, body_html:e.target.value}))} rows={4} inputClassName="enterprise-page-e4" /></div>
            </>}
            <div className="u-actions-10">
              <Button variant="secondary" onClick={() => setShowSend(false)}>{t('pagina_ent.cancelar')}</Button>
              <Button onClick={() => send(sendForm)} disabled={sending || !sendForm.to}>{sending ? t('pagina_ent.enviando') : t('pagina_ent.enviar')}</Button>
            </div>
          </div>
        </Modal>
      )}
      {showCreate && (
        <Modal open title={traducir('enterprise.nueva_plantilla_de_email')} onClose={() => setShowCreate(false)} width={560}>
          <div className="u-stack-14">
            <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="enterprise-page-e16">{t('pagina_ent.nombre')}</label><Input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={newTpl.name} onChange={e => setNewTpl(f => ({...f, name:e.target.value}))} inputClassName="enterprise-page-e17" /></div>
            <div><label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="enterprise-page-e16">{t('pagina_ent.asunto_usa')}{' '}{'{{variable}}'})</label><Input id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={newTpl.subject} onChange={e => setNewTpl(f => ({...f, subject:e.target.value}))} inputClassName="enterprise-page-e17" /></div>
            <div><label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} className="enterprise-page-e16">{traducir('enterprise.categoria')}</label>
              <Select suelto placeholder={false} id={`${idCampo}-6`} value={newTpl.category} onChange={e => setNewTpl(f => ({...f, category:e.target.value}))} className="enterprise-page-e17">
                {['automation','alert','report','invoice'].map((c: string) => <option key={c} value={c}>{t(`pagina_ent.tpl_cat_${c}`)}</option>)}
              </Select>
            </div>
            <div><label id={`${idCampo}-et7`} htmlFor={`${idCampo}-7`} className="enterprise-page-e16">{traducir('enterprise.html_del_cuerpo')}</label><Textarea id={`${idCampo}-7`} aria-labelledby={`${idCampo}-et7`} value={newTpl.body_html} onChange={e => setNewTpl(f => ({...f, body_html:e.target.value}))} rows={5} inputClassName="enterprise-page-e4" /></div>
            <div className="u-actions-10">
              <Button variant="secondary" onClick={() => setShowCreate(false)}>{t('pagina_ent.cancelar')}</Button>
              <Button onClick={() => createTpl(newTpl)} disabled={!newTpl.name || !newTpl.subject || !newTpl.body_html}>{t('pagina_ent.crear')}</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

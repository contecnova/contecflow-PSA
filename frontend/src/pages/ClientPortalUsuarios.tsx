// Pestaña de usuarios del portal de cliente (lista, alta y edicion). 23-11-2026: troceado de ClientPortalPage sin cambio de comportamiento.
import React, { useState } from 'react'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { portalClientsApi, projectsApi } from '../services/api'
import { Button, Checkbox, Modal, Spinner, EmptyState, EstadoDeError, useErroresDeCampo, Input } from '../components/ui'
import Pagination from '../components/ui/Pagination'
import { Users, Plus, Check, Pencil, Pause, Play, Archive } from 'lucide-react'
import { AccionesDeUsuarioDelPortal, SeccionContrasenaInicial, contrasenaInicialPorDefecto, datosDeContrasenaInicial, type ContrasenaInicial } from './clients/AccionesUsuarioPortal'
import { fmtDate, extractErr } from '../utils/helpers'
import { useAppT } from '../i18n/AppLangContext'
import { useFormValidation } from '../hooks/useFormValidation'
import { LARGE_PAGE_SIZE } from '../constants/timings'
import { CONTACTOS_POR_PAGINA, type ClientePortal, type DatosAltaCliente, type DatosEdicionCliente, type EventoDeCampo, type FormCliente, type FormEdicionCliente, MensajeError, type PermisoCliente, crearEsquemaAltaCliente, crearEsquemaEdicionCliente, propsDeError } from './ClientPortalComun'

export function ClientUsersTab({ projectId }: { projectId: string }) {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [showCreate, setShowCreate] = useState(false)
  const [editingClient, setEditingClient] = useState<ClientePortal | null>(null)
  const [page, setPage] = useState(1)
  // 23-11-2026 (portal_usuarios): los archivados, solo a petición.
  const [verArchivados, setVerArchivados] = useState(false)
  // Paginada en el servidor (#22): total en meta.total / X-Total-Count.
  const { data: pagina, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['portal-clients', projectId, 'pagina', page, verArchivados],
    queryFn: () => portalClientsApi.list({ project_id: projectId, page, page_size: CONTACTOS_POR_PAGINA, include_archived: verArchivados || undefined }).then(r => ({
      items: r.data,
      total: r.meta?.total ?? Number(r.headers?.['x-total-count'] ?? r.data.length),
    })),
    enabled: !!projectId,
    placeholderData: keepPreviousData,
  })
  const clients = pagina?.items ?? []
  const total = pagina?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / CONTACTOS_POR_PAGINA))
  // Al borrar el último de la última página, o al cambiar de proyecto, no quedarse en una página vacía.
  React.useEffect(() => { if (pagina && page > totalPages) setPage(totalPages) }, [pagina, page, totalPages])
  React.useEffect(() => { setPage(1) }, [projectId, verArchivados])
  const refrescar = () => { void qc.invalidateQueries({ queryKey: ['portal-clients', projectId] }) }
  const { mutate: toggleActive } = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) => portalClientsApi.update(id, { is_active: active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['portal-clients', projectId] }),
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  return (
    <div>
      <div className="u-row-between-mb16">
        <div className="u-text2-base">{total} {t('client_portal.contacts_count')}</div>
        <div className="u-row-8">
          <Checkbox checked={verArchivados} onChange={m => setVerArchivados(m)} label={t('portalacc.ver_archivados')} />
          <Button onClick={() => setShowCreate(true)} icon={<Plus size={14} />}>{t('client_portal.add_contact')}</Button>
        </div>
      </div>
      {isLoading ? <Spinner /> : isError ? <EstadoDeError error={error} onReintentar={() => { void refetch() }} /> : clients.length === 0 ? (
        <EmptyState svgIcon={<Users size={36} />} title={t('client_portal.empty_contacts_title')} description={t('client_portal.empty_contacts_desc')} />
      ) : (
        <div className="u-stack-10">
          {clients.map(c => (
            <div key={c.id} className={c.is_active ? 'cpp-user' : 'cpp-user is-inactive'}>
              <div className="cpp-avatar" aria-hidden="true">
                {c.full_name.split(' ').map(w => w[0]).join('').slice(0, 2)}
              </div>
              <div className="u-flex1">
                <div className="u-md-700">{c.full_name}
                  {c.archived_at && <span className="u-text2-xs cpp-con-icono"> <Archive size={12} aria-hidden="true" />{t('portalacc.archivado_badge')}</span>}
                </div>
                <div className="u-text2-sm">{c.job_title || t('client_portal.role_unknown')} · {c.company || c.project_name} · {c.email}</div>
                <div className="cpp-perms">
                  {c.can_approve_deliverables && <span className="u-success cpp-con-icono"><Check size={12} aria-hidden="true" />{t('client_portal.perm_approve')}</span>}
                  {c.can_request_changes && <span className="u-accent cpp-con-icono"><Check size={12} aria-hidden="true" />{t('client_portal.perm_request')}</span>}
                  {c.can_view_budget && <span className="u-warning cpp-con-icono"><Check size={12} aria-hidden="true" />{t('client_portal.perm_view_budget')}</span>}
                </div>
              </div>
              {c.last_login && <div className="u-text2-xs">{`${t('client_portal.last_access')}: ${fmtDate(c.last_login)}`}</div>}
              <div className="u-row-8">
                {!c.archived_at && <>
                <Button variant="secondary" size="sm" icon={<Pencil size={13} />} onClick={() => setEditingClient(c)}>
                  {t('client_portal.edit')}
                </Button>
                <Button variant="secondary" size="sm" icon={c.is_active ? <Pause size={13} /> : <Play size={13} />}
                  onClick={() => toggleActive({ id: c.id, active: !c.is_active })}>
                  {c.is_active ? t('client_portal.suspend') : t('client_portal.activate')}
                </Button>
                </>}
                {/* Establecer contraseña, reenviar acceso, eliminar o archivar (lo decide el servidor), restaurar y RGPD. */}
                <AccionesDeUsuarioDelPortal usuario={c} onCambio={refrescar} />
              </div>
            </div>
          ))}
        </div>
      )}
      <Pagination page={page} totalPages={totalPages} onChange={setPage} total={total} pageSize={CONTACTOS_POR_PAGINA} maxVisible={5} />
      {showCreate && projectId && <CreateClientModal projectId={projectId} onClose={() => setShowCreate(false)} />}
      {editingClient && <EditClientModal client={editingClient} onClose={() => setEditingClient(null)} onSaved={() => { qc.invalidateQueries({ queryKey: ['portal-clients', projectId] }); setEditingClient(null) }} />}
    </div>
  )
}

function CreateClientModal({ projectId, onClose }: { projectId: string; onClose: () => void }) {
  const idCampo = React.useId()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [form, setForm] = useState<FormCliente>({ full_name: '', email: '', job_title: '', company: '', phone: '', can_approve_deliverables: true, can_request_changes: true, can_view_budget: true, can_view_team: false })
  const [extraProjectIds, setExtraProjectIds] = useState<string[]>([]) // additional projects beyond projectId
  // 23-11-2026 (portal_usuarios): contraseña inicial generada (por defecto) o a mano.
  const [inicial, setInicial] = useState<ContrasenaInicial>(contrasenaInicialPorDefecto)
  const esquema = React.useMemo(() => crearEsquemaAltaCliente(t), [t])
  const validation = useFormValidation(esquema)
  const errs = validation.errors as Record<string, string | undefined>
  const err = (k: string) => propsDeError(errs, k, idCampo)
  const msg = (k: string) => <MensajeError errors={errs} campo={k} idBase={idCampo} />
  const set = (k: keyof FormCliente) => (e: EventoDeCampo) => {
    setForm(f => ({ ...f, [k]: e.target.value }))
    validation.clearFieldError(k)
  }

  const { data: allProjects = [] } = useQuery({
    queryKey: ['projects-list'],
    queryFn: () => projectsApi.list({ page_size: LARGE_PAGE_SIZE }).then(r => r.data),
  })

  const camposC = useErroresDeCampo()
  const msgC = (k: string) => camposC.de(k) ? <div className="u-field-error">{camposC.de(k)}</div> : null
  const { mutate, isPending } = useMutation({
    onMutate: () => camposC.limpiar(),
    mutationFn: (data: DatosAltaCliente & { project_id: string; project_ids: string[] }) => portalClientsApi.create({ ...data, ...datosDeContrasenaInicial(inicial) }),
    // 23-11-2026 (M10 del 04b): la contraseña la genera el servidor y la envía al cliente.
    onSuccess: (r) => {
      validation.setErrors({}); qc.invalidateQueries({ queryKey: ['portal-clients', projectId] })
      if (r.data?.credenciales_enviadas === false) toast.warning(t('portaluserstab.acceso_no_enviado'), 10000)
      else if (r.data?.credenciales_enviadas === true) toast.success(t('portaluserstab.acceso_enviado'))
      else toast.success(t('portaluserstab.acceso_creado'))
      onClose()
    },
    onError: (e: unknown) => { if (!camposC.recoger(e)) toast.error(extractErr(e, t('ai.generic_error'))) },
  })

  const allProjectIds = [...new Set([projectId, ...extraProjectIds].filter(Boolean))]

  const handleSubmit = () => {
    const result = validation.validateForm(form)
    if (!result.success) return
    mutate({ ...result.data, project_id: projectId, project_ids: allProjectIds })
  }

  return (
    <Modal open title={t('client_portal.create_contact_title')} onClose={onClose} width={560}>
      <div className="u-grid2-14">
        <div className="u-col-full">
          <Input label={<>{t('client_portal.label_full_name')}*</>} id={`${idCampo}-1`} value={form.full_name} onChange={set('full_name')} {...err('full_name')} />{msgC('full_name')}
          {msg('full_name')}
        </div>
        <div>
          <Input label={<>{t('client_portal.label_email')}*</>} id={`${idCampo}-2`} type="email" value={form.email} onChange={set('email')} {...err('email')} />{msgC('email')}
          {msg('email')}
        </div>
        <div><Input label={t('client_portal.label_job_title')} id={`${idCampo}-3`} value={form.job_title} onChange={set('job_title')} placeholder={t('client_portal.label_job_title')} />{msgC('job_title')}</div>
        <div><Input label={t('client_portal.label_company')} id={`${idCampo}-4`} value={form.company} onChange={set('company')} />{msgC('company')}</div>
        <div><Input label={t('client_portal.label_phone')} id={`${idCampo}-5`} value={form.phone} onChange={set('phone')} />{msgC('phone')}</div>
        {inicial.modo === 'generar' && <div className="u-col-full u-hint">{t('portaluserstab.acceso_se_envia_por_correo')} /portal</div>}
        <SeccionContrasenaInicial valor={inicial} onChange={c => { camposC.limpiar('password'); setInicial(c) }} email={form.email} error={camposC.de('password')} />
        {allProjects.length > 1 && (
          <fieldset className="u-col-full cpp-fieldset ds-grupo-opciones">
            <legend className="cpp-label cpp-label--group">{t('client_portal.additional_projects_access')}</legend>
            <div className="cpp-projects-box">
              {allProjects.filter(p => p.id !== projectId).map(p => (
                <Checkbox key={p.id} checked={extraProjectIds.includes(p.id)}
                  onChange={marcado => setExtraProjectIds(prev => marcado ? [...prev, p.id] : prev.filter(id => id !== p.id))}
                  label={<><span className="cpp-project-code">{p.code}</span> <span className="u-text2-sm">{p.name}</span></>} />
              ))}
            </div>
          </fieldset>
        )}
        <fieldset className="u-col-full cpp-fieldset ds-grupo-opciones">
          <legend className="cpp-label cpp-label--group">{t('client_portal.permissions')}</legend>
          <div className="u-stack-8">
            {([['can_approve_deliverables', t('client_portal.perm_approve_desc')],['can_request_changes', t('client_portal.perm_request_desc')],['can_view_budget', t('client_portal.perm_budget_desc')],['can_view_team', t('client_portal.perm_team_desc')]] as Array<[PermisoCliente, string]>).map(([k, label]) => (
              <Checkbox key={k} className="cpp-check" label={label} checked={form[k]} onChange={marcado => setForm(f => ({ ...f, [k]: marcado }))} />
            ))}
          </div>
        </fieldset>
        <div className="cpp-actions">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={handleSubmit} disabled={isPending || (inicial.modo === 'manual' && !inicial.password)} loading={isPending}>
            {isPending ? t('client_portal.creating') : t('client_portal.create_access')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── UAT Management ────────────────────────────────────────────────────────────
function EditClientModal({ client, onClose, onSaved }: { client: ClientePortal; onClose: () => void; onSaved: () => void }) {
  const idCampo = React.useId()
  const t = useAppT()
  const { data: allProjects = [] } = useQuery({
    queryKey: ['projects-list'],
    queryFn: () => projectsApi.list({ page_size: LARGE_PAGE_SIZE }).then(r => r.data),
  })
  const camposB = useErroresDeCampo()
  const msgB = (k: string) => camposB.de(k) ? <div className="u-field-error">{camposB.de(k)}</div> : null
  const { mutate, isPending } = useMutation({
    onMutate: () => camposB.limpiar(),
    mutationFn: (data: DatosEdicionCliente) => portalClientsApi.update(client.id, data),
    onSuccess: onSaved,
    onError: (e: unknown) => { if (!camposB.recoger(e)) toast.error(extractErr(e, t('ai.generic_error'))) },
  })

  const toast = useToast()
  const [form, setForm] = useState<FormEdicionCliente>({
    full_name: client.full_name || '',
    email: client.email || '',
    job_title: client.job_title || '',
    company: client.company || '',
    phone: client.phone || '',
    project_ids: Array.isArray(client.project_ids) ? client.project_ids : (client.project_id ? [client.project_id] : []),
    can_approve_deliverables: client.can_approve_deliverables ?? true,
    can_request_changes: client.can_request_changes ?? true,
    can_view_budget: client.can_view_budget ?? true,
    can_view_team: client.can_view_team ?? false,
  })
  const esquema = React.useMemo(() => crearEsquemaEdicionCliente(t), [t])
  const validation = useFormValidation(esquema)
  const errs = validation.errors as Record<string, string | undefined>
  const err = (k: string) => propsDeError(errs, k, idCampo)
  const msg = (k: string) => <MensajeError errors={errs} campo={k} idBase={idCampo} />
  const set = (k: keyof FormEdicionCliente) => (e: EventoDeCampo) => {
    setForm(f => ({ ...f, [k]: e.target.value }))
    validation.clearFieldError(k)
  }

  const handleSave = () => {
    const result = validation.validateForm(form)
    if (!result.success) return
    mutate({ ...result.data })
  }

  return (
    <Modal open title={`${t('client_portal.edit')} — ${client.full_name}`} onClose={onClose} width={560}>
      <div className="u-grid2-14">
        <div className="u-col-full">
          <Input label={<>{t('client_portal.label_full_name')}*</>} id={`${idCampo}-1`} value={form.full_name} onChange={set('full_name')} {...err('full_name')} />{msgB('full_name')}
          {msg('full_name')}
        </div>
        <div>
          <Input label={<>{t('client_portal.label_email')}*</>} id={`${idCampo}-2`} type="email" value={form.email} onChange={set('email')} {...err('email')} />{msgB('email')}
          {msg('email')}
        </div>
        <div><Input label={t('client_portal.label_job_title')} id={`${idCampo}-3`} value={form.job_title} onChange={set('job_title')} placeholder={t('client_portal.label_job_title')} />{msgB('job_title')}</div>
        <div><Input label={t('client_portal.label_company')} id={`${idCampo}-4`} value={form.company} onChange={set('company')} />{msgB('company')}</div>
        <div><Input label={t('client_portal.label_phone')} id={`${idCampo}-5`} value={form.phone} onChange={set('phone')} />{msgB('phone')}</div>
        <fieldset className="u-col-full cpp-fieldset ds-grupo-opciones">
          <legend className="cpp-label cpp-label--group">{t('client_portal.additional_projects_access')}</legend>
          <div className="cpp-projects-box">
            {allProjects.map(project => (
              <Checkbox key={project.id} checked={form.project_ids.includes(String(project.id))}
                onChange={marcado => { camposB.limpiar('project_ids'); setForm(f => ({ ...f, project_ids: marcado ? [...f.project_ids, String(project.id)] : f.project_ids.filter(id => id !== String(project.id)) })) }}
                label={<><span className="cpp-project-code">{project.code}</span> <span className="u-text2-sm">{project.name}</span></>} />
            ))}
          </div>
        </fieldset>
        <fieldset className="u-col-full cpp-fieldset ds-grupo-opciones">
          <legend className="cpp-label cpp-label--group">{t('client_portal.permissions')}</legend>
          <div className="u-stack-8">
            {([
              ['can_approve_deliverables', t('client_portal.perm_approve_desc')],
              ['can_request_changes', t('client_portal.perm_request_desc')],
              ['can_view_budget', t('client_portal.perm_budget_desc')],
              ['can_view_team', t('client_portal.perm_team_desc')],
            ] as Array<[PermisoCliente, string]>).map(([k, label]) => (
              <Checkbox key={k} className="cpp-check" label={label} checked={form[k]} onChange={marcado => setForm(f => ({ ...f, [k]: marcado }))} />
            ))}
          </div>
        </fieldset>
        <div className="cpp-actions">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={handleSave} loading={isPending} disabled={isPending || !form.full_name || !form.email}>
            {isPending ? t('common.saving') : t('common.save')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

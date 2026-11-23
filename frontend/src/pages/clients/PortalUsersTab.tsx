import { PRODUCT_NAME } from '../../constants/brand'
import { type CSSProperties, useState, useId } from 'react'
import { useToast } from '../../context/ToastContext'
import { openConfirmGlobal, pedirTexto } from '../../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { portalClientsApi, clientsApi } from '../../services/api'
import { Button, EmptyState, Modal, Checkbox, GrupoDeOpciones, useErroresDeCampo, Input } from '../../components/ui'
import { Check, ClipboardCopy, Coins, FolderOpen, Globe, KeyRound, Lock, LockOpen, Mail, Pause, Pencil, Play, Plus, TriangleAlert, Users } from 'lucide-react'
import { extractErr, fmtDate } from '../../utils/helpers'
import { invalidarContactosDelCliente } from './contactosCliente'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { useAppLang } from '../../i18n/AppLangContext'
import './PortalUsersTab.css'

type PortalUsersTabProps = {
  cid: string | number
  clientName?: string
}

type PortalUser = {
  id: string
  full_name: string
  email: string
  job_title?: string | null
  phone?: string | null
  project_ids?: string[]
  project_id?: string | null
  is_active: boolean
  can_approve_deliverables?: boolean
  can_request_changes?: boolean
  can_view_budget?: boolean
  can_view_team?: boolean
  last_login?: string | null
}

/** Resultado del alta o del reenvío: a quién se mandó el acceso y si salió el correo.
 *  23-11-2026 (M10 del 04b): la contraseña la genera el servidor y solo la recibe el
 *  titular por correo; el equipo nunca la ve, no se pinta ni se copia. */
type AccesoEnviado = {
  email: string
  enviado: boolean | null
}

type PortalForm = {
  full_name: string
  email: string
  job_title: string
  phone: string
  project_ids: string[]
  can_approve_deliverables: boolean
  can_request_changes: boolean
  can_view_budget: boolean
  can_view_team: boolean
}

type PortalEditForm = PortalForm


const emptyForm = (): PortalForm => ({
  full_name: '',
  email: '',
  job_title: '',
  phone: '',
  project_ids: [],
  can_approve_deliverables: true,
  can_request_changes: true,
  can_view_budget: false,
  can_view_team: false,
})

type PortalPermissionKey = keyof Pick<
  PortalEditForm,
  'can_approve_deliverables' | 'can_request_changes' | 'can_view_budget' | 'can_view_team'
>

// Etiqueta y descripción: portaluserstab.perm_<key> y perm_<key>_desc.
const PORTAL_PERMISSIONS: { key: PortalPermissionKey }[] = [
  { key: 'can_approve_deliverables' },
  { key: 'can_request_changes' },
  { key: 'can_view_budget' },
  { key: 'can_view_team' },
]

/** Aviso tras dar acceso: se envió (o no) el correo con la contraseña inicial al
 *  titular. También lo usa la pestaña Contactos al dar acceso a un contacto. */
export function CredencialesDelPortal({ acceso, onClose }: { acceso: AccesoEnviado; onClose: () => void }) {
  const { t } = useAppLang()
  const portalUrl = `${window.location.origin}/portal`
  return (
    <Modal open title={t('portaluserstab.acceso_creado')} onClose={onClose} width={480}>
      <div className="pousta-box-10">
        <div className="u-stack-8">
          <div className="u-row-between">
            <span className="u-text2-sm">{t('portalusers.url_del_portal')}</span>
            <strong className="pousta-txt-2">{portalUrl}</strong>
          </div>
          <div className="u-row-between">
            <span className="u-text2-sm">{t('portaluserstab.email_dos_puntos')}</span>
            <strong className="pousta-txt-3">{acceso.email}</strong>
          </div>
        </div>
      </div>
      <div className="pousta-box-13 pousta-ico">
        {acceso.enviado === false
          ? <><TriangleAlert size={14} aria-hidden="true" />{t('portaluserstab.acceso_no_enviado')}</>
          : <><Mail size={14} aria-hidden="true" />{t('portaluserstab.acceso_enviado')}</>}
      </div>
      <div className="u-actions-8">
        <Button onClick={onClose}>{t('portaluserstab.entendido')}</Button>
      </div>
    </Modal>
  )
}

export function PortalUsersTab({ cid, clientName }: PortalUsersTabProps) {
  const idCampo = useId()
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [createdCreds, setCreatedCreds] = useState<AccesoEnviado | null>(null)
  const [editUser, setEditUser] = useState<PortalUser | null>(null)
  const [editForm, setEditForm] = useState<PortalEditForm | null>(null)
  const [form, setForm] = useState<PortalForm>(emptyForm)

  const { data: users = [] } = useQuery<PortalUser[]>({
    queryKey: ['portal-clients-org', cid],
    queryFn: () => portalClientsApi.list({ client_org_id: String(cid) }).then(r => r.data),
  })
  const { data: clientDetail } = useQuery({
    queryKey: ['client-detail-projects', cid],
    queryFn: () => clientsApi.get(cid).then(r => r.data),
  })
  const projects = clientDetail?.projects || []
  const projectLabelById = new Map(projects.map(p => [p.id, `${p.code} — ${p.name}`]))

  const campos = useErroresDeCampo()
  const camposEdit = useErroresDeCampo()
  const msg = (k: string) => campos.de(k) ? <div className="u-field-error">{campos.de(k)}</div> : null
  const msgEdit = (k: string) => camposEdit.de(k) ? <div className="u-field-error">{camposEdit.de(k)}</div> : null

  const { mutate: add, isPending } = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: (d: PortalForm & { client_org_id: string | number; project_ids?: string[] }) => portalClientsApi.create(d).then(r => r.data),
    onSuccess: (creado) => {
      // El servidor crea/actualiza el contacto del usuario: contactos y ficha cambian.
      invalidarContactosDelCliente(qc, cid)
      setShowAdd(false)
      setCreatedCreds({ email: form.email, enviado: creado?.credenciales_enviadas ?? null })
      setForm(emptyForm())
    },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(extractErr(e, t('portaluserstab.error_crear'))) },
  })

  const { mutate: toggle } = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) => portalClientsApi.update(id, { is_active: active }),
    onSuccess: () => invalidarContactosDelCliente(qc, cid),
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  })

  // Reenviar acceso: el servidor genera otra contraseña y la manda al titular.
  const { mutate: reenviar } = useMutation({
    mutationFn: (id: string) => portalClientsApi.sendAccess(id).then(r => r.data),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['portal-clients-org', cid] })
      setCreatedCreds({ email: r.email, enviado: r.credenciales_enviadas })
    },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  // 23-11-2026: forzar el restablecimiento (cambio obligatorio, cierre de sesiones y enlace), con motivo.
  const forzarRestablecimiento = async (u: PortalUser) => {
    const motivo = await pedirTexto({ title: t('portaluserstab.forzar_restablecimiento'), message: t('portaluserstab.confirmar_forzar_restablecimiento', { email: u.email }), label: t('portaluserstab.motivo_restablecimiento'), required: true })
    if (motivo === null) return
    try {
      const r = await portalClientsApi.forcePasswordReset(u.id, motivo)
      toast.success(r.data.link_sent ? t('portaluserstab.restablecimiento_forzado') : t('portaluserstab.restablecimiento_sin_enlace'))
    } catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) }
  }

  const { mutate: updateUser, isPending: updating } = useMutation({
    onMutate: () => camposEdit.limpiar(),
    mutationFn: ({ id, data }: { id: string; data: Partial<PortalEditForm> }) => portalClientsApi.update(id, data).then(r => r.data),
    onSuccess: () => {
      invalidarContactosDelCliente(qc, cid)
      setEditUser(null)
      setEditForm(null)
      toast.success(t('portaluserstab.usuario_actualizado'))
    },
    onError: (e: unknown) => { if (!camposEdit.recoger(e)) toast.error(extractErr(e, t('portaluserstab.error_actualizar'))) },
  })

  const openEdit = (u: PortalUser) => {
    setEditUser(u)
    setEditForm({
      full_name: u.full_name || '',
      email: u.email || '',
      job_title: u.job_title || '',
      phone: u.phone || '',
      project_ids: Array.isArray(u.project_ids) ? u.project_ids : (u.project_id ? [u.project_id] : []),
      can_approve_deliverables: u.can_approve_deliverables ?? true,
      can_request_changes: u.can_request_changes ?? true,
      can_view_budget: u.can_view_budget ?? false,
      can_view_team: u.can_view_team ?? false,
    })
  }

  const portalUrl = `${window.location.origin}/portal`

  return (
    <div>
      <div className="pousta-box-1">
        <div className="pousta-box-2 pousta-ico"><Globe size={15} aria-hidden="true" />{t('portalusers.como_accede_el_cliente_al_portal')}</div>
        <div className="pousta-txt-1">
          {t('portalusers.1_crea_un_usuario_con_email_y')}<br/>
          {t('portalusers.2_comparte_las_credenciales_con_el_cliente')}<br/>
          {t('portalusers.3_el_cliente_accede_en')} <strong className="u-text1">{portalUrl}</strong><br/>
          {t('portalusers.4_desde_el_portal_puede_ver_proyectos')}
        </div>
        <Button size="sm" variant="secondary" icon={<ClipboardCopy size={14} />} onClick={() => navigator.clipboard.writeText(portalUrl).then(() => toast.success(t('portaluserstab.copiado')), () => toast.error(t('portaluserstab.error_copiar')))}>
          {t('portalusers.copiar_url_del_portal')}
        </Button>
      </div>

      <div className="pousta-row-1">
        <div className="u-text2-base">{users.length} {t('portalusers.usuario_s_de_portal_activos')}</div>
        <Button onClick={() => setShowAdd(true)} size="sm" icon={<Plus size={14} />}>{t('portalusers.crear_usuario_de_portal')}</Button>
      </div>

      {users.length === 0
        ? <EmptyState icon={<Lock size={28} />} title={t('portalusers.sin_usuarios_de_portal')} description={t('portaluserstab.crea_primer_acceso')}
          action={<Button onClick={() => setShowAdd(true)} size="sm" icon={<Plus size={14} />}>{t('portalusers.crear_usuario_de_portal')}</Button>} />
        : users.map(u => {
          const assignedProjects = (u.project_ids || []).map(pid => projectLabelById.get(pid)).filter((label): label is string => Boolean(label))
          return (
          <div className={`pousta-panel ${u.is_active ? 'portal-users-tab-m1' : 'portal-users-tab-m2'}`} key={u.id}>
            <div className="pousta-row-2">
              <div className="u-row-center-12">
                <div className={`pousta-row-5 ${u.is_active ? 'portal-users-tab-m3' : 'portal-users-tab-m4'}`}>
                  {u.full_name?.charAt(0)?.toUpperCase() || '?'}
                </div>
                <div>
                  <div className="u-md-700">{u.full_name}
                    {!u.is_active && <span className="pousta-box-4">{t('portaluserstab.inactivo')}</span>}
                  </div>
                  <div className="u-text2-sm pousta-ico">
                    <Mail size={13} aria-hidden="true" />{u.email}{u.job_title && ` · ${u.job_title}`}
                  </div>
                  <div className="u-text3-xs-mt2">
                    <span className="pousta-ico">{assignedProjects.length > 0
                      ? <><FolderOpen size={12} aria-hidden="true" />{t('portaluserstab.proyectos_lista', { lista: assignedProjects.join(' · ') })}</>
                      : <><LockOpen size={12} aria-hidden="true" />{t('portaluserstab.sin_proyecto')}</>}</span>
                    {u.last_login && <span className="pousta-sp-1">{t('portalusers.ultimo_acceso')} <strong className="u-text2">{fmtDate(u.last_login)}</strong></span>}
                    {!u.last_login && <span className="pousta-nunca">· {t('portaluserstab.nunca_accedido')}</span>}
                  </div>
                </div>
              </div>
              <div className="pousta-row-3">
                {u.can_approve_deliverables && <span className="pousta-box-5 pousta-ico"><Check size={12} aria-hidden="true" />{t('portaluserstab.aprueba')}</span>}
                {u.can_view_budget && <span className="pousta-box-6 pousta-ico"><Coins size={12} aria-hidden="true" />{t('portaluserstab.presupuesto')}</span>}
                {u.can_view_team && <span className="pousta-equipo pousta-ico"><Users size={12} aria-hidden="true" />{t('portaluserstab.equipo')}</span>}
              </div>
            </div>
            <div className="pousta-row-4">
              <Button size="sm" variant="secondary" icon={<Pencil size={14} />} onClick={() => openEdit(u)}>
                {t('portaluserstab.editar')}
              </Button>
              <Button size="sm" variant="secondary" icon={<KeyRound size={14} />} onClick={() => openConfirmGlobal({ title: t('portaluserstab.reenviar_acceso'), message: t('portaluserstab.confirmar_reenviar_acceso', { email: u.email }), confirmLabel: t('portaluserstab.reenviar_acceso'), onConfirm: () => reenviar(u.id) })}>
                {t('portaluserstab.reenviar_acceso')}
              </Button>
              <Button size="sm" variant="secondary" icon={<Lock size={14} />} onClick={() => { void forzarRestablecimiento(u) }}>
                {t('portaluserstab.forzar_restablecimiento')}
              </Button>
              <Button size="sm" variant="secondary" icon={u.is_active ? <Pause size={14} /> : <Play size={14} />} onClick={() => toggle({ id: u.id, active: !u.is_active })}>
                {u.is_active ? t('portaluserstab.suspender') : t('portaluserstab.reactivar')}
              </Button>
              <Button size="sm" variant="ghost" icon={<ClipboardCopy size={14} />} onClick={() => {
                const text = [t('portaluserstab.acceso_titulo', { cliente: clientName || PRODUCT_NAME }), '', `URL: ${portalUrl}`, `${t('portaluserstab.email_dos_puntos')} ${u.email}`, '', t('portaluserstab.acceso_contacta')].join('\n')
                navigator.clipboard.writeText(text).then(() => toast.info(t('portaluserstab.info_copiada')), () => toast.error(t('portaluserstab.error_copiar')))
              }}>
                {t('portalusers.copiar_datos_de_acceso')}
              </Button>
            </div>
          </div>
          )
        })
      }

      {createdCreds && <CredencialesDelPortal acceso={createdCreds} onClose={() => setCreatedCreds(null)} />}

      {editUser && (
        <Modal open title={t('portaluserstab.editar_nombre', { nombre: editUser.full_name })} onClose={() => setEditUser(null)} width={560}>
          {editForm && (
            <>
          <div className="pousta-grid-1">
            <div>
              <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="pousta-lbl">{t('portaluserstab.nombre_completo')} *</label>
              <Input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={editForm?.full_name ?? ''} onChange={e => { camposEdit.limpiar('full_name'); setEditForm(f => f && ({ ...f, full_name: e.target.value })) }} inputClassName="pousta-inp" />
              {msgEdit('full_name')}
            </div>
            <div>
              <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="pousta-lbl">{t('portaluserstab.email')} *</label>
              <Input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} type="email" value={editForm?.email ?? ''} onChange={e => { camposEdit.limpiar('email'); setEditForm(f => f && ({ ...f, email: e.target.value })) }} inputClassName="pousta-inp" />
              {msgEdit('email')}
            </div>
            <div>
              <label id={`${idCampo}-cargo-edit-et`} htmlFor={`${idCampo}-cargo-edit`} className="pousta-lbl">{t('portaluserstab.cargo')}</label>
              <Input id={`${idCampo}-cargo-edit`} aria-labelledby={`${idCampo}-cargo-edit-et`} value={editForm?.job_title ?? ''} onChange={e => { camposEdit.limpiar('job_title'); setEditForm(f => f && ({ ...f, job_title: e.target.value })) }} placeholder={t('portaluserstab.cargo')} inputClassName="pousta-inp" />
              {msgEdit('job_title')}
            </div>
            <div>
              <label id={`${idCampo}-tel-et`} htmlFor={`${idCampo}-tel`} className="pousta-lbl">{t('portalusers.telefono')}</label>
              <Input id={`${idCampo}-tel`} aria-labelledby={`${idCampo}-tel-et`} value={editForm?.phone ?? ''} onChange={e => { camposEdit.limpiar('phone'); setEditForm(f => f && ({ ...f, phone: e.target.value })) }} placeholder={t('portalusers.telefono')} inputClassName="pousta-inp" />
              {msgEdit('phone')}
            </div>
            <div className="u-col-full">
              <GrupoDeOpciones tipo="checkbox" forma="lista" className="pousta-proyectos" leyenda={t('portaluserstab.proyectos_asociados')}
                valor={editForm.project_ids || []}
                onChange={v => setEditForm(f => f && ({ ...f, project_ids: v }))}
                opciones={projects.map(p => ({ valor: String(p.id), titulo: `${p.code} — ${p.name}` }))} />
              <div className="u-hint">{t('portalusers.puedes_asignar_acceso_a_varios_proyectos_al')}</div>
            </div>
          </div>

          <div className="pousta-panel2">
            <div className="pousta-box-16">{t('portalusers.permisos_en_el_portal')}</div>
            <div className="pousta-grid-2">
              {/* El tipo se declara en el ARRAY, no en el callback (auditoría 2026-08,
                  P1-10): así el literal se infiere con la unión estrecha en `key`
                  y `editForm[p.key]` queda comprobado. Anotarlo sólo en el
                  callback pedía a TypeScript aceptar un parámetro más estrecho
                  que el elemento del array — lo que `strictFunctionTypes`
                  rechaza, con razón. */}
              {PORTAL_PERMISSIONS.map((p) => (
                <label className={`pousta-row-6 portalus-sx1 portal-users-tab-e8 ${editForm[p.key] ? 'portal-users-tab-m9' : 'portal-users-tab-m10'}`} key={p.key} style={{ '--portal-users-tab-border': `1px solid ${editForm[p.key] ? 'var(--accent)' : 'var(--surface-4)'}` } as CSSProperties}>
                  <Checkbox checked={!!editForm[p.key]}
                    onChange={(_, e) => setEditForm(f => f && ({ ...f, [p.key]: e.target.checked }))}
                    className="pousta-box-17" />
                  <div>
                    <div className={`pousta-txt-4 ${editForm[p.key] ? 'portal-users-tab-m11' : 'portal-users-tab-m12'}`}>{t(`portaluserstab.perm_${p.key}`)}</div>
                    <div className="u-text3-2xs">{t(`portaluserstab.perm_${p.key}_desc`)}</div>
                  </div>
                </label>
              ))}
            </div>
          </div>

          <div className="u-actions-8">
            <Button variant="secondary" onClick={() => setEditUser(null)}>
              {t('common.cancel')}
            </Button>
            <Button
              loading={updating}
              disabled={!editForm.full_name || !editForm.email || updating}
              onClick={() => updateUser({ id: editUser.id, data: {
                full_name:                editForm.full_name,
                email:                    editForm.email,
                job_title:                editForm.job_title,
                phone:                    editForm.phone,
                project_ids:              editForm.project_ids || [],
                can_approve_deliverables: editForm.can_approve_deliverables,
                can_request_changes:      editForm.can_request_changes,
                can_view_budget:          editForm.can_view_budget,
                can_view_team:            editForm.can_view_team,
              }})}>
              {updating ? t('common.saving') : t('portaluserstab.guardar_cambios')}
            </Button>
          </div>
            </>
          )}
        </Modal>
      )}

      {showAdd && (
        <Modal open title={t('portalusers.nuevo_usuario_de_portal')} onClose={() => setShowAdd(false)} width={560}>
          <form onSubmit={e => { e.preventDefault(); add({ ...form, client_org_id: cid, project_ids: form.project_ids ?? [] }) }}>
          <div className="pousta-aviso">
            {t('portaluserstab.acceso_se_envia_por_correo')} <strong className="u-text1">{portalUrl}</strong>
          </div>
          <div className="pousta-grid-1">
            <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="pousta-lbl">{t('portaluserstab.nombre_completo')} *</label><Input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.full_name} onChange={e => { campos.limpiar('full_name'); setForm(f => ({ ...f, full_name: e.target.value })) }} inputClassName="pousta-inp" />{msg('full_name')}</div>
            <div><label id={`${idCampo}-mail-et`} htmlFor={`${idCampo}-mail`} className="pousta-lbl">{t('portalusers.email_sera_el_usuario_de_login')}</label><Input id={`${idCampo}-mail`} aria-labelledby={`${idCampo}-mail-et`} type="email" value={form.email} onChange={e => { campos.limpiar('email'); setForm(f => ({ ...f, email: e.target.value })) }} placeholder={t('portalusers.email_de_acceso')} inputClassName="pousta-inp" />{msg('email')}</div>
            <div><label id={`${idCampo}-cargo-et`} htmlFor={`${idCampo}-cargo`} className="pousta-lbl">{t('portaluserstab.cargo')}</label><Input id={`${idCampo}-cargo`} aria-labelledby={`${idCampo}-cargo-et`} value={form.job_title} onChange={e => { campos.limpiar('job_title'); setForm(f => ({ ...f, job_title: e.target.value })) }} placeholder={t('portaluserstab.cargo')} inputClassName="pousta-inp" />{msg('job_title')}</div>
            <div>
              <GrupoDeOpciones tipo="checkbox" forma="lista" className="pousta-proyectos" leyenda={t('portaluserstab.asociar_proyectos')}
                valor={form.project_ids}
                onChange={v => setForm(f => ({ ...f, project_ids: v }))}
                opciones={projects.map(p => ({ valor: String(p.id), titulo: `${p.code} — ${p.name}` }))} />
            </div>
          </div>
          <div className="pousta-panel2">
            <div className="pousta-box-16">{t('portalusers.permisos_en_el_portal')}</div>
            <div className="pousta-grid-2">
              {PORTAL_PERMISSIONS.map(p => (
                <label className={`pousta-row-6 portalus-sx1 portal-users-tab-e8 ${form[p.key] ? 'portal-users-tab-m9' : 'portal-users-tab-m10'}`} key={p.key} style={{ '--portal-users-tab-border': `1px solid ${form[p.key] ? 'var(--accent)' : 'var(--surface-4)'}` } as CSSProperties}>
                  <Checkbox checked={form[p.key]} onChange={(_, e) => setForm(f => ({ ...f, [p.key]: e.target.checked }))}
                    className="pousta-box-17" />
                  <div>
                    <div className={`pousta-txt-4 ${form[p.key] ? 'portal-users-tab-m11' : 'portal-users-tab-m12'}`}>{t(`portaluserstab.perm_${p.key}`)}</div>
                    <div className="u-text3-2xs">{t(`portaluserstab.perm_${p.key}_desc`)}</div>
                  </div>
                </label>
              ))}
            </div>
          </div>
          <div className="u-actions-8">
            <Button variant="secondary" onClick={() => setShowAdd(false)}>{t('common.cancel')}</Button>
            <Button type="submit"
              disabled={!form.full_name || !form.email || isPending}>
              {isPending ? t('portaluserstab.creando') : t('portaluserstab.crear_acceso')}
            </Button>
          </div>
          </form>
        </Modal>
      )}
    </div>
  )
}

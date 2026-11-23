// Pestañas de proyectos, contactos, licencias y contratos de la ficha de cliente. 23-11-2026: troceado de ClientsPageTabs sin cambio de comportamiento.
import { type CSSProperties, useState, useId } from 'react'
import { FolderKanban, Globe, KeyRound, Link2, Pencil, Phone, Plus, Star, Trash2, Unlink, User, ScrollText } from 'lucide-react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { useToast } from '../../context/ToastContext'
import { clientExtApi, clientsApi, contractsApi, type ClientContact, type Contract, licensesApi } from '../../services/api'
import { Button, Spinner, EmptyState, Modal, IconButton, Select, Checkbox, useErroresDeCampo, Input } from '../../components/ui'
import { fmtCurrency, fmtDate, extractErr } from '../../utils/helpers'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { CredencialesDelPortal } from './PortalUsersTab'
import { ModalEditarContacto } from './ModalEditarContacto'
import { invalidarContactosDelCliente, rolesDeContacto } from './contactosCliente'
import { useAppLang } from '../../i18n/AppLangContext'
import { alpha } from '../../constants/theme'
import { STALE_ALWAYS } from '../../constants/timings'
import { type ClientProjectRow, type ContactForm, type License, type LinkedContract, type LinkedLicense } from './ClientsTabsComun'

export function ProjectsTab({ cid }: { cid: string }) {
  const { t: traducir } = useAppLang()
  const qc = useQueryClient()
  const toast = useToast()
  const [showLink, setShowLink] = useState(false)

  const { data: linked = [], isLoading: loadingLinked } = useQuery<ClientProjectRow[]>({
    queryKey: ['client-projects-linked', cid],
    queryFn: () => clientExtApi.projects(cid).then(r => r.data),
    staleTime: STALE_ALWAYS,
    refetchOnWindowFocus: true,
    refetchOnMount: 'always',
  })

  const { data: available = [], isLoading: loadingAvail, refetch: refetchAvailable } = useQuery<ClientProjectRow[]>({
    queryKey: ['client-projects-available', cid],
    queryFn: () => clientExtApi.availableProjects(cid).then(r => r.data),
    staleTime: STALE_ALWAYS,
    refetchOnWindowFocus: true,
    refetchOnMount: 'always',
  })

  const { mutate: link } = useMutation({
    mutationFn: (pid: string) => clientExtApi.linkProject(cid, pid).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['client-projects-linked', cid] }); qc.invalidateQueries({ queryKey: ['client-projects-available', cid] }); qc.invalidateQueries({ queryKey: ['client-detail'] }); qc.invalidateQueries({ queryKey: ['clients'] }) },
    onError: e => toast.error(extractErr(e, traducir('clientstabs.error_vincular'))),
  })

  const { mutate: unlink } = useMutation({
    mutationFn: (pid: string) => clientExtApi.unlinkProject(cid, pid).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['client-projects-linked', cid] }); qc.invalidateQueries({ queryKey: ['client-projects-available', cid] }); qc.invalidateQueries({ queryKey: ['client-detail'] }); qc.invalidateQueries({ queryKey: ['clients'] }) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const statusColor: Record<string, string> = { active: 'var(--success)', planning: 'var(--accent)', on_hold: 'var(--warning)', completed: 'var(--text-2)', cancelled: 'var(--danger)' }
  const statusLabel: Record<string, string> = { active: traducir('clientstabs.proy_activo'), planning: traducir('clientstabs.proy_planificacion'), on_hold: traducir('clientstabs.proy_en_espera'), completed: traducir('clientstabs.proy_completado'), cancelled: traducir('clientstabs.proy_cancelado') }

  const unlinked = available.filter(p => !p.is_linked)

  return (
    <div>
      <div className="clpata-box-1">
        {traducir('clients.un_proyecto_solo_puede_estar_vinculado_a')}
      </div>

      <div className="u-row-between-mb16">
        <div className="u-text2-base">{traducir('clientstabs.n_proyectos_vinculados', { n: linked.length })}</div>
        <Button onClick={() => { setShowLink(s => !s); refetchAvailable() }} size="sm" variant={showLink ? 'secondary' : 'primary'} icon={showLink ? undefined : <Link2 size={14} />}>
          {showLink ? traducir('clientstabs.cerrar') : traducir('clientstabs.vincular_proyecto')}
        </Button>
      </div>

      {showLink && (
        <div className="clpata-panel">
          <div className="clpata-box-2">{traducir('clients.proyectos_disponibles_para_vincular')}</div>
          {loadingAvail ? <Spinner /> : unlinked.length === 0 ? (
            <div className="clpata-box-3">{traducir('clients.no_hay_proyectos_disponibles_sin_cliente_asignado')}</div>
          ) : (
            unlinked.map(p => (
              <div key={p.id} className="clpata-row-1">
                <div>
                  <span className="clpata-box-4">{p.code}</span>
                  <span className="u-base-600">{p.name}</span>
                  <span className="clpata-box-28 clients-page-tabs-e1" style={{ '--clients-page-tabs-background': alpha((statusColor[p.status] || 'var(--text-2)'), '20'), '--clients-page-tabs-color': statusColor[p.status] || 'var(--text-2)' } as CSSProperties}>
                    {statusLabel[p.status] || p.status}
                  </span>
                </div>
                <Button size="sm" variant="secondary" icon={<Link2 size={14} />} onClick={() => link(p.id)}>
                  {traducir('clientstabs.mas_vincular')}
                </Button>
              </div>
            ))
          )}
        </div>
      )}

      {loadingLinked ? <Spinner /> : linked.length === 0 ? (
        <EmptyState icon={<FolderKanban size={28} />} title={traducir('clients.sin_proyectos_vinculados')} description={traducir('clientstabs.vincula_primer_proyecto')} />
      ) : (
        linked.map(p => (
          <div key={p.id} className="clpata-panel2">
            <div className="clpata-row-2">
              <div>
                <div className="clpata-row-3">
                  <span className="u-text2-mono-xs">{p.code}</span>
                  <span className="u-md-700">{p.name}</span>
                  <span className="clpata-box-29 clients-page-tabs-e1" style={{ '--clients-page-tabs-background': alpha((statusColor[p.status] || 'var(--text-2)'), '20'), '--clients-page-tabs-color': statusColor[p.status] || 'var(--text-2)' } as CSSProperties}>
                    {statusLabel[p.status] || p.status}
                  </span>
                </div>
                <div className="u-text3-xs">
                  {p.start_date && `${fmtDate(p.start_date)} – ${p.end_date ? fmtDate(p.end_date) : traducir('clientstabs.en_curso')}`}
                </div>
              </div>
              <Button size="sm" variant="ghost" icon={<Unlink size={14} />} onClick={() => { openConfirmGlobal({ message: traducir('clientstabs.confirmar_desvincular', { nombre: p.name }), onConfirm: () => unlink(p.id), danger: true }) }}>
                {traducir('clientstabs.desvincular')}
              </Button>
            </div>
          </div>
        ))
      )}
    </div>
  )
}

export function ContactsTab({ cid }: { cid: string }) {
  const idCampo = useId()
  const { t: traducir } = useAppLang()
  const qc = useQueryClient()
  const toast = useToast()
  const [showAdd, setShowAdd] = useState(false)
  const [form, setForm] = useState<ContactForm>({ full_name: '', email: '', phone: '', job_title: '', role: 'other', is_primary: false })
  const [editando, setEditando] = useState<ClientContact | null>(null)
  const [accesoPara, setAccesoPara] = useState<ClientContact | null>(null)
  // 23-11-2026 (M10 del 04b): el servidor genera la contraseña y la envía al contacto.
  const [credenciales, setCredenciales] = useState<{ email: string; enviado: boolean | null } | null>(null)

  const { data: contacts = [], isLoading } = useQuery<ClientContact[]>({
    queryKey: ['client-contacts', cid],
    queryFn: () => clientsApi.contacts(cid).then(r => r.data),
  })
  // El servidor ya los manda con el principal primero; se asegura igualmente.
  const ordenados = [...contacts].sort((a, b) => Number(!!b.is_primary) - Number(!!a.is_primary))
  const invalidar = () => invalidarContactosDelCliente(qc, cid)
  const camposB = useErroresDeCampo()
  const camposAcceso = useErroresDeCampo()
  const msgB = (k: string) => camposB.de(k) ? <div className="u-field-error">{camposB.de(k)}</div> : null
  const { mutate: add } = useMutation({
    onMutate: () => camposB.limpiar(),
    mutationFn: (d: ContactForm) => clientExtApi.createContact(cid, d).then(r => r.data),
    onSuccess: () => { invalidar(); setShowAdd(false); setForm({ full_name: '', email: '', phone: '', job_title: '', role: 'other', is_primary: false }) },
    onError: (e: unknown) => { if (!camposB.recoger(e)) toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) },
  })
  const { mutate: remove } = useMutation({
    mutationFn: (id: string) => clientExtApi.deleteContact(cid, id),
    onSuccess: () => { invalidar(); toast.success(traducir('clicontactos.contacto_desactivado')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: marcarPrincipal } = useMutation({
    mutationFn: (ct: ClientContact) => clientExtApi.setPrimaryContact(cid, ct.id),
    onSuccess: (_r, ct) => { invalidar(); toast.success(traducir('clicontactos.marcado_principal', { nombre: ct.full_name })) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: darAcceso, isPending: dandoAcceso } = useMutation({
    onMutate: () => camposAcceso.limpiar(),
    mutationFn: ({ ct }: { ct: ClientContact }) => clientExtApi.givePortalAccess(cid, ct.id, {}).then(r => r.data),
    onSuccess: (r, { ct }) => {
      invalidar()
      setAccesoPara(null)
      setCredenciales({ email: r.email || ct.email || '', enviado: r.credenciales_enviadas ?? null })
    },
    onError: (e: unknown) => { if (!camposAcceso.recoger(e)) toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) },
  })

  const roles = rolesDeContacto(traducir)
  const roleColor: Record<string, string> = { primary: 'var(--accent)', billing: 'var(--warning)', technical: 'var(--purple)', executive: 'var(--success)', support: 'var(--warning)', other: 'var(--text-2)' }

  if (isLoading) return <Spinner />
  return (
    <div>
      <div className="u-row-between-mb16">
        <div className="u-text2-base">{traducir('clientstabs.n_contactos', { n: contacts.length })}</div>
        <Button onClick={() => setShowAdd(true)} size="sm" icon={<Plus size={14} />}>{traducir('clients.anadir_contacto')}</Button>
      </div>
      {contacts.length === 0 ? (
        <EmptyState icon={<User size={28} />} title={traducir('clients.sin_contactos')} description={traducir('clientstabs.anade_contacto')}
          action={<Button onClick={() => setShowAdd(true)} size="sm" icon={<Plus size={14} />}>{traducir('clients.anadir_contacto')}</Button>} />
      ) : ordenados.map(ct => (
        <div key={ct.id} className="clpata-panel3">
          <div className="u-row-center-12">
            <div className="clpata-row-14 clients-page-tabs-e1" style={{ '--clients-page-tabs-background': alpha((roleColor[ct.role] || 'var(--text-2)'), '20'), '--clients-page-tabs-color': roleColor[ct.role] || 'var(--text-2)' } as CSSProperties}>
              {ct.full_name?.charAt(0) || '?'}
            </div>
            <div>
              <div className="u-md-700">{ct.full_name}
                {ct.is_primary && <span className="clpata-box-7">{traducir('clicontactos.principal')}</span>}
                {ct.portal_active === true && <span className="clpata-portal">{traducir('clicontactos.portal')}</span>}
                {ct.portal_active === false && <span className="clpata-portal clpata-portal--off">{traducir('clicontactos.portal_desactivado')}</span>}
              </div>
              <div className="u-text2-sm">{ct.job_title} {ct.email && `· ${ct.email}`}</div>
            </div>
          </div>
          <div className="u-row-center-8">
            <span className="clpata-box-30 clients-page-tabs-e1" style={{ '--clients-page-tabs-background': alpha((roleColor[ct.role] || 'var(--text-2)'), '15'), '--clients-page-tabs-color': roleColor[ct.role] || 'var(--text-2)' } as CSSProperties}>
              {roles.find(r => r.id === ct.role)?.label || ct.role}
            </span>
            {ct.phone && <span className="u-text2-sm clpata-ico"><Phone size={13} aria-hidden="true" />{ct.phone}</span>}
            <IconButton onClick={() => setEditando(ct)} ariaLabel={traducir('clicontactos.editar_contacto_de', { nombre: ct.full_name || '' })}><Pencil size={14} /></IconButton>
            {!ct.is_primary && (
              <IconButton onClick={() => marcarPrincipal(ct)} ariaLabel={traducir('clicontactos.marcar_principal_de', { nombre: ct.full_name || '' })}
                title={traducir('clicontactos.marcar_principal')}><Star size={14} /></IconButton>
            )}
            {!ct.portal_user_id && ct.email && (
              <Button size="sm" variant="secondary" icon={<Globe size={14} />} onClick={() => { camposAcceso.limpiar(); setAccesoPara(ct) }}>
                {traducir('clicontactos.dar_acceso_portal')}
              </Button>
            )}
            <IconButton className="clpata-del" ariaLabel={traducir('clicontactos.desactivar_contacto', { nombre: ct.full_name || '' })}
              onClick={() => openConfirmGlobal({ message: traducir('clicontactos.confirmar_desactivar', { nombre: ct.full_name || '' }), onConfirm: () => remove(ct.id), danger: true })}>
              <Trash2 size={14} />
            </IconButton>
          </div>
        </div>
      ))}
      {editando && <ModalEditarContacto cid={cid} contacto={editando} onClose={() => setEditando(null)} />}
      {accesoPara && (
        <Modal open title={traducir('clicontactos.dar_acceso_titulo', { nombre: accesoPara.full_name })} onClose={() => setAccesoPara(null)} width={460}>
          <form onSubmit={e => { e.preventDefault(); darAcceso({ ct: accesoPara }) }}>
            <div className="u-text2-sm u-mb-16">{traducir('clicontactos.dar_acceso_ayuda_envio', { email: accesoPara.email || '' })}</div>
            {camposAcceso.de('email') && <div className="u-field-error u-mb-16">{camposAcceso.de('email')}</div>}
            <div className="u-actions-8">
              <Button variant="secondary" onClick={() => setAccesoPara(null)}>{traducir('clicontactos.cancelar')}</Button>
              <Button type="submit" loading={dandoAcceso}
                disabled={dandoAcceso}>
                {dandoAcceso ? traducir('clicontactos.creando') : traducir('clicontactos.crear_acceso')}
              </Button>
            </div>
          </form>
        </Modal>
      )}
      {credenciales && <CredencialesDelPortal acceso={credenciales} onClose={() => setCredenciales(null)} />}
      {showAdd && (
        <Modal open title={traducir('clients.nuevo_contacto')} onClose={() => setShowAdd(false)} width={500}>
          <div className="clpata-grid-1">
            <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="clpata-lbl">{traducir('clientstabs.nombre_completo')} *</label><Input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.full_name} onChange={e => { camposB.limpiar('full_name'); setForm(f => ({ ...f, full_name: e.target.value })) }} inputClassName="clpata-inp" />{msgB('full_name')}</div>
            <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="clpata-lbl">{traducir('clicontactos.email_contacto')}</label><Input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} type="email" value={form.email} onChange={e => { camposB.limpiar('email'); setForm(f => ({ ...f, email: e.target.value })) }} inputClassName="clpata-inp" />{msgB('email')}</div>
            <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="clpata-lbl">{traducir('clicontactos.telefono_contacto')}</label><Input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.phone} onChange={e => { camposB.limpiar('phone'); setForm(f => ({ ...f, phone: e.target.value })) }} inputClassName="clpata-inp" />{msgB('phone')}</div>
            <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="clpata-lbl">{traducir('clientstabs.cargo')}</label><Input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.job_title} onChange={e => { camposB.limpiar('job_title'); setForm(f => ({ ...f, job_title: e.target.value })) }} inputClassName="clpata-inp" />{msgB('job_title')}</div>
            <div><label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="clpata-lbl">{traducir('clientstabs.rol')}</label>
              <Select suelto placeholder={false} id={`${idCampo}-5`} value={form.role} onChange={e => { camposB.limpiar('role'); setForm(f => ({ ...f, role: e.target.value })) }} className="clpata-inp">
                {roles.map(r => <option key={r.id} value={r.id}>{r.label}</option>)}
              </Select>{msgB('role')}
            </div>
            <div className="clpata-row-4">
              <label className="u-row-center-8-pointer">
                <Checkbox checked={form.is_primary} onChange={(_, e) => setForm(f => ({ ...f, is_primary: e.target.checked }))} />
                {traducir('clientstabs.contacto_principal')}
              </label>
            </div>
          </div>
          <div className="u-actions-8">
            <Button variant="secondary" onClick={() => setShowAdd(false)}>{traducir('common.cancel')}</Button>
            <Button onClick={() => add(form)} disabled={!form.full_name}>{traducir('clients.anadir')}</Button>
          </div>
        </Modal>
      )}
    </div>
  )
}

export function LicensesTab({ cid }: { cid: string }) {
  const idCampo = useId()
  const { t: traducir } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const [showLink, setShowLink] = useState(false)
  const [selectedLic, setSelectedLic] = useState('')
  const [licNote, setLicNote] = useState('')

  const { data: linked = [] } = useQuery<LinkedLicense[]>({ queryKey: ['client-licenses', cid], queryFn: () => clientExtApi.licenses(cid).then(r => r.data) })
  const { data: allLics = [] } = useQuery<License[]>({ queryKey: ['alm-licenses'], queryFn: () => licensesApi.list(undefined).then(r => r.data) })

  const { mutate: link } = useMutation({
    mutationFn: (d: { license_id: string; notes: string }) => clientExtApi.linkLicense(cid, d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['client-licenses', cid] }); qc.invalidateQueries({ queryKey: ['alm-licenses'] }); setShowLink(false); setSelectedLic(''); setLicNote('') },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: unlink } = useMutation({
    mutationFn: (id: string) => clientExtApi.unlinkLicense(cid, id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['client-licenses', cid] }); qc.invalidateQueries({ queryKey: ['alm-licenses'] }) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const linkedIds = linked.map(l => l.license_id)
  const available = allLics.filter(l => !linkedIds.includes(l.id))
  const statusCol: Record<string, string> = { active: 'var(--success)', expired: 'var(--danger)', cancelled: 'var(--text-2)' }

  return (
    <div>
      <div className="clpata-row-5">
        <div className="u-text2-base">{traducir('clientstabs.n_licencias_vinculadas', { n: linked.length })}</div>
        <Button onClick={() => setShowLink(true)} size="sm" icon={<Link2 size={14} />}>{traducir('clientstabs.mas_vincular_licencia')}</Button>
      </div>
      {linked.length === 0 ? (
        <EmptyState icon={<KeyRound size={28} />} title={traducir('clients.sin_licencias_vinculadas')} description={traducir('clientstabs.vincula_licencia')}
          action={<Button onClick={() => setShowLink(true)} size="sm" icon={<Link2 size={14} />}>{traducir('clientstabs.mas_vincular_licencia')}</Button>} />
      ) : linked.map(l => (
        <div key={l.link_id} className="clpata-panel3">
          <div>
            <div className="u-md-700">{l.name}</div>
            <div className="u-text2-sm">
              {l.total_seats && traducir('clientstabs.n_puestos', { n: l.total_seats })}
              {l.expiry_date && ` · ${traducir('clientstabs.vence', { fecha: fmtDate(l.expiry_date) })}`}
              {l.annual_cost && ` · ${traducir('clientstabs.importe_anual', { importe: fmtCurrency(l.annual_cost) })}`}
            </div>
            {l.notes && <div className="clpata-box-9">{l.notes}</div>}
          </div>
          <div className="u-row-center-8">
            <span className="clpata-box-29 clients-page-tabs-e1" style={{ '--clients-page-tabs-background': alpha((statusCol[l.status] || 'var(--text-2)'), '15'), '--clients-page-tabs-color': statusCol[l.status] || 'var(--text-2)' } as CSSProperties}>{etiquetaCodigo(traducir, 'estado', l.status)}</span>
            <IconButton onClick={() => openConfirmGlobal({ message: traducir('clientstabs.confirmar_desvincular', { nombre: l.name || '' }), onConfirm: () => unlink(l.link_id), danger: true })} className="clpata-del" ariaLabel={traducir('clientstabs.desvincular_elemento', { nombre: l.name || '' })}><Unlink size={14} /></IconButton>
          </div>
        </div>
      ))}
      {showLink && (
        <Modal open title={traducir('clientstabs.vincular_licencia')} onClose={() => setShowLink(false)} width={440}>
          <div className="u-mb-14">
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="clpata-lbl">{traducir('clientstabs.licencia')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-1`} value={selectedLic} onChange={e => setSelectedLic(e.target.value)} className="clpata-inp">
              <option value="">{traducir('clientstabs.seleccionar')}</option>
              {available.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
            </Select>
          </div>
          <div className="u-mb-16">
            <label id={`${idCampo}-notas-et`} htmlFor={`${idCampo}-notas`} className="clpata-lbl">{traducir('clientstabs.notas_opcional')}</label>
            <Input id={`${idCampo}-notas`} aria-labelledby={`${idCampo}-notas-et`} value={licNote} onChange={e => setLicNote(e.target.value)} placeholder={traducir('clients.notas_de_la_licencia')} aria-label={traducir('clients.notas_de_la_licencia')} inputClassName="clpata-inp" />
          </div>
          <div className="u-actions-8">
            <Button variant="secondary" onClick={() => setShowLink(false)}>{traducir('common.cancel')}</Button>
            <Button onClick={() => link({ license_id: selectedLic, notes: licNote })} disabled={!selectedLic}>{traducir('clientstabs.vincular')}</Button>
          </div>
        </Modal>
      )}
    </div>
  )
}

export function ContractsTab({ cid }: { cid: string }) {
  const idCampo = useId()
  const { t: traducir } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const [showLink, setShowLink] = useState(false)
  const [selectedCon, setSelectedCon] = useState('')

  const { data: linked = [] } = useQuery<LinkedContract[]>({ queryKey: ['client-contracts', cid], queryFn: () => clientExtApi.contracts(cid).then(r => r.data) })
  const { data: allCons = [] } = useQuery<Contract[]>({ queryKey: ['contracts'], queryFn: () => contractsApi.list(undefined).then(r => r.data ?? []) })

  const { mutate: link } = useMutation({
    mutationFn: (d: { contract_id: string }) => clientExtApi.linkContract(cid, d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['client-contracts', cid] }); qc.invalidateQueries({ queryKey: ['contracts'] }); qc.invalidateQueries({ queryKey: ['alm-contracts'] }); setShowLink(false); setSelectedCon('') },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: unlink } = useMutation({
    mutationFn: (id: string) => clientExtApi.unlinkContract(cid, id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['client-contracts', cid] }); qc.invalidateQueries({ queryKey: ['contracts'] }); qc.invalidateQueries({ queryKey: ['alm-contracts'] }) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const linkedIds = linked.map(l => l.contract_id)
  const available = allCons.filter(c => !linkedIds.includes(c.id))
  const statusCol: Record<string, string> = { active: 'var(--success)', draft: 'var(--text-2)', completed: 'var(--accent)', cancelled: 'var(--danger)' }

  return (
    <div>
      <div className="clpata-row-5">
        <div className="u-text2-base">{traducir('clientstabs.n_contratos_vinculados', { n: linked.length })}</div>
        <Button onClick={() => setShowLink(true)} size="sm" icon={<Link2 size={14} />}>{traducir('clientstabs.mas_vincular_contrato')}</Button>
      </div>
      {linked.length === 0 ? (
        <EmptyState icon={<ScrollText size={28} />} title={traducir('clients.sin_contratos_vinculados')} description={traducir('clientstabs.asocia_contrato')}
          action={<Button onClick={() => setShowLink(true)} size="sm" icon={<Link2 size={14} />}>{traducir('clientstabs.mas_vincular_contrato')}</Button>} />
      ) : linked.map(c => (
        <div key={c.link_id ?? c.contract_id} className="clpata-panel3">
          <div>
            <div className="u-md-700">{c.title}</div>
            <div className="u-text2-sm">
              {c.reference && `${traducir('clientstabs.ref', { ref: c.reference })} · `}
              {c.total_amount && `${fmtCurrency(c.total_amount)} · `}
              {c.start_date && `${fmtDate(c.start_date)} – ${c.end_date ? fmtDate(c.end_date) : '…'}`}
            </div>
          </div>
          <div className="u-row-center-8">
            <span className="clpata-box-29 clients-page-tabs-e1" style={{ '--clients-page-tabs-background': alpha((statusCol[c.status] || 'var(--text-2)'), '15'), '--clients-page-tabs-color': statusCol[c.status] || 'var(--text-2)' } as CSSProperties}>{etiquetaCodigo(traducir, 'estado', c.status)}</span>
            {c.link_id && <IconButton onClick={() => openConfirmGlobal({ message: traducir('clientstabs.confirmar_desvincular', { nombre: c.title || '' }), onConfirm: () => unlink(c.link_id), danger: true })} className="clpata-del" ariaLabel={traducir('clientstabs.desvincular_elemento', { nombre: c.title || '' })}><Unlink size={14} /></IconButton>}
          </div>
        </div>
      ))}
      {showLink && (
        <Modal open title={traducir('clientstabs.vincular_contrato')} onClose={() => setShowLink(false)} width={440}>
          <div className="u-mb-16">
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="clpata-lbl">{traducir('clientstabs.contrato')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-1`} value={selectedCon} onChange={e => setSelectedCon(e.target.value)} className="clpata-inp">
              <option value="">{traducir('clientstabs.seleccionar')}</option>
              {available.map(c => <option key={c.id} value={c.id}>{c.name || c.client_name} — {etiquetaCodigo(traducir, 'estado', c.status)}</option>)}
            </Select>
          </div>
          <div className="u-actions-8">
            <Button variant="secondary" onClick={() => setShowLink(false)}>{traducir('common.cancel')}</Button>
            <Button onClick={() => link({ contract_id: selectedCon })} disabled={!selectedCon}>{traducir('clientstabs.vincular')}</Button>
          </div>
        </Modal>
      )}
    </div>
  )
}

import { type CSSProperties, useState, useEffect, useId } from 'react'
import type { LucideIcon } from 'lucide-react'
import { BookOpen, Check, Download, FilePen, FileText, FlaskConical, FolderKanban, FolderOpen, Globe, KeyRound, LayoutDashboard, Lightbulb, Link2, Map as MapIcon, MessageSquare, Package, PenLine, Phone, Plus, Receipt, Rocket, Ticket, Trash2, TriangleAlert, Unlink, User, FileBarChart, ClipboardList, Paperclip, ScrollText } from 'lucide-react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { useToast } from '../../context/ToastContext'
import { useAuth } from '../../context/AuthContext'
import { clientExtApi, clientsApi, contractsApi, type ClientContact, type Contract, licensesApi, portalApi, wsApi, apiWsUrl } from '../../services/api'
import { Button, Spinner, EmptyState, Modal, Tabs, IconButton, Select, TablaSimple, Checkbox } from '../../components/ui'
import Pagination from '../../components/ui/Pagination'
import { BadgeWithTooltip } from '../../components/ui/BadgeWithTooltip'
import { IconFR, IconCR } from '../../components/ui/FRCRIcons'
import { fmtCurrency, fmtDate, fmtDateTime, extractErr } from '../../utils/helpers'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { PortalUsersTab } from './PortalUsersTab'
import { ConversationPoliciesPanel, TeamGovernedConversationInbox } from '../../components/portal/GovernedConversations'
import { useAppLang } from '../../i18n/AppLangContext'
import type { FacturaDeCliente, ClienteContrato, ClienteLicencia, ClientePortalConfig, ClienteProyecto, PortalDocumento, PortalPeticion, PortalSesionUat } from '../../services/api/tipos-alm'
import { alpha } from '../../constants/theme'

import { useFormatoMoneda } from '../../hooks/useFormatoMoneda'
import { STALE_ALWAYS, WS_RECONNECT_DELAY_MS } from '../../constants/timings'
import './ClientsPageTabs.css'

// Etiqueta: clientstabs.mod_<id>.
const MODULES: { id: string; Icon: LucideIcon }[] = [
  { id: 'dashboard',    Icon: LayoutDashboard },
  { id: 'deliverables', Icon: Package },
  { id: 'uat',          Icon: FlaskConical },
  { id: 'requests',     Icon: Lightbulb },
  { id: 'documents',    Icon: FileText },
  { id: 'roadmap',      Icon: MapIcon },
  { id: 'wiki',         Icon: BookOpen },
  { id: 'support',      Icon: Ticket },
  { id: 'messages',     Icon: MessageSquare },
]

/** Icono de cada categoría de documento del portal. */
const DOC_ICON: Record<string, LucideIcon> = {
  general: FileText, contract: FilePen, invoice: Receipt, report: FileBarChart, specification: ClipboardList, other: Paperclip,
}

// ── Datos de las pestañas del cliente (campos según su uso aquí) ─────────────
// Respuestas de /clients/{id}/* y /portal/*/team: services/api/tipos-alm.
type ClientProjectRow = ClienteProyecto

/** Proyecto del detalle del cliente que se pasa a las pestañas del portal. */
interface ClientProjectRef {
  id: string
  code?: string
  name?: string
}

/** Lo que las pestañas usan del detalle del cliente (`projects` llega sin tipar). */
interface ClientDetail {
  name?: string
  projects?: unknown[]
}

interface ContactForm { full_name: string; email: string; phone: string; job_title: string; role: string; is_primary: boolean }

type LinkedLicense = ClienteLicencia
interface License { id: string; name: string }

type LinkedContract = ClienteContrato
// Contrato: el tipo del cliente de API. Auditoria 2026-11 (#39): aqui se leia
// `title`, que el backend no envia (contract_service da `name`): el selector salia sin nombre.

type TeamUatSession = PortalSesionUat

type TeamFeatureRequest = PortalPeticion

interface FeatureRequestResponseForm {
  pm_response: string
  estimated_hours: string
  estimated_cost: string
  estimated_delivery_weeks: string
  status: string
}

type TeamPortalDocument = PortalDocumento

type PortalConfig = ClientePortalConfig

interface PortalConfigPayload {
  enabled_modules: string[]
  sd_without_project: boolean
  sla_tier: string | null
  max_portal_users: number
  default_language: string
  allow_profile_edit: boolean
  allow_pwd_change: boolean
}

const CR_FECHAS = ['submitted_at', 'approved_at', 'implemented_at'] as const

const SLA_COLOR: Record<string, string> = {
  enterprise: 'var(--purple)',
  gold: 'var(--warning)',
  silver: 'var(--text-2)',
  bronze: 'var(--warning)',
}

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

  const { data: contacts = [], isLoading } = useQuery<ClientContact[]>({
    queryKey: ['client-contacts', cid],
    queryFn: () => clientsApi.contacts(cid).then(r => r.data),
  })
  const { mutate: add } = useMutation({
    mutationFn: (d: ContactForm) => clientExtApi.createContact(cid, d).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['client-contacts', cid] }); setShowAdd(false); setForm({ full_name: '', email: '', phone: '', job_title: '', role: 'other', is_primary: false }) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: remove } = useMutation({
    mutationFn: (id: string) => clientExtApi.deleteContact(cid, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['client-contacts', cid] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const roles = [
    { id: 'primary', label: traducir('clientstabs.rol_principal') }, { id: 'billing', label: traducir('clientstabs.rol_facturacion') },
    { id: 'technical', label: traducir('clientstabs.rol_tecnico') }, { id: 'executive', label: traducir('clientstabs.rol_ejecutivo') },
    { id: 'support', label: traducir('clientstabs.rol_soporte') }, { id: 'other', label: traducir('clientstabs.rol_otro') },
  ]
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
      ) : contacts.map(ct => (
        <div key={ct.id} className="clpata-panel3">
          <div className="u-row-center-12">
            <div className="clpata-row-14 clients-page-tabs-e1" style={{ '--clients-page-tabs-background': alpha((roleColor[ct.role] || 'var(--text-2)'), '20'), '--clients-page-tabs-color': roleColor[ct.role] || 'var(--text-2)' } as CSSProperties}>
              {ct.full_name?.charAt(0) || '?'}
            </div>
            <div>
              <div className="u-md-700">{ct.full_name}
                {ct.is_primary && <span className="clpata-box-7">{traducir('clientstabs.rol_principal')}</span>}
              </div>
              <div className="u-text2-sm">{ct.job_title} {ct.email && `· ${ct.email}`}</div>
            </div>
          </div>
          <div className="u-row-center-8">
            <span className="clpata-box-30 clients-page-tabs-e1" style={{ '--clients-page-tabs-background': alpha((roleColor[ct.role] || 'var(--text-2)'), '15'), '--clients-page-tabs-color': roleColor[ct.role] || 'var(--text-2)' } as CSSProperties}>
              {roles.find(r => r.id === ct.role)?.label || ct.role}
            </span>
            {ct.phone && <span className="u-text2-sm clpata-ico"><Phone size={13} aria-hidden="true" />{ct.phone}</span>}
            <IconButton onClick={() => remove(ct.id)} className="clpata-del" ariaLabel={traducir('clientstabs.eliminar_contacto', { nombre: ct.full_name || '' })}><Trash2 size={14} /></IconButton>
          </div>
        </div>
      ))}
      {showAdd && (
        <Modal open title={traducir('clients.nuevo_contacto')} onClose={() => setShowAdd(false)} width={500}>
          <div className="clpata-grid-1">
            <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="clpata-lbl">{traducir('clientstabs.nombre_completo')} *</label><input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.full_name} onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))} className="clpata-inp" /></div>
            <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="clpata-lbl">{traducir('clientstabs.email')}</label><input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} type="email" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} className="clpata-inp" /></div>
            <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="clpata-lbl">{traducir('clients.telefono')}</label><input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.phone} onChange={e => setForm(f => ({ ...f, phone: e.target.value }))} className="clpata-inp" /></div>
            <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="clpata-lbl">{traducir('clientstabs.cargo')}</label><input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.job_title} onChange={e => setForm(f => ({ ...f, job_title: e.target.value }))} className="clpata-inp" /></div>
            <div><label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="clpata-lbl">{traducir('clientstabs.rol')}</label>
              <Select suelto placeholder={false} id={`${idCampo}-5`} value={form.role} onChange={e => setForm(f => ({ ...f, role: e.target.value }))} className="clpata-inp">
                {roles.map(r => <option key={r.id} value={r.id}>{r.label}</option>)}
              </Select>
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
            <IconButton onClick={() => unlink(l.link_id)} className="clpata-del" ariaLabel={traducir('clientstabs.desvincular_elemento', { nombre: l.name || '' })}><Unlink size={14} /></IconButton>
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
            <input id={`${idCampo}-notas`} aria-labelledby={`${idCampo}-notas-et`} value={licNote} onChange={e => setLicNote(e.target.value)} className="clpata-inp" placeholder={traducir('clients.notas_de_la_licencia')} aria-label={traducir('clients.notas_de_la_licencia')} />
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
            {c.link_id && <IconButton onClick={() => unlink(c.link_id)} className="clpata-del" ariaLabel={traducir('clientstabs.desvincular_elemento', { nombre: c.title || '' })}><Unlink size={14} /></IconButton>}
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

export function PortalConfigTab({ cid, clientDetail }: { cid: string; clientDetail?: ClientDetail | null }) {
  const { t: traducir } = useAppLang()
  const [sub, setSub] = useState('accesos')
  // Proyectos del detalle del cliente: aquí solo se usan id, código y nombre.
  const proyectos = (clientDetail?.projects || []) as ClientProjectRef[]

  const subTabs = [
    { id: 'accesos', label: traducir('clientstabs.sub_accesos') },
    { id: 'uat', label: traducir('clientstabs.sub_uat') },
    { id: 'solicitudes', label: traducir('clientstabs.sub_solicitudes') },
    { id: 'mensajes', label: traducir('clientstabs.sub_mensajes') },
    { id: 'documentos', label: traducir('clientstabs.sub_documentos') },
    { id: 'config', label: traducir('clientstabs.sub_config') },
  ]

  return (
    <div>
      <Tabs items={subTabs} active={sub} onChange={setSub} ariaLabel={traducir('clientstabs.secciones_portal')} className="clpata-subtabs" />

      {sub === 'accesos' && <PortalUsersTab cid={cid} clientName={clientDetail?.name} />}
      {sub === 'uat' && <PortalUATTab _cid={cid} projects={proyectos} />}
      {sub === 'solicitudes' && <PortalSolicitudesTab cid={cid} projects={proyectos} />}
      {sub === 'mensajes' && <PortalMensajesTab cid={cid} projects={proyectos} />}
      {sub === 'documentos' && <PortalDocumentosTab cid={cid} projects={proyectos} />}
      {sub === 'config' && <PortalSettingsTab cid={cid} />}
    </div>
  )
}

export function PortalUATTab({ _cid, projects }: { _cid?: string; projects: ClientProjectRef[] }) {
  const idCampo = useId()
  const { t: traducir } = useAppLang()
  const [selectedProject, setSelectedProject] = useState(projects[0]?.id || '')

  const { data: sessions = [], isLoading } = useQuery<TeamUatSession[]>({
    queryKey: ['uat-team-client', selectedProject],
    queryFn: () => portalApi.uat({ project_id: selectedProject }).then(r => r.data).catch(() => []),
    enabled: !!selectedProject,
  })

  const statusColor: Record<string, string> = {
    pending: 'var(--text-2)', in_progress: 'var(--accent)', passed: 'var(--success)',
    failed: 'var(--danger)', conditional: 'var(--warning)',
  }
  const statusLabel: Record<string, string> = {
    pending: traducir('clientstabs.uat_pendiente'), in_progress: traducir('clientstabs.uat_en_progreso'), passed: traducir('clientstabs.uat_aprobado'),
    failed: traducir('clientstabs.uat_rechazado'), conditional: traducir('clientstabs.uat_con_reservas'),
  }

  return (
    <div>
      {projects.length === 0 ? (
        <EmptyState icon={<FlaskConical size={28} />} title={traducir('clients.sin_proyectos_para_uat')} description={traducir('clientstabs.asocia_proyecto_uat')} />
      ) : (
        <>
          {projects.length > 1 && (
            <div className="u-mb-16">
              <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="clpata-lbl">{traducir('clientstabs.proyecto')}</label>
              <Select suelto placeholder={false} id={`${idCampo}-1`} value={selectedProject} onChange={e => setSelectedProject(e.target.value)} className="clpata-inp">
                {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
              </Select>
            </div>
          )}

          {!selectedProject ? (
            <EmptyState icon={<FolderOpen size={28} />} title={traducir('clients.selecciona_un_proyecto')} description={traducir('clientstabs.elige_proyecto_uat')} />
          ) : isLoading ? <Spinner /> : sessions.length === 0 ? (
            <EmptyState icon={<FlaskConical size={28} />} title={traducir('clients.sin_sesiones_uat')} description={traducir('clientstabs.sin_sesiones_uat_proyecto')} />
          ) : (
            sessions.map(s => (
              <div key={s.id} className="clpata-panel2">
                <div className="clpata-row-7">
                  <div>
                    <div className="clpata-row-8">
                      <span className="u-text2-mono-xs">{s.code}</span>
                      <span className="u-md-700">{s.title}</span>
                    </div>
                    {s.description && <div className="u-text2-sm">{s.description.slice(0, 120)}</div>}
                    <div className="u-hint">
                      {s.available_from && traducir('clientstabs.disponible_desde', { fecha: fmtDate(s.available_from) })}
                      {s.deadline && ` · ${traducir('clientstabs.limite', { fecha: fmtDate(s.deadline) })}`}
                    </div>
                  </div>
                  <span className="clpata-box-32 clients-page-tabs-e1" style={{ '--clients-page-tabs-background': alpha((statusColor[s.status] || 'var(--text-2)'), '20'), '--clients-page-tabs-color': statusColor[s.status] || 'var(--text-2)' } as CSSProperties}>
                    {statusLabel[s.status] || s.status}
                  </span>
                </div>
                {s.test_environment && (
                  <div className="clpata-box-11">
                    <a href={s.test_environment} target="_blank" rel="noopener noreferrer" className="clpata-txt-1">
                      {traducir('clients.entorno_de_pruebas')}
                    </a>
                  </div>
                )}
                {s.issues_count > 0 && (
                  <div className="clpata-box-12 clpata-ico">
                    <TriangleAlert size={13} aria-hidden="true" />{traducir('clientstabs.n_incidencias', { n: s.issues_count })}
                  </div>
                )}
              </div>
            ))
          )}
        </>
      )}
    </div>
  )
}

export function PortalSolicitudesTab({ cid }: { cid: string; projects?: ClientProjectRef[] }) {
  const fmtMoneda = useFormatoMoneda()
  const idCampo = useId()
  const { t: traducir } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const { user, loading } = useAuth()

  useEffect(() => {
    if (loading || !user) return undefined

    let ws: WebSocket | undefined
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined
    function connectWS() {
      wsApi.ticket().then((res) => {
        const ticket = res.data.ticket
        ws = new window.WebSocket(apiWsUrl(`/ws/notifications?ticket=${ticket}`))
        ws.onclose = () => { reconnectTimer = setTimeout(connectWS, WS_RECONNECT_DELAY_MS) }
        ws.onerror = () => { ws!.close() }
        ws.onmessage = (ev) => {
          try {
            const msg = JSON.parse(ev.data)
            if (msg.type === 'cr_state_changed' && msg.feature_request_id) {
              toast.info(traducir('clientstabs.cr_cambio_estado', { titulo: msg.title, estado: msg.cr_status }))
              qc.invalidateQueries({ queryKey: ['portal-frs-client', cid] })
            }
          } catch {
            // ignore parse errors
          }
        }
      })
    }
    connectWS()
    return () => { if (ws) ws.close(); clearTimeout(reconnectTimer) }
  }, [cid, loading, qc, toast, user, traducir])

  const [responding, setResponding] = useState<TeamFeatureRequest | null>(null)
  const [responseForm, setResponseForm] = useState<FeatureRequestResponseForm>({ pm_response: '', estimated_hours: '', estimated_cost: '', estimated_delivery_weeks: '', status: 'estimated' })
  const [crDetail, setCrDetail] = useState<TeamFeatureRequest | null>(null)
  const [crFilter, setCrFilter] = useState('all')

  const { data: frs = [], isLoading } = useQuery<TeamFeatureRequest[]>({
    queryKey: ['portal-frs-client', cid],
    queryFn: () => portalApi.featureRequests({ client_org_id: cid }).then(r => r.data).catch(() => []),
    enabled: !!cid,
  })

  const { mutate: respond, isPending } = useMutation({
    mutationFn: ({ id, data }: { id: string; data: FeatureRequestResponseForm }) => portalApi.respondFeatureRequest(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['portal-frs-client', cid] }); setResponding(null) },
    onError: e => toast.error(extractErr(e, traducir('clientstabs.error_responder'))),
  })

  const { mutate: updateStatus } = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => portalApi.respondFeatureRequest(id, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['portal-frs-client', cid] }),
    onError: e => toast.error(extractErr(e, traducir('clientstabs.error_actualizar_estado'))),
  })

  const statusColor: Record<string, string> = { new: 'var(--text-2)', reviewing: 'var(--accent)', estimated: 'var(--warning)', approved: 'var(--success)', rejected: 'var(--danger)', in_development: 'var(--purple)', done: 'var(--success)' }
  const statusLabel: Record<string, string> = { new: traducir('clientstabs.fr_nueva'), reviewing: traducir('clientstabs.fr_en_revision'), estimated: traducir('clientstabs.fr_presupuestada'), approved: traducir('clientstabs.fr_aprobada'), rejected: traducir('clientstabs.fr_rechazada'), in_development: traducir('clientstabs.fr_en_desarrollo'), done: traducir('clientstabs.fr_completada') }
  const prioColor: Record<string, string> = { low: 'var(--text-2)', medium: 'var(--warning)', high: 'var(--warning)', critical: 'var(--danger)' }

  if (isLoading) return <Spinner />

  const crStates = [
    { value: 'all', label: traducir('clientstabs.cr_todas') },
    { value: 'none', label: traducir('clientstabs.sin_cr') },
    { value: 'submitted', label: traducir('clientstabs.cr_enviada') },
    { value: 'under_review', label: traducir('clientstabs.cr_en_revision') },
    { value: 'approved', label: traducir('clientstabs.cr_aprobada') },
    { value: 'rejected', label: traducir('clientstabs.cr_rechazada') },
    { value: 'implemented', label: traducir('clientstabs.cr_implementada') },
  ]
  const filteredFrs = frs.filter(fr => {
    if (crFilter === 'all') return true
    if (crFilter === 'none') return !fr.cr_status
    return fr.cr_status === crFilter
  })

  return (
    <div>
      <div className="clpata-row-9">
        <span className="u-text2-base">{filteredFrs.length} {traducir('clients.solicitud_es_del_cliente')}</span>
        <Select suelto placeholder={false} aria-label={traducir('clientstabs.filtrar_por_cr')} value={crFilter} onChange={e => setCrFilter(e.target.value)} className="clpata-inp2">
          {crStates.map(opt => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
        </Select>
      </div>
      {filteredFrs.length === 0 ? (
        <EmptyState icon={<Lightbulb size={28} />} title={traducir('clients.sin_solicitudes')} description={traducir('clientstabs.sin_solicitudes_cliente')} />
      ) : filteredFrs.map(fr => (
        <div className={`clpata-panel4 clients-page-tabs-e5 ${fr.cr_status ? 'clients-page-tabs-m6' : ''}`} key={fr.id} style={{ '--clients-page-tabs-border-left': fr.cr_status_color ? `6px solid ${fr.cr_status_color}` : '6px solid var(--text-3)' } as CSSProperties}>
          <div className="clpata-row-7">
            <div className="u-flex1">
              <div className="clpata-row-8">
                <IconFR />
                <span className="u-text2-mono-xs">{fr.code}</span>
                <span className="u-md-700">{fr.title}</span>
              </div>
              {fr.project_name && <div className="clpata-box-13 clpata-ico"><FolderOpen size={13} aria-hidden="true" />{fr.project_name}</div>}
            </div>
            <div className="clpata-row-10">
              <span className="clpata-box-33 clients-page-tabs-e1" style={{ '--clients-page-tabs-background': alpha((prioColor[fr.priority] || 'var(--text-2)'), '20'), '--clients-page-tabs-color': prioColor[fr.priority] || 'var(--text-2)' } as CSSProperties}>{etiquetaCodigo(traducir, 'estado', fr.priority)}</span>
              <span className="clpata-box-33 clients-page-tabs-e1" style={{ '--clients-page-tabs-background': alpha((statusColor[fr.status] || 'var(--text-2)'), '20'), '--clients-page-tabs-color': statusColor[fr.status] || 'var(--text-2)' } as CSSProperties}>{statusLabel[fr.status] || fr.status}</span>
              {fr.cr_status ? (
                <BadgeWithTooltip
                  label={`CR: ${fr.cr_status_label || fr.cr_status}`}
                  color={fr.cr_status_color || 'var(--text-3)'}
                  tooltip={traducir('clientstabs.tooltip_cr')}
                  icon={<IconCR />}
                  onClick={() => setCrDetail(fr)}
                />
              ) : (
                <BadgeWithTooltip
                  label={traducir('clientstabs.sin_cr')}
                  color="var(--text-3)"
                  tooltip={traducir('clientstabs.tooltip_sin_cr')}
                  icon={<IconCR />}
                />
              )}
            </div>
          </div>
          <div className="clpata-txt-2">{fr.description?.slice(0, 200)}</div>
          {fr.pm_response && (
            <div className="clpata-box-14">
              <strong className="u-success">{traducir('clients.respuesta_del_equipo')}</strong> {fr.pm_response}
              {fr.estimated_cost && <span className="clpata-box-15">· {fmtMoneda(fr.estimated_cost)}</span>}
              {fr.estimated_delivery_weeks && <span className="clpata-box-16">· {traducir('clientstabs.n_semanas', { n: fr.estimated_delivery_weeks })}</span>}
            </div>
          )}
          {fr.client_approved === true && <div className="clpata-box-17">{traducir('clients.cliente_aprobo_el')} {fmtDate(fr.client_approved_at)}</div>}
          {fr.client_approved === false && <div className="clpata-box-18">{traducir('clients.cliente_rechazo')}</div>}
          <div className="clpata-row-11">
            {['new', 'reviewing'].includes(fr.status) && (
              <Button size="sm" icon={<MessageSquare size={14} />} onClick={() => { setResponding(fr); setResponseForm({ pm_response: '', estimated_hours: '', estimated_cost: '', estimated_delivery_weeks: '', status: 'estimated' }) }}>
                {traducir('clientstabs.responder')}
              </Button>
            )}
            {fr.status === 'approved' && (
              <Button size="sm" variant="secondary" icon={<Rocket size={14} />} onClick={() => updateStatus({ id: fr.id, status: 'in_development' })}>
                {traducir('clientstabs.iniciar_desarrollo')}
              </Button>
            )}
            {fr.status === 'in_development' && (
              <Button size="sm" variant="secondary" icon={<Check size={14} />} onClick={() => updateStatus({ id: fr.id, status: 'done' })}>
                {traducir('clientstabs.marcar_completada')}
              </Button>
            )}
          </div>
          <div className="clpata-box-19">{fmtDateTime(fr.submitted_at)}</div>
        </div>
      ))}

      {responding && (
        <Modal open title={traducir('clientstabs.responder_a', { titulo: responding.title })} onClose={() => setResponding(null)} width={520}>
          <div className="u-stack-14">
            <div><label className="clpata-ls">{traducir('clients.respuesta_analisis')}</label><textarea value={responseForm.pm_response} onChange={e => setResponseForm(f => ({ ...f, pm_response: e.target.value }))} rows={3} className="clpata-fs2" placeholder={traducir('clients.respuesta_del_equipo_2')} aria-label={traducir('clients.respuesta_del_equipo_2')} /></div>
            <div className="clpata-grid-2">
              <div><label id={`${idCampo}-horas-et`} htmlFor={`${idCampo}-horas`} className="clpata-ls">{traducir('clientstabs.horas_estimadas')}</label><input id={`${idCampo}-horas`} aria-labelledby={`${idCampo}-horas-et`} type="number" value={responseForm.estimated_hours} onChange={e => setResponseForm(f => ({ ...f, estimated_hours: e.target.value }))} className="clpata-fs" placeholder={traducir('clientstabs.horas')} /></div>
              <div><label id={`${idCampo}-coste-et`} htmlFor={`${idCampo}-coste`} className="clpata-ls">{traducir('clientstabs.coste_estimado')} ({fmtMoneda.simbolo})</label><input id={`${idCampo}-coste`} aria-labelledby={`${idCampo}-coste-et`} type="number" value={responseForm.estimated_cost} onChange={e => setResponseForm(f => ({ ...f, estimated_cost: e.target.value }))} className="clpata-fs" placeholder={traducir('clientstabs.coste')} /></div>
              <div><label id={`${idCampo}-semanas-et`} htmlFor={`${idCampo}-semanas`} className="clpata-ls">{traducir('clientstabs.semanas_entrega')}</label><input id={`${idCampo}-semanas`} aria-labelledby={`${idCampo}-semanas-et`} type="number" value={responseForm.estimated_delivery_weeks} onChange={e => setResponseForm(f => ({ ...f, estimated_delivery_weeks: e.target.value }))} className="clpata-fs" placeholder={traducir('clientstabs.semanas')} /></div>
            </div>
            <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="clpata-ls">{traducir('common.status')}</label>
              <Select suelto placeholder={false} id={`${idCampo}-1`} value={responseForm.status} onChange={e => setResponseForm(f => ({ ...f, status: e.target.value }))} className="clpata-fs">
                <option value="estimated">{traducir('clients.presupuestada_pendiente_aprobacion_cliente')}</option>
                <option value="rejected">{traducir('clients.rechazada_no_factible')}</option>
              </Select>
            </div>
            <div className="u-actions-10">
              <Button variant="secondary" onClick={() => setResponding(null)}>{traducir('common.cancel')}</Button>
              <Button onClick={() => respond({ id: responding.id, data: responseForm })} disabled={isPending || !responseForm.pm_response}>{traducir('clientstabs.enviar_respuesta')}</Button>
            </div>
          </div>
        </Modal>
      )}

      {crDetail && (
        <Modal open title={traducir('clientstabs.detalle_cr')} onClose={() => setCrDetail(null)} width={520}>
          {crDetail.cr_status ? (
            <div className="u-stack-12">
              <div className="clpata-txt-5 clients-page-tabs-e7" style={{ '--clients-page-tabs-color': crDetail.cr_status_color } as CSSProperties}>
                <IconCR /> {traducir('clientstabs.estado_valor', { estado: crDetail.cr_status_label || crDetail.cr_status })}
              </div>
              <div><b>{traducir('clients.titulo')}</b> {crDetail.title}</div>
              <div><b>{traducir('clients.descripcion')}</b> {crDetail.description}</div>
              <div><b>{traducir('clientstabs.impacto')}</b> {crDetail.impact_label || crDetail.impact || '—'}</div>
              <div><b>{traducir('clientstabs.coste_impacto')}</b> {crDetail.cost_impact != null ? fmtMoneda(crDetail.cost_impact) : '—'}</div>
              <div><b>{traducir('clientstabs.impacto_plazo')}</b> {crDetail.schedule_impact_days != null ? traducir('clientstabs.n_dias', { n: crDetail.schedule_impact_days }) : '—'}</div>
              <div><b>{traducir('clients.notas_resolucion')}</b> {crDetail.resolution_notes || '—'}</div>
              <div><b>{traducir('clientstabs.fechas')}</b> {CR_FECHAS.map(f => crDetail[f] && (<span key={f} className="clpata-sp-1">{etiquetaCodigo(traducir, 'estado', f.replace('_at', ''))}: {fmtDateTime(crDetail[f])}</span>))}</div>
            </div>
          ) : (
            <div>{traducir('clients.no_hay_change_request_vinculada_aun_se')}</div>
          )}
        </Modal>
      )}
    </div>
  )
}

export function PortalMensajesTab({ cid, projects }: { cid: string; projects: ClientProjectRef[] }) {
  const { t: traducir } = useAppLang()
  return (
    <div className="u-stack-16">
      <TeamGovernedConversationInbox
        title={traducir('clients.conversaciones_del_cliente')}
        emptyTitle={traducir('clientstabs.sin_conversaciones')}
        emptyDescription={traducir('clientstabs.sin_conversaciones_desc')}
        projectOptions={projects.map(project => ({ id: project.id, name: project.name || project.code || project.id, code: project.code || '' }))}
        initialProjectId={projects[0]?.id || ''}
        clientOrgId={cid}
      />
      <ConversationPoliciesPanel />
    </div>
  )
}

export function PortalDocumentosTab({ cid, projects }: { cid: string; projects: ClientProjectRef[] }) {
  const idCampo = useId()
  const { t: traducir } = useAppLang()
  const [selectedProject, setSelectedProject] = useState(projects[0]?.id || '')
  const { data: docs = [], isLoading } = useQuery<TeamPortalDocument[]>({
    queryKey: ['portal-docs-team', cid, selectedProject],
    queryFn: () => selectedProject
      ? portalApi.documents({ project_id: selectedProject }).then(r => r.data).catch(() => [])
      : Promise.resolve([]),
    enabled: !!selectedProject,
  })
  if (isLoading) return <Spinner />
  return (
    <div>
      {projects.length > 1 && (
        <div className="u-mb-16">
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="clpata-lbl">{traducir('clientstabs.proyecto')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-1`} value={selectedProject} onChange={e => setSelectedProject(e.target.value)} className="clpata-inp">
            {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
          </Select>
        </div>
      )}
      {!selectedProject
        ? <EmptyState icon={<FolderOpen size={28} />} title={traducir('clients.selecciona_un_proyecto')} description={traducir('clientstabs.elige_proyecto_docs')} />
        : <div className="clpata-box-20">{traducir('clientstabs.n_documentos', { n: docs.length })}</div>}
      {docs.length === 0
        ? <EmptyState icon={<FileText size={28} />} title={traducir('clients.sin_documentos')} description={traducir('clientstabs.sin_docs_proyecto')} />
        : docs.map(d => (
          <div key={d.id} className="clpata-panel3">
            <div className="u-row-center-12">
              {(() => { const DocIcon = DOC_ICON[d.category] ?? FileText; return <span className="clpata-txt-3" aria-hidden="true"><DocIcon size={18} /></span> })()}
              <div>
                <div className="u-md-700">{d.title}</div>
                <div className="u-text2-xs">
                  {d.file_name && `${d.file_name} · `}{d.created_at ? fmtDate(d.created_at) : ''}
                  {d.requires_signature && <span className="clpata-box-15 clpata-ico"><PenLine size={12} aria-hidden="true" />{traducir('clientstabs.requiere_firma')}</span>}
                </div>
              </div>
            </div>
            {d.file_url && (
              <a href={d.file_url} target="_blank" rel="noopener noreferrer" className="clpata-box-21 clpata-ico">
                <Download size={14} aria-hidden="true" />{traducir('clientstabs.descargar')}
              </a>
            )}
          </div>
        ))}
    </div>
  )
}

export function PortalSettingsTab({ cid }: { cid: string }) {
  const idCampo = useId()
  const { t: traducir } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: cfg, isLoading } = useQuery<PortalConfig>({
    queryKey: ['client-portal-cfg', cid],
    queryFn: () => clientExtApi.portalConfig(cid).then(r => r.data),
  })
  const [modules, setModules] = useState<string[]>([])
  const [sdWithout, setSdWithout] = useState(true)
  const [slaTier, setSlaTier] = useState('')
  const [maxUsers, setMaxUsers] = useState(10)
  const [defaultLang, setDefaultLang] = useState('es')
  const [allowEdit, setAllowEdit] = useState(true)
  const [allowPwd, setAllowPwd] = useState(true)

  useEffect(() => {
    if (cfg) {
      setModules(cfg.enabled_modules || [])
      setSdWithout(cfg.sd_without_project ?? true)
      setSlaTier(cfg.sla_tier || '')
      setMaxUsers(cfg.max_portal_users || 10)
      setDefaultLang(cfg.default_language || 'es')
      setAllowEdit(cfg.allow_profile_edit ?? true)
      setAllowPwd(cfg.allow_pwd_change ?? true)
    }
  }, [cfg])

  const { mutate: save, isPending: saving } = useMutation({
    mutationFn: (d: PortalConfigPayload) => clientExtApi.updatePortalConfig(cid, d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['client-portal-cfg', cid] }); toast.success(traducir('clientstabs.config_guardada')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const toggleModule = (mod: string) => setModules(m => m.includes(mod) ? m.filter(x => x !== mod) : [...m, mod])

  const languages = [
    { code: 'es', label: 'Español' }, { code: 'en', label: 'English' },
    { code: 'fr', label: 'Français' }, { code: 'de', label: 'Deutsch' },
    { code: 'pt', label: 'Português' }, { code: 'it', label: 'Italiano' },
    { code: 'pl', label: 'Polski' }, { code: 'zh', label: '中文' },
  ]

  if (isLoading) return <Spinner />
  return (
    <div className="clpata-grid-3">
      <div className="u-stack-16">
        <div className="clpata-panel5">
          <div className="clpata-box-22">{traducir('clients.modulos_del_portal')}</div>
          <div className="clpata-box-23">{traducir('clients.que_secciones_puede_ver_el_cliente_en')}</div>
          {MODULES.map(m => (
            <label key={m.id} className="clpata-row-12">
              <Checkbox checked={modules.includes(m.id)} onChange={() => toggleModule(m.id)} className="clpata-box-24" />
              <span className="clpata-txt-4" aria-hidden="true"><m.Icon size={15} /></span>
              <span className={`clpata-txt-6 ${modules.includes(m.id) ? 'clients-page-tabs-m8' : 'clients-page-tabs-m9'}`}>{traducir(`clientstabs.mod_${m.id}`)}</span>
            </label>
          ))}
        </div>

        <div className="clpata-panel5">
          <div className="clpata-box-22 clpata-ico"><Ticket size={15} aria-hidden="true" />{traducir('clientstabs.mod_support')}</div>
          <label className="clpata-row-13">
            <Checkbox aria-label={traducir('clients.acceso_sin_proyecto_vinculado')} checked={sdWithout} onChange={(_, e) => setSdWithout(e.target.checked)} className="clpata-box-25" />
            <div>
              <div className="u-base-600">{traducir('clients.acceso_sin_proyecto_vinculado')}</div>
              <div className="u-text2-xs">{traducir('clients.puede_abrir_tickets_aunque_no_tenga_proyectos')}</div>
            </div>
          </label>
        </div>
      </div>

      <div className="u-stack-16">
        <div className="clpata-panel5">
          <div className="clpata-box-22 clpata-ico"><Globe size={15} aria-hidden="true" />{traducir('clientstabs.idioma_y_sla')}</div>
          <div className="u-mb-14">
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="clpata-lbl">{traducir('clients.idioma_por_defecto_del_portal')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-1`} value={defaultLang} onChange={e => setDefaultLang(e.target.value)} className="clpata-inp">
              {languages.map(l => <option key={l.code} value={l.code}>{l.label}</option>)}
            </Select>
            <div className="clpata-box-26">{traducir('clients.se_aplica_a_nuevos_usuarios_cada_usuario')}</div>
          </div>
          <div>
            <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="clpata-lbl">{traducir('clientstabs.tier_sla')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-2`} value={slaTier} onChange={e => setSlaTier(e.target.value)} className="clpata-inp">
              <option value="">{traducir('clients.sin_tier')}</option>
              <option value="bronze">{traducir('clientstabs.sla_bronze')}</option>
              <option value="silver">{traducir('clientstabs.sla_silver')}</option>
              <option value="gold">{traducir('clientstabs.sla_gold')}</option>
              <option value="enterprise">{traducir('clientstabs.sla_enterprise')}</option>
            </Select>
            {slaTier && <div className="clpata-box-34 clients-page-tabs-e1" style={{ '--clients-page-tabs-background': alpha((SLA_COLOR[slaTier] || 'var(--text-2)'), '15'), '--clients-page-tabs-color': SLA_COLOR[slaTier] || 'var(--text-2)' } as CSSProperties}>
              {traducir('clientstabs.tier_activo')} <strong>{traducir(`clientstabs.sla_${slaTier}`).split(' — ')[0]}</strong>
            </div>}
          </div>
        </div>

        <div className="clpata-panel5">
          <div className="clpata-box-22">{traducir('clients.perfil_del_cliente')}</div>
          <div className="clpata-box-23">{traducir('clients.define_que_puede_modificar_el_cliente_desde')}</div>
          {[
            { key: 'allowEdit', val: allowEdit, set: setAllowEdit, label: traducir('clientstabs.puede_editar_perfil'), desc: traducir('clientstabs.puede_editar_perfil_desc') },
            { key: 'allowPwd', val: allowPwd, set: setAllowPwd, label: traducir('clientstabs.puede_cambiar_pwd'), desc: traducir('clientstabs.puede_cambiar_pwd_desc') },
          ].map(opt => (
            <label className={`clpata-row-15 clientsp-sx1 clients-page-tabs-e2 ${opt.val ? 'clients-page-tabs-m10' : 'clients-page-tabs-m11'}`} key={opt.key} style={{ '--clients-page-tabs-border': `1px solid ${opt.val ? 'var(--accent)' : 'var(--surface-4)'}` } as CSSProperties}>
              <Checkbox checked={opt.val} onChange={(_, e) => opt.set(e.target.checked)} className="clpata-box-27" />
              <div>
                <div className={`clpata-txt-7 ${opt.val ? 'clients-page-tabs-m12' : 'clients-page-tabs-m13'}`}>{opt.label}</div>
                <div className="u-text3-xs">{opt.desc}</div>
              </div>
            </label>
          ))}
          <div className="clpata-sp-2">
            <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="clpata-lbl">{traducir('clients.max_usuarios_de_portal')}</label>
            <input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} type="number" min={1} max={100} value={maxUsers} onChange={e => setMaxUsers(+e.target.value)} className="clpata-inp" />
          </div>
        </div>

        <Button onClick={() => save({ enabled_modules: modules, sd_without_project: sdWithout, sla_tier: slaTier || null, max_portal_users: maxUsers, default_language: defaultLang, allow_profile_edit: allowEdit, allow_pwd_change: allowPwd })} className="clientsp-sx2" loading={saving}>
          {traducir('clients.guardar_configuracion_del_portal')}
        </Button>
      </div>
    </div>
  )
}

// ── Facturas del cliente (#22) ───────────────────────────────────────────────
// GET /clients/{cid}/invoices pagina en el servidor: el total llega en `meta.total`
// (o `X-Total-Count`) y la pestana solo trae la pagina visible.
const FACTURAS_POR_PAGINA = 20
const FACTURA_ESTADOS = ['draft', 'sent', 'paid', 'overdue', 'cancelled'] as const

export function InvoicesTab({ cid }: { cid: string }) {
  const { t: traducir } = useAppLang()
  const dinero = useFormatoMoneda()
  const [page, setPage] = useState(1)

  const { data, isLoading, isError, isFetching, refetch } = useQuery({
    queryKey: ['client-invoices', cid, page],
    queryFn: () => clientsApi.invoices(cid, { page, page_size: FACTURAS_POR_PAGINA }).then(r => ({
      items: r.data,
      total: r.meta?.total ?? Number(r.headers?.['x-total-count'] ?? r.data.length),
    })),
    placeholderData: previous => previous,
  })

  const total = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / FACTURAS_POR_PAGINA))
  // Si la pagina pedida queda fuera del total, vuelve a la ultima que existe.
  useEffect(() => { if (data && page > totalPages) setPage(totalPages) }, [data, page, totalPages])
  useEffect(() => { setPage(1) }, [cid])

  const etiquetaEstado = (st: string) => (FACTURA_ESTADOS as readonly string[]).includes(st) ? traducir(`clientstabs.fact_estado_${st}`) : st

  if (isLoading) return <Spinner />
  if (isError) {
    return (
      <div className="clifac-error" role="alert">
        <span>{traducir('clientstabs.fact_error')}</span>
        <Button variant="secondary" size="sm" onClick={() => refetch()}>{traducir('clientstabs.fact_reintentar')}</Button>
      </div>
    )
  }
  const facturas: FacturaDeCliente[] = data?.items ?? []
  if (facturas.length === 0) {
    return <EmptyState icon={<Receipt size={28} />} title={traducir('clientstabs.fact_vacio_titulo')} description={traducir('clientstabs.fact_vacio_desc')} />
  }
  return (
    <div className="clifac" aria-busy={isFetching || undefined}>
      <div className="clifac-scroll">
        <TablaSimple claseTabla="clifac-tabla">
          <thead>
            <tr>
              <th scope="col">{traducir('clientstabs.fact_numero')}</th>
              <th scope="col">{traducir('clientstabs.fact_proyecto')}</th>
              <th scope="col">{traducir('clientstabs.fact_emision')}</th>
              <th scope="col">{traducir('clientstabs.fact_vencimiento')}</th>
              <th scope="col" className="clifac-num">{traducir('clientstabs.fact_importe')}</th>
              <th scope="col">{traducir('clientstabs.fact_estado')}</th>
            </tr>
          </thead>
          <tbody>
            {facturas.map(f => (
              <tr key={f.id}>
                <td className="clifac-numero">{f.number ?? '—'}</td>
                <td>{f.project_name ?? '—'}</td>
                <td>{f.issue_date ? fmtDate(f.issue_date) : '—'}</td>
                <td>{f.due_date ? fmtDate(f.due_date) : '—'}</td>
                <td className="clifac-num">{f.total_amount == null ? '—' : dinero(f.total_amount)}</td>
                <td><span className={`clifac-estado clifac-estado--${f.status}`}>{etiquetaEstado(f.status)}</span></td>
              </tr>
            ))}
          </tbody>
        </TablaSimple>
      </div>
      <Pagination page={page} totalPages={totalPages} onChange={setPage} total={total} pageSize={FACTURAS_POR_PAGINA} maxVisible={5} />
    </div>
  )
}

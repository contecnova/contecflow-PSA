import type { CSSProperties, ChangeEvent } from 'react'
import { useState, useId, useMemo } from 'react'
import { z } from 'zod'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { clientsApi, unwrapList, type ClientContact } from '../services/api'
import type { MetaDeLista } from '../services/api/tipos-plataforma'
import { Button, Spinner, EmptyState, Modal, Tabs, useSort, SortableTH, Pulsable, Select, useErroresDeCampo, Textarea } from '../components/ui'
import Pagination from '../components/ui/Pagination'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { extractErr, fmtDate } from '../utils/helpers'
import { etiquetaCodigo } from '../i18n/etiquetaCodigo'
import { useFormValidation } from '../hooks/useFormValidation'
import { useAppT } from '../i18n/AppLangContext'
import { Award, Briefcase, Building2, FileText, FolderKanban, Globe, KeyRound, LayoutGrid, List, Mail, MapPin, Pencil, Phone, Plus, Receipt, Ticket, User, Users } from 'lucide-react'
import {
  ProjectsTab,
  ContactsTab,
  LicensesTab,
  ContractsTab,
  InvoicesTab,
  PortalConfigTab,
} from './clients/ClientsPageTabs'
import { ModalEditarContacto } from './clients/ModalEditarContacto'
import { SelectorContactoPrincipal, datosDeContactoPrincipal, NUEVO_CONTACTO_VACIO, type NuevoContacto } from './clients/SelectorContactoPrincipal'
import { useCatalogo } from '../hooks/useCatalogo'
import { CamposInternos } from './clients/CamposInternos'
import { FORM_INTERNO_VACIO, datosInternos, formInternoDe, sinCamposInternos } from './internos/logica'
import './ClientsPage.css'

type Traductor = ReturnType<typeof useAppT>

// Estados de la EMPRESA cliente (ClientStatus en app/models/clients.py): en
// captación, activo, inactivo o perdido. «Rechazado», «aprobado», «en
// revisión»… son de oportunidades, presupuestos o peticiones, no de un
// cliente. La etiqueta sale de i18n (`clientspage.estado_<clave>`) y el color
// es un token del tema.
const STATUS_COLOR: Record<string, string> = {
  prospect: 'var(--accent)',
  active: 'var(--success)',
  inactive: 'var(--text-2)',
  churned: 'var(--danger)',
}
const STATUS_KEYS = Object.keys(STATUS_COLOR)
const SLA_COLOR: Record<string, string> = {
  enterprise: 'var(--purple)',
  gold: 'var(--warning)',
  silver: 'var(--text-2)',
  bronze: 'var(--warning)',
}
// 19-11-2026: los sectores son el catálogo de la empresa (`/settings/client-industries`).

/** Tamaño de página de la lista de clientes (#22: el backend pagina con page/page_size). */
const CLIENTS_PAGE_SIZE = 25

/** Color de datos → custom property que consume `.cli-status`. */
const colorVar = (color: string | undefined): CSSProperties =>
  ({ '--cli-color': color || 'var(--text-2)' } as CSSProperties)

// ── Client shape (list item + hydrated detail) ───────────────────────────────
type Client = {
  [key: string]: unknown
  id: string
  name: string
  short_name?: string
  tax_id?: string
  status?: string
  industry?: string
  notes?: string
  website?: string
  country?: string
  city?: string
  address?: string
  /** Teléfono y email generales de la empresa. */
  phone?: string
  email?: string
  primary_contact_id?: string | null
  /** Reflejo de solo lectura del contacto principal (persona). */
  contact_name?: string
  contact_email?: string
  contact_phone?: string
  contact_role?: string
  account_manager_name?: string
  projects_count?: number
  tickets_count?: number
  invoices_count?: number
  portal_users_count?: number
  portal_config?: { sla_tier?: string } | null
  projects?: unknown[]
  contracts?: unknown[]
  licenses?: unknown[]
  portal_users?: unknown[]
}

// ── Zod schema mirroring backend Client model (app/models/clients.py) ────────
// Se construye con el traductor activo para que los mensajes salgan en el idioma del usuario.
function crearEsquemaCliente(t: Traductor) {
  const max = (n: number) => t('clientspage.max_caracteres', { n })
  const optionalString = (n: number) => z.union([
    z.literal(''),
    z.string().trim().max(n, max(n)),
  ]).optional()
  const optionalEmail = z.union([
    z.literal(''),
    z.string().trim().pipe(z.email(t('clientspage.email_invalido')).max(200, max(200))),
  ]).optional()
  return z.object({
    name: z.string().trim().min(1, t('clientspage.nombre_obligatorio')).max(255, max(255)),
    short_name: optionalString(50),
    tax_id: optionalString(50),
    phone: optionalString(50),
    email: optionalEmail,
    website: optionalString(255),
    address: optionalString(500),
    city: optionalString(100),
    country: optionalString(100),
    // Nuevo contacto principal (persona).
    contact_name: optionalString(200),
    contact_role: optionalString(100),
    contact_email: optionalEmail,
    contact_phone: optionalString(50),
    status: z.string().min(1),
    industry: z.string().min(1),
    notes: z.union([z.literal(''), z.string().max(2000, max(2000))]).optional(),
  })
}

// 22-11-2026 (clientes internos): «Tipo» y campos internos en el mismo formulario (ver pages/internos/logica.ts).
const FORM_VACIO = { name: '', short_name: '', tax_id: '', phone: '', email: '', website: '', address: '', city: '', country: '', status: 'active', industry: 'other', notes: '', ...FORM_INTERNO_VACIO }
/** Carga útil del formulario: datos de la empresa + campos internos normalizados (externo → solo `kind`). */
const cargaDelFormulario = (form: Record<string, string>): Record<string, unknown> => ({ ...sinCamposInternos(form), ...datosInternos(form) })

// Campos de datos de la EMPRESA (alta y edición). El contacto principal va
// aparte, en SelectorContactoPrincipal.
type CamposEmpresaProps = {
  idBase: string
  t: Traductor
  form: Record<string, string>
  onCampo: (clave: string, valor: string) => void
  errorDe: (clave: string) => string | undefined
  opcionesSector: JSX.Element[]
  opcionesEstado: JSX.Element[]
}
function CamposEmpresa({ idBase, t, form, onCampo, errorDe, opcionesSector, opcionesEstado }: CamposEmpresaProps): JSX.Element {
  const texto = (clave: string, etiqueta: string, opciones: { tipo?: string; ancho?: boolean; placeholder?: string } = {}) => {
    const id = `${idBase}-${clave}`
    const err = errorDe(clave)
    return (
      <div className={opciones.ancho ? 'u-col-full' : undefined}>
        <label id={`${id}-et`} htmlFor={id} className="cli-label">{etiqueta}</label>
        <input id={id} aria-labelledby={`${id}-et`} type={opciones.tipo ?? 'text'} value={form[clave] ?? ''}
          placeholder={opciones.placeholder} className="cli-input"
          aria-invalid={err ? true : undefined} aria-describedby={err ? `${id}-err` : undefined}
          onChange={e => onCampo(clave, e.target.value)} />
        {err && <div id={`${id}-err`} className="u-field-error">{err}</div>}
      </div>
    )
  }
  return (
    <div className="cli-seccion" role="group" aria-labelledby={`${idBase}-empresa`}>
      <div id={`${idBase}-empresa`} className="cli-seccion__titulo">{t('clicontactos.seccion_empresa')}</div>
      <div className="cli-form-grid">
        {texto('name', t('clientspage.campo_nombre'))}
        {texto('short_name', t('clientspage.campo_nombre_corto'))}
        {texto('tax_id', t('clientspage.campo_cif'))}
        <Select label={t('clientspage.campo_sector')} placeholder={false} value={form.industry}
          onChange={e => onCampo('industry', e.target.value)} error={errorDe('industry')}>
          {opcionesSector}
        </Select>
        {texto('phone', t('clicontactos.telefono_empresa'))}
        {texto('email', t('clicontactos.email_empresa'), { tipo: 'email' })}
        {texto('website', t('clientspage.campo_web'), { placeholder: t('clientspage.placeholder_web') })}
        <Select label={t('clientspage.campo_estado')} placeholder={false} value={form.status}
          onChange={e => onCampo('status', e.target.value)} error={errorDe('status')}>
          {opcionesEstado}
        </Select>
        {texto('address', t('clicontactos.direccion'), { ancho: true })}
        {texto('city', t('clientspage.campo_ciudad'))}
        {texto('country', t('clients.pais'))}
      </div>
    </div>
  )
}

// ── Página principal ──────────────────────────────────────────────────────────
export default function ClientsPage(): JSX.Element {
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [search, setSearch] = useState('')
  const [statusF, setStatusF] = useState('')
  // Clientes internos: '' (todos), 'externo' o 'interno' (`GET /clients?kind=`).
  const [kindF, setKindF] = useState('')
  const [page, setPage] = useState(1)
  const [sortBy, setSortBy] = useState('name')
  const [selected, setSelected] = useState<Client | null>(null)
  const [activeTab, setActiveTab] = useState('contacts')
  const [showCreate, setShowCreate] = useState(false)
  const [newForm, setNewForm] = useState<Record<string, string>>(FORM_VACIO)
  const clientCreateSchema = useMemo(() => crearEsquemaCliente(t), [t])
  const createValidation = useFormValidation(clientCreateSchema)
  const [showEdit, setShowEdit] = useState(false)
  const [editClientForm, setEditClientForm] = useState<Record<string, string>>({})
  // Contacto principal en el alta/edición: id elegido (o NUEVO_CONTACTO) y datos del nuevo.
  const [contactoElegido, setContactoElegido] = useState('')
  const [contactoNuevo, setContactoNuevo] = useState<NuevoContacto>(NUEVO_CONTACTO_VACIO)
  const [contactoAEditar, setContactoAEditar] = useState<ClientContact | null>(null)
  const [clientView, setClientView] = useState('grid')
  const camposNuevo = useErroresDeCampo()
  const camposEdit = useErroresDeCampo()

  const statusLabel = (s: string | undefined) => (s && STATUS_COLOR[s] ? t(`clientspage.estado_${s}`) : s)
  const sectores = useCatalogo('client-industries')
  const industryLabel = (i: string) => sectores.etiqueta(i)

  // Lista paginada en el servidor (page/page_size; total en meta.total).
  const { data: paginaClientes, isLoading } = useQuery<{ items: Client[]; total: number }>({
    queryKey: ['clients', search, statusF, kindF, page],
    queryFn: () => clientsApi.list({ q: search || undefined, status: statusF || undefined, kind: kindF || undefined, page, page_size: CLIENTS_PAGE_SIZE })
      .then(r => {
        const items = unwrapList(r) as Client[]
        const meta = (r as typeof r & { meta?: MetaDeLista }).meta
        const total = meta?.total ?? Number(r.headers?.['x-total-count'] ?? items.length)
        return { items, total }
      }),
    placeholderData: keepPreviousData,
  })
  const clients = paginaClientes?.items ?? []
  const clientsTotal = paginaClientes?.total ?? 0
  const clientsTotalPages = Math.max(1, Math.ceil(clientsTotal / CLIENTS_PAGE_SIZE))

  const { sort: clientSort, setSort: setClientSort, sortedData: sortedClients } = useSort(clients, sortBy)

  const { data: detail } = useQuery({
    queryKey: ['client-detail', selected?.id],
    queryFn: () => clientsApi.get(selected!.id).then(r => r.data),
    enabled: !!selected,
  })
  // Misma clave que la pestaña Contactos: comparten caché y se invalidan juntas.
  const { data: contactos = [] } = useQuery<ClientContact[]>({
    queryKey: ['client-contacts', selected?.id],
    queryFn: () => clientsApi.contacts(selected!.id).then(r => r.data),
    enabled: !!selected,
  })
  const principal = contactos.find(c => c.is_primary)
    ?? (detail?.primary_contact_id ? contactos.find(c => c.id === detail.primary_contact_id) : undefined)

  const { mutate: create, isPending: creating } = useMutation({
    mutationFn: (d: Record<string, unknown>) => clientsApi.create(d),
    onMutate: () => camposNuevo.limpiar(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['clients'] })
      setShowCreate(false)
      setNewForm(FORM_VACIO)
      setContactoNuevo(NUEVO_CONTACTO_VACIO)
      createValidation.setErrors({})
      toast.success(t('clientspage.cliente_creado'))
    },
    onError: (e: unknown) => { if (!camposNuevo.recoger(e)) toast.error(extractErr(e, t('clientspage.error_crear'))) },
  })

  const { mutate: updateClient, isPending: updatingClient } = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Record<string, unknown> }) => clientsApi.update(id, data),
    onMutate: () => camposEdit.limpiar(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['clients'] })
      qc.invalidateQueries({ queryKey: ['client-detail', selected?.id] })
      qc.invalidateQueries({ queryKey: ['client-contacts', selected?.id] })
      qc.invalidateQueries({ queryKey: ['client-detail-projects', selected?.id] })
      setShowEdit(false)
      toast.success(t('clientspage.cliente_actualizado'))
    },
    onError: (e: unknown) => { if (!camposEdit.recoger(e)) toast.error(extractErr(e, t('clientspage.error_actualizar'))) },
  })

  const openEditClient = () => {
    if (!selected) return
    // El detalle trae los campos nuevos (phone/email de empresa, principal); si
    // aún no ha llegado, lo del listado.
    const c: Record<string, unknown> = { ...selected, ...(detail ?? {}) }
    const txt = (k: string, porDefecto = '') => (typeof c[k] === 'string' && c[k] ? String(c[k]) : porDefecto)
    setEditClientForm({
      name:       txt('name'),
      short_name: txt('short_name'),
      tax_id:     txt('tax_id'),
      industry:   txt('industry', 'other'),
      phone:      txt('phone'),
      email:      txt('email'),
      status:     txt('status', 'active'),
      notes:      txt('notes'),
      website:    txt('website'),
      address:    txt('address'),
      country:    txt('country'),
      city:       txt('city'),
      ...formInternoDe(c),
    })
    setContactoElegido(txt('primary_contact_id') || principal?.id || '')
    setContactoNuevo(NUEVO_CONTACTO_VACIO)
    setShowEdit(true)
  }

  // Clientes internos: lenguaje adaptado («Unidad interna», «Coste», «Responsable»).
  const esInterno = (detail as unknown as { kind?: string } | undefined)?.kind === 'interno' || selected?.kind === 'interno'
  const TABS = [
    { id: 'contacts', label: t('clientspage.tab_contactos'), icon: <Users size={14} /> },
    { id: 'projects', label: t('clientspage.tab_proyectos'), icon: <FolderKanban size={14} /> },
    { id: 'contracts', label: t('clientspage.tab_contratos'), icon: <FileText size={14} /> },
    { id: 'licenses', label: t('clientspage.tab_licencias'), icon: <KeyRound size={14} /> },
    { id: 'invoices', label: esInterno ? t('internos.tab_coste') : t('clientspage.tab_facturas'), icon: <Receipt size={14} /> },
    { id: 'tickets', label: t('clientspage.tab_tickets'), icon: <Ticket size={14} /> },
    { id: 'portal', label: t('clientspage.tab_portal'), icon: <Globe size={14} /> },
  ]
  const newClientButton = (
    <Button data-tour="btn-new-client" icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{t('clients.new_client')}</Button>
  )

  const selectClient = (c: Client) => { setSelected(c); setActiveTab('contacts') }
  const statusOptions = STATUS_KEYS.map(k => <option key={k} value={k}>{statusLabel(k)}</option>)
  const industryOptions = sectores.opciones.map(o => <option key={o.value} value={o.value}>{o.label}</option>)

  return (
    <PageShell>
      <PageHeader
        icon={<Briefcase size={18} />}
        title={t('nav.clients')}
        subtitle={t('clients.subtitle')}
        actions={
          <div className="ds-row">
            <div className="ds-segmented" role="group" aria-label={t('proyectos_ui.vista')}>
              {[
                { v: 'grid', label: t('proyectos_ui.vista_tarjetas'), Icon: LayoutGrid },
                { v: 'list', label: t('proyectos_ui.vista_lista'), Icon: List },
              ].map(({ v, label, Icon }) => (
                <Pulsable aria-label={label} key={v} type="button" aria-pressed={clientView === v}
                  onClick={() => setClientView(v)} title={label}>
                  <Icon size={12} />
                </Pulsable>
              ))}
            </div>
            {newClientButton}
          </div>
        }
      />
      <div className="cli-layout">
      {/* Lista de clientes */}
      <div className="cli-list">
        <input value={search} onChange={e => { setSearch(e.target.value); setPage(1) }}
          placeholder={t('clients.buscar_cliente_por_nombre_o_codigo')} aria-label={t('clients.buscar_cliente_por_nombre_o_codigo')}
          className="cli-input cli-input--mb" />
        <div className="cli-filters">
          <Select suelto placeholder={false} value={statusF} onChange={e => { setStatusF(e.target.value); setPage(1) }}
            aria-label={t('clientspage.filtrar_estado')} className="cli-input u-flex1">
            <option value="">{t('clients.todos_los_estados')}</option>
            {statusOptions}
          </Select>
          <Select suelto placeholder={false} value={kindF} onChange={e => { setKindF(e.target.value); setPage(1) }}
            aria-label={t('internos.filtrar_tipo')} className="cli-input cli-input--auto"
            options={[
              { value: '', label: t('internos.filtro_todos') },
              { value: 'externo', label: t('internos.filtro_externos') },
              { value: 'interno', label: t('internos.filtro_internos') },
            ]} />
          <Select suelto placeholder={false} value={sortBy} onChange={e => setSortBy(e.target.value)}
            aria-label={t('clientspage.ordenar_por')} className="cli-input cli-input--auto">
            <option value="name">{t('clientspage.orden_az')}</option>
            <option value="projects_count">{t('clientspage.orden_proyectos')}</option>
            <option value="tickets_count">{t('clientspage.orden_tickets')}</option>
            <option value="status">{t('clientspage.orden_estado')}</option>
          </Select>
        </div>
        {isLoading ? <Spinner /> : clients.length === 0
          ? <EmptyState icon={<Building2 size={28} />} title={t('clients.no_clients')} description={t('clientspage.crea_primer_cliente')} action={newClientButton} />
          : clientView === 'grid' ? (sortedClients as Client[]).map(c => (
            <Pulsable key={c.id} type="button" onClick={() => selectClient(c)}
              aria-pressed={selected?.id === c.id}
              className={selected?.id === c.id ? 'cli-card is-selected' : 'cli-card'}>
              <div className="cli-card__head">
                <div title={c.name} className="cli-card__name">{c.name}</div>
                {c.kind === 'interno' && <span className="cli-tag cli-tag--accent">{t('internos.unidad_interna')}</span>}
                <span className="cli-status cli-status--card" style={colorVar(STATUS_COLOR[c.status || ''])}>
                  {statusLabel(c.status)}
                </span>
              </div>
              {c.contact_name && (
                <div className="cli-card__contact" title={t('clicontactos.contacto_principal_de', { nombre: c.contact_name })}>
                  <User size={12} aria-hidden="true" /><span className="cli-ellipsis">{c.contact_name}</span>
                </div>
              )}
              {(c.phone || c.contact_phone) && (
                <div className="cli-card__contact" title={c.phone ? t('clicontactos.telefono_empresa') : t('clicontactos.telefono_contacto')}>
                  <Phone size={12} aria-hidden="true" />
                  <span className="cli-ellipsis">{c.phone || c.contact_phone}</span>
                  {!c.phone && <span className="cli-card__nota">({t('clicontactos.del_contacto')})</span>}
                </div>
              )}
              <div className="cli-card__stats">
                <span title={t('clientspage.orden_proyectos')}><FolderKanban size={12} aria-hidden="true" />{c.projects_count ?? 0}</span>
                <span title={t('clientspage.orden_tickets')}><Ticket size={12} aria-hidden="true" />{c.tickets_count ?? 0}</span>
                {(c.invoices_count ?? 0) > 0 && <span title={t('clientspage.facturas')}><Receipt size={12} aria-hidden="true" />{c.invoices_count}</span>}
                <span title={t('clientspage.usuarios_portal_titulo')}><Globe size={12} aria-hidden="true" />{c.portal_users_count ?? 0}</span>
              </div>
            </Pulsable>
          ))
          : (
            <div className="cli-table">
              <div className="cli-table__head">
                <SortableTH col="name" sort={clientSort} onSort={setClientSort}>{t('clientspage.col_cliente')}</SortableTH>
                <SortableTH col="projects_count" sort={clientSort} onSort={setClientSort}>
                  <abbr title={t('clientspage.orden_proyectos')}>{t('clientspage.col_proy')}</abbr>
                </SortableTH>
                <abbr title={t('clientspage.orden_tickets')}>{t('clientspage.col_sd')}</abbr>
              </div>
              {(sortedClients as Client[]).map(c => (
                <Pulsable key={c.id} type="button" onClick={() => selectClient(c)}
                  aria-pressed={selected?.id === c.id}
                  className={selected?.id === c.id ? 'cli-table__row is-selected' : 'cli-table__row'}>
                  <div className="u-min0">
                    <div className="cli-table__name">{c.name}</div>
                    <span className="cli-status cli-status--row" style={colorVar(STATUS_COLOR[c.status || ''])}>
                      {statusLabel(c.status)}
                    </span>
                  </div>
                  <span className="cli-table__num">{c.projects_count}</span>
                  <span className="cli-table__num">{c.tickets_count}</span>
                </Pulsable>
              ))}
            </div>
          )
        }
        <div className="cli-pagination">
          <Pagination page={page} totalPages={clientsTotalPages} onChange={setPage}
            total={clientsTotal} pageSize={CLIENTS_PAGE_SIZE} maxVisible={5} />
        </div>
      </div>

      {/* Detalle del cliente */}
      <div className="cli-detail">
        {!selected ? (
          <EmptyState icon={<Building2 size={28} />} title={t('clients.selecciona_un_cliente_para_ver_su_perfil')} />
        ) : (
          <div>
            {/* Header del cliente */}
            <div className="u-mb-20">
              <div className="cli-detail__head">
                <div className="u-min0">
                  <div className="cli-detail__name">{detail?.name || selected.name}</div>
                  <div className="u-text2-base">
                    {detail?.industry && `${industryLabel(detail.industry)} · `}
                    {detail?.city && `${detail.city}, `}{detail?.country}
                    {esInterno
                      ? ` · ${t('internos.unidad_interna')}${(detail as unknown as { business_owner_name?: string } | undefined)?.business_owner_name ? ` · ${t('internos.responsable_de', { name: (detail as unknown as { business_owner_name?: string }).business_owner_name })}` : ''}`
                      : detail?.account_manager_name && ` · ${t('clientspage.account_manager', { name: detail.account_manager_name })}`}
                  </div>
                </div>
                <div className="cli-detail__actions">
                  <Button size="sm" variant="secondary" icon={<Pencil size={14} />} onClick={openEditClient}>
                    {t('clientspage.editar')}
                  </Button>
                  <span className="cli-status cli-status--head" style={colorVar(STATUS_COLOR[detail?.status || ''])}>
                    {statusLabel(detail?.status)}
                  </span>
                  {detail?.portal_config?.sla_tier && (
                    <span className="cli-status cli-status--head cli-ico" style={colorVar(SLA_COLOR[detail.portal_config.sla_tier])}>
                      <Award size={12} aria-hidden="true" />{t(`clientstabs.sla_${detail.portal_config.sla_tier}`).split(' — ')[0]}
                    </span>
                  )}
                </div>
              </div>
              {/* Datos generales de la EMPRESA */}
              {(detail?.phone || detail?.email || detail?.website || detail?.address) && (
                <div className="cli-empresa-datos">
                  {detail?.phone && <span title={t('clicontactos.telefono_empresa')}><Phone size={13} aria-hidden="true" />{detail.phone}</span>}
                  {detail?.email && <span title={t('clicontactos.email_empresa')}><Mail size={13} aria-hidden="true" />{detail.email}</span>}
                  {detail?.website && <span title={t('clientspage.campo_web')}><Globe size={13} aria-hidden="true" />{detail.website}</span>}
                  {detail?.address && <span title={t('clicontactos.direccion')}><MapPin size={13} aria-hidden="true" />{detail.address}</span>}
                </div>
              )}
              {/* Contacto principal (persona) */}
              <div className="cli-contacto-principal" role="group" aria-label={t('clicontactos.seccion_contacto_principal')}>
                <div className="u-min0">
                  <div className="cli-contacto-principal__titulo">{t('clicontactos.seccion_contacto_principal')}</div>
                  {principal ? (
                    <>
                      <div className="cli-contacto-principal__nombre">{principal.full_name}{principal.job_title && <span className="u-text2-sm"> · {principal.job_title}</span>}</div>
                      <div className="cli-empresa-datos">
                        {principal.email && <span title={t('clicontactos.email_contacto')}><Mail size={13} aria-hidden="true" />{principal.email}</span>}
                        {principal.phone && <span title={t('clicontactos.telefono_contacto')}><Phone size={13} aria-hidden="true" />{principal.phone}</span>}
                      </div>
                    </>
                  ) : (
                    <div className="cli-contacto-principal__vacio">{t('clicontactos.sin_contacto_principal')}</div>
                  )}
                </div>
                {principal && (
                  <Button size="sm" variant="secondary" icon={<Pencil size={14} />} onClick={() => setContactoAEditar(principal)}>
                    {t('clicontactos.editar_contacto')}
                  </Button>
                )}
              </div>
              {/* Chips de recursos vinculados */}
              <div className="u-wrap-8">
                {(detail?.projects?.length ?? 0) > 0 && <span className="cli-chip cli-chip--accent cli-ico"><FolderKanban size={12} aria-hidden="true" />{t('clientspage.n_proyectos', { count: detail?.projects?.length ?? 0 })}</span>}
                {(detail?.contracts?.length ?? 0) > 0 && <span className="cli-chip cli-chip--success cli-ico"><FileText size={12} aria-hidden="true" />{t('clientspage.n_contratos', { count: detail?.contracts?.length ?? 0 })}</span>}
                {(detail?.licenses?.length ?? 0) > 0 && <span className="cli-chip cli-chip--purple cli-ico"><KeyRound size={12} aria-hidden="true" />{t('clientspage.n_licencias', { count: detail?.licenses?.length ?? 0 })}</span>}
                {(detail?.portal_users?.length ?? 0) > 0 && <span className="cli-chip cli-chip--warning cli-ico"><Globe size={12} aria-hidden="true" />{t('clientspage.n_usuarios_portal', { count: detail?.portal_users?.length ?? 0 })}</span>}
              </div>
            </div>

            {/* Tabs */}
            <Tabs items={TABS} active={activeTab} onChange={setActiveTab} ariaLabel={t('clients.title')} className="cli-tabs" />

            {/* Contenido de cada tab */}
            {activeTab === 'contacts' && <ContactsTab cid={selected.id} />}
            {activeTab === 'projects' && <ProjectsTab cid={selected.id} />}
            {activeTab === 'contracts' && <ContractsTab cid={selected.id} />}
            {activeTab === 'licenses'  && <LicensesTab cid={selected.id} />}
            {activeTab === 'invoices'  && <InvoicesTab cid={selected.id} />}
            {activeTab === 'tickets' && (
              <div>
                {detail?.tickets?.length === 0
                  ? <EmptyState icon={<Ticket size={28} />} title={t('clients.sin_tickets')} description={t('clientspage.sin_tickets_desc')} />
                  : detail?.tickets?.map(tk => (
                    <div key={tk.id} className="cli-ticket">
                      <div className="u-min0">
                        <div className="u-base-600">{tk.title}</div>
                        <div className="u-text2-xs">
                          {tk.code} · {fmtDate(tk.created_at)}
                        </div>
                      </div>
                      <div className="u-row-6">
                        <span className="cli-tag cli-tag--neutral">{etiquetaCodigo(t, 'estado', tk.priority)}</span>
                        <span className="cli-tag cli-tag--accent">{etiquetaCodigo(t, 'estado', tk.status)}</span>
                      </div>
                    </div>
                  ))
                }
              </div>
            )}
            {activeTab === 'portal'   && <PortalConfigTab cid={selected.id} clientDetail={detail} />}

          </div>
        )}
      </div>

      {/* Modal editar cliente */}
      {showEdit && (
        <Modal open title={t('clientspage.editar_titulo', { name: editClientForm.name })} onClose={() => setShowEdit(false)} width={640}>
          <CamposEmpresa idBase={`${idCampo}-edit`} t={t} form={editClientForm}
            onCampo={(k, v) => { camposEdit.limpiar(k); setEditClientForm(f => ({ ...f, [k]: v })) }}
            errorDe={k => camposEdit.de(k)} opcionesSector={industryOptions} opcionesEstado={statusOptions} />
          <CamposInternos idBase={`${idCampo}-edit-interno`} form={editClientForm}
            onCampo={(k, v) => { camposEdit.limpiar(k); setEditClientForm(f => ({ ...f, [k]: v })) }}
            errorDe={k => camposEdit.de(k)} />
          <SelectorContactoPrincipal idBase={`${idCampo}-edit-contacto`} contactos={contactos}
            valor={contactoElegido} onCambiar={v => { camposEdit.limpiar('primary_contact_id'); setContactoElegido(v) }}
            nuevo={contactoNuevo} onCambiarNuevo={(k, v) => { camposEdit.limpiar(k); setContactoNuevo(n => ({ ...n, [k]: v })) }}
            errorDe={k => camposEdit.de(k)} />
          <div className="u-mb-16">
            <label id={`${idCampo}-et9`} htmlFor={`${idCampo}-9`} className="cli-label">{t('clientspage.campo_notas')}</label>
            <Textarea id={`${idCampo}-9`} aria-labelledby={`${idCampo}-et9`} value={editClientForm.notes} onChange={e => { camposEdit.limpiar('notes'); setEditClientForm(f => ({ ...f, notes: e.target.value })) }} inputClassName="cli-input" />
              {camposEdit.de('notes') && <div className="u-field-error">{camposEdit.de('notes')}</div>}
          </div>
          <div className="u-actions-8">
            <Button variant="secondary" onClick={() => setShowEdit(false)}>
              {t('clientspage.cancelar')}
            </Button>
            <Button
              loading={updatingClient}
              disabled={!editClientForm.name || updatingClient}
              onClick={() => selected && updateClient({ id: selected.id, data: {
                ...cargaDelFormulario(editClientForm),
                // Existente → primary_contact_id; nuevo → contact_* (el servidor lo crea o reutiliza).
                ...datosDeContactoPrincipal(contactos.length > 0, contactoElegido, contactoNuevo),
              } })}>
              {updatingClient ? t('clientspage.guardando') : t('clientspage.guardar_cambios')}
            </Button>
          </div>
        </Modal>
      )}

      {/* Modal editar contacto (tarjeta «Contacto principal») */}
      {contactoAEditar && selected && (
        <ModalEditarContacto cid={selected.id} contacto={contactoAEditar} onClose={() => setContactoAEditar(null)} />
      )}

      {/* Modal nuevo cliente */}
      {showCreate && (() => {
        const datosDelAlta = () => ({ ...cargaDelFormulario(newForm), ...datosDeContactoPrincipal(false, '', contactoNuevo) })
        const submitCreate = () => {
          const result = createValidation.validateForm({ ...newForm, ...contactoNuevo })
          if (!result.success) return
          create(datosDelAlta())
        }
        const errTxt = (key: string) => createValidation.errors[key] ?? camposNuevo.de(key)
        const limpiarError = (key: string) => { createValidation.clearFieldError(key); camposNuevo.limpiar(key) }
        const cerrar = () => { setShowCreate(false); createValidation.setErrors({}) }
        return (
        <Modal open title={newForm.kind === 'interno' ? t('internos.nueva_unidad') : t('clients.new_client')} onClose={cerrar} width={640}>
          <CamposEmpresa idBase={`${idCampo}-nuevo`} t={t} form={newForm}
            onCampo={(k, v) => { setNewForm(f => ({ ...f, [k]: v })); limpiarError(k) }}
            errorDe={errTxt} opcionesSector={industryOptions} opcionesEstado={statusOptions} />
          <CamposInternos idBase={`${idCampo}-nuevo-interno`} form={newForm}
            onCampo={(k, v) => { setNewForm(f => ({ ...f, [k]: v })); limpiarError(k) }}
            errorDe={errTxt} />
          <SelectorContactoPrincipal idBase={`${idCampo}-nuevo-contacto`} contactos={[]}
            valor="" onCambiar={() => undefined}
            nuevo={contactoNuevo} onCambiarNuevo={(k, v) => { setContactoNuevo(n => ({ ...n, [k]: v })); limpiarError(k) }}
            errorDe={errTxt} />
          <div className="u-mb-16">
            <label id={`${idCampo}-etnuevo-notas`} htmlFor={`${idCampo}-nuevo-notas`} className="cli-label">{t('clientspage.campo_notas')}</label>
            <Textarea id={`${idCampo}-nuevo-notas`} aria-labelledby={`${idCampo}-etnuevo-notas`} value={newForm.notes} onChange={(e: ChangeEvent<HTMLTextAreaElement>) => { const v = e.target.value; setNewForm(f => ({ ...f, notes: v })); limpiarError('notes') }} aria-invalid={errTxt('notes') ? true : undefined} inputClassName="cli-input" />
            {errTxt('notes') && <div className="u-field-error">{errTxt('notes')}</div>}
          </div>
          <div className="u-actions-8">
            <Button variant="secondary" onClick={cerrar}>{t('clientspage.cancelar')}</Button>
            <Button onClick={submitCreate} disabled={creating} loading={creating}>
              {creating ? t('clientspage.creando') : newForm.kind === 'interno' ? t('internos.crear_unidad') : t('clientspage.crear_cliente')}
            </Button>
          </div>
        </Modal>
        )
      })()}
      </div>
    </PageShell>
  )
}

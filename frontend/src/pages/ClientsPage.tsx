import type { CSSProperties, ChangeEvent } from 'react'
import { useState, useId, useMemo } from 'react'
import { z } from 'zod'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { clientsApi, unwrapList } from '../services/api'
import type { MetaDeLista } from '../services/api/tipos-plataforma'
import { Button, Spinner, EmptyState, Modal, Tabs, useSort, SortableTH, Pulsable, Select, useErroresDeCampo } from '../components/ui'
import Pagination from '../components/ui/Pagination'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { extractErr, fmtDate } from '../utils/helpers'
import { etiquetaCodigo } from '../i18n/etiquetaCodigo'
import { useFormValidation } from '../hooks/useFormValidation'
import { useAppT } from '../i18n/AppLangContext'
import { Award, Briefcase, Building2, FileText, FolderKanban, Globe, KeyRound, LayoutGrid, List, Pencil, Plus, Receipt, Ticket, User, Users } from 'lucide-react'
import {
  ProjectsTab,
  ContactsTab,
  LicensesTab,
  ContractsTab,
  InvoicesTab,
  PortalConfigTab,
} from './clients/ClientsPageTabs'
import './ClientsPage.css'

type Traductor = ReturnType<typeof useAppT>

// Estados que se pueden asignar a un cliente; la etiqueta sale de i18n
// (`clientspage.estado_<clave>`) y el color es un token del tema.
const STATUS_COLOR: Record<string, string> = {
  active: 'var(--success)',
  planning: 'var(--accent)',
  on_hold: 'var(--warning)',
  completed: 'var(--text-2)',
  cancelled: 'var(--danger)',
  new: 'var(--accent)',
  reviewing: 'var(--warning)',
  estimated: 'var(--accent)',
  approved: 'var(--success)',
  rejected: 'var(--danger)',
  in_development: 'var(--accent)',
  done: 'var(--success)',
  pending: 'var(--text-2)',
  in_progress: 'var(--accent)',
  passed: 'var(--success)',
  failed: 'var(--danger)',
  conditional: 'var(--warning)',
}
const STATUS_KEYS = Object.keys(STATUS_COLOR)
const SLA_COLOR: Record<string, string> = {
  enterprise: 'var(--purple)',
  gold: 'var(--warning)',
  silver: 'var(--text-2)',
  bronze: 'var(--warning)',
}
const INDUSTRIES = ['technology', 'finance', 'healthcare', 'retail', 'manufacturing', 'education', 'consulting', 'real_estate', 'media', 'other']

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
  contact_name?: string
  contact_email?: string
  contact_phone?: string
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
    contact_name: optionalString(200),
    contact_email: optionalEmail,
    contact_phone: optionalString(50),
    status: z.string().min(1),
    industry: z.string().min(1),
    notes: z.union([z.literal(''), z.string().max(2000, max(2000))]).optional(),
  })
}

const FORM_VACIO = { name: '', short_name: '', tax_id: '', contact_name: '', contact_email: '', contact_phone: '', status: 'active', industry: 'other', notes: '' }

// ── Página principal ──────────────────────────────────────────────────────────
export default function ClientsPage(): JSX.Element {
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [search, setSearch] = useState('')
  const [statusF, setStatusF] = useState('')
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
  const [clientView, setClientView] = useState('grid')
  const camposNuevo = useErroresDeCampo()
  const camposEdit = useErroresDeCampo()

  const statusLabel = (s: string | undefined) => (s && STATUS_COLOR[s] ? t(`clientspage.estado_${s}`) : s)
  const industryLabel = (i: string) => (INDUSTRIES.includes(i) ? t(`clientspage.sector_${i}`) : i)

  // Lista paginada en el servidor (page/page_size; total en meta.total).
  const { data: paginaClientes, isLoading } = useQuery<{ items: Client[]; total: number }>({
    queryKey: ['clients', search, statusF, page],
    queryFn: () => clientsApi.list({ q: search || undefined, status: statusF || undefined, page, page_size: CLIENTS_PAGE_SIZE })
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

  const { mutate: create, isPending: creating } = useMutation({
    mutationFn: (d: Record<string, unknown>) => clientsApi.create(d),
    onMutate: () => camposNuevo.limpiar(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['clients'] })
      setShowCreate(false)
      setNewForm(FORM_VACIO)
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
      setShowEdit(false)
      toast.success(t('clientspage.cliente_actualizado'))
    },
    onError: (e: unknown) => { if (!camposEdit.recoger(e)) toast.error(extractErr(e, t('clientspage.error_actualizar'))) },
  })

  const openEditClient = () => {
    if (!selected) return
    setEditClientForm({
      name:          selected.name          || '',
      short_name:    selected.short_name    || '',
      tax_id:        selected.tax_id        || '',
      industry:      selected.industry      || 'other',
      contact_name:  selected.contact_name  || '',
      contact_email: selected.contact_email || '',
      contact_phone: selected.contact_phone || '',
      status:        selected.status        || 'active',
      notes:         selected.notes         || '',
      website:       selected.website       || '',
      country:       selected.country       || '',
      city:          selected.city          || '',
    })
    setShowEdit(true)
  }

  const TABS = [
    { id: 'contacts', label: t('clientspage.tab_contactos'), icon: <Users size={14} /> },
    { id: 'projects', label: t('clientspage.tab_proyectos'), icon: <FolderKanban size={14} /> },
    { id: 'contracts', label: t('clientspage.tab_contratos'), icon: <FileText size={14} /> },
    { id: 'licenses', label: t('clientspage.tab_licencias'), icon: <KeyRound size={14} /> },
    { id: 'invoices', label: t('clientspage.tab_facturas'), icon: <Receipt size={14} /> },
    { id: 'tickets', label: t('clientspage.tab_tickets'), icon: <Ticket size={14} /> },
    { id: 'portal', label: t('clientspage.tab_portal'), icon: <Globe size={14} /> },
  ]
  const newClientButton = (
    <Button data-tour="btn-new-client" icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{t('clients.new_client')}</Button>
  )

  const selectClient = (c: Client) => { setSelected(c); setActiveTab('contacts') }
  const statusOptions = STATUS_KEYS.map(k => <option key={k} value={k}>{statusLabel(k)}</option>)
  const industryOptions = INDUSTRIES.map(i => <option key={i} value={i}>{industryLabel(i)}</option>)

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
                <span className="cli-status cli-status--card" style={colorVar(STATUS_COLOR[c.status || ''])}>
                  {statusLabel(c.status)}
                </span>
              </div>
              {c.contact_name && <div className="cli-card__contact"><User size={12} aria-hidden="true" /><span className="cli-ellipsis">{c.contact_name}</span></div>}
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
                    {detail?.account_manager_name && ` · ${t('clientspage.account_manager', { name: detail.account_manager_name })}`}
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
        <Modal open title={t('clientspage.editar_titulo', { name: editClientForm.name })} onClose={() => setShowEdit(false)} width={600}>
          <div className="cli-form-grid">
            <div>
              <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="cli-label">{t('clientspage.campo_nombre')}</label>
              <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={editClientForm.name}
                onChange={e => { camposEdit.limpiar('name'); setEditClientForm(f => ({ ...f, name: e.target.value })) }}
                className="cli-input" />
              {camposEdit.de('name') && <div className="u-field-error">{camposEdit.de('name')}</div>}
            </div>
            <div>
              <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="cli-label">{t('clientspage.campo_nombre_corto')}</label>
              <input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={editClientForm.short_name}
                onChange={e => { camposEdit.limpiar('short_name'); setEditClientForm(f => ({ ...f, short_name: e.target.value })) }}
                className="cli-input" />
              {camposEdit.de('short_name') && <div className="u-field-error">{camposEdit.de('short_name')}</div>}
            </div>
            <div>
              <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="cli-label">{t('clientspage.campo_cif')}</label>
              <input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={editClientForm.tax_id}
                onChange={e => { camposEdit.limpiar('tax_id'); setEditClientForm(f => ({ ...f, tax_id: e.target.value })) }}
                className="cli-input" />
              {camposEdit.de('tax_id') && <div className="u-field-error">{camposEdit.de('tax_id')}</div>}
            </div>
            <div>
              <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="cli-label">{t('clientspage.campo_sector')}</label>
              <Select suelto placeholder={false} id={`${idCampo}-4`} value={editClientForm.industry}
                onChange={e => { camposEdit.limpiar('industry'); setEditClientForm(f => ({ ...f, industry: e.target.value })) }}
                className="cli-input">
                {industryOptions}
              </Select>
              {camposEdit.de('industry') && <div className="u-field-error">{camposEdit.de('industry')}</div>}
            </div>
            <div>
              <label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="cli-label">{t('clientspage.campo_contacto')}</label>
              <input id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={editClientForm.contact_name}
                onChange={e => { camposEdit.limpiar('contact_name'); setEditClientForm(f => ({ ...f, contact_name: e.target.value })) }}
                className="cli-input" />
              {camposEdit.de('contact_name') && <div className="u-field-error">{camposEdit.de('contact_name')}</div>}
            </div>
            <div>
              <label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} className="cli-label">{t('clientspage.campo_email')}</label>
              <input id={`${idCampo}-6`} aria-labelledby={`${idCampo}-et6`} type="email" value={editClientForm.contact_email}
                onChange={e => { camposEdit.limpiar('contact_email'); setEditClientForm(f => ({ ...f, contact_email: e.target.value })) }}
                className="cli-input" />
              {camposEdit.de('contact_email') && <div className="u-field-error">{camposEdit.de('contact_email')}</div>}
            </div>
            <div>
              <label id={`${idCampo}-et7`} htmlFor={`${idCampo}-7`} className="cli-label">{t('clients.telefono')}</label>
              <input id={`${idCampo}-7`} aria-labelledby={`${idCampo}-et7`} value={editClientForm.contact_phone}
                onChange={e => { camposEdit.limpiar('contact_phone'); setEditClientForm(f => ({ ...f, contact_phone: e.target.value })) }}
                className="cli-input" />
              {camposEdit.de('contact_phone') && <div className="u-field-error">{camposEdit.de('contact_phone')}</div>}
            </div>
            <div>
              <label id={`${idCampo}-et8`} htmlFor={`${idCampo}-8`} className="cli-label">{t('clientspage.campo_estado')}</label>
              <Select suelto placeholder={false} id={`${idCampo}-8`} value={editClientForm.status}
                onChange={e => { camposEdit.limpiar('status'); setEditClientForm(f => ({ ...f, status: e.target.value })) }}
                className="cli-input">
                {statusOptions}
              </Select>
              {camposEdit.de('status') && <div className="u-field-error">{camposEdit.de('status')}</div>}
            </div>
            <div>
              <label id={`${idCampo}-etpais`} htmlFor={`${idCampo}-pais`} className="cli-label">{t('clients.pais')}</label>
              <input id={`${idCampo}-pais`} aria-labelledby={`${idCampo}-etpais`} value={editClientForm.country}
                onChange={e => { camposEdit.limpiar('country'); setEditClientForm(f => ({ ...f, country: e.target.value })) }}
                className="cli-input" placeholder={t('clients.pais')} />
              {camposEdit.de('country') && <div className="u-field-error">{camposEdit.de('country')}</div>}
            </div>
            <div>
              <label id={`${idCampo}-etciudad`} htmlFor={`${idCampo}-ciudad`} className="cli-label">{t('clientspage.campo_ciudad')}</label>
              <input id={`${idCampo}-ciudad`} aria-labelledby={`${idCampo}-etciudad`} value={editClientForm.city}
                onChange={e => { camposEdit.limpiar('city'); setEditClientForm(f => ({ ...f, city: e.target.value })) }}
                className="cli-input" placeholder={t('clientspage.campo_ciudad')} />
              {camposEdit.de('city') && <div className="u-field-error">{camposEdit.de('city')}</div>}
            </div>
            <div className="u-col-full">
              <label id={`${idCampo}-etweb`} htmlFor={`${idCampo}-web`} className="cli-label">{t('clientspage.campo_web')}</label>
              <input id={`${idCampo}-web`} aria-labelledby={`${idCampo}-etweb`} value={editClientForm.website}
                onChange={e => { camposEdit.limpiar('website'); setEditClientForm(f => ({ ...f, website: e.target.value })) }}
                className="cli-input" placeholder={t('clientspage.placeholder_web')} />
              {camposEdit.de('website') && <div className="u-field-error">{camposEdit.de('website')}</div>}
            </div>
          </div>
          <div className="u-mb-16">
            <label id={`${idCampo}-et9`} htmlFor={`${idCampo}-9`} className="cli-label">{t('clientspage.campo_notas')}</label>
            <textarea id={`${idCampo}-9`} aria-labelledby={`${idCampo}-et9`} value={editClientForm.notes}
              onChange={e => { camposEdit.limpiar('notes'); setEditClientForm(f => ({ ...f, notes: e.target.value })) }}
              className="cli-input" />
              {camposEdit.de('notes') && <div className="u-field-error">{camposEdit.de('notes')}</div>}
          </div>
          <div className="u-actions-8">
            <Button variant="secondary" onClick={() => setShowEdit(false)}>
              {t('clientspage.cancelar')}
            </Button>
            <Button
              loading={updatingClient}
              disabled={!editClientForm.name || updatingClient}
              onClick={() => selected && updateClient({ id: selected.id, data: editClientForm })}>
              {updatingClient ? t('clientspage.guardando') : t('clientspage.guardar_cambios')}
            </Button>
          </div>
        </Modal>
      )}

      {/* Modal nuevo cliente */}
      {showCreate && (() => {
        const setCreateField = (key: string) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
          const value = e.target.value
          setNewForm(f => ({ ...f, [key]: value }))
          createValidation.clearFieldError(key)
          camposNuevo.limpiar(key)
        }
        const submitCreate = () => {
          const result = createValidation.validateForm(newForm)
          if (!result.success) return
          create(newForm)
        }
        const errId = (key: string) => `${idCampo}-err-${key}`
        // Props de error de un campo: marca aria-invalid (lo pinta .cli-input) y lo enlaza al mensaje.
        const errTxt = (key: string) => createValidation.errors[key] ?? camposNuevo.de(key)
        const errProps = (key: string) => errTxt(key)
          ? { 'aria-invalid': true as const, 'aria-describedby': errId(key) }
          : {}
        const errField = (key: string) => errTxt(key) && (
          <div id={errId(key)} className="u-field-error">{errTxt(key)}</div>
        )
        return (
        <Modal open title={t('clients.new_client')} onClose={() => { setShowCreate(false); createValidation.setErrors({}) }} width={600}>
          <div className="cli-form-grid">
            <div><label id={`${idCampo}-etnuevo515`} htmlFor={`${idCampo}-nuevo515`} className="cli-label">{t('clientspage.campo_nombre')}</label><input id={`${idCampo}-nuevo515`} aria-labelledby={`${idCampo}-etnuevo515`} value={newForm.name} onChange={setCreateField('name')} className="cli-input" {...errProps('name')} />{errField('name')}</div>
            <div><label id={`${idCampo}-etnuevo516`} htmlFor={`${idCampo}-nuevo516`} className="cli-label">{t('clientspage.campo_nombre_corto')}</label><input id={`${idCampo}-nuevo516`} aria-labelledby={`${idCampo}-etnuevo516`} value={newForm.short_name} onChange={setCreateField('short_name')} className="cli-input" {...errProps('short_name')} />{errField('short_name')}</div>
            <div><label id={`${idCampo}-etnuevo517`} htmlFor={`${idCampo}-nuevo517`} className="cli-label">{t('clientspage.campo_cif')}</label><input id={`${idCampo}-nuevo517`} aria-labelledby={`${idCampo}-etnuevo517`} value={newForm.tax_id} onChange={setCreateField('tax_id')} className="cli-input" {...errProps('tax_id')} />{errField('tax_id')}</div>
            <div><label id={`${idCampo}-etnuevo518`} htmlFor={`${idCampo}-nuevo518`} className="cli-label">{t('clientspage.campo_sector')}</label>
              <Select suelto placeholder={false} id={`${idCampo}-nuevo518`} value={newForm.industry} onChange={setCreateField('industry')} className="cli-input">
                {industryOptions}
              </Select>{errField('industry')}
            </div>
            <div><label id={`${idCampo}-etnuevo523`} htmlFor={`${idCampo}-nuevo523`} className="cli-label">{t('clientspage.campo_contacto')}</label><input id={`${idCampo}-nuevo523`} aria-labelledby={`${idCampo}-etnuevo523`} value={newForm.contact_name} onChange={setCreateField('contact_name')} className="cli-input" {...errProps('contact_name')} />{errField('contact_name')}</div>
            <div><label id={`${idCampo}-etnuevo524`} htmlFor={`${idCampo}-nuevo524`} className="cli-label">{t('clientspage.campo_email')}</label><input id={`${idCampo}-nuevo524`} aria-labelledby={`${idCampo}-etnuevo524`} type="email" value={newForm.contact_email} onChange={setCreateField('contact_email')} className="cli-input" {...errProps('contact_email')} />{errField('contact_email')}</div>
            <div><label id={`${idCampo}-etnuevo525`} htmlFor={`${idCampo}-nuevo525`} className="cli-label">{t('clients.telefono')}</label><input id={`${idCampo}-nuevo525`} aria-labelledby={`${idCampo}-etnuevo525`} value={newForm.contact_phone} onChange={setCreateField('contact_phone')} className="cli-input" {...errProps('contact_phone')} />{errField('contact_phone')}</div>
            <div><label id={`${idCampo}-etnuevo526`} htmlFor={`${idCampo}-nuevo526`} className="cli-label">{t('clientspage.campo_estado')}</label>
              <Select suelto placeholder={false} id={`${idCampo}-nuevo526`} value={newForm.status} onChange={setCreateField('status')} className="cli-input">
                {statusOptions}
              </Select>{errField('status')}
            </div>
          </div>
          <div className="u-mb-16"><label id={`${idCampo}-etnuevo532`} htmlFor={`${idCampo}-nuevo532`} className="cli-label">{t('clientspage.campo_notas')}</label><textarea id={`${idCampo}-nuevo532`} aria-labelledby={`${idCampo}-etnuevo532`} value={newForm.notes} onChange={setCreateField('notes')} className="cli-input" {...errProps('notes')} />{errField('notes')}</div>
          <div className="u-actions-8">
            <Button variant="secondary" onClick={() => { setShowCreate(false); createValidation.setErrors({}) }}>{t('clientspage.cancelar')}</Button>
            <Button onClick={submitCreate} disabled={creating} loading={creating}>
              {creating ? t('clientspage.creando') : t('clientspage.crear_cliente')}
            </Button>
          </div>
        </Modal>
        )
      })()}
      </div>
    </PageShell>
  )
}

// Estilos reutilizables globales (asegurar que siempre estén definidos)
const panel = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12 }
const inp = { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', width: '100%', boxSizing: 'border-box' }
const lbl = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 5 }

// Estado global para clientes (usado en toda la página)
const STATUS_LABEL = {
  active: 'Activo',
  planning: 'Planificación',
  on_hold: 'En espera',
  completed: 'Completado',
  cancelled: 'Cancelado',
  new: 'Nueva',
  reviewing: 'En revisión',
  estimated: 'Presupuestada',
  approved: 'Aprobada',
  rejected: 'Rechazada',
  in_development: 'En desarrollo',
  done: 'Completada',
  pending: 'Pendiente',
  in_progress: 'En progreso',
  passed: 'Aprobado',
  failed: 'Rechazado',
  conditional: 'Con reservas',
}
const STATUS_COLOR = {
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
const SLA_COLOR = {
  enterprise: 'var(--purple)',
  gold: 'var(--warning)',
  silver: 'var(--text-2)',
  bronze: 'var(--warning)',
}
// Refuerzo: exportar para debug si es necesario
// export const inp = inp;
import { useState } from 'react'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'
import { Button, Spinner, EmptyState, Modal, useSort, SortableTH, ViewToggle } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { extractErr} from '../utils/helpers'
import { useAppT } from '../i18n/AppLangContext'
import { Briefcase } from 'lucide-react'
import {
  ProjectsTab,
  ContactsTab,
  LicensesTab,
  ContractsTab,
  PortalConfigTab,
} from './clients/ClientsPageTabs'





// ── Página principal ──────────────────────────────────────────────────────────
export default function ClientsPage() {
  const _t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [search, setSearch] = useState('')
  const [statusF, setStatusF] = useState('')
  const [sortBy, setSortBy] = useState('name')
  const [selected, setSelected] = useState(null)
  const [activeTab, setActiveTab] = useState('contacts')
  const [showCreate, setShowCreate] = useState(false)
  const [newForm, setNewForm] = useState({ name: '', short_name: '', tax_id: '', contact_name: '', contact_email: '', contact_phone: '', status: 'active', industry: 'other', notes: '' })
  const [showEdit, setShowEdit] = useState(false)
  const [editClientForm, setEditClientForm] = useState({})
  const [clientView, setClientView] = useState('grid')

  const { data: clients = [], isLoading } = useQuery({
    queryKey: ['clients', search, statusF],
    queryFn: () => api.get('/clients', { params: { q: search || undefined, status: statusF || undefined } }).then(r => r.data),
  })

  const { sort: clientSort, setSort: setClientSort, sortedData: sortedClients } = useSort(clients, sortBy)

  const { data: detail } = useQuery({
    queryKey: ['client-detail', selected?.id],
    queryFn: () => api.get(`/clients/${selected.id}`).then(r => r.data),
    enabled: !!selected,
  })

  const { mutate: create, isPending: creating } = useMutation({
    mutationFn: d => api.post('/clients', d),
    onSuccess: (_res) => {
      qc.invalidateQueries(['clients'])
      setShowCreate(false)
      setNewForm({ name: '', short_name: '', tax_id: '', contact_name: '', contact_email: '', contact_phone: '', status: 'active', industry: 'other', notes: '' })
      toast.success('Cliente creado correctamente')
    },
    onError: e => toast.error(extractErr(e, 'Error al crear cliente')),
  })

  const { mutate: updateClient, isPending: updatingClient } = useMutation({
    mutationFn: ({ id, data }) => api.patch(`/clients/${id}`, data),
    onSuccess: () => {
      qc.invalidateQueries(['clients'])
      qc.invalidateQueries(['client-detail', selected?.id])
      setShowEdit(false)
      toast.success('Cliente actualizado correctamente')
    },
    onError: e => toast.error(extractErr(e, 'Error al actualizar cliente')),
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
    { id: 'contacts', label: 'Contactos' },
    { id: 'projects', label: '⬡ Proyectos' },
    { id: 'contracts',label: 'Contratos' },
    { id: 'licenses', label: 'Licencias' },
    { id: 'tickets',  label: 'Tickets SD' },
    { id: 'portal',   label: 'Portal' },
  ]

  const INDUSTRIES = ['technology','finance','healthcare','retail','manufacturing','education','consulting','real_estate','media','other']

  return (
    <PageShell>
      <PageHeader
        icon={<Briefcase size={18} />}
        title={_t('clients.title')}
        subtitle={_t('clients.subtitle')}
        actions={
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <ViewToggle view={clientView} onChange={setClientView} />
            <Button data-tour="btn-new-client" onClick={() => setShowCreate(true)}>+ {_t('clients.new_client')}</Button>
          </div>
        }
      />
      <div style={{ display: 'grid', gridTemplateColumns: '320px 1fr', gap: 0 }}>
      {/* Lista de clientes */}
      <div style={{ paddingRight: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <div style={{ fontSize: "var(--text-base)", fontWeight: 600, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{_t('clients.title')}</div>
        </div>
        <input value={search} onChange={e => setSearch(e.target.value)}
          placeholder="Buscar cliente por nombre o codigo" aria-label="Buscar cliente por nombre o codigo" style={{ ...inp, marginBottom: 8 }} />
        <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
          <select value={statusF} onChange={e => setStatusF(e.target.value)} style={{ ...inp, flex: 1 }}>
            <option value="">Todos los estados</option>
            {Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <select value={sortBy} onChange={e => setSortBy(e.target.value)} style={{ ...inp, width: 'auto' }}>
            <option value="name">A-Z</option>
            <option value="projects_count">Proyectos</option>
            <option value="tickets_count">Tickets</option>
            <option value="status">Estado</option>
          </select>
        </div>
        {isLoading ? <Spinner /> : clients.length === 0
          ? <EmptyState icon="🏢" title="Sin clientes" description="Crea el primer cliente para empezar" />
          : clientView === 'grid' ? sortedClients.map(c => (
            <button key={c.id} type="button" onClick={() => { setSelected(c); setActiveTab('contacts') }}
              style={{ ...panel, padding: '14px 16px', marginBottom: 8, cursor: 'pointer', borderColor: selected?.id === c.id ? 'var(--accent)' : 'var(--surface-4)', background: selected?.id === c.id ? 'var(--accent-muted)' : 'var(--surface-2)', transition: 'all 0.12s' }}
              onMouseEnter={e => { if (selected?.id !== c.id) { e.currentTarget.style.borderColor = 'var(--surface-5)' } }}
              onMouseLeave={e => { if (selected?.id !== c.id) { e.currentTarget.style.borderColor = 'var(--surface-4)' } }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
                <div style={{ fontSize: "var(--text-md)", fontWeight: 600 }}>{c.name}</div>
                <span style={{ fontSize: "var(--text-2xs)", padding: '2px 8px', borderRadius: 20, background: (STATUS_COLOR[c.status] || 'var(--text-2)') + '20', color: STATUS_COLOR[c.status] || 'var(--text-2)', fontWeight: 700, whiteSpace: 'nowrap' }}>
                  {STATUS_LABEL[c.status] || c.status}
                </span>
              </div>
              {c.contact_name && <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginBottom: 4 }}>👤 {c.contact_name}</div>}
              <div style={{ display: 'flex', gap: 12, fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>
                <span>⬡ {c.projects_count}</span>
                <span>🎫 {c.tickets_count}</span>
                {c.invoices_count > 0 && <span>🧾 {c.invoices_count}</span>}
                <span>👤 {c.portal_users_count}</span>
              </div>
            </button>
          ))
          : (
            <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, overflow: 'hidden' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 50px 40px', gap: 8, padding: '8px 12px', borderBottom: '1px solid var(--surface-4)', fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', alignItems: 'center' }}>
                <SortableTH col="name" sort={clientSort} onSort={setClientSort}>Cliente</SortableTH>
                <SortableTH col="projects_count" sort={clientSort} onSort={setClientSort}>Proy</SortableTH>
                <span>SD</span>
              </div>
              {sortedClients.map(c => (
                <button key={c.id} type="button" onClick={() => { setSelected(c); setActiveTab('contacts') }}
                  style={{ display: 'grid', gridTemplateColumns: '1fr 50px 40px', gap: 8, padding: '9px 12px', borderBottom: '1px solid var(--surface-4)30', alignItems: 'center', cursor: 'pointer', background: selected?.id === c.id ? 'var(--accent-muted)' : 'transparent' }}
                  onMouseEnter={e => { if (selected?.id !== c.id) e.currentTarget.style.background = 'var(--surface-3)' }}
                  onMouseLeave={e => { if (selected?.id !== c.id) e.currentTarget.style.background = 'transparent' }}>
                  <div>
                    <div style={{ fontSize: "var(--text-sm)", fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.name}</div>
                    <span style={{ fontSize: "var(--text-3xs)", padding: '1px 5px', borderRadius: 10, background: (STATUS_COLOR[c.status] || 'var(--text-2)') + '20', color: STATUS_COLOR[c.status] || 'var(--text-2)', fontWeight: 700 }}>
                      {STATUS_LABEL[c.status] || c.status}
                    </span>
                  </div>
                  <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', textAlign: 'center' }}>{c.projects_count}</span>
                  <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', textAlign: 'center' }}>{c.tickets_count}</span>
                </button>
              ))}
            </div>
          )
        }
      </div>

      {/* Detalle del cliente */}
      <div style={{ borderLeft: '1px solid var(--surface-4)', paddingLeft: 24 }}>
        {!selected ? (
          <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-3)' }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: "var(--text-6xl)", marginBottom: 16 }}>🏢</div>
              <div style={{ fontSize: "var(--text-md)" }}>Selecciona un cliente para ver su perfil completo</div>
            </div>
          </div>
        ) : (
          <div>
            {/* Header del cliente */}
            <div style={{ marginBottom: 20 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                <div>
                  <div style={{ fontSize: "var(--text-xl-em)", fontWeight: 800 }}>{detail?.name || selected.name}</div>
                  <div style={{ fontSize: "var(--text-base)", color: 'var(--text-2)' }}>
                    {detail?.industry && `${detail.industry} · `}
                    {detail?.city && `${detail.city}, `}{detail?.country}
                    {detail?.account_manager_name && ` · Account: ${detail.account_manager_name}`}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <button onClick={openEditClient}
                    style={{ fontSize: "var(--text-sm)", padding: '5px 14px', borderRadius: 8, border: '1px solid var(--surface-4)',
                      background: 'transparent', color: 'var(--accent)', cursor: 'pointer', fontFamily: 'inherit',
                      fontWeight: 600, display: 'flex', alignItems: 'center', gap: 5 }}>
                    ✏️ Editar
                  </button>
                  <span style={{ fontSize: "var(--text-xs)", padding: '4px 12px', borderRadius: 20, background: (STATUS_COLOR[detail?.status] || 'var(--text-2)') + '20', color: STATUS_COLOR[detail?.status] || 'var(--text-2)', fontWeight: 700 }}>
                    {STATUS_LABEL[detail?.status] || detail?.status}
                  </span>
                  {detail?.portal_config?.sla_tier && (
                    <span style={{ fontSize: "var(--text-xs)", padding: '4px 12px', borderRadius: 20, background: (SLA_COLOR[detail.portal_config.sla_tier] || 'var(--text-2)') + '20', color: SLA_COLOR[detail.portal_config.sla_tier] || 'var(--text-2)', fontWeight: 700 }}>
                      ⭐ {detail.portal_config.sla_tier.toUpperCase()}
                    </span>
                  )}
                </div>
              </div>
              {/* Chips de recursos vinculados */}
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {detail?.projects?.length > 0 && <span style={{ fontSize: "var(--text-xs)", padding: '3px 10px', borderRadius: 20, background: 'var(--accent-muted)', color: 'var(--accent)' }}>⬡ {detail.projects.length} proyectos</span>}
                {detail?.contracts?.length > 0 && <span style={{ fontSize: "var(--text-xs)", padding: '3px 10px', borderRadius: 20, background: 'var(--success-bg)', color: 'var(--success)' }}>📄 {detail.contracts.length} contratos</span>}
                {detail?.licenses?.length > 0 && <span style={{ fontSize: "var(--text-xs)", padding: '3px 10px', borderRadius: 20, background: 'var(--purple-bg)', color: 'var(--purple)' }}>🔑 {detail.licenses.length} licencias</span>}
                {detail?.portal_users?.length > 0 && <span style={{ fontSize: "var(--text-xs)", padding: '3px 10px', borderRadius: 20, background: 'var(--warning-bg)', color: 'var(--warning)' }}>👤 {detail.portal_users.length} usuarios portal</span>}
              </div>
            </div>

            {/* Tabs */}
            <div style={{ display: 'flex', gap: 4, marginBottom: 20, flexWrap: 'wrap', borderBottom: '1px solid var(--surface-4)', paddingBottom: 12 }}>
              {TABS.map(t => (
                <button key={t.id} onClick={() => setActiveTab(t.id)}
                  style={{ padding: '7px 16px', borderRadius: 8, border: `1px solid ${activeTab === t.id ? 'var(--accent-glow)' : 'transparent'}`,
                    background: activeTab === t.id ? 'var(--accent-muted)' : 'transparent', color: activeTab === t.id ? 'var(--accent)' : 'var(--text-2)',
                    fontSize: "var(--text-sm)", fontWeight: activeTab === t.id ? 700 : 400, cursor: 'pointer', fontFamily: 'inherit' }}>
                  {t.label}
                </button>
              ))}
            </div>

            {/* Contenido de cada tab */}
            {activeTab === 'contacts' && <ContactsTab cid={selected.id} />}
            {activeTab === 'projects' && <ProjectsTab cid={selected.id} />}
            {activeTab === 'contracts' && <ContractsTab cid={selected.id} />}
            {activeTab === 'licenses'  && <LicensesTab cid={selected.id} />}
            {activeTab === 'tickets' && (
              <div>
                {detail?.tickets?.length === 0
                  ? <EmptyState icon="🎫" title="Sin tickets" description="Este cliente todavia no tiene tickets asociados" />
                  : detail?.tickets?.map(t => (
                    <div key={t.id} style={{ ...panel, padding: '12px 16px', marginBottom: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div>
                        <div style={{ fontSize: "var(--text-base)", fontWeight: 600 }}>{t.title}</div>
                        <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>
                          {t.linked_resource_type && `${t.linked_resource_type} · `}{t.created_at?.slice(0, 10)}
                        </div>
                      </div>
                      <div style={{ display: 'flex', gap: 6 }}>
                        <span style={{ fontSize: "var(--text-2xs)", padding: '2px 6px', borderRadius: 4, background: 'var(--surface-4)', color: 'var(--text-2)' }}>{t.priority}</span>
                        <span style={{ fontSize: "var(--text-2xs)", padding: '2px 6px', borderRadius: 4, background: 'var(--accent-muted)', color: 'var(--accent)' }}>{t.status}</span>
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
        <Modal open title={`✏️ Editar: ${editClientForm.name}`} onClose={() => setShowEdit(false)} width={600}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
            <div>
              <label style={lbl}>Nombre *</label>
              <input value={editClientForm.name}
                onChange={e => setEditClientForm(f => ({ ...f, name: e.target.value }))}
                style={inp} />
            </div>
            <div>
              <label style={lbl}>Nombre corto</label>
              <input value={editClientForm.short_name}
                onChange={e => setEditClientForm(f => ({ ...f, short_name: e.target.value }))}
                style={inp} />
            </div>
            <div>
              <label style={lbl}>CIF / NIF / VAT</label>
              <input value={editClientForm.tax_id}
                onChange={e => setEditClientForm(f => ({ ...f, tax_id: e.target.value }))}
                style={inp} />
            </div>
            <div>
              <label style={lbl}>Sector</label>
              <select value={editClientForm.industry}
                onChange={e => setEditClientForm(f => ({ ...f, industry: e.target.value }))}
                style={inp}>
                {INDUSTRIES.map(i => (
                  <option key={i} value={i}>{i.charAt(0).toUpperCase() + i.slice(1)}</option>
                ))}
              </select>
            </div>
            <div>
              <label style={lbl}>Contacto principal</label>
              <input value={editClientForm.contact_name}
                onChange={e => setEditClientForm(f => ({ ...f, contact_name: e.target.value }))}
                style={inp} />
            </div>
            <div>
              <label style={lbl}>Email contacto</label>
              <input type="email" value={editClientForm.contact_email}
                onChange={e => setEditClientForm(f => ({ ...f, contact_email: e.target.value }))}
                style={inp} />
            </div>
            <div>
              <label style={lbl}>Teléfono</label>
              <input value={editClientForm.contact_phone}
                onChange={e => setEditClientForm(f => ({ ...f, contact_phone: e.target.value }))}
                style={inp} />
            </div>
            <div>
              <label style={lbl}>Estado</label>
              <select value={editClientForm.status}
                onChange={e => setEditClientForm(f => ({ ...f, status: e.target.value }))}
                style={inp}>
                {Object.entries(STATUS_LABEL).map(([k, v]) => (
                  <option key={k} value={k}>{v}</option>
                ))}
              </select>
            </div>
            <div>
              <label style={lbl}>País</label>
              <input value={editClientForm.country}
                onChange={e => setEditClientForm(f => ({ ...f, country: e.target.value }))}
                style={inp} placeholder="Pais" aria-label="Pais" />
            </div>
            <div>
              <label style={lbl}>Ciudad</label>
              <input value={editClientForm.city}
                onChange={e => setEditClientForm(f => ({ ...f, city: e.target.value }))}
                style={inp} placeholder="Ciudad" aria-label="Ciudad" />
            </div>
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={lbl}>Website</label>
              <input value={editClientForm.website}
                onChange={e => setEditClientForm(f => ({ ...f, website: e.target.value }))}
                style={inp} placeholder="https://cliente.com" aria-label="Sitio web" />
            </div>
          </div>
          <div style={{ marginBottom: 16 }}>
            <label style={lbl}>Notas</label>
            <textarea value={editClientForm.notes}
              onChange={e => setEditClientForm(f => ({ ...f, notes: e.target.value }))}
              style={{ ...inp, minHeight: 70, resize: 'vertical' }} />
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={() => setShowEdit(false)}
              style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8,
                padding: '7px 16px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>
              Cancelar
            </button>
            <Button
              loading={updatingClient}
              disabled={!editClientForm.name || updatingClient}
              onClick={() => updateClient({ id: selected.id, data: editClientForm })}>
              {updatingClient ? '⟳ Guardando...' : '💾 Guardar cambios'}
            </Button>
          </div>
        </Modal>
      )}

      {/* Modal nuevo cliente */}
      {showCreate && (
        <Modal open title="Nuevo cliente" onClose={() => setShowCreate(false)} width={600}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
            <div><label style={lbl}>Nombre *</label><input value={newForm.name} onChange={e => setNewForm(f => ({ ...f, name: e.target.value }))} style={inp} /></div>
            <div><label style={lbl}>Nombre corto</label><input value={newForm.short_name} onChange={e => setNewForm(f => ({ ...f, short_name: e.target.value }))} style={inp} /></div>
            <div><label style={lbl}>CIF / NIF / VAT</label><input value={newForm.tax_id} onChange={e => setNewForm(f => ({ ...f, tax_id: e.target.value }))} style={inp} /></div>
            <div><label style={lbl}>Sector</label>
              <select value={newForm.industry} onChange={e => setNewForm(f => ({ ...f, industry: e.target.value }))} style={inp}>
                {INDUSTRIES.map(i => <option key={i} value={i}>{i.charAt(0).toUpperCase() + i.slice(1)}</option>)}
              </select>
            </div>
            <div><label style={lbl}>Contacto principal</label><input value={newForm.contact_name} onChange={e => setNewForm(f => ({ ...f, contact_name: e.target.value }))} style={inp} /></div>
            <div><label style={lbl}>Email contacto</label><input type="email" value={newForm.contact_email} onChange={e => setNewForm(f => ({ ...f, contact_email: e.target.value }))} style={inp} /></div>
            <div><label style={lbl}>Teléfono</label><input value={newForm.contact_phone} onChange={e => setNewForm(f => ({ ...f, contact_phone: e.target.value }))} style={inp} /></div>
            <div><label style={lbl}>Estado</label>
              <select value={newForm.status} onChange={e => setNewForm(f => ({ ...f, status: e.target.value }))} style={inp}>
                {Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </div>
          </div>
          <div style={{ marginBottom: 16 }}><label style={lbl}>Notas</label><textarea value={newForm.notes} onChange={e => setNewForm(f => ({ ...f, notes: e.target.value }))} style={{ ...inp, minHeight: 70, resize: 'vertical' }} /></div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={() => setShowCreate(false)} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 16px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>Cancelar</button>
            <Button onClick={() => create(newForm)} disabled={!newForm.name || creating}>
              {creating ? '⟳ Creando...' : '✓ Crear cliente'}
            </Button>
          </div>
        </Modal>
      )}
      </div>
    </PageShell>
  )
}

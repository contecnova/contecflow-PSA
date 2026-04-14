/**
 * EntitySelect — Reusable select components for shared catalog entities.
 *
 * All modules use these components so that:
 *  - Client/User/Project lists come from the same API call and React Query cache
 *  - Changing a client's name in ClientsPage is immediately reflected everywhere
 *  - There is no free-text fallback for entities that must be referenced by ID
 *
 * Usage:
 *   <ClientSelect value={form.client_id} onChange={(id, client) => setForm(...)} />
 *   <UserSelect   value={form.user_id}   onChange={(id, user)   => setForm(...)} />
 *   <ProjectSelect value={form.project_id} onChange={(id, proj) => setForm(...)} />
 */
import { useQuery } from '@tanstack/react-query'
import {
  clientsApi, usersApi, projectsApi,
  sprintsApi, epicsApi, contractsApi,
  milestonesApi, tasksApi,
  assetsApi, licensesApi, vendorsApi,
  ticketsApi, problemsApi,
  subcontractorsApi,
} from '../../services/api'

const SELECT_STYLE = {
  width: '100%',
  background: 'var(--surface-3)',
  border: '1px solid #1e2d45',
  borderRadius: 8,
  padding: '8px 12px',
  color: 'var(--text-1)',
  fontSize: 13,
  outline: 'none',
  fontFamily: 'inherit',
  boxSizing: 'border-box',
}

// ── ClientSelect ──────────────────────────────────────────────────────────────
/**
 * @param {string}   value       - current client ID
 * @param {function} onChange(id, clientObj) - called when selection changes
 * @param {string}   placeholder - placeholder option text
 * @param {boolean}  required    - whether the field is required
 * @param {object}   style       - override styles
 */
export function ClientSelect({ value = '', onChange, placeholder = 'Seleccionar cliente…', required = false, style }) {
  const { data: clients = [], isLoading } = useQuery({
    queryKey: ['clients'],
    queryFn: () => clientsApi.list().then(r => r.data),
    staleTime: 2 * 60 * 1000,
  })

  const handleChange = (e) => {
    const id = e.target.value
    const client = clients.find(c => c.id === id) || null
    onChange(id, client)
  }

  return (
    <select
      value={value}
      onChange={handleChange}
      required={required}
      disabled={isLoading}
      style={{ ...SELECT_STYLE, ...style }}
    >
      <option value="">{isLoading ? 'Cargando…' : placeholder}</option>
      {clients.map(c => (
        <option key={c.id} value={c.id}>{c.name}</option>
      ))}
    </select>
  )
}

// ── UserSelect ────────────────────────────────────────────────────────────────
/**
 * @param {string}   value       - current user ID
 * @param {function} onChange(id, userObj) - called when selection changes
 * @param {string}   placeholder - placeholder option text
 * @param {string}   filterRole  - if set, filter by user role (pm, dev, admin, etc.)
 * @param {boolean}  required    - whether the field is required
 * @param {object}   style       - override styles
 */
export function UserSelect({ value = '', onChange, placeholder = 'Seleccionar usuario…', filterRole, required = false, style }) {
  const { data: rawUsers = [], isLoading } = useQuery({
    queryKey: ['users'],
    queryFn: () => usersApi.list().then(r => r.data),
    staleTime: 2 * 60 * 1000,
  })

  const users = filterRole
    ? rawUsers.filter(u => u.role === filterRole && u.is_active !== false)
    : rawUsers.filter(u => u.is_active !== false)

  const handleChange = (e) => {
    const id = e.target.value
    const user = users.find(u => u.id === id) || null
    onChange(id, user)
  }

  return (
    <select
      value={value}
      onChange={handleChange}
      required={required}
      disabled={isLoading}
      style={{ ...SELECT_STYLE, ...style }}
    >
      <option value="">{isLoading ? 'Cargando…' : placeholder}</option>
      {users.map(u => (
        <option key={u.id} value={u.id}>{u.full_name} ({u.role})</option>
      ))}
    </select>
  )
}

// ── ProjectSelect ─────────────────────────────────────────────────────────────
/**
 * @param {string}   value       - current project ID
 * @param {function} onChange(id, projectObj) - called when selection changes
 * @param {string}   placeholder - placeholder option text
 * @param {string}   filterStatus - if set, filter by project status (active, planning, etc.)
 * @param {boolean}  required    - whether the field is required
 * @param {object}   style       - override styles
 */
export function ProjectSelect({ value = '', onChange, placeholder = 'Seleccionar proyecto…', filterStatus, required = false, style }) {
  const { data: rawProjects = [], isLoading } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list().then(r => r.data),
    staleTime: 2 * 60 * 1000,
  })

  const projects = filterStatus
    ? rawProjects.filter(p => p.status === filterStatus)
    : rawProjects

  const handleChange = (e) => {
    const id = e.target.value
    const project = projects.find(p => p.id === id) || null
    onChange(id, project)
  }

  return (
    <select
      value={value}
      onChange={handleChange}
      required={required}
      disabled={isLoading}
      style={{ ...SELECT_STYLE, ...style }}
    >
      <option value="">{isLoading ? 'Cargando…' : placeholder}</option>
      {projects.map(p => (
        <option key={p.id} value={p.id}>{p.name}{p.code ? ` [${p.code}]` : ''}</option>
      ))}
    </select>
  )
}

// ── SprintSelect ──────────────────────────────────────────────────────────────
export function SprintSelect({ value = '', onChange, projectId, placeholder = 'Seleccionar sprint…', required = false, style }) {
  const { data: sprints = [], isLoading } = useQuery({
    queryKey: ['sprints', projectId],
    queryFn: () => sprintsApi.list(projectId).then(r => r.data),
    enabled: !!projectId,
    staleTime: 2 * 60 * 1000,
  })
  const handleChange = (e) => {
    const id = e.target.value
    onChange(id, sprints.find(s => s.id === id) || null)
  }
  return (
    <select value={value} onChange={handleChange} required={required} disabled={isLoading} style={{ ...SELECT_STYLE, ...style }}>
      <option value="">{isLoading ? 'Cargando…' : placeholder}</option>
      {sprints.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
    </select>
  )
}

// ── EpicSelect ────────────────────────────────────────────────────────────────
export function EpicSelect({ value = '', onChange, projectId, placeholder = 'Seleccionar épica…', required = false, style }) {
  const { data: epics = [], isLoading } = useQuery({
    queryKey: ['epics', projectId],
    queryFn: () => epicsApi.list(projectId).then(r => r.data),
    enabled: !!projectId,
    staleTime: 2 * 60 * 1000,
  })
  const handleChange = (e) => {
    const id = e.target.value
    onChange(id, epics.find(ep => ep.id === id) || null)
  }
  return (
    <select value={value} onChange={handleChange} required={required} disabled={isLoading} style={{ ...SELECT_STYLE, ...style }}>
      <option value="">{isLoading ? 'Cargando…' : placeholder}</option>
      {epics.map(ep => <option key={ep.id} value={ep.id}>{ep.name}</option>)}
    </select>
  )
}

// ── ContractSelect ────────────────────────────────────────────────────────────
export function ContractSelect({ value = '', onChange, placeholder = 'Seleccionar contrato…', required = false, style }) {
  const { data: contracts = [], isLoading } = useQuery({
    queryKey: ['contracts'],
    queryFn: () => contractsApi.list().then(r => r.data),
    staleTime: 2 * 60 * 1000,
  })
  const handleChange = (e) => {
    const id = e.target.value
    onChange(id, contracts.find(c => c.id === id) || null)
  }
  return (
    <select value={value} onChange={handleChange} required={required} disabled={isLoading} style={{ ...SELECT_STYLE, ...style }}>
      <option value="">{isLoading ? 'Cargando…' : placeholder}</option>
      {contracts.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
    </select>
  )
}

// ── MilestoneSelect ───────────────────────────────────────────────────────────
export function MilestoneSelect({ value = '', onChange, projectId, placeholder = 'Seleccionar hito…', required = false, style }) {
  const { data: milestones = [], isLoading } = useQuery({
    queryKey: ['milestones', projectId],
    queryFn: () => milestonesApi.list(projectId).then(r => r.data),
    enabled: !!projectId,
    staleTime: 2 * 60 * 1000,
  })
  const handleChange = (e) => {
    const id = e.target.value
    onChange(id, milestones.find(m => m.id === id) || null)
  }
  return (
    <select value={value} onChange={handleChange} required={required} disabled={isLoading} style={{ ...SELECT_STYLE, ...style }}>
      <option value="">{isLoading ? 'Cargando…' : placeholder}</option>
      {milestones.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
    </select>
  )
}

// ── TaskSelect ────────────────────────────────────────────────────────────────
export function TaskSelect({ value = '', onChange, projectId, placeholder = 'Seleccionar tarea…', required = false, style }) {
  const params = projectId ? { project_id: projectId } : {}
  const { data: tasks = [], isLoading } = useQuery({
    queryKey: ['tasks', params],
    queryFn: () => tasksApi.list(params).then(r => r.data),
    staleTime: 2 * 60 * 1000,
  })
  const handleChange = (e) => {
    const id = e.target.value
    onChange(id, tasks.find(t => t.id === id) || null)
  }
  return (
    <select value={value} onChange={handleChange} required={required} disabled={isLoading} style={{ ...SELECT_STYLE, ...style }}>
      <option value="">{isLoading ? 'Cargando…' : placeholder}</option>
      {tasks.map(t => <option key={t.id} value={t.id}>{t.title || t.name}</option>)}
    </select>
  )
}

// ── AssetSelect ───────────────────────────────────────────────────────────────
export function AssetSelect({ value = '', onChange, placeholder = 'Seleccionar asset…', required = false, style }) {
  const { data: assets = [], isLoading } = useQuery({
    queryKey: ['alm-assets'],
    queryFn: () => assetsApi.list().then(r => r.data),
    staleTime: 2 * 60 * 1000,
  })
  const handleChange = (e) => {
    const id = e.target.value
    onChange(id, assets.find(a => a.id === id) || null)
  }
  return (
    <select value={value} onChange={handleChange} required={required} disabled={isLoading} style={{ ...SELECT_STYLE, ...style }}>
      <option value="">{isLoading ? 'Cargando…' : placeholder}</option>
      {assets.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
    </select>
  )
}

// ── LicenseSelect ─────────────────────────────────────────────────────────────
export function LicenseSelect({ value = '', onChange, placeholder = 'Seleccionar licencia…', required = false, style }) {
  const { data: licenses = [], isLoading } = useQuery({
    queryKey: ['alm-licenses'],
    queryFn: () => licensesApi.list().then(r => r.data),
    staleTime: 2 * 60 * 1000,
  })
  const handleChange = (e) => {
    const id = e.target.value
    onChange(id, licenses.find(l => l.id === id) || null)
  }
  return (
    <select value={value} onChange={handleChange} required={required} disabled={isLoading} style={{ ...SELECT_STYLE, ...style }}>
      <option value="">{isLoading ? 'Cargando…' : placeholder}</option>
      {licenses.map(l => <option key={l.id} value={l.id}>{l.name} ({l.product || l.vendor_name || ''})</option>)}
    </select>
  )
}

// ── VendorSelect ──────────────────────────────────────────────────────────────
export function VendorSelect({ value = '', onChange, placeholder = 'Seleccionar proveedor…', required = false, style }) {
  const { data: vendors = [], isLoading } = useQuery({
    queryKey: ['alm-vendors'],
    queryFn: () => vendorsApi.list().then(r => r.data),
    staleTime: 2 * 60 * 1000,
  })
  const handleChange = (e) => {
    const id = e.target.value
    onChange(id, vendors.find(v => v.id === id) || null)
  }
  return (
    <select value={value} onChange={handleChange} required={required} disabled={isLoading} style={{ ...SELECT_STYLE, ...style }}>
      <option value="">{isLoading ? 'Cargando…' : placeholder}</option>
      {vendors.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}
    </select>
  )
}

// ── TicketSelect ──────────────────────────────────────────────────────────────
export function TicketSelect({ value = '', onChange, placeholder = 'Seleccionar incidencia…', required = false, style }) {
  const { data: tickets = [], isLoading } = useQuery({
    queryKey: ['sd-tickets', {}],
    queryFn: () => ticketsApi.list().then(r => r.data),
    staleTime: 60 * 1000,
  })
  const handleChange = (e) => {
    const id = e.target.value
    onChange(id, tickets.find(t => t.id === id) || null)
  }
  return (
    <select value={value} onChange={handleChange} required={required} disabled={isLoading} style={{ ...SELECT_STYLE, ...style }}>
      <option value="">{isLoading ? 'Cargando…' : placeholder}</option>
      {tickets.map(t => <option key={t.id} value={t.id}>{t.number ? `#${t.number} ` : ''}{t.title || t.subject}</option>)}
    </select>
  )
}

// ── ProblemSelect ─────────────────────────────────────────────────────────────
export function ProblemSelect({ value = '', onChange, placeholder = 'Seleccionar problema…', required = false, style }) {
  const { data: problems = [], isLoading } = useQuery({
    queryKey: ['sd-problems'],
    queryFn: () => problemsApi.list().then(r => r.data),
    staleTime: 2 * 60 * 1000,
  })
  const handleChange = (e) => {
    const id = e.target.value
    onChange(id, problems.find(p => p.id === id) || null)
  }
  return (
    <select value={value} onChange={handleChange} required={required} disabled={isLoading} style={{ ...SELECT_STYLE, ...style }}>
      <option value="">{isLoading ? 'Cargando…' : placeholder}</option>
      {problems.map(p => <option key={p.id} value={p.id}>{p.title}</option>)}
    </select>
  )
}

// ── SubcontractorSelect ───────────────────────────────────────────────────────
export function SubcontractorSelect({ value = '', onChange, placeholder = 'Seleccionar subcontratista…', required = false, style }) {
  const { data: subs = [], isLoading } = useQuery({
    queryKey: ['subcontractors'],
    queryFn: () => subcontractorsApi.list().then(r => r.data),
    staleTime: 2 * 60 * 1000,
  })
  const handleChange = (e) => {
    const id = e.target.value
    onChange(id, subs.find(s => s.id === id) || null)
  }
  return (
    <select value={value} onChange={handleChange} required={required} disabled={isLoading} style={{ ...SELECT_STYLE, ...style }}>
      <option value="">{isLoading ? 'Cargando…' : placeholder}</option>
      {subs.map(s => <option key={s.id} value={s.id}>{s.name || s.company_name}</option>)}
    </select>
  )
}

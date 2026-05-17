// @ts-nocheck
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
import type { CSSProperties } from 'react'
import { useQuery } from '@tanstack/react-query'
// TODO type: services/api still JS.
import {
  clientsApi, usersApi, projectsApi,
  sprintsApi, epicsApi, contractsApi,
  milestonesApi, tasksApi,
  assetsApi, licensesApi, vendorsApi,
  ticketsApi, problemsApi,
  subcontractorsApi,
} from '../../services/api'

const SELECT_STYLE: CSSProperties = {
  width: '100%',
  background: 'var(--surface-3)',
  border: '1px solid var(--surface-4)',
  borderRadius: 8,
  padding: '8px 12px',
  color: 'var(--text-1)',
  fontSize: 'var(--text-base)',
  outline: 'none',
  fontFamily: 'inherit',
  boxSizing: 'border-box',
}

// ── Shared entity shapes ─────────────────────────────────────────────────────
// TODO type: real domain models live in services/api (still JS). Until that
// migrates, mirror only the fields these selects actually read.
export interface BaseEntity {
  id: string
  name?: string
}

export interface ClientEntity extends BaseEntity {
  name: string
}

export interface UserEntity {
  id: string
  full_name?: string
  role?: string
  is_active?: boolean
}

export interface ProjectEntity extends BaseEntity {
  name: string
  code?: string
  status?: string
}

export interface NamedEntity extends BaseEntity {
  name: string
}

export interface SprintEntity extends NamedEntity {}
export interface EpicEntity extends NamedEntity {}
export interface ContractEntity extends NamedEntity {}
export interface MilestoneEntity extends NamedEntity {}

export interface TaskEntity {
  id: string
  title?: string
  name?: string
}

export interface AssetEntity extends NamedEntity {}

export interface LicenseEntity extends NamedEntity {
  product?: string
  vendor_name?: string
}

export interface VendorEntity extends NamedEntity {}

export interface TicketEntity {
  id: string
  number?: string | number
  title?: string
  subject?: string
}

export interface ProblemEntity {
  id: string
  title: string
}

export interface SubcontractorEntity {
  id: string
  name?: string
  company_name?: string
}

// ── ClientSelect ──────────────────────────────────────────────────────────────
export interface ClientSelectProps {
  value?: string
  onChange: (id: string, client: ClientEntity | null) => void
  placeholder?: string
  required?: boolean
  style?: CSSProperties
}

export function ClientSelect({ value = '', onChange, placeholder = 'Seleccionar cliente…', required = false, style }: ClientSelectProps) {
  const { data: clients = [], isLoading } = useQuery<ClientEntity[]>({
    queryKey: ['clients'],
    queryFn: () => clientsApi.list().then((r: { data: { items?: ClientEntity[] } | ClientEntity[] }) => {
      const d = r.data
      if (Array.isArray(d)) return d
      return d?.items ?? []
    }),
    staleTime: 2 * 60 * 1000,
  })

  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const id = e.target.value
    const client = clients.find((c) => c.id === id) || null
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
      {clients.map((c) => (
        <option key={c.id} value={c.id}>{c.name}</option>
      ))}
    </select>
  )
}

// ── UserSelect ────────────────────────────────────────────────────────────────
export interface UserSelectProps {
  value?: string
  onChange: (id: string, user: UserEntity | null) => void
  placeholder?: string
  filterRole?: string
  required?: boolean
  style?: CSSProperties
  filterFn?: (user: UserEntity) => boolean
}

export function UserSelect({ value = '', onChange, placeholder = 'Seleccionar usuario…', filterRole, required = false, style, filterFn }: UserSelectProps) {
  const { data: rawUsers = [], isLoading } = useQuery<UserEntity[]>({
    queryKey: ['users'],
    queryFn: () => usersApi.list().then((r: { data: UserEntity[] }) => r.data),
    staleTime: 2 * 60 * 1000,
  })

  let users = filterRole
    ? rawUsers.filter((u) => u.role === filterRole && u.is_active !== false)
    : rawUsers.filter((u) => u.is_active !== false)
  if (filterFn) users = users.filter(filterFn)

  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const id = e.target.value
    const user = users.find((u) => u.id === id) || null
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
      {users.map((u) => (
        <option key={u.id} value={u.id}>{u.full_name} ({u.role})</option>
      ))}
    </select>
  )
}

// ── ProjectSelect ─────────────────────────────────────────────────────────────
export interface ProjectSelectProps {
  value?: string
  onChange: (id: string, project: ProjectEntity | null) => void
  placeholder?: string
  filterStatus?: string
  required?: boolean
  style?: CSSProperties
}

export function ProjectSelect({ value = '', onChange, placeholder = 'Seleccionar proyecto…', filterStatus, required = false, style }: ProjectSelectProps) {
  const { data: rawProjects = [], isLoading } = useQuery<ProjectEntity[]>({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list().then((r: { data: { items?: ProjectEntity[] } | ProjectEntity[] }) => {
      const d = r.data
      if (Array.isArray(d)) return d
      return d?.items ?? []
    }),
    staleTime: 2 * 60 * 1000,
  })

  const projects = filterStatus
    ? rawProjects.filter((p) => p.status === filterStatus)
    : rawProjects

  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const id = e.target.value
    const project = projects.find((p) => p.id === id) || null
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
      {projects.map((p) => (
        <option key={p.id} value={p.id}>{p.name}{p.code ? ` [${p.code}]` : ''}</option>
      ))}
    </select>
  )
}

// ── SprintSelect ──────────────────────────────────────────────────────────────
export interface SprintSelectProps {
  value?: string
  onChange: (id: string, sprint: SprintEntity | null) => void
  projectId?: string
  placeholder?: string
  required?: boolean
  style?: CSSProperties
}

export function SprintSelect({ value = '', onChange, projectId, placeholder = 'Seleccionar sprint…', required = false, style }: SprintSelectProps) {
  const { data: sprints = [], isLoading } = useQuery<SprintEntity[]>({
    queryKey: ['sprints', projectId],
    queryFn: () => sprintsApi.list(projectId).then((r: { data: { items?: SprintEntity[] } | SprintEntity[] }) => {
      const d = r.data
      if (Array.isArray(d)) return d
      return d?.items ?? []
    }),
    enabled: !!projectId,
    staleTime: 2 * 60 * 1000,
  })
  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const id = e.target.value
    onChange(id, sprints.find((s) => s.id === id) || null)
  }
  return (
    <select value={value} onChange={handleChange} required={required} disabled={isLoading} style={{ ...SELECT_STYLE, ...style }}>
      <option value="">{isLoading ? 'Cargando…' : placeholder}</option>
      {sprints.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
    </select>
  )
}

// ── EpicSelect ────────────────────────────────────────────────────────────────
export interface EpicSelectProps {
  value?: string
  onChange: (id: string, epic: EpicEntity | null) => void
  projectId?: string
  placeholder?: string
  required?: boolean
  style?: CSSProperties
}

export function EpicSelect({ value = '', onChange, projectId, placeholder = 'Seleccionar épica…', required = false, style }: EpicSelectProps) {
  const { data: epics = [], isLoading } = useQuery<EpicEntity[]>({
    queryKey: ['epics', projectId],
    queryFn: () => epicsApi.list(projectId).then((r: { data: EpicEntity[] }) => r.data),
    enabled: !!projectId,
    staleTime: 2 * 60 * 1000,
  })
  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const id = e.target.value
    onChange(id, epics.find((ep) => ep.id === id) || null)
  }
  return (
    <select value={value} onChange={handleChange} required={required} disabled={isLoading} style={{ ...SELECT_STYLE, ...style }}>
      <option value="">{isLoading ? 'Cargando…' : placeholder}</option>
      {epics.map((ep) => <option key={ep.id} value={ep.id}>{ep.name}</option>)}
    </select>
  )
}

// ── ContractSelect ────────────────────────────────────────────────────────────
export interface ContractSelectProps {
  value?: string
  onChange: (id: string, contract: ContractEntity | null) => void
  placeholder?: string
  required?: boolean
  style?: CSSProperties
}

export function ContractSelect({ value = '', onChange, placeholder = 'Seleccionar contrato…', required = false, style }: ContractSelectProps) {
  const { data: contracts = [], isLoading } = useQuery<ContractEntity[]>({
    queryKey: ['contracts'],
    queryFn: () => contractsApi.list().then((r: { data: { items?: ContractEntity[] } | ContractEntity[] }) => {
      const d = r.data
      if (Array.isArray(d)) return d
      return d?.items ?? []
    }),
    staleTime: 2 * 60 * 1000,
  })
  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const id = e.target.value
    onChange(id, contracts.find((c) => c.id === id) || null)
  }
  return (
    <select value={value} onChange={handleChange} required={required} disabled={isLoading} style={{ ...SELECT_STYLE, ...style }}>
      <option value="">{isLoading ? 'Cargando…' : placeholder}</option>
      {contracts.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
    </select>
  )
}

// ── MilestoneSelect ───────────────────────────────────────────────────────────
export interface MilestoneSelectProps {
  value?: string
  onChange: (id: string, milestone: MilestoneEntity | null) => void
  projectId?: string
  placeholder?: string
  required?: boolean
  style?: CSSProperties
}

export function MilestoneSelect({ value = '', onChange, projectId, placeholder = 'Seleccionar hito…', required = false, style }: MilestoneSelectProps) {
  const { data: milestones = [], isLoading } = useQuery<MilestoneEntity[]>({
    queryKey: ['milestones', projectId],
    queryFn: () => milestonesApi.list(projectId).then((r: { data: { items?: MilestoneEntity[] } | MilestoneEntity[] }) => {
      const d = r.data
      if (Array.isArray(d)) return d
      return d?.items ?? []
    }),
    enabled: !!projectId,
    staleTime: 2 * 60 * 1000,
  })
  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const id = e.target.value
    onChange(id, milestones.find((m) => m.id === id) || null)
  }
  return (
    <select value={value} onChange={handleChange} required={required} disabled={isLoading} style={{ ...SELECT_STYLE, ...style }}>
      <option value="">{isLoading ? 'Cargando…' : placeholder}</option>
      {milestones.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
    </select>
  )
}

// ── TaskSelect ────────────────────────────────────────────────────────────────
export interface TaskSelectProps {
  value?: string
  onChange: (id: string, task: TaskEntity | null) => void
  projectId?: string
  placeholder?: string
  required?: boolean
  style?: CSSProperties
}

export function TaskSelect({ value = '', onChange, projectId, placeholder = 'Seleccionar tarea…', required = false, style }: TaskSelectProps) {
  const params: Record<string, string> = projectId ? { project_id: projectId } : {}
  const { data: tasks = [], isLoading } = useQuery<TaskEntity[]>({
    queryKey: ['tasks', params],
    queryFn: () => tasksApi.list(params).then((r: { data: { items?: TaskEntity[] } | TaskEntity[] }) => {
      const d = r.data
      if (Array.isArray(d)) return d
      return d?.items ?? []
    }),
    staleTime: 2 * 60 * 1000,
  })
  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const id = e.target.value
    onChange(id, tasks.find((t) => t.id === id) || null)
  }
  return (
    <select value={value} onChange={handleChange} required={required} disabled={isLoading} style={{ ...SELECT_STYLE, ...style }}>
      <option value="">{isLoading ? 'Cargando…' : placeholder}</option>
      {tasks.map((t) => <option key={t.id} value={t.id}>{t.title || t.name}</option>)}
    </select>
  )
}

// ── AssetSelect ───────────────────────────────────────────────────────────────
export interface AssetSelectProps {
  value?: string
  onChange: (id: string, asset: AssetEntity | null) => void
  placeholder?: string
  required?: boolean
  style?: CSSProperties
}

export function AssetSelect({ value = '', onChange, placeholder = 'Seleccionar asset…', required = false, style }: AssetSelectProps) {
  const { data: assets = [], isLoading } = useQuery<AssetEntity[]>({
    queryKey: ['alm-assets'],
    queryFn: () => assetsApi.list().then((r: { data: AssetEntity[] }) => r.data),
    staleTime: 2 * 60 * 1000,
  })
  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const id = e.target.value
    onChange(id, assets.find((a) => a.id === id) || null)
  }
  return (
    <select value={value} onChange={handleChange} required={required} disabled={isLoading} style={{ ...SELECT_STYLE, ...style }}>
      <option value="">{isLoading ? 'Cargando…' : placeholder}</option>
      {assets.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
    </select>
  )
}

// ── LicenseSelect ─────────────────────────────────────────────────────────────
export interface LicenseSelectProps {
  value?: string
  onChange: (id: string, license: LicenseEntity | null) => void
  placeholder?: string
  required?: boolean
  style?: CSSProperties
}

export function LicenseSelect({ value = '', onChange, placeholder = 'Seleccionar licencia…', required = false, style }: LicenseSelectProps) {
  const { data: licenses = [], isLoading } = useQuery<LicenseEntity[]>({
    queryKey: ['alm-licenses'],
    queryFn: () => licensesApi.list().then((r: { data: LicenseEntity[] }) => r.data),
    staleTime: 2 * 60 * 1000,
  })
  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const id = e.target.value
    onChange(id, licenses.find((l) => l.id === id) || null)
  }
  return (
    <select value={value} onChange={handleChange} required={required} disabled={isLoading} style={{ ...SELECT_STYLE, ...style }}>
      <option value="">{isLoading ? 'Cargando…' : placeholder}</option>
      {licenses.map((l) => <option key={l.id} value={l.id}>{l.name} ({l.product || l.vendor_name || ''})</option>)}
    </select>
  )
}

// ── VendorSelect ──────────────────────────────────────────────────────────────
export interface VendorSelectProps {
  value?: string
  onChange: (id: string, vendor: VendorEntity | null) => void
  placeholder?: string
  required?: boolean
  style?: CSSProperties
}

export function VendorSelect({ value = '', onChange, placeholder = 'Seleccionar proveedor…', required = false, style }: VendorSelectProps) {
  const { data: vendors = [], isLoading } = useQuery<VendorEntity[]>({
    queryKey: ['alm-vendors'],
    queryFn: () => vendorsApi.list().then((r: { data: VendorEntity[] }) => r.data),
    staleTime: 2 * 60 * 1000,
  })
  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const id = e.target.value
    onChange(id, vendors.find((v) => v.id === id) || null)
  }
  return (
    <select value={value} onChange={handleChange} required={required} disabled={isLoading} style={{ ...SELECT_STYLE, ...style }}>
      <option value="">{isLoading ? 'Cargando…' : placeholder}</option>
      {vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
    </select>
  )
}

// ── TicketSelect ──────────────────────────────────────────────────────────────
export interface TicketSelectProps {
  value?: string
  onChange: (id: string, ticket: TicketEntity | null) => void
  placeholder?: string
  required?: boolean
  style?: CSSProperties
}

export function TicketSelect({ value = '', onChange, placeholder = 'Seleccionar incidencia…', required = false, style }: TicketSelectProps) {
  const { data: tickets = [], isLoading } = useQuery<TicketEntity[]>({
    queryKey: ['sd-tickets', {}],
    queryFn: () => ticketsApi.list().then((r: { data: TicketEntity[] }) => r.data),
    staleTime: 60 * 1000,
  })
  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const id = e.target.value
    onChange(id, tickets.find((t) => t.id === id) || null)
  }
  return (
    <select value={value} onChange={handleChange} required={required} disabled={isLoading} style={{ ...SELECT_STYLE, ...style }}>
      <option value="">{isLoading ? 'Cargando…' : placeholder}</option>
      {tickets.map((t) => <option key={t.id} value={t.id}>{t.number ? `#${t.number} ` : ''}{t.title || t.subject}</option>)}
    </select>
  )
}

// ── ProblemSelect ─────────────────────────────────────────────────────────────
export interface ProblemSelectProps {
  value?: string
  onChange: (id: string, problem: ProblemEntity | null) => void
  placeholder?: string
  required?: boolean
  style?: CSSProperties
}

export function ProblemSelect({ value = '', onChange, placeholder = 'Seleccionar problema…', required = false, style }: ProblemSelectProps) {
  const { data: problems = [], isLoading } = useQuery<ProblemEntity[]>({
    queryKey: ['sd-problems'],
    queryFn: () => problemsApi.list().then((r: { data: ProblemEntity[] }) => r.data),
    staleTime: 2 * 60 * 1000,
  })
  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const id = e.target.value
    onChange(id, problems.find((p) => p.id === id) || null)
  }
  return (
    <select value={value} onChange={handleChange} required={required} disabled={isLoading} style={{ ...SELECT_STYLE, ...style }}>
      <option value="">{isLoading ? 'Cargando…' : placeholder}</option>
      {problems.map((p) => <option key={p.id} value={p.id}>{p.title}</option>)}
    </select>
  )
}

// ── SubcontractorSelect ───────────────────────────────────────────────────────
export interface SubcontractorSelectProps {
  value?: string
  onChange: (id: string, subcontractor: SubcontractorEntity | null) => void
  placeholder?: string
  required?: boolean
  style?: CSSProperties
}

export function SubcontractorSelect({ value = '', onChange, placeholder = 'Seleccionar subcontratista…', required = false, style }: SubcontractorSelectProps) {
  const { data: subs = [], isLoading } = useQuery<SubcontractorEntity[]>({
    queryKey: ['subcontractors'],
    queryFn: () => subcontractorsApi.list().then((r: { data: SubcontractorEntity[] }) => r.data),
    staleTime: 2 * 60 * 1000,
  })
  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const id = e.target.value
    onChange(id, subs.find((s) => s.id === id) || null)
  }
  return (
    <select value={value} onChange={handleChange} required={required} disabled={isLoading} style={{ ...SELECT_STYLE, ...style }}>
      <option value="">{isLoading ? 'Cargando…' : placeholder}</option>
      {subs.map((s) => <option key={s.id} value={s.id}>{s.name || s.company_name}</option>)}
    </select>
  )
}

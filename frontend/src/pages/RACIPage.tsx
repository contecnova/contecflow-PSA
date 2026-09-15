/**
 * RACIPage — Matriz de responsabilidades por proyecto (R/A/C/I)
 * Permite definir quién es Responsable, Aprobador, Consultado e Informado
 * para cada entregable, milestone o fase del proyecto.
 */
import { useState } from 'react'
import type { ChangeEvent, CSSProperties } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api, { projectsApi } from '../services/api'
import { Avatar, Spinner, EmptyState, Button, Modal } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Shield } from 'lucide-react'
import { useToast } from '../context/ToastContext'
import { extractErr } from '../utils/helpers'
import { useAppT } from '../i18n/AppLangContext'
import { openConfirmGlobal } from '../context/ConfirmContext'

type IdType = string | number

interface ProjectItem {
  id: IdType
  code?: string
  name?: string
}

interface UserSlim {
  id: IdType
  full_name: string
  department?: string
  role?: string
}

interface RaciAssignment {
  user_id: IdType
  user?: UserSlim
  role?: string
  entry_id: IdType
}

interface RaciItem {
  item_type: string
  item_label: string
  assignments: RaciAssignment[]
}

interface RaciResponse {
  items?: RaciItem[]
}

const ROLES_META = {
  R: { label: 'Responsible',  short: 'R', color: 'var(--accent)',   bg: 'rgba(79,142,247,0.15)',  desc: 'Ejecuta el trabajo' },
  A: { label: 'Accountable',  short: 'A', color: 'var(--success)',  bg: 'rgba(74,222,128,0.15)',  desc: 'Aprueba y responde' },
  C: { label: 'Consulted',    short: 'C', color: 'var(--warning)',  bg: 'rgba(251,191,36,0.15)',  desc: 'Aporta información' },
  I: { label: 'Informed',     short: 'I', color: 'var(--text-2)',   bg: 'rgba(122,138,170,0.15)', desc: 'Se le comunica' },
}

const ITEM_TYPES = [
  { value: 'deliverable', label: 'Entregable' },
  { value: 'milestone',   label: 'Milestone' },
  { value: 'phase',       label: 'Fase' },
  { value: 'custom',      label: 'Personalizado' },
]

function RoleCell({ role, onClick, editable }: { role?: string; onClick?: () => void; editable: boolean }) {
  const meta = (role && ROLES_META[role]) || null
  const sharedStyle: CSSProperties = {
    width: 32, height: 32, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontWeight: 800, fontSize: "var(--text-base)", cursor: editable ? 'pointer' : 'default',
    background: meta ? meta.bg : 'var(--surface-3)',
    color: meta ? meta.color : 'var(--text-4)',
    border: `1px solid ${meta ? meta.color + '40' : 'var(--surface-4)'}`,
    transition: 'all .1s',
    userSelect: 'none',
  }

  if (editable) {
    return (
      <button
        type="button"
        onClick={onClick}
        title={meta ? `${meta.label} — ${meta.desc}` : 'Sin asignar'}
        style={{ ...sharedStyle, fontFamily: 'inherit' }}
      >
        {meta ? meta.short : '—'}
      </button>
    )
  }

  return (
    <div
      title={meta ? `${meta.label} — ${meta.desc}` : 'Sin asignar'}
      style={sharedStyle}
    >
      {meta ? meta.short : '·'}
    </div>
  )
}

function AddEntryModal({ projectId, users, onClose, onSaved }: { projectId: IdType; users: UserSlim[]; onClose: () => void; onSaved: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const [form, setForm] = useState({ item_type: 'deliverable', item_label: '', user_id: '', role: 'R' })

  const { mutate: save, isPending } = useMutation({
    mutationFn: () => api.put(`/projects/${projectId}/raci`, {
      entries: [{ item_type: form.item_type, item_label: form.item_label, user_id: form.user_id, role: form.role }]
    }),
    onSuccess: () => { onSaved(); onClose() },
    onError: (e: unknown) => toast.error(extractErr(e, 'Error al guardar')),
  })

  const inputStyle: CSSProperties = {
    width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
    borderRadius: 8, padding: '9px 12px', color: 'var(--text-1)', fontSize: "var(--text-base)",
    outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box',
  }
  const lbStyle: CSSProperties = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', display: 'block', marginBottom: 5 }
  const onField = (key: 'item_type' | 'item_label' | 'user_id' | 'role') => (e: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    setForm((f) => ({ ...f, [key]: e.target.value }))
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 12 }}>
        <div>
          <label style={lbStyle}>Tipo</label>
          <select value={form.item_type} onChange={onField('item_type')} style={inputStyle}>
            {ITEM_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
        </div>
        <div>
          <label style={lbStyle}>Nombre del elemento</label>
          <input value={form.item_label} onChange={onField('item_label')} style={inputStyle} placeholder="Nombre del elemento" aria-label="Nombre del elemento" />
        </div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 12 }}>
        <div>
          <label style={lbStyle}>Persona</label>
          <select value={form.user_id} onChange={onField('user_id')} style={inputStyle}>
            <option value="">Selecciona persona...</option>
            {users.map(u => <option key={u.id} value={u.id}>{u.full_name} ({u.department || u.role})</option>)}
          </select>
        </div>
        <div>
          <label style={lbStyle}>Rol RACI</label>
          <select value={form.role} onChange={onField('role')} style={inputStyle}>
            {Object.entries(ROLES_META).map(([k, v]) => <option key={k} value={k}>{k} — {v.label}</option>)}
          </select>
        </div>
      </div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
        <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
        <Button onClick={() => save()} disabled={isPending || !form.item_label || !form.user_id}>
          {isPending ? t('common.saving') : 'Añadir entrada'}
        </Button>
      </div>
    </div>
  )
}

export default function RACIPage() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [selectedProject, setSelectedProject] = useState<IdType | ''>('')
  const [showAdd, setShowAdd] = useState(false)

  const { data: projRaw = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list({}).then(r => r.data ?? []),
  })
  const projects = (Array.isArray(projRaw) ? projRaw : []) as ProjectItem[]

  const { data: raciRaw, isLoading } = useQuery({
    queryKey: ['raci', selectedProject],
    queryFn: () => api.get(`/projects/${selectedProject}/raci`).then(r => r.data),
    enabled: !!selectedProject,
  })
  const raci = (raciRaw ?? null) as RaciResponse | null

  const { data: usersRaw = [] } = useQuery({
    queryKey: ['users-slim'],
    queryFn: () => api.get('/users').then(r => Array.isArray(r.data) ? r.data : r.data?.items || []),
    enabled: true,
    staleTime: 60000,
  })
  const usersData = usersRaw as UserSlim[]

  const { mutate: deleteEntry } = useMutation({
    mutationFn: (entryId: IdType) => api.delete(`/projects/${selectedProject}/raci/${entryId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['raci', selectedProject] }),
    onError: (e: unknown) => toast.error(extractErr(e, 'Error al eliminar')),
  })

  // Build matrix: rows = items, columns = unique users
  const items = (raci?.items || []) as RaciItem[]
  const allAssignments = items.flatMap((it) => it.assignments || [])
  const uniqueUsers = [...new Map(allAssignments.map((a) => [a.user_id, a.user])).values()].filter(Boolean) as UserSlim[]

  return (
    <PageShell>
      <PageHeader title={t('raci.title')} subtitle={t('raci.subtitle')} icon={<Shield size={18} />} />

      {/* Legend */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 24, flexWrap: 'wrap' }}>
        {Object.entries(ROLES_META).map(([k, v]) => (
          <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '5px 12px',
            background: v.bg, border: `1px solid ${v.color}40`, borderRadius: 20 }}>
            <span style={{ fontWeight: 800, fontSize: "var(--text-base)", color: v.color }}>{k}</span>
            <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{v.label}</span>
            <span style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)' }}>— {v.desc}</span>
          </div>
        ))}
      </div>

      {/* Project selector + action */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 24, alignItems: 'center' }}>
        <select value={String(selectedProject)} onChange={e => setSelectedProject(e.target.value)}
          style={{ flex: 1, maxWidth: 380, background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', cursor: 'pointer' }}>
          <option value="">Selecciona un proyecto...</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
        </select>
        {selectedProject && (
          <Button onClick={() => setShowAdd(true)}>+ Añadir entrada</Button>
        )}
      </div>

      {!selectedProject ? (
        <EmptyState icon="📋" title="Selecciona un proyecto" description="Elige un proyecto para ver y gestionar su matriz RACI" />
      ) : isLoading ? (
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '40px 0' }}><Spinner /><span style={{ color: 'var(--text-2)' }}>{t('common.loading')}</span></div>
      ) : items.length === 0 ? (
        <EmptyState icon="📊" title="Matriz RACI vacia" description="Anade la primera entrada para empezar a asignar responsabilidades" action={<button className="btn-primary" onClick={() => setShowAdd(true)} style={{ fontSize: "var(--text-base)", padding: '8px 20px' }}>+ Añadir primera entrada</button>} />
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'separate', borderSpacing: 0, minWidth: 600 }}>
            <thead>
              <tr>
                <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', borderBottom: '1px solid var(--surface-4)', background: 'var(--surface-2)', borderRadius: '8px 0 0 0', whiteSpace: 'nowrap', minWidth: 180 }}>Elemento</th>
                <th style={{ padding: '10px 12px', textAlign: 'center', fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', borderBottom: '1px solid var(--surface-4)', background: 'var(--surface-2)', minWidth: 80 }}>Tipo</th>
                {uniqueUsers.map(u => (
                  <th key={u.id} style={{ padding: '10px 8px', textAlign: 'center', fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', borderBottom: '1px solid var(--surface-4)', background: 'var(--surface-2)', minWidth: 70 }}>
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3 }}>
                      <Avatar name={u.full_name} size={22} url={undefined} />
                      <span style={{ fontSize: "var(--text-2xs)", whiteSpace: 'nowrap', maxWidth: 70, overflow: 'hidden', textOverflow: 'ellipsis' }}>{u.full_name.split(' ')[0]}</span>
                    </div>
                  </th>
                ))}
                <th style={{ width: 40, borderBottom: '1px solid var(--surface-4)', background: 'var(--surface-2)' }} />
              </tr>
            </thead>
            <tbody>
              {items.map((item, idx) => {
                const assignMap = Object.fromEntries(item.assignments.map((a) => [a.user_id, a])) as Record<string, RaciAssignment>
                return (
                  <tr key={idx} style={{ background: idx % 2 === 0 ? 'var(--surface-1)' : 'var(--surface-2)' }}
                    onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-3)'}
                    onMouseLeave={e => e.currentTarget.style.background = idx % 2 === 0 ? 'var(--surface-1)' : 'var(--surface-2)'}
                  >
                    <td style={{ padding: '10px 16px', fontSize: "var(--text-base)", fontWeight: 600, color: 'var(--text-1)', borderBottom: '1px solid var(--surface-4)' }}>{item.item_label}</td>
                    <td style={{ padding: '10px 12px', textAlign: 'center', borderBottom: '1px solid var(--surface-4)' }}>
                      <span style={{ fontSize: "var(--text-2xs)", padding: '2px 7px', borderRadius: 10, background: 'var(--surface-3)', color: 'var(--text-3)', textTransform: 'uppercase' }}>
                        {ITEM_TYPES.find(t => t.value === item.item_type)?.label || item.item_type}
                      </span>
                    </td>
                    {uniqueUsers.map(u => {
                      const a = assignMap[String(u.id)]
                      return (
                        <td key={u.id} style={{ padding: '8px', textAlign: 'center', borderBottom: '1px solid var(--surface-4)' }}>
                          {a ? (
                            <div style={{ display: 'flex', justifyContent: 'center' }}>
                              <div style={{ position: 'relative' }}>
                                <RoleCell role={a.role} editable={false} />
                                <button onClick={() => { openConfirmGlobal({ message: '¿Quitar esta asignación RACI? Esta acción no se puede deshacer.', onConfirm: () => deleteEntry(a.entry_id), danger: true }) }}
                                  title="Quitar asignacion"
                                  style={{ position: 'absolute', top: -6, right: -6, width: 14, height: 14, borderRadius: '50%', background: 'var(--danger)', border: 'none', color: '#fff', cursor: 'pointer', fontSize: "var(--text-3xs)", display: 'flex', alignItems: 'center', justifyContent: 'center', lineHeight: 1 }}>
                                  ×
                                </button>
                              </div>
                            </div>
                          ) : (
                            <div style={{ width: 32, height: 32, margin: '0 auto' }} />
                          )}
                        </td>
                      )
                    })}
                    <td style={{ padding: '8px', borderBottom: '1px solid var(--surface-4)' }} />
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {showAdd && (
        <Modal open title="Anadir entrada RACI" onClose={() => setShowAdd(false)} width={560}>
          <AddEntryModal
            projectId={selectedProject}
            users={usersData}
            onClose={() => setShowAdd(false)}
            onSaved={() => qc.invalidateQueries({ queryKey: ['raci', selectedProject] })}
          />
        </Modal>
      )}
    </PageShell>
  )
}

/**
 * OrgChartPage — Organigrama, posiciones y cadenas de aprobación
 * 
 * Pestaña 1 — Árbol: visualización jerárquica con edición inline
 * Pestaña 2 — Posiciones: tabla editable de todos los usuarios
 * Pestaña 3 — Aprobaciones: quién aprueba gastos, ausencias e imputaciones
 */
import { useState, useMemo } from 'react'
import type { CSSProperties } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useToast } from '../context/ToastContext'
import { useAuth } from '../context/AuthContext'
import { usersApi } from '../services/api'
import { settingsApi } from '../services/settingsApi'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Network } from 'lucide-react'
import { Button, Spinner, EmptyState, Modal } from '../components/ui'
import { extractErr } from '../utils/helpers'
import { useAppT } from '../i18n/AppLangContext'

// ── Colores por rol ───────────────────────────────────────────────────────────
const ROLE_COLOR = {
  admin: '#4f8ef7', pm: '#a78bfa', team_lead: '#0891b2',
  employee: '#34d399', hr: '#f59e0b', client: '#7a8aaa',
}
const ROLE_LABEL = {
  admin: 'Admin', pm: 'PM', team_lead: 'Team Lead',
  employee: 'Empleado', hr: 'RRHH', client: 'Cliente',
}

interface DepartmentOption {
  id: string | number
  name: string
  is_active?: boolean
}

interface OrgUser {
  id: string
  full_name: string
  email: string
  role: string
  job_title?: string | null
  department?: string | null
  manager_id?: string | null
  children?: OrgUser[]
}

interface OrgChartData {
  nodes: OrgUser[]
  total: number
}

interface ApprovalChainData {
  user_name: string
  chain: OrgUser[]
}

function getRoleColor(role: string) {
  return ROLE_COLOR[role as keyof typeof ROLE_COLOR] ?? '#7a8aaa'
}

function getRoleLabel(role: string) {
  return ROLE_LABEL[role as keyof typeof ROLE_LABEL] ?? role
}

// ── Modal editar posición ─────────────────────────────────────────────────────
function EditPositionModal({ user, allUsers, onClose, onSaved }: {
  user: OrgUser
  allUsers: OrgUser[]
  onClose: () => void
  onSaved: () => void
}) {
  const toast = useToast()
  const [managerId, setManagerId]   = useState(user.manager_id || '')
  const [jobTitle, setJobTitle]     = useState(user.job_title || '')
  const [department, setDepartment] = useState(user.department || '')
  const [saving, setSaving]         = useState(false)

  const { data: departments = [] } = useQuery<DepartmentOption[]>({
    queryKey: ['departments-select'],
    queryFn: () => settingsApi.getDepartments().then(r => r.data),
  })

  const IS: CSSProperties = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)',
    borderRadius:8, padding:'9px 12px', color:'var(--text-1)', fontSize: "var(--text-base)",
    outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
  const LS: CSSProperties = { fontSize: "var(--text-xs)", fontWeight:600, color:'var(--text-2)', display:'block',
    marginBottom:5, textTransform:'uppercase', letterSpacing:'0.06em' }

  const eligible = allUsers.filter(u => u.id !== user.id)

  const handleSave = async () => {
    setSaving(true)
    try {
      await usersApi.update(user.id, {
        job_title: jobTitle || undefined,
        department: department || undefined,
      } as Parameters<typeof usersApi.update>[1])
      await usersApi.updateManager(user.id, { manager_id: managerId || null })
      toast.success('Posición actualizada')
      onSaved()
    } catch (e) {
      toast.error(extractErr(e, 'Error al actualizar'))
    } finally { setSaving(false) }
  }

  return (
    <Modal open title={`Editar posición — ${user.full_name}`} onClose={onClose}>
      <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
        <div style={{ padding:'10px 14px', background:'var(--surface-2)', borderRadius:8,
          border:'1px solid var(--surface-4)' }}>
          <div style={{ fontSize: "var(--text-md)", fontWeight:600 }}>{user.full_name}</div>
          <div style={{ fontSize: "var(--text-sm)", color:'var(--text-3)', marginTop:2 }}>
            {user.email} · <span style={{ color: getRoleColor(user.role) }}>{getRoleLabel(user.role)}</span>
          </div>
        </div>

        <div>
          <label style={LS}>Cargo / Puesto</label>
          <input value={jobTitle} onChange={e => setJobTitle(e.target.value)} style={IS}
            placeholder="Ej: Desarrollador Senior" />
        </div>
        <div>
          <label style={LS}>Departamento</label>
          <select value={department} onChange={e => setDepartment(e.target.value)} style={IS}>
            <option value="">— Sin departamento —</option>
            {departments.filter(d => d.is_active !== false).map(d => <option key={d.id} value={d.name}>{d.name}</option>)}
          </select>
        </div>
        <div>
          <label style={LS}>Reporta a / Aprobador directo</label>
          <div style={{ fontSize: "var(--text-xs)", color:'var(--text-3)', marginBottom:6, lineHeight:1.6 }}>
            Esta persona aprobará los <strong>gastos</strong>, <strong>ausencias</strong> e <strong>imputaciones</strong> de {user.full_name.split(' ')[0]}.
          </div>
          <select value={managerId} onChange={e => setManagerId(e.target.value)} style={IS}>
            <option value="">Sin manager (nivel raíz — aprobación manual)</option>
            {eligible.map(u => (
              <option key={u.id} value={u.id}>
                {u.full_name}
                {u.job_title ? ` — ${u.job_title}` : ''}
                {u.department ? ` (${u.department})` : ''}
              </option>
            ))}
          </select>
        </div>

        <div style={{ padding:'10px 14px', background:'var(--accent-muted)',
          border:'1px solid var(--accent-glow)', borderRadius:8, fontSize: "var(--text-sm)",
          color:'var(--text-2)', lineHeight:1.7 }}>
          💡 <strong>Cómo funciona la aprobación:</strong> cuando {user.full_name.split(' ')[0]} envíe
          un gasto, solicite una ausencia o entregue su timesheet,
          {managerId
            ? ` ${eligible.find(u=>u.id===managerId)?.full_name || 'su manager'} recibirá la notificación para aprobar o rechazar.`
            : ' quedará pendiente de asignación de aprobador.'}
        </div>

        <div style={{ display:'flex', justifyContent:'flex-end', gap:10 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={handleSave} disabled={saving} loading={saving}>Guardar posición</Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Pestaña 1: Árbol jerárquico ───────────────────────────────────────────────
function UserNode({ node, depth = 0, onEdit, isAdmin }: {
  node: OrgUser
  depth?: number
  onEdit: (user: OrgUser) => void
  isAdmin: boolean
}) {
  const [expanded, setExpanded] = useState(depth < 2)
  const hasChildren = node.children?.length > 0
  const indent = depth * 24

  return (
    <div>
      <div style={{ display:'flex', alignItems:'center', gap:9,
        padding:'7px 10px 7px', marginLeft:indent,
        borderLeft: depth > 0 ? '2px solid var(--surface-4)' : 'none',
        marginBottom:2 }}>
        {hasChildren
          ? <button onClick={() => setExpanded(e=>!e)}
              style={{ background:'none', border:'none', color:'var(--text-3)', cursor:'pointer',
                fontSize: "var(--text-xs)", width:18, flexShrink:0, padding:0 }}>
              {expanded ? '▼' : '▶'}
            </button>
          : <span style={{ width:18, flexShrink:0, fontSize: "var(--text-2xs)", color:'var(--text-4)' }}>└─</span>
        }
        <div style={{ width:30, height:30, borderRadius:'50%', flexShrink:0,
          background: getRoleColor(node.role),
          display:'flex', alignItems:'center', justifyContent:'center',
          fontSize: "var(--text-sm)", fontWeight:700, color:'#fff' }}>
          {node.full_name?.charAt(0)?.toUpperCase()}
        </div>
        <div style={{ flex:1, minWidth:0 }}>
          <div style={{ fontSize: "var(--text-base)", fontWeight:600, color:'var(--text-1)',
            overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
            {node.full_name}
          </div>
          <div style={{ fontSize: "var(--text-xs)", color:'var(--text-3)', display:'flex', gap:6 }}>
            {node.job_title && <span>{node.job_title}</span>}
            {node.department && <span>· {node.department}</span>}
          </div>
        </div>
        <span style={{ fontSize: "var(--text-2xs)", padding:'2px 7px', borderRadius:4, fontWeight:600,
          background:`${getRoleColor(node.role)}20`,
          color: getRoleColor(node.role), flexShrink:0, whiteSpace:'nowrap' }}>
          {getRoleLabel(node.role)}
        </span>
        {hasChildren && (
          <span style={{ fontSize: "var(--text-2xs)", color:'var(--text-4)', flexShrink:0 }}>
            {node.children.length} reporte{node.children.length!==1?'s':''}
          </span>
        )}
        {isAdmin && (
          <button onClick={() => onEdit(node)}
            style={{ background:'none', border:'1px solid var(--surface-4)', borderRadius:5,
              padding:'3px 8px', color:'var(--text-2)', cursor:'pointer', fontSize: "var(--text-xs)",
              fontFamily:'inherit', flexShrink:0 }}>
            ✏ Editar
          </button>
        )}
      </div>
      {expanded && hasChildren && node.children.map(child => (
        <UserNode key={child.id} node={child} depth={depth+1} onEdit={onEdit} isAdmin={isAdmin} />
      ))}
    </div>
  )
}

function ArbolTab({ nodes, allUsers, isAdmin }: {
  nodes: OrgUser[]
  allUsers: OrgUser[]
  isAdmin: boolean
}) {
  const [search, setSearch] = useState('')
  const [editing, setEditing] = useState<OrgUser | null>(null)
  const qc = useQueryClient()

  const flatUsers = useMemo<OrgUser[]>(() => {
    const flat: OrgUser[] = []
    const walk = (arr: OrgUser[]) => arr.forEach(n => { flat.push(n); if (n.children) walk(n.children) })
    walk(nodes)
    return flat
  }, [nodes])

  const searchResults = useMemo(() => {
    if (!search.trim()) return []
    const q = search.toLowerCase()
    return flatUsers.filter(u =>
      u.full_name?.toLowerCase().includes(q) ||
      u.job_title?.toLowerCase().includes(q) ||
      u.department?.toLowerCase().includes(q)
    ).slice(0,8)
  }, [flatUsers, search])

  const deptCounts = useMemo<Array<[string, number]>>(() => {
    const counts: Record<string, number> = {}
    flatUsers.forEach(u => { if (u.department) counts[u.department] = (counts[u.department]||0)+1 })
    return Object.entries(counts).sort((a, b) => b[1] - a[1])
  }, [flatUsers])

  return (
    <div style={{ display:'grid', gridTemplateColumns:'240px 1fr', gap:20 }}>
      {/* Sidebar */}
      <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
        <div style={{ background:'var(--surface-2)', border:'1px solid var(--surface-4)',
          borderRadius:12, padding:16 }}>
          <div style={{ fontSize: "var(--text-xs)", fontWeight:700, color:'var(--text-3)', marginBottom:10,
            textTransform:'uppercase', letterSpacing:'0.06em' }}>🔍 Buscar persona</div>
          <input value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Buscar persona..."
            style={{ width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)',
              borderRadius:7, padding:'8px 11px', color:'var(--text-1)', fontSize: "var(--text-sm-h)",
              outline:'none', fontFamily:'inherit', boxSizing:'border-box' }} />
          {searchResults.length > 0 && (
            <div style={{ marginTop:8, display:'flex', flexDirection:'column', gap:3 }}>
              {searchResults.map(u => (
                <button key={u.id} type="button" onClick={() => { setSearch(''); setEditing(u) }}
                  style={{ padding:'6px 10px', background:'var(--surface-1)', borderRadius:6,
                    cursor:'pointer', fontSize: "var(--text-sm)", width:'100%', textAlign:'left', fontFamily:'inherit', border:'none' }}>
                  <div style={{ fontWeight:600, color:'var(--text-1)' }}>{u.full_name}</div>
                  <div style={{ fontSize: "var(--text-xs)", color:'var(--text-3)' }}>{u.job_title||u.role}</div>
                </button>
              ))}
            </div>
          )}
        </div>

        {deptCounts.length > 0 && (
          <div style={{ background:'var(--surface-2)', border:'1px solid var(--surface-4)',
            borderRadius:12, padding:16 }}>
            <div style={{ fontSize: "var(--text-xs)", fontWeight:700, color:'var(--text-3)', marginBottom:10,
              textTransform:'uppercase', letterSpacing:'0.06em' }}>🏢 Departamentos</div>
            {deptCounts.map(([dept, count]) => (
              <div key={dept} style={{ display:'flex', justifyContent:'space-between',
                padding:'5px 0', borderBottom:'1px solid var(--surface-4)', fontSize: "var(--text-sm)" }}>
                <span style={{ color:'var(--text-1)' }}>{dept}</span>
                <span style={{ color:'var(--text-3)', fontWeight:600 }}>{count}</span>
              </div>
            ))}
          </div>
        )}

        <div style={{ background:'var(--surface-2)', border:'1px solid var(--surface-4)',
          borderRadius:12, padding:16 }}>
          <div style={{ fontSize: "var(--text-xs)", fontWeight:700, color:'var(--text-3)', marginBottom:10,
            textTransform:'uppercase', letterSpacing:'0.06em' }}>🎭 Roles</div>
          {Object.entries(ROLE_COLOR).map(([role, color]) => (
            <div key={role} style={{ display:'flex', alignItems:'center', gap:8,
              padding:'4px 0', fontSize: "var(--text-sm)" }}>
              <div style={{ width:9, height:9, borderRadius:'50%', background:color }} />
              <span style={{ color:'var(--text-1)' }}>{getRoleLabel(role)}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Árbol */}
      <div style={{ background:'var(--surface-2)', border:'1px solid var(--surface-4)',
        borderRadius:12, padding:20, overflow:'auto', maxHeight:'calc(100vh - 260px)' }}>
        {nodes.length === 0
          ? <EmptyState icon="🏢" title="Sin organigrama configurado"
              description={isAdmin
                ? 'Ve a la pestaña Posiciones para asignar managers y construir la jerarquía'
                : 'El organigrama aún no ha sido configurado'} />
          : nodes.map(root => (
              <UserNode key={root.id} node={root} depth={0} onEdit={setEditing} isAdmin={isAdmin} />
            ))
        }
      </div>

      {editing && (
        <EditPositionModal
          user={editing}
          allUsers={allUsers}
          onClose={() => setEditing(null)}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ['org-chart'] })
            qc.invalidateQueries({ queryKey: ['users'] })
            setEditing(null)
          }}
        />
      )}
    </div>
  )
}

// ── Pestaña 2: Tabla de posiciones ────────────────────────────────────────────
function PosicionesTab({ allUsers, isAdmin }: { allUsers: OrgUser[]; isAdmin: boolean }) {
  const [editing, setEditing]   = useState<OrgUser | null>(null)
  const [filterDept, setFilterDept] = useState('')
  const [search, setSearch]     = useState('')
  const qc = useQueryClient()

  const depts: string[] = [...new Set(allUsers.map(u => u.department).filter((value): value is string => Boolean(value)))].sort()

  const filtered = useMemo(() => {
    let list = allUsers
    if (filterDept) list = list.filter(u => u.department === filterDept)
    if (search.trim()) {
      const q = search.toLowerCase()
      list = list.filter(u =>
        u.full_name?.toLowerCase().includes(q) ||
        u.job_title?.toLowerCase().includes(q) ||
        u.email?.toLowerCase().includes(q)
      )
    }
    return list.sort((a,b) => (a.department||'').localeCompare(b.department||'') || a.full_name.localeCompare(b.full_name))
  }, [allUsers, filterDept, search])

  const IS: CSSProperties = { background:'var(--surface-3)', border:'1px solid var(--surface-4)',
    borderRadius:7, padding:'7px 11px', color:'var(--text-1)', fontSize: "var(--text-sm-h)",
    outline:'none', fontFamily:'inherit' }

  return (
    <div>
      {/* Filtros */}
      <div style={{ display:'flex', gap:10, marginBottom:16, flexWrap:'wrap', alignItems:'center' }}>
        <input value={search} onChange={e => setSearch(e.target.value)}
          placeholder="Buscar persona..."
          style={{ ...IS, flex:1, minWidth:200 }} />
        <select value={filterDept} onChange={e => setFilterDept(e.target.value)} style={IS}>
          <option value="">Todos los departamentos</option>
          {depts.map(d => <option key={d} value={d}>{d}</option>)}
        </select>
        <span style={{ fontSize: "var(--text-sm)", color:'var(--text-3)' }}>{filtered.length} persona{filtered.length!==1?'s':''}</span>
      </div>

      {/* Tabla */}
      <div style={{ background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:12, overflow:'hidden' }}>
        <table style={{ width:'100%', borderCollapse:'collapse', fontSize: "var(--text-base)" }}>
          <thead>
            <tr style={{ borderBottom:'2px solid var(--surface-4)', background:'var(--surface-1)' }}>
              {['Persona','Cargo','Departamento','Rol','Reporta a / Aprobador',''].map(h => (
                <th key={h} style={{ padding:'10px 14px', fontSize: "var(--text-2xs)", fontWeight:700,
                  color:'var(--text-3)', textAlign:'left', textTransform:'uppercase',
                  letterSpacing:'0.06em' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((u, i) => {
              const managerUser = allUsers.find(m => m.id === u.manager_id)
              return (
                <tr key={u.id} style={{ borderBottom:'1px solid var(--surface-4)',
                  background: i%2===0 ? 'transparent' : 'rgba(255,255,255,0.01)' }}>
                  <td style={{ padding:'10px 14px' }}>
                    <div style={{ display:'flex', alignItems:'center', gap:9 }}>
                      <div style={{ width:28, height:28, borderRadius:'50%', flexShrink:0,
                        background: ROLE_COLOR[u.role]||'#7a8aaa',
                        display:'flex', alignItems:'center', justifyContent:'center',
                        fontSize: "var(--text-xs)", fontWeight:700, color:'#fff' }}>
                        {u.full_name?.charAt(0)?.toUpperCase()}
                      </div>
                      <div>
                        <div style={{ fontWeight:600, color:'var(--text-1)' }}>{u.full_name}</div>
                        <div style={{ fontSize: "var(--text-xs)", color:'var(--text-3)' }}>{u.email}</div>
                      </div>
                    </div>
                  </td>
                  <td style={{ padding:'10px 14px', color: u.job_title ? 'var(--text-1)' : 'var(--text-4)',
                    fontStyle: u.job_title ? 'normal' : 'italic' }}>
                    {u.job_title || '—'}
                  </td>
                  <td style={{ padding:'10px 14px', color: u.department ? 'var(--text-1)' : 'var(--text-4)',
                    fontStyle: u.department ? 'normal' : 'italic' }}>
                    {u.department || '—'}
                  </td>
                  <td style={{ padding:'10px 14px' }}>
                    <span style={{ fontSize: "var(--text-xs)", padding:'2px 7px', borderRadius:4, fontWeight:600,
                      background:`${ROLE_COLOR[u.role]||'#7a8aaa'}20`,
                      color: ROLE_COLOR[u.role]||'#7a8aaa' }}>
                      {getRoleLabel(u.role)}
                    </span>
                  </td>
                  <td style={{ padding:'10px 14px' }}>
                    {managerUser ? (
                      <div style={{ display:'flex', alignItems:'center', gap:7 }}>
                        <div style={{ width:22, height:22, borderRadius:'50%',
                          background: getRoleColor(managerUser.role),
                          display:'flex', alignItems:'center', justifyContent:'center',
                          fontSize: "var(--text-2xs)", fontWeight:700, color:'#fff', flexShrink:0 }}>
                          {managerUser.full_name?.charAt(0)}
                        </div>
                        <div>
                          <div style={{ fontSize: "var(--text-sm)", fontWeight:600, color:'var(--text-1)' }}>{managerUser.full_name}</div>
                          <div style={{ fontSize: "var(--text-xs)", color:'var(--text-3)' }}>{managerUser.job_title||getRoleLabel(managerUser.role)}</div>
                        </div>
                      </div>
                    ) : (
                      <span style={{ fontSize: "var(--text-sm)", color:'var(--text-4)', fontStyle:'italic' }}>
                        Sin aprobador asignado
                      </span>
                    )}
                  </td>
                  <td style={{ padding:'10px 14px' }}>
                    {isAdmin && (
                      <button onClick={() => setEditing(u)}
                        style={{ padding:'4px 10px', borderRadius:6, border:'1px solid var(--surface-4)',
                          background:'transparent', color:'var(--accent)', fontSize: "var(--text-xs)",
                          cursor:'pointer', fontFamily:'inherit', whiteSpace:'nowrap' }}>
                        ✏ Editar
                      </button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>

        {filtered.length === 0 && (
          <div style={{ padding:'32px', textAlign:'center', color:'var(--text-3)', fontSize: "var(--text-base)" }}>
            Sin resultados para los filtros seleccionados
          </div>
        )}
      </div>

      {editing && (
        <EditPositionModal
          user={editing}
          allUsers={allUsers}
          onClose={() => setEditing(null)}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ['org-chart'] })
            qc.invalidateQueries({ queryKey: ['users'] })
            setEditing(null)
          }}
        />
      )}
    </div>
  )
}

// ── Pestaña 3: Cadenas de aprobación ─────────────────────────────────────────
function AprobacionesTab({ allUsers }: { allUsers: OrgUser[] }) {
  const [selectedUserId, setSelectedUserId] = useState('')
  const [search, setSearch] = useState('')

  const { data: chain } = useQuery<ApprovalChainData>({
    queryKey: ['approval-chain', selectedUserId],
    queryFn: () => (
      selectedUserId
        ? usersApi.approvalChain(selectedUserId)
        : usersApi.myApprovalChain()
    ).then(r => r.data as unknown as ApprovalChainData),
    enabled: true,
    staleTime: 10000,
  })

  const filteredUsers = useMemo(() => {
    if (!search.trim()) return allUsers.slice(0,15)
    const q = search.toLowerCase()
    return allUsers.filter(u =>
      u.full_name?.toLowerCase().includes(q) || u.department?.toLowerCase().includes(q)
    ).slice(0,12)
  }, [allUsers, search])

  const selectedUser = allUsers.find(u => u.id === selectedUserId)

  return (
    <div style={{ display:'grid', gridTemplateColumns:'280px 1fr', gap:20 }}>
      {/* Selector de persona */}
      <div style={{ background:'var(--surface-2)', border:'1px solid var(--surface-4)',
        borderRadius:12, padding:16, height:'fit-content' }}>
        <div style={{ fontSize: "var(--text-sm)", fontWeight:700, color:'var(--text-2)', marginBottom:12,
          textTransform:'uppercase', letterSpacing:'0.06em' }}>
          👤 Ver cadena de aprobación
        </div>
        <input value={search} onChange={e => setSearch(e.target.value)}
          placeholder="Buscar persona..."
          style={{ width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)',
            borderRadius:7, padding:'7px 11px', color:'var(--text-1)', fontSize: "var(--text-sm-h)",
            outline:'none', fontFamily:'inherit', boxSizing:'border-box', marginBottom:8 }} />
        <div style={{ display:'flex', flexDirection:'column', gap:3, maxHeight:300, overflowY:'auto' }}>
          <button
            type="button"
            onClick={() => setSelectedUserId('')}
            style={{ padding:'8px 10px', borderRadius:7, cursor:'pointer',
              background: !selectedUserId ? 'var(--accent-muted)' : 'transparent',
              border: !selectedUserId ? '1px solid var(--accent-glow)' : '1px solid transparent',
              fontSize: "var(--text-sm)", fontWeight: !selectedUserId ? 600 : 400,
              color: !selectedUserId ? 'var(--accent)' : 'var(--text-2)', width:'100%', textAlign:'left', fontFamily:'inherit' }}>
            Mi propia cadena
          </button>
          {filteredUsers.map(u => (
            <button key={u.id}
              type="button"
              onClick={() => setSelectedUserId(u.id)}
              style={{ padding:'8px 10px', borderRadius:7, cursor:'pointer',
                background: selectedUserId===u.id ? 'var(--accent-muted)' : 'transparent',
                border: selectedUserId===u.id ? '1px solid var(--accent-glow)' : '1px solid transparent',
                width:'100%', textAlign:'left', fontFamily:'inherit',
              }}>
              <div style={{ fontSize: "var(--text-sm-h)", fontWeight:600, color:'var(--text-1)' }}>{u.full_name}</div>
              <div style={{ fontSize: "var(--text-xs)", color:'var(--text-3)' }}>
                {u.job_title || ROLE_LABEL[u.role]}{u.department ? ` · ${u.department}` : ''}
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Resultado de la cadena */}
      <div>
        {chain ? (
          <div style={{ display:'flex', flexDirection:'column', gap:16 }}>
            {/* Usuario */}
            <div style={{ background:'var(--surface-2)', border:'1px solid var(--surface-4)',
              borderRadius:12, padding:'16px 20px' }}>
              <div style={{ fontSize: "var(--text-xs)", fontWeight:700, color:'var(--text-3)',
                textTransform:'uppercase', letterSpacing:'0.06em', marginBottom:10 }}>
                Empleado
              </div>
              <div style={{ display:'flex', alignItems:'center', gap:12 }}>
                <div style={{ width:40, height:40, borderRadius:'50%',
                  background:'var(--accent)', display:'flex', alignItems:'center',
                  justifyContent:'center', fontSize: "var(--text-lg)", fontWeight:700, color:'#fff' }}>
                  {chain.user_name?.charAt(0)}
                </div>
                <div>
                  <div style={{ fontSize: "var(--text-md-em)", fontWeight:700, color:'var(--text-1)' }}>{chain.user_name}</div>
                  <div style={{ fontSize: "var(--text-sm)", color:'var(--text-3)' }}>
                    {selectedUser?.job_title || ''} {selectedUser?.department ? `· ${selectedUser.department}` : ''}
                  </div>
                </div>
              </div>
            </div>

            {/* Lo que se aprueba */}
            <div style={{ background:'var(--surface-2)', border:'1px solid var(--surface-4)',
              borderRadius:12, padding:'16px 20px' }}>
              <div style={{ fontSize: "var(--text-xs)", fontWeight:700, color:'var(--text-3)',
                textTransform:'uppercase', letterSpacing:'0.06em', marginBottom:12 }}>
                Qué necesita aprobación
              </div>
              <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:10 }}>
                {[
                  { icon:'💸', label:'Gastos', desc:'Cada gasto enviado requiere aprobación del manager directo' },
                  { icon:'🏖', label:'Ausencias', desc:'Vacaciones, bajas y permisos requieren aprobación' },
                  { icon:'⏱', label:'Timesheets', desc:'Los timesheets semanales requieren validación del manager' },
                ].map(item => (
                  <div key={item.label} style={{ padding:'12px 14px', background:'var(--surface-1)',
                    borderRadius:8, border:'1px solid var(--surface-4)' }}>
                    <div style={{ fontSize: "var(--text-xl)", marginBottom:6 }}>{item.icon}</div>
                    <div style={{ fontSize: "var(--text-base)", fontWeight:600, color:'var(--text-1)', marginBottom:4 }}>{item.label}</div>
                    <div style={{ fontSize: "var(--text-xs)", color:'var(--text-3)', lineHeight:1.5 }}>{item.desc}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Cadena de aprobación */}
            <div style={{ background:'var(--surface-2)', border:'1px solid var(--surface-4)',
              borderRadius:12, padding:'16px 20px' }}>
              <div style={{ fontSize: "var(--text-xs)", fontWeight:700, color:'var(--text-3)',
                textTransform:'uppercase', letterSpacing:'0.06em', marginBottom:12 }}>
                Cadena de aprobación
              </div>

              {chain.chain.length === 0 ? (
                <div style={{ padding:'16px', background:'rgba(255,71,87,0.06)',
                  border:'1px solid rgba(255,71,87,0.2)', borderRadius:8 }}>
                  <div style={{ fontSize: "var(--text-base)", color:'var(--danger)', fontWeight:600, marginBottom:4 }}>
                    ⚠️ Sin aprobador configurado
                  </div>
                  <div style={{ fontSize: "var(--text-sm)", color:'var(--text-2)', lineHeight:1.6 }}>
                    {chain.user_name} no tiene manager asignado. Sus gastos, ausencias e imputaciones
                    quedarán pendientes sin poder ser aprobados. Ve a la pestaña <strong>Posiciones</strong> para configurarlo.
                  </div>
                </div>
              ) : (
                <div>
                  {/* Flecha visual de la cadena */}
                  <div style={{ display:'flex', flexDirection:'column', gap:0 }}>
                    {chain.chain.map((approver, idx) => {
                      const _approverFull = allUsers.find(u => u.id === approver.id)
                      return (
                        <div key={approver.id}>
                          {/* Flecha */}
                          <div style={{ display:'flex', alignItems:'center', gap:8,
                            padding:'4px 0 4px 16px' }}>
                            <div style={{ width:2, height:24, background:'var(--surface-4)' }} />
                            <span style={{ fontSize: "var(--text-xs)", color:'var(--text-3)' }}>
                              {idx === 0 ? 'aprobación directa' : `escalado nivel ${idx+1}`}
                            </span>
                          </div>
                          {/* Aprobador */}
                          <div style={{ padding:'14px 16px',
                            background: idx===0 ? 'rgba(0,229,160,0.06)' : 'var(--surface-1)',
                            border: `1px solid ${idx===0 ? 'rgba(0,229,160,0.25)' : 'var(--surface-4)'}`,
                            borderRadius:10, display:'flex', alignItems:'center', gap:12 }}>
                            <div style={{ width:36, height:36, borderRadius:'50%', flexShrink:0,
                              background: getRoleColor(approver.role),
                              display:'flex', alignItems:'center', justifyContent:'center',
                              fontSize: "var(--text-md)", fontWeight:700, color:'#fff' }}>
                              {approver.full_name?.charAt(0)}
                            </div>
                            <div style={{ flex:1 }}>
                              <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                                <span style={{ fontSize: "var(--text-md)", fontWeight:600, color:'var(--text-1)' }}>
                                  {approver.full_name}
                                </span>
                                {idx === 0 && (
                                  <span style={{ fontSize: "var(--text-2xs)", padding:'2px 8px', borderRadius:4,
                                    background:'rgba(0,229,160,0.15)', color:'#34d399',
                                    fontWeight:700 }}>APROBADOR DIRECTO</span>
                                )}
                              </div>
                              <div style={{ fontSize: "var(--text-sm)", color:'var(--text-3)' }}>
                                {approver.job_title || getRoleLabel(approver.role)}
                                {approver.department ? ` · ${approver.department}` : ''}
                              </div>
                            </div>
                            <div style={{ display:'flex', flexDirection:'column', gap:4, alignItems:'flex-end' }}>
                              {['💸 Gastos','🏖 Ausencias','⏱ Timesheets'].map(lbl => (
                                <span key={lbl} style={{ fontSize: "var(--text-2xs)", padding:'2px 8px', borderRadius:4,
                                  background:'var(--surface-3)', color:'var(--text-2)' }}>{lbl}</span>
                              ))}
                            </div>
                          </div>
                        </div>
                      )
                    })}
                  </div>

                  <div style={{ marginTop:12, padding:'10px 14px',
                    background:'var(--accent-muted)', border:'1px solid var(--accent-glow)',
                    borderRadius:8, fontSize: "var(--text-sm)", color:'var(--text-2)', lineHeight:1.6 }}>
                    💡 <strong>{chain.chain[0]?.full_name}</strong> es el aprobador directo.
                    Si no responde en el plazo configurado, la solicitud se escala automáticamente
                    al siguiente nivel de la cadena.
                  </div>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div style={{ display:'flex', alignItems:'center', justifyContent:'center',
            height:200 }}><Spinner /></div>
        )}
      </div>
    </div>
  )
}

// ── Página principal ──────────────────────────────────────────────────────────
export default function OrgChartPage() {
  const t = useAppT()
  const { hasRole } = useAuth()
  const [tab, setTab] = useState('arbol')
  const isAdmin = hasRole('admin')

  const { data: chartData, isLoading: loadingChart } = useQuery<OrgChartData>({
    queryKey: ['org-chart'],
    queryFn: () => usersApi.orgChart().then(r => ((r.data as { data?: OrgChartData })?.data ?? r.data) as OrgChartData),
    staleTime: 30000,
  })

  const { data: allUsers = [] } = useQuery<OrgUser[]>({
    queryKey: ['users'],
    queryFn: () => usersApi.list().then(r => r.data),
    staleTime: 30000,
  })

  const nodes: OrgUser[] = chartData?.nodes || []
  const total = chartData?.total || 0

  const TABS = [
    { id:'arbol',       label:'Árbol jerárquico',      desc:'Vista visual del organigrama' },
    { id:'posiciones',  label:'Posiciones',             desc:'Editar cargo, depto y manager de todos' },
    { id:'aprobaciones',label:'Cadenas de aprobación',  desc:'Quién aprueba qué para quién' },
  ]

  return (
    <PageShell>
      <PageHeader
        icon={<Network size={18} />}
        title="Organigrama"
        subtitle={t('org_chart.subtitle', { total })}
        showListExport={tab !== 'arbol'}
      />

      {/* Tabs */}
      <div style={{ display:'flex', gap:6, marginBottom:24,
        borderBottom:'1px solid var(--surface-4)', paddingBottom:14 }}>
        {TABS.map(tabObj => (
          <button key={tabObj.id} onClick={() => setTab(tabObj.id)} style={{
            padding:'8px 16px', borderRadius:8,
            border:`1px solid ${tab===tabObj.id ? 'var(--accent)' : 'var(--surface-4)'}`,
            background: tab===tabObj.id ? 'var(--accent-muted)' : 'transparent',
            color: tab===tabObj.id ? 'var(--accent)' : 'var(--text-2)',
            fontSize: "var(--text-sm)", fontWeight:600, cursor:'pointer', fontFamily:'inherit',
          }} title={tabObj.desc}>{tabObj.label}</button>
        ))}
      </div>

      {/* Contenido */}
      {loadingChart && tab === 'arbol'
        ? <div style={{ textAlign:'center', padding:60 }}><Spinner /></div>
        : tab === 'arbol'
          ? <ArbolTab nodes={nodes} allUsers={allUsers} isAdmin={isAdmin} />
          : tab === 'posiciones'
            ? <PosicionesTab allUsers={allUsers} isAdmin={isAdmin} />
            : <AprobacionesTab allUsers={allUsers} />
      }
    </PageShell>
  )
}

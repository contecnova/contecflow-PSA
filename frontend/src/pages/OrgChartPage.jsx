/**
 * OrgChartPage — Organigrama, posiciones y cadenas de aprobación
 * 
 * Pestaña 1 — Árbol: visualización jerárquica con edición inline
 * Pestaña 2 — Posiciones: tabla editable de todos los usuarios
 * Pestaña 3 — Aprobaciones: quién aprueba gastos, ausencias e imputaciones
 */
import { useState, useMemo } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useToast } from '../context/ToastContext'
import { useAuth } from '../context/AuthContext'
import api from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import { Button, Spinner, EmptyState, Modal } from '../components/ui'
import { extractErr } from '../utils/helpers'
import { useAppT } from '../i18n/AppLangContext'

// ── Colores por rol ───────────────────────────────────────────────────────────
const ROLE_COLOR = {
  admin: '#4f8ef7', pm: '#7c3aed', team_lead: '#0891b2',
  employee: '#059669', hr: '#d97706', client: '#6b7280',
}
const ROLE_LABEL = {
  admin: 'Admin', pm: 'PM', team_lead: 'Team Lead',
  employee: 'Empleado', hr: 'RRHH', client: 'Cliente',
}

// ── Modal editar posición ─────────────────────────────────────────────────────
function EditPositionModal({ user, allUsers, onClose, onSaved }) {
  const toast = useToast()
  const [managerId, setManagerId]   = useState(user.manager_id || '')
  const [jobTitle, setJobTitle]     = useState(user.job_title || '')
  const [department, setDepartment] = useState(user.department || '')
  const [saving, setSaving]         = useState(false)

  const IS = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)',
    borderRadius:8, padding:'9px 12px', color:'var(--text-1)', fontSize:13,
    outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
  const LS = { fontSize:11, fontWeight:600, color:'var(--text-2)', display:'block',
    marginBottom:5, textTransform:'uppercase', letterSpacing:'0.06em' }

  const eligible = allUsers.filter(u => u.id !== user.id)

  const handleSave = async () => {
    setSaving(true)
    try {
      await api.patch(`/users/${user.id}`, {
        job_title: jobTitle || undefined,
        department: department || undefined,
      })
      await api.patch(`/users/${user.id}/manager`, { manager_id: managerId || null })
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
          <div style={{ fontSize:14, fontWeight:600 }}>{user.full_name}</div>
          <div style={{ fontSize:12, color:'var(--text-3)', marginTop:2 }}>
            {user.email} · <span style={{ color: ROLE_COLOR[user.role] }}>{ROLE_LABEL[user.role]}</span>
          </div>
        </div>

        <div>
          <label style={LS}>Cargo / Puesto</label>
          <input value={jobTitle} onChange={e => setJobTitle(e.target.value)} style={IS}
            placeholder="Ej: Desarrollador Senior" />
        </div>
        <div>
          <label style={LS}>Departamento</label>
          <input value={department} onChange={e => setDepartment(e.target.value)} style={IS}
            placeholder="Ej: Tecnologia" />
        </div>
        <div>
          <label style={LS}>Reporta a / Aprobador directo</label>
          <div style={{ fontSize:11, color:'var(--text-3)', marginBottom:6, lineHeight:1.6 }}>
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
          border:'1px solid var(--accent-glow)', borderRadius:8, fontSize:12,
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
function UserNode({ node, depth=0, onEdit, isAdmin }) {
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
                fontSize:11, width:18, flexShrink:0, padding:0 }}>
              {expanded ? '▼' : '▶'}
            </button>
          : <span style={{ width:18, flexShrink:0, fontSize:10, color:'var(--text-4)' }}>└─</span>
        }
        <div style={{ width:30, height:30, borderRadius:'50%', flexShrink:0,
          background: ROLE_COLOR[node.role] || '#6b7280',
          display:'flex', alignItems:'center', justifyContent:'center',
          fontSize:12, fontWeight:700, color:'#fff' }}>
          {node.full_name?.charAt(0)?.toUpperCase()}
        </div>
        <div style={{ flex:1, minWidth:0 }}>
          <div style={{ fontSize:13, fontWeight:600, color:'var(--text-1)',
            overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
            {node.full_name}
          </div>
          <div style={{ fontSize:11, color:'var(--text-3)', display:'flex', gap:6 }}>
            {node.job_title && <span>{node.job_title}</span>}
            {node.department && <span>· {node.department}</span>}
          </div>
        </div>
        <span style={{ fontSize:10, padding:'2px 7px', borderRadius:4, fontWeight:600,
          background:`${ROLE_COLOR[node.role]||'#6b7280'}20`,
          color: ROLE_COLOR[node.role]||'#6b7280', flexShrink:0, whiteSpace:'nowrap' }}>
          {ROLE_LABEL[node.role]||node.role}
        </span>
        {hasChildren && (
          <span style={{ fontSize:10, color:'var(--text-4)', flexShrink:0 }}>
            {node.children.length} reporte{node.children.length!==1?'s':''}
          </span>
        )}
        {isAdmin && (
          <button onClick={() => onEdit(node)}
            style={{ background:'none', border:'1px solid var(--surface-4)', borderRadius:5,
              padding:'3px 8px', color:'var(--text-2)', cursor:'pointer', fontSize:11,
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

function ArbolTab({ nodes, allUsers, isAdmin, _onRefresh }) {
  const [search, setSearch] = useState('')
  const [editing, setEditing] = useState(null)
  const qc = useQueryClient()

  const flatUsers = useMemo(() => {
    const flat = []
    const walk = arr => arr.forEach(n => { flat.push(n); if (n.children) walk(n.children) })
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

  const deptCounts = useMemo(() => {
    const counts = {}
    flatUsers.forEach(u => { if (u.department) counts[u.department] = (counts[u.department]||0)+1 })
    return Object.entries(counts).sort((a,b) => b[1]-a[1])
  }, [flatUsers])

  return (
    <div style={{ display:'grid', gridTemplateColumns:'240px 1fr', gap:20 }}>
      {/* Sidebar */}
      <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
        <div style={{ background:'var(--surface-2)', border:'1px solid var(--surface-4)',
          borderRadius:12, padding:16 }}>
          <div style={{ fontSize:11, fontWeight:700, color:'var(--text-3)', marginBottom:10,
            textTransform:'uppercase', letterSpacing:'0.06em' }}>🔍 Buscar persona</div>
          <input value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Buscar persona..."
            style={{ width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)',
              borderRadius:7, padding:'8px 11px', color:'var(--text-1)', fontSize:12.5,
              outline:'none', fontFamily:'inherit', boxSizing:'border-box' }} />
          {searchResults.length > 0 && (
            <div style={{ marginTop:8, display:'flex', flexDirection:'column', gap:3 }}>
              {searchResults.map(u => (
                <div key={u.id} onClick={() => { setSearch(''); setEditing(u) }}
                  style={{ padding:'6px 10px', background:'var(--surface-1)', borderRadius:6,
                    cursor:'pointer', fontSize:12 }}>
                  <div style={{ fontWeight:600, color:'var(--text-1)' }}>{u.full_name}</div>
                  <div style={{ fontSize:11, color:'var(--text-3)' }}>{u.job_title||u.role}</div>
                </div>
              ))}
            </div>
          )}
        </div>

        {deptCounts.length > 0 && (
          <div style={{ background:'var(--surface-2)', border:'1px solid var(--surface-4)',
            borderRadius:12, padding:16 }}>
            <div style={{ fontSize:11, fontWeight:700, color:'var(--text-3)', marginBottom:10,
              textTransform:'uppercase', letterSpacing:'0.06em' }}>🏢 Departamentos</div>
            {deptCounts.map(([dept, count]) => (
              <div key={dept} style={{ display:'flex', justifyContent:'space-between',
                padding:'5px 0', borderBottom:'1px solid var(--surface-4)', fontSize:12 }}>
                <span style={{ color:'var(--text-1)' }}>{dept}</span>
                <span style={{ color:'var(--text-3)', fontWeight:600 }}>{count}</span>
              </div>
            ))}
          </div>
        )}

        <div style={{ background:'var(--surface-2)', border:'1px solid var(--surface-4)',
          borderRadius:12, padding:16 }}>
          <div style={{ fontSize:11, fontWeight:700, color:'var(--text-3)', marginBottom:10,
            textTransform:'uppercase', letterSpacing:'0.06em' }}>🎭 Roles</div>
          {Object.entries(ROLE_COLOR).map(([role, color]) => (
            <div key={role} style={{ display:'flex', alignItems:'center', gap:8,
              padding:'4px 0', fontSize:12 }}>
              <div style={{ width:9, height:9, borderRadius:'50%', background:color }} />
              <span style={{ color:'var(--text-1)' }}>{ROLE_LABEL[role]||role}</span>
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
function PosicionesTab({ allUsers, isAdmin }) {
  const [editing, setEditing]   = useState(null)
  const [filterDept, setFilterDept] = useState('')
  const [search, setSearch]     = useState('')
  const qc = useQueryClient()

  const depts = [...new Set(allUsers.map(u => u.department).filter(Boolean))].sort()

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

  const IS = { background:'var(--surface-3)', border:'1px solid var(--surface-4)',
    borderRadius:7, padding:'7px 11px', color:'var(--text-1)', fontSize:12.5,
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
        <span style={{ fontSize:12, color:'var(--text-3)' }}>{filtered.length} persona{filtered.length!==1?'s':''}</span>
      </div>

      {/* Tabla */}
      <div style={{ background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:12, overflow:'hidden' }}>
        <table style={{ width:'100%', borderCollapse:'collapse', fontSize:13 }}>
          <thead>
            <tr style={{ borderBottom:'2px solid var(--surface-4)', background:'var(--surface-1)' }}>
              {['Persona','Cargo','Departamento','Rol','Reporta a / Aprobador',''].map(h => (
                <th key={h} style={{ padding:'10px 14px', fontSize:10, fontWeight:700,
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
                        background: ROLE_COLOR[u.role]||'#6b7280',
                        display:'flex', alignItems:'center', justifyContent:'center',
                        fontSize:11, fontWeight:700, color:'#fff' }}>
                        {u.full_name?.charAt(0)?.toUpperCase()}
                      </div>
                      <div>
                        <div style={{ fontWeight:600, color:'var(--text-1)' }}>{u.full_name}</div>
                        <div style={{ fontSize:11, color:'var(--text-3)' }}>{u.email}</div>
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
                    <span style={{ fontSize:11, padding:'2px 7px', borderRadius:4, fontWeight:600,
                      background:`${ROLE_COLOR[u.role]||'#6b7280'}20`,
                      color: ROLE_COLOR[u.role]||'#6b7280' }}>
                      {ROLE_LABEL[u.role]||u.role}
                    </span>
                  </td>
                  <td style={{ padding:'10px 14px' }}>
                    {managerUser ? (
                      <div style={{ display:'flex', alignItems:'center', gap:7 }}>
                        <div style={{ width:22, height:22, borderRadius:'50%',
                          background: ROLE_COLOR[managerUser.role]||'#6b7280',
                          display:'flex', alignItems:'center', justifyContent:'center',
                          fontSize:10, fontWeight:700, color:'#fff', flexShrink:0 }}>
                          {managerUser.full_name?.charAt(0)}
                        </div>
                        <div>
                          <div style={{ fontSize:12, fontWeight:600, color:'var(--text-1)' }}>{managerUser.full_name}</div>
                          <div style={{ fontSize:11, color:'var(--text-3)' }}>{managerUser.job_title||ROLE_LABEL[managerUser.role]}</div>
                        </div>
                      </div>
                    ) : (
                      <span style={{ fontSize:12, color:'var(--text-4)', fontStyle:'italic' }}>
                        Sin aprobador asignado
                      </span>
                    )}
                  </td>
                  <td style={{ padding:'10px 14px' }}>
                    {isAdmin && (
                      <button onClick={() => setEditing(u)}
                        style={{ padding:'4px 10px', borderRadius:6, border:'1px solid var(--surface-4)',
                          background:'transparent', color:'var(--accent)', fontSize:11,
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
          <div style={{ padding:'32px', textAlign:'center', color:'var(--text-3)', fontSize:13 }}>
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
function AprobacionesTab({ allUsers }) {
  const [selectedUserId, setSelectedUserId] = useState('')
  const [search, setSearch] = useState('')

  const { data: chain } = useQuery({
    queryKey: ['approval-chain', selectedUserId],
    queryFn: () => api.get(
      selectedUserId
        ? `/users/${selectedUserId}/approval-chain`
        : '/users/me/approval-chain'
    ).then(r => r.data),
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
        <div style={{ fontSize:12, fontWeight:700, color:'var(--text-2)', marginBottom:12,
          textTransform:'uppercase', letterSpacing:'0.06em' }}>
          👤 Ver cadena de aprobación
        </div>
        <input value={search} onChange={e => setSearch(e.target.value)}
          placeholder="Buscar persona..."
          style={{ width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)',
            borderRadius:7, padding:'7px 11px', color:'var(--text-1)', fontSize:12.5,
            outline:'none', fontFamily:'inherit', boxSizing:'border-box', marginBottom:8 }} />
        <div style={{ display:'flex', flexDirection:'column', gap:3, maxHeight:300, overflowY:'auto' }}>
          <div
            onClick={() => setSelectedUserId('')}
            style={{ padding:'8px 10px', borderRadius:7, cursor:'pointer',
              background: !selectedUserId ? 'var(--accent-muted)' : 'transparent',
              border: !selectedUserId ? '1px solid var(--accent-glow)' : '1px solid transparent',
              fontSize:12, fontWeight: !selectedUserId ? 600 : 400,
              color: !selectedUserId ? 'var(--accent)' : 'var(--text-2)' }}>
            Mi propia cadena
          </div>
          {filteredUsers.map(u => (
            <div key={u.id}
              onClick={() => setSelectedUserId(u.id)}
              style={{ padding:'8px 10px', borderRadius:7, cursor:'pointer',
                background: selectedUserId===u.id ? 'var(--accent-muted)' : 'transparent',
                border: selectedUserId===u.id ? '1px solid var(--accent-glow)' : '1px solid transparent',
              }}>
              <div style={{ fontSize:12.5, fontWeight:600, color:'var(--text-1)' }}>{u.full_name}</div>
              <div style={{ fontSize:11, color:'var(--text-3)' }}>
                {u.job_title || ROLE_LABEL[u.role]}{u.department ? ` · ${u.department}` : ''}
              </div>
            </div>
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
              <div style={{ fontSize:11, fontWeight:700, color:'var(--text-3)',
                textTransform:'uppercase', letterSpacing:'0.06em', marginBottom:10 }}>
                Empleado
              </div>
              <div style={{ display:'flex', alignItems:'center', gap:12 }}>
                <div style={{ width:40, height:40, borderRadius:'50%',
                  background:'var(--accent)', display:'flex', alignItems:'center',
                  justifyContent:'center', fontSize:16, fontWeight:700, color:'#fff' }}>
                  {chain.user_name?.charAt(0)}
                </div>
                <div>
                  <div style={{ fontSize:15, fontWeight:700, color:'var(--text-1)' }}>{chain.user_name}</div>
                  <div style={{ fontSize:12, color:'var(--text-3)' }}>
                    {(selectedUser||{}).job_title || ''} {(selectedUser||{}).department ? `· ${(selectedUser||{}).department}` : ''}
                  </div>
                </div>
              </div>
            </div>

            {/* Lo que se aprueba */}
            <div style={{ background:'var(--surface-2)', border:'1px solid var(--surface-4)',
              borderRadius:12, padding:'16px 20px' }}>
              <div style={{ fontSize:11, fontWeight:700, color:'var(--text-3)',
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
                    <div style={{ fontSize:20, marginBottom:6 }}>{item.icon}</div>
                    <div style={{ fontSize:13, fontWeight:600, color:'var(--text-1)', marginBottom:4 }}>{item.label}</div>
                    <div style={{ fontSize:11, color:'var(--text-3)', lineHeight:1.5 }}>{item.desc}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Cadena de aprobación */}
            <div style={{ background:'var(--surface-2)', border:'1px solid var(--surface-4)',
              borderRadius:12, padding:'16px 20px' }}>
              <div style={{ fontSize:11, fontWeight:700, color:'var(--text-3)',
                textTransform:'uppercase', letterSpacing:'0.06em', marginBottom:12 }}>
                Cadena de aprobación
              </div>

              {chain.chain.length === 0 ? (
                <div style={{ padding:'16px', background:'rgba(255,71,87,0.06)',
                  border:'1px solid rgba(255,71,87,0.2)', borderRadius:8 }}>
                  <div style={{ fontSize:13, color:'var(--danger)', fontWeight:600, marginBottom:4 }}>
                    ⚠️ Sin aprobador configurado
                  </div>
                  <div style={{ fontSize:12, color:'var(--text-2)', lineHeight:1.6 }}>
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
                            <span style={{ fontSize:11, color:'var(--text-3)' }}>
                              {idx === 0 ? 'aprobación directa' : `escalado nivel ${idx+1}`}
                            </span>
                          </div>
                          {/* Aprobador */}
                          <div style={{ padding:'14px 16px',
                            background: idx===0 ? 'rgba(0,229,160,0.06)' : 'var(--surface-1)',
                            border: `1px solid ${idx===0 ? 'rgba(0,229,160,0.25)' : 'var(--surface-4)'}`,
                            borderRadius:10, display:'flex', alignItems:'center', gap:12 }}>
                            <div style={{ width:36, height:36, borderRadius:'50%', flexShrink:0,
                              background: ROLE_COLOR[approver.role]||'#6b7280',
                              display:'flex', alignItems:'center', justifyContent:'center',
                              fontSize:14, fontWeight:700, color:'#fff' }}>
                              {approver.full_name?.charAt(0)}
                            </div>
                            <div style={{ flex:1 }}>
                              <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                                <span style={{ fontSize:14, fontWeight:600, color:'var(--text-1)' }}>
                                  {approver.full_name}
                                </span>
                                {idx === 0 && (
                                  <span style={{ fontSize:10, padding:'2px 8px', borderRadius:4,
                                    background:'rgba(0,229,160,0.15)', color:'#00e5a0',
                                    fontWeight:700 }}>APROBADOR DIRECTO</span>
                                )}
                              </div>
                              <div style={{ fontSize:12, color:'var(--text-3)' }}>
                                {approver.job_title || ROLE_LABEL[approver.role]}
                                {approver.department ? ` · ${approver.department}` : ''}
                              </div>
                            </div>
                            <div style={{ display:'flex', flexDirection:'column', gap:4, alignItems:'flex-end' }}>
                              {['💸 Gastos','🏖 Ausencias','⏱ Timesheets'].map(lbl => (
                                <span key={lbl} style={{ fontSize:10, padding:'2px 8px', borderRadius:4,
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
                    borderRadius:8, fontSize:12, color:'var(--text-2)', lineHeight:1.6 }}>
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
  const _t = useAppT()
  const { hasRole } = useAuth()
  const [tab, setTab] = useState('arbol')
  const isAdmin = hasRole('admin')

  const { data: chartData, isLoading: loadingChart } = useQuery({
    queryKey: ['org-chart'],
    queryFn: () => api.get('/users/org-chart').then(r => r.data),
    staleTime: 30000,
  })

  const { data: allUsers = [] } = useQuery({
    queryKey: ['users'],
    queryFn: () => api.get('/users').then(r => r.data),
    staleTime: 30000,
  })

  const nodes = chartData?.nodes || []
  const total = chartData?.total || 0

  const TABS = [
    { id:'arbol',       label:'🌳 Árbol jerárquico',      desc:'Vista visual del organigrama' },
    { id:'posiciones',  label:'📋 Posiciones',             desc:'Editar cargo, depto y manager de todos' },
    { id:'aprobaciones',label:'✅ Cadenas de aprobación',  desc:'Quién aprueba qué para quién' },
  ]

  return (
    <div style={{ padding:'20px 28px' }}>
      <PageHeader
        title="Organigrama"
        subtitle={_t('org_chart.subtitle', { total })}
      />

      {/* Tabs */}
      <div style={{ display:'flex', gap:6, marginBottom:24,
        borderBottom:'1px solid var(--surface-4)', paddingBottom:14 }}>
        {TABS.map(tabObj => (
          <button key={tabObj.id} onClick={() => setTab(tabObj.id)} style={{
            padding:'8px 16px', borderRadius:8,
            border:`1px solid ${tab===tabObj.id ? 'var(--accent-glow)' : 'var(--surface-4)'}`,
            background: tab===tabObj.id ? 'var(--accent-muted)' : 'transparent',
            color: tab===tabObj.id ? 'var(--accent)' : 'var(--text-2)',
            fontSize:12, fontWeight:600, cursor:'pointer', fontFamily:'inherit',
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
    </div>
  )
}

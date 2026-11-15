/**
 * OrgChartPage — Organigrama, posiciones y cadenas de aprobación
 * 
 * Pestaña 1 — Árbol: visualización jerárquica con edición inline
 * Pestaña 2 — Posiciones: tabla editable de todos los usuarios
 * Pestaña 3 — Aprobaciones: quién aprueba gastos, ausencias e imputaciones
 */
import { useAppLang } from '../i18n/AppLangContext'
import { useState, useMemo, useId } from 'react'
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
import { alpha } from '../constants/theme'
import { STALE_LIVE_MS, STALE_SHORT_MS } from '../constants/timings'
import './OrgChartPage.css'

// ── Colores por rol ───────────────────────────────────────────────────────────
const ROLE_COLOR: Record<string, string> = {
  admin: 'var(--accent)', pm: 'var(--purple)', team_lead: 'var(--info)',
  employee: 'var(--success)', hr: 'var(--warning)', client: 'var(--text-3)',
}
const ROLE_LABEL: Record<string, string> = {
  admin: 'pagina_orgc.admin', pm: 'pagina_orgc.pm', team_lead: 'pagina_orgc.team_lead',
  employee: 'pagina_orgc.empleado', hr: 'pagina_orgc.rrhh', client: 'pagina_orgc.cliente',
}

interface DepartmentOption {
  id: string | number
  name: string
  is_active?: boolean
}

interface OrgUser {
  id: string
  full_name: string
  /** Solo con la ficha completa: `GET /users` no lo manda al empleado (`PersonaInterna`). */
  email?: string
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

function getRoleColor(role: string) {
  return ROLE_COLOR[role as keyof typeof ROLE_COLOR] ?? 'var(--text-3)'
}

function getRoleLabel(role: string, t: (k: string) => string) {
  const clave = ROLE_LABEL[role as keyof typeof ROLE_LABEL]
  return clave ? t(clave) : role
}

// ── Modal editar posición ─────────────────────────────────────────────────────
function EditPositionModal({ user, allUsers, onClose, onSaved }: {
  user: OrgUser
  allUsers: OrgUser[]
  onClose: () => void
  onSaved: () => void
}) {
  const idCampo = useId()
  const t = useAppT()
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
      // Una sola llamada: responsable, puesto y departamento se guardan juntos o no se guarda nada.
      await usersApi.updateManager(user.id, { manager_id: managerId || null, job_title: jobTitle || null, department: department || null })
      toast.success(t('pagina_orgc.posicion_actualizada'))
      onSaved()
    } catch (e) {
      toast.error(extractErr(e, t('pagina_orgc.error_al_actualizar')))
    } finally { setSaving(false) }
  }

  return (
    <Modal open title={t('pagina_orgc.editar_posicion', { full_name: user.full_name })} onClose={onClose}>
      <div className="u-stack-14">
        <div className="orgc-card">
          <div className="u-md-600">{user.full_name}</div>
          <div className="orgc-box">
            {user.email && <>{user.email} · </>}<span className="orgchart-sx2" style={{ '--orgchart-v1': getRoleColor(user.role) } as React.CSSProperties}>{getRoleLabel(user.role, t)}</span>
          </div>
        </div>

        <div>
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={LS}>{t('pagina_orgc.cargo_puesto')}</label>
          <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={jobTitle} onChange={e => setJobTitle(e.target.value)} style={IS}
            placeholder={t('pagina_orgc.ej_desarrollador_senior')} />
        </div>
        <div>
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={LS}>{t('pagina_orgc.departamento')}</label>
          <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={department} onChange={e => setDepartment(e.target.value)} style={IS}>
            <option value="">{t('orgchart.sin_departamento')}</option>
            {departments.filter(d => d.is_active !== false).map(d => <option key={d.id} value={d.name}>{d.name}</option>)}
          </select>
        </div>
        <div>
          <label id={`${idCampo}-eta133`} htmlFor={`${idCampo}-a133`} style={LS}>{t('pagina_orgc.reporta_a_aprobador_directo')}</label>
          <div className="orgc-box-2">
            {t('orgchart.esta_persona_aprobara_los')} <strong>{t('pagina_orgc.gastos_min')}</strong>, <strong>{t('pagina_orgc.ausencias_min')}</strong> {t('pagina_orgc.y')} <strong>{t('pagina_orgc.imputaciones_min')}</strong> {t('orgchart.de')} {user.full_name.split(' ')[0]}.
          </div>
          <select id={`${idCampo}-a133`} aria-labelledby={`${idCampo}-eta133`} value={managerId} onChange={e => setManagerId(e.target.value)} style={IS}>
            <option value="">{t('orgchart.sin_manager_nivel_raiz_aprobacion_manual')}</option>
            {eligible.map(u => (
              <option key={u.id} value={u.id}>
                {u.full_name}
                {u.job_title ? ` — ${u.job_title}` : ''}
                {u.department ? ` (${u.department})` : ''}
              </option>
            ))}
          </select>
        </div>

        <div className="orgc-card-2">
          💡 <strong>{t('orgchart.como_funciona_la_aprobacion')}</strong> {t('orgchart.cuando')} {user.full_name.split(' ')[0]} {t('orgchart.envie_un_gasto_solicite_una_ausencia_o')}
          {managerId
            ? ' ' + t('pagina_orgc.recibira_la_notificacion_para_aprobar_o', { v1: eligible.find(u=>u.id===managerId)?.full_name || t('pagina_orgc.su_manager') })
            : t('pagina_orgc.quedara_pendiente_de_asignacion_de_aprobador')}
        </div>

        <div className="u-actions-10">
          <Button variant="secondary" onClick={onClose}>{t('pagina_orgc.cancelar')}</Button>
          <Button onClick={handleSave} disabled={saving} loading={saving}>{t('orgchart.guardar_posicion')}</Button>
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
  const { t } = useAppLang()
  const [expanded, setExpanded] = useState(depth < 2)
  const hasChildren = (node.children?.length ?? 0) > 0
  const indent = depth * 24

  return (
    <div>
      <div className={`orgc-row ${depth > 0 ? 'orgchart-sx3' : 'orgchart-sx4'}`} style={{ marginLeft:indent }}>
        {hasChildren
          ? <button onClick={() => setExpanded(e=>!e)}
              className="orgc-btn">
              {expanded ? '▼' : '▶'}
            </button>
          : <span className="orgc-label">└─</span>
        }
        <div className="orgc-row-2" style={{ background: getRoleColor(node.role) }}>
          {node.full_name?.charAt(0)?.toUpperCase()}
        </div>
        <div className="u-flex1-min0">
          <div className="orgc-box-3">
            {node.full_name}
          </div>
          <div className="orgc-row-3">
            {node.job_title && <span>{node.job_title}</span>}
            {node.department && <span>· {node.department}</span>}
          </div>
        </div>
        <span className="orgc-label-2" style={{ background:alpha(getRoleColor(node.role), '20'), color: getRoleColor(node.role) }}>
          {getRoleLabel(node.role, t)}
        </span>
        {hasChildren && (
          <span className="orgc-label-3">
            {t((node.children?.length ?? 0) === 1 ? 'pagina_orgc.reportes_uno' : 'pagina_orgc.reportes_otros', { n: node.children?.length ?? 0 })}
          </span>
        )}
        {isAdmin && (
          <button onClick={() => onEdit(node)}
            className="orgc-btn-2">
            {t('pagina_orgc.editar')}
          </button>
        )}
      </div>
      {expanded && hasChildren && (node.children ?? []).map(child => (
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
  const t = useAppT()
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
    <div className="orgc-grid">
      {/* Sidebar */}
      <div className="u-stack-14">
        <div className="orgc-card-3">
          <div className="orgc-box-4">{t('pagina_orgc.buscar_persona')}</div>
          <input aria-label={t('pagina_orgc.buscar_persona_2')} value={search} onChange={e => setSearch(e.target.value)}
            placeholder={t('pagina_orgc.buscar_persona_2')}
            className="orgc-input" />
          {searchResults.length > 0 && (
            <div className="orgc-stack">
              {searchResults.map(u => (
                <button key={u.id} type="button" onClick={() => { setSearch(''); setEditing(u) }}
                  className="orgc-btn-3">
                  <div className="orgc-box-5">{u.full_name}</div>
                  <div className="u-text3-xs">{u.job_title||u.role}</div>
                </button>
              ))}
            </div>
          )}
        </div>

        {deptCounts.length > 0 && (
          <div className="orgc-card-3">
            <div className="orgc-box-4">{t('pagina_orgc.departamentos')}</div>
            {deptCounts.map(([dept, count]) => (
              <div key={dept} className="orgc-row-4">
                <span className="u-text1">{dept}</span>
                <span className="orgc-label-4">{count}</span>
              </div>
            ))}
          </div>
        )}

        <div className="orgc-card-3">
          <div className="orgc-box-4">{t('pagina_orgc.roles')}</div>
          {Object.entries(ROLE_COLOR).map(([role, color]) => (
            <div key={role} className="orgc-row-5">
              <div className="orgc-box-6" style={{ background:color }} />
              <span className="u-text1">{getRoleLabel(role, t)}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Árbol */}
      <div className="orgc-card-4">
        {nodes.length === 0
          ? <EmptyState icon="🏢" title={t('orgchart.sin_organigrama_configurado')}
              description={isAdmin
                ? t('pagina_orgc.ve_a_la_pestana_posiciones_para')
                : t('pagina_orgc.el_organigrama_aun_no_ha_sido')} />
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
  const t = useAppT()
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
      <div className="orgc-row-6">
        <input aria-label={t('pagina_orgc.buscar_persona_2')} value={search} onChange={e => setSearch(e.target.value)}
          placeholder={t('pagina_orgc.buscar_persona_2')}
          style={{ ...IS, flex:1, minWidth:200 }} />
        <select value={filterDept} onChange={e => setFilterDept(e.target.value)} style={IS}>
          <option value="">{t('orgchart.todos_los_departamentos')}</option>
          {depts.map(d => <option key={d} value={d}>{d}</option>)}
        </select>
        <span className="u-text3-sm">{t(filtered.length === 1 ? 'pagina_orgc.personas_uno' : 'pagina_orgc.personas_otros', { n: filtered.length })}</span>
      </div>

      {/* Tabla */}
      <div className="ds-card ds-card--plano">
        <table className="orgc-table">
          <thead>
            <tr className="orgc-row-7">
              {[t('pagina_orgc.persona'),t('pagina_orgc.cargo'),t('pagina_orgc.departamento'),t('pagina_orgc.rol'),t('pagina_orgc.reporta_a_aprobador'),''].map(h => (
                <th key={h} className="orgc-th">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((u, i) => {
              const managerUser = allUsers.find(m => m.id === u.manager_id)
              return (
                <tr key={u.id} className={`u-border-b ${i%2===0 ? 'orgchart-sx5' : 'orgchart-sx6'}`}>
                  <td className="orgc-td" aria-label={`${u.full_name ?? ''} · ${u.email ?? ''}`}>
                    <div className="orgc-row-8">
                      <div className="orgc-row-9" style={{ background: ROLE_COLOR[u.role]||'var(--text-3)' }}>
                        {u.full_name?.charAt(0)?.toUpperCase()}
                      </div>
                      <div>
                        <div className="orgc-box-5">{u.full_name}</div>
                        <div className="u-text3-xs">{u.email}</div>
                      </div>
                    </div>
                  </td>
                  <td className={`orgc-td ${u.job_title ? 'orgchart-sx7' : 'orgchart-sx8'}`}>
                    {u.job_title || '—'}
                  </td>
                  <td className={`orgc-td ${u.department ? 'orgchart-sx7' : 'orgchart-sx8'}`}>
                    {u.department || '—'}
                  </td>
                  <td className="orgc-td">
                    <span className="orgc-label-5" style={{ background:alpha(ROLE_COLOR[u.role]||'var(--text-3)', '20'), color: ROLE_COLOR[u.role]||'var(--text-3)' }}>
                      {getRoleLabel(u.role, t)}
                    </span>
                  </td>
                  <td className="orgc-td">
                    {managerUser ? (
                      <div className="orgc-row-10">
                        <div className="orgc-row-11" style={{ background: getRoleColor(managerUser.role) }}>
                          {managerUser.full_name?.charAt(0)}
                        </div>
                        <div>
                          <div className="u-text1-sm-600">{managerUser.full_name}</div>
                          <div className="u-text3-xs">{managerUser.job_title||getRoleLabel(managerUser.role, t)}</div>
                        </div>
                      </div>
                    ) : (
                      <span className="orgc-label-6">
                        {t('orgchart.sin_aprobador_asignado')}
                      </span>
                    )}
                  </td>
                  <td className="orgc-td">
                    {isAdmin && (
                      <button onClick={() => setEditing(u)}
                        className="orgc-btn-4">
                        {t('pagina_orgc.editar')}
                      </button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>

        {filtered.length === 0 && (
          <div className="orgc-box-7">
            {t('orgchart.sin_resultados_para_los_filtros_seleccionados')}
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
  const t = useAppT()
  // La cadena de otra persona es para gestores (como en el servidor); el resto ve la suya.
  const puedeVerOtras = useAuth().hasRole('admin', 'pm', 'team_lead', 'hr')
  const [selectedUserId, setSelectedUserId] = useState('')
  const [search, setSearch] = useState('')

  const { data: chain } = useQuery({
    queryKey: ['approval-chain', selectedUserId],
    queryFn: () => (
      selectedUserId
        ? usersApi.approvalChain(selectedUserId)
        : usersApi.myApprovalChain()
    ).then(r => r.data),
    enabled: true,
    staleTime: STALE_LIVE_MS,
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
    <div className="orgc-grid-2">
      {/* Selector de persona */}
      <div className="orgc-card-5">
        <div className="orgc-box-8">
          {t('orgchart.ver_cadena_de_aprobacion')}
        </div>
        {puedeVerOtras && <input aria-label={t('pagina_orgc.buscar_persona_2')} value={search} onChange={e => setSearch(e.target.value)}
          placeholder={t('pagina_orgc.buscar_persona_2')}
          className="orgc-input-2" />}
        <div className="orgc-stack-2">
          <button
            type="button"
            onClick={() => setSelectedUserId('')}
            className={`orgc-btn-5 orgchart-sx9 ${!selectedUserId ? 'orgchart-sx10' : 'orgchart-sx11'}`}>
            {t('pagina_orgc.mi_propia_cadena')}
          </button>
          {puedeVerOtras && filteredUsers.map(u => (
            <button key={u.id}
              type="button"
              onClick={() => setSelectedUserId(u.id)}
              className={`orgc-btn-6 orgchart-sx9 ${selectedUserId===u.id ? 'orgchart-sx12' : 'orgchart-sx13'}`}>
              <div className="orgc-box-9">{u.full_name}</div>
              <div className="u-text3-xs">
                {u.job_title || getRoleLabel(u.role, t)}{u.department ? ` · ${u.department}` : ''}
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Resultado de la cadena */}
      <div>
        {chain ? (
          <div className="u-stack-16">
            {/* Usuario */}
            <div className="orgc-card-6">
              <div className="orgc-box-10">
                {t('pagina_orgc.empleado')}
              </div>
              <div className="u-row-center-12">
                <div className="orgc-row-12">
                  {chain.user_name?.charAt(0)}
                </div>
                <div>
                  <div className="orgc-box-11">{chain.user_name}</div>
                  <div className="u-text3-sm">
                    {selectedUser?.job_title || ''} {selectedUser?.department ? `· ${selectedUser.department}` : ''}
                  </div>
                </div>
              </div>
            </div>

            {/* Lo que se aprueba */}
            <div className="orgc-card-6">
              <div className="orgc-box-12">
                {t('orgchart.que_necesita_aprobacion')}
              </div>
              <div className="orgc-grid-3">
                {[
                  { icon:'💸', label:t('pagina_orgc.gastos'), desc:t('pagina_orgc.cada_gasto_enviado_requiere_aprobacion_del') },
                  { icon:'🏖', label:t('pagina_orgc.ausencias'), desc:t('pagina_orgc.vacaciones_bajas_y_permisos_requieren_aprobacion') },
                  { icon:'⏱', label:t('pagina_orgc.timesheets'), desc:t('pagina_orgc.los_timesheets_semanales_requieren_validacion_del') },
                ].map(item => (
                  <div key={item.label} className="orgc-card-7">
                    <div className="orgc-box-13">{item.icon}</div>
                    <div className="orgc-box-14">{item.label}</div>
                    <div className="orgc-box-15">{item.desc}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Cadena de aprobación */}
            <div className="orgc-card-6">
              <div className="orgc-box-12">
                {t('orgchart.cadena_de_aprobacion')}
              </div>

              {chain.chain.length === 0 ? (
                <div className="orgc-card-8">
                  <div className="orgc-box-16">
                    {t('orgchart.sin_aprobador_configurado')}
                  </div>
                  <div className="orgc-box-17">
                    {chain.user_name} {t('orgchart.no_tiene_manager_asignado_sus_gastos_ausencias')} <strong>{t('pagina_orgc.posiciones')}</strong> {t('orgchart.para_configurarlo')}
                  </div>
                </div>
              ) : (
                <div>
                  {/* Flecha visual de la cadena */}
                  <div className="orgc-stack-3">
                    {chain.chain.map((approver, idx) => {
                      const _approverFull = allUsers.find(u => u.id === approver.id)
                      return (
                        <div key={approver.id}>
                          {/* Flecha */}
                          <div className="orgc-row-13">
                            <div className="orgc-box-18" />
                            <span className="u-text3-xs">
                              {idx === 0 ? t('pagina_orgc.aprobacion_directa') : t('pagina_orgc.escalado_nivel', { v1: idx+1 })}
                            </span>
                          </div>
                          {/* Aprobador */}
                          <div className={`orgc-row-14 orgchart-sx14 ${idx===0 ? 'orgchart-sx15' : 'orgchart-sx16'}`} style={{ border: `1px solid ${idx===0 ? 'var(--success-border)' : 'var(--surface-4)'}` }}>
                            <div className="orgc-row-15" style={{ background: getRoleColor(approver.role) }}>
                              {approver.full_name?.charAt(0)}
                            </div>
                            <div className="u-flex1">
                              <div className="u-row-center-8">
                                <span className="orgc-label-7">
                                  {approver.full_name}
                                </span>
                                {idx === 0 && (
                                  <span className="orgc-card-9">{t('pagina_orgc.aprobador_directo')}</span>
                                )}
                              </div>
                              <div className="u-text3-sm">
                                {approver.job_title || getRoleLabel(approver.role, t)}
                                {approver.department ? ` · ${approver.department}` : ''}
                              </div>
                            </div>
                            <div className="orgc-stack-4">
                              {[t('pagina_orgc.gastos_2'),t('pagina_orgc.ausencias_2'),t('pagina_orgc.timesheets_2')].map(lbl => (
                                <span key={lbl} className="orgc-card-10">{lbl}</span>
                              ))}
                            </div>
                          </div>
                        </div>
                      )
                    })}
                  </div>

                  <div className="orgc-card-11">
                    💡 <strong>{chain.chain[0]?.full_name}</strong> {t('orgchart.es_el_aprobador_directo_si_no_responde')}
                  </div>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="orgc-row-16"><Spinner /></div>
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
    staleTime: STALE_SHORT_MS,
  })

  const { data: allUsers = [] } = useQuery<OrgUser[]>({
    queryKey: ['users'],
    queryFn: () => usersApi.list().then(r => r.data),
    staleTime: STALE_SHORT_MS,
  })

  const nodes: OrgUser[] = chartData?.nodes || []
  const total = chartData?.total || 0

  const TABS = [
    { id:'arbol',       label:t('pagina_orgc.arbol_jerarquico'),      desc:t('pagina_orgc.vista_visual_del_organigrama') },
    { id:'posiciones',  label:t('pagina_orgc.posiciones'),             desc:t('pagina_orgc.editar_cargo_depto_y_manager_de') },
    { id:'aprobaciones',label:t('pagina_orgc.cadenas_de_aprobacion'),  desc:t('pagina_orgc.quien_aprueba_que_para_quien') },
  ]

  return (
    <PageShell>
      <PageHeader
        icon={<Network size={18} />}
        title={t('pagina_orgc.organigrama')}
        subtitle={t('org_chart.subtitle', { total })}
        showListExport={tab !== 'arbol'}
      />

      {/* Tabs */}
      <div className="orgc-row-17">
        {TABS.map(tabObj => (
          <button key={tabObj.id} onClick={() => setTab(tabObj.id)} className={`orgc-btn-7 orgchart-sx17 ${tab===tabObj.id ? 'orgchart-sx18' : 'orgchart-sx19'}`} style={{ border:`1px solid ${tab===tabObj.id ? 'var(--accent)' : 'var(--surface-4)'}` }} title={tabObj.desc}>{tabObj.label}</button>
        ))}
      </div>

      {/* Contenido */}
      {loadingChart && tab === 'arbol'
        ? <div className="orgc-box-19"><Spinner /></div>
        : tab === 'arbol'
          ? <ArbolTab nodes={nodes} allUsers={allUsers} isAdmin={isAdmin} />
          : tab === 'posiciones'
            ? <PosicionesTab allUsers={allUsers} isAdmin={isAdmin} />
            : <AprobacionesTab allUsers={allUsers} />
      }
    </PageShell>
  )
}

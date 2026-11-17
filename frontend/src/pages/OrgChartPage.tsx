/**
 * OrgChartPage — Organigrama, posiciones y cadenas de aprobación
 *
 * Pestaña 1 — Árbol: visualización jerárquica con edición inline
 * Pestaña 2 — Posiciones: tabla editable de todos los usuarios
 * Pestaña 3 — Aprobaciones: quién aprueba gastos, ausencias e imputaciones
 *
 * 16-11-2026: título = el del menú; subtítulo corregido (decía en inglés
 * "Margin, costs and revenue by project"); pestañas con Tabs del kit (antes
 * botones más grandes propios); tarjetas con Card/Section; iconos lucide en
 * lugar de emojis y símbolos de texto; botones del kit; roles con
 * StatusBadge; tabla de posiciones con DataTable; vacíos con EmptyState;
 * "timesheets"/"manager" en castellano.
 */
import { useState, useMemo, useId } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useToast } from '../context/ToastContext'
import { useAuth } from '../context/AuthContext'
import { usersApi } from '../services/api'
import { settingsApi } from '../services/settingsApi'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import {
  AlertTriangle, Briefcase, Building2, CalendarOff, ChevronDown, ChevronRight, Clock, CornerDownRight,
  GitBranch, Info, Network, Pencil, Receipt, Search, ShieldCheck, Tag, UserRound,
} from 'lucide-react'
import { Button, Card, DataTable, EmptyState, IconButton, Modal, Pulsable, Section, Select, Spinner, Tabs } from '../components/ui'
import StatusBadge from '../components/ui/StatusBadge'
import { extractErr } from '../utils/helpers'
import { useAppT } from '../i18n/AppLangContext'
import { STALE_LIVE_MS, STALE_SHORT_MS } from '../constants/timings'
import './OrgChartPage.css'
import { px } from '../utils/estilos'

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

function RolBadge({ role }: { role: string }) {
  const t = useAppT()
  return <StatusBadge color={getRoleColor(role)} caps={false}>{getRoleLabel(role, t)}</StatusBadge>
}

/** Inicial con el color del rol. */
function Inicial({ nombre, role, grande = false }: { nombre?: string; role: string; grande?: boolean }) {
  return (
    <span className={`orgc-inicial${grande ? ' orgc-inicial--grande' : ''}`} style={{ '--orgc-color': getRoleColor(role) } as CSSProperties} aria-hidden>
      {nombre?.charAt(0)?.toUpperCase()}
    </span>
  )
}

/** Título de sección con icono lucide. */
const Titulo = ({ icon, children }: { icon: ReactNode; children: ReactNode }) => (
  <span className="orgc-titulo">{icon}{children}</span>
)

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
        <div className="orgc-ficha">
          <Inicial nombre={user.full_name} role={user.role} />
          <div className="u-flex1-min0">
            <div className="orgc-ficha__nombre">{user.full_name}</div>
            <div className="orgc-ficha__meta">
              {user.email && <span>{user.email}</span>}
              <RolBadge role={user.role} />
            </div>
          </div>
        </div>

        <div className="ds-field">
          <label htmlFor={`${idCampo}-1`} className="ds-field__label">{t('pagina_orgc.cargo_puesto')}</label>
          <input id={`${idCampo}-1`} value={jobTitle} onChange={e => setJobTitle(e.target.value)} className="ds-input"
            placeholder={t('pagina_orgc.ej_desarrollador_senior')} />
        </div>
        <div className="ds-field">
          <label htmlFor={`${idCampo}-2`} className="ds-field__label">{t('pagina_orgc.departamento')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-2`} value={department} onChange={e => setDepartment(e.target.value)}>
            <option value="">{t('orgchart.sin_departamento')}</option>
            {departments.filter(d => d.is_active !== false).map(d => <option key={d.id} value={d.name}>{d.name}</option>)}
          </Select>
        </div>
        <div className="ds-field">
          <label htmlFor={`${idCampo}-3`} className="ds-field__label">{t('pagina_orgc.reporta_a_aprobador_directo')}</label>
          <div className="orgc-ayuda">
            {t('orgchart.esta_persona_aprobara_los')} <strong>{t('pagina_orgc.gastos_min')}</strong>, <strong>{t('pagina_orgc.ausencias_min')}</strong> {t('pagina_orgc.y')} <strong>{t('pagina_orgc.imputaciones_min')}</strong> {t('orgchart.de')} {user.full_name.split(' ')[0]}.
          </div>
          <Select suelto placeholder={false} id={`${idCampo}-3`} value={managerId} onChange={e => setManagerId(e.target.value)}>
            <option value="">{t('orgchart.sin_manager_nivel_raiz_aprobacion_manual')}</option>
            {eligible.map(u => (
              <option key={u.id} value={u.id}>
                {u.full_name}
                {u.job_title ? ` — ${u.job_title}` : ''}
                {u.department ? ` (${u.department})` : ''}
              </option>
            ))}
          </Select>
        </div>

        <div className="orgc-nota">
          <Info size={14} aria-hidden />
          <span>
            <strong>{t('orgchart.como_funciona_la_aprobacion')}</strong>{' '}{managerId
              ? t('orgchart.aprobacion_con_aprobador', { nombre: user.full_name.split(' ')[0], aprobador: eligible.find(u => u.id === managerId)?.full_name || t('pagina_orgc.su_manager') })
              : t('orgchart.aprobacion_sin_aprobador', { nombre: user.full_name.split(' ')[0] })}
          </span>
        </div>

        <div className="orgc-acciones">
          <Button variant="secondary" onClick={onClose}>{t('pagina_orgc.cancelar')}</Button>
          <Button onClick={handleSave} loading={saving}>{t('orgchart.guardar_posicion')}</Button>
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
  const t = useAppT()
  const [expanded, setExpanded] = useState(depth < 2)
  const hasChildren = (node.children?.length ?? 0) > 0

  return (
    <div>
      <div className={`orgc-nodo${depth === 0 ? ' orgc-nodo--raiz' : ''}`} style={{ '--orgc-sangria': px(depth * 24) } as CSSProperties}>
        {hasChildren
          ? <IconButton ariaLabel={expanded ? t('pagina_orgc.contraer') : t('pagina_orgc.expandir')} aria-expanded={expanded} onClick={() => setExpanded(e => !e)}>
              {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </IconButton>
          : <span className="orgc-nodo__rama" aria-hidden><CornerDownRight size={14} /></span>
        }
        <Inicial nombre={node.full_name} role={node.role} />
        <div className="u-flex1-min0">
          <div className="orgc-nodo__nombre">{node.full_name}</div>
          {(node.job_title || node.department) && (
            <div className="orgc-nodo__meta">
              {[node.job_title, node.department].filter(Boolean).join(' · ')}
            </div>
          )}
        </div>
        <RolBadge role={node.role} />
        {hasChildren && (
          <span className="orgc-nodo__reportes">
            {t((node.children?.length ?? 0) === 1 ? 'pagina_orgc.reportes_uno' : 'pagina_orgc.reportes_otros', { n: node.children?.length ?? 0 })}
          </span>
        )}
        {isAdmin && (
          <Button size="sm" variant="ghost" icon={<Pencil size={13} />} onClick={() => onEdit(node)}>
            {t('pagina_orgc.editar')}
          </Button>
        )}
      </div>
      {expanded && hasChildren && (node.children ?? []).map(child => (
        <UserNode key={child.id} node={child} depth={depth + 1} onEdit={onEdit} isAdmin={isAdmin} />
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
    ).slice(0, 8)
  }, [flatUsers, search])

  const deptCounts = useMemo<Array<[string, number]>>(() => {
    const counts: Record<string, number> = {}
    flatUsers.forEach(u => { if (u.department) counts[u.department] = (counts[u.department] || 0) + 1 })
    return Object.entries(counts).sort((a, b) => b[1] - a[1])
  }, [flatUsers])

  return (
    <div className="orgc-arbol">
      {/* Lateral */}
      <div className="u-stack-14 u-min0">
        <Card>
          <Section title={<Titulo icon={<Search size={15} />}>{t('pagina_orgc.buscar_persona')}</Titulo>}>
            <input aria-label={t('pagina_orgc.buscar_persona_2')} value={search} onChange={e => setSearch(e.target.value)}
              placeholder={t('pagina_orgc.buscar_persona_2')} className="ds-input" />
            {searchResults.length > 0 && (
              <div className="orgc-resultados">
                {searchResults.map(u => (
                  <Pulsable key={u.id} onClick={() => { setSearch(''); setEditing(u) }} className="orgc-resultado">
                    <span className="orgc-resultado__nombre">{u.full_name}</span>
                    <span className="orgc-resultado__meta">{u.job_title || getRoleLabel(u.role, t)}</span>
                  </Pulsable>
                ))}
              </div>
            )}
          </Section>
        </Card>

        {deptCounts.length > 0 && (
          <Card>
            <Section title={<Titulo icon={<Building2 size={15} />}>{t('pagina_orgc.departamentos')}</Titulo>}>
              <ul className="orgc-lista">
                {deptCounts.map(([dept, count]) => (
                  <li key={dept} className="orgc-lista__fila">
                    <span className="u-text1">{dept}</span>
                    <span className="orgc-lista__num">{count}</span>
                  </li>
                ))}
              </ul>
            </Section>
          </Card>
        )}

        <Card>
          <Section title={<Titulo icon={<Tag size={15} />}>{t('pagina_orgc.roles')}</Titulo>}>
            <ul className="orgc-lista">
              {Object.keys(ROLE_COLOR).map(role => (
                <li key={role} className="orgc-lista__fila orgc-lista__fila--rol">
                  <span className="orgc-punto" style={{ '--orgc-color': getRoleColor(role) } as CSSProperties} aria-hidden />
                  <span className="u-text1">{getRoleLabel(role, t)}</span>
                </li>
              ))}
            </ul>
          </Section>
        </Card>
      </div>

      {/* Árbol */}
      <Card>
        {nodes.length === 0
          ? <EmptyState icon={<Network size={28} />} title={t('orgchart.sin_organigrama_configurado')}
              description={isAdmin
                ? t('pagina_orgc.ve_a_la_pestana_posiciones_para')
                : t('pagina_orgc.el_organigrama_aun_no_ha_sido')} />
          : <div className="orgc-arbol__nodos">
              {nodes.map(root => (
                <UserNode key={root.id} node={root} depth={0} onEdit={setEditing} isAdmin={isAdmin} />
              ))}
            </div>
        }
      </Card>

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
    return [...list].sort((a, b) => (a.department || '').localeCompare(b.department || '') || a.full_name.localeCompare(b.full_name))
  }, [allUsers, filterDept, search])

  return (
    <div className="u-stack-14">
      {/* Filtros */}
      <Card>
        <div className="orgc-filtros">
          <input aria-label={t('pagina_orgc.buscar_persona_2')} value={search} onChange={e => setSearch(e.target.value)}
            placeholder={t('pagina_orgc.buscar_persona_2')} className="ds-input orgc-filtros__buscar" />
          <Select suelto placeholder={false} value={filterDept} onChange={e => setFilterDept(e.target.value)} className="orgc-filtros__depto"
            aria-label={t('pagina_orgc.departamento')}>
            <option value="">{t('orgchart.todos_los_departamentos')}</option>
            {depts.map(d => <option key={d} value={d}>{d}</option>)}
          </Select>
          <span className="orgc-filtros__total">{t(filtered.length === 1 ? 'pagina_orgc.personas_uno' : 'pagina_orgc.personas_otros', { n: filtered.length })}</span>
        </div>
      </Card>

      <div data-export-table="org-positions">
        <DataTable<OrgUser>
          data={filtered}
          emptyIcon={<Search size={28} />}
          emptyTitle={t('orgchart.sin_resultados_para_los_filtros_seleccionados')}
          columns={[
            { key: 'full_name', label: t('pagina_orgc.persona'), render: (_v, u) => (
              <div className="orgc-celda-persona">
                <Inicial nombre={u.full_name} role={u.role} />
                <div className="u-min0">
                  <div className="orgc-celda-persona__nombre">{u.full_name}</div>
                  {u.email && <div className="orgc-celda-persona__email">{u.email}</div>}
                </div>
              </div>
            ) },
            { key: 'job_title', label: t('pagina_orgc.cargo'), render: (_v, u) => u.job_title || <span className="orgc-vacio">—</span> },
            { key: 'department', label: t('pagina_orgc.departamento'), render: (_v, u) => u.department || <span className="orgc-vacio">—</span> },
            { key: 'role', label: t('pagina_orgc.rol'), render: (_v, u) => <RolBadge role={u.role} /> },
            { key: 'manager_id', label: t('pagina_orgc.reporta_a_aprobador'), sortable: false, render: (_v, u) => {
              const managerUser = allUsers.find(m => m.id === u.manager_id)
              return managerUser ? (
                <div className="orgc-celda-persona">
                  <Inicial nombre={managerUser.full_name} role={managerUser.role} />
                  <div className="u-min0">
                    <div className="orgc-celda-persona__nombre">{managerUser.full_name}</div>
                    <div className="orgc-celda-persona__email">{managerUser.job_title || getRoleLabel(managerUser.role, t)}</div>
                  </div>
                </div>
              ) : (
                <span className="orgc-sin-aprobador"><AlertTriangle size={13} aria-hidden />{t('orgchart.sin_aprobador_asignado')}</span>
              )
            } },
            { key: 'acciones', label: '', sortable: false, render: (_v, u) => isAdmin ? (
              <Button size="sm" variant="ghost" icon={<Pencil size={13} />} onClick={() => setEditing(u)}>{t('pagina_orgc.editar')}</Button>
            ) : null },
          ]}
        />
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
    if (!search.trim()) return allUsers.slice(0, 15)
    const q = search.toLowerCase()
    return allUsers.filter(u =>
      u.full_name?.toLowerCase().includes(q) || u.department?.toLowerCase().includes(q)
    ).slice(0, 12)
  }, [allUsers, search])

  const selectedUser = allUsers.find(u => u.id === selectedUserId)
  const tipos = [
    { icon: <Receipt size={18} />, label: t('pagina_orgc.gastos'), desc: t('pagina_orgc.cada_gasto_enviado_requiere_aprobacion_del') },
    { icon: <CalendarOff size={18} />, label: t('pagina_orgc.ausencias'), desc: t('pagina_orgc.vacaciones_bajas_y_permisos_requieren_aprobacion') },
    { icon: <Clock size={18} />, label: t('pagina_orgc.timesheets'), desc: t('pagina_orgc.los_timesheets_semanales_requieren_validacion_del') },
  ]

  return (
    <div className="orgc-aprob">
      {/* Selector de persona */}
      <Card>
        <Section title={<Titulo icon={<UserRound size={15} />}>{t('orgchart.ver_cadena_de_aprobacion')}</Titulo>}>
          {puedeVerOtras && <input aria-label={t('pagina_orgc.buscar_persona_2')} value={search} onChange={e => setSearch(e.target.value)}
            placeholder={t('pagina_orgc.buscar_persona_2')} className="ds-input orgc-aprob__buscar" />}
          <div className="orgc-aprob__personas">
            <Pulsable onClick={() => setSelectedUserId('')} aria-pressed={!selectedUserId}
              className={`orgc-persona${!selectedUserId ? ' orgc-persona--activa' : ''}`}>
              <span className="orgc-persona__nombre">{t('pagina_orgc.mi_propia_cadena')}</span>
            </Pulsable>
            {puedeVerOtras && filteredUsers.map(u => (
              <Pulsable key={u.id} onClick={() => setSelectedUserId(u.id)} aria-pressed={selectedUserId === u.id}
                className={`orgc-persona${selectedUserId === u.id ? ' orgc-persona--activa' : ''}`}>
                <span className="orgc-persona__nombre">{u.full_name}</span>
                <span className="orgc-persona__meta">
                  {u.job_title || getRoleLabel(u.role, t)}{u.department ? ` · ${u.department}` : ''}
                </span>
              </Pulsable>
            ))}
          </div>
        </Section>
      </Card>

      {/* Resultado de la cadena */}
      <div className="u-min0">
        {chain ? (
          <div className="u-stack-16">
            {/* Persona */}
            <Card>
              <div className="orgc-ficha">
                <span className="orgc-inicial orgc-inicial--grande orgc-inicial--acento" aria-hidden>{chain.user_name?.charAt(0)}</span>
                <div className="u-flex1-min0">
                  <div className="ds-eyebrow">{t('pagina_orgc.empleado')}</div>
                  <div className="orgc-ficha__nombre">{chain.user_name}</div>
                  {(selectedUser?.job_title || selectedUser?.department) && (
                    <div className="orgc-ficha__meta">
                      {[selectedUser?.job_title, selectedUser?.department].filter(Boolean).join(' · ')}
                    </div>
                  )}
                </div>
              </div>
            </Card>

            {/* Lo que se aprueba */}
            <Card>
              <Section title={t('orgchart.que_necesita_aprobacion')}>
                <div className="orgc-tipos">
                  {tipos.map(item => (
                    <div key={item.label} className="orgc-tipo">
                      <span className="orgc-tipo__icono" aria-hidden>{item.icon}</span>
                      <div className="orgc-tipo__titulo">{item.label}</div>
                      <div className="orgc-tipo__desc">{item.desc}</div>
                    </div>
                  ))}
                </div>
              </Section>
            </Card>

            {/* Cadena de aprobación */}
            <Card>
              <Section title={<Titulo icon={<GitBranch size={15} />}>{t('orgchart.cadena_de_aprobacion')}</Titulo>}>
                {chain.chain.length === 0 ? (
                  <div className="orgc-aviso">
                    <AlertTriangle size={16} aria-hidden />
                    <div>
                      <div className="orgc-aviso__titulo">{t('orgchart.sin_aprobador_configurado')}</div>
                      <div className="orgc-aviso__texto">
                        {chain.user_name} {t('orgchart.no_tiene_manager_asignado_sus_gastos_ausencias')} <strong>{t('pagina_orgc.posiciones')}</strong> {t('orgchart.para_configurarlo')}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="u-stack-12">
                    <ol className="orgc-cadena">
                      {chain.chain.map((approver, idx) => (
                        <li key={approver.id} className="orgc-eslabon">
                          <div className="orgc-eslabon__nivel">
                            <span className="orgc-eslabon__linea" aria-hidden />
                            {idx === 0 ? t('pagina_orgc.aprobacion_directa') : t('pagina_orgc.escalado_nivel', { v1: idx + 1 })}
                          </div>
                          <div className={`orgc-eslabon__caja${idx === 0 ? ' orgc-eslabon__caja--directo' : ''}`}>
                            <Inicial nombre={approver.full_name} role={approver.role} grande />
                            <div className="u-flex1-min0">
                              <div className="orgc-eslabon__nombre">
                                <span>{approver.full_name}</span>
                                {idx === 0 && <StatusBadge kind="success">{t('pagina_orgc.aprobador_directo')}</StatusBadge>}
                              </div>
                              <div className="orgc-eslabon__meta">
                                {approver.job_title || getRoleLabel(approver.role, t)}
                                {approver.department ? ` · ${approver.department}` : ''}
                              </div>
                            </div>
                            <div className="orgc-eslabon__tipos">
                              {[t('pagina_orgc.gastos_2'), t('pagina_orgc.ausencias_2'), t('pagina_orgc.timesheets_2')].map(lbl => (
                                <StatusBadge key={lbl} kind="neutral" caps={false}>{lbl}</StatusBadge>
                              ))}
                            </div>
                          </div>
                        </li>
                      ))}
                    </ol>

                    <div className="orgc-nota">
                      <ShieldCheck size={14} aria-hidden />
                      <span><strong>{chain.chain[0]?.full_name}</strong> {t('orgchart.es_el_aprobador_directo_si_no_responde')}</span>
                    </div>
                  </div>
                )}
              </Section>
            </Card>
          </div>
        ) : (
          <Spinner />
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

  return (
    <PageShell>
      <PageHeader
        icon={<Network size={18} />}
        title={t('nav.org_chart')}
        subtitle={t('org_chart.subtitle')}
        showListExport={tab === 'posiciones'}
        exportTargetSelector='[data-export-table="org-positions"]'
        exportFilePrefix='org-positions'
      />

      <div className="u-stack-16">
        <Tabs
          ariaLabel={t('nav.org_chart')}
          active={tab}
          onChange={setTab}
          items={[
            { id: 'arbol',        label: t('pagina_orgc.arbol_jerarquico'),     icon: <Network size={14} /> },
            { id: 'posiciones',   label: t('pagina_orgc.posiciones'),            icon: <Briefcase size={14} /> },
            { id: 'aprobaciones', label: t('pagina_orgc.cadenas_de_aprobacion'), icon: <GitBranch size={14} /> },
          ]}
        />

        {loadingChart && tab === 'arbol'
          ? <Spinner />
          : tab === 'arbol'
            ? <ArbolTab nodes={nodes} allUsers={allUsers} isAdmin={isAdmin} />
            : tab === 'posiciones'
              ? <PosicionesTab allUsers={allUsers} isAdmin={isAdmin} />
              : <AprobacionesTab allUsers={allUsers} />
        }
      </div>
    </PageShell>
  )
}

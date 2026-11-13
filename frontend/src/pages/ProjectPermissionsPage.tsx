import { useState, useId } from 'react'
import type { CSSProperties } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, usersApi, permissionsApi } from '../services/api'
import { Avatar, Button, Spinner, EmptyState, Modal } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { ShieldCheck } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import { alpha } from '../constants/theme'

type IdType = string | number

interface ProjectItem {
  id: IdType
  name?: string
}

interface UserItem {
  id: IdType
  full_name?: string
  role?: string
  job_title?: string
}

interface PermissionItem {
  id: IdType
  user_id: IdType
  level: string
  can_see_financials?: boolean
  can_see_rates?: boolean
  can_export?: boolean
  user?: UserItem
}

interface PermissionFormState {
  user_id: string
  level: string
  can_see_financials: boolean
  can_see_rates: boolean
  can_export: boolean
}

const LEVELS = [
  { value: 'none',    label: 'Sin acceso',  color: 'var(--danger)', desc: 'Bloqueado explícitamente — no puede ver el proyecto' },
  { value: 'viewer',  label: 'Visor',       color: 'var(--text-2)', desc: 'Solo lectura — ve tareas y avance, sin datos financieros' },
  { value: 'member',  label: 'Miembro',     color: 'var(--accent)', desc: 'Puede imputar horas, crear y editar sus tareas' },
  { value: 'manager', label: 'Manager',     color: 'var(--warning)', desc: 'PM-level: edita el proyecto, ve finanzas' },
  { value: 'owner',   label: 'Propietario', color: 'var(--success)', desc: 'Control total incluyendo eliminar' },
]

const panelStyle: CSSProperties = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: '20px 24px' }
const inputStyle: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const labelStyle: CSSProperties = { fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

function PermissionForm({ projectId, users, perm, onClose }: { projectId: string; users: UserItem[]; perm: PermissionItem | null; onClose: () => void }) {
  const idCampo = useId()
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const isEdit = !!perm?.id
  const [form, setForm] = useState<PermissionFormState>({
    user_id:            perm?.user_id ? String(perm.user_id) : '',
    level:              perm?.level              || 'member',
    can_see_financials: perm?.can_see_financials || false,
    can_see_rates:      perm?.can_see_rates      || false,
    can_export:         perm?.can_export         ?? true,
  })
  const set = <K extends keyof PermissionFormState>(k: K) => (v: PermissionFormState[K]) => setForm((f) => ({ ...f, [k]: v }))
  const _selectedLevel = LEVELS.find(l => l.value === form.level)

  const { mutate, isPending } = useMutation({
    mutationFn: (d: PermissionFormState) => isEdit
      ? permissionsApi.update(projectId, perm.id, d).then(r => r.data)
      : permissionsApi.create(projectId, d).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['permissions', projectId] }); onClose() },
    onError: (e: unknown) => toast.error(extractErr(e, 'Error al guardar')),
  })

  return (
    <Modal open onClose={onClose} title={isEdit ? 'Editar permiso' : 'Añadir acceso al proyecto'}>
      <div className="u-stack-16">
        {!isEdit && (
          <div>
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={labelStyle}>Usuario</label>
            <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} style={inputStyle} value={form.user_id} onChange={e => set('user_id')(e.target.value)}>
              <option value="">{t('projectpermissions.selecciona_un_usuario')}</option>
              {users.map(u => <option key={u.id} value={u.id}>{u.full_name} — {u.role}</option>)}
            </select>
          </div>
        )}
        {isEdit && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px', background: 'var(--surface-1)', borderRadius: 8 }}>
            <Avatar name={perm.user?.full_name} size={36} url={undefined} />
            <div>
              <div style={{ fontWeight: 500 }}>{perm.user?.full_name}</div>
              <div className="u-text2-sm">{perm.user?.job_title || perm.user?.role}</div>
            </div>
          </div>
        )}

        <div>
          <label style={labelStyle}>{t('projectpermissions.nivel_de_acceso')}</label>
          <div className="u-stack-6">
            {LEVELS.map(l => (
              <button key={l.value} onClick={() => set('level')(l.value)}
                style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px', borderRadius: 8, border: `1px solid ${form.level === l.value ? alpha(l.color, '50') : 'var(--surface-4)'}`, background: form.level === l.value ? alpha(l.color, '15') : 'transparent', cursor: 'pointer', fontFamily: 'inherit', textAlign: 'left' }}>
                <div style={{ width: 10, height: 10, borderRadius: '50%', background: l.color, flexShrink: 0 }} />
                <div className="u-flex1">
                  <div style={{ fontSize: "var(--text-base)", fontWeight: form.level === l.value ? 600 : 400, color: form.level === l.value ? l.color : 'var(--text-1)' }}>{l.label}</div>
                  <div className="u-text2-xs">{l.desc}</div>
                </div>
                {form.level === l.value && <span style={{ color: l.color }}>✓</span>}
              </button>
            ))}
          </div>
        </div>

        {['member','manager','owner'].includes(form.level) && (
          <div style={{ padding: '14px', background: 'var(--surface-1)', borderRadius: 8, border: '1px solid var(--surface-4)' }}>
            <div style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 10 }}>Permisos adicionales</div>
            <div className="u-stack-8">
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: "var(--text-base)" }}>
                <input type="checkbox" checked={form.can_see_financials} onChange={e => set('can_see_financials')(e.target.checked)} />
                <span>{t('projectpermissions.ver_datos_financieros_costes_presupuesto_facturacion')}</span>
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: "var(--text-base)" }}>
                <input type="checkbox" checked={form.can_see_rates} onChange={e => set('can_see_rates')(e.target.checked)} />
                <span>{t('projectpermissions.ver_tarifas_hora_de_los_companeros')}</span>
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: "var(--text-base)" }}>
                <input type="checkbox" checked={form.can_export} onChange={e => set('can_export')(e.target.checked)} />
                <span>{t('projectpermissions.exportar_datos_del_proyecto')}</span>
              </label>
            </div>
          </div>
        )}

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 4 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => mutate(form)} disabled={isPending || (!isEdit && !form.user_id)} loading={isPending}>
            {isPending ? 'Guardando...' : isEdit ? 'Actualizar permiso' : 'Conceder acceso'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export default function ProjectPermissionsPage() {
  const idCampo = useId()
  const t = useAppT()
  const _t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [selectedProject, setSelectedProject] = useState<string>('')
  const [showForm, setShowForm] = useState(false)
  const [editingPerm, setEditingPerm] = useState<PermissionItem | null>(null)

  const { data: projectsRaw = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list({}).then(r => Array.isArray(r.data) ? r.data : []).catch(() => []),
  })
  const projects = projectsRaw as ProjectItem[]

  const { data: allUsersRaw = [] } = useQuery({
    queryKey: ['users'],
    queryFn: () => usersApi.list({ page_size: 500 }).then(r => Array.isArray(r.data) ? r.data : []).catch(() => []),
  })
  const allUsers = allUsersRaw as UserItem[]

  const { data: permsRaw = [], isLoading } = useQuery({
    queryKey: ['permissions', selectedProject],
    queryFn: () => permissionsApi.list(selectedProject).then(r => r.data).catch(() => []),
    enabled: !!selectedProject,
  })
  const perms = permsRaw as PermissionItem[]

  const { mutate: revoke } = useMutation({
    mutationFn: (pid: IdType) => permissionsApi.delete(selectedProject, pid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['permissions', selectedProject] }),
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const selectedProj = projects.find((p) => String(p.id) === selectedProject)
  const assignedUserIds = new Set(perms.map(p => p.user_id))
  const availableUsers = allUsers.filter(u => !assignedUserIds.has(u.id))

  const byLevel = Object.fromEntries(LEVELS.map(l => [l.value, perms.filter(p => p.level === l.value)]))

  return (
    <PageShell>
      <PageHeader
        icon={<ShieldCheck size={18} />}
        title={t('projectpermissions.permisos_de_proyecto')}
        subtitle={_t('project_permissions.subtitle')}
        actions={selectedProject && (
          <Button onClick={() => { setEditingPerm(null); setShowForm(true) }}>{t('projectpermissions.anadir_acceso')}</Button>
        )}
      />

      {/* Selector de proyecto */}
      <div style={{ ...panelStyle, marginBottom: 24 }}>
        <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={labelStyle}>Proyecto</label>
        <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={selectedProject} onChange={e => setSelectedProject(e.target.value)}
          style={{ ...inputStyle, width: 360 }}>
          <option value="">{t('projectpermissions.selecciona_un_proyecto')}</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        {selectedProject && (
          <div style={{ marginTop: 10, fontSize: "var(--text-sm)", color: 'var(--text-3)' }}>
            {t('projectpermissions.los_permisos_de_proyecto_sobrescriben_el_rol')}
          </div>
        )}
      </div>

      {!selectedProject && (
        <EmptyState icon="🔐" title={t('projectpermissions.selecciona_un_proyecto_2')} description="Elige un proyecto para ver y gestionar sus permisos de acceso" />
      )}

      {selectedProject && isLoading && <Spinner />}

      {selectedProject && !isLoading && perms.length === 0 && (
        <div style={{ ...panelStyle, textAlign: 'center', padding: '48px 24px' }}>
          <div className="u-empty-icon">🔓</div>
          <div style={{ fontSize: "var(--text-md-em)", fontWeight: 600, marginBottom: 8 }}>{t('projectpermissions.sin_permisos_especificos')}</div>
          <div className="u-text2-base-mb20">
            {t('projectpermissions.todos_los_usuarios_con_rol_pm_o')}<br />
            {t('projectpermissions.anade_permisos_especificos_para_restringir_o_ampliar')}
          </div>
          <Button onClick={() => { setEditingPerm(null); setShowForm(true) }}>{t('projectpermissions.anadir_primer_permiso')}</Button>
        </div>
      )}

      {selectedProject && perms.length > 0 && (
        <div>
          {/* Resumen */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 10, marginBottom: 20 }}>
            {LEVELS.map(l => (
              <div key={l.value} style={{ background: 'var(--surface-2)', border: `1px solid ${byLevel[l.value]?.length > 0 ? alpha(l.color, '40') : 'var(--surface-4)'}`, borderRadius: 'var(--radius-md)', padding: '12px 14px' }}>
                <div style={{ fontSize: "var(--text-xl)", fontWeight: 700, color: l.color }}>{byLevel[l.value]?.length || 0}</div>
                <div className="u-text2-xs-mt2">{l.label}</div>
              </div>
            ))}
          </div>

          {/* Tabla de permisos */}
          <div style={panelStyle}>
            <div style={{ fontSize: "var(--text-md)", fontWeight: 600, marginBottom: 16 }}>
              {perms.length} {perms.length === 1 ? 'permiso' : 'permisos'} — {selectedProj?.name}
            </div>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: "var(--text-base)" }}>
              <thead>
                <tr className="u-border-b">
                  {['Usuario', 'Nivel de acceso', 'Finanzas', 'Tarifas', 'Exportar', 'Acciones'].map(h => (
                    <th key={h} style={{ textAlign: 'left', padding: '8px 12px', fontSize: "var(--text-xs)", color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {perms.map((perm, i) => {
                  const level = LEVELS.find(l => l.value === perm.level)
                  return (
                    <tr key={perm.id} style={{ borderBottom: '1px solid var(--surface-4)', background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.03)' }}>
                      <td className="u-pad-10-12">
                        <div className="u-row-center-10">
                          <Avatar name={perm.user?.full_name} size={30} url={undefined} />
                          <div>
                            <div style={{ fontWeight: 500 }}>{perm.user?.full_name || perm.user_id}</div>
                            <div className="u-text2-xs">{perm.user?.job_title || perm.user?.role}</div>
                          </div>
                        </div>
                      </td>
                      <td className="u-pad-10-12">
                        <span style={{ fontSize: "var(--text-sm)", padding: '3px 10px', borderRadius: 'var(--radius-sm)', background: alpha((level?.color || 'var(--text-2)'), '20'), color: level?.color || 'var(--text-2)', fontWeight: 500 }}>
                          {level?.label || perm.level}
                        </span>
                      </td>
                      {[perm.can_see_financials, perm.can_see_rates, perm.can_export].map((v, idx) => (
                        <td key={idx} className="u-pad-10-12">
                          <span style={{ color: v ? 'var(--success)' : 'var(--danger)', fontSize: "var(--text-lg)" }}>{v ? '✓' : '✕'}</span>
                        </td>
                      ))}
                      <td className="u-pad-10-12">
                        <div className="u-row-8">
                          <button onClick={() => { setEditingPerm(perm); setShowForm(true) }}
                            style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)', padding: '4px 10px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>
                            Editar
                          </button>
                          <button onClick={() => { openConfirmGlobal({ message: `¿Revocar acceso de ${perm.user?.full_name}?`, onConfirm: () => revoke(perm.id), danger: true }) }}
                            style={{ background: 'none', border: '1px solid var(--danger-border)', borderRadius: 'var(--radius-sm)', padding: '4px 10px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>
                            Revocar
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {/* Leyenda de niveles */}
          <div style={{ ...panelStyle, marginTop: 16 }}>
            <div style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 12 }}>{t('projectpermissions.niveles_de_acceso')}</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 10 }}>
              {LEVELS.map(l => (
                <div key={l.value}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                    <div style={{ width: 8, height: 8, borderRadius: '50%', background: l.color }} />
                    <span style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: l.color }}>{l.label}</span>
                  </div>
                  <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', lineHeight: 1.4 }}>{l.desc}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {showForm && (
        <PermissionForm
          projectId={selectedProject}
          users={availableUsers}
          perm={editingPerm}
          onClose={() => { setShowForm(false); setEditingPerm(null) }}
        />
      )}
    </PageShell>
  )
}

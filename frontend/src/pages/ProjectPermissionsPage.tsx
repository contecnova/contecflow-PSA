import { useState, useId } from 'react'
import type { CSSProperties } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, usersApi, permissionsApi } from '../services/api'
import type { PermisoDeProyecto } from '../services/api/tipos-plataforma'
import { Avatar, Button, Spinner, EmptyState, Modal } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { ShieldCheck } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import { alpha } from '../constants/theme'
import { FULL_LIST_SIZE } from '../constants/pagination'
import './ProjectPermissionsPage.css'

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

interface PermissionFormState {
  user_id: string
  level: string
  can_see_financials: boolean
  can_see_rates: boolean
  can_export: boolean
}

const LEVELS = [
  { value: 'none',    label: 'permisos_proyecto_ui.nivel_none', color: 'var(--danger)', desc: 'permisos_proyecto_ui.nivel_none_desc' },
  { value: 'viewer',  label: 'permisos_proyecto_ui.nivel_viewer', color: 'var(--text-2)', desc: 'permisos_proyecto_ui.nivel_viewer_desc' },
  { value: 'member',  label: 'permisos_proyecto_ui.nivel_member', color: 'var(--accent)', desc: 'permisos_proyecto_ui.nivel_member_desc' },
  { value: 'manager', label: 'permisos_proyecto_ui.nivel_manager', color: 'var(--warning)', desc: 'permisos_proyecto_ui.nivel_manager_desc' },
  { value: 'owner',   label: 'permisos_proyecto_ui.nivel_owner', color: 'var(--success)', desc: 'permisos_proyecto_ui.nivel_owner_desc' },
]


function PermissionForm({ projectId, users, perm, onClose }: { projectId: string; users: UserItem[]; perm: PermisoDeProyecto | null; onClose: () => void }) {
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
    onError: (e: unknown) => toast.error(extractErr(e, t('permisos_proyecto_ui.error_guardar'))),
  })

  return (
    <Modal open onClose={onClose} title={isEdit ? t('permisos_proyecto_ui.editar_permiso') : t('permisos_proyecto_ui.anadir_acceso')}>
      <div className="u-stack-16">
        {!isEdit && (
          <div>
            <label className="pperm-label-style" id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`}>{t('permisos_proyecto_ui.usuario')}</label>
            <select className="pperm-input-style" id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.user_id} onChange={e => set('user_id')(e.target.value)}>
              <option value="">{t('projectpermissions.selecciona_un_usuario')}</option>
              {users.map(u => <option key={u.id} value={u.id}>{u.full_name} — {u.role}</option>)}
            </select>
          </div>
        )}
        {isEdit && (
          <div className="pperm-row">
            <Avatar name={perm.user?.full_name} size={36} url={undefined} />
            <div>
              <div className="pperm-text">{perm.user?.full_name}</div>
              <div className="u-text2-sm">{perm.user?.job_title || perm.user?.role}</div>
            </div>
          </div>
        )}

        <div>
          <label className="pperm-label-style">{t('projectpermissions.nivel_de_acceso')}</label>
          <div className="u-stack-6">
            {LEVELS.map(l => (
              <button className="pperm-btn" type="button" aria-pressed={form.level === l.value} key={l.value} onClick={() => set('level')(l.value)}
                style={{ '--pperm-btn-border': `1px solid ${form.level === l.value ? alpha(l.color, '50') : 'var(--surface-4)'}`, '--pperm-btn-background': form.level === l.value ? alpha(l.color, '15') : 'transparent' } as CSSProperties}>
                <div className="pperm-box pperm-box-4" style={{ '--pperm-box-4-background': l.color } as CSSProperties} />
                <div className="u-flex1">
                  <div className="pperm-text-base" style={{ '--pperm-text-base-font-weight': form.level === l.value ? '600' : '400', '--pperm-text-base-color': form.level === l.value ? l.color : 'var(--text-1)' } as CSSProperties}>{t(l.label)}</div>
                  <div className="u-text2-xs">{t(l.desc)}</div>
                </div>
                {form.level === l.value && <span className="pperm-text-4" style={{ '--pperm-text-4-color': l.color } as CSSProperties}>✓</span>}
              </button>
            ))}
          </div>
        </div>

        {['member','manager','owner'].includes(form.level) && (
          <div className="pperm-card">
            <div className="pperm-text-muted-sm">{t('permisos_proyecto_ui.permisos_adicionales')}</div>
            <div className="u-stack-8">
              <label className="u-row-center-8-pointer">
                <input type="checkbox" aria-label={t('projectpermissions.ver_datos_financieros_costes_presupuesto_facturacion')} checked={form.can_see_financials} onChange={e => set('can_see_financials')(e.target.checked)} />
                <span>{t('projectpermissions.ver_datos_financieros_costes_presupuesto_facturacion')}</span>
              </label>
              <label className="u-row-center-8-pointer">
                <input type="checkbox" aria-label={t('projectpermissions.ver_tarifas_hora_de_los_companeros')} checked={form.can_see_rates} onChange={e => set('can_see_rates')(e.target.checked)} />
                <span>{t('projectpermissions.ver_tarifas_hora_de_los_companeros')}</span>
              </label>
              <label className="u-row-center-8-pointer">
                <input type="checkbox" aria-label={t('projectpermissions.exportar_datos_del_proyecto')} checked={form.can_export} onChange={e => set('can_export')(e.target.checked)} />
                <span>{t('projectpermissions.exportar_datos_del_proyecto')}</span>
              </label>
            </div>
          </div>
        )}

        <div className="pperm-row-2">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => mutate(form)} disabled={isPending || (!isEdit && !form.user_id)} loading={isPending}>
            {isPending ? t('permisos_proyecto_ui.guardando') : isEdit ? t('permisos_proyecto_ui.actualizar_permiso') : t('permisos_proyecto_ui.conceder_acceso')}
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
  const [editingPerm, setEditingPerm] = useState<PermisoDeProyecto | null>(null)

  const { data: projectsRaw = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list({}).then(r => Array.isArray(r.data) ? r.data : []).catch(() => []),
  })
  const projects = projectsRaw as ProjectItem[]

  const { data: allUsersRaw = [] } = useQuery({
    queryKey: ['users'],
    queryFn: () => usersApi.list({ page_size: FULL_LIST_SIZE }).then(r => Array.isArray(r.data) ? r.data : []).catch(() => []),
  })
  const allUsers = allUsersRaw as UserItem[]

  const { data: perms = [], isLoading } = useQuery({
    queryKey: ['permissions', selectedProject],
    queryFn: () => permissionsApi.list(selectedProject).then(r => r.data).catch((): PermisoDeProyecto[] => []),
    enabled: !!selectedProject,
  })

  const { mutate: revoke } = useMutation({
    mutationFn: (pid: IdType) => permissionsApi.delete(selectedProject, pid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['permissions', selectedProject] }),
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const selectedProj = projects.find((p) => String(p.id) === selectedProject)
  const assignedUserIds = new Set<IdType>(perms.map(p => p.user_id))
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
      <div className="pperm-panel-style pperm-text-2">
        <label className="pperm-label-style" id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`}>{t('permisos_proyecto_ui.proyecto')}</label>
        <select className="pperm-input-style pperm-input" id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={selectedProject} onChange={e => setSelectedProject(e.target.value)}>
          <option value="">{t('projectpermissions.selecciona_un_proyecto')}</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        {selectedProject && (
          <div className="pperm-text-muted-sm-2">
            {t('projectpermissions.los_permisos_de_proyecto_sobrescriben_el_rol')}
          </div>
        )}
      </div>

      {!selectedProject && (
        <EmptyState icon="🔐" title={t('projectpermissions.selecciona_un_proyecto_2')} description={t('permisos_proyecto_ui.selecciona_desc')} />
      )}

      {selectedProject && isLoading && <Spinner />}

      {selectedProject && !isLoading && perms.length === 0 && (
        <div className="pperm-panel-style pperm-state">
          <div className="u-empty-icon">🔓</div>
          <div className="pperm-text-md-em">{t('projectpermissions.sin_permisos_especificos')}</div>
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
          <div className="pperm-grid">
            {LEVELS.map(l => (
              <div className="pperm-card-2" key={l.value} style={{ '--pperm-card-2-border': `1px solid ${byLevel[l.value]?.length > 0 ? alpha(l.color, '40') : 'var(--surface-4)'}` } as CSSProperties}>
                <div className="pperm-text-xl-strong pperm-text-5" style={{ '--pperm-text-5-color': l.color } as CSSProperties}>{byLevel[l.value]?.length || 0}</div>
                <div className="u-text2-xs-mt2">{t(l.label)}</div>
              </div>
            ))}
          </div>

          {/* Tabla de permisos */}
          <div className="pperm-panel-style">
            <div className="pperm-text-md">
              {perms.length} {perms.length === 1 ? 'permiso' : 'permisos'} — {selectedProj?.name}
            </div>
            <table className="pperm-table">
              <thead>
                <tr className="u-border-b">
                  {[t('permisos_proyecto_ui.usuario'), t('permisos_proyecto_ui.col_nivel'), t('permisos_proyecto_ui.col_finanzas'), t('permisos_proyecto_ui.col_tarifas'), t('permisos_proyecto_ui.col_exportar'), t('permisos_proyecto_ui.col_acciones')].map(h => (
                    <th className="pperm-th" key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {perms.map((perm, i) => {
                  const level = LEVELS.find(l => l.value === perm.level)
                  return (
                    <tr className="pperm-tr" key={perm.id} style={{ '--pperm-tr-background': i % 2 === 0 ? 'transparent' : 'color-mix(in srgb, var(--text-1) 3%, transparent)' } as CSSProperties}>
                      <td className="u-pad-10-12">
                        <div className="u-row-center-10">
                          <Avatar name={perm.user?.full_name} size={30} url={undefined} />
                          <div>
                            <div className="pperm-text">{perm.user?.full_name || perm.user_id}</div>
                            <div className="u-text2-xs">{perm.user?.job_title || perm.user?.role}</div>
                          </div>
                        </div>
                      </td>
                      <td className="u-pad-10-12">
                        <span className="pperm-box-2 pperm-box-5" style={{ '--pperm-box-5-background': alpha((level?.color || 'var(--text-2)'), '20'), '--pperm-box-5-color': level?.color || 'var(--text-2)' } as CSSProperties}>
                          {level ? t(level.label) : perm.level}
                        </span>
                      </td>
                      {[perm.can_see_financials, perm.can_see_rates, perm.can_export].map((v, idx) => (
                        <td key={idx} className="u-pad-10-12" aria-label={v ? t('common.yes') : t('common.no')}>
                          <span className="pperm-text-lg" style={{ '--pperm-text-lg-color': v ? 'var(--success)' : 'var(--danger)' } as CSSProperties}><span aria-hidden="true">{v ? '✓' : '✕'}</span><span className="u-sr-only">{v ? t('common.yes') : t('common.no')}</span></span>
                        </td>
                      ))}
                      <td className="u-pad-10-12" aria-label={t('permisos_proyecto_ui.col_acciones')}>
                        <div className="u-row-8">
                          <button className="pperm-btn-xs" onClick={() => { setEditingPerm(perm); setShowForm(true) }}>
                            {t('common.edit')}
                          </button>
                          <button className="pperm-btn-danger-xs" onClick={() => { openConfirmGlobal({ message: t('permisos_proyecto_ui.revocar_confirm', { nombre: perm.user?.full_name ?? '' }), onConfirm: () => revoke(perm.id), danger: true }) }}>
                            {t('permisos_proyecto_ui.revocar')}
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
          <div className="pperm-panel-style pperm-text-3">
            <div className="pperm-text-muted-sm-3">{t('projectpermissions.niveles_de_acceso')}</div>
            <div className="pperm-grid-2">
              {LEVELS.map(l => (
                <div key={l.value}>
                  <div className="pperm-row-3">
                    <div className="pperm-box-3 pperm-box-6" style={{ '--pperm-box-6-background': l.color } as CSSProperties} />
                    <span className="pperm-text-sm pperm-text-6" style={{ '--pperm-text-6-color': l.color } as CSSProperties}>{l.label}</span>
                  </div>
                  <div className="pperm-text-muted-xs">{l.desc}</div>
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

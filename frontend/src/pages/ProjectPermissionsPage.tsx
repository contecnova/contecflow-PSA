/**
 * ProjectPermissionsPage — permisos de acceso por proyecto (/project-permissions).
 *
 * 16-11-2026: pasada de diseño. Título del menú; selector de proyecto con el
 * campo del kit dentro de una Card; vacíos con EmptyState e icono lucide
 * (antes emojis en una caja propia); resumen por nivel con KpiCard; nivel con
 * StatusBadge; botones del kit (antes «+ » en el texto y botones propios); la
 * leyenda mostraba la clave interna en vez del nombre del nivel y «permiso/
 * permisos» estaba fijo en castellano; el rol del usuario sale traducido.
 */
import { useState, useId } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, usersApi, permissionsApi } from '../services/api'
import type { PermisoDeProyecto } from '../services/api/tipos-plataforma'
import { Avatar, Button, Card, Spinner, EmptyState, KpiCard, Modal } from '../components/ui'
import StatusBadge from '../components/ui/StatusBadge'
import type { StatusBadgeKind } from '../components/ui/StatusBadge'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { ShieldCheck, ShieldOff, Eye, User, UserCog, Crown, Plus, Pencil, Check, X, FolderLock, Users, Info } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import { etiquetaCodigo } from '../i18n/etiquetaCodigo'
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

const LEVELS: Array<{ value: string; label: string; desc: string; kind: StatusBadgeKind; Icon: LucideIcon }> = [
  { value: 'none',    label: 'permisos_proyecto_ui.nivel_none',    desc: 'permisos_proyecto_ui.nivel_none_desc',    kind: 'danger',  Icon: ShieldOff },
  { value: 'viewer',  label: 'permisos_proyecto_ui.nivel_viewer',  desc: 'permisos_proyecto_ui.nivel_viewer_desc',  kind: 'neutral', Icon: Eye },
  { value: 'member',  label: 'permisos_proyecto_ui.nivel_member',  desc: 'permisos_proyecto_ui.nivel_member_desc',  kind: 'accent',  Icon: User },
  { value: 'manager', label: 'permisos_proyecto_ui.nivel_manager', desc: 'permisos_proyecto_ui.nivel_manager_desc', kind: 'warning', Icon: UserCog },
  { value: 'owner',   label: 'permisos_proyecto_ui.nivel_owner',   desc: 'permisos_proyecto_ui.nivel_owner_desc',   kind: 'success', Icon: Crown },
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
          <div className="ui-field">
            <label className="uiinde-estiloetiqueta" htmlFor={`${idCampo}-1`}>{t('permisos_proyecto_ui.usuario')}</label>
            <select className="ds-input" id={`${idCampo}-1`} value={form.user_id} onChange={e => set('user_id')(e.target.value)}>
              <option value="">{t('projectpermissions.selecciona_un_usuario')}</option>
              {users.map(u => <option key={u.id} value={u.id}>{u.full_name}{u.role ? ` — ${etiquetaCodigo(t, 'rol_usuario', u.role)}` : ''}</option>)}
            </select>
          </div>
        )}
        {isEdit && (
          <div className="pperm-usuario">
            <Avatar name={perm.user?.full_name} size={36} url={undefined} />
            <div className="u-min0">
              <div className="pperm-usuario__nombre">{perm.user?.full_name}</div>
              <div className="u-text2-sm">{perm.user?.job_title || etiquetaCodigo(t, 'rol_usuario', perm.user?.role)}</div>
            </div>
          </div>
        )}

        <div className="ui-field">
          <span className="uiinde-estiloetiqueta" id={`${idCampo}-nivel`}>{t('projectpermissions.nivel_de_acceso')}</span>
          <div className="u-stack-6" role="group" aria-labelledby={`${idCampo}-nivel`}>
            {LEVELS.map(l => {
              const activo = form.level === l.value
              return (
                <button className={`pperm-nivel${activo ? ' pperm-nivel--activo' : ''}`} type="button" aria-pressed={activo} key={l.value} onClick={() => set('level')(l.value)}>
                  <l.Icon size={16} className="pperm-nivel__icono" aria-hidden />
                  <div className="u-flex1-min0">
                    <div className="pperm-nivel__nombre">{t(l.label)}</div>
                    <div className="u-text2-xs">{t(l.desc)}</div>
                  </div>
                  {activo && <Check size={16} className="pperm-nivel__check" aria-hidden />}
                </button>
              )
            })}
          </div>
        </div>

        {['member','manager','owner'].includes(form.level) && (
          <div className="pperm-extra">
            <div className="ds-eyebrow">{t('permisos_proyecto_ui.permisos_adicionales')}</div>
            <div className="u-stack-8">
              <label className="u-row-center-8-pointer">
                <input type="checkbox" checked={form.can_see_financials} onChange={e => set('can_see_financials')(e.target.checked)} />
                <span>{t('projectpermissions.ver_datos_financieros_costes_presupuesto_facturacion')}</span>
              </label>
              <label className="u-row-center-8-pointer">
                <input type="checkbox" checked={form.can_see_rates} onChange={e => set('can_see_rates')(e.target.checked)} />
                <span>{t('projectpermissions.ver_tarifas_hora_de_los_companeros')}</span>
              </label>
              <label className="u-row-center-8-pointer">
                <input type="checkbox" checked={form.can_export} onChange={e => set('can_export')(e.target.checked)} />
                <span>{t('projectpermissions.exportar_datos_del_proyecto')}</span>
              </label>
            </div>
          </div>
        )}

        <div className="pperm-acciones">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button icon={isEdit ? <Check size={14} /> : <Plus size={14} />} onClick={() => mutate(form)} disabled={!isEdit && !form.user_id} loading={isPending}>
            {isPending ? t('permisos_proyecto_ui.guardando') : isEdit ? t('permisos_proyecto_ui.actualizar_permiso') : t('permisos_proyecto_ui.conceder_acceso')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function SiNo({ v }: { v?: boolean }) {
  const t = useAppT()
  return (
    <span className={`pperm-sino${v ? ' pperm-sino--si' : ''}`}>
      {v ? <Check size={15} aria-hidden /> : <X size={15} aria-hidden />}
      <span className="u-sr-only">{v ? t('common.yes') : t('common.no')}</span>
    </span>
  )
}

export default function ProjectPermissionsPage() {
  const idCampo = useId()
  const t = useAppT()
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
  const nuevo = () => { setEditingPerm(null); setShowForm(true) }

  return (
    <PageShell>
      <PageHeader
        icon={<ShieldCheck size={18} />}
        title={t('nav.project_permissions')}
        subtitle={t('project_permissions.subtitle')}
        actions={selectedProject ? (
          <Button icon={<Plus size={14} />} onClick={nuevo}>{t('projectpermissions.anadir_acceso')}</Button>
        ) : undefined}
      />

      <div className="u-stack-16">
      {/* Selector de proyecto */}
      <Card>
        <div className="ui-field pperm-selector">
          <label className="uiinde-estiloetiqueta" htmlFor={`${idCampo}-1`}>{t('permisos_proyecto_ui.proyecto')}</label>
          <select className="ds-input" id={`${idCampo}-1`} value={selectedProject} onChange={e => setSelectedProject(e.target.value)}>
            <option value="">{t('projectpermissions.selecciona_un_proyecto')}</option>
            {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
        {selectedProject && (
          <p className="pperm-ayuda">
            <Info size={14} aria-hidden />
            <span>{t('projectpermissions.los_permisos_de_proyecto_sobrescriben_el_rol')}</span>
          </p>
        )}
      </Card>

      {!selectedProject && (
        <EmptyState icon={<FolderLock size={28} />} title={t('projectpermissions.selecciona_un_proyecto_2')} description={t('permisos_proyecto_ui.selecciona_desc')} />
      )}

      {selectedProject && isLoading && <Spinner />}

      {selectedProject && !isLoading && perms.length === 0 && (
        <EmptyState icon={<Users size={28} />} title={t('projectpermissions.sin_permisos_especificos')}
          description={`${t('projectpermissions.todos_los_usuarios_con_rol_pm_o')} ${t('projectpermissions.anade_permisos_especificos_para_restringir_o_ampliar')}`}
          ctaLabel={t('projectpermissions.anadir_primer_permiso')} onCta={nuevo} />
      )}

      {selectedProject && perms.length > 0 && (
        <>
          {/* Resumen */}
          <div className="ds-grid-stats">
            {LEVELS.map(l => (
              <KpiCard key={l.value} icon={<l.Icon size={16} />} label={t(l.label)} value={byLevel[l.value]?.length || 0} />
            ))}
          </div>

          {/* Tabla de permisos */}
          <Card className="pperm-tabla-card">
            <div className="pperm-tabla-cabecera">
              {t('permisos_proyecto_ui.n_permisos', { n: perms.length, proyecto: selectedProj?.name ?? '' })}
            </div>
            <div className="pperm-tabla-scroll">
            <table className="pperm-table">
              <thead>
                <tr>
                  {[t('permisos_proyecto_ui.usuario'), t('permisos_proyecto_ui.col_nivel'), t('permisos_proyecto_ui.col_finanzas'), t('permisos_proyecto_ui.col_tarifas'), t('permisos_proyecto_ui.col_exportar'), t('permisos_proyecto_ui.col_acciones')].map(h => (
                    <th className="pperm-th" key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {perms.map(perm => {
                  const level = LEVELS.find(l => l.value === perm.level)
                  return (
                    <tr className="pperm-tr" key={perm.id}>
                      <td className="pperm-td">
                        <div className="u-row-center-10">
                          <Avatar name={perm.user?.full_name} size={30} url={undefined} />
                          <div className="u-min0">
                            <div className="pperm-usuario__nombre">{perm.user?.full_name || perm.user_id}</div>
                            <div className="u-text2-xs">{perm.user?.job_title || etiquetaCodigo(t, 'rol_usuario', perm.user?.role)}</div>
                          </div>
                        </div>
                      </td>
                      <td className="pperm-td">
                        <StatusBadge kind={level?.kind ?? 'neutral'} caps={false}>{level ? t(level.label) : perm.level}</StatusBadge>
                      </td>
                      <td className="pperm-td"><SiNo v={perm.can_see_financials} /></td>
                      <td className="pperm-td"><SiNo v={perm.can_see_rates} /></td>
                      <td className="pperm-td"><SiNo v={perm.can_export} /></td>
                      <td className="pperm-td">
                        <div className="u-row-center-6">
                          <Button size="xs" variant="ghost" icon={<Pencil size={12} />} onClick={() => { setEditingPerm(perm); setShowForm(true) }}>
                            {t('common.edit')}
                          </Button>
                          <Button size="xs" variant="danger" onClick={() => { openConfirmGlobal({ message: t('permisos_proyecto_ui.revocar_confirm', { nombre: perm.user?.full_name ?? '' }), onConfirm: () => revoke(perm.id), danger: true }) }}>
                            {t('permisos_proyecto_ui.revocar')}
                          </Button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            </div>
          </Card>

          {/* Leyenda de niveles */}
          <Card>
            <div className="ds-eyebrow">{t('projectpermissions.niveles_de_acceso')}</div>
            <div className="pperm-leyenda">
              {LEVELS.map(l => (
                <div key={l.value} className="u-stack-6">
                  <StatusBadge kind={l.kind} caps={false}><l.Icon size={12} aria-hidden />{t(l.label)}</StatusBadge>
                  <div className="pperm-leyenda__desc">{t(l.desc)}</div>
                </div>
              ))}
            </div>
          </Card>
        </>
      )}
      </div>

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

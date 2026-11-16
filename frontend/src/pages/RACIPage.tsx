/**
 * RACIPage — Matriz de responsabilidades por proyecto (R/A/C/I)
 * Permite definir quién es Responsable, Aprobador, Consultado e Informado
 * para cada entregable, milestone o fase del proyecto.
 *
 * 16-11-2026: pasada de diseño. «Añadir entrada» a la cabecera con icono
 * (antes en el cuerpo y con «+ » en el texto); selector de proyecto en una
 * Card con el campo del kit; vacíos con icono lucide (antes emojis); campos
 * del formulario del kit (antes grises propios); botón crudo `btn-primary`
 * cambiado por Button; tipo con StatusBadge. Dentro de la ficha del proyecto
 * (con `projectId`) ya no repite la cabecera de página.
 */
import { useState, useId } from 'react'
import type { ChangeEvent, CSSProperties, ReactNode } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api, { projectsApi, usersApi } from '../services/api'
import type { PersonaVisible } from '../services/api'
import { Avatar, Spinner, EmptyState, Button, Card, Modal } from '../components/ui'
import StatusBadge from '../components/ui/StatusBadge'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Shield, Plus, X, FolderSearch, Grid3x3 } from 'lucide-react'
import { useToast } from '../context/ToastContext'
import { extractErr } from '../utils/helpers'
import { useAppT } from '../i18n/AppLangContext'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { alpha } from '../constants/theme'
import { STALE_DEFAULT_MS } from '../constants/timings'
import './RACIPage.css'

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

const ROLES_META: Record<string, { label: string; short: string; color: string; bg: string; desc: string }> = {
  R: { label: 'raci_ui.rol_r', short: 'R', color: 'var(--accent)',   bg: 'color-mix(in srgb, var(--accent) 15%, transparent)',  desc: 'raci_ui.rol_r_desc' },
  A: { label: 'raci_ui.rol_a', short: 'A', color: 'var(--success)',  bg: 'color-mix(in srgb, var(--success) 15%, transparent)', desc: 'raci_ui.rol_a_desc' },
  C: { label: 'raci_ui.rol_c', short: 'C', color: 'var(--warning)',  bg: 'color-mix(in srgb, var(--warning) 15%, transparent)', desc: 'raci_ui.rol_c_desc' },
  I: { label: 'raci_ui.rol_i', short: 'I', color: 'var(--text-2)',   bg: 'color-mix(in srgb, var(--text-2) 15%, transparent)', desc: 'raci_ui.rol_i_desc' },
}

const ITEM_TYPES = [
  { value: 'deliverable', label: 'raci_ui.tipo_deliverable' },
  { value: 'milestone',   label: 'raci_ui.tipo_milestone' },
  { value: 'phase',       label: 'raci_ui.tipo_phase' },
  { value: 'custom',      label: 'raci_ui.tipo_custom' },
]

function RoleCell({ role, onClick, editable }: { role?: string; onClick?: () => void; editable: boolean }) {
  const t = useAppT()
  const meta = (role && ROLES_META[role]) || null
  const titulo = meta ? t('raci_ui.rol_titulo', { rol: t(meta.label), desc: t(meta.desc) }) : t('raci_ui.sin_asignar')
  const variables = {
    '--raci-celda-cursor': editable ? 'pointer' : 'default',
    '--raci-celda-fondo': meta ? meta.bg : 'var(--surface-3)',
    '--raci-celda-color': meta ? meta.color : 'var(--text-3)',
    '--raci-celda-borde': `1px solid ${meta ? alpha(meta.color, '40') : 'var(--surface-4)'}`,
  } as CSSProperties

  if (editable) {
    return (
      <button
        type="button"
        className="raci-celda raci-celda--boton"
        onClick={onClick}
        title={titulo}
        aria-label={titulo}
        style={variables}
      >
        {meta ? meta.short : '—'}
      </button>
    )
  }

  return (
    <div
      className="raci-celda"
      title={titulo}
      style={variables}
    >
      {meta ? meta.short : '·'}
    </div>
  )
}

function AddEntryModal({ projectId, users, onClose, onSaved }: { projectId: IdType; users: PersonaVisible[]; onClose: () => void; onSaved: () => void }) {
  const idCampo = useId()
  const traducir = useAppT()
  const t = useAppT()
  const toast = useToast()
  const [form, setForm] = useState({ item_type: 'deliverable', item_label: '', user_id: '', role: 'R' })

  const { mutate: save, isPending } = useMutation({
    mutationFn: () => api.put(`/projects/${projectId}/raci`, {
      entries: [{ item_type: form.item_type, item_label: form.item_label, user_id: form.user_id, role: form.role }]
    }),
    onSuccess: () => { onSaved(); onClose() },
    onError: (e: unknown) => toast.error(extractErr(e, t('raci_ui.error_guardar'))),
  })

  const onField = (key: 'item_type' | 'item_label' | 'user_id' | 'role') => (e: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    setForm((f) => ({ ...f, [key]: e.target.value }))
  }

  return (
    <div className="u-stack-14">
      <div className="raci-grid">
        <div className="ui-field">
          <label className="uiinde-estiloetiqueta" htmlFor={`${idCampo}-1`}>{t('raci_ui.tipo')}</label>
          <select className="ds-input" id={`${idCampo}-1`} value={form.item_type} onChange={onField('item_type')}>
            {ITEM_TYPES.map(it => <option key={it.value} value={it.value}>{t(it.label)}</option>)}
          </select>
        </div>
        <div className="ui-field">
          <label className="uiinde-estiloetiqueta" htmlFor={`${idCampo}-4`}>{traducir('raci.nombre_del_elemento')}</label>
          <input id={`${idCampo}-4`} className="ds-input" value={form.item_label} onChange={onField('item_label')} placeholder={traducir('raci.nombre_del_elemento')} />
        </div>
      </div>
      <div className="raci-grid-2">
        <div className="ui-field">
          <label className="uiinde-estiloetiqueta" htmlFor={`${idCampo}-2`}>{t('raci_ui.persona')}</label>
          <select className="ds-input" id={`${idCampo}-2`} value={form.user_id} onChange={onField('user_id')}>
            <option value="">{t('raci_ui.selecciona_persona')}</option>
            {users.map(u => <option key={u.id} value={u.id}>{u.full_name}{(u.job_title || u.role) ? ` (${u.job_title || u.role})` : ''}</option>)}
          </select>
        </div>
        <div className="ui-field">
          <label className="uiinde-estiloetiqueta" htmlFor={`${idCampo}-3`}>{t('raci_ui.rol_raci')}</label>
          <select className="ds-input" id={`${idCampo}-3`} value={form.role} onChange={onField('role')}>
            {Object.entries(ROLES_META).map(([k, v]) => <option key={k} value={k}>{k} — {t(v.label)}</option>)}
          </select>
        </div>
      </div>
      <div className="u-actions-10">
        <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
        <Button icon={<Plus size={14} />} onClick={() => save()} disabled={!form.item_label || !form.user_id} loading={isPending}>
          {isPending ? t('common.saving') : t('raci_ui.anadir_entrada')}
        </Button>
      </div>
    </div>
  )
}

/** Rev. 173: con `projectId` va dentro de la ficha del proyecto, con el proyecto fijo y sin selector. */
export default function RACIPage({ projectId }: { projectId?: string } = {}) {
  const traducir = useAppT()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [selectedProject, setSelectedProject] = useState<IdType | ''>(projectId ?? '')
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

  // Selector de personas: `/users/directory` (ficha mínima) sirve a cualquier rol; `/users` da 403 al subcontratado.
  const { data: usersData = [] } = useQuery({
    queryKey: ['users', 'directory'],
    queryFn: () => usersApi.directory().then(r => r.data),
    staleTime: STALE_DEFAULT_MS,
  })

  const { mutate: deleteEntry } = useMutation({
    mutationFn: (entryId: IdType) => api.delete(`/projects/${selectedProject}/raci/${entryId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['raci', selectedProject] }),
    onError: (e: unknown) => toast.error(extractErr(e, t('raci_ui.error_eliminar'))),
  })

  // Build matrix: rows = items, columns = unique users
  const items = (raci?.items || []) as RaciItem[]
  const allAssignments = items.flatMap((it) => it.assignments || [])
  const uniqueUsers = [...new Map(allAssignments.map((a) => [a.user_id, a.user])).values()].filter(Boolean) as UserSlim[]

  const botonAnadir = selectedProject ? (
    <Button icon={<Plus size={14} />} onClick={() => setShowAdd(true)}>{traducir('raci.anadir_entrada')}</Button>
  ) : undefined

  const contenido: ReactNode = (
    <div className="u-stack-16">
      {/* Project selector (solo en la página suelta) o acción (dentro de la ficha) */}
      {!projectId ? (
        <Card>
          <div className="ui-field raci-selector">
            <label className="uiinde-estiloetiqueta" htmlFor="raci-proyecto">{t('raci_ui.proyecto')}</label>
            <select id="raci-proyecto" className="ds-input" value={String(selectedProject)} onChange={e => setSelectedProject(e.target.value)}>
              <option value="">{traducir('raci.selecciona_un_proyecto')}</option>
              {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
            </select>
          </div>
        </Card>
      ) : (
        <div className="raci-acciones-ficha">{botonAnadir}</div>
      )}

      {/* Legend */}
      <div className="raci-leyenda">
        {Object.entries(ROLES_META).map(([k, v]) => (
          <div className="raci-leyenda__item" key={k}>
            <span className="raci-leyenda__letra" style={{ '--raci-color': v.color, '--raci-fondo': v.bg } as CSSProperties}>{k}</span>
            <span className="raci-leyenda__nombre">{t(v.label)}</span>
            <span className="raci-leyenda__desc">{t(v.desc)}</span>
          </div>
        ))}
      </div>

      {!selectedProject ? (
        <EmptyState icon={<FolderSearch size={28} />} title={traducir('raci.selecciona_un_proyecto_2')} description={t('raci_ui.selecciona_desc')} />
      ) : isLoading ? (
        <div className="raci-cargando"><Spinner label={t('common.loading')} /></div>
      ) : items.length === 0 ? (
        <EmptyState icon={<Grid3x3 size={28} />} title={t('raci_ui.matriz_vacia')} description={t('raci_ui.matriz_vacia_desc')}
          ctaLabel={traducir('raci.anadir_primera_entrada')} onCta={() => setShowAdd(true)} />
      ) : (
        <div className="ds-card raci-tabla-card u-scroll-x">
          <table className="raci-table">
            <thead>
              <tr>
                <th className="raci-th">{t('raci_ui.elemento')}</th>
                <th className="raci-th-2">{t('raci_ui.tipo')}</th>
                {uniqueUsers.map(u => (
                  <th className="raci-th-3" key={u.id}>
                    <div className="raci-stack">
                      <Avatar name={u.full_name} size={22} url={undefined} />
                      <span className="raci-box">{u.full_name.split(' ')[0]}</span>
                    </div>
                  </th>
                ))}
                <th className="raci-th-4" aria-hidden="true" />
              </tr>
            </thead>
            <tbody>
              {items.map((item, idx) => {
                const assignMap = Object.fromEntries(item.assignments.map((a) => [a.user_id, a])) as Record<string, RaciAssignment>
                return (
                  <tr className="raci-tr" key={idx}>
                    <td className="raci-td-base">{item.item_label}</td>
                    <td className="raci-td">
                      <StatusBadge caps={false}>
                        {(() => { const tipo = ITEM_TYPES.find(it => it.value === item.item_type); return tipo ? t(tipo.label) : item.item_type })()}
                      </StatusBadge>
                    </td>
                    {uniqueUsers.map(u => {
                      const a = assignMap[String(u.id)]
                      return (
                        <td className="raci-td-2" key={u.id}>
                          {a ? (
                            <div className="raci-row-5">
                              <div className="raci-box-2">
                                <RoleCell role={a.role} editable={false} />
                                <button className="raci-btn-3xs" type="button" aria-label={t('raci_ui.quitar')} onClick={() => { openConfirmGlobal({ message: t('raci_ui.quitar_confirm'), onConfirm: () => deleteEntry(a.entry_id), danger: true }) }}
                                  title={t('raci_ui.quitar')}>
                                  <X size={9} aria-hidden />
                                </button>
                              </div>
                            </div>
                          ) : (
                            <div className="raci-box-3" />
                          )}
                        </td>
                      )
                    })}
                    <td className="raci-td-3" aria-hidden="true" />
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )

  const modal = showAdd && (
        <Modal open title={t('raci_ui.anadir_entrada_raci')} onClose={() => setShowAdd(false)} width={560}>
          <AddEntryModal
            projectId={selectedProject}
            users={usersData}
            onClose={() => setShowAdd(false)}
            onSaved={() => qc.invalidateQueries({ queryKey: ['raci', selectedProject] })}
          />
        </Modal>
  )

  // Dentro de la ficha del proyecto la cabecera ya la pone la ficha.
  if (projectId) return <>{contenido}{modal}</>

  return (
    <PageShell>
      <PageHeader title={t('nav.raci')} subtitle={t('raci.subtitle')} icon={<Shield size={18} />} actions={botonAnadir} />
      {contenido}
      {modal}
    </PageShell>
  )
}

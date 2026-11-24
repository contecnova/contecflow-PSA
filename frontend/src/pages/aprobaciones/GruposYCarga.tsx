/**
 * Grupos de aprobadores, carga por aprobador y matriz de aprobación.
 * Troceado de ApprovalsPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import { useId, useState } from 'react'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { extractErr } from '../../utils/helpers'
import { useToast } from '../../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { approvalsApi } from '../../services/api'
import { useListaDeUsuarios } from '../../hooks/useListas'
import { Trash2, Users, Pencil, Plus, AlertTriangle } from 'lucide-react'
import {
  Button,
  Modal,
  EmptyState,
  Table,
  IconButton,
  StatusBadge,
  SelectorDePeriodo,
  TablaSimple,
  Checkbox,
  Input,
} from '../../components/ui'
import { usePeriodo } from '../../hooks/usePeriodo'
import { CON_HORA, codigoDeErrorDePeriodo } from '../../utils/periodo'
import { useAppT } from '../../i18n/AppLangContext'
import { type ApprovalGroup, type ApprovalWorkflow, type ApproverLoadResponse, entityLabels, type GroupForm } from './compartido'

// ── Grupos de aprobadores ─────────────────────────────────────────────────────
export function ApprovalGroupsTab() {
  const idCampo = useId()
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const { data: groups = [], isLoading } = useQuery<ApprovalGroup[]>({
    queryKey: ['approval-groups'],
    queryFn: () => approvalsApi.listGroups().then(r => r.data),
  })
  const { data: users = [] } = useListaDeUsuarios()
  const [showCreate, setShowCreate] = useState(false)
  const [editGroup, setEditGroup] = useState<ApprovalGroup | null>(null)
  const [form, setForm] = useState<GroupForm>({ name: '', description: '', member_ids: [] })

  const { mutate: save, isPending } = useMutation({
    mutationFn: (d: GroupForm) => editGroup ? approvalsApi.updateGroup(editGroup.id, d) : approvalsApi.createGroup(d),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['approval-groups'] }); setShowCreate(false); setEditGroup(null)
      setForm({ name: '', description: '', member_ids: [] })
      toast.success(editGroup ? t('approvals.grupo_actualizado') : t('approvals.grupo_creado'))
    },
    onError: e => toast.error(extractErr(e, t('approvals.error_guardar_grupo'))),
  })
  const { mutate: del } = useMutation({
    mutationFn: approvalsApi.deleteGroup,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['approval-groups'] }); toast.success(t('approvals.grupo_eliminado')) },
    onError: e => toast.error(extractErr(e, t('approvals.error_eliminar_grupo'))),
  })

  const openEdit = (g: ApprovalGroup) => {
    setEditGroup(g)
    setForm({ name: g.name, description: g.description || '', member_ids: g.member_ids || [] })
    setShowCreate(true)
  }

  const toggleMember = (uid: string) => setForm(f => ({
    ...f,
    member_ids: f.member_ids.includes(uid) ? f.member_ids.filter(x => x !== uid) : [...f.member_ids, uid],
  }))

  if (isLoading) return <div className="apv-cargando" role="status">{t('approvals.cargando_grupos')}</div>

  return (
    <div>
      <div className="apv-fin">
        <Button icon={<Plus size={14} />} onClick={() => { setEditGroup(null); setForm({ name: '', description: '', member_ids: [] }); setShowCreate(true) }}>{t('approvals.nuevo_grupo')}</Button>
      </div>
      {groups.length === 0 ? (
        <div className="ds-card">
          <EmptyState icon={<Users size={28} />} title={t('approvals.sin_grupos')} description={t('approvals.sin_grupos_texto')}
            action={<Button icon={<Plus size={14} />} onClick={() => { setEditGroup(null); setForm({ name: '', description: '', member_ids: [] }); setShowCreate(true) }}>{t('approvals.nuevo_grupo')}</Button>} />
        </div>
      ) : (
        <div className="apv-rejilla-tarjetas apv-rejilla-tarjetas--280">
          {groups.map(g => {
            const members = g.member_ids || []
            return (
              <div key={g.id} className="ds-card apv-grupo">
                <div className="apv-grupo__nombre apv-icono-texto"><Users size={14} aria-hidden /> {g.name}</div>
                {g.description && <div className="apv-grupo__descripcion">{g.description}</div>}
                <div className="u-text3-xs">{t('approvals.n_miembros', { n: members.length })}</div>
                <div className="apv-grupo__acciones">
                  <Button size="sm" variant="secondary" icon={<Pencil size={14} />} onClick={() => openEdit(g)}>{t('approvals.editar')}</Button>
                  <IconButton variante="caja" tono="peligro" ariaLabel={t('approvals.eliminar_grupo_aria', { nombre: g.name })}
                    onClick={() => openConfirmGlobal({ message: t('approvals.eliminar_grupo_confirmar', { nombre: g.name }), onConfirm: () => del(g.id), danger: true })}><Trash2 size={14} aria-hidden /></IconButton>
                </div>
              </div>
            )
          })}
        </div>
      )}
      {showCreate && (
        <Modal open title={editGroup ? t('approvals.editar_grupo') : t('approvals.nuevo_grupo_titulo')} onClose={() => { setShowCreate(false); setEditGroup(null) }} width={480}>
          <div className="apv-columna">
            <div>
              <label htmlFor={`${idCampo}-1`} className="apv-label">{t('approvals.name_required')}</label>
              <Input id={`${idCampo}-1`} value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder={t('approvals.ej_comite_financiero')} inputClassName="apv-input" />
            </div>
            <div>
              <label htmlFor={`${idCampo}-2`} className="apv-label">{t('approvals.description')}</label>
              <Input id={`${idCampo}-2`} value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} inputClassName="apv-input" />
            </div>
            <div>
              <div id={`${idCampo}-miembros`} className="apv-label">{t('approvals.miembros')}</div>
              <div role="group" aria-labelledby={`${idCampo}-miembros`} className="apv-miembros">
                {users.map(u => (
                  <label key={u.id} className="apv-miembro">
                    <Checkbox checked={form.member_ids.includes(u.id)} onChange={() => toggleMember(u.id)} />
                    {u.full_name} <span className="u-text3-xs">({t(`pol.rol_${u.role}`, u.role)})</span>
                  </label>
                ))}
              </div>
            </div>
          </div>
          <div className="u-actions-8">
            <Button variant="secondary" onClick={() => { setShowCreate(false); setEditGroup(null) }}>{t('common.cancel')}</Button>
            <Button onClick={() => save(form)} loading={isPending} disabled={!form.name || isPending}>{t('approvals.guardar')}</Button>
          </div>
        </Modal>
      )}
    </div>
  )
}

// ── Carga de aprobadores ──────────────────────────────────────────────────────
export function ApproverLoadTab() {
  const t = useAppT()
  // Periodo libre (16-11-2026): antes 30/60/90/180 días propios. Prefijo propio:
  // otra pestaña de la pantalla tiene su periodo.
  const periodo = usePeriodo({ defecto: '90d', granularidades: CON_HORA, prefijo: 'carga_' })
  const { data, isLoading, error } = useQuery<ApproverLoadResponse>({
    queryKey: ['approver-load', periodo.params],
    queryFn: () => approvalsApi.approverLoad({ ...periodo.params }).then(r => r.data),
  })
  const errorDePeriodo = codigoDeErrorDePeriodo(error)

  return (
    <div>
      <div className="ds-card apv-barra">
        <span className="u-text2-sm">{t('approvals.periodo')}</span>
        <SelectorDePeriodo {...periodo.selector} sinGranularidad />
      </div>
      {isLoading ? (
        <div className="apv-cargando" role="status">{t('approvals.cargando_carga_de_aprobadores')}</div>
      ) : errorDePeriodo ? (
        <div className="ds-card">
          <EmptyState icon={<AlertTriangle size={28} />} title={t(`periodo_err.${errorDePeriodo.motivo}`, errorDePeriodo.params)} />
        </div>
      ) : !data ? null : (
        <>
          {(data.overloaded_approvers || []).length > 0 && (
            <div className="apv-alerta" role="alert">
              <strong className="u-danger apv-icono-texto"><AlertTriangle size={14} aria-hidden /> {t('approvals.aprobadores_sobrecargados')}</strong>
              <span className="apv-alerta__lista">{data.overloaded_approvers.map(a => a.user_name).join(', ')}</span>
            </div>
          )}
          <div className="u-scroll-x">
            <Table
              data={data.items || []}
              columns={[
                { key: 'user_name', label: t('approvals.aprobador'), render: (_v, row) => <span className="u-600">{row.user_name}</span> },
                { key: 'pending_count', label: t('approvals.pending') },
                { key: 'avg_response_hours', label: t('approvals.tiempo_respuesta'), render: (_v, row) => (row.avg_response_hours != null ? row.avg_response_hours.toFixed(1) : '—') },
                { key: 'rejection_rate_pct', label: t('approvals.tasa_rechazo'), render: (_v, row) => (row.rejection_rate_pct != null ? row.rejection_rate_pct.toFixed(0) + '%' : '—') },
                { key: 'load_score', label: t('approvals.score_carga'), render: (_v, row) => (
                  <span className={`apv-score ${row.load_score > 7 ? 'apv-nivel--alto' : row.load_score > 4 ? 'apv-nivel--medio' : 'apv-nivel--bajo'}`}>
                    {row.load_score?.toFixed(1) || '—'}
                  </span>
                ) },
                { key: 'overloaded', label: '', render: (_v, row) => (
                  row.load_score > 7 && <StatusBadge kind="danger" caps={false}>{t('approvals.sobrecargado')}</StatusBadge>
                ) },
              ]}
            />
          </div>
        </>
      )}
    </div>
  )
}

// ── Matriz de aprobación ──────────────────────────────────────────────────────
export function ApprovalMatrixTab({ workflows = [] }: { workflows?: ApprovalWorkflow[] }) {
  const t = useAppT()
  const entityMap = entityLabels(t)
  const entityTypes = Object.keys(entityMap)
  const allWorkflowNames = [...new Set(workflows.map(w => w.name))]

  return (
    <div>
      <p className="apv-intro">{t('approvals.vista_de_que_flujos_estan_activos_por')}</p>
      <div className="u-scroll-x">
        <TablaSimple claseTabla="apv-matriz">
          <thead>
            <tr>
              <th scope="col">{t('approvals.entidad')}</th>
              {allWorkflowNames.map(name => <th key={name} scope="col">{name}</th>)}
            </tr>
          </thead>
          <tbody>
            {entityTypes.map(et => {
              const cfg = entityMap[et]
              return (
                <tr key={et} className="u-border-b">
                  <th scope="row"><span className="apv-icono-texto">{cfg.icon} {cfg.label}</span></th>
                  {allWorkflowNames.map(name => {
                    const wf = workflows.find(w => w.entity_type === et && w.name === name)
                    if (!wf) return <td key={name} className="apv-matriz__vacio">—</td>
                    const estado = wf.is_default ? 'defecto' : wf.is_active ? 'activo' : 'inactivo'
                    return (
                      <td key={name}>
                        <span className={`apv-estado apv-estado--${estado}`}>{t(`approvals.estado_${estado}`)}</span>
                      </td>
                    )
                  })}
                </tr>
              )
            })}
          </tbody>
        </TablaSimple>
      </div>
    </div>
  )
}

// Pestaña de ejecuciones de un blueprint (lista, reanudar, lanzar). 23-11-2026: troceado de WorkflowDesignerPage sin cambio de comportamiento.
import { useState, useId } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Play, XCircle, Activity, PauseCircle, MousePointerClick } from 'lucide-react'
import { sdWorkflowDesignerApi, type ApiError } from '../../services/api'
import { useToast } from '../../context/ToastContext'
import { Button, Spinner, StatusBadge, Modal, EmptyState, Select, TablaSimple, Input, Textarea } from '../../components/ui'
import { useAppLang } from '../../i18n/AppLangContext'
import { extractErr, fmtDateTime } from '../../utils/helpers'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { POLL_RUN_DETAIL_MS, POLL_RUN_LIST_MS } from '../../constants/timings'
import { type Blueprint, type DetalleEjecucion, ESTADO_KIND, NODE_VISUAL, PROCESOS, colorVar, nombreDeEntidad, nombreDeEstado, nombreDeNodo, nombreDeRama } from './WorkflowDesignerComun'

// ── Runs tab ────────────────────────────────────────────────────────────────
export function RunsTab({ blueprintId }: { blueprintId: string }) {
  const { t: traducir } = useAppLang()
  const qc = useQueryClient()
  const toast = useToast()
  const [activeRunId, setActiveRunId] = useState<string | null>(null)

  const { data: runs = [], isLoading } = useQuery({
    queryKey: ['sd-wf-runs', blueprintId],
    queryFn: () => sdWorkflowDesignerApi.runs({ blueprint_id: blueprintId }).then(r => r.data),
    refetchInterval: POLL_RUN_LIST_MS,
  })
  const { data: runDetail } = useQuery({
    queryKey: ['sd-wf-run', activeRunId],
    queryFn: () => sdWorkflowDesignerApi.run(activeRunId).then(r => r.data),
    enabled: !!activeRunId,
    refetchInterval: POLL_RUN_DETAIL_MS,
  })

  const resume = useMutation({
    mutationFn: ({ runId, branch }: { runId: string; branch: string }) => sdWorkflowDesignerApi.resumeRun(runId, { branch }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sd-wf-runs', blueprintId] })
      qc.invalidateQueries({ queryKey: ['sd-wf-run', activeRunId] })
      toast.success(traducir('workflowdesigner.ejecucion_reanudada'))
    },
    onError: (e: ApiError) => toast.error(extractErr(e, traducir('workflowdesigner.error_reanudar'))),
  })
  const cancel = useMutation({
    // 23-11-2026: el motivo es opcional en el servidor (`reason`, solo se guarda en `last_error`, que la pantalla enseña tal cual);
    // no se manda texto libre en inglés: sin motivo, el estado «cancelada» ya lo dice.
    mutationFn: (runId: string) => sdWorkflowDesignerApi.cancelRun(runId, ''),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sd-wf-runs', blueprintId] })
      qc.invalidateQueries({ queryKey: ['sd-wf-run', activeRunId] })
      toast.success(traducir('workflowdesigner.ejecucion_cancelada'))
    },
  })
  // 23-11-2026: cancelar una ejecución en curso no se puede deshacer: pide confirmación.
  const confirmarCancelar = (runId: string) => openConfirmGlobal({
    message: traducir('workflowdesigner.confirmar_cancelar_ejecucion'),
    confirmLabel: traducir('workflowdesigner.cancelar'),
    danger: true,
    onConfirm: () => cancel.mutate(runId),
  })

  const fmtDate = (iso: string | null) => iso ? fmtDateTime(iso) : ''

  return (
    <div className="wfd-runs">
      <div className="wfd-panel">
        {isLoading ? (
          <div className="wfd-loading"><Spinner /></div>
        ) : runs.length === 0 ? (
          <EmptyState icon={<Activity size={28} />}
            title={traducir('workflowdesigner.aun_no_hay_ejecuciones')}
            description={traducir('workflowdesigner.pulsa_ejecutar_para_iniciar_una_nueva')} />
        ) : (
          <TablaSimple claseTabla="u-table-sm">
            <thead className="wfd-thead">
              <tr className="wfd-thead-row">
                <th className="wfd-th">{traducir('workflowdesigner.th_estado')}</th>
                <th className="wfd-th">{traducir('workflowdesigner.th_nodo')}</th>
                <th className="wfd-th">{traducir('workflowdesigner.th_entidad')}</th>
                <th className="wfd-th">{traducir('workflowdesigner.th_iniciado')}</th>
                <th className="wfd-th"><abbr title={traducir('workflowdesigner.th_version')}>v</abbr></th>
              </tr>
            </thead>
            <tbody>
              {runs.map(r => (
                <tr key={r.id} onClick={() => setActiveRunId(r.id)}
                  tabIndex={0} aria-selected={r.id === activeRunId}
                  onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setActiveRunId(r.id) } }}
                  className={r.id === activeRunId ? 'wfd-run-row wfd-run-row--active' : 'wfd-run-row'}>
                  <td className="wfd-td">
                    <StatusBadge kind={ESTADO_KIND[r.status] ?? 'neutral'} caps={false}>{nombreDeEstado(r.status, traducir)}</StatusBadge>
                  </td>
                  <td className="wfd-td wfd-td--muted">{r.current_node_id || '—'}</td>
                  <td className="wfd-td wfd-td--muted">
                    {r.target_entity_type ? `${nombreDeEntidad(r.target_entity_type, traducir)} ${(r.target_entity_id || '').slice(0, 8)}`.trim() : traducir('workflowdesigner.manual')}
                  </td>
                  <td className="wfd-td wfd-td--dim wfd-td--xs">{fmtDate(r.started_at)}</td>
                  <td className="wfd-td wfd-td--dim">v{r.blueprint_version}</td>
                </tr>
              ))}
            </tbody>
          </TablaSimple>
        )}
      </div>
      {/* Detail panel */}
      <div className="wfd-panel wfd-panel--detail">
        {!activeRunId ? (
          <EmptyState icon={<MousePointerClick size={28} />}
            title={traducir('workflowdesigner.selecciona_una_ejecucion_para_ver_su_historial')} />
        ) : !runDetail ? (
          <Spinner />
        ) : (
          <>
            <div className="u-row-between">
              <div>
                <div className="wfd-bold">{runDetail.run.id.slice(0, 8)}</div>
                <div className="wfd-run-meta">
                  <StatusBadge kind={ESTADO_KIND[runDetail.run.status] ?? 'neutral'} caps={false}>{nombreDeEstado(runDetail.run.status, traducir)}</StatusBadge>
                  <span className="u-text3-xs">v{runDetail.run.blueprint_version}</span>
                </div>
              </div>
              {runDetail.run.status === 'running' || runDetail.run.status === 'waiting' ? (
                <Button size="sm" variant="secondary" icon={<XCircle size={12} />} onClick={() => confirmarCancelar(runDetail.run.id)}>
                  {traducir('workflowdesigner.cancelar')}
                </Button>
              ) : null}
            </div>

            {runDetail.run.last_error && (
              <div className="wfd-error-box" role="alert">
                {runDetail.run.last_error}
              </div>
            )}

            {runDetail.run.status === 'waiting' && (
              <ResumeBranchPicker
                runDetail={runDetail}
                onResume={(branch: string) => resume.mutate({ runId: runDetail.run.id, branch })}
                pending={resume.isPending}
              />
            )}

            <div className="wfd-mt-6">
              <div className="wfd-heading">
                {traducir('workflowdesigner.historial', { n: runDetail.steps.length })}
              </div>
              {runDetail.steps.length === 0 ? (
                <div className="u-text3-xs">{traducir('workflowdesigner.sin_pasos_aun')}</div>
              ) : runDetail.steps.map((s, i) => (
                <div key={s.id} className="wfd-step" style={colorVar(NODE_VISUAL[s.node_type]?.color || 'var(--text-3)')}>
                  <div className="wfd-step__head">
                    <span className="wfd-step__name">
                      {i + 1}. {nombreDeNodo(s.node_type, traducir)}
                    </span>
                    <StatusBadge kind={ESTADO_KIND[s.status] ?? 'neutral'} caps={false}>
                      {nombreDeEstado(s.status, traducir)}{s.branch_taken ? ` · ${nombreDeRama(s.branch_taken, traducir)}` : ''}
                    </StatusBadge>
                  </div>
                  <div className="u-text3-xs">{s.node_id}</div>
                  {s.error && <div className="wfd-step__error">{s.error}</div>}
                </div>
              ))}
            </div>

            {Object.keys(runDetail.run.context || {}).length > 0 && (
              <div>
                <div className="wfd-heading wfd-heading--mb4">
                  {traducir('workflowdesigner.contexto')}
                </div>
                <pre className="wfd-pre">{JSON.stringify(runDetail.run.context, null, 2)}</pre>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function ResumeBranchPicker({ runDetail, onResume, pending }: { runDetail: DetalleEjecucion; onResume: (branch: string) => void; pending: boolean }) {
  const { t: traducir } = useAppLang()
  // Branch options según el tipo del nodo actual
  const nodeType = runDetail.steps?.find(s => s.status === 'waiting')?.node_type || 'approval'
  const branches: { b: string; label: string }[] = ({
    approval: [{ b: 'approved', label: traducir('workflowdesigner.br_aprobar') }, { b: 'rejected', label: traducir('workflowdesigner.br_rechazar') }],
    decision: [{ b: 'true', label: traducir('workflowdesigner.br_verdadero') }, { b: 'false', label: traducir('workflowdesigner.br_falso') }],
    wait: [{ b: 'next', label: traducir('workflowdesigner.br_continuar') }],
    http_call: [{ b: 'success', label: traducir('workflowdesigner.br_exito') }, { b: 'failure', label: traducir('workflowdesigner.br_fallo') }],
  } as Record<string, { b: string; label: string }[]>)[nodeType] || [{ b: 'next', label: traducir('workflowdesigner.br_continuar') }]

  return (
    <div className="wfd-resume">
      <div className="wfd-resume__title">
        <PauseCircle size={14} aria-hidden="true" />
        {traducir('workflowdesigner.esperando_intervencion', { nodo: nombreDeNodo(nodeType, traducir) })}
      </div>
      <div className="u-wrap-6">
        {branches.map(({ b, label }, i) => (
          <Button key={b} size="sm" variant={i === 0 ? 'primary' : 'secondary'} onClick={() => onResume(b)} disabled={pending}>
            {label}
          </Button>
        ))}
      </div>
    </div>
  )
}

export function StartRunModal({ blueprint, onClose, onStarted }: { blueprint: Blueprint; onClose: () => void; onStarted?: () => void }) {
  const idCampo = useId()
  const { t: traducir } = useAppLang()
  const toast = useToast()
  const [contextJson, setContextJson] = useState('{\n  "priority": "P3"\n}')
  const [targetType, setTargetType] = useState(blueprint.process_type || 'manual')
  const [targetId, setTargetId] = useState('')
  const start = useMutation({
    mutationFn: () => {
      let ctx = {}
      try { ctx = contextJson.trim() ? JSON.parse(contextJson) : {} }
      catch { throw new Error(traducir('workflowdesigner.contexto_json_invalido')) }
      return sdWorkflowDesignerApi.startRun(blueprint.id, {
        target_entity_type: targetType || null,
        target_entity_id: targetId || null,
        context: ctx,
      })
    },
    onSuccess: () => { toast.success(traducir('workflowdesigner.ejecucion_iniciada')); onStarted?.() },
    onError: (e: ApiError) => toast.error(e?.response ? extractErr(e, traducir('workflowdesigner.error')) : (e?.message || traducir('workflowdesigner.error'))),
  })
  return (
    <Modal open title={traducir('workflowdesigner.iniciar_ejecucion')} onClose={onClose} width={520}>
      <div className="u-stack-12">
        <div className="u-row-10">
          <div className="u-flex1">
            <Select label={traducir('workflowdesigner.tipo_de_entidad')} placeholder={false} id={`${idCampo}-1`} value={targetType} onChange={e => setTargetType(e.target.value)}>
              {[...PROCESOS, 'manual'].map(p => <option key={p} value={p}>{nombreDeEntidad(p, traducir)}</option>)}
            </Select>
          </div>
          <div className="u-flex1">
            <Input label={traducir('workflowdesigner.id_de_entidad_opcional')} id={`${idCampo}-2`} value={targetId} onChange={e => setTargetId(e.target.value)} placeholder="123e4567-…" />
          </div>
        </div>
        <div>
          <Textarea label={traducir('workflowdesigner.contexto_inicial')} id={`${idCampo}-3`} value={contextJson} onChange={e => setContextJson(e.target.value)} rows={6} inputClassName="wfd-input--mono ds-campo-codigo" />
          <div className="u-hint">
            {traducir('workflowdesigner.las_decisiones_del_workflow_lo_evaluaran_p')} <code>priority == 'P1'</code>).
          </div>
        </div>
        <div className="wfd-actions wfd-actions--mt4">
          <Button variant="secondary" onClick={onClose}>{traducir('workflowdesigner.cancelar')}</Button>
          <Button icon={<Play size={12} />} onClick={() => start.mutate()} loading={start.isPending}>
            {traducir('workflowdesigner.ejecutar')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

/**
 * Ejecución de procesos BPMN: bandeja de pasos humanos e instancias.
 *
 * Auditoría 2026-11: /bpm era un editor sin motor. El backend ejecuta ahora los
 * diagramas guardados (`app/services/bpmn_engine.py`); aquí se completan los
 * pasos que esperan a una persona y se sigue cada instancia.
 *
 * Revisión BPM 2026-11-16:
 * - decisiones manuales: una compuerta exclusiva sin condiciones espera en la
 *   bandeja y quien la completa elige la salida (`flow_id`);
 * - `BpmInbox` se exporta: la usa también la pestaña «Procesos» de /inbox, que
 *   es donde llegan RRHH y empleados (no ven /bpm);
 * - tipos, roles, estados y motivos de fallo se traducen desde sus códigos
 *   (`./textos`); las fechas en hora local con el formato del idioma;
 * - cancelar pide confirmación y solo se ofrece a admin/PM (lo que exige la API).
 */
import { type CSSProperties, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Button, Modal, Spinner, EmptyState, Table } from '../../components/ui'
import { Inbox, Activity } from 'lucide-react'
import { bpmnInstancesApi, apiErrorMsg } from '../../services/api'
import type { InstanciaBpmn, PasoDeBandejaBpmn, PasoDeInstanciaBpmn } from '../../services/api/tipos-documentos'
import { useToast } from '../../context/ToastContext'
import { useAuth } from '../../context/AuthContext'
import { useConfirm } from '../../context/ConfirmContext'
import { useAppLang } from '../../i18n/AppLangContext'
import { fmtDateTime } from '../../utils/helpers'
import { leerVariables, textoErrorDeInstancia, textoEstado, textoRol, textoTipo } from './textos'
import './BpmRunPanel.css'


const STATUS_COLOR: Record<string, string> = {
  running: 'var(--accent)', completed: 'var(--success)', cancelled: 'var(--text-3)', failed: 'var(--danger)',
  active: 'var(--warning)',
}

type BpmnStep = PasoDeInstanciaBpmn
type InboxStep = PasoDeBandejaBpmn
type BpmnInstance = InstanciaBpmn

function invalidarEjecucion(qc: ReturnType<typeof useQueryClient>, instanceId?: string) {
  qc.invalidateQueries({ queryKey: ['bpmn-inbox'] })
  qc.invalidateQueries({ queryKey: ['bpmn-instances'] })
  if (instanceId) qc.invalidateQueries({ queryKey: ['bpmn-instance', instanceId] })
}

function CompleteModal({ step, onClose }: { step: InboxStep; onClose: () => void }) {
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const [vars, setVars] = useState('')
  const esDecision = step.wait_kind === 'decision'
  const opciones = step.options ?? []
  const [salida, setSalida] = useState<string>(opciones.find(o => o.default)?.flow_id ?? '')
  const { mutate, isPending } = useMutation({
    mutationFn: () => bpmnInstancesApi.complete(step.instance_id, step.id, {
      variables: leerVariables(vars),
      ...(esDecision ? { flow_id: salida } : {}),
    }),
    onSuccess: () => { invalidarEjecucion(qc, step.instance_id); toast.success(t('bpm.paso_completado')); onClose() },
    onError: (e: unknown) => toast.error(apiErrorMsg(e, t('common.error'))),
  })
  return (
    <Modal open title={`${esDecision ? t('bpm.decidir') : t('bpm.completar')} — ${step.name || step.element_id}`} onClose={onClose} width={520}>
      <div className="u-stack-12">
        <div className="u-text2-sm">{step.process_name}</div>
        {step.variables && Object.keys(step.variables).length > 0 && (
          <div className="bprupa-box-1">
            {Object.entries(step.variables).map(([k, v]) => <div key={k}>{k} = {String(v)}</div>)}
          </div>
        )}
        {esDecision && (
          <>
            <label htmlFor="bpm-salida" className="bprupa-txt-1">{t('bpm.elige_salida')}</label>
            <select id="bpm-salida" className="ds-input" value={salida} onChange={e => setSalida(e.target.value)}>
              <option value="" disabled>{t('bpm.elige_salida')}</option>
              {opciones.map(o => (
                <option key={o.flow_id} value={o.flow_id}>{o.name}{o.default ? ` ${t('bpm.salida_por_defecto')}` : ''}</option>
              ))}
            </select>
          </>
        )}
        <label htmlFor="bpm-vars" id="bpm-vars-etiqueta" className="bprupa-txt-1">{t('bpm.variables_ayuda')}</label>
        <textarea id="bpm-vars" aria-labelledby="bpm-vars-etiqueta" value={vars} onChange={e => setVars(e.target.value)} rows={4} className="bprupa-fs" placeholder={t('bpm.variables_ejemplo')} />
        <div className="u-actions-8">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => mutate()} loading={isPending} disabled={isPending || (esDecision && !salida)}>
            {esDecision ? t('bpm.decidir') : t('bpm.completar')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function InstanceModal({ id, onClose }: { id: string; onClose: () => void }) {
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const { hasRole } = useAuth()
  const { confirmar } = useConfirm()
  const { data, isLoading, isError } = useQuery<BpmnInstance>({ queryKey: ['bpmn-instance', id], queryFn: () => bpmnInstancesApi.get(id).then(r => r.data) })
  const { mutate: cancel, isPending: cancelando } = useMutation({
    mutationFn: () => bpmnInstancesApi.cancel(id),
    onSuccess: () => invalidarEjecucion(qc, id),
    onError: (e: unknown) => toast.error(apiErrorMsg(e, t('common.error'))),
  })
  const pedirCancelar = async () => {
    if (await confirmar({ message: t('bpm.confirmar_cancelar_instancia'), danger: true })) cancel()
  }
  const motivo = data ? textoErrorDeInstancia(t, data) : null
  return (
    <Modal open title={t('bpm.instancia')} onClose={onClose} width={640}>
      {isError ? <div role="alert" className="bprupa-box-2">{t('bpm.error_cargar_instancia')}</div>
        : isLoading || !data ? <Spinner /> : (
        <div className="u-stack-10">
          <div className="u-sm">
            <strong className="bpm-run-panel-e1" style={{ '--bpm-run-panel-color': STATUS_COLOR[data.status] } as CSSProperties}>{textoEstado(t, data.status)}</strong> · v{data.version}
            {motivo && <div role="alert" className="bprupa-box-2">{motivo}</div>}
          </div>
          <Table
            data={data.steps || []}
            columns={[
              { key: 'name', label: t('bpm.paso'), render: (_v, s: BpmnStep) => s.name || s.element_id },
              { key: 'element_type', label: t('bpm.tipo'), render: (_v, s: BpmnStep) => <span className="u-text2-xs">{textoTipo(t, s.element_type)}{s.candidate_role ? ` · ${textoRol(t, s.candidate_role)}` : ''}</span> },
              { key: 'status', label: t('bpm.estado'), render: (_v, s: BpmnStep) => <span className="bpm-run-panel-e1" style={{ '--bpm-run-panel-color': STATUS_COLOR[s.status] } as CSSProperties}>{textoEstado(t, s.status)}</span> },
              { key: 'completed_at', label: t('bpm.cuando'), render: (_v, s: BpmnStep) => <span className="u-xs">{fmtDateTime(s.completed_at || s.due_at || s.created_at)}</span> },
            ]}
          />
          {data.status === 'running' && hasRole('admin', 'pm') && (
            <div className="u-row-end">
              <Button variant="secondary" onClick={pedirCancelar} loading={cancelando} disabled={cancelando}>{t('bpm.cancelar_instancia')}</Button>
            </div>
          )}
        </div>
      )}
    </Modal>
  )
}

/** Pasos humanos (tareas y decisiones) pendientes que puede completar el usuario. */
export function BpmInbox(): JSX.Element {
  const { t } = useAppLang()
  const [completing, setCompleting] = useState<InboxStep | null>(null)
  const { data: inbox = [], isLoading, isError } = useQuery<InboxStep[]>({
    queryKey: ['bpmn-inbox'], queryFn: () => bpmnInstancesApi.inbox().then(r => r.data),
  })
  return (
    <section className="ds-card bprupa-sp-1">
      <h3 className="bprupa-box-3">{t('bpm.mi_bandeja')}</h3>
      {isLoading ? <Spinner /> : isError ? (
        <div role="alert" className="bprupa-box-2">{t('bpm.error_cargar_bandeja')}</div>
      ) : inbox.length === 0 ? (
        <EmptyState icon={<Inbox size={28} />} title={t('bpm.bandeja_vacia')} description={t('bpm.bandeja_vacia_desc')} />
      ) : (
        <table className="table">
          <thead><tr><th>{t('bpm.paso')}</th><th>{t('bpm.proceso')}</th><th>{t('bpm.rol')}</th><th>{t('bpm.desde')}</th><th><span className="u-sr-only">{t('cmdb.actions')}</span></th></tr></thead>
          <tbody>
            {inbox.map(s => (
              <tr key={s.id}>
                <td>{s.name || s.element_id}{s.wait_kind === 'decision' && <span className="u-text2-xs"> · {t('bpm.decision')}</span>}</td>
                <td>{s.process_name}</td>
                <td className="u-text2">{textoRol(t, s.candidate_role)}</td>
                <td className="u-xs">{fmtDateTime(s.created_at)}</td>
                <td className="bprupa-txt-2"><Button onClick={() => setCompleting(s)}>{s.wait_kind === 'decision' ? t('bpm.decidir') : t('bpm.completar')}</Button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {completing && <CompleteModal step={completing} onClose={() => setCompleting(null)} />}
    </section>
  )
}

export default function BpmRunPanel() {
  const { t } = useAppLang()
  const [viewing, setViewing] = useState<string | null>(null)
  const { data: instances = [], isLoading: loadingInst, isError } = useQuery<BpmnInstance[]>({
    queryKey: ['bpmn-instances'], queryFn: () => bpmnInstancesApi.list().then(r => r.data),
  })
  return (
    <div className="bprupa-stack-1">
      <BpmInbox />
      <section className="ds-card bprupa-sp-1">
        <h3 className="bprupa-box-3">{t('bpm.instancias')}</h3>
        {loadingInst ? <Spinner /> : isError ? (
          <div role="alert" className="bprupa-box-2">{t('bpm.error_cargar_instancias')}</div>
        ) : instances.length === 0 ? (
          <EmptyState icon={<Activity size={28} />} title={t('bpm.sin_instancias')} description={t('bpm.sin_instancias_desc')} />
        ) : (
          <table className="table">
            <thead><tr><th>{t('bpm.proceso')}</th><th>{t('bpm.estado')}</th><th>{t('bpm.pendiente')}</th><th>{t('bpm.inicio')}</th><th><span className="u-sr-only">{t('cmdb.actions')}</span></th></tr></thead>
            <tbody>
              {instances.map(i => (
                <tr key={i.id}>
                  <td>{i.process_name}</td>
                  <td className="bpm-run-panel-e1" style={{ '--bpm-run-panel-color': STATUS_COLOR[i.status] } as CSSProperties}>{textoEstado(t, i.status)}</td>
                  <td className="u-xs">{(i.active_steps || []).join(', ') || '—'}</td>
                  <td className="u-xs">{fmtDateTime(i.started_at)}</td>
                  <td className="bprupa-txt-2"><Button variant="secondary" onClick={() => setViewing(i.id)}>{t('bpm.ver')}</Button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      {viewing && <InstanceModal id={viewing} onClose={() => setViewing(null)} />}
    </div>
  )
}

/**
 * Ejecución de procesos BPMN: bandeja de pasos humanos, instancias y métricas.
 *
 * Auditoría 2026-11: /bpm era un editor sin motor. El backend ejecuta ahora los
 * diagramas guardados (`app/services/bpmn_engine.py`); aquí se completan los
 * pasos que esperan a una persona y se sigue cada instancia.
 *
 * Revisión BPM 2026-11-16: decisiones manuales, `BpmInbox` exportada (pestaña
 * «Procesos» de /inbox), textos por código, cancelar con confirmación.
 *
 * Revisión BPM 2026-11-23 (docs/BPM.md):
 * - completar con el formulario tipado de la tarea, aprobar o rechazar, varias
 *   salidas en una compuerta inclusiva y terminar con un error de negocio;
 * - la bandeja dice a quién está asignada cada tarea y si está fuera de plazo,
 *   y se filtra con el `Buscador`;
 * - la instancia se ve sobre el diagrama de su versión, con quién hizo cada
 *   paso; se suspende, reanuda, migra de versión, cancela, reasigna y
 *   reintenta (incidentes), con confirmación en lo destructivo;
 * - instancias con `FiltrosDeLista` (texto y estado) y métricas: duración,
 *   cuellos de botella, atascadas y tareas fuera de plazo.
 */
import { type CSSProperties, useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Button, Modal, Spinner, EmptyState, Select, TablaSimple, Textarea, Input, Checkbox, Buscador, FiltrosDeLista,
  SelectRico, IconButton, KpiCard, UserSelect,
} from '../../components/ui'
import { Inbox, Activity, UserCog, RotateCcw, Timer, AlertTriangle, Clock, Gauge } from 'lucide-react'
import { bpmnInstancesApi, bpmnProcessesApi, apiErrorMsg } from '../../services/api'
import type { CampoBpmn, InstanciaBpmn, MetricasBpmn, PasoDeBandejaBpmn, PasoDeInstanciaBpmn, VersionDeProcesoBpmn } from '../../services/api/tipos-documentos'
import { useToast } from '../../context/ToastContext'
import { useAuth } from '../../context/AuthContext'
import { useConfirm } from '../../context/ConfirmContext'
import { useAppLang } from '../../i18n/AppLangContext'
import { fmtDateTime } from '../../utils/helpers'
import { leerVariables, textoErrorDeInstancia, textoEspera, textoEstado, textoRol, textoTipo } from './textos'
import BpmDiagrama from './BpmDiagrama'
import './BpmRunPanel.css'


const STATUS_COLOR: Record<string, string> = {
  running: 'var(--accent)', completed: 'var(--success)', cancelled: 'var(--text-3)', failed: 'var(--danger)',
  active: 'var(--warning)', suspended: 'var(--warning)',
}
const ESTADOS = ['running', 'suspended', 'completed', 'cancelled', 'failed'] as const

type BpmnStep = PasoDeInstanciaBpmn
type InboxStep = PasoDeBandejaBpmn
type BpmnInstance = InstanciaBpmn
type Traducir = (k: string, p?: Record<string, unknown>) => string

function invalidarEjecucion(qc: ReturnType<typeof useQueryClient>, instanceId?: string) {
  qc.invalidateQueries({ queryKey: ['bpmn-inbox'] })
  qc.invalidateQueries({ queryKey: ['bpmn-instances'] })
  qc.invalidateQueries({ queryKey: ['bpmn-metrics'] })
  if (instanceId) qc.invalidateQueries({ queryKey: ['bpmn-instance', instanceId] })
}

/** Quién puede completar el paso, en texto: persona asignada, candidatos o rol. */
function textoAsignacion(t: Traducir, s: BpmnStep): string {
  if (s.assignee_name || s.assignee_user_id) return s.assignee_name || t('bpm.persona_asignada')
  const grupos = (s.candidate_groups || []).filter(g => !g.startsWith('role:'))
  if (grupos.length) return t('bpm.candidatos_n', { n: grupos.length + (s.candidate_role ? 1 : 0) })
  return textoRol(t, s.candidate_role)
}

/** Un campo del formulario de la tarea, con el control de su tipo. */
function CampoDeFormulario({ campo, valor, onChange }: { campo: CampoBpmn; valor: unknown; onChange: (v: unknown) => void }) {
  const { t } = useAppLang()
  const etiqueta = `${campo.label || campo.name}${campo.required ? ' *' : ''}`
  if (campo.type === 'boolean') {
    return <Checkbox checked={valor === true} onChange={m => onChange(m)} label={etiqueta} />
  }
  if (campo.type === 'enum') {
    return (
      <Select label={etiqueta} value={String(valor ?? '')} onChange={e => onChange(e.target.value)} required={campo.required}>
        <option value="">{t('bpm.elige')}</option>
        {(campo.options || []).map(o => <option key={o} value={o}>{o}</option>)}
      </Select>
    )
  }
  if (campo.type === 'user') {
    return (
      <div>
        <div className="bprupa-txt-1">{etiqueta}</div>
        <UserSelect value={String(valor ?? '')} onChange={id => onChange(id)} required={campo.required} />
      </div>
    )
  }
  if (campo.type === 'text') {
    return <Textarea label={etiqueta} value={String(valor ?? '')} onChange={e => onChange(e.target.value)} rows={3} required={campo.required} />
  }
  const tipo = campo.type === 'number' || campo.type === 'integer' ? 'number' : campo.type === 'date' ? 'date' : 'text'
  return (
    <Input label={etiqueta} type={tipo} value={String(valor ?? '')} required={campo.required}
      step={campo.type === 'integer' ? 1 : undefined}
      onChange={e => onChange(tipo === 'number' && e.target.value !== '' ? Number(e.target.value) : e.target.value)} />
  )
}

function CompleteModal({ step, onClose }: { step: InboxStep; onClose: () => void }) {
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const [vars, setVars] = useState('')
  const [valores, setValores] = useState<Record<string, unknown>>({})
  const [errorCode, setErrorCode] = useState('')
  const esDecision = step.wait_kind === 'decision'
  const multiple = !!step.multiple
  const opciones = step.options ?? []
  const formulario = step.form ?? []
  const [salidas, setSalidas] = useState<string[]>(() => {
    const d = opciones.find(o => o.default)?.flow_id
    return d ? [d] : []
  })
  const { mutate, isPending } = useMutation({
    mutationFn: (extra: Record<string, unknown> = {}) => {
      const variables = formulario.length
        ? Object.fromEntries(Object.entries(valores).filter(([, v]) => v !== '' && v !== undefined))
        : leerVariables(vars)
      return bpmnInstancesApi.complete(step.instance_id, step.id, {
        variables: { ...variables, ...extra },
        ...(esDecision ? (multiple ? { flow_ids: salidas } : { flow_id: salidas[0] }) : {}),
        ...(errorCode ? { error_code: errorCode } : {}),
      })
    },
    onSuccess: () => { invalidarEjecucion(qc, step.instance_id); toast.success(t('bpm.paso_completado')); onClose() },
    onError: (e: unknown) => toast.error(apiErrorMsg(e, t('common.error'))),
  })
  const titulo = esDecision ? t('bpm.decidir') : step.approval ? t('bpm.aprobar_o_rechazar') : t('bpm.completar')
  return (
    <Modal open title={`${titulo} — ${step.name || step.element_id}`} onClose={onClose} width={560}>
      <div className="u-stack-12">
        <div className="u-text2-sm">{step.process_name}{step.business_key ? ` · ${step.business_key}` : ''}</div>
        {step.sla_due_at && (
          <div className={step.overdue ? 'bpm-vencida' : 'u-text2-sm'}>{t('bpm.plazo_dp')} {fmtDateTime(step.sla_due_at)}</div>
        )}
        {step.variables && Object.keys(step.variables).length > 0 && (
          <div className="ds-codigo ds-codigo--bloque bprupa-box-1">
            {Object.entries(step.variables).map(([k, v]) => <div key={k}>{k} = {String(v)}</div>)}
          </div>
        )}
        {esDecision && !multiple && (
          <>
            <Select label={t('bpm.elige_salida')} placeholder={false} id="bpm-salida" value={salidas[0] ?? ''} onChange={e => setSalidas([e.target.value])}>
              <option value="" disabled>{t('bpm.elige_salida')}</option>
              {opciones.map(o => (
                <option key={o.flow_id} value={o.flow_id}>{o.name}{o.default ? ` ${t('bpm.salida_por_defecto')}` : ''}</option>
              ))}
            </Select>
          </>
        )}
        {esDecision && multiple && (
          <fieldset className="ds-grupo-opciones">
            <legend className="bprupa-txt-1">{t('bpm.elige_salidas')}</legend>
            {opciones.map(o => (
              <Checkbox key={o.flow_id} label={o.name} checked={salidas.includes(o.flow_id)}
                onChange={m => setSalidas(prev => m ? [...prev, o.flow_id] : prev.filter(x => x !== o.flow_id))} />
            ))}
          </fieldset>
        )}
        {formulario.length > 0 ? (
          <div className="bpm-campos">
            {formulario.map(c => (
              <CampoDeFormulario key={c.name} campo={c} valor={valores[c.name]} onChange={v => setValores(p => ({ ...p, [c.name]: v }))} />
            ))}
          </div>
        ) : (
          <>
            <Textarea label={t('bpm.variables_ayuda')} id="bpm-vars" value={vars} onChange={e => setVars(e.target.value)} rows={4} placeholder={t('bpm.variables_ejemplo')} inputClassName="ds-codigo" />
          </>
        )}
        {(step.error_codes ?? []).length > 0 && (
          <Select label={t('bpm.terminar_con_error')} value={errorCode} onChange={e => setErrorCode(e.target.value)}>
            <option value="">{t('bpm.sin_error')}</option>
            {(step.error_codes ?? []).map(c => <option key={c || '*'} value={c || 'error'}>{c || t('bpm.error_generico')}</option>)}
          </Select>
        )}
        <div className="u-actions-8">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          {step.approval && !esDecision ? (
            <>
              <Button variant="danger" onClick={() => mutate({ aprobado: false })} loading={isPending} disabled={isPending}>{t('bpm.rechazar')}</Button>
              <Button onClick={() => mutate({ aprobado: true })} loading={isPending} disabled={isPending}>{t('bpm.aprobar')}</Button>
            </>
          ) : (
            <Button onClick={() => mutate({})} loading={isPending} disabled={isPending || (esDecision && salidas.length === 0)}>
              {esDecision ? t('bpm.decidir') : t('bpm.completar')}
            </Button>
          )}
        </div>
      </div>
    </Modal>
  )
}

function ReasignarModal({ instanceId, step, onClose }: { instanceId: string; step: BpmnStep; onClose: () => void }) {
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const [persona, setPersona] = useState(step.assignee_user_id ?? '')
  const { mutate, isPending } = useMutation({
    mutationFn: () => bpmnInstancesApi.assign(instanceId, step.id, persona || null),
    onSuccess: () => { invalidarEjecucion(qc, instanceId); toast.success(t('bpm.paso_reasignado')); onClose() },
    onError: (e: unknown) => toast.error(apiErrorMsg(e, t('common.error'))),
  })
  return (
    <Modal open title={`${t('bpm.reasignar')} — ${step.name || step.element_id}`} onClose={onClose} width={460}>
      <div className="u-stack-12">
        <div className="bprupa-txt-1">{t('bpm.asignar_a')}</div>
        <UserSelect value={persona} onChange={id => setPersona(id)} placeholder={t('bpm.sin_asignar')} />
        <div className="u-actions-8">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => mutate()} loading={isPending} disabled={isPending}>{t('common.save')}</Button>
        </div>
      </div>
    </Modal>
  )
}

function InstanceModal({ id, onClose }: { id: string; onClose: () => void }) {
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const { puede } = useAuth()
  const { confirmar } = useConfirm()
  const gestiona = puede('bpm.editar')
  const [reasignando, setReasignando] = useState<BpmnStep | null>(null)
  const [destino, setDestino] = useState('')
  const { data, isLoading, isError } = useQuery<BpmnInstance>({ queryKey: ['bpmn-instance', id], queryFn: () => bpmnInstancesApi.get(id).then(r => r.data) })
  const { data: version } = useQuery<VersionDeProcesoBpmn>({
    queryKey: ['bpmn-version', data?.process_id, data?.version],
    queryFn: () => bpmnProcessesApi.version(data!.process_id, data!.version).then(r => r.data),
    enabled: !!data,
  })
  const { data: versiones = [] } = useQuery<VersionDeProcesoBpmn[]>({
    queryKey: ['bpmn-versions', data?.process_id],
    queryFn: () => bpmnProcessesApi.versions(data!.process_id).then(r => r.data),
    enabled: !!data && gestiona && (data.status === 'running' || data.status === 'suspended'),
  })
  const accion = useMutation({
    mutationFn: (f: () => Promise<unknown>) => f(),
    onSuccess: () => { invalidarEjecucion(qc, id); toast.success(t('bpm.hecho')) },
    onError: (e: unknown) => toast.error(apiErrorMsg(e, t('common.error'))),
  })
  const pedir = async (mensaje: string, f: () => Promise<unknown>, peligro = true) => {
    if (await confirmar({ message: mensaje, danger: peligro })) accion.mutate(f)
  }
  const motivo = data ? textoErrorDeInstancia(t, data) : null
  const pasos = data?.steps ?? []
  const viva = data?.status === 'running' || data?.status === 'suspended'
  return (
    <Modal open title={`${t('bpm.instancia')}${data?.process_name ? ` — ${data.process_name}` : ''}`} onClose={onClose} width={880}>
      {isError ? <div role="alert" className="bprupa-box-2">{t('bpm.error_cargar_instancia')}</div>
        : isLoading || !data ? <Spinner /> : (
        <div className="u-stack-10">
          <div className="u-sm">
            <strong className="bpm-run-panel-e1" style={{ '--bpm-run-panel-color': STATUS_COLOR[data.status] } as CSSProperties}>{textoEstado(t, data.status)}</strong>
            {' · '}v{data.version}
            {data.business_key ? ` · ${t('bpm.clave_de_negocio')}: ${data.business_key}` : ''}
            {data.started_by_name ? ` · ${t('bpm.iniciada_por', { name: data.started_by_name })}` : ''}
            {motivo && <div role="alert" className="bprupa-box-2">{motivo}</div>}
          </div>
          <BpmDiagrama xml={version?.bpmn_xml}
            activos={pasos.filter(s => s.status === 'active' && s.wait_kind !== 'incident').map(s => s.element_id)}
            hechos={pasos.filter(s => s.status === 'completed').map(s => s.element_id)}
            incidentes={pasos.filter(s => s.status === 'active' && s.wait_kind === 'incident').map(s => s.element_id)} />
          <TablaSimple claseTabla="table">
            <thead><tr><th>{t('bpm.paso')}</th><th>{t('bpm.tipo')}</th><th>{t('bpm.estado')}</th><th>{t('bpm.quien')}</th><th>{t('bpm.cuando')}</th><th><span className="u-sr-only">{t('cmdb.actions')}</span></th></tr></thead>
            <tbody>
              {pasos.map(s => (
                <tr key={s.id}>
                  <td>{s.name || s.element_id}</td>
                  <td className="u-text2-xs">{textoTipo(t, s.element_type)}{s.status === 'active' && s.wait_kind ? ` · ${textoEspera(t, s.wait_kind)}` : ''}</td>
                  <td><span className="bpm-run-panel-e1" style={{ '--bpm-run-panel-color': STATUS_COLOR[s.status] } as CSSProperties}>{textoEstado(t, s.status)}</span>
                    {s.overdue && <span className="bpm-vencida"> · {t('bpm.fuera_de_plazo')}</span>}</td>
                  <td className="u-xs">{s.status === 'active' ? (s.human ? textoAsignacion(t, s) : '—') : (s.completed_by_name || '—')}</td>
                  <td className="u-xs">{fmtDateTime(s.completed_at || s.due_at || s.created_at)}</td>
                  <td>
                    <div className="ui-acciones">
                      {gestiona && viva && s.status === 'active' && s.human && (
                        <IconButton variante="caja" ariaLabel={t('bpm.reasignar')} onClick={() => setReasignando(s)}><UserCog /></IconButton>
                      )}
                      {gestiona && viva && s.status === 'active' && s.wait_kind === 'incident' && (
                        <IconButton variante="caja" tono="acento" ariaLabel={t('bpm.reintentar')} onClick={() => accion.mutate(() => bpmnInstancesApi.retry(id, s.id))}><RotateCcw /></IconButton>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </TablaSimple>
          {(data.children ?? []).length > 0 && (
            <div className="u-text2-sm">{t('bpm.subinstancias')}: {(data.children ?? []).map(c => `${c.id.slice(0, 8)} (${textoEstado(t, c.status)})`).join(', ')}</div>
          )}
          {gestiona && viva && (
            <div className="bpm-acciones-instancia">
              {versiones.length > 1 && (
                <>
                  <Select suelto aria-label={t('bpm.migrar_a_version')} value={destino} onChange={e => setDestino(e.target.value)}>
                    <option value="">{t('bpm.migrar_a_version')}</option>
                    {versiones.filter(v => v.version !== data.version).map(v => <option key={v.id} value={v.version}>v{v.version}</option>)}
                  </Select>
                  <Button variant="secondary" disabled={!destino || accion.isPending}
                    onClick={() => pedir(t('bpm.confirmar_migrar', { n: destino }), () => bpmnInstancesApi.migrate(id, Number(destino)), false)}>
                    {t('bpm.migrar')}
                  </Button>
                </>
              )}
              {data.status === 'running' ? (
                <Button variant="secondary" disabled={accion.isPending} onClick={() => pedir(t('bpm.confirmar_suspender'), () => bpmnInstancesApi.suspend(id), false)}>{t('bpm.suspender')}</Button>
              ) : (
                <Button variant="secondary" disabled={accion.isPending} onClick={() => accion.mutate(() => bpmnInstancesApi.resume(id))}>{t('bpm.reanudar')}</Button>
              )}
              <Button variant="danger" disabled={accion.isPending} onClick={() => pedir(t('bpm.confirmar_cancelar_instancia'), () => bpmnInstancesApi.cancel(id))}>{t('bpm.cancelar_instancia')}</Button>
            </div>
          )}
        </div>
      )}
      {reasignando && <ReasignarModal instanceId={id} step={reasignando} onClose={() => setReasignando(null)} />}
    </Modal>
  )
}

/** Pasos humanos (tareas y decisiones) pendientes que puede completar el usuario. */
export function BpmInbox(): JSX.Element {
  const { t } = useAppLang()
  const [completing, setCompleting] = useState<InboxStep | null>(null)
  const [q, setQ] = useState('')
  const { data: inbox = [], isLoading, isError } = useQuery<InboxStep[]>({
    queryKey: ['bpmn-inbox'], queryFn: () => bpmnInstancesApi.inbox().then(r => r.data),
  })
  const visibles = useMemo(() => {
    const texto = q.trim().toLowerCase()
    return !texto ? inbox : inbox.filter(s => [s.name, s.element_id, s.process_name, s.business_key]
      .some(v => (v || '').toLowerCase().includes(texto)))
  }, [inbox, q])
  return (
    <section className="ds-card bprupa-sp-1">
      <h3 className="bprupa-box-3">{t('bpm.mi_bandeja')}</h3>
      {inbox.length > 0 && <FiltrosDeLista buscador={<Buscador value={q} onChange={setQ} placeholder={t('bpm.buscar_tarea')} aria-label={t('bpm.buscar_tarea')} />} />}
      {isLoading ? <Spinner /> : isError ? (
        <div role="alert" className="bprupa-box-2">{t('bpm.error_cargar_bandeja')}</div>
      ) : inbox.length === 0 ? (
        <EmptyState icon={<Inbox size={28} />} title={t('bpm.bandeja_vacia')} description={t('bpm.bandeja_vacia_desc')} />
      ) : (
        <TablaSimple claseTabla="table">
          <thead><tr><th>{t('bpm.paso')}</th><th>{t('bpm.proceso')}</th><th>{t('bpm.asignada_a')}</th><th>{t('bpm.plazo')}</th><th>{t('bpm.desde')}</th><th><span className="u-sr-only">{t('cmdb.actions')}</span></th></tr></thead>
          <tbody>
            {visibles.map(s => (
              <tr key={s.id}>
                <td>{s.name || s.element_id}{s.wait_kind === 'decision' && <span className="u-text2-xs"> · {t('bpm.decision')}</span>}{s.approval && <span className="u-text2-xs"> · {t('bpm.aprobacion')}</span>}</td>
                <td>{s.process_name}{s.business_key ? <span className="u-text2-xs"> · {s.business_key}</span> : null}</td>
                <td className="u-text2">{textoAsignacion(t, s)}</td>
                <td className={s.overdue ? 'bpm-vencida u-xs' : 'u-xs'}>{s.sla_due_at ? fmtDateTime(s.sla_due_at) : '—'}</td>
                <td className="u-xs">{fmtDateTime(s.created_at)}</td>
                <td className="bprupa-txt-2"><Button onClick={() => setCompleting(s)}>{s.wait_kind === 'decision' ? t('bpm.decidir') : t('bpm.completar')}</Button></td>
              </tr>
            ))}
          </tbody>
        </TablaSimple>
      )}
      {completing && <CompleteModal step={completing} onClose={() => setCompleting(null)} />}
    </section>
  )
}

/** Duración, cuellos de botella, instancias atascadas y tareas fuera de plazo (últimos 30 días). */
export function BpmMetricas({ processId }: { processId?: string }): JSX.Element {
  const { t } = useAppLang()
  const { data, isLoading, isError } = useQuery<MetricasBpmn>({
    queryKey: ['bpmn-metrics', processId ?? null],
    queryFn: () => bpmnInstancesApi.metrics(processId ? { process_id: processId } : {}).then(r => r.data),
  })
  const horas = (v: number | null | undefined) => (v == null ? '—' : t('bpm.n_horas', { n: v }))
  return (
    <section className="ds-card bprupa-sp-1">
      <h3 className="bprupa-box-3">{t('bpm.metricas')}</h3>
      {isLoading ? <Spinner /> : isError || !data ? <div role="alert" className="bprupa-box-2">{t('bpm.error_cargar_metricas')}</div> : (
        <div className="u-stack-12">
          <div className="bpm-kpis">
            <KpiCard icon={<Activity size={16} />} label={t('bpm.iniciadas_n_dias', { n: data.days })} value={data.started} />
            <KpiCard icon={<Clock size={16} />} label={t('bpm.duracion_media')} value={horas(data.duration_hours.avg)} sub={`p50 ${horas(data.duration_hours.p50)} · p90 ${horas(data.duration_hours.p90)}`} />
            <KpiCard icon={<AlertTriangle size={16} />} label={t('bpm.atascadas')} value={data.stuck_count} warning={data.stuck_count > 0} sub={t('bpm.atascada_tras_n_horas', { n: data.stuck_hours })} />
            <KpiCard icon={<Timer size={16} />} label={t('bpm.tareas_fuera_de_plazo')} value={data.overdue_tasks} danger={data.overdue_tasks > 0} />
          </div>
          {data.bottlenecks.length > 0 && (
            <TablaSimple claseTabla="table">
              <caption className="u-text2-sm">{t('bpm.cuellos_de_botella')}</caption>
              <thead><tr><th>{t('bpm.paso')}</th><th>{t('bpm.veces')}</th><th>{t('bpm.espera_media')}</th><th>p90</th></tr></thead>
              <tbody>{data.bottlenecks.map(b => (
                <tr key={b.element_id}><td>{b.name || b.element_id}</td><td>{b.count}</td><td>{horas(b.avg_hours)}</td><td>{horas(b.p90_hours)}</td></tr>
              ))}</tbody>
            </TablaSimple>
          )}
          {data.stuck.length > 0 && (
            <TablaSimple claseTabla="table">
              <caption className="u-text2-sm">{t('bpm.instancias_atascadas')}</caption>
              <thead><tr><th>{t('bpm.proceso')}</th><th>{t('bpm.paso')}</th><th>{t('bpm.motivo')}</th><th>{t('bpm.desde')}</th></tr></thead>
              <tbody>{data.stuck.map(a => (
                <tr key={a.instance_id}><td>{a.process_name || a.instance_id.slice(0, 8)}</td><td>{a.step}</td><td>{t(`bpm.atasco_${a.reason}`)}</td><td className="u-xs">{fmtDateTime(a.since)}</td></tr>
              ))}</tbody>
            </TablaSimple>
          )}
          {data.bottlenecks.length === 0 && data.stuck.length === 0 && <EmptyState icon={<Gauge size={28} />} title={t('bpm.sin_metricas')} />}
        </div>
      )}
    </section>
  )
}

export default function BpmRunPanel() {
  const { t } = useAppLang()
  const [viewing, setViewing] = useState<string | null>(null)
  const [q, setQ] = useState('')
  const [estado, setEstado] = useState('')
  const { data: instances = [], isLoading: loadingInst, isError } = useQuery<BpmnInstance[]>({
    queryKey: ['bpmn-instances', q, estado],
    queryFn: () => bpmnInstancesApi.list({ ...(q.trim() ? { q: q.trim() } : {}), ...(estado ? { status: estado } : {}) }).then(r => r.data),
  })
  const filtrando = !!q.trim() || !!estado
  return (
    <div className="bprupa-stack-1">
      <BpmInbox />
      <BpmMetricas />
      <section className="ds-card bprupa-sp-1">
        <h3 className="bprupa-box-3">{t('bpm.instancias')}</h3>
        <FiltrosDeLista buscador={<Buscador value={q} onChange={setQ} retardo={300} placeholder={t('bpm.buscar_instancia')} aria-label={t('bpm.buscar_instancia')} />}>
          <SelectRico aria-label={t('bpm.estado')} valor={estado} onChange={setEstado}
            opciones={[{ valor: '', etiqueta: t('bpm.todos_los_estados') }, ...ESTADOS.map(e => ({ valor: e, etiqueta: textoEstado(t, e) }))]} />
        </FiltrosDeLista>
        {loadingInst ? <Spinner /> : isError ? (
          <div role="alert" className="bprupa-box-2">{t('bpm.error_cargar_instancias')}</div>
        ) : instances.length === 0 ? (
          <EmptyState icon={<Activity size={28} />} title={filtrando ? t('bpm.sin_instancias_filtro') : t('bpm.sin_instancias')} description={filtrando ? undefined : t('bpm.sin_instancias_desc')} />
        ) : (
          <TablaSimple claseTabla="table">
            <thead><tr><th>{t('bpm.proceso')}</th><th>{t('bpm.estado')}</th><th>{t('bpm.pendiente')}</th><th>{t('bpm.inicio')}</th><th><span className="u-sr-only">{t('cmdb.actions')}</span></th></tr></thead>
            <tbody>
              {instances.map(i => (
                <tr key={i.id}>
                  <td>{i.process_name}{i.business_key ? <span className="u-text2-xs"> · {i.business_key}</span> : null}</td>
                  <td className="bpm-run-panel-e1" style={{ '--bpm-run-panel-color': STATUS_COLOR[i.status] } as CSSProperties}>
                    {textoEstado(t, i.status)}{(i.incidents ?? 0) > 0 && <span className="bpm-vencida"> · {t('bpm.n_incidentes', { n: i.incidents })}</span>}
                  </td>
                  <td className="u-xs">{(i.active_steps || []).join(', ') || '—'}</td>
                  <td className="u-xs">{fmtDateTime(i.started_at)}</td>
                  <td className="bprupa-txt-2"><Button variant="secondary" onClick={() => setViewing(i.id)}>{t('bpm.ver')}</Button></td>
                </tr>
              ))}
            </tbody>
          </TablaSimple>
        )}
      </section>
      {viewing && <InstanceModal id={viewing} onClose={() => setViewing(null)} />}
    </div>
  )
}

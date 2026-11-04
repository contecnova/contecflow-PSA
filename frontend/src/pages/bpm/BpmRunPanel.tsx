/**
 * Ejecución de procesos BPMN: bandeja de pasos humanos e instancias.
 *
 * Auditoría 2026-11: /bpm era un editor sin motor. El backend ejecuta ahora los
 * diagramas guardados (`app/services/bpmn_engine.py`); aquí se completan los
 * pasos que esperan a una persona y se sigue cada instancia.
 */
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Button, Modal, Spinner, EmptyState } from '../../components/ui'
import { bpmnInstancesApi, apiErrorMsg } from '../../services/api'
import { useToast } from '../../context/ToastContext'
import { useAppLang } from '../../i18n/AppLangContext'

const fs: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 10px', color: 'var(--text-1)', fontSize: 'var(--text-sm)', fontFamily: 'inherit', boxSizing: 'border-box' }

const STATUS_COLOR: Record<string, string> = {
  running: 'var(--accent)', completed: 'var(--success)', cancelled: 'var(--text-3)', failed: 'var(--danger)',
  active: 'var(--warning)',
}

function parseVars(text: string): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  text.split('\n').map(l => l.trim()).filter(Boolean).forEach(l => {
    const i = l.indexOf('=')
    if (i <= 0) return
    const k = l.slice(0, i).trim()
    const raw = l.slice(i + 1).trim()
    if (raw === 'true' || raw === 'false') out[k] = raw === 'true'
    else if (raw !== '' && !Number.isNaN(Number(raw))) out[k] = Number(raw)
    else out[k] = raw
  })
  return out
}

function CompleteModal({ step, onClose }: { step: any; onClose: () => void }) {
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const [vars, setVars] = useState('')
  const { mutate, isPending } = useMutation({
    mutationFn: () => bpmnInstancesApi.complete(step.instance_id, step.id, parseVars(vars)),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['bpmn-inbox'] }); qc.invalidateQueries({ queryKey: ['bpmn-instances'] }); onClose() },
    onError: (e: unknown) => toast.error(apiErrorMsg(e, 'Error')),
  })
  return (
    <Modal open title={`${t('bpm.completar')} — ${step.name || step.element_id}`} onClose={onClose} width={520}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)' }}>{step.process_name}</div>
        {step.variables && Object.keys(step.variables).length > 0 && (
          <div style={{ fontSize: 'var(--text-xs)', fontFamily: 'var(--font-mono)', background: 'var(--surface-3)', borderRadius: 8, padding: 10 }}>
            {Object.entries(step.variables).map(([k, v]) => <div key={k}>{k} = {String(v)}</div>)}
          </div>
        )}
        <label htmlFor="bpm-vars" style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--text-2)' }}>{t('bpm.variables_ayuda')}</label>
        <textarea id="bpm-vars" value={vars} onChange={e => setVars(e.target.value)} rows={4} style={{ ...fs, fontFamily: 'var(--font-mono)' }} placeholder={'aprobada=true\nimporte=500'} />
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => mutate()} loading={isPending} disabled={isPending}>{t('bpm.completar')}</Button>
        </div>
      </div>
    </Modal>
  )
}

function InstanceModal({ id, onClose }: { id: string; onClose: () => void }) {
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const { data, isLoading } = useQuery<any>({ queryKey: ['bpmn-instance', id], queryFn: () => bpmnInstancesApi.get(id).then(r => r.data) })
  const { mutate: cancel } = useMutation({
    mutationFn: () => bpmnInstancesApi.cancel(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['bpmn-instances'] }); qc.invalidateQueries({ queryKey: ['bpmn-instance', id] }) },
    onError: (e: unknown) => toast.error(apiErrorMsg(e, 'Error')),
  })
  return (
    <Modal open title={t('bpm.instancia')} onClose={onClose} width={640}>
      {isLoading || !data ? <Spinner /> : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ fontSize: 'var(--text-sm)' }}>
            <strong style={{ color: STATUS_COLOR[data.status] }}>{t('bpm.estado_' + data.status)}</strong> · v{data.version}
            {data.error && <div role="alert" style={{ color: 'var(--danger)', marginTop: 4 }}>{data.error}</div>}
          </div>
          <table className="table">
            <thead><tr><th>{t('bpm.paso')}</th><th>{t('bpm.tipo')}</th><th>{t('bpm.estado')}</th><th>{t('bpm.cuando')}</th></tr></thead>
            <tbody>
              {(data.steps || []).map((s: any) => (
                <tr key={s.id}>
                  <td>{s.name || s.element_id}</td>
                  <td style={{ fontSize: 'var(--text-xs)', color: 'var(--text-2)' }}>{s.element_type}{s.candidate_role ? ` · ${s.candidate_role}` : ''}</td>
                  <td style={{ color: STATUS_COLOR[s.status] }}>{t('bpm.estado_' + s.status)}</td>
                  <td style={{ fontSize: 'var(--text-xs)' }}>{(s.completed_at || s.due_at || s.created_at || '').slice(0, 16).replace('T', ' ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.status === 'running' && (
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <Button variant="secondary" onClick={() => cancel()}>{t('bpm.cancelar_instancia')}</Button>
            </div>
          )}
        </div>
      )}
    </Modal>
  )
}

export default function BpmRunPanel() {
  const { t } = useAppLang()
  const [completing, setCompleting] = useState<any>(null)
  const [viewing, setViewing] = useState<string | null>(null)
  const { data: inbox = [], isLoading: loadingInbox } = useQuery<any[]>({
    queryKey: ['bpmn-inbox'], queryFn: () => bpmnInstancesApi.inbox().then(r => (Array.isArray(r.data) ? r.data : [])),
  })
  const { data: instances = [], isLoading: loadingInst } = useQuery<any[]>({
    queryKey: ['bpmn-instances'], queryFn: () => bpmnInstancesApi.list().then(r => (Array.isArray(r.data) ? r.data : [])),
  })
  return (
    <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 'var(--space-5)' }}>
      <section className="ds-card" style={{ padding: 16 }}>
        <h3 style={{ margin: '0 0 10px', fontSize: 'var(--text-md)' }}>{t('bpm.mi_bandeja')}</h3>
        {loadingInbox ? <Spinner /> : inbox.length === 0 ? (
          <EmptyState title={t('bpm.bandeja_vacia')} description={t('bpm.bandeja_vacia_desc')} />
        ) : (
          <table className="table">
            <thead><tr><th>{t('bpm.paso')}</th><th>{t('bpm.proceso')}</th><th>{t('bpm.rol')}</th><th /></tr></thead>
            <tbody>
              {inbox.map((s: any) => (
                <tr key={s.id}>
                  <td>{s.name || s.element_id}</td>
                  <td>{s.process_name}</td>
                  <td style={{ color: 'var(--text-2)' }}>{s.candidate_role || '—'}</td>
                  <td style={{ textAlign: 'right' }}><Button onClick={() => setCompleting(s)}>{t('bpm.completar')}</Button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      <section className="ds-card" style={{ padding: 16 }}>
        <h3 style={{ margin: '0 0 10px', fontSize: 'var(--text-md)' }}>{t('bpm.instancias')}</h3>
        {loadingInst ? <Spinner /> : instances.length === 0 ? (
          <EmptyState title={t('bpm.sin_instancias')} description={t('bpm.sin_instancias_desc')} />
        ) : (
          <table className="table">
            <thead><tr><th>{t('bpm.proceso')}</th><th>{t('bpm.estado')}</th><th>{t('bpm.pendiente')}</th><th>{t('bpm.inicio')}</th><th /></tr></thead>
            <tbody>
              {instances.map((i: any) => (
                <tr key={i.id}>
                  <td>{i.process_name}</td>
                  <td style={{ color: STATUS_COLOR[i.status] }}>{t('bpm.estado_' + i.status)}</td>
                  <td style={{ fontSize: 'var(--text-xs)' }}>{(i.active_steps || []).join(', ') || '—'}</td>
                  <td style={{ fontSize: 'var(--text-xs)' }}>{(i.started_at || '').slice(0, 16).replace('T', ' ')}</td>
                  <td style={{ textAlign: 'right' }}><Button variant="secondary" onClick={() => setViewing(i.id)}>{t('bpm.ver')}</Button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      {completing && <CompleteModal step={completing} onClose={() => setCompleting(null)} />}
      {viewing && <InstanceModal id={viewing} onClose={() => setViewing(null)} />}
    </div>
  )
}

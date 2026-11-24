/**
 * Variables declaradas de un proceso y prueba (simulación) del diagrama.
 *
 * Revisión BPM 23-11-2026 (docs/BPM.md, «Variables» y «Probar»):
 * - las variables del proceso tienen tipo, pueden ser obligatorias y marcarse
 *   como dato personal (entran en la copia y la supresión RGPD); el motor
 *   valida el tipo al iniciar y al completar;
 * - «Probar» recorre el diagrama en el servidor sin escribir nada y dice por
 *   dónde pasa, qué acciones ejecutaría y dónde se queda colgado.
 */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, FlaskConical } from 'lucide-react'
import { Button, Checkbox, EmptyState, IconButton, Input, Modal, Select, Textarea } from '../../components/ui'
import { bpmnProcessesApi, apiErrorMsg } from '../../services/api'
import type { CampoBpmn, SimulacionBpmn } from '../../services/api/tipos-documentos'
import { useToast } from '../../context/ToastContext'
import { useAppLang } from '../../i18n/AppLangContext'
import { leerVariables, textoProblema, textoTipo, textoTipoDeVariable } from './textos'
import BpmDiagrama from './BpmDiagrama'
import './BpmRunPanel.css'

const TIPOS: CampoBpmn['type'][] = ['string', 'text', 'number', 'integer', 'boolean', 'date', 'enum', 'user']

export function BpmVariablesModal({ processId, iniciales, puedeEditar, onGuardado, onClose }: {
  processId: string; iniciales: CampoBpmn[]; puedeEditar: boolean; onGuardado: () => void; onClose: () => void
}): JSX.Element {
  const { t } = useAppLang()
  const toast = useToast()
  const [campos, setCampos] = useState<CampoBpmn[]>(iniciales)
  const cambiar = (i: number, p: Partial<CampoBpmn>) => setCampos(cs => cs.map((c, j) => (j === i ? { ...c, ...p } : c)))
  const guardar = useMutation({
    mutationFn: () => bpmnProcessesApi.update(processId, {
      variables_schema: campos.filter(c => c.name.trim()).map(c => ({ ...c, name: c.name.trim() })),
    }),
    onSuccess: () => { toast.success(t('bpm.variables_guardadas')); onGuardado(); onClose() },
    onError: (e: unknown) => toast.error(apiErrorMsg(e, t('common.error'))),
  })
  return (
    <Modal open title={t('bpm.variables_del_proceso')} onClose={onClose} width={760}>
      <div className="u-stack-12">
        <div className="u-text2-sm">{t('bpm.variables_del_proceso_desc')}</div>
        {campos.length === 0 && <EmptyState title={t('bpm.sin_variables')} />}
        {campos.map((c, i) => (
          <div key={i} className="bpm-fila-variable">
            <Input label={t('bpm.variable_nombre')} value={c.name} disabled={!puedeEditar} onChange={e => cambiar(i, { name: e.target.value })} />
            <Select label={t('bpm.tipo')} value={c.type} disabled={!puedeEditar} onChange={e => cambiar(i, { type: e.target.value as CampoBpmn['type'] })}>
              {TIPOS.map(x => <option key={x} value={x}>{textoTipoDeVariable(t, x)}</option>)}
            </Select>
            <Checkbox checked={!!c.required} disabled={!puedeEditar} label={t('bpm.obligatoria')} onChange={v => cambiar(i, { required: v })} />
            <Checkbox checked={!!c.personal} disabled={!puedeEditar} label={t('bpm.dato_personal')} onChange={v => cambiar(i, { personal: v })} />
            {puedeEditar && (
              <div className="ui-acciones">
                <IconButton variante="caja" tono="peligro" ariaLabel={t('bpm.quitar_variable')} onClick={() => setCampos(cs => cs.filter((_, j) => j !== i))}><Trash2 /></IconButton>
              </div>
            )}
            {c.type === 'enum' && (
              <Input label={t('bpm.opciones')} value={(c.options || []).join(', ')} disabled={!puedeEditar}
                onChange={e => cambiar(i, { options: e.target.value.split(',').map(x => x.trim()).filter(Boolean) })} />
            )}
          </div>
        ))}
        <div className="u-actions-8">
          {puedeEditar && <Button variant="secondary" icon={<Plus size={14} />} onClick={() => setCampos(cs => [...cs, { name: '', type: 'string' }])}>{t('bpm.anadir_variable')}</Button>}
          <Button variant="secondary" onClick={onClose}>{t('common.close')}</Button>
          {puedeEditar && <Button onClick={() => guardar.mutate()} loading={guardar.isPending} disabled={guardar.isPending}>{t('common.save')}</Button>}
        </div>
      </div>
    </Modal>
  )
}

export function BpmSimulacionModal({ processId, xml, onClose }: { processId: string; xml: string; onClose: () => void }): JSX.Element {
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const [vars, setVars] = useState('')
  const [res, setRes] = useState<SimulacionBpmn | null>(null)
  const probar = useMutation({
    mutationFn: () => bpmnProcessesApi.simulate(processId, { variables: leerVariables(vars) }).then(r => r.data),
    onSuccess: d => { setRes(d); qc.invalidateQueries({ queryKey: ['bpmn-versions', processId] }) },
    onError: (e: unknown) => toast.error(apiErrorMsg(e, t('common.error'))),
  })
  return (
    <Modal open title={t('bpm.probar_proceso')} onClose={onClose} width={860}>
      <div className="u-stack-12">
        <div className="u-text2-sm">{t('bpm.probar_desc')}</div>
        <Textarea label={t('bpm.variables_ayuda')} value={vars} onChange={e => setVars(e.target.value)} rows={3}
          placeholder={t('bpm.variables_ejemplo')} inputClassName="ds-codigo bprupa-fs" />
        <div className="u-actions-8">
          <Button variant="secondary" onClick={onClose}>{t('common.close')}</Button>
          <Button icon={<FlaskConical size={14} />} onClick={() => probar.mutate()} loading={probar.isPending} disabled={probar.isPending}>{t('bpm.probar')}</Button>
        </div>
        {res && (
          <div className="u-stack-10" aria-live="polite">
            <div role={res.completed ? 'status' : 'alert'} className={res.completed ? 'u-sm' : 'bprupa-box-2'}>
              {res.problems.length ? t('bpm.no_ejecutable_titulo')
                : res.completed ? t('bpm.simulacion_llega_al_final', { n: res.path.length })
                  : res.error ? t('bpm.simulacion_error', { error: res.error }) : t('bpm.simulacion_se_queda')}
            </div>
            {[...res.problems, ...res.warnings].length > 0 && (
              <ul>{[...res.problems, ...res.warnings].map((p, i) => <li key={i}>{textoProblema(t, p)}</li>)}</ul>
            )}
            {res.stuck.length > 0 && (
              <ul>{res.stuck.map(s => <li key={s.element_id}>{t('bpm.union_esperando', { name: s.name || s.element_id, n: s.arrived, total: s.expected })}</li>)}</ul>
            )}
            {res.actions.length > 0 && (
              <div className="u-text2-sm">{t('bpm.acciones_que_ejecutaria')}: {res.actions.map(a => t(`bpm.accion_${a.action}`)).join(', ')}</div>
            )}
            <BpmDiagrama xml={xml} alto="bajo" hechos={res.path.map(p => p.element_id)} activos={res.stuck.map(s => s.element_id)} />
            <ol className="u-text2-sm">
              {res.path.map((p, i) => <li key={i}>{p.name || p.element_id} <span className="u-text2-xs">({textoTipo(t, p.type)})</span></li>)}
            </ol>
          </div>
        )}
      </div>
    </Modal>
  )
}

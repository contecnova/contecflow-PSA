/**
 * Panel de propiedades del editor BPMN: lo que el motor ejecuta y el lienzo no deja escribir.
 *
 * Revisión BPM 23-11-2026 (docs/BPM.md, «Modelar»). Hasta ahora el editor no
 * tenía panel: las condiciones, temporizadores, asignaciones y acciones solo
 * se podían poner importando un `.bpmn`. Según el elemento seleccionado:
 *
 * - tareas: asignar a (persona, `${initiator}`, `${variable}`), grupos
 *   candidatos, plazo (ISO 8601), es una aprobación, formulario (JSON);
 * - tareas de servicio: acción automática de la lista cerrada, su
 *   configuración (JSON) y reintentos;
 * - flujos que salen de una compuerta: condición (`importe > 1000 and urgente == true`);
 * - temporizadores: duración; bordes: interrumpe o no;
 * - mensajes (evento o tarea de recepción): nombre del mensaje;
 * - llamadas: clave del proceso llamado.
 *
 * Las extensiones van como atributos `contecflow:*` (espacio de nombres
 * `CONTECFLOW_NS`, el mismo que lee `app/services/bpmn_engine.py`).
 */
import { useEffect, useState } from 'react'
import { Checkbox, Input, Select, Textarea } from '../../components/ui'
import { useAppLang } from '../../i18n/AppLangContext'
import './BpmRunPanel.css'

export const CONTECFLOW_NS = 'http://contecflow.io/schema/bpmn/1.0'
const ACCIONES = ['', 'set', 'notify', 'ticket', 'change', 'demand', 'approval', 'policy'] as const
const HUMANAS = ['bpmn:Task', 'bpmn:UserTask', 'bpmn:ManualTask']
const SERVICIO = ['bpmn:ServiceTask', 'bpmn:SendTask', 'bpmn:BusinessRuleTask', 'bpmn:ScriptTask']

// Lo mínimo de bpmn-js que usa el panel (sus tipos son genéricos).
type ObjetoDeNegocio = {
  $type: string
  $attrs: Record<string, string | undefined>
  $parent?: ObjetoDeNegocio
  id?: string
  name?: string
  sourceRef?: ObjetoDeNegocio
  conditionExpression?: { body?: string }
  eventDefinitions?: { $type: string; timeDuration?: { body?: string }; messageRef?: { name?: string } }[]
  cancelActivity?: boolean
  calledElement?: string
  messageRef?: { name?: string }
  rootElements?: ObjetoDeNegocio[]
}
type Elemento = { id: string; type: string; businessObject: ObjetoDeNegocio }
type Modelador = {
  get: <T>(nombre: string) => T
  getDefinitions: () => ObjetoDeNegocio
}
type BusDeEventos = { on: (e: string, f: (ev: { newSelection?: Elemento[] }) => void) => void; off: (e: string, f: unknown) => void }
type Moddle = { create: (tipo: string, attrs?: Record<string, unknown>) => unknown }
type Modelado = { updateProperties: (el: Elemento, props: Record<string, unknown>) => void }

export default function BpmPropiedades({ modelador }: { modelador: unknown }): JSX.Element | null {
  const { t } = useAppLang()
  const m = modelador as Modelador | null
  // Solo el id: el elemento vivo se pide al registro de bpmn-js en cada render
  // (es un objeto del modelador, no estado de React).
  const [selId, setSelId] = useState<string | null>(null)
  const [, setVersion] = useState(0)

  useEffect(() => {
    if (!m) return
    const bus = m.get<BusDeEventos>('eventBus')
    const alCambiar = (e: { newSelection?: Elemento[] }) => setSelId(e.newSelection && e.newSelection.length === 1 ? e.newSelection[0].id : null)
    bus.on('selection.changed', alCambiar)
    return () => bus.off('selection.changed', alCambiar)
  }, [m])

  const sel = m && selId ? m.get<{ get: (id: string) => Elemento | undefined }>('elementRegistry').get(selId) ?? null : null
  if (!m || !sel) return <div className="bpm-propiedades u-text2-sm">{t('bpm.props_selecciona')}</div>
  const bo = sel.businessObject
  const refrescar = () => setVersion(v => v + 1)
  const attr = (k: string) => bo.$attrs[`contecflow:${k}`] ?? ''
  const ponerAttr = (k: string, v: string) => {
    const defs = m.getDefinitions()
    defs.$attrs['xmlns:contecflow'] = CONTECFLOW_NS
    if (v) bo.$attrs[`contecflow:${k}`] = v
    else delete bo.$attrs[`contecflow:${k}`]
    refrescar()
  }
  const moddle = m.get<Moddle>('moddle')
  const modelado = m.get<Modelado>('modeling')
  const expresion = (body: string) => moddle.create('bpmn:FormalExpression', { body })
  const tipo = bo.$type
  const defs = bo.eventDefinitions ?? []
  const timer = defs.find(d => d.$type === 'bpmn:TimerEventDefinition')
  const msgDef = defs.find(d => d.$type === 'bpmn:MessageEventDefinition')
  const esHumana = HUMANAS.includes(tipo)
  const esServicio = SERVICIO.includes(tipo)
  const origen = bo.sourceRef?.$type

  const ponerMensaje = (nombre: string) => {
    const raiz = m.getDefinitions()
    const existentes = (raiz.rootElements ?? []).filter(r => r.$type === 'bpmn:Message')
    let msg = existentes.find(r => r.name === nombre)
    if (!msg && nombre) {
      msg = moddle.create('bpmn:Message', { id: `Message_${Math.random().toString(36).slice(2, 9)}`, name: nombre }) as ObjetoDeNegocio
      raiz.rootElements = [...(raiz.rootElements ?? []), msg]
    }
    if (tipo === 'bpmn:ReceiveTask') modelado.updateProperties(sel, { messageRef: msg ?? undefined })
    else if (msgDef) msgDef.messageRef = msg ?? undefined
    refrescar()
  }

  return (
    <div className="bpm-propiedades" aria-label={t('bpm.props_titulo')} role="group">
      <div className="u-md-700">{t('bpm.props_titulo')} · {sel.businessObject.name || sel.id}</div>
      {(esHumana || esServicio || tipo === 'bpmn:ExclusiveGateway' || tipo === 'bpmn:InclusiveGateway') && (
        <>
          <Input label={t('bpm.props_asignar_a')} value={attr('assignee')} onChange={e => ponerAttr('assignee', e.target.value)}
            placeholder="${initiator}" hint={t('bpm.props_asignar_a_ayuda')} />
          <Input label={t('bpm.props_grupos')} value={attr('candidateGroups')} onChange={e => ponerAttr('candidateGroups', e.target.value)}
            placeholder="pm, Compras" hint={t('bpm.props_grupos_ayuda')} />
        </>
      )}
      {esHumana && (
        <>
          <Input label={t('bpm.props_personas')} value={attr('candidateUsers')} onChange={e => ponerAttr('candidateUsers', e.target.value)} placeholder="ana@empresa.com" />
          <Input label={t('bpm.props_plazo')} value={attr('dueIn')} onChange={e => ponerAttr('dueIn', e.target.value)} placeholder="P2D" hint={t('bpm.props_plazo_ayuda')} />
          <Checkbox checked={attr('approval') === 'true'} onChange={v => ponerAttr('approval', v ? 'true' : '')} label={t('bpm.props_es_aprobacion')} />
          <Textarea label={t('bpm.props_formulario')} value={attr('formFields')} rows={4} onChange={e => ponerAttr('formFields', e.target.value)}
            placeholder='[{"name":"importe","label":"Importe","type":"number","required":true}]' hint={t('bpm.props_formulario_ayuda')} inputClassName="ds-codigo" />
        </>
      )}
      {esServicio && (
        <>
          <Select label={t('bpm.props_accion')} value={attr('action')} onChange={e => ponerAttr('action', e.target.value)}>
            {ACCIONES.map(a => <option key={a} value={a}>{a ? t(`bpm.accion_${a}`) : t('bpm.accion_ninguna')}</option>)}
          </Select>
          {attr('action') && (
            <>
              <Textarea label={t('bpm.props_config')} value={attr('actionConfig')} rows={3} onChange={e => ponerAttr('actionConfig', e.target.value)}
                placeholder={t('bpm.props_config_ejemplo')} hint={t('bpm.props_config_ayuda')} inputClassName="ds-codigo" />
              <Input label={t('bpm.props_reintentos')} type="number" min={0} max={20} value={attr('retries')} onChange={e => ponerAttr('retries', e.target.value)} />
            </>
          )}
        </>
      )}
      {tipo === 'bpmn:SequenceFlow' && (origen === 'bpmn:ExclusiveGateway' || origen === 'bpmn:InclusiveGateway') && (
        <Input label={t('bpm.props_condicion')} value={bo.conditionExpression?.body ?? ''} placeholder="importe > 1000"
          hint={t('bpm.props_condicion_ayuda')}
          onChange={e => { modelado.updateProperties(sel, { conditionExpression: e.target.value ? expresion(e.target.value) : undefined }); refrescar() }} />
      )}
      {timer && (
        <Input label={t('bpm.props_duracion')} value={timer.timeDuration?.body ?? ''} placeholder="PT2H"
          hint={t('bpm.props_plazo_ayuda')}
          onChange={e => { timer.timeDuration = expresion(e.target.value) as { body?: string }; refrescar() }} />
      )}
      {tipo === 'bpmn:BoundaryEvent' && (
        <Checkbox checked={bo.cancelActivity !== false} label={t('bpm.props_interrumpe')}
          onChange={v => { modelado.updateProperties(sel, { cancelActivity: v }); refrescar() }} />
      )}
      {(msgDef || tipo === 'bpmn:ReceiveTask') && (
        <Input label={t('bpm.props_mensaje')} value={(tipo === 'bpmn:ReceiveTask' ? bo.messageRef?.name : msgDef?.messageRef?.name) ?? ''}
          placeholder="pago_recibido" onChange={e => ponerMensaje(e.target.value.trim())} />
      )}
      {tipo === 'bpmn:CallActivity' && (
        <Input label={t('bpm.props_llamado')} value={bo.calledElement ?? ''} placeholder="alta_de_proveedor"
          hint={t('bpm.props_llamado_ayuda')}
          onChange={e => { modelado.updateProperties(sel, { calledElement: e.target.value }); refrescar() }} />
      )}
    </div>
  )
}

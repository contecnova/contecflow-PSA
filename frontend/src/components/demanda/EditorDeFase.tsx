/**
 * Editor de una fase de la definición del flujo de demanda (22-11-2026):
 * clave, nombres, tipo, pasos con responsable y quórum, decisiones permitidas,
 * salidas, plazos, segregación, avisos, puerta (gate) y comité.
 * Las opciones salen de `GET /demand/catalog`; la validación final es del servidor.
 */
import { useEffect, useState } from 'react'
import { ArrowDown, ArrowUp, ChevronDown, ChevronRight, Plus, Trash2 } from 'lucide-react'
import { Button, Checkbox, GrupoDeOpciones, Input, Select, IconButton } from '../ui'
import type { AvisoDeFlujo, CampoDeFlujo, CatalogoDeDemanda, CondicionDePuerta, DefinicionDeFlujo, FaseDeFlujo, PasoDeFlujo } from '../../services/api/demanda'
import { useAppT } from '../../i18n/AppLangContext'
import { CamposI18n, etiquetaDe, opcionesDe } from './comunes'
import { pasoNuevo, siguienteClave } from './utilDemanda'
import EditorDeCondiciones from './Condiciones'
import EditorDePlantillaResumen from './PlantillaResumen'
import './demanda.css'

type OpcionesVL = Array<{ value: string; label: string }>

/** Responsables que se resuelven solos, sin valor que elegir. */
const TIPOS_SIN_VALOR = ['requester', 'assignees', 'project_manager', 'client_manager', 'requester_manager', 'department_head']

/** Selector de valor de un asignado/aviso según su tipo; texto libre si no hay catálogo. */
function ValorPorTipo({ tipo, valor, onChange, catalogo, etiqueta, onEtiqueta }: {
  tipo: string; valor: string | undefined; onChange: (v: string) => void; catalogo: CatalogoDeDemanda
  etiqueta: string; onEtiqueta?: (l: string) => void
}) {
  const t = useAppT()
  const lista: OpcionesVL | null = tipo === 'role' ? catalogo.roles
    : tipo === 'group' || tipo === 'committee' ? catalogo.groups
      : tipo === 'user' ? catalogo.users
        : tipo === 'approval_workflow' ? catalogo.approval_workflows : null
  if (TIPOS_SIN_VALOR.includes(tipo)) return null
  if (lista && lista.length > 0) {
    return (
      <Select label={etiqueta} value={valor ?? ''} options={lista}
        onChange={e => { onChange(e.target.value); const o = lista.find(x => x.value === e.target.value); if (o && onEtiqueta) onEtiqueta(o.label) }} />
    )
  }
  return <Input label={etiqueta} value={valor ?? ''} placeholder={t('demanda.cfg_valor_libre')} onChange={e => onChange(e.target.value)} />
}

function Avisos({ avisos, onChange, catalogo }: { avisos: AvisoDeFlujo[]; onChange: (a: AvisoDeFlujo[]) => void; catalogo: CatalogoDeDemanda }) {
  const t = useAppT()
  const eventos = catalogo.notify_events.length ? catalogo.notify_events : ['enter', 'decision', 'sla_warning', 'sla_breach', 'info_requested', 'closed']
  const destinos = catalogo.notify_targets?.length ? catalogo.notify_targets : ['requester', 'assignees', 'role', 'group', 'user']
  const poner = (i: number, a: AvisoDeFlujo) => onChange(avisos.map((x, j) => j === i ? a : x))
  return (
    <div className="dem-bloque">
      <div className="dem-bloque__titulo">{t('demanda.cfg_avisos')}</div>
      {avisos.map((a, i) => (
        <div key={i} className="dem-rejilla">
          <Select label={t('demanda.cfg_evento')} placeholder={false} value={a.event} onChange={e => poner(i, { ...a, event: e.target.value })} options={opcionesDe(t, 'evento', eventos)} />
          <Select label={t('demanda.cfg_destinatario')} placeholder={false} value={a.to.type} onChange={e => poner(i, { ...a, to: { type: e.target.value } })} options={opcionesDe(t, 'destino', destinos)} />
          <ValorPorTipo tipo={a.to.type} valor={a.to.value} catalogo={catalogo} etiqueta={t('demanda.cfg_valor')} onChange={v => poner(i, { ...a, to: { ...a.to, value: v } })} />
          <div><Button size="xs" variant="ghost" icon={<Trash2 size={12} />} onClick={() => onChange(avisos.filter((_, j) => j !== i))}>{t('demanda.cfg_quitar')}</Button></div>
        </div>
      ))}
      <div><Button size="xs" variant="subtle" icon={<Plus size={12} />} onClick={() => onChange([...avisos, { event: eventos[0], to: { type: 'requester' } }])}>{t('demanda.cfg_anadir_aviso')}</Button></div>
    </div>
  )
}

function Pasos({ fase, onChange, catalogo }: { fase: FaseDeFlujo; onChange: (f: FaseDeFlujo) => void; catalogo: CatalogoDeDemanda }) {
  const t = useAppT()
  const tipos = catalogo.assignee_types.length ? catalogo.assignee_types : ['role', 'group', 'user', 'department', 'committee', 'approval_workflow', 'requester', 'project_manager', 'client_manager', 'requester_manager', 'department_head', 'supplier']
  const modos = catalogo.step_modes?.length ? catalogo.step_modes : ['task', 'approval']
  const quorums = catalogo.quorums?.length ? catalogo.quorums : ['any', 'all', 'majority']
  const poner = (i: number, p: PasoDeFlujo) => onChange({ ...fase, steps: fase.steps.map((x, j) => j === i ? p : x) })
  return (
    <div className="dem-bloque">
      <div className="dem-bloque__titulo">{t('demanda.cfg_pasos')}</div>
      {fase.steps.map((p, i) => (
        <div key={i} className="dem-bloque">
          <div className="dem-rejilla">
            <Input label={t('demanda.cfg_clave')} required inputClassName="u-mono dem-mono" value={p.key} onChange={e => poner(i, { ...p, key: e.target.value })} />
            <Select label={t('demanda.cfg_modo_paso')} placeholder={false} value={p.mode} onChange={e => poner(i, { ...p, mode: e.target.value })} options={opcionesDe(t, 'paso_modo', modos)} />
            <Select label={t('demanda.cfg_asignado_tipo')} placeholder={false} value={p.assignee.type} onChange={e => poner(i, { ...p, assignee: { type: e.target.value, value: '', label: '' } })} options={opcionesDe(t, 'asig', tipos)} />
            <ValorPorTipo tipo={p.assignee.type} valor={p.assignee.value} catalogo={catalogo} etiqueta={t('demanda.cfg_asignado_valor')}
              onChange={v => poner(i, { ...p, assignee: { ...p.assignee, value: v } })}
              onEtiqueta={l => poner(i, { ...p, assignee: { ...p.assignee, label: p.assignee.label || l } })} />
            <Input label={t('demanda.cfg_asignado_etiqueta')} value={p.assignee.label ?? ''} onChange={e => poner(i, { ...p, assignee: { ...p.assignee, label: e.target.value } })} />
            {['group', 'committee'].includes(p.assignee.type) && (
              <Select label={t('demanda.cfg_quorum')} placeholder={false} value={p.quorum ?? 'any'} onChange={e => poner(i, { ...p, quorum: e.target.value })} options={opcionesDe(t, 'quorum', quorums)} />
            )}
          </div>
          <CamposI18n etiqueta={t('demanda.cfg_nombre')} valor={p.name} requeridoEs onChange={v => poner(i, { ...p, name: v })} />
          <div className="dem-fila dem-fila--entre">
            <Checkbox label={t('demanda.cfg_paso_opcional')} checked={!!p.optional} onChange={ok => poner(i, { ...p, optional: ok })} />
            <Button size="xs" variant="ghost" icon={<Trash2 size={12} />} onClick={() => onChange({ ...fase, steps: fase.steps.filter((_, j) => j !== i) })}>{t('demanda.cfg_quitar_paso')}</Button>
          </div>
        </div>
      ))}
      <div><Button size="xs" variant="subtle" icon={<Plus size={12} />} onClick={() => onChange({ ...fase, steps: [...fase.steps, pasoNuevo(siguienteClave('paso', fase.steps.map(s => s.key)))] })}>{t('demanda.cfg_anadir_paso')}</Button></div>
    </div>
  )
}

function Puerta({ fase, onChange, def, catalogo, destinos }: {
  fase: FaseDeFlujo; onChange: (f: FaseDeFlujo) => void; def: DefinicionDeFlujo; catalogo: CatalogoDeDemanda; destinos: OpcionesVL
}) {
  const t = useAppT()
  const g = fase.gate ?? { conditions: [], match: 'any', use_policies: false, if_true: 'next', if_false: 'end:approved', allow_bypass: false }
  const poner = (parche: Partial<typeof g>) => onChange({ ...fase, gate: { ...g, ...parche } })
  const ops = catalogo.condition_ops.length ? catalogo.condition_ops : ['gt', 'gte', 'lt', 'lte', 'eq', 'neq', 'in']
  const camposOpc: OpcionesVL = def.fields.map(c => ({ value: c.key, label: `${c.label.es || c.key} (${c.key})` }))
  const ponerCond = (i: number, c: CondicionDePuerta) => poner({ conditions: g.conditions.map((x, j) => j === i ? c : x) })
  const valorTexto = (v: unknown) => v === null || v === undefined ? '' : String(v)
  const aValor = (s: string): unknown => s.trim() !== '' && !Number.isNaN(Number(s)) ? Number(s) : s === 'true' ? true : s === 'false' ? false : s
  return (
    <div className="dem-bloque">
      <div className="dem-bloque__titulo">{t('demanda.cfg_puerta')}</div>
      {g.conditions.map((c, i) => (
        <div key={i} className="dem-rejilla">
          <Select label={t('demanda.cfg_condicion_campo')} value={c.field} onChange={e => ponerCond(i, { ...c, field: e.target.value })} options={camposOpc} />
          <Select label={t('demanda.cfg_condicion_op')} placeholder={false} value={c.op} onChange={e => ponerCond(i, { ...c, op: e.target.value })} options={opcionesDe(t, 'op', ops)} />
          <Input label={t('demanda.cfg_condicion_valor')} value={valorTexto(c.value)} onChange={e => ponerCond(i, { ...c, value: aValor(e.target.value) })} />
          <div><Button size="xs" variant="ghost" icon={<Trash2 size={12} />} onClick={() => poner({ conditions: g.conditions.filter((_, j) => j !== i) })}>{t('demanda.cfg_quitar')}</Button></div>
        </div>
      ))}
      <div><Button size="xs" variant="subtle" icon={<Plus size={12} />} onClick={() => poner({ conditions: [...g.conditions, { field: def.fields[0]?.key ?? '', op: ops[0], value: '' }] })}>{t('demanda.cfg_anadir_condicion')}</Button></div>
      <div className="dem-rejilla">
        <Select label={t('demanda.cfg_match')} placeholder={false} value={g.match} onChange={e => poner({ match: e.target.value })} options={opcionesDe(t, 'match', ['any', 'all'])} />
        <Select label={t('demanda.cfg_si_cumple')} placeholder={false} value={g.if_true} onChange={e => poner({ if_true: e.target.value })} options={destinos} />
        <Select label={t('demanda.cfg_si_no_cumple')} placeholder={false} value={g.if_false} onChange={e => poner({ if_false: e.target.value })} options={destinos} />
      </div>
      <Checkbox label={t('demanda.cfg_usar_politicas')} ayuda={t('demanda.cfg_usar_politicas_ayuda')} checked={!!g.use_policies} onChange={ok => poner({ use_policies: ok })} />
      <Checkbox label={t('demanda.cfg_permitir_bypass')} ayuda={t('demanda.cfg_permitir_bypass_ayuda')} checked={!!g.allow_bypass} onChange={ok => poner({ allow_bypass: ok })} />
    </div>
  )
}

export interface EditorDeFaseProps {
  fase: FaseDeFlujo; indice: number; total: number; def: DefinicionDeFlujo; catalogo: CatalogoDeDemanda
  onChange: (f: FaseDeFlujo) => void; onBorrar: () => void; onMover: (dir: -1 | 1) => void
  /** Cambio de clave: el padre actualiza las referencias en el resto de fases. */
  onRenombrar: (de: string, a: string) => void
  /** Abre la fase (p. ej. al pulsar su nodo en el diagrama). */
  forzarAbierta?: boolean
}

export default function EditorDeFase({ fase, indice, total, def, catalogo, onChange, onBorrar, onMover, onRenombrar, forzarAbierta }: EditorDeFaseProps) {
  const t = useAppT()
  const [abierta, setAbierta] = useState(!!forzarAbierta)
  useEffect(() => { if (forzarAbierta) setAbierta(true) }, [forzarAbierta])
  // La clave se confirma al salir del campo: renombrar arrastra las referencias de las demás fases.
  const [claveLocal, setClaveLocal] = useState(fase.key)
  useEffect(() => { setClaveLocal(fase.key) }, [fase.key])
  const tipos = catalogo.phase_kinds.length ? catalogo.phase_kinds : ['intake', 'work', 'review', 'approval', 'gate', 'committee']
  const decisiones = catalogo.decisions.length ? catalogo.decisions : ['approve', 'complete', 'reject', 'return', 'request_info', 'skip', 'hold', 'fast_track', 'to_committee']
  const tags = catalogo.document_tags
  const otras = def.phases.filter(f => f.key !== fase.key).map(f => f.key)
  const destinos: OpcionesVL = [
    { value: 'next', label: t('demanda.cfg_destino_next') },
    ...def.phases.map(f => ({ value: f.key, label: f.name.es || f.key })),
    { value: 'end:approved', label: t('demanda.cfg_destino_aprobada') },
    { value: 'end:rejected', label: t('demanda.cfg_destino_rechazada') },
  ]
  const poner = (parche: Partial<FaseDeFlujo>) => onChange({ ...fase, ...parche })
  const marcasDeCampos: CampoDeFlujo[] = def.fields
  const seg = fase.segregation ?? {}
  const numero = (v: string) => v === '' ? null : Number(v)
  return (
    <div className="dem-bloque">
      <div className="dem-fila dem-fila--entre">
        <Button size="sm" variant="subtle" icon={abierta ? <ChevronDown size={13} /> : <ChevronRight size={13} />} onClick={() => setAbierta(a => !a)}>
          {indice + 1}. {fase.name.es || fase.key} <span className="u-mono dem-mono">({fase.key})</span> · {etiquetaDe(t, 'kind', fase.kind)}
        </Button>
        <span className="dem-fila">
          <IconButton variante="caja" ariaLabel={t('demanda.cfg_subir')} disabled={indice === 0} onClick={() => onMover(-1)}><ArrowUp size={12} /></IconButton>
          <IconButton variante="caja" ariaLabel={t('demanda.cfg_bajar')} disabled={indice === total - 1} onClick={() => onMover(1)}><ArrowDown size={12} /></IconButton>
          <Button size="xs" variant="ghost" icon={<Trash2 size={12} />} onClick={onBorrar}>{t('demanda.cfg_quitar_fase')}</Button>
        </span>
      </div>
      {abierta && (
        <div className="dem-editor">
          <div className="dem-rejilla">
            <Input label={t('demanda.cfg_clave')} required inputClassName="u-mono dem-mono" value={claveLocal} hint={t('demanda.cfg_clave_ayuda')} onChange={e => setClaveLocal(e.target.value)}
              onBlur={() => { const k = claveLocal.trim(); if (k && k !== fase.key) onRenombrar(fase.key, k); else setClaveLocal(fase.key) }} />
            <Select label={t('demanda.cfg_tipo_fase')} placeholder={false} value={fase.kind} onChange={e => poner({ kind: e.target.value })} options={opcionesDe(t, 'kind', tipos)} />
            <Select label={t('demanda.cfg_etiqueta_documentos')} value={fase.documents_tag ?? ''} onChange={e => poner({ documents_tag: e.target.value || null })} options={opcionesDe(t, 'tag', tags)} />
          </div>
          <CamposI18n etiqueta={t('demanda.cfg_nombre')} valor={fase.name} requeridoEs onChange={v => poner({ name: v })} />
          <Checkbox label={t('demanda.cfg_paralelo')} ayuda={t('demanda.cfg_paralelo_ayuda')} checked={!!fase.parallel} onChange={ok => poner({ parallel: ok })} />
          {fase.kind !== 'gate' && <Pasos fase={fase} onChange={onChange} catalogo={catalogo} />}
          <GrupoDeOpciones tipo="checkbox" forma="fila" leyenda={t('demanda.cfg_decisiones')} valor={fase.decisions} onChange={v => poner({ decisions: v })}
            opciones={decisiones.map(d => ({ valor: d, titulo: etiquetaDe(t, 'dec', d) }))} />
          <div className="dem-rejilla">
            <Select label={t('demanda.cfg_on_approve')} placeholder={false} value={fase.on_approve} onChange={e => poner({ on_approve: e.target.value })} options={destinos} />
            <Select label={t('demanda.cfg_on_reject')} placeholder={false} value={fase.on_reject} onChange={e => poner({ on_reject: e.target.value })} options={destinos} />
          </div>
          {otras.length > 0 && (
            <GrupoDeOpciones tipo="checkbox" forma="fila" leyenda={t('demanda.cfg_return_targets')} valor={fase.return_targets || []} onChange={v => poner({ return_targets: v })}
              opciones={otras.map(k => ({ valor: k, titulo: k }))} />
          )}
          {marcasDeCampos.length > 0 && (
            <GrupoDeOpciones tipo="checkbox" forma="fila" leyenda={t('demanda.cfg_required_fields')} valor={fase.required_fields || []} onChange={v => poner({ required_fields: v })}
              opciones={marcasDeCampos.map(c => ({ valor: c.key, titulo: c.label.es || c.key }))} />
          )}
          {marcasDeCampos.length > 0 && (
            <GrupoDeOpciones tipo="checkbox" forma="fila" leyenda={t('demanda.cfg_internal_editable')} valor={fase.internal_editable || []} onChange={v => poner({ internal_editable: v })}
              opciones={marcasDeCampos.map(c => ({ valor: c.key, titulo: c.label.es || c.key }))} />
          )}
          <div className="dem-rejilla">
            <Checkbox label={t('demanda.cfg_client_editable')} checked={!!fase.client_editable} onChange={ok => poner({ client_editable: ok })} />
            <Checkbox label={t('demanda.cfg_lock_client')} ayuda={t('demanda.cfg_lock_client_ayuda')} checked={!!fase.lock_client_from_here} onChange={ok => poner({ lock_client_from_here: ok })} />
            <Checkbox label={t('demanda.cfg_pause_on_info')} ayuda={t('demanda.cfg_pause_on_info_ayuda')} checked={!!fase.pause_on_info} onChange={ok => poner({ pause_on_info: ok })} />
          </div>
          <div className="dem-rejilla">
            <Input label={t('demanda.cfg_sla_horas')} type="number" min={0} value={fase.sla_hours ?? ''} onChange={e => poner({ sla_hours: numero(e.target.value) })} />
            <Input label={t('demanda.cfg_sla_aviso')} type="number" min={0} max={100} value={fase.sla_warn_pct ?? ''} onChange={e => poner({ sla_warn_pct: numero(e.target.value) })} />
          </div>
          <div className="dem-bloque">
            <div className="dem-bloque__titulo">{t('demanda.cfg_segregacion')}</div>
            <Checkbox label={t('demanda.cfg_no_solicitante')} checked={seg.not_requester !== false} onChange={ok => poner({ segregation: { ...seg, not_requester: ok } })} />
            {otras.length > 0 && (
              <GrupoDeOpciones tipo="checkbox" forma="fila" leyenda={t('demanda.cfg_no_actor_fases')} valor={seg.not_actor_of_phases || []} onChange={v => poner({ segregation: { ...seg, not_actor_of_phases: v } })}
                opciones={otras.map(k => ({ valor: k, titulo: k }))} />
            )}
          </div>
          {def.fields.length > 0 && (
            <GrupoDeOpciones tipo="checkbox" forma="fila" leyenda={t('demanda.cfg_locked_fields')} valor={fase.locked_fields || []} onChange={v => poner({ locked_fields: v })}
              opciones={def.fields.map(c => ({ valor: c.key, titulo: c.label.es || c.key }))} />
          )}
          <div className="dem-bloque">
            <div className="dem-bloque__titulo">{t('demanda.cfg_destinos_por_decision')}</div>
            <p className="plan-muted">{t('demanda.cfg_destinos_ayuda')}</p>
            <div className="dem-rejilla">
              {(['approve', 'reject', 'hold'] as const).map(dec => (
                <Select key={dec} label={etiquetaDe(t, 'dec', dec)} placeholder={t('demanda.cfg_destino_por_defecto')} value={fase.targets?.[dec] ?? ''}
                  onChange={e => poner({ targets: { ...fase.targets, [dec]: e.target.value || undefined } })} options={destinos} />
              ))}
            </div>
          </div>
          <div className="dem-bloque">
            <div className="dem-bloque__titulo">{t('demanda.cfg_fase_condicional')}</div>
            <p className="plan-muted">{t('demanda.cfg_fase_condicional_ayuda')}</p>
            {fase.condition ? (
              <>
                <EditorDeCondiciones valor={fase.condition} def={def} catalogo={catalogo} onChange={v => poner({ condition: v })} />
                <div><Button size="xs" variant="ghost" icon={<Trash2 size={12} />} onClick={() => poner({ condition: undefined })}>{t('demanda.cfg_quitar_condicion_fase')}</Button></div>
              </>
            ) : (
              <div><Button size="xs" variant="subtle" icon={<Plus size={12} />} onClick={() => poner({ condition: { conditions: [], match: 'any', use_policies: false } })}>{t('demanda.cfg_hacer_condicional')}</Button></div>
            )}
          </div>
          <div className="dem-bloque">
            <div className="dem-bloque__titulo">{t('demanda.cfg_escalado')}</div>
            <p className="plan-muted">{t('demanda.cfg_escalado_ayuda')}</p>
            {fase.escalation ? (
              <>
                <div className="dem-rejilla">
                  <Select label={t('demanda.cfg_asignado_tipo')} placeholder={false} value={fase.escalation.to.type} onChange={e => poner({ escalation: { to: { type: e.target.value, value: '', label: '' } } })} options={opcionesDe(t, 'asig', tipos)} />
                  <ValorPorTipo tipo={fase.escalation.to.type} valor={fase.escalation.to.value} catalogo={catalogo} etiqueta={t('demanda.cfg_asignado_valor')}
                    onChange={v => poner({ escalation: { to: { ...fase.escalation!.to, value: v } } })}
                    onEtiqueta={l => poner({ escalation: { to: { ...fase.escalation!.to, label: fase.escalation!.to.label || l } } })} />
                  <Input label={t('demanda.cfg_asignado_etiqueta')} value={fase.escalation.to.label ?? ''} onChange={e => poner({ escalation: { to: { ...fase.escalation!.to, label: e.target.value } } })} />
                </div>
                <div><Button size="xs" variant="ghost" icon={<Trash2 size={12} />} onClick={() => poner({ escalation: undefined })}>{t('demanda.cfg_quitar_escalado')}</Button></div>
              </>
            ) : (
              <div><Button size="xs" variant="subtle" icon={<Plus size={12} />} onClick={() => poner({ escalation: { to: { type: 'role', value: '', label: '' } } })}>{t('demanda.cfg_anadir_escalado')}</Button></div>
            )}
          </div>
          <Avisos avisos={fase.notify || []} onChange={n => poner({ notify: n })} catalogo={catalogo} />
          {fase.kind === 'gate' && <Puerta fase={fase} onChange={onChange} def={def} catalogo={catalogo} destinos={destinos} />}
          {fase.kind === 'committee' && (
            <div className="dem-bloque">
              <Checkbox label={t('demanda.cfg_resumen_ejecutivo')} ayuda={t('demanda.cfg_resumen_ejecutivo_ayuda')} checked={!!fase.committee?.executive_summary}
                onChange={ok => poner({ committee: { ...fase.committee, executive_summary: ok } })} />
              {!!fase.committee?.executive_summary && (
                <EditorDePlantillaResumen def={def} valor={typeof fase.committee.executive_summary === 'object' ? fase.committee.executive_summary : {}}
                  onChange={v => poner({ committee: { ...fase.committee, executive_summary: v } })} />
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

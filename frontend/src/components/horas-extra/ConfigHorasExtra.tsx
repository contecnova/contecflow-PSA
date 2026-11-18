/**
 * «Configuración» de horas extra (18-11-2026, admin/RRHH): GET/PUT
 * /overtime/config, presupuestos (/overtime/budgets), regularizar un periodo
 * (POST /overtime/regularize), enlace a Políticas del dominio `horas_extra` y
 * «Cargar reglas de ejemplo» (POST /policies/examples/horas_extra, borradores).
 */
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Pencil, Plus, RefreshCw, Save, Scale, Sparkles, Trash2 } from 'lucide-react'
import {
  horasExtraApi, AMBITOS_HE, COMPENSACIONES_HE, CONTROLES_HE,
  type AmbitoPresupuesto, type CompensacionHe, type ConfigHe, type ConfigHeIn, type ControlImputacion, type PresupuestoHe,
  type PresupuestoHeIn,
} from '../../services/api/horas-extra'
import {
  Button, Checkbox, GrupoDeOpciones, Input, LoadBar, Modal, ProjectSelect, FormField, Section, Select, Spinner, StatusBadge, Switch,
  Tabla, type ColumnaTabla,
} from '../ui'
import { confirmar } from '../../context/ConfirmContext'
import { useToast } from '../../context/ToastContext'
import { extractErr, fmtNumber } from '../../utils/helpers'
import { nivelDeConsumo, pctDePresupuesto } from './logica'
import { AvisoDeError, TONO_DE_NIVEL, fechaHora, horas, useConfigHe, useTh } from './comun'

export default function ConfigHorasExtra() {
  const { th } = useTh()
  const config = useConfigHe()
  if (config.isLoading) return <Spinner label={th('cargando')} />
  if (config.isError || !config.data) return <AvisoDeError error={config.error} />
  return (
    <div className="hext-panel">
      <Ajustes key={config.data.updated_at ?? 'base'} c={config.data} />
      <Presupuestos />
      <Regularizar />
      <Reglas />
    </div>
  )
}

const aEntrada = (c: ConfigHe): ConfigHeIn => ({
  activo: c.activo, control_imputacion: c.control_imputacion, tolerancia_minutos: c.tolerancia_minutos,
  compensaciones: c.compensaciones, compensacion_por_defecto: c.compensacion_por_defecto, workflow_id: c.workflow_id,
  tipo_bolsa_id: c.tipo_bolsa_id, pedir_en_nombre: c.pedir_en_nombre, exigir_motivo: c.exigir_motivo,
})

function Ajustes({ c }: { c: ConfigHe }) {
  const { th } = useTh()
  const qc = useQueryClient()
  const toast = useToast()
  const [v, setV] = useState<ConfigHeIn>(() => aEntrada(c))
  const poner = (x: Partial<ConfigHeIn>) => setV(a => ({ ...a, ...x }))
  const guardar = useMutation({
    mutationFn: () => horasExtraApi.guardarConfig(v),
    onSuccess: d => { qc.setQueryData(['horas-extra', 'config'], d); qc.invalidateQueries({ queryKey: ['horas-extra'] }); toast.success(th('config_guardada')) },
  })
  const soloLectura = !c.puede_editar
  const defectoValido = v.compensaciones.includes(v.compensacion_por_defecto)
  return (
    <Section title={th('config_titulo')} subtitle={c.updated_at ? th('config_actualizada', { cuando: fechaHora(c.updated_at), quien: c.updated_by ?? '—' }) : th('config_ayuda')}>
      <div className="hext-rejilla">
        <Switch className="hext-rejilla--ancho" label={th('activo')} ayuda={th('activo_ayuda')} checked={v.activo} disabled={soloLectura}
          onChange={m => poner({ activo: m })} />
        <Select label={th('control_imputacion')} value={v.control_imputacion} placeholder={false} disabled={soloLectura}
          hint={th(`control_${v.control_imputacion}_ayuda`)}
          onChange={e => poner({ control_imputacion: e.target.value as ControlImputacion })}
          options={CONTROLES_HE.map(x => ({ value: x, label: th(`control_${x}`) }))} />
        <Input type="number" label={th('tolerancia_minutos')} hint={th('tolerancia_ayuda')} min={0} max={240} step={5} disabled={soloLectura}
          value={v.tolerancia_minutos} onChange={e => poner({ tolerancia_minutos: Math.max(0, Number(e.target.value) || 0) })} />
        <GrupoDeOpciones tipo="checkbox" forma="fila" leyenda={th('compensaciones_permitidas')} valor={v.compensaciones} disabled={soloLectura}
          onChange={x => poner({ compensaciones: x as CompensacionHe[] })}
          opciones={COMPENSACIONES_HE.map(x => ({ valor: x, titulo: th(`compensacion_${x}`) }))} />
        <Select label={th('compensacion_por_defecto')} value={v.compensacion_por_defecto} placeholder={false} disabled={soloLectura}
          error={defectoValido ? undefined : th('defecto_no_permitida')}
          onChange={e => poner({ compensacion_por_defecto: e.target.value as CompensacionHe })}
          options={COMPENSACIONES_HE.map(x => ({ value: x, label: th(`compensacion_${x}`) }))} />
        <Select label={th('flujo_aprobacion')} value={v.workflow_id ?? ''} placeholder={th('sin_flujo_responsable')} disabled={soloLectura}
          hint={th('flujo_ayuda')} onChange={e => poner({ workflow_id: e.target.value || null })}
          options={c.flujos.map(f => ({ value: f.id, label: f.name }))} />
        <Select label={th('tipo_bolsa')} value={v.tipo_bolsa_id ?? ''} placeholder={th('sin_bolsa')} disabled={soloLectura}
          hint={th('tipo_bolsa_ayuda')} onChange={e => poner({ tipo_bolsa_id: e.target.value || null })}
          options={c.tipos_de_bolsa.map(f => ({ value: f.id, label: f.nombre }))} />
        <Checkbox label={th('pedir_en_nombre')} ayuda={th('pedir_en_nombre_ayuda')} checked={v.pedir_en_nombre} disabled={soloLectura}
          onChange={m => poner({ pedir_en_nombre: m })} />
        <Checkbox label={th('exigir_motivo')} checked={v.exigir_motivo} disabled={soloLectura} onChange={m => poner({ exigir_motivo: m })} />
      </div>
      <AvisoDeError error={guardar.error} />
      {!soloLectura && (
        <div className="hext-acciones">
          <Button icon={<Save size={14} />} loading={guardar.isPending} disabled={!v.compensaciones.length || !defectoValido}
            onClick={() => guardar.mutate()}>{th('guardar')}</Button>
        </div>
      )}
    </Section>
  )
}

const presupuestoNuevo = (): PresupuestoHeIn => ({
  ambito: 'empresa', valor: null, periodo: 'anio', anio: new Date().getFullYear(), horas: 0, nota: null, activo: true,
})

function Presupuestos() {
  const { th } = useTh()
  const qc = useQueryClient()
  const toast = useToast()
  const q = useQuery({ queryKey: ['horas-extra', 'presupuestos'], queryFn: () => horasExtraApi.presupuestos() })
  const [editando, setEditando] = useState<{ id: string | null; v: PresupuestoHeIn } | null>(null)
  const borrar = useMutation({
    mutationFn: (id: string) => horasExtraApi.borrarPresupuesto(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['horas-extra'] }); toast.success(th('presupuesto_borrado')) },
    onError: e => toast.error(extractErr(e, th('error'))),
  })
  const pedirBorrar = async (p: PresupuestoHe) => {
    if (await confirmar({ title: th('borrar_presupuesto'), message: th('borrar_presupuesto_texto', { nombre: p.etiqueta }), danger: true })) borrar.mutate(p.id)
  }
  const columnas: Array<ColumnaTabla<PresupuestoHe>> = [
    { key: 'ambito', label: th('ambito'), render: (_, p) => th(`ambito_${p.ambito}`) },
    { key: 'etiqueta', label: th('aplica_a'), cabeceraDeFila: true },
    { key: 'periodo', label: th('periodo'), render: (_, p) => `${th(`periodo_${p.periodo}`)}${p.anio ? ` · ${p.anio}` : ''}` },
    { key: 'horas', label: th('horas'), alinear: 'derecha', render: (_, p) => horas(p.horas) },
    { key: 'consumidas', label: th('consumidas'), alinear: 'derecha', render: (_, p) => horas(p.consumidas) },
    { key: 'restantes', label: th('restantes'), alinear: 'derecha', render: (_, p) => <span className={p.restantes < 0 ? 'hext-negativo' : ''}>{horas(p.restantes)}</span> },
    { key: 'consumo', label: th('consumo'), sortable: false, render: (_, p) => {
      const pct = pctDePresupuesto(p) ?? 0
      return (
        <div className="hext-consumo">
          <LoadBar value={pct} max={100} label={th('consumo_pct', { pct: fmtNumber(pct, 0) })} />
          <StatusBadge kind={TONO_DE_NIVEL[nivelDeConsumo(pct)]}>{fmtNumber(pct, 0)} %</StatusBadge>
        </div>
      )
    } },
    { key: 'activo', label: th('activo'), render: (_, p) => (p.activo ? th('si') : th('no')) },
    { key: 'acciones', label: <span className="u-sr-only">{th('acciones')}</span>, sortable: false, render: (_, p) => (
      <span className="hext-acciones">
        <Button size="xs" variant="ghost" icon={<Pencil size={12} />} onClick={() => setEditando({ id: p.id, v: {
          ambito: p.ambito, valor: p.valor, periodo: p.periodo, anio: p.anio, horas: p.horas, nota: p.nota, activo: p.activo,
        } })}>{th('editar')}</Button>
        <Button size="xs" variant="ghost" icon={<Trash2 size={12} />} onClick={() => pedirBorrar(p)}>{th('borrar')}</Button>
      </span>
    ) },
  ]
  return (
    <Section title={th('presupuestos')} subtitle={th('presupuestos_ayuda')}
      actions={<Button size="sm" icon={<Plus size={14} />} onClick={() => setEditando({ id: null, v: presupuestoNuevo() })}>{th('nuevo_presupuesto')}</Button>}>
      {q.isError && <AvisoDeError error={q.error} />}
      <Tabla etiqueta={th('presupuestos')} filas={q.data ?? []} columnas={columnas} claveDeFila={p => p.id} cargando={q.isLoading}
        vacio={{ titulo: th('sin_presupuestos') }} />
      {editando && <EditorDePresupuesto id={editando.id} inicial={editando.v} onCerrar={() => setEditando(null)} />}
    </Section>
  )
}

function EditorDePresupuesto({ id, inicial, onCerrar }: { id: string | null; inicial: PresupuestoHeIn; onCerrar: () => void }) {
  const { th } = useTh()
  const qc = useQueryClient()
  const toast = useToast()
  const [v, setV] = useState(inicial)
  const poner = (x: Partial<PresupuestoHeIn>) => setV(a => ({ ...a, ...x }))
  const guardar = useMutation({
    mutationFn: () => (id ? horasExtraApi.guardarPresupuesto(id, v) : horasExtraApi.crearPresupuesto(v)),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['horas-extra'] }); toast.success(th('presupuesto_guardado')); onCerrar() },
  })
  const valido = v.horas > 0 && (v.ambito === 'empresa' || Boolean(v.valor))
  return (
    <Modal open onClose={onCerrar} title={id ? th('editar_presupuesto') : th('nuevo_presupuesto')}>
      <div className="hext-rejilla">
        <Select label={th('ambito')} value={v.ambito} placeholder={false}
          onChange={e => poner({ ambito: e.target.value as AmbitoPresupuesto, valor: null })}
          options={AMBITOS_HE.map(x => ({ value: x, label: th(`ambito_${x}`) }))} />
        {v.ambito === 'proyecto' && (
          <FormField label={th('proyecto')} required>
            <ProjectSelect value={v.valor ?? ''} onChange={x => poner({ valor: x || null })} />
          </FormField>
        )}
        {(v.ambito === 'equipo' || v.ambito === 'departamento') && (
          <Input label={th(v.ambito)} required value={v.valor ?? ''} onChange={e => poner({ valor: e.target.value || null })} />
        )}
        <Select label={th('periodo')} value={v.periodo} placeholder={false} onChange={e => poner({ periodo: e.target.value as 'mes' | 'anio' })}
          options={[{ value: 'mes', label: th('periodo_mes') }, { value: 'anio', label: th('periodo_anio') }]} />
        <Input type="number" label={th('anio')} hint={th('anio_ayuda')} min={2000} max={2100} value={v.anio ?? ''}
          onChange={e => poner({ anio: e.target.value ? Number(e.target.value) : null })} />
        <Input type="number" label={th('horas')} required min={0} step={0.5} value={v.horas}
          onChange={e => poner({ horas: Math.max(0, Number(e.target.value) || 0) })} />
        <Input className="hext-rejilla--ancho" label={th('nota')} value={v.nota ?? ''} maxLength={500} onChange={e => poner({ nota: e.target.value || null })} />
        <Checkbox label={th('activo')} checked={v.activo} onChange={m => poner({ activo: m })} />
      </div>
      <AvisoDeError error={guardar.error} />
      <div className="hext-acciones">
        <Button variant="ghost" onClick={onCerrar}>{th('cancelar')}</Button>
        <Button icon={<Save size={14} />} loading={guardar.isPending} disabled={!valido} onClick={() => guardar.mutate()}>{th('guardar')}</Button>
      </div>
    </Modal>
  )
}

function Regularizar() {
  const { th } = useTh()
  const qc = useQueryClient()
  const toast = useToast()
  const hoy = new Date().toISOString().slice(0, 10)
  const [desde, setDesde] = useState(`${hoy.slice(0, 7)}-01`)
  const [hasta, setHasta] = useState(hoy)
  const m = useMutation({
    mutationFn: () => horasExtraApi.regularizar(desde, hasta),
    onSuccess: r => { qc.invalidateQueries({ queryKey: ['horas-extra'] }); toast.success(th('regularizado', r)) },
  })
  return (
    <Section title={th('regularizar')} subtitle={th('regularizar_ayuda')}>
      <div className="hext-decidir">
        <Input type="date" label={th('desde')} value={desde} max={hasta} onChange={e => setDesde(e.target.value)} />
        <Input type="date" label={th('hasta')} value={hasta} min={desde} onChange={e => setHasta(e.target.value)} />
        <Button variant="secondary" icon={<RefreshCw size={14} />} loading={m.isPending} disabled={!desde || !hasta || hasta < desde}
          onClick={() => m.mutate()}>{th('regularizar_periodo')}</Button>
      </div>
      <AvisoDeError error={m.error} />
    </Section>
  )
}

function Reglas() {
  const { th } = useTh()
  const qc = useQueryClient()
  const toast = useToast()
  const m = useMutation({
    mutationFn: horasExtraApi.cargarEjemplos,
    onSuccess: r => {
      qc.invalidateQueries({ queryKey: ['politicas'] })
      toast.success(r.politicas_creadas || r.tablas_creadas?.length
        ? th('ejemplos_cargados', { n: r.politicas_creadas, tablas: r.tablas_creadas?.length ?? 0 })
        : th('ejemplos_ya_estaban'))
    },
    onError: e => toast.error(extractErr(e, th('error'))),
  })
  return (
    <Section title={th('reglas')} subtitle={th('reglas_ayuda')}>
      <div className="hext-fila">
        <Link className="hext-enlace" to="/settings/policies?dominio=horas_extra"><Scale size={14} aria-hidden /> {th('ir_a_politicas')}</Link>
        <Button variant="secondary" icon={<Sparkles size={14} />} loading={m.isPending} onClick={() => m.mutate()}>{th('cargar_ejemplos')}</Button>
      </div>
      <p className="hext-ayuda">{th('cargar_ejemplos_ayuda')}</p>
    </Section>
  )
}

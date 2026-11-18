/**
 * «Mis horas extra» (18-11-2026): pedir (o editar) con vista previa en vivo
 * (POST /overtime/preview con pausa) y, debajo, mis peticiones del periodo
 * (GET /overtime/mine) con cancelar y editar las pendientes.
 */
import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlarmClockPlus, Ban, CheckCircle2, Clock, Pencil, Scale, Send, X } from 'lucide-react'
import {
  horasExtraApi, ESTADOS_HE, TIPOS_HE,
  type CompensacionHe, type PeticionHe, type PeticionHeIn, type TipoHe, type VistaPreviaHe,
} from '../../services/api/horas-extra'
import {
  BarraDeFiltros, Button, EmptyState, FormField, Input, ProjectSelect, Section, Select, SelectorDePeriodo, Spinner, Tabla,
  TicketSelect, UserSelect, type ColumnaTabla,
} from '../ui'
import { useAuth } from '../../context/AuthContext'
import { pedirTexto } from '../../context/ConfirmContext'
import { useToast } from '../../context/ToastContext'
import { usePeriodo } from '../../hooks/usePeriodo'
import { SIN_HORA } from '../../utils/periodo'
import { extractErr } from '../../utils/helpers'
import { horasDeFranja } from './logica'
import {
  Aviso, AvisoDeError, Datos, EstadoHeBadge, fecha, franja, horas, textoDeTramos, useConfigHe, useRetrasado, useTh, type Th,
} from './comun'

const ESPERA_MS = 400

interface Borrador {
  user_id: string; fecha: string; tipo: TipoHe; hora_inicio: string; hora_fin: string; horas: string
  motivo: string; project_id: string; ticket_id: string; sustituto_id: string; compensacion: CompensacionHe | ''
}

const borradorDe = (p: PeticionHe | null, hoy: string): Borrador => ({
  user_id: p?.user_id ?? '', fecha: p?.fecha ?? hoy, tipo: p?.tipo ?? 'laborable',
  hora_inicio: p?.hora_inicio ?? '', hora_fin: p?.hora_fin ?? '', horas: p ? String(p.horas) : '',
  motivo: p?.motivo ?? '', project_id: p?.project_id ?? '', ticket_id: p?.ticket_id ?? '', sustituto_id: p?.sustituto_id ?? '',
  compensacion: p?.compensacion ?? '',
})

/** Horas escritas con coma o punto; null si no es un número. */
const leerHoras = (s: string): number | null => {
  if (!s.trim()) return null
  const n = Number(s.replace(',', '.'))
  return Number.isFinite(n) ? n : null
}

export default function MisHorasExtra() {
  const { th } = useTh()
  const config = useConfigHe()
  const [editando, setEditando] = useState<PeticionHe | null>(null)
  if (config.isLoading) return <Spinner label={th('cargando')} />
  if (config.isError) return <AvisoDeError error={config.error} />
  if (!config.data?.activo) {
    return <EmptyState svgIcon={<AlarmClockPlus size={26} />} title={th('desactivadas')} description={th('desactivadas_texto')} />
  }
  return (
    <div className="hext-panel">
      <Section title={editando ? th('editar_peticion') : th('nueva_peticion')} subtitle={th('nueva_peticion_ayuda')}>
        <Formulario key={editando?.id ?? 'nueva'} editar={editando} onHecho={() => setEditando(null)} />
      </Section>
      <MisPeticiones onEditar={setEditando} />
    </div>
  )
}

function Formulario({ editar, onHecho }: { editar: PeticionHe | null; onHecho: () => void }) {
  const { th } = useTh()
  const qc = useQueryClient()
  const toast = useToast()
  const { hasRole } = useAuth()
  const cfg = useConfigHe().data
  const hoy = new Date().toISOString().slice(0, 10)
  const [b, setB] = useState<Borrador>(() => borradorDe(editar, hoy))
  const poner = (c: Partial<Borrador>) => setB(x => ({ ...x, ...c }))
  const compensaciones = cfg?.compensaciones ?? []
  useEffect(() => {
    if (!b.compensacion && cfg?.compensacion_por_defecto) setB(x => ({ ...x, compensacion: cfg.compensacion_por_defecto }))
  }, [cfg?.compensacion_por_defecto, b.compensacion])
  const enNombreDeOtro = Boolean(cfg?.pedir_en_nombre) && hasRole('admin', 'hr', 'pm', 'team_lead')
  const horasDeLaFranja = horasDeFranja(b.hora_inicio, b.hora_fin)
  const horasEscritas = leerHoras(b.horas)
  const peticion = useMemo<PeticionHeIn>(() => ({
    user_id: enNombreDeOtro && b.user_id ? b.user_id : null,
    fecha: b.fecha, tipo: b.tipo,
    hora_inicio: b.hora_inicio || null, hora_fin: b.hora_fin || null,
    horas: horasEscritas,
    motivo: b.motivo.trim() || null, project_id: b.project_id || null, ticket_id: b.ticket_id || null,
    sustituto_id: b.sustituto_id || null, compensacion: b.compensacion || null,
  }), [b, enNombreDeOtro, horasEscritas])
  const completa = Boolean(b.fecha && b.tipo && ((horasEscritas ?? 0) > 0 || horasDeLaFranja))
  const consulta = useRetrasado(peticion, ESPERA_MS)
  const previa = useQuery({
    queryKey: ['horas-extra', 'previa', consulta],
    queryFn: () => horasExtraApi.vistaPrevia(consulta),
    enabled: completa,
    retry: false,
  })
  const guardar = useMutation({
    mutationFn: () => (editar ? horasExtraApi.editar(editar.id, peticion) : horasExtraApi.pedir(peticion)),
    onSuccess: () => {
      toast.success(editar ? th('guardada') : th('enviada'))
      qc.invalidateQueries({ queryKey: ['horas-extra'] })
      setB(borradorDe(null, hoy))
      onHecho()
    },
  })
  const v = previa.data
  const bloqueada = Boolean(v && (v.decision === 'block' || v.bloqueos.length || v.errores.length))
  const faltaMotivo = Boolean(cfg?.exigir_motivo) && !b.motivo.trim()
  const horasMal = horasEscritas !== null && (horasEscritas <= 0 || horasEscritas > 24)

  return (
    <form className="hext-formulario" onSubmit={e => { e.preventDefault(); if (completa && !bloqueada && !faltaMotivo && !horasMal) guardar.mutate() }}>
      <div className="hext-formulario-datos">
        <div className="hext-rejilla">
          {enNombreDeOtro && (
            <FormField label={th('persona')} hint={th('persona_ayuda')}>
              <UserSelect value={b.user_id} placeholder={th('yo_mismo')} onChange={id => poner({ user_id: id })} />
            </FormField>
          )}
          <Input type="date" label={th('fecha')} required value={b.fecha} onChange={e => poner({ fecha: e.target.value })} />
          <Select label={th('tipo')} value={b.tipo} placeholder={false} onChange={e => poner({ tipo: e.target.value as TipoHe })}
            options={TIPOS_HE.map(x => ({ value: x, label: th(`tipo_${x}`) }))} hint={th(`tipo_${b.tipo}_ayuda`)} />
          <Input type="time" label={th('hora_inicio')} value={b.hora_inicio} onChange={e => poner({ hora_inicio: e.target.value })} />
          <Input type="time" label={th('hora_fin')} value={b.hora_fin} onChange={e => poner({ hora_fin: e.target.value })} />
          <Input label={th('horas')} inputMode="decimal" value={b.horas} onChange={e => poner({ horas: e.target.value })}
            placeholder={horasDeLaFranja ? String(horasDeLaFranja) : ''}
            hint={horasDeLaFranja ? th('horas_de_la_franja', { n: horas(horasDeLaFranja) }) : th('horas_ayuda')}
            error={horasMal ? th('horas_fuera_de_rango') : undefined} />
          {compensaciones.length > 0 && (
            <Select label={th('compensacion')} value={b.compensacion} placeholder={false}
              onChange={e => poner({ compensacion: e.target.value as CompensacionHe })}
              options={compensaciones.map(x => ({ value: x, label: th(`compensacion_${x}`) }))} />
          )}
          <FormField label={th('proyecto')}>
            <ProjectSelect value={b.project_id} placeholder={th('sin_proyecto')} onChange={id => poner({ project_id: id })} />
          </FormField>
          <FormField label={th('ticket')}>
            <TicketSelect value={b.ticket_id} placeholder={th('sin_ticket')} onChange={id => poner({ ticket_id: id })} />
          </FormField>
          <FormField label={th('sustituto')}>
            <UserSelect value={b.sustituto_id} placeholder={th('sin_sustituto')} onChange={id => poner({ sustituto_id: id })} />
          </FormField>
          <Input className="hext-rejilla--ancho" label={th('motivo')} required={Boolean(cfg?.exigir_motivo)} value={b.motivo}
            maxLength={1000} onChange={e => poner({ motivo: e.target.value })}
            hint={cfg?.exigir_motivo ? th('motivo_obligatorio') : undefined} />
        </div>
        <AvisoDeError error={guardar.error} />
        <div className="hext-acciones">
          {editar && <Button variant="ghost" onClick={onHecho}>{th('cancelar_edicion')}</Button>}
          <Button type="submit" icon={<Send size={14} />} loading={guardar.isPending}
            disabled={!completa || bloqueada || faltaMotivo || horasMal}>
            {editar ? th('guardar_cambios') : th('enviar_peticion')}
          </Button>
        </div>
      </div>
      <aside className="hext-previa" aria-live="polite" aria-label={th('vista_previa')}>
        <h3 className="hext-subtitulo">{th('vista_previa')}</h3>
        {!completa && <p className="hext-ayuda">{th('vista_previa_ayuda')}</p>}
        {completa && previa.isFetching && !v && <Spinner label={th('calculando')} />}
        {completa && previa.isError && <AvisoDeError error={previa.error} />}
        {completa && v && <VistaPrevia v={v} th={th} />}
      </aside>
    </form>
  )
}

const ICONO_DECISION = { allow: CheckCircle2, auto_approve: CheckCircle2, review: Scale, block: Ban } as const

function VistaPrevia({ v, th }: { v: VistaPreviaHe; th: Th }) {
  const Icono = ICONO_DECISION[v.decision] ?? Clock
  const a = v.acumulados
  return (
    <>
      <p className={`hext-decision hext-decision--${v.decision}`}><Icono size={15} aria-hidden />{th(`decision_${v.decision}`)}</p>
      <Datos filas={[
        [th('clase_dia'), th(`clase_${v.clase_dia}`) + (v.horario.festivo ? ` · ${v.horario.festivo}` : '')],
        [th('horario_del_dia'), `${horas(v.horario.horas)} · ${textoDeTramos(v.horario.tramos)}`],
        [th('horas_pedidas'), horas(v.horas)],
        [th('fuera_de_horario'), horas(v.horas_fuera_de_horario)],
        [th('acum_dia'), horas(a.dia)],
        [th('acum_semana'), horas(a.semana)],
        [th('acum_mes'), horas(a.mes)],
        [th('acum_anio'), horas(a.anio)],
        [th('acum_anio_pago'), horas(a.anio_pago)],
        v.presupuesto_restante !== null && [th('presupuesto_restante'),
          <span key="p" className={v.presupuesto_restante < 0 ? 'hext-negativo' : ''}>{horas(v.presupuesto_restante)}</span>],
        v.descanso_horas !== null && [th('descanso'), horas(v.descanso_horas)],
        [th('dias_seguidos'), String(v.dias_seguidos)],
        [th('antelacion'), horas(v.antelacion_horas)],
        [th('compensacion'), `${th(`compensacion_${v.compensacion}`)} · ×${v.factor}`],
        [th('horas_ponderadas'), horas(v.horas_ponderadas)],
      ]} />
      {v.aprobaciones.length > 0 && (
        <>
          <h4 className="hext-subtitulo">{th('aprobaciones_previstas')}</h4>
          <ol className="hext-pasos">
            {v.aprobaciones.map((x, i) => (
              <li key={i}>{x.nombre} · {x.aprobador}{x.rol ? ` (${x.rol})` : ''} · {th(`origen_aprobacion_${x.origen}`)}</li>
            ))}
          </ol>
        </>
      )}
      {v.aprobaciones.length === 0 && v.decision !== 'block' && <p className="hext-ayuda">{th('sin_aprobaciones')}</p>}
      {v.errores.map(x => <Aviso key={`e${x}`} tono="bloqueo">{x}</Aviso>)}
      {v.bloqueos.map(x => <Aviso key={`b${x}`} tono="bloqueo">{x}</Aviso>)}
      {v.requisitos.map(x => <Aviso key={`r${x}`} tono="info">{th('requisito', { texto: x })}</Aviso>)}
      {v.avisos.map(x => <Aviso key={`a${x}`} tono="aviso">{x}</Aviso>)}
    </>
  )
}

function MisPeticiones({ onEditar }: { onEditar: (p: PeticionHe) => void }) {
  const { th } = useTh()
  const qc = useQueryClient()
  const toast = useToast()
  const periodo = usePeriodo({ defecto: '90d', granularidades: SIN_HORA, prefijo: 'hem_' })
  const [estado, setEstado] = useState('')
  const q = useQuery({
    queryKey: ['horas-extra', 'mias', periodo.fechas, estado],
    queryFn: () => horasExtraApi.mias({ ...periodo.fechas, estado }),
  })
  const cancelar = useMutation({
    mutationFn: ({ id, nota }: { id: string; nota: string }) => horasExtraApi.cancelar(id, nota),
    onSuccess: () => { toast.success(th('cancelada_ok')); qc.invalidateQueries({ queryKey: ['horas-extra'] }) },
    onError: e => toast.error(extractErr(e, th('error'))),
  })
  const pedirCancelar = async (p: PeticionHe) => {
    const nota = await pedirTexto({ title: th('cancelar_peticion'), message: th('cancelar_peticion_texto'), label: th('nota_opcional'), danger: true })
    if (nota !== null) cancelar.mutate({ id: p.id, nota })
  }
  const columnas: Array<ColumnaTabla<PeticionHe>> = [
    { key: 'fecha', label: th('fecha'), render: (_, p) => fecha(p.fecha), valorOrden: p => p.fecha },
    { key: 'tipo', label: th('tipo'), render: (_, p) => th(`tipo_${p.tipo}`) },
    { key: 'origen', label: th('origen'), render: (_, p) => th(`origen_${p.origen}`) },
    { key: 'franja', label: th('franja'), render: (_, p) => franja(p) },
    { key: 'horas', label: th('horas'), alinear: 'derecha', render: (_, p) => horas(p.horas) },
    { key: 'horas_autorizadas', label: th('autorizadas'), alinear: 'derecha', render: (_, p) => horas(p.horas_autorizadas) },
    { key: 'compensacion', label: th('compensacion'), render: (_, p) => th(`compensacion_${p.compensacion}`) },
    { key: 'estado', label: th('estado'), render: (_, p) => <EstadoHeBadge p={p} />, valorOrden: p => p.estado },
    {
      key: 'acciones', label: <span className="u-sr-only">{th('acciones')}</span>, sortable: false, render: (_, p) => (
        <span className="hext-acciones">
          {p.puede_editar && <Button size="xs" variant="ghost" icon={<Pencil size={12} />} onClick={() => onEditar(p)}>{th('editar')}</Button>}
          {p.puede_cancelar && <Button size="xs" variant="ghost" icon={<X size={12} />} onClick={() => pedirCancelar(p)}>{th('cancelar')}</Button>}
        </span>
      ),
    },
  ]
  return (
    <Section title={th('mis_peticiones')}>
      <BarraDeFiltros>
        <SelectorDePeriodo {...periodo.selector} sinGranularidad />
        <Select suelto aria-label={th('estado')} value={estado} placeholder={th('todos_los_estados')} onChange={e => setEstado(e.target.value)}
          options={ESTADOS_HE.map(x => ({ value: x, label: th(`estado_${x}`) }))} />
      </BarraDeFiltros>
      {q.isError && <AvisoDeError error={q.error} />}
      <Tabla etiqueta={th('mis_peticiones')} filas={q.data ?? []} columnas={columnas} claveDeFila={p => p.id}
        ordenable ordenInicial={{ col: 'fecha', dir: 'desc' }} cargando={q.isLoading}
        vacio={{ icono: <AlarmClockPlus size={28} />, titulo: th('sin_peticiones'), descripcion: th('sin_peticiones_texto') }} />
    </Section>
  )
}

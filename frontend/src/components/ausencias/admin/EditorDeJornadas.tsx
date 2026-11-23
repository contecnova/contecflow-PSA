/**
 * Jornadas laborales (rev. 180): el horario de quien no trabaja a turnos
 * (normal, de verano, reducida…). Cada jornada tiene sus tramos por día de la
 * semana y una pausa no trabajada; se ven las horas por día y por semana.
 *
 * Una jornada se aplica con asignaciones: a toda la empresa, una sede, un
 * departamento, un equipo, un grupo o una persona, entre dos fechas (o cada
 * año entre esas fechas: la jornada de verano) y con prioridad. Gana la de
 * mayor prioridad; a igualdad, la más concreta (persona > grupo > equipo >
 * departamento > sede > empresa) y luego la temporal.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarRange, Copy, Plus, Save, Trash2 } from 'lucide-react'
import { ausenciasApi } from '../../../services/api/ausencias'
import type {
  AmbitoDeJornada, AsignacionDeJornada, AsignacionDeJornadaIn, DiaDeSemana, Jornada, JornadaIn, Tramo,
} from '../../../services/api/tipos-ausencias'
import { Button, EmptyState, Modal, Spinner, Select, Pulsable , useErroresDeCampo, Input } from '../../ui'
import DateInput from '../../ui/DateInput'
import { UserSelect } from '../../ui/EntitySelect'
import { confirmar } from '../../../context/ConfirmContext'
import { useToast } from '../../../context/ToastContext'
import { useOpciones } from '../../politicas/comun'
import { fecha, horasDeTramos, num } from '../comun'
import { AvisoDeError, ErrorDeCampo, hayDeCampo, Casilla, DIAS_SEMANA, Muestra, NombresPorIdioma, colorPorDefecto, errorDe, nombreEn, useT } from './comun'
import EditorDeTramos from './EditorDeTramos'
import { useOficinas } from './EditorDeTurnos'

const AMBITOS: AmbitoDeJornada[] = ['empresa', 'sede', 'departamento', 'equipo', 'grupo', 'persona']
const DIAS = DIAS_SEMANA.map(String) as DiaDeSemana[]

const semanaVacia = (): Record<DiaDeSemana, Tramo[]> => ({ 1: [], 2: [], 3: [], 4: [], 5: [], 6: [], 7: [] })
const nueva = (): JornadaIn => ({ nombre: '', nombres: {}, color: colorPorDefecto(), semana: semanaVacia(), pausa_minutos: 0, activo: true, orden: 100 })
function aEntrada(j: Jornada): JornadaIn {
  return {
    nombre: j.nombre, nombres: { ...j.nombres }, color: j.color, pausa_minutos: j.pausa_minutos, activo: j.activo, orden: j.orden,
    semana: Object.fromEntries(DIAS.map(d => [d, (j.semana?.[d] ?? []).map(([a, b]) => [a, b] as Tramo)])) as Record<DiaDeSemana, Tramo[]>,
  }
}
const asignacionNueva = (jornadaId: string): AsignacionDeJornadaIn => ({
  jornada_id: jornadaId, ambito: 'empresa', valor: null, desde: null, hasta: null, recurrente_anual: false, prioridad: 0, nota: null,
})

export default function EditorDeJornadas({ puedeEditar }: { puedeEditar: boolean }) {
  const { ta, lang } = useT()
  const [abierta, setAbierta] = useState<{ id: string | null; datos: JornadaIn } | null>(null)
  const q = useQuery({ queryKey: ['ausencias', 'jornadas', 'todas'], queryFn: () => ausenciasApi.jornadas(true) })
  if (q.isLoading) return <Spinner label={ta('cargando')} />
  if (q.isError) return <AvisoDeError error={q.error} defecto={ta('error_cargar')} />
  const jornadas = q.data ?? []
  const abrir = (j: Jornada) => setAbierta({ id: j.id, datos: aEntrada(j) })
  return (
    <section aria-labelledby="ausadm-jornadas-titulo">
      <div className="ausadm-cabecera">
        <h2 id="ausadm-jornadas-titulo" className="ausadm-titulo">{ta('jornadas_titulo')}</h2>
        {puedeEditar && <Button icon={<Plus size={14} />} onClick={() => setAbierta({ id: null, datos: nueva() })}>{ta('nueva_jornada')}</Button>}
      </div>
      <p className="ausadm-ayuda">{ta('jornadas_ayuda')}</p>
      {jornadas.length === 0
        ? <EmptyState svgIcon={<CalendarRange size={26} />} title={ta('sin_jornadas')} description={ta('sin_jornadas_texto')}
            ctaLabel={puedeEditar ? ta('nueva_jornada') : undefined} onCta={puedeEditar ? () => setAbierta({ id: null, datos: nueva() }) : undefined} />
        : (
          <ul className="ausadm-lista">
            {jornadas.map(j => (
              <li key={j.id}>
                <Pulsable className={`ausadm-item${j.activo ? '' : ' ausadm-item--inactivo'}`} onClick={() => abrir(j)}>
                  <Muestra color={j.color} className="ausadm-muestra--punto" />
                  <span className="ausadm-item-nombre">{nombreEn(j, lang)}
                    <span className="ausadm-ayuda"> {ta('horas_semana', { n: num(j.horas_semana) })}</span></span>
                  <span className="ausadm-chips">
                    {DIAS.filter(d => (j.horas_por_dia?.[d] ?? 0) > 0).map(d => (
                      <span key={d} className="ausadm-chip">{ta(`dia_corto_${d}`)} {num(j.horas_por_dia[d])}</span>
                    ))}
                    <span className="ausadm-chip">{ta('n_asignaciones', { n: j.asignaciones.length })}</span>
                    {!j.activo && <span className="ausadm-chip">{ta('inactivo')}</span>}
                  </span>
                </Pulsable>
              </li>
            ))}
          </ul>
        )}
      {abierta && (
        <FormularioDeJornada key={abierta.id ?? 'nueva'} id={abierta.id} inicial={abierta.datos} puedeEditar={puedeEditar}
          asignaciones={jornadas.find(j => j.id === abierta.id)?.asignaciones ?? []}
          onGuardada={j => setAbierta({ id: j.id, datos: aEntrada(j) })} onCerrar={() => setAbierta(null)} />
      )}
    </section>
  )
}

function FormularioDeJornada({ id, inicial, asignaciones, puedeEditar, onGuardada, onCerrar }: {
  id: string | null; inicial: JornadaIn; asignaciones: AsignacionDeJornada[]; puedeEditar: boolean
  onGuardada: (j: Jornada) => void; onCerrar: () => void
}) {
  const { ta } = useT()
  const qc = useQueryClient()
  const toast = useToast()
  const [d, setD] = useState(inicial)
  const campos = useErroresDeCampo()
  const cambiar = (c: Partial<JornadaIn>) => { Object.keys(c).forEach(k => campos.limpiar(k)); setD(x => ({ ...x, ...c })) }
  const ponerDia = (dia: DiaDeSemana, tramos: Tramo[]) => setD(x => ({ ...x, semana: { ...x.semana, [dia]: tramos } }))
  // Copia los tramos del lunes a los demás días laborables que aún no tienen horario.
  const copiarLunes = () => setD(x => ({
    ...x, semana: Object.fromEntries(DIAS.map(dia => [dia, dia !== '1' && Number(dia) <= 5 && !x.semana[dia].length
      ? x.semana['1'].map(([a, b]) => [a, b] as Tramo) : x.semana[dia]])) as Record<DiaDeSemana, Tramo[]>,
  }))
  const horasDia = (dia: DiaDeSemana) => horasDeTramos(d.semana[dia], d.semana[dia].length ? d.pausa_minutos : 0).horas
  const total = DIAS.reduce((s, dia) => s + horasDia(dia), 0)
  const refrescar = () => qc.invalidateQueries({ queryKey: ['ausencias'] })
  const guardar = useMutation({
    onMutate: () => campos.limpiar(),
    onError: e => { campos.recoger(e) },
    mutationFn: () => (id ? ausenciasApi.guardarJornada(id, d) : ausenciasApi.crearJornada(d)),
    onSuccess: j => { toast.success(ta('guardado')); refrescar(); if (!id) onGuardada(j); else onCerrar() },
  })
  const borrar = useMutation({
    mutationFn: () => ausenciasApi.borrarJornada(id as string),
    onSuccess: r => { toast.success(r.desactivado ? ta('desactivado_en_uso') : ta('borrado')); refrescar(); onCerrar() },
    onError: e => toast.error(errorDe(e, ta('error_guardar')).mensaje),
  })
  return (
    <Modal open onClose={onCerrar} title={id ? ta('editar_jornada') : ta('nueva_jornada')} size="lg">
      <form className="ausadm-form" onSubmit={e => { e.preventDefault(); if (puedeEditar) guardar.mutate() }}>
        <fieldset className="ds-grupo-opciones ausadm-fieldset" disabled={!puedeEditar}>
          <legend className="u-sr-only">{ta('jornada')}</legend>
          <div className="ausadm-grid-2">
            <label className="ausadm-campo-con-etiqueta">
              <span className="ausadm-etiqueta">{ta('nombre')}</span>
              <Input aria-label={ta('nombre')} required value={d.nombre} onChange={e => cambiar({ nombre: e.target.value })} inputClassName="ausadm-campo" />
              <ErrorDeCampo texto={campos.de('nombre')} />
            </label>
            <label className="ausadm-campo-con-etiqueta">
              <span className="ausadm-etiqueta">{ta('color')}</span>
              <input aria-label={ta('color')} type="color" className="ausadm-color" value={d.color} onChange={e => cambiar({ color: e.target.value })} />
            </label>
          </div>
          <NombresPorIdioma valor={d.nombres} onChange={nombres => cambiar({ nombres })} />
          <div className="ausadm-cabecera">
            <span className="ausadm-etiqueta">{ta('horario_por_dia')}</span>
            <Button size="xs" variant="ghost" icon={<Copy size={13} />} onClick={copiarLunes} disabled={!d.semana['1'].length}>{ta('copiar_lunes')}</Button>
          </div>
          <div className="ausadm-semana">
            {DIAS.map(dia => (
              <div key={dia} className="ausadm-semana-dia">
                <span className="ausadm-etiqueta">{ta(`dia_${dia}`)}
                  <span className="ausadm-ayuda"> {d.semana[dia].length ? ta('n_horas', { n: num(horasDia(dia)) }) : ta('no_se_trabaja')}</span></span>
                <EditorDeTramos compacto minimo={0} tramos={d.semana[dia]} onChange={t => ponerDia(dia, t)} leyenda={ta(`dia_${dia}`)} />
              </div>
            ))}
          </div>
          <div className="ausadm-grid-2">
            <label className="ausadm-campo-con-etiqueta">
              <span className="ausadm-etiqueta">{ta('pausa_minutos')}</span>
              <Input aria-label={ta('pausa_minutos')} type="number" min={0} step={5} value={d.pausa_minutos} onChange={e => cambiar({ pausa_minutos: Math.max(0, Number(e.target.value) || 0) })} inputClassName="ausadm-campo ausadm-campo--corto" />
              <span className="ausadm-ayuda">{ta('pausa_jornada_ayuda')}</span>
              <ErrorDeCampo texto={campos.de('pausa_minutos')} />
            </label>
            <p className="ausadm-ayuda" aria-live="polite">{ta('horas_semana', { n: num(total) })}</p>
          </div>
          <Casilla etiqueta={ta('activo')} valor={d.activo} onChange={v => cambiar({ activo: v })} />
        </fieldset>
        <AvisoDeError error={hayDeCampo(campos) ? null : guardar.error} defecto={ta('error_guardar')} />
        {puedeEditar && (
          <div className="ausadm-acciones">
            {id && <Button variant="danger" icon={<Trash2 size={14} />} loading={borrar.isPending}
              onClick={async () => { if (await confirmar({ title: ta('borrar'), danger: true, message: ta('borrar_jornada_confirmar') })) borrar.mutate() }}>
              {ta('borrar')}</Button>}
            <Button variant="secondary" onClick={onCerrar}>{ta('cerrar')}</Button>
            <Button type="submit" loading={guardar.isPending}>{ta('guardar')}</Button>
          </div>
        )}
      </form>
      {id ? <Asignaciones jornadaId={id} asignaciones={asignaciones} puedeEditar={puedeEditar} />
        : <p className="ausadm-ayuda">{ta('guarda_para_asignar')}</p>}
    </Modal>
  )
}

/** A quién y cuándo se aplica una jornada. */
function Asignaciones({ jornadaId, asignaciones, puedeEditar }: { jornadaId: string; asignaciones: AsignacionDeJornada[]; puedeEditar: boolean }) {
  const { ta } = useT()
  const [nuevas, setNuevas] = useState<number[]>([])
  return (
    <section className="ausadm-fieldset u-stack-10" aria-labelledby="ausadm-asig-titulo">
      <h3 id="ausadm-asig-titulo" className="ausadm-subtitulo">{ta('asignaciones')}</h3>
      <p className="ausadm-ayuda">{ta('asignaciones_ayuda')}</p>
      {asignaciones.length === 0 && nuevas.length === 0 && <p className="ausadm-ayuda">{ta('sin_asignaciones')}</p>}
      {asignaciones.map(a => {
        const { id: _id, ...datos } = a
        return <FilaDeAsignacion key={a.id} id={a.id} inicial={datos} puedeEditar={puedeEditar} />
      })}
      {nuevas.map(n => (
        <FilaDeAsignacion key={`n${n}`} id={null} inicial={asignacionNueva(jornadaId)} puedeEditar={puedeEditar}
          onHecha={() => setNuevas(x => x.filter(y => y !== n))} />
      ))}
      {puedeEditar && (
        <Button size="xs" variant="secondary" icon={<Plus size={13} />} onClick={() => setNuevas(x => [...x, Date.now()])}>{ta('anadir_asignacion')}</Button>
      )}
    </section>
  )
}

function FilaDeAsignacion({ id, inicial, puedeEditar, onHecha }: {
  id: string | null; inicial: AsignacionDeJornadaIn; puedeEditar: boolean; onHecha?: () => void
}) {
  const { ta } = useT()
  const qc = useQueryClient()
  const toast = useToast()
  const [a, setA] = useState(inicial)
  const campos = useErroresDeCampo()
  const poner = (c: Partial<AsignacionDeJornadaIn>) => { Object.keys(c).forEach(k => campos.limpiar(k)); setA(x => ({ ...x, ...c })) }
  const refrescar = () => qc.invalidateQueries({ queryKey: ['ausencias'] })
  const guardar = useMutation({
    onMutate: () => campos.limpiar(),
    onError: e => { campos.recoger(e) },
    mutationFn: () => (id ? ausenciasApi.guardarAsignacion(id, a) : ausenciasApi.crearAsignacion(a)),
    onSuccess: () => { toast.success(ta('guardado')); refrescar(); onHecha?.() },
  })
  const quitar = useMutation({
    mutationFn: () => ausenciasApi.borrarAsignacion(id as string),
    onSuccess: () => { toast.success(ta('borrado')); refrescar() },
    onError: e => toast.error(errorDe(e, ta('error_guardar')).mensaje),
  })
  const falta = a.ambito !== 'empresa' && !a.valor
  return (
    <form className="ausadm-tarjeta" aria-label={ta('asignacion')} onSubmit={e => { e.preventDefault(); if (!falta) guardar.mutate() }}>
      <fieldset className="ds-grupo-opciones ausadm-fieldset" disabled={!puedeEditar}>
        <legend className="u-sr-only">{ta('asignacion')}</legend>
        <div className="ausadm-fila">
          <Select suelto className="ausadm-campo" aria-label={ta('ambito')} value={a.ambito} placeholder={false}
            onChange={e => poner({ ambito: e.target.value as AmbitoDeJornada, valor: null })}>
            {AMBITOS.map(x => <option key={x} value={x}>{ta(`ambito_${x}`)}</option>)}
          </Select>
          <ValorDeAmbito ambito={a.ambito} valor={a.valor} onChange={valor => poner({ valor })} />
        </div>
        <div className="ausadm-fila">
          <label className="ausadm-fila"><span className="ausadm-ayuda">{ta('desde')}</span>
            <DateInput className="ausadm-campo" aria-label={ta('desde')} value={a.desde ?? ''} onChange={e => poner({ desde: e.target.value || null })} />
          </label>
          <label className="ausadm-fila"><span className="ausadm-ayuda">{ta('hasta')}</span>
            <DateInput className="ausadm-campo" aria-label={ta('hasta')} value={a.hasta ?? ''} min={a.desde ?? undefined}
              onChange={e => poner({ hasta: e.target.value || null })} />
          </label>
          <Casilla etiqueta={ta('cada_anio')} ayuda={ta('cada_anio_ayuda')} valor={a.recurrente_anual} onChange={v => poner({ recurrente_anual: v })} />
          <label className="ausadm-fila"><span className="ausadm-ayuda">{ta('prioridad')}</span>
            <Input type="number" aria-label={ta('prioridad')} value={a.prioridad} onChange={e => poner({ prioridad: Number(e.target.value) || 0 })} className="ausadm-campo--mini" />
            <ErrorDeCampo texto={campos.de('prioridad')} />
          </label>
        </div>
        <label className="ausadm-campo-con-etiqueta"><span className="ausadm-ayuda">{ta('nota')}</span>
          <Input aria-label={ta('nota')} value={a.nota ?? ''} onChange={e => poner({ nota: e.target.value || null })} inputClassName="ausadm-campo" />
          <ErrorDeCampo texto={campos.de('nota')} />
        </label>
        {!a.desde && !a.hasta && <span className="ausadm-ayuda">{ta('sin_fechas_siempre')}</span>}
        {a.desde && a.hasta && <span className="ausadm-ayuda">{ta(a.recurrente_anual ? 'vigencia_cada_anio' : 'vigencia', { desde: fecha(a.desde), hasta: fecha(a.hasta) })}</span>}
      </fieldset>
      <AvisoDeError error={hayDeCampo(campos) ? null : guardar.error} defecto={ta('error_guardar')} />
      {puedeEditar && (
        <div className="ausadm-acciones">
          {id ? <Button size="xs" variant="danger" icon={<Trash2 size={13} />} loading={quitar.isPending}
            onClick={async () => { if (await confirmar({ title: ta('quitar'), danger: true, message: ta('quitar_asignacion_confirmar') })) quitar.mutate() }}>{ta('quitar')}</Button>
            : <Button size="xs" variant="ghost" onClick={onHecha}>{ta('cancelar')}</Button>}
          <Button size="xs" type="submit" icon={<Save size={13} />} disabled={falta} loading={guardar.isPending}>{ta('guardar')}</Button>
        </div>
      )}
    </form>
  )
}

/** El selector del valor de un ámbito: sede, departamento, equipo, grupo o persona. */
export function ValorDeAmbito({ ambito, valor, onChange }: { ambito: AmbitoDeJornada; valor: string | null; onChange: (v: string | null) => void }) {
  const { ta } = useT()
  const opciones = useOpciones().data
  const oficinas = useOficinas().data ?? []
  if (ambito === 'empresa') return null
  if (ambito === 'persona') {
    return <span aria-label={ta('ambito_persona')} className="ausadm-selector-persona"><UserSelect value={valor ?? ''} onChange={(v: string) => onChange(v || null)} /></span>
  }
  const lista: { valor: string; etiqueta: string }[] = ambito === 'sede' ? oficinas.map(o => ({ valor: o.id, etiqueta: o.name }))
    : ambito === 'grupo' ? (opciones?.grupos ?? []).map(g => ({ valor: g.id, etiqueta: g.nombre }))
    : (ambito === 'equipo' ? opciones?.equipos ?? [] : opciones?.departamentos ?? []).map(x => ({ valor: x, etiqueta: x }))
  return (
    <Select suelto className="ausadm-campo" aria-label={ta(`ambito_${ambito}`)} value={valor ?? ''} onChange={e => onChange(e.target.value || null)} placeholder={ta('elige')}>
      {lista.map(x => <option key={x.valor} value={x.valor}>{x.etiqueta}</option>)}
    </Select>
  )
}

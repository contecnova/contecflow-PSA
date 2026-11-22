/**
 * Turnos: nombre, color, horario (puede cruzar la medianoche), días de la
 * semana en que opera, equipo, departamento, oficina, personas requeridas
 * (cobertura mínima) y si trabaja en festivos.
 *
 * Rev. 180: turno partido (varios tramos inicio–fin, cada uno puede cruzar la
 * medianoche) y pausa no trabajada en minutos; se ve la duración neta.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Clock, MoonStar, Plus, Split, Trash2 } from 'lucide-react'
import { ausenciasApi } from '../../../services/api/ausencias'
import { advancedConfigApi } from '../../../services/settingsApi'
import type { Turno, TurnoIn } from '../../../services/api/tipos-ausencias'
import { Button, EmptyState, Modal, Spinner, Select, Pulsable, Checkbox , useErroresDeCampo, Input } from '../../ui'
import { confirmar } from '../../../context/ConfirmContext'
import { useToast } from '../../../context/ToastContext'
import { useOpciones } from '../../politicas/comun'
import { AvisoDeError, ErrorDeCampo, hayDeCampo, colorPorDefecto, Casilla, DIAS_SEMANA, Muestra, errorDe, useT } from './comun'
import { horasDeTramos, textoDeTramos, tramosDe } from '../comun'
import EditorDeTramos from './EditorDeTramos'

const nuevo = (): TurnoIn => ({
  nombre: '', color: colorPorDefecto(), hora_inicio: '08:00', hora_fin: '16:00', dias_semana: [1, 2, 3, 4, 5], equipo: null,
  departamento: null, office_id: null, personas_requeridas: 0, trabaja_festivos: false, activo: true, orden: 100,
  tramos: [['08:00', '16:00']], pausa_minutos: 0,
})
interface Oficina { id: string; name: string }

export function useOficinas() {
  return useQuery({
    queryKey: ['ausencias', 'oficinas'],
    queryFn: () => advancedConfigApi.getOffices().then(r => (r.data ?? []) as Oficina[]),
  })
}

export default function EditorDeTurnos() {
  const { ta } = useT()
  const [abierto, setAbierto] = useState<{ id: string | null; datos: TurnoIn } | null>(null)
  const q = useQuery({ queryKey: ['ausencias', 'turnos', 'todos'], queryFn: () => ausenciasApi.turnos(true) })
  const oficinas = useOficinas().data ?? []
  if (q.isLoading) return <Spinner label={ta('cargando')} />
  if (q.isError) return <AvisoDeError error={q.error} defecto={ta('error_cargar')} />
  const turnos = q.data ?? []
  const abrir = (t: Turno) => {
    const { id: _id, cruza_medianoche: _c, duracion_horas: _d, partido: _p, ...resto } = t
    setAbierto({ id: t.id, datos: { ...resto, tramos: tramosDe(t), pausa_minutos: t.pausa_minutos ?? 0 } })
  }
  return (
    <section aria-labelledby="ausadm-turnos-titulo">
      <div className="ausadm-cabecera">
        <h2 id="ausadm-turnos-titulo" className="ausadm-titulo">{ta('turnos_titulo')}</h2>
        <Button icon={<Plus size={14} />} onClick={() => setAbierto({ id: null, datos: nuevo() })}>{ta('nuevo_turno')}</Button>
      </div>
      <p className="ausadm-ayuda">{ta('turnos_ayuda')}</p>
      {turnos.length === 0
        ? <EmptyState svgIcon={<Clock size={26} />} title={ta('sin_turnos')} description={ta('sin_turnos_texto')}
            ctaLabel={ta('nuevo_turno')} onCta={() => setAbierto({ id: null, datos: nuevo() })} />
        : (
          <ul className="ausadm-lista">
            {turnos.map(t => (
              <li key={t.id}>
                <Pulsable className={`ausadm-item${t.activo ? '' : ' ausadm-item--inactivo'}`} onClick={() => abrir(t)}>
                  <Muestra color={t.color} className="ausadm-muestra--punto" />
                  <span className="ausadm-item-nombre">{t.nombre}
                    <span className="ausadm-ayuda"> {textoDeTramos(tramosDe(t))} · {ta('n_horas', { n: t.duracion_horas })}</span></span>
                  <span className="ausadm-chips">
                    {t.cruza_medianoche && <span className="ausadm-chip"><MoonStar size={12} aria-hidden /> {ta('cruza_medianoche')}</span>}
                    {t.partido && <span className="ausadm-chip"><Split size={12} aria-hidden /> {ta('turno_partido')}</span>}
                    {t.pausa_minutos > 0 && <span className="ausadm-chip">{ta('pausa_n', { n: t.pausa_minutos })}</span>}
                    <span className="ausadm-chip">{t.dias_semana.length ? t.dias_semana.map(d => ta(`dia_corto_${d}`)).join(' ') : ta('todos_los_dias')}</span>
                    {t.personas_requeridas > 0 && <span className="ausadm-chip">{ta('requeridas_n', { n: t.personas_requeridas })}</span>}
                    {t.equipo && <span className="ausadm-chip">{t.equipo}</span>}
                    {t.office_id && <span className="ausadm-chip">{oficinas.find(o => o.id === t.office_id)?.name ?? '—'}</span>}
                    {!t.activo && <span className="ausadm-chip">{ta('inactivo')}</span>}
                  </span>
                </Pulsable>
              </li>
            ))}
          </ul>
        )}
      {abierto && <Formulario key={abierto.id ?? 'nuevo'} id={abierto.id} inicial={abierto.datos} oficinas={oficinas}
        onCerrar={() => setAbierto(null)} />}
    </section>
  )
}

function Formulario({ id, inicial, oficinas, onCerrar }: { id: string | null; inicial: TurnoIn; oficinas: Oficina[]; onCerrar: () => void }) {
  const { ta } = useT()
  const qc = useQueryClient()
  const toast = useToast()
  const opciones = useOpciones().data
  const [d, setD] = useState(inicial)
  const campos = useErroresDeCampo()
  const cambiar = (c: Partial<TurnoIn>) => { Object.keys(c).forEach(k => campos.limpiar(k)); setD(x => ({ ...x, ...c })) }
  const h = horasDeTramos(d.tramos, d.pausa_minutos)
  const refrescar = () => qc.invalidateQueries({ queryKey: ['ausencias'] })
  // Inicio y fin del turno: el principio del primer tramo y el final del último.
  const aEnviar = (): TurnoIn => ({ ...d, hora_inicio: d.tramos[0]?.[0] ?? d.hora_inicio, hora_fin: d.tramos[d.tramos.length - 1]?.[1] ?? d.hora_fin })
  const guardar = useMutation({
    onMutate: () => campos.limpiar(),
    onError: e => { campos.recoger(e) },
    mutationFn: () => (id ? ausenciasApi.guardarTurno(id, aEnviar()) : ausenciasApi.crearTurno(aEnviar())),
    onSuccess: () => { toast.success(ta('guardado')); refrescar(); onCerrar() },
  })
  const borrar = useMutation({
    mutationFn: () => ausenciasApi.borrarTurno(id as string),
    onSuccess: r => { toast.success(r.desactivado ? ta('desactivado_en_uso') : ta('borrado')); refrescar(); onCerrar() },
    onError: e => toast.error(errorDe(e, ta('error_guardar')).mensaje),
  })
  return (
    <Modal open onClose={onCerrar} title={id ? ta('editar_turno') : ta('nuevo_turno')}>
      <form className="ausadm-form" onSubmit={e => { e.preventDefault(); guardar.mutate() }}>
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
        <EditorDeTramos tramos={d.tramos} onChange={tramos => cambiar({ tramos })} leyenda={ta('tramos_del_turno')} />
        <label className="ausadm-campo-con-etiqueta">
          <span className="ausadm-etiqueta">{ta('pausa_minutos')}</span>
          <Input aria-label={ta('pausa_minutos')} type="number" min={0} step={5} value={d.pausa_minutos} aria-describedby="ausadm-horario" onChange={e => cambiar({ pausa_minutos: Math.max(0, Number(e.target.value) || 0) })} inputClassName="ausadm-campo ausadm-campo--corto" />
          <ErrorDeCampo texto={campos.de('pausa_minutos')} />
        </label>
        <p id="ausadm-horario" className="ausadm-ayuda" aria-live="polite">
          {h.cruza ? ta('horario_cruza', { n: h.horas }) : ta('horario_dura', { n: h.horas })}
          {d.tramos.length > 1 ? ` · ${ta('turno_partido')}` : ''}
        </p>
        <fieldset className="ds-grupo-opciones ausadm-fieldset">
          <legend className="ausadm-etiqueta">{ta('dias_que_opera')}</legend>
          <div className="ausadm-fila">
            {DIAS_SEMANA.map(dia => (
              <Checkbox key={dia} className="ausadm-chip ausadm-chip--seleccionable" label={ta(`dia_corto_${dia}`)} checked={d.dias_semana.includes(dia)}
                onChange={m => cambiar({ dias_semana: m ? [...d.dias_semana, dia].sort() : d.dias_semana.filter(x => x !== dia) })} />
            ))}
          </div>
          <span className="ausadm-ayuda">{ta('dias_vacio_todos')}</span>
        </fieldset>
        <div className="ausadm-grid-2">
          <label className="ausadm-campo-con-etiqueta">
            <span className="ausadm-etiqueta">{ta('equipo')}</span>
            <Select suelto className="ausadm-campo" value={d.equipo ?? ''} onChange={e => cambiar({ equipo: e.target.value || null })} placeholder={ta('cualquiera')}>
              {(opciones?.equipos ?? []).map(x => <option key={x} value={x}>{x}</option>)}
            </Select>
            <ErrorDeCampo texto={campos.de('equipo')} />
          </label>
          <label className="ausadm-campo-con-etiqueta">
            <span className="ausadm-etiqueta">{ta('departamento')}</span>
            <Select suelto className="ausadm-campo" value={d.departamento ?? ''} onChange={e => cambiar({ departamento: e.target.value || null })} placeholder={ta('cualquiera')}>
              {(opciones?.departamentos ?? []).map(x => <option key={x} value={x}>{x}</option>)}
            </Select>
            <ErrorDeCampo texto={campos.de('departamento')} />
          </label>
          <label className="ausadm-campo-con-etiqueta">
            <span className="ausadm-etiqueta">{ta('oficina')}</span>
            <Select suelto className="ausadm-campo" value={d.office_id ?? ''} onChange={e => cambiar({ office_id: e.target.value || null })} placeholder={ta('cualquiera')}>
              {oficinas.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}
            </Select>
            <ErrorDeCampo texto={campos.de('office_id')} />
          </label>
          <label className="ausadm-campo-con-etiqueta">
            <span className="ausadm-etiqueta">{ta('personas_requeridas')}</span>
            <Input aria-label={ta('personas_requeridas')} type="number" min={0} value={d.personas_requeridas} onChange={e => cambiar({ personas_requeridas: Math.max(0, Number(e.target.value) || 0) })} inputClassName="ausadm-campo ausadm-campo--corto" />
            <span className="ausadm-ayuda">{ta('personas_requeridas_ayuda')}</span>
            <ErrorDeCampo texto={campos.de('personas_requeridas')} />
          </label>
        </div>
        <Casilla etiqueta={ta('trabaja_festivos')} valor={d.trabaja_festivos} onChange={v => cambiar({ trabaja_festivos: v })} />
        <Casilla etiqueta={ta('activo')} valor={d.activo} onChange={v => cambiar({ activo: v })} />
        <AvisoDeError error={hayDeCampo(campos) ? null : guardar.error} defecto={ta('error_guardar')} />
        <div className="ausadm-acciones">
          {id && <Button variant="danger" icon={<Trash2 size={14} />} loading={borrar.isPending}
            onClick={async () => { if (await confirmar({ title: ta('borrar'), danger: true, message: ta('borrar_turno_confirmar') })) borrar.mutate() }}>
            {ta('borrar')}</Button>}
          <Button variant="secondary" onClick={onCerrar}>{ta('cancelar')}</Button>
          <Button type="submit" loading={guardar.isPending}>{ta('guardar')}</Button>
        </div>
      </form>
    </Modal>
  )
}

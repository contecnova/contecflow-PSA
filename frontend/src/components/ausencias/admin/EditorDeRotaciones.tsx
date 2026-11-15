/**
 * Rotaciones: un ciclo de N días (turno o libre por día) que empieza en una
 * fecha, con las personas que lo siguen, sus fechas y su desfase (para que
 * roten escalonadas). Un cambio en el cuadrante manda sobre la rotación.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Repeat, Trash2 } from 'lucide-react'
import { ausenciasApi } from '../../../services/api/ausencias'
import type { Rotacion, RotacionIn, Turno } from '../../../services/api/tipos-ausencias'
import { Button, EmptyState, Modal, Spinner } from '../../ui'
import { UserSelect } from '../../ui/EntitySelect'
import { confirmar } from '../../../context/ConfirmContext'
import { useToast } from '../../../context/ToastContext'
import { AvisoDeError, Casilla, Muestra, errorDe, isoDe, useT } from './comun'

const NUEVA = (): RotacionIn => ({ nombre: '', ciclo: [null, null, null, null, null, null, null], inicio: isoDe(new Date()), activo: true, miembros: [] })

export default function EditorDeRotaciones() {
  const { ta } = useT()
  const [abierta, setAbierta] = useState<{ id: string | null; datos: RotacionIn } | null>(null)
  const q = useQuery({ queryKey: ['ausencias', 'rotaciones'], queryFn: ausenciasApi.rotaciones })
  const turnos = useQuery({ queryKey: ['ausencias', 'turnos'], queryFn: () => ausenciasApi.turnos() })
  const porId = new Map((turnos.data ?? []).map(t => [t.id, t]))
  return (
    <section aria-labelledby="ausadm-rot-titulo" className="ausadm-tarjeta">
      <div className="ausadm-cabecera">
        <h3 id="ausadm-rot-titulo" className="ausadm-subtitulo">{ta('rotaciones_titulo')}</h3>
        <Button size="sm" icon={<Plus size={14} />} onClick={() => setAbierta({ id: null, datos: NUEVA() })}>{ta('nueva_rotacion')}</Button>
      </div>
      <p className="ausadm-ayuda">{ta('rotaciones_ayuda')}</p>
      {q.isLoading ? <Spinner label={ta('cargando')} />
        : q.isError ? <AvisoDeError error={q.error} defecto={ta('error_cargar')} />
        : !(q.data ?? []).length ? <EmptyState svgIcon={<Repeat size={26} />} title={ta('sin_rotaciones')} />
        : (
          <ul className="ausadm-lista">
            {(q.data ?? []).map((r: Rotacion) => (
              <li key={r.id}>
                <button type="button" className={`ausadm-item${r.activo ? '' : ' ausadm-item--inactivo'}`}
                  onClick={() => { const { id: _id, ...resto } = r; setAbierta({ id: r.id, datos: resto }) }}>
                  <Repeat size={16} aria-hidden />
                  <span className="ausadm-item-nombre">{r.nombre}
                    <span className="ausadm-ayuda"> · {ta('ciclo_de_n', { n: r.ciclo.length })} · {ta('n_personas', { n: r.miembros.length })}</span></span>
                  <span className="ausadm-ciclo-mini" aria-hidden>
                    {r.ciclo.map((x, i) => {
                      const t = x ? porId.get(x) : undefined
                      return t ? <Muestra key={i} color={t.color} className="ausadm-muestra--mini" /> : <span key={i} className="ausadm-muestra ausadm-muestra--mini ausadm-muestra--libre" />
                    })}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      {abierta && <Formulario key={abierta.id ?? 'nueva'} id={abierta.id} inicial={abierta.datos} turnos={turnos.data ?? []}
        onCerrar={() => setAbierta(null)} />}
    </section>
  )
}

function Formulario({ id, inicial, turnos, onCerrar }: { id: string | null; inicial: RotacionIn; turnos: Turno[]; onCerrar: () => void }) {
  const { ta } = useT()
  const qc = useQueryClient()
  const toast = useToast()
  const [d, setD] = useState(inicial)
  const refrescar = () => qc.invalidateQueries({ queryKey: ['ausencias'] })
  const guardar = useMutation({
    mutationFn: () => (id ? ausenciasApi.guardarRotacion(id, d) : ausenciasApi.crearRotacion(d)),
    onSuccess: () => { toast.success(ta('guardado')); refrescar(); onCerrar() },
  })
  const borrar = useMutation({
    mutationFn: () => ausenciasApi.borrarRotacion(id as string),
    onSuccess: () => { toast.success(ta('borrado')); refrescar(); onCerrar() },
    onError: e => toast.error(errorDe(e, ta('error_guardar')).mensaje),
  })
  const porId = new Map(turnos.map(t => [t.id, t]))
  return (
    <Modal open onClose={onCerrar} title={id ? ta('editar_rotacion') : ta('nueva_rotacion')} size="lg">
      <form className="ausadm-form" onSubmit={e => { e.preventDefault(); guardar.mutate() }}>
        <div className="ausadm-grid-2">
          <label className="ausadm-campo-con-etiqueta">
            <span className="ausadm-etiqueta">{ta('nombre')}</span>
            <input aria-label={ta('nombre')} className="ausadm-campo" required value={d.nombre} onChange={e => setD({ ...d, nombre: e.target.value })} />
          </label>
          <label className="ausadm-campo-con-etiqueta">
            <span className="ausadm-etiqueta">{ta('inicio_del_ciclo')}</span>
            <input aria-label={ta('inicio_del_ciclo')} type="date" className="ausadm-campo" required value={d.inicio} onChange={e => setD({ ...d, inicio: e.target.value })} />
          </label>
        </div>
        <fieldset className="ausadm-fieldset">
          <legend className="ausadm-etiqueta">{ta('ciclo')}</legend>
          <ol className="ausadm-ciclo">
            {d.ciclo.map((x, i) => (
              <li key={i} className="ausadm-ciclo-dia">
                <span className="ausadm-ayuda">{ta('dia_n', { n: i + 1 })}</span>
                <Muestra color={x ? porId.get(x)?.color : null} className={x ? 'ausadm-muestra--barra' : 'ausadm-muestra--barra ausadm-muestra--libre'} />
                <select className="ausadm-campo ausadm-campo--mini" aria-label={ta('turno_del_dia', { n: i + 1 })} value={x ?? ''}
                  onChange={e => setD({ ...d, ciclo: d.ciclo.map((y, j) => (j === i ? (e.target.value || null) : y)) })}>
                  <option value="">{ta('libre')}</option>
                  {turnos.map(t => <option key={t.id} value={t.id}>{t.nombre}</option>)}
                </select>
              </li>
            ))}
          </ol>
          <div className="ausadm-fila">
            <Button size="xs" variant="secondary" icon={<Plus size={13} />} onClick={() => setD({ ...d, ciclo: [...d.ciclo, null] })}>{ta('anadir_dia')}</Button>
            <Button size="xs" variant="ghost" icon={<Trash2 size={13} />} disabled={d.ciclo.length <= 1}
              onClick={() => setD({ ...d, ciclo: d.ciclo.slice(0, -1) })}>{ta('quitar_ultimo_dia')}</Button>
          </div>
        </fieldset>
        <fieldset className="ausadm-fieldset">
          <legend className="ausadm-etiqueta">{ta('personas')}</legend>
          <p className="ausadm-ayuda">{ta('desfase_ayuda')}</p>
          {d.miembros.map((m, i) => (
            <div key={i} className="ausadm-fila" role="group" aria-label={ta('persona_n', { n: i + 1 })}>
              <span className="ausadm-selector-persona">
                <UserSelect value={m.user_id} onChange={(v: string) => setD({ ...d, miembros: d.miembros.map((x, j) => (j === i ? { ...x, user_id: v } : x)) })} />
              </span>
              <label className="ausadm-fila"><span className="ausadm-ayuda">{ta('desde')}</span>
                <input aria-label={ta('desde')} type="date" className="ausadm-campo" required value={m.desde}
                  onChange={e => setD({ ...d, miembros: d.miembros.map((x, j) => (j === i ? { ...x, desde: e.target.value } : x)) })} /></label>
              <label className="ausadm-fila"><span className="ausadm-ayuda">{ta('hasta')}</span>
                <input aria-label={ta('hasta')} type="date" className="ausadm-campo" value={m.hasta ?? ''}
                  onChange={e => setD({ ...d, miembros: d.miembros.map((x, j) => (j === i ? { ...x, hasta: e.target.value || null } : x)) })} /></label>
              <label className="ausadm-fila"><span className="ausadm-ayuda">{ta('desfase')}</span>
                <input aria-label={ta('desfase')} type="number" min={0} max={d.ciclo.length - 1} className="ausadm-campo ausadm-campo--corto" value={m.desfase}
                  onChange={e => setD({ ...d, miembros: d.miembros.map((x, j) => (j === i ? { ...x, desfase: Number(e.target.value) || 0 } : x)) })} /></label>
              <Button size="xs" variant="ghost" icon={<Trash2 size={13} />} title={ta('quitar')}
                onClick={() => setD({ ...d, miembros: d.miembros.filter((_, j) => j !== i) })}><span className="u-sr-only">{ta('quitar')}</span></Button>
            </div>
          ))}
          <Button size="xs" variant="secondary" icon={<Plus size={13} />}
            onClick={() => setD({ ...d, miembros: [...d.miembros, { user_id: '', desde: d.inicio, hasta: null, desfase: d.miembros.length % d.ciclo.length }] })}>
            {ta('anadir_persona')}</Button>
        </fieldset>
        <Casilla etiqueta={ta('activa')} valor={d.activo} onChange={v => setD({ ...d, activo: v })} />
        <AvisoDeError error={guardar.error} defecto={ta('error_guardar')} />
        <div className="ausadm-acciones">
          {id && <Button variant="danger" icon={<Trash2 size={14} />} loading={borrar.isPending}
            onClick={async () => { if (await confirmar({ title: ta('borrar'), danger: true, message: ta('borrar_rotacion_confirmar') })) borrar.mutate() }}>
            {ta('borrar')}</Button>}
          <Button variant="secondary" onClick={onCerrar}>{ta('cancelar')}</Button>
          <Button type="submit" loading={guardar.isPending}>{ta('guardar')}</Button>
        </div>
      </form>
    </Modal>
  )
}

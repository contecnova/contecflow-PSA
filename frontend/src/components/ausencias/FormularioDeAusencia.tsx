/**
 * Pedir (o editar) una ausencia con vista previa en vivo (tarea #25):
 * días que cuentan con su turno, plazas libres del cupo por día y turno,
 * puesto en la lista de espera, aprobaciones que hará falta, documentos que se
 * pedirán, saldo antes y después, avisos y bloqueos de las políticas. Los
 * documentos se pueden adjuntar ya; se suben al guardar la petición.
 */
import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, Clock, FileText, ListOrdered, Paperclip, ShieldAlert, Trash2, Users } from 'lucide-react'
import { ausenciasApi } from '../../services/api/ausencias'
import type { AusenciaServida, PeticionDeAusencia, VistaPreviaDeAusencia } from '../../services/api/tipos-ausencias'
import { Button, Modal, Spinner } from '../ui'
import DateInput from '../ui/DateInput'
import { UserSelect } from '../ui/EntitySelect'
import IconoDeAusencia from './IconoDeAusencia'
import { AvisoDeError, Muestra } from './admin/comun'
import { fecha, nombreDeTipo, useTa, useTipos, useTiposDeDocumento, useTurnos } from './comun'

interface Adjunto { tipoId: string; fichero: File }

const ESPERA_MS = 350

function useRetrasado<T>(valor: T, ms: number): T {
  const [v, setV] = useState(valor)
  useEffect(() => {
    const id = window.setTimeout(() => setV(valor), ms)
    return () => window.clearTimeout(id)
  }, [valor, ms])
  return v
}

export default function FormularioDeAusencia({ abierto, onCerrar, editar }: {
  abierto: boolean; onCerrar: () => void; editar?: AusenciaServida | null
}) {
  const { ta, lang } = useTa()
  const qc = useQueryClient()
  const tipos = useTipos()
  const turnos = useTurnos().data ?? []
  const docs = useTiposDeDocumento().data ?? []
  const [p, setP] = useState<PeticionDeAusencia>(() => ({
    absence_type_id: editar?.absence_type_id ?? '', start_date: editar?.start_date ?? '', end_date: editar?.end_date ?? '',
    reason: editar?.reason ?? '', shift_id: editar?.shift_id ?? null, substitute_id: editar?.substitute_id ?? null,
    half_day_start: editar?.half_day_start ?? false, half_day_end: editar?.half_day_end ?? false, hours: editar?.hours ?? null,
    id: editar?.id,
  }))
  const [adjuntos, setAdjuntos] = useState<Adjunto[]>([])
  const [subiendo, setSubiendo] = useState(false)
  const tipo = (tipos.data ?? []).find(x => x.id === p.absence_type_id)
  useEffect(() => {
    if (!p.absence_type_id && tipos.data?.length) setP(x => ({ ...x, absence_type_id: tipos.data[0].id }))
  }, [tipos.data, p.absence_type_id])
  const completa = Boolean(p.absence_type_id && p.start_date && p.end_date && p.end_date >= p.start_date)
  const consulta = useRetrasado(p, ESPERA_MS)
  const previa = useQuery({
    queryKey: ['ausencias', 'previa', consulta],
    queryFn: () => ausenciasApi.vistaPrevia(consulta),
    enabled: abierto && completa,
    retry: false,
  })
  const guardar = useMutation({
    mutationFn: async () => {
      const a = editar ? await ausenciasApi.editar(editar.id, p) : await ausenciasApi.pedir(p)
      setSubiendo(true)
      for (const x of adjuntos) await ausenciasApi.subirDocumento(a.id, x.tipoId, x.fichero)
      return a
    },
    onSettled: () => { setSubiendo(false); qc.invalidateQueries({ queryKey: ['ausencias'] }) },
    onSuccess: () => { setAdjuntos([]); onCerrar() },
  })
  const poner = (cambios: Partial<PeticionDeAusencia>) => setP(x => ({ ...x, ...cambios }))
  const v = previa.data
  const bloqueada = Boolean(v && (v.decision === 'block' || v.bloqueos.length))

  return (
    <Modal open={abierto} onClose={onCerrar} title={editar ? ta('editar_ausencia') : ta('pedir_ausencia')} size="lg">
      <form className="aus-formulario" onSubmit={e => { e.preventDefault(); if (completa && !bloqueada) guardar.mutate() }}>
        <div className="aus-formulario-datos">
          <fieldset className="aus-tipos" aria-label={ta('tipo')}>
            <legend className="aus-etiqueta">{ta('tipo')}</legend>
            {tipos.isLoading && <Spinner label={ta('cargando')} />}
            {(tipos.data ?? []).map(t => (
              <label key={t.id} className="aus-tipo-opcion">
                <input type="radio" name="tipo" aria-label={nombreDeTipo(t, lang)} value={t.id} checked={p.absence_type_id === t.id}
                  onChange={() => poner({ absence_type_id: t.id, hours: null })} />
                <Muestra color={t.color} className="aus-tipo"><IconoDeAusencia icono={t.icono} size={14} />{nombreDeTipo(t, lang)}</Muestra>
              </label>
            ))}
          </fieldset>
          <div className="aus-fila">
            <label className="aus-campo-con-etiqueta"><span className="aus-etiqueta">{ta('desde')}</span>
              <DateInput className="aus-campo" aria-label={ta('desde')} value={p.start_date}
                onChange={e => poner({ start_date: e.target.value, end_date: p.end_date && p.end_date >= e.target.value ? p.end_date : e.target.value })} />
            </label>
            <label className="aus-campo-con-etiqueta"><span className="aus-etiqueta">{ta('hasta')}</span>
              <DateInput className="aus-campo" aria-label={ta('hasta')} value={p.end_date} min={p.start_date || undefined}
                onChange={e => poner({ end_date: e.target.value })} />
            </label>
          </div>
          {tipo?.unidad === 'horas' ? (
            <label className="aus-campo-con-etiqueta"><span className="aus-etiqueta">{ta('horas')}</span>
              <input type="number" min={0.25} step={0.25} className="aus-campo aus-campo--corto" aria-label={ta('horas')}
                value={p.hours ?? ''} placeholder={ta('horas_del_turno')}
                onChange={e => poner({ hours: e.target.value === '' ? null : Number(e.target.value) })} />
            </label>
          ) : (
            <div className="aus-fila">
              <label className="aus-casilla"><input type="checkbox" aria-label={ta('medio_dia_inicio')} checked={Boolean(p.half_day_start)}
                onChange={e => poner({ half_day_start: e.target.checked })} />{ta('medio_dia_inicio')}</label>
              {p.end_date !== p.start_date && (
                <label className="aus-casilla"><input type="checkbox" aria-label={ta('medio_dia_fin')} checked={Boolean(p.half_day_end)}
                  onChange={e => poner({ half_day_end: e.target.checked })} />{ta('medio_dia_fin')}</label>
              )}
            </div>
          )}
          {turnos.length > 0 && (
            <label className="aus-campo-con-etiqueta"><span className="aus-etiqueta">{ta('turno')}</span>
              <select className="aus-campo" aria-label={ta('turno')} value={p.shift_id ?? ''} onChange={e => poner({ shift_id: e.target.value || null })}>
                <option value="">{ta('turno_del_cuadrante')}</option>
                {turnos.map(t => <option key={t.id} value={t.id}>{t.nombre} · {t.hora_inicio}–{t.hora_fin}</option>)}
              </select>
            </label>
          )}
          <label className="aus-campo-con-etiqueta">
            <span className="aus-etiqueta">{ta('sustituto')}{tipo?.requiere_sustituto ? ` · ${ta('obligatorio')}` : ''}</span>
            <UserSelect value={p.substitute_id ?? ''} onChange={(id: string) => poner({ substitute_id: id || null })} required={tipo?.requiere_sustituto} />
          </label>
          <label className="aus-campo-con-etiqueta"><span className="aus-etiqueta">{ta('motivo')}</span>
            <textarea className="aus-campo" rows={2} aria-label={ta('motivo')} value={p.reason ?? ''} onChange={e => poner({ reason: e.target.value })} />
          </label>
          <Adjuntos docs={docs.map(d => ({ id: d.id, nombre: d.nombres?.[lang as 'es'] || d.nombre }))} valor={adjuntos} onChange={setAdjuntos} />
        </div>
        <aside className="aus-previa" aria-live="polite" aria-label={ta('vista_previa')}>
          <h3 className="aus-subtitulo">{ta('vista_previa')}</h3>
          {!completa && <p className="aus-ayuda">{ta('previa_elige_fechas')}</p>}
          {completa && previa.isLoading && <Spinner label={ta('calculando')} />}
          {completa && previa.isError && <AvisoDeError error={previa.error} defecto={ta('error_previa')} />}
          {v && <Previa v={v} turnos={turnos.map(t => ({ id: t.id, nombre: t.nombre, color: t.color }))} lang={lang} />}
        </aside>
        {guardar.isError && <AvisoDeError error={guardar.error} defecto={ta('error_guardar')} />}
        <div className="aus-acciones">
          <Button variant="secondary" onClick={onCerrar}>{ta('cancelar')}</Button>
          <Button type="submit" disabled={!completa || bloqueada} loading={guardar.isPending || subiendo}>
            {v?.lista_de_espera ? ta('pedir_en_espera') : editar ? ta('guardar') : ta('pedir')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

function Adjuntos({ docs, valor, onChange }: { docs: { id: string; nombre: string }[]; valor: Adjunto[]; onChange: (a: Adjunto[]) => void }) {
  const { ta } = useTa()
  const [tipoId, setTipoId] = useState('')
  return (
    <fieldset className="aus-fieldset">
      <legend className="aus-etiqueta"><Paperclip size={13} aria-hidden /> {ta('adjuntar_ya')}</legend>
      <div className="aus-fila">
        <select className="aus-campo" aria-label={ta('tipo_de_documento')} value={tipoId} onChange={e => setTipoId(e.target.value)}>
          <option value="">{ta('elige_tipo_de_documento')}</option>
          {docs.map(d => <option key={d.id} value={d.id}>{d.nombre}</option>)}
        </select>
        <input type="file" className="aus-campo" aria-label={ta('fichero')} disabled={!tipoId}
          onChange={e => { const f = e.target.files?.[0]; if (f && tipoId) onChange([...valor, { tipoId, fichero: f }]); e.target.value = '' }} />
      </div>
      {valor.length > 0 && (
        <ul className="aus-lista-simple">
          {valor.map((a, i) => (
            <li key={`${a.fichero.name}-${i}`} className="aus-fila">
              <FileText size={13} aria-hidden /> {docs.find(d => d.id === a.tipoId)?.nombre} · {a.fichero.name}
              <Button size="xs" variant="ghost" icon={<Trash2 size={12} />} onClick={() => onChange(valor.filter((_, j) => j !== i))}
                title={ta('quitar')}><span className="u-sr-only">{ta('quitar')}</span></Button>
            </li>
          ))}
        </ul>
      )}
    </fieldset>
  )
}

function Previa({ v, turnos, lang }: { v: VistaPreviaDeAusencia; turnos: { id: string; nombre: string; color: string }[]; lang: string }) {
  const { ta } = useTa()
  const nombreDeTurno = (id: string | null) => turnos.find(t => t.id === id)?.nombre ?? ta('sin_turno')
  const huecos = useMemo(() => v.cupos.flatMap(c => c.huecos.map(h => ({ ...h, maximo: c.maximo, momento: c.momento }))), [v.cupos])
  return (
    <div className="aus-previa-cuerpo">
      <p className={`aus-decision aus-decision--${v.decision}`}>
        {v.decision === 'block' ? <ShieldAlert size={15} aria-hidden /> : v.decision === 'waitlist' ? <ListOrdered size={15} aria-hidden />
          : <CheckCircle2 size={15} aria-hidden />} {ta(`decision_${v.decision}`)}
      </p>
      {v.bloqueos.map(b => <p key={b} role="alert" className="aus-bloqueo"><ShieldAlert size={13} aria-hidden /> {b}</p>)}
      {v.avisos.map(a => <p key={a} className="aus-aviso"><AlertTriangle size={13} aria-hidden /> {a}</p>)}
      <dl className="aus-datos">
        <dt>{ta('cuentan')}</dt><dd>{ta(`unidad_${v.unidad}`, { n: v.cantidad })} · {ta('dias_laborables', { n: v.dias_laborables })}</dd>
        {v.saldo && (<><dt>{ta('saldo')}</dt>
          <dd>{ta('saldo_antes_despues', { antes: v.saldo.restante, despues: v.saldo_restante ?? '—' })}</dd></>)}
        {v.cobertura_restante !== null && (<><dt>{ta('cobertura_que_queda')}</dt>
          <dd className={v.cobertura_restante < 0 ? 'aus-negativo' : ''}>{v.cobertura_restante}</dd></>)}
        <dt><Users size={12} aria-hidden /> {ta('companeros_ausentes')}</dt><dd>{v.companeros_ausentes}</dd>
      </dl>
      {huecos.length > 0 && (
        <table className="aus-tabla aus-tabla--compacta">
          <caption>{ta('plazas_por_dia_y_turno')}</caption>
          <thead><tr><th scope="col">{ta('dia')}</th><th scope="col">{ta('turno')}</th><th scope="col">{ta('libres')}</th><th scope="col">{ta('en_espera')}</th></tr></thead>
          <tbody>
            {huecos.map(h => (
              <tr key={`${h.fecha}-${h.turno}-${h.grupo}`} className={h.libres <= 0 ? 'aus-fila-llena' : ''}>
                <td>{fecha(h.fecha, lang)}</td><td>{nombreDeTurno(h.turno)}</td>
                <td>{h.libres <= 0 ? ta('lleno') : ta('libres_de', { n: h.libres, max: h.maximo })}</td><td>{h.espera}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {v.cupos.filter(c => c.lleno).map(c => (
        <p key={c.clave} className="aus-aviso"><Clock size={13} aria-hidden /> {c.momento === 'solicitud'
          ? ta('irias_en_espera', { n: c.posicion_estimada ?? 1 }) : ta('lleno_al_aprobar')}</p>
      ))}
      <h4 className="aus-subtitulo">{ta('aprobaciones')}</h4>
      {v.aprobaciones.length === 0 ? <p className="aus-ayuda">{ta(v.decision === 'auto_approve' ? 'sin_aprobacion' : 'aprueba_responsable')}</p> : (
        <ol className="aus-pasos">
          {v.aprobaciones.map((a, i) => (
            <li key={i} className={`aus-paso aus-paso--${a.tipo}`}>
              {a.nombre || ta(`aprobador_${a.aprobador}`)}{a.tipo === 'inform' ? ` · ${ta('informa')}` : ''}
              {a.origen === 'politica' && <span className="aus-chip">{ta('por_politica')}</span>}
            </li>
          ))}
        </ol>
      )}
      <h4 className="aus-subtitulo">{ta('documentos_que_se_piden')}</h4>
      {v.documentos.length === 0 ? <p className="aus-ayuda">{ta('ningun_documento')}</p> : (
        <ul className="aus-lista-simple">
          {v.documentos.map(d => (
            <li key={d.tipo_id}><FileText size={13} aria-hidden /> {d.nombre} · {ta(`plazo_${d.plazo_desde}`, { n: d.plazo_dias })}
              {d.repetir_cada_dias ? ` · ${ta('repite_cada', { n: d.repetir_cada_dias })}` : ''}</li>
          ))}
        </ul>
      )}
      {v.dias.length > 0 && (
        <p className="aus-ayuda">{ta('dias_que_cuentan')}: {v.dias.map(d => `${fecha(d.fecha, lang)}${d.turno ? ` (${nombreDeTurno(d.turno)})` : ''}`).join(', ')}</p>
      )}
    </div>
  )
}

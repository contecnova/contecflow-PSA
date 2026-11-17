/**
 * Pedir (o editar) una ausencia con vista previa en vivo (tarea #25):
 * días que cuentan con su turno, plazas libres del cupo por día y turno,
 * puesto en la lista de espera, aprobaciones que hará falta, documentos que se
 * pedirán, saldo antes y después, avisos y bloqueos de las políticas. Los
 * documentos se pueden adjuntar ya; se suben al guardar la petición.
 *
 * Rev. 180: por días o por horas según los modos del tipo (selector solo si
 * hay más de uno). Por horas se pide una franja (inicio–fin, puede cruzar la
 * medianoche) que vale para cada día del rango; medio día solo si el tipo lo
 * admite. La vista previa enseña las horas que cubre y los días equivalentes,
 * las horas por día, las horas fuera de horario, el redondeo, el saldo antes y
 * después en su unidad y su equivalente, el negativo permitido, las próximas
 * caducidades y las reglas que aplican.
 */
import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle, CalendarClock, CheckCircle2, Clock, FileText, ListOrdered, Paperclip, Scale, ShieldAlert, Trash2, Users,
} from 'lucide-react'
import { ausenciasApi } from '../../services/api/ausencias'
import type { AusenciaServida, PeticionDeAusencia, SaldoDeAusencia, TipoDeAusencia, VistaPreviaDeAusencia } from '../../services/api/tipos-ausencias'
import { Button, Modal, Spinner, Select, TablaSimple, GrupoDeOpciones, Checkbox, Segmentado } from '../ui'
import { CampoFecha } from '../ui/SelectorDeFecha'
import DateInput from '../ui/DateInput'
import { UserSelect } from '../ui/EntitySelect'
import IconoDeAusencia from './IconoDeAusencia'
import { AvisoDeError, Muestra } from './admin/comun'
import { fecha, modosDeTipo, nombreDeTipo, num, textoDeTramos, tramosDe, useTa, useTipos, useTiposDeDocumento, useTurnos } from './comun'

interface Adjunto { tipoId: string; fichero: File }
type Ta = (k: string, p?: Record<string, unknown>) => string

const ESPERA_MS = 350

function useRetrasado<T>(valor: T, ms: number): T {
  const [v, setV] = useState(valor)
  useEffect(() => {
    const id = window.setTimeout(() => setV(valor), ms)
    return () => window.clearTimeout(id)
  }, [valor, ms])
  return v
}

/** El modo con que empieza un tipo: días si lo admite; si no, horas. */
function modoInicial(t: TipoDeAusencia | undefined): 'dias' | 'horas' {
  const m = modosDeTipo(t)
  return m.includes('dias') || m.includes('medio_dia') ? 'dias' : 'horas'
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
    half_day_start: editar?.half_day_start ?? false, half_day_end: editar?.half_day_end ?? false, hours: null,
    modo: editar?.modo, start_time: editar?.start_time ?? null, end_time: editar?.end_time ?? null, id: editar?.id,
  }))
  const [adjuntos, setAdjuntos] = useState<Adjunto[]>([])
  const [subiendo, setSubiendo] = useState(false)
  const tipo = (tipos.data ?? []).find(x => x.id === p.absence_type_id)
  useEffect(() => {
    if (!p.absence_type_id && tipos.data?.length) setP(x => ({ ...x, absence_type_id: tipos.data[0].id }))
  }, [tipos.data, p.absence_type_id])
  const modos = useMemo(() => modosDeTipo(tipo), [tipo])
  const porDias = modos.includes('dias') || modos.includes('medio_dia')
  const porHoras = modos.includes('horas')
  const modo: 'dias' | 'horas' = p.modo === 'horas' && porHoras ? 'horas' : p.modo === 'dias' && porDias ? 'dias' : modoInicial(tipo)
  const franjaValida = modo === 'dias' || Boolean(p.start_time && p.end_time && p.start_time !== p.end_time)
  const completa = Boolean(p.absence_type_id && p.start_date && p.end_date && p.end_date >= p.start_date && franjaValida)
  // Lo que se manda: el modo resuelto y solo lo que vale en ese modo.
  const peticion = useMemo<PeticionDeAusencia>(() => (modo === 'horas'
    ? { ...p, modo, hours: null, half_day_start: false, half_day_end: false }
    : {
        ...p, modo, hours: null, start_time: null, end_time: null,
        half_day_start: modos.includes('medio_dia') && Boolean(p.half_day_start),
        half_day_end: modos.includes('medio_dia') && Boolean(p.half_day_end),
      }), [p, modo, modos])
  const consulta = useRetrasado(peticion, ESPERA_MS)
  const previa = useQuery({
    queryKey: ['ausencias', 'previa', consulta],
    queryFn: () => ausenciasApi.vistaPrevia(consulta),
    enabled: abierto && completa,
    retry: false,
  })
  const guardar = useMutation({
    mutationFn: async () => {
      const a = editar ? await ausenciasApi.editar(editar.id, peticion) : await ausenciasApi.pedir(peticion)
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
  const cruza = Boolean(p.start_time && p.end_time && p.end_time < p.start_time)

  return (
    <Modal open={abierto} onClose={onCerrar} title={editar ? ta('editar_ausencia') : ta('pedir_ausencia')} size="lg">
      <form className="aus-formulario" onSubmit={e => { e.preventDefault(); if (completa && !bloqueada) guardar.mutate() }}>
        <div className="aus-formulario-datos">
          {tipos.isLoading && <Spinner label={ta('cargando')} />}
          <GrupoDeOpciones forma="fila" name="tipo" leyenda={ta('tipo')} valor={p.absence_type_id ?? ''}
            onChange={v => { const t = (tipos.data ?? []).find(x => String(x.id) === v); if (t) poner({ absence_type_id: t.id, hours: null, modo: modoInicial(t) }) }}
            opciones={(tipos.data ?? []).map(t => ({
              valor: String(t.id),
              titulo: <Muestra color={t.color} className="aus-tipo"><IconoDeAusencia icono={t.icono} size={14} />{nombreDeTipo(t, lang)}</Muestra>,
            }))} />
          {porDias && porHoras && (
            <div className="aus-campo-con-etiqueta">
              <span className="aus-etiqueta">{ta('pedir_por')}</span>
              <Segmentado aria-label={ta('pedir_por')} valor={modo} onChange={x => poner({ modo: x as 'dias' | 'horas' })}
                opciones={[{ valor: 'dias', etiqueta: ta('modo_dias') }, { valor: 'horas', etiqueta: ta('modo_horas') }]} />
            </div>
          )}
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
          {modo === 'horas' ? (
            <div className="aus-fila" role="group" aria-label={ta('franja')} aria-describedby="aus-franja-ayuda">
              <label className="aus-campo-con-etiqueta"><span className="aus-etiqueta">{ta('hora_inicio')}</span>
                <CampoFecha modo="hora" className="aus-campo" aria-label={ta('hora_inicio')} required value={p.start_time ?? ''}
                  onChange={x => poner({ start_time: x || null })} />
              </label>
              <label className="aus-campo-con-etiqueta"><span className="aus-etiqueta">{ta('hora_fin')}</span>
                <CampoFecha modo="hora" className="aus-campo" aria-label={ta('hora_fin')} required value={p.end_time ?? ''}
                  onChange={x => poner({ end_time: x || null })} />
              </label>
              <span id="aus-franja-ayuda" className="aus-ayuda" aria-live="polite">{ta(cruza ? 'franja_cruza' : 'franja_ayuda')}</span>
            </div>
          ) : modos.includes('medio_dia') && (
            <div className="aus-fila">
              <Checkbox className="aus-casilla" label={ta('medio_dia_inicio')} checked={Boolean(p.half_day_start)}
                onChange={m => poner({ half_day_start: m })} />
              {p.end_date !== p.start_date && (
                <Checkbox className="aus-casilla" label={ta('medio_dia_fin')} checked={Boolean(p.half_day_end)}
                  onChange={m => poner({ half_day_end: m })} />
              )}
            </div>
          )}
          {turnos.length > 0 && (
            <label className="aus-campo-con-etiqueta"><span className="aus-etiqueta">{ta('turno')}</span>
              <Select suelto className="aus-campo" aria-label={ta('turno')} value={p.shift_id ?? ''} onChange={e => poner({ shift_id: e.target.value || null })} placeholder={ta('turno_del_cuadrante')}>
                {turnos.map(t => <option key={t.id} value={t.id}>{t.nombre} · {textoDeTramos(tramosDe(t))}</option>)}
              </Select>
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
          {!completa && <p className="aus-ayuda">{ta(franjaValida ? 'previa_elige_fechas' : 'previa_elige_franja')}</p>}
          {completa && previa.isLoading && <Spinner label={ta('calculando')} />}
          {completa && previa.isError && <AvisoDeError error={previa.error} defecto={ta('error_previa')} />}
          {v && <Previa v={v} turnos={turnos.map(t => ({ id: t.id, nombre: t.nombre, color: t.color }))} />}
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
    <fieldset className="ds-grupo-opciones aus-fieldset">
      <legend className="aus-etiqueta"><Paperclip size={13} aria-hidden /> {ta('adjuntar_ya')}</legend>
      <div className="aus-fila">
        <Select suelto className="aus-campo" aria-label={ta('tipo_de_documento')} value={tipoId} onChange={e => setTipoId(e.target.value)} placeholder={ta('elige_tipo_de_documento')}>
          {docs.map(d => <option key={d.id} value={d.id}>{d.nombre}</option>)}
        </Select>
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

/** Una cantidad del saldo en su unidad («3 días», «12,5 h»). */
function enUnidad(ta: Ta, unidad: string, n: number | null | undefined): string {
  return n == null ? '—' : ta(`unidad_${unidad}`, { n: num(n) })
}

/** El saldo antes y después de la petición en su unidad y su equivalente en la otra. */
function SaldoDeLaPrevia({ v, s }: { v: VistaPreviaDeAusencia; s: SaldoDeAusencia }) {
  const { ta } = useTa()
  const otra = s.equivalente?.unidad ?? (s.unidad === 'dias' ? 'horas' : 'dias')
  const media = s.media_diaria_horas || 0
  // Equivalente de lo que queda después: el API da las horas; los días salen de la media diaria.
  const despuesEquivalente = v.saldo_restante == null ? null
    : otra === 'horas' ? (v.saldo_restante_horas ?? (media ? v.saldo_restante * media : null))
    : (media ? v.saldo_restante / media : null)
  return (
    <>
      <dt>{ta('saldo')}{s.periodo?.etiqueta ? ` · ${s.periodo.etiqueta}` : ''}</dt>
      <dd>
        {ta('saldo_antes_despues', { antes: enUnidad(ta, s.unidad, s.restante), despues: enUnidad(ta, s.unidad, v.saldo_restante) })}
        {s.equivalente && (
          <span className="aus-ayuda"> ({ta('equivale_a', {
            antes: enUnidad(ta, otra, s.equivalente.restante), despues: enUnidad(ta, otra, despuesEquivalente),
          })})</span>
        )}
        {v.saldo_restante != null && v.saldo_restante < 0 && <span className="aus-negativo"> · {ta('saldo_en_negativo')}</span>}
      </dd>
      {v.negativo_permitido > 0 && (<><dt>{ta('negativo_permitido')}</dt><dd>{enUnidad(ta, s.unidad, v.negativo_permitido)}</dd></>)}
      {(s.proximas_caducidades ?? []).length > 0 && (
        <>
          <dt><CalendarClock size={12} aria-hidden /> {ta('proximas_caducidades')}</dt>
          <dd>
            <ul className="aus-lista-simple">
              {s.proximas_caducidades.map((c, i) => (
                <li key={`${c.fecha}-${i}`}>{ta('caduca_el', { n: enUnidad(ta, s.unidad, c.cantidad), fecha: fecha(c.fecha) })}
                  {c.origen ? ` · ${ta(`origen_saldo_${c.origen}`)}` : ''}</li>
              ))}
            </ul>
          </dd>
        </>
      )}
    </>
  )
}

function Previa({ v, turnos }: { v: VistaPreviaDeAusencia; turnos: { id: string; nombre: string; color: string }[] }) {
  const { ta } = useTa()
  const nombreDeTurno = (id: string | null) => turnos.find(t => t.id === id)?.nombre ?? ta('sin_turno')
  const huecos = useMemo(() => v.cupos.flatMap(c => c.huecos.map(h => ({ ...h, maximo: c.maximo, momento: c.momento }))), [v.cupos])
  const conFranja = huecos.some(h => h.franja)
  const porHoras = v.modo === 'horas'
  return (
    <div className="aus-previa-cuerpo">
      <p className={`aus-decision aus-decision--${v.decision}`}>
        {v.decision === 'block' ? <ShieldAlert size={15} aria-hidden /> : v.decision === 'waitlist' ? <ListOrdered size={15} aria-hidden />
          : <CheckCircle2 size={15} aria-hidden />} {ta(`decision_${v.decision}`)}
      </p>
      {v.bloqueos.map(b => <p key={b} role="alert" className="aus-bloqueo"><ShieldAlert size={13} aria-hidden /> {b}</p>)}
      {v.avisos.map(a => <p key={a} className="aus-aviso"><AlertTriangle size={13} aria-hidden /> {a}</p>)}
      {(v.horas_fuera_de_horario ?? 0) > 0 && (
        <p className="aus-aviso"><AlertTriangle size={13} aria-hidden /> {ta('horas_fuera_de_horario', { n: num(v.horas_fuera_de_horario) })}</p>
      )}
      <dl className="aus-datos">
        <dt>{ta('cuentan')}</dt>
        <dd>{ta(`unidad_${v.unidad}`, { n: num(v.cantidad) })}
          {' · '}{porHoras || v.horas ? ta('horas_y_equivalentes', { h: num(v.horas), n: num(v.dias_laborables) }) : ta('dias_laborables', { n: num(v.dias_laborables) })}</dd>
        {porHoras && v.horas_max_dia > 0 && (<><dt>{ta('horas_max_dia')}</dt><dd>{ta('unidad_horas', { n: num(v.horas_max_dia) })}</dd></>)}
        {v.redondeo && (
          <>
            <dt>{ta('redondeo')}</dt>
            <dd>{ta('redondeo_aplicado', {
              antes: num(v.redondeo.antes), despues: num(v.redondeo.despues), minutos: v.redondeo.minutos,
              modo: ta(`redondeo_${v.redondeo.modo}`),
            })}{v.redondeo.politica ? ` · ${v.redondeo.politica}` : ''}</dd>
          </>
        )}
        {v.saldo && <SaldoDeLaPrevia v={v} s={v.saldo} />}
        {v.cobertura_restante !== null && (<><dt>{ta('cobertura_que_queda')}</dt>
          <dd className={v.cobertura_restante < 0 ? 'aus-negativo' : ''}>{v.cobertura_restante}</dd></>)}
        <dt><Users size={12} aria-hidden /> {ta('companeros_ausentes')}</dt><dd>{v.companeros_ausentes}</dd>
      </dl>
      {v.dias.length > 0 && (
        <TablaSimple claseTabla="aus-tabla aus-tabla--compacta">
          <caption>{ta('horas_por_dia')}</caption>
          <thead><tr><th scope="col">{ta('dia')}</th><th scope="col">{ta('turno')}</th><th scope="col">{ta('horas')}</th></tr></thead>
          <tbody>
            {v.dias.map(d => (
              <tr key={d.fecha}>
                <td>{fecha(d.fecha)}</td><td>{d.turno ? nombreDeTurno(d.turno) : '—'}</td>
                <td>{ta('unidad_horas', { n: num(d.horas) })}</td>
              </tr>
            ))}
          </tbody>
        </TablaSimple>
      )}
      {huecos.length > 0 && (
        <TablaSimple claseTabla="aus-tabla aus-tabla--compacta">
          <caption>{ta('plazas_por_dia_y_turno')}</caption>
          <thead><tr>
            <th scope="col">{ta('dia')}</th><th scope="col">{ta('turno')}</th>
            {conFranja && <th scope="col">{ta('franja')}</th>}
            <th scope="col">{ta('libres')}</th><th scope="col">{ta('en_espera')}</th>
          </tr></thead>
          <tbody>
            {huecos.map(h => (
              <tr key={`${h.fecha}-${h.turno}-${h.grupo}-${h.franja ?? ''}`} className={h.libres <= 0 ? 'aus-fila-llena' : ''}>
                <td>{fecha(h.fecha)}</td><td>{nombreDeTurno(h.turno)}</td>
                {conFranja && <td>{h.franja ?? '—'}</td>}
                <td>{h.libres <= 0 ? ta('lleno') : ta('libres_de', { n: h.libres, max: h.maximo })}</td><td>{h.espera}</td>
              </tr>
            ))}
          </tbody>
        </TablaSimple>
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
      <h4 className="aus-subtitulo"><Scale size={13} aria-hidden /> {ta('reglas_que_aplican')}</h4>
      {(v.politicas_que_aplican ?? []).length === 0 ? <p className="aus-ayuda">{ta('ninguna_regla')}</p> : (
        <ul className="aus-lista-simple">
          {v.politicas_que_aplican.map(x => (
            <li key={x.politica}><strong>{x.politica}</strong>{x.reglas.length > 0 && `: ${x.reglas.join(', ')}`}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

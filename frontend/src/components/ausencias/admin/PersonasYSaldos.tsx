/**
 * Personas (rev. 180): la ficha laboral de cada una (sede, fecha de alta y
 * tipo de contrato, editables en la propia tabla) y sus saldos en su unidad y
 * su equivalente. Al abrir los saldos de una persona se ve el detalle de
 * movimientos de cada saldo (ajustes a mano y horas de la bolsa) y se pueden
 * dar de alta o quitar ajustes con su motivo y su caducidad. «Recalcular
 * bolsa» vuelve a sacar las horas de la bolsa de las imputaciones de un rango.
 */
import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Calculator, Plus, Trash2, Users, Wallet } from 'lucide-react'
import { ausenciasApi } from '../../../services/api/ausencias'
import type { FichaLaboral, FichaLaboralIn, SaldoDeAusencia, SaldosDePersona, UnidadDeSaldo } from '../../../services/api/tipos-ausencias'
import { Button, EmptyState, Modal, Spinner, Select, TablaSimple, Buscador, useErroresDeCampo, Input } from '../../ui'
import DateInput from '../../ui/DateInput'
import { confirmar } from '../../../context/ConfirmContext'
import { useToast } from '../../../context/ToastContext'
import { useOpciones } from '../../politicas/comun'
import TarjetasDeSaldo, { cantidadDeSaldo, useNombreDeSaldo } from '../Saldos'
import { fecha, useTa } from '../comun'
import { AvisoDeError, errorDe, isoDe, useT } from './comun'
import { Filtros } from './MapaDeCobertura'
import { useOficinas } from './EditorDeTurnos'

export default function PersonasYSaldos({ puedeEditar }: { puedeEditar: boolean }) {
  const { ta } = useT()
  const opciones = useOpciones().data
  const [equipo, setEquipo] = useState('')
  const [departamento, setDepartamento] = useState('')
  const [busca, setBusca] = useState('')
  const [abierta, setAbierta] = useState<SaldosDePersona | null>(null)
  const fichas = useQuery({ queryKey: ['ausencias', 'fichas'], queryFn: () => ausenciasApi.fichas(), enabled: puedeEditar })
  const saldos = useQuery({
    queryKey: ['ausencias', 'saldos-personas', equipo, departamento],
    queryFn: () => ausenciasApi.saldosDePersonas({ equipo: equipo || undefined, departamento: departamento || undefined }),
  })
  const porPersona = useMemo(() => new Map((saldos.data ?? []).map(s => [s.user_id, s])), [saldos.data])
  // Filas: las fichas (RRHH y administración) o, si no se ven, las personas con saldos.
  const filas = useMemo(() => {
    const base: FichaLaboral[] = fichas.data ?? (saldos.data ?? []).map(s => ({
      user_id: s.user_id, nombre: s.nombre, equipo: s.equipo, departamento: s.departamento, office_id: null, hire_date: null,
      employment_type: null, weekly_capacity_hours: null,
    }))
    const texto = busca.trim().toLowerCase()
    return base
      .filter(f => (!equipo || f.equipo === equipo) && (!departamento || f.departamento === departamento))
      .filter(f => !texto || f.nombre.toLowerCase().includes(texto))
      .sort((a, b) => a.nombre.localeCompare(b.nombre))
  }, [fichas.data, saldos.data, equipo, departamento, busca])
  const contratos = useMemo(() => [...new Set((fichas.data ?? []).map(f => f.employment_type).filter(Boolean) as string[])].sort(), [fichas.data])

  return (
    <section aria-labelledby="ausadm-personas-titulo" className="u-stack-10">
      <div className="ausadm-cabecera">
        <h2 id="ausadm-personas-titulo" className="ausadm-titulo">{ta('personas_titulo')}</h2>
      </div>
      <p className="ausadm-ayuda">{ta('personas_ayuda')}</p>
      {puedeEditar && <RecalcularBolsa userIds={filas.map(f => f.user_id)} />}
      <div className="ds-toolbar">
        <Buscador value={busca} onChange={setBusca} placeholder={ta('buscar_persona')} />
        <Filtros equipo={equipo} departamento={departamento} equipos={opciones?.equipos ?? []}
          departamentos={opciones?.departamentos ?? []} onEquipo={setEquipo} onDepartamento={setDepartamento} />
      </div>
      {(fichas.isLoading || saldos.isLoading) && <Spinner label={ta('cargando')} />}
      {fichas.isError && <AvisoDeError error={fichas.error} defecto={ta('error_cargar')} />}
      {saldos.isError && <AvisoDeError error={saldos.error} defecto={ta('error_cargar')} />}
      {!fichas.isLoading && !saldos.isLoading && filas.length === 0 && <EmptyState svgIcon={<Users size={26} />} title={ta('sin_personas')} />}
      {filas.length > 0 && (
        <TablaSimple claseTabla="aus-tabla">
          <caption className="u-sr-only">{ta('personas_titulo')}</caption>
          <thead><tr>
            <th scope="col">{ta('persona')}</th><th scope="col">{ta('sede')}</th><th scope="col">{ta('fecha_de_alta')}</th>
            <th scope="col">{ta('tipo_de_contrato')}</th><th scope="col">{ta('saldos')}</th>
          </tr></thead>
          <tbody>
            {filas.map(f => (
              <FilaDePersona key={f.user_id} ficha={f} saldos={porPersona.get(f.user_id)} contratos={contratos}
                editable={puedeEditar && Boolean(fichas.data)} onSaldos={setAbierta} />
            ))}
          </tbody>
        </TablaSimple>
      )}
      {contratos.length > 0 && <datalist id="ausadm-contratos">{contratos.map(c => <option key={c} value={c}>{c}</option>)}</datalist>}
      {abierta && <SaldosDeUnaPersona persona={abierta} puedeEditar={puedeEditar} onCerrar={() => setAbierta(null)} />}
    </section>
  )
}

function FilaDePersona({ ficha, saldos, contratos, editable, onSaldos }: {
  ficha: FichaLaboral; saldos: SaldosDePersona | undefined; contratos: string[]; editable: boolean
  onSaldos: (s: SaldosDePersona) => void
}) {
  const { ta } = useT()
  const t = useTa().ta
  const nombreDeSaldo = useNombreDeSaldo()
  const qc = useQueryClient()
  const toast = useToast()
  const oficinas = useOficinas().data ?? []
  const [contrato, setContrato] = useState(ficha.employment_type ?? '')
  const guardar = useMutation({
    mutationFn: (c: Partial<FichaLaboralIn>) => ausenciasApi.guardarFicha(ficha.user_id, c),
    onSuccess: () => { toast.success(ta('guardado')); qc.invalidateQueries({ queryKey: ['ausencias'] }) },
    onError: e => toast.error(errorDe(e, ta('error_guardar')).mensaje),
  })
  return (
    <tr>
      <th scope="row">{ficha.nombre}<span className="ausadm-ayuda"> {[ficha.equipo, ficha.departamento].filter(Boolean).join(' · ')}</span></th>
      <td>
        {editable ? (
          <Select suelto className="ausadm-campo" aria-label={ta('sede_de', { nombre: ficha.nombre })} value={ficha.office_id ?? ''}
            onChange={e => guardar.mutate({ office_id: e.target.value || null })} placeholder={ta('sin_sede')}>
            {oficinas.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}
          </Select>
        ) : (oficinas.find(o => o.id === ficha.office_id)?.name ?? '—')}
      </td>
      <td>
        {editable ? (
          <DateInput className="ausadm-campo" aria-label={ta('fecha_de_alta_de', { nombre: ficha.nombre })} value={ficha.hire_date ?? ''}
            onChange={e => { if ((e.target.value || null) !== ficha.hire_date) guardar.mutate({ hire_date: e.target.value || null }) }} />
        ) : fecha(ficha.hire_date)}
      </td>
      <td>
        {editable ? (
          <Input aria-label={ta('tipo_de_contrato_de', { nombre: ficha.nombre })} value={contrato} maxLength={40} list={contratos.length ? 'ausadm-contratos' : undefined} placeholder={ta('sin_contrato')} onChange={e => setContrato(e.target.value)} onBlur={() => { if ((contrato || null) !== (ficha.employment_type || null)) guardar.mutate({ employment_type: contrato || null }) }} inputClassName="ausadm-campo" />
        ) : (ficha.employment_type || '—')}
      </td>
      <td>
        {saldos ? (
          <Button size="xs" variant="ghost" icon={<Wallet size={12} />} onClick={() => onSaldos(saldos)}
            title={ta('ver_saldos_de', { nombre: ficha.nombre })}>
            {saldos.saldos.length ? saldos.saldos.map(s => `${nombreDeSaldo(s)} ${cantidadDeSaldo(t, s.unidad, s.restante)}`).join(' · ') : ta('sin_saldos')}
          </Button>
        ) : '—'}
      </td>
    </tr>
  )
}

/** Los saldos de una persona con el detalle de movimientos de cada uno y los ajustes. */
function SaldosDeUnaPersona({ persona, puedeEditar, onCerrar }: { persona: SaldosDePersona; puedeEditar: boolean; onCerrar: () => void }) {
  const { ta } = useT()
  const nombreDeSaldo = useNombreDeSaldo()
  // Los saldos vivos (se refrescan tras un ajuste); la fila abierta solo da el punto de partida.
  const q = useQuery({
    queryKey: ['ausencias', 'saldos-personas', 'una', persona.user_id],
    queryFn: () => ausenciasApi.saldosDePersonas({ user_ids: [persona.user_id] }).then(r => r.find(x => x.user_id === persona.user_id) ?? persona),
    initialData: persona,
  })
  const saldos = q.data?.saldos ?? []
  const [clave, setClave] = useState(saldos[0]?.clave ?? '')
  const elegido = saldos.find(s => s.clave === clave) ?? saldos[0]
  return (
    <Modal open onClose={onCerrar} title={ta('saldos_de', { nombre: persona.nombre })} size="lg">
      <div className="u-stack-14">
        {saldos.length === 0 ? <p className="ausadm-ayuda">{ta('sin_saldos')}</p> : (
          <>
            <TarjetasDeSaldo saldos={saldos} acciones={s => (
              <Button size="xs" variant={s.clave === elegido?.clave ? 'secondary' : 'ghost'} aria-pressed={s.clave === elegido?.clave}
                onClick={() => setClave(s.clave)}>{ta('ver_movimientos')}</Button>
            )} />
            {elegido && (
              <section aria-labelledby="ausadm-mov-titulo" className="u-stack-10">
                <h3 id="ausadm-mov-titulo" className="ausadm-subtitulo">{ta('movimientos_de', { saldo: nombreDeSaldo(elegido) })}</h3>
                <Movimientos userId={persona.user_id} saldo={elegido} puedeEditar={puedeEditar} />
                {puedeEditar && <NuevoAjuste userId={persona.user_id} saldo={elegido} />}
              </section>
            )}
          </>
        )}
        <div className="ausadm-acciones"><Button variant="secondary" onClick={onCerrar}>{ta('cerrar')}</Button></div>
      </div>
    </Modal>
  )
}

/** La clave con que se ajusta un saldo: «vacaciones» o el id del tipo (cupo propio, bolsa). */
const claveDeAjuste = (s: SaldoDeAusencia) => (s.saldo === 'vacaciones' ? 'vacaciones' : (s.tipo_id ?? s.clave))

function Movimientos({ userId, saldo, puedeEditar }: { userId: string; saldo: SaldoDeAusencia; puedeEditar: boolean }) {
  const { ta } = useT()
  const t = useTa().ta
  const qc = useQueryClient()
  const toast = useToast()
  const q = useQuery({
    queryKey: ['ausencias', 'movimientos', userId, claveDeAjuste(saldo)],
    queryFn: () => ausenciasApi.movimientos(userId, claveDeAjuste(saldo)),
  })
  const quitar = useMutation({
    mutationFn: (id: string) => ausenciasApi.quitarAjuste(id),
    onSuccess: () => { toast.success(ta('borrado')); qc.invalidateQueries({ queryKey: ['ausencias'] }) },
    onError: e => toast.error(errorDe(e, ta('error_guardar')).mensaje),
  })
  if (q.isLoading) return <Spinner label={ta('cargando')} />
  if (q.isError) return <AvisoDeError error={q.error} defecto={ta('error_cargar')} />
  const lista = q.data ?? []
  if (!lista.length) return <p className="ausadm-ayuda">{ta('sin_movimientos')}</p>
  return (
    <TablaSimple claseTabla="aus-tabla">
      <caption className="u-sr-only">{ta('movimientos')}</caption>
      <thead><tr>
        <th scope="col">{ta('fecha')}</th><th scope="col">{ta('cantidad')}</th><th scope="col">{ta('origen')}</th>
        <th scope="col">{ta('caduca')}</th><th scope="col">{ta('motivo')}</th>
        {puedeEditar && <th scope="col"><span className="u-sr-only">{ta('acciones')}</span></th>}
      </tr></thead>
      <tbody>
        {lista.map(m => (
          <tr key={m.id}>
            <td>{fecha(m.fecha)}</td>
            <td className={m.cantidad < 0 ? 'aus-negativo' : undefined}>{m.cantidad > 0 ? '+' : ''}{cantidadDeSaldo(t, m.unidad, m.cantidad)}</td>
            <td>{ta(`movimiento_${m.origen}`)}</td>
            <td>{m.caduca ? fecha(m.caduca) : '—'}</td>
            <td>{m.nota || m.referencia || '—'}</td>
            {puedeEditar && (
              <td>{m.origen === 'manual' && (
                <Button size="xs" variant="ghost" icon={<Trash2 size={12} />} loading={quitar.isPending && quitar.variables === m.id}
                  onClick={async () => { if (await confirmar({ title: ta('quitar_ajuste'), danger: true, message: ta('quitar_ajuste_confirmar') })) quitar.mutate(m.id) }}>
                  {ta('quitar')}</Button>
              )}</td>
            )}
          </tr>
        ))}
      </tbody>
    </TablaSimple>
  )
}

function NuevoAjuste({ userId, saldo }: { userId: string; saldo: SaldoDeAusencia }) {
  const { ta } = useT()
  const t = useTa().ta
  const qc = useQueryClient()
  const toast = useToast()
  const [cantidad, setCantidad] = useState('')
  const [unidad, setUnidad] = useState<UnidadDeSaldo>(saldo.unidad)
  const [dia, setDia] = useState(() => isoDe(new Date()))
  const [caduca, setCaduca] = useState('')
  const [nota, setNota] = useState('')
  const n = Number(cantidad)
  const valido = cantidad !== '' && !Number.isNaN(n) && n !== 0 && nota.trim().length > 0
  const campos = useErroresDeCampo()
  const msg = (k: string) => campos.de(k) ? <div className="u-field-error">{campos.de(k)}</div> : null
  const guardar = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: () => ausenciasApi.ajustarSaldo({
      user_id: userId, saldo_clave: claveDeAjuste(saldo), cantidad: n, unidad, fecha: dia || null, caduca: caduca || null, nota: nota.trim(),
    }),
    onSuccess: () => {
      toast.success(ta('ajuste_guardado'))
      setCantidad(''); setNota(''); setCaduca('')
      qc.invalidateQueries({ queryKey: ['ausencias'] })
    },
    onError: (e: unknown) => { campos.recoger(e) },
  })
  return (
    <form className="ausadm-tarjeta" aria-labelledby="ausadm-ajuste-titulo" onSubmit={e => { e.preventDefault(); if (valido) guardar.mutate() }}>
      <span id="ausadm-ajuste-titulo" className="ausadm-etiqueta">{ta('nuevo_ajuste')}</span>
      <div className="ausadm-fila">
        <label className="ausadm-fila"><span className="ausadm-ayuda">{ta('cantidad_mas_menos')}</span>
          <Input type="number" step="0.25" required aria-label={ta('cantidad_mas_menos')} value={cantidad} onChange={e => setCantidad(e.target.value)} className="ausadm-campo--corto" />{msg('cantidad_mas_menos')}
        </label>
        <Select suelto className="ausadm-campo" aria-label={ta('unidad')} value={unidad} placeholder={false}
          onChange={e => setUnidad(e.target.value as UnidadDeSaldo)}>
          {(['dias', 'horas'] as const).map(u => <option key={u} value={u}>{ta(`unidad_${u}`)}</option>)}
        </Select>{msg('unidad')}
        <label className="ausadm-fila"><span className="ausadm-ayuda">{ta('fecha')}</span>
          <DateInput className="ausadm-campo" aria-label={ta('fecha')} value={dia} onChange={e => setDia(e.target.value)} />{msg('fecha')}
        </label>
        <label className="ausadm-fila"><span className="ausadm-ayuda">{ta('caduca')}</span>
          <DateInput className="ausadm-campo" aria-label={ta('caduca')} value={caduca} min={dia || undefined} onChange={e => setCaduca(e.target.value)} />{msg('caduca')}
        </label>
      </div>
      <label className="ausadm-campo-con-etiqueta"><span className="ausadm-ayuda">{ta('motivo_obligatorio')}</span>
        <Input required maxLength={500} aria-label={ta('motivo_obligatorio')} value={nota} onChange={e => setNota(e.target.value)} inputClassName="ausadm-campo" />{msg('motivo_obligatorio')}
      </label>
      {cantidad !== '' && !Number.isNaN(n) && n !== 0 && (
        <span className="ausadm-ayuda">{ta(n > 0 ? 'ajuste_suma' : 'ajuste_resta', { n: cantidadDeSaldo(t, unidad, Math.abs(n)) })}</span>
      )}
      <AvisoDeError error={guardar.error} defecto={ta('error_guardar')} />
      <div className="ausadm-acciones">
        <Button type="submit" size="sm" icon={<Plus size={13} />} disabled={!valido} loading={guardar.isPending}>{ta('anadir_ajuste')}</Button>
      </div>
    </form>
  )
}

/** Vuelve a calcular la bolsa de horas desde las imputaciones de un rango (de las personas a la vista). */
function RecalcularBolsa({ userIds }: { userIds: string[] }) {
  const { ta } = useT()
  const qc = useQueryClient()
  const toast = useToast()
  const hoy = new Date()
  const [desde, setDesde] = useState(() => isoDe(new Date(hoy.getFullYear(), 0, 1)))
  const [hasta, setHasta] = useState(() => isoDe(hoy))
  const [todas, setTodas] = useState(true)
  const recalcular = useMutation({
    mutationFn: () => ausenciasApi.recalcularBolsa(desde, hasta, todas ? undefined : userIds),
    onSuccess: r => {
      toast.success(ta('bolsa_recalculada', { personas: r.personas, creados: r.creados, cambiados: r.cambiados, borrados: r.borrados }))
      qc.invalidateQueries({ queryKey: ['ausencias'] })
    },
  })
  return (
    <form className="ausadm-tarjeta" aria-labelledby="ausadm-bolsa-titulo" onSubmit={e => { e.preventDefault(); if (desde && hasta && hasta >= desde) recalcular.mutate() }}>
      <span id="ausadm-bolsa-titulo" className="ausadm-etiqueta">{ta('recalcular_bolsa')}</span>
      <span className="ausadm-ayuda">{ta('recalcular_bolsa_ayuda')}</span>
      <div className="ausadm-fila">
        <label className="ausadm-fila"><span className="ausadm-ayuda">{ta('desde')}</span>
          <DateInput className="ausadm-campo" aria-label={ta('desde')} value={desde} onChange={e => setDesde(e.target.value)} />
        </label>
        <label className="ausadm-fila"><span className="ausadm-ayuda">{ta('hasta')}</span>
          <DateInput className="ausadm-campo" aria-label={ta('hasta')} value={hasta} min={desde || undefined} onChange={e => setHasta(e.target.value)} />
        </label>
        <Select suelto className="ausadm-campo" aria-label={ta('a_quien')} value={todas ? 'todas' : 'vista'} placeholder={false}
          onChange={e => setTodas(e.target.value === 'todas')}>
          <option value="todas">{ta('todas_las_personas')}</option>
          <option value="vista">{ta('personas_a_la_vista', { n: userIds.length })}</option>
        </Select>
        <Button type="submit" size="sm" variant="secondary" icon={<Calculator size={13} />} loading={recalcular.isPending}
          disabled={!desde || !hasta || hasta < desde}>{ta('recalcular_bolsa')}</Button>
      </div>
      <AvisoDeError error={recalcular.error} defecto={ta('error_guardar')} />
      {recalcular.data && (
        <p className="ausadm-ayuda" role="status">{ta('bolsa_recalculada', {
          personas: recalcular.data.personas, creados: recalcular.data.creados, cambiados: recalcular.data.cambiados, borrados: recalcular.data.borrados,
        })}</p>
      )}
    </form>
  )
}


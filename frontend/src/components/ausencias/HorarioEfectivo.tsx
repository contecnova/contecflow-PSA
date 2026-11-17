/**
 * Horario efectivo persona × día (rev. 180) con la rejilla única del kit
 * (RejillaPersonaDia). Cada celda dice el turno o la jornada que toca ese día
 * (su color y sus horas), el festivo de la sede de la persona (atenuado, con
 * su nombre), si está fuera de contrato, y sus ausencias: la de día completo
 * con el color del tipo; la de horas, como parcial («−2 h») con la franja en
 * el detalle; pendiente = tentativa (borde discontinuo). Una ausencia privada
 * sale como «Ausencia», sin tipo.
 *
 * `RejillaDeHorario` pinta unos datos; `PanelDeHorario` los pide con su
 * navegador de mes y, si no se le dan personas, los filtros de equipo y
 * departamento. Lo usan la administración de ausencias (pestaña «Horario») y
 * la carga por persona del planificador (modo «Horario»).
 */
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CalendarDays, Star } from 'lucide-react'
import { ausenciasApi } from '../../services/api/ausencias'
import type { AusenciaEnHorario, CeldaDeHorario, HorarioEfectivo, PersonaDeHorario } from '../../services/api/tipos-ausencias'
import { EmptyState, NavegadorDeMes, RejillaPersonaDia, Spinner, columnasDeDias, rangoDelMes } from '../ui'
import type { CeldaDeRejilla, EntradaDeLeyenda } from '../ui'
import { politicasApi } from '../../services/api'
import { STALE_5_MIN_MS } from '../../constants/timings'
import { AvisoDeError } from './admin/comun'
import { Filtros } from './admin/MapaDeCobertura'
import { num, textoDeTramos, useTa, useTipos, nombreDeTipo } from './comun'

const PRIVADA = 'private'

/** El nombre de una ausencia del horario en el idioma de la pantalla. */
function useNombreDeAusencia() {
  const { ta, lang } = useTa()
  const tipos = useTipos().data ?? []
  return (a: AusenciaEnHorario) => {
    if (a.tipo === PRIVADA) return ta('privada')
    const t = a.tipo_id ? tipos.find(x => x.id === a.tipo_id) : undefined
    return t ? nombreDeTipo(t, lang) : (a.nombre ?? a.tipo)
  }
}

export function RejillaDeHorario({ datos, titulo }: { datos: HorarioEfectivo; titulo?: string }) {
  const { ta } = useTa()
  const nombreDeAusencia = useNombreDeAusencia()
  const columnas = useMemo(() => columnasDeDias(datos.desde, datos.hasta), [datos.desde, datos.hasta])

  const leyenda = useMemo(() => {
    const vistas = new Map<string, EntradaDeLeyenda>()
    for (const p of datos.personas) {
      for (const c of Object.values(p.celdas)) {
        if (c.laborable && !c.fuera_de_contrato && c.etiqueta) {
          const clave = `h:${c.turno_id ?? c.jornada_id ?? c.etiqueta}`
          if (!vistas.has(clave)) vistas.set(clave, { clave, etiqueta: c.etiqueta, color: c.color, tono: c.color ? undefined : 'info' })
        }
        for (const a of c.ausencias) {
          const clave = `a:${a.tipo === PRIVADA ? PRIVADA : (a.tipo_id ?? a.tipo)}`
          if (!vistas.has(clave)) {
            vistas.set(clave, a.tipo === PRIVADA || !a.color
              ? { clave, etiqueta: nombreDeAusencia(a), tono: 'neutral' }
              : { clave, etiqueta: nombreDeAusencia(a), color: a.color })
          }
        }
      }
    }
    return [
      ...vistas.values(),
      { clave: 'festivo', etiqueta: ta('festivo'), tono: 'neutral' as const },
      { clave: 'fuera', etiqueta: ta('fuera_de_contrato'), tono: 'vacio' as const },
      { clave: 'pendiente', etiqueta: ta('estado_pending'), tono: 'vacio' as const, tentativa: true },
    ]
  }, [datos, ta, nombreDeAusencia])

  if (!datos.personas.length) return <EmptyState svgIcon={<CalendarDays size={26} />} title={ta('horario_sin_personas')} description="" />

  const textoDeAusencia = (a: AusenciaEnHorario) => {
    const franja = !a.completa && a.tramos.length ? ` ${textoDeTramos(a.tramos)}` : ''
    return `${nombreDeAusencia(a)}${franja} (${ta(a.completa ? 'dia_completo' : 'menos_horas', { n: num(a.horas) })}, ${ta(`estado_${a.estado}`)})`
  }
  const detalleDe = (p: PersonaDeHorario, fechaIso: string, c: CeldaDeHorario) => [
    `${p.nombre} · ${fechaIso}`,
    c.fuera_de_contrato ? ta('fuera_de_contrato') : '',
    c.festivo ? `${ta('festivo')}: ${c.festivo}${c.trabaja_festivo ? ` (${ta('trabaja_festivo')})` : ''}` : '',
    c.laborable && c.etiqueta ? `${c.etiqueta} ${textoDeTramos(c.tramos)}${c.pausa_minutos ? ` · ${ta('pausa_n', { n: c.pausa_minutos })}` : ''}` : '',
    !c.laborable && !c.festivo && !c.fuera_de_contrato ? ta('descanso') : '',
    c.horas_teoricas ? ta('horas_de', { h: num(c.horas), t: num(c.horas_teoricas) }) : '',
    ...c.ausencias.map(textoDeAusencia),
    c.libres.length && c.ausencias.length ? `${ta('libre_en')}: ${textoDeTramos(c.libres)}` : '',
  ].filter(Boolean).join('. ')

  const celda = (p: PersonaDeHorario, fechaIso: string): CeldaDeRejilla | null => {
    const c = p.celdas[fechaIso]
    if (!c) return null
    const detalle = detalleDe(p, fechaIso, c)
    if (c.fuera_de_contrato) return { tono: 'vacio', detalle }
    const completa = c.ausencias.find(a => a.completa)
    if (completa) {
      return {
        color: completa.tipo === PRIVADA ? null : completa.color, tono: completa.tipo === PRIVADA || !completa.color ? 'neutral' : undefined,
        tentativa: completa.estado !== 'approved', detalle,
        contenido: <span className="aus-horario-celda" aria-hidden>{nombreDeAusencia(completa).slice(0, 1)}</span>,
      }
    }
    if (c.festivo && !c.trabaja_festivo) return { tono: 'neutral', detalle, contenido: <Star size={10} aria-hidden /> }
    if (!c.laborable) return { detalle }
    const parciales = c.ausencias.filter(a => !a.completa)
    const horasParciales = parciales.reduce((s, a) => s + (a.horas || 0), 0)
    return {
      color: c.color, tono: c.color ? undefined : 'info',
      tentativa: parciales.some(a => a.estado !== 'approved'), detalle,
      contenido: parciales.length
        ? <span className="aus-horario-celda aus-horario-celda--parcial" aria-hidden>{ta('menos_horas', { n: num(horasParciales) })}</span>
        : <span className="aus-horario-celda" aria-hidden>{num(c.horas)}</span>,
    }
  }

  return (
    <RejillaPersonaDia
      titulo={titulo ?? ta('horario_titulo')}
      cabeceraFilas={ta('persona')}
      filas={datos.personas.map(p => ({
        ...p, sub: [p.equipo, ta('horas_de', { h: num(p.horas), t: num(p.horas_teoricas) })].filter(Boolean).join(' · '),
      }))}
      columnas={columnas}
      celda={(p, col) => celda(p, col.clave)}
      leyenda={leyenda}
      notaLeyenda={ta('horario_leyenda')}
    />
  )
}

/** El horario efectivo de un mes: de unas personas (planificador) o con filtros de equipo y departamento. */
export default function PanelDeHorario({ userIds, titulo }: { userIds?: string[]; titulo?: string }) {
  const { ta } = useTa()
  const [mes, setMes] = useState(() => { const h = new Date(); return new Date(h.getFullYear(), h.getMonth(), 1) })
  const { desde, hasta } = rangoDelMes(mes)
  const [equipo, setEquipo] = useState('')
  const [departamento, setDepartamento] = useState('')
  const conFiltros = !userIds
  // Las opciones de equipo y departamento solo hacen falta con filtros (el planificador da las personas).
  const opciones = useQuery({ queryKey: ['politicas', 'opciones'], queryFn: politicasApi.opciones, staleTime: STALE_5_MIN_MS, enabled: conFiltros }).data
  const ids = useMemo(() => (userIds ? [...userIds].sort() : undefined), [userIds])
  const q = useQuery({
    queryKey: ['ausencias', 'horario', desde, hasta, equipo, departamento, ids?.join(',') ?? ''],
    queryFn: () => ausenciasApi.horario({
      desde, hasta, equipo: equipo || undefined, departamento: departamento || undefined, user_ids: ids,
    }),
    enabled: !ids || ids.length > 0,
  })
  return (
    <section className="aus-horario u-stack-10" aria-label={titulo ?? ta('horario_titulo')}>
      <div className="ds-toolbar">
        {conFiltros && (
          <Filtros equipo={equipo} departamento={departamento} equipos={opciones?.equipos ?? []}
            departamentos={opciones?.departamentos ?? []} onEquipo={setEquipo} onDepartamento={setDepartamento} />
        )}
        <div className="ds-toolbar__spacer" />
        <NavegadorDeMes mes={mes} onCambiar={setMes} />
      </div>
      {ids && ids.length === 0 ? <EmptyState svgIcon={<CalendarDays size={26} />} title={ta('horario_sin_personas')} description="" />
        : q.isLoading ? <Spinner label={ta('cargando')} />
        : q.isError ? <AvisoDeError error={q.error} defecto={ta('error_cargar')} />
        : q.data && <RejillaDeHorario datos={q.data} titulo={titulo} />}
    </section>
  )
}

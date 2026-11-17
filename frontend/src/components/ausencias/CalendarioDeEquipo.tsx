/**
 * Calendario del equipo (tarea #25): personas × días del mes con las ausencias
 * (color del tipo; un tipo privado sale como «Ausencia»), festivos, y debajo
 * el mapa de cobertura por turno (requeridas frente a disponibles).
 *
 * 16-11-2026: rejilla única del kit (RejillaPersonaDia) con color por tipo y
 * leyenda (antes barras grises iguales); un solo navegador de mes para el
 * calendario y la cobertura (antes dos, uno con «Noviembre De 2026»); un solo
 * título de cobertura; todo a lo ancho.
 *
 * Rev. 180: una ausencia por horas sale como parcial (marca de reloj, no el
 * día entero) con su franja y sus horas en el detalle.
 */
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CalendarDays, Clock } from 'lucide-react'
import { ausenciasApi } from '../../services/api/ausencias'
import type { AusenciaServida } from '../../services/api/tipos-ausencias'
import { EmptyState, NavegadorDeMes, RejillaPersonaDia, Spinner, columnasDeDias, rangoDelMes } from '../ui'
import type { EntradaDeLeyenda, TonoDeRejilla } from '../ui'
import { COLOR_DATO_POR_DEFECTO } from '../../constants/theme'
import { AvisoDeError } from './admin/comun'
import { PanelDeCobertura } from './admin/MapaDeCobertura'
import { num, useTa } from './comun'

/** Tonos del tema para los tipos que no traen color propio (o traen el gris por defecto). */
const TONOS_DE_TIPO: TonoDeRejilla[] = ['accent', 'purple', 'success', 'warning', 'info', 'orange', 'danger']
const CLAVE_PRIVADA = '__privada'

function colorPropio(c: string | null | undefined): string | null {
  return c && c.toLowerCase() !== COLOR_DATO_POR_DEFECTO.toLowerCase() ? c : null
}

export default function CalendarioDeEquipo({ onAbrir }: { onAbrir: (id: string) => void }) {
  const { ta } = useTa()
  const [ref, setRef] = useState(() => { const h = new Date(); return new Date(h.getFullYear(), h.getMonth(), 1) })
  const { desde, hasta } = rangoDelMes(ref)
  const mes = desde.slice(0, 7)
  const q = useQuery({ queryKey: ['ausencias', 'equipo', mes], queryFn: () => ausenciasApi.delEquipo(mes) })
  const vivas = useMemo(() => (q.data ?? []).filter(x => x.status !== 'cancelled' && x.status !== 'rejected'), [q.data])
  const personas = useMemo(() => {
    const m = new Map<string, { id: string; nombre: string; items: AusenciaServida[] }>()
    for (const a of vivas) {
      const p = m.get(a.user_id) ?? { id: a.user_id, nombre: a.user_name, items: [] }
      p.items.push(a)
      m.set(a.user_id, p)
    }
    return [...m.values()].sort((x, y) => x.nombre.localeCompare(y.nombre))
  }, [vivas])
  // Leyenda: un color por tipo presente en el mes (el privado, neutro) y la muestra de «pendiente».
  const leyenda = useMemo(() => {
    const tipos = new Map<string, EntradaDeLeyenda>()
    let i = 0
    for (const a of [...vivas].sort((x, y) => x.type_label.localeCompare(y.type_label))) {
      const clave = a.private ? CLAVE_PRIVADA : (a.absence_type_id ?? a.type)
      if (tipos.has(clave)) continue
      tipos.set(clave, a.private
        ? { clave, etiqueta: ta('privada'), tono: 'neutral' }
        : { clave, etiqueta: a.type_label, color: colorPropio(a.type_color), tono: TONOS_DE_TIPO[i++ % TONOS_DE_TIPO.length] })
    }
    return [...tipos.values()]
  }, [vivas, ta])
  const conPendientes = vivas.some(a => a.status !== 'approved')
  const conParciales = vivas.some(a => a.modo === 'horas')
  const columnas = useMemo(() => columnasDeDias(desde, hasta), [desde, hasta])
  return (
    <div className="aus-calendario">
      <div className="ds-toolbar">
        <h2 className="aus-titulo-seccion">{ta('calendario_de_equipo')}</h2>
        <div className="ds-toolbar__spacer" />
        <NavegadorDeMes mes={ref} onCambiar={setRef} />
      </div>
      {q.isLoading && <Spinner label={ta('cargando')} />}
      {q.isError && <AvisoDeError error={q.error} defecto={ta('error_cargar')} />}
      {q.data && personas.length === 0 && <EmptyState svgIcon={<CalendarDays size={26} />} title={ta('equipo_sin_ausencias')} description="" />}
      {personas.length > 0 && (
        <RejillaPersonaDia
          titulo={ta('calendario_de_equipo')}
          cabeceraFilas={ta('persona')}
          filas={personas}
          columnas={columnas}
          celda={(p, col) => {
            const delDia = p.items.filter(x => x.start_date <= col.clave && x.end_date >= col.clave)
            // Manda la de día completo; si solo hay por horas, la celda es parcial.
            const a = delDia.find(x => x.modo !== 'horas') ?? delDia[0]
            if (!a) return null
            const tipo = a.private ? ta('privada') : a.type_label
            const parcial = a.modo === 'horas'
            const franjas = delDia.filter(x => x.modo === 'horas' && x.start_time && x.end_time)
              .map(x => `${x.private ? ta('privada') : x.type_label} ${x.start_time}–${x.end_time}`)
            return {
              estado: a.private ? CLAVE_PRIVADA : (a.absence_type_id ?? a.type),
              tentativa: a.status !== 'approved',
              contenido: parcial ? <Clock size={10} aria-hidden /> : undefined,
              detalle: [
                `${p.nombre} · ${tipo} · ${ta(`estado_${a.status}`)}`,
                parcial ? ta('parcial_por_horas') : '',
                franjas.length ? franjas.join(', ') : '',
                parcial && a.scheduled_hours != null ? ta('unidad_horas', { n: num(a.scheduled_hours) }) : '',
              ].filter(Boolean).join(' · '),
              boton: { onClick: () => onAbrir(a.id) },
            }
          }}
          leyenda={[
            ...leyenda,
            ...(conPendientes ? [{ clave: '__pendiente', etiqueta: ta('estado_pending'), tono: 'vacio' as const, tentativa: true }] : []),
          ]}
          notaLeyenda={conParciales ? ta('leyenda_parcial') : undefined}
        />
      )}
      <PanelDeCobertura mes={ref} />
    </div>
  )
}

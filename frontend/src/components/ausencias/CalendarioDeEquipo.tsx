/**
 * Calendario del equipo (tarea #25): personas × días del mes con las ausencias
 * (color del tipo; un tipo privado sale como «Ausencia»), festivos, y debajo
 * el mapa de cobertura por turno (requeridas frente a disponibles).
 */
import { fmtMonth } from '../../utils/helpers'
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CalendarDays, ChevronLeft, ChevronRight } from 'lucide-react'
import { ausenciasApi } from '../../services/api/ausencias'
import type { AusenciaServida } from '../../services/api/tipos-ausencias'
import { Button, EmptyState, Spinner } from '../ui'
import { AvisoDeError, useColorCss } from './admin/comun'
import { PanelDeCobertura } from './admin/MapaDeCobertura'
import { useTa } from './comun'

function mesDe(d: Date) { return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}` }

function Barra({ a, onAbrir }: { a: AusenciaServida; onAbrir: (id: string) => void }) {
  const { ta } = useTa()
  const ref = useColorCss<HTMLButtonElement>(a.type_color)
  return (
    <button ref={ref} type="button" className={`aus-barra aus-barra--${a.status}`} onClick={() => onAbrir(a.id)}
      aria-label={`${a.user_name} · ${a.private ? ta('privada') : a.type_label} · ${ta(`estado_${a.status}`)}`}
      title={`${a.private ? ta('privada') : a.type_label} · ${ta(`estado_${a.status}`)}`} />
  )
}

export default function CalendarioDeEquipo({ onAbrir }: { onAbrir: (id: string) => void }) {
  const { ta, lang } = useTa()
  const [ref, setRef] = useState(() => new Date())
  const mes = mesDe(ref)
  const q = useQuery({ queryKey: ['ausencias', 'equipo', mes], queryFn: () => ausenciasApi.delEquipo(mes) })
  const dias = useMemo(() => {
    const n = new Date(ref.getFullYear(), ref.getMonth() + 1, 0).getDate()
    return Array.from({ length: n }, (_, i) => `${mes}-${String(i + 1).padStart(2, '0')}`)
  }, [ref, mes])
  const personas = useMemo(() => {
    const m = new Map<string, { nombre: string; items: AusenciaServida[] }>()
    for (const a of (q.data ?? []).filter(x => x.status !== 'cancelled' && x.status !== 'rejected')) {
      const p = m.get(a.user_id) ?? { nombre: a.user_name, items: [] }
      p.items.push(a)
      m.set(a.user_id, p)
    }
    return [...m.entries()].sort((x, y) => x[1].nombre.localeCompare(y[1].nombre))
  }, [q.data])
  const mover = (n: number) => setRef(new Date(ref.getFullYear(), ref.getMonth() + n, 1))
  return (
    <div className="aus-calendario">
      <div className="aus-fila">
        <Button size="sm" variant="ghost" icon={<ChevronLeft size={14} />} onClick={() => mover(-1)} title={ta('mes_anterior')}><span className="u-sr-only">{ta('mes_anterior')}</span></Button>
        <strong className="aus-mes">{fmtMonth(ref)}</strong>
        <Button size="sm" variant="ghost" icon={<ChevronRight size={14} />} onClick={() => mover(1)} title={ta('mes_siguiente')}><span className="u-sr-only">{ta('mes_siguiente')}</span></Button>
      </div>
      {q.isLoading && <Spinner label={ta('cargando')} />}
      {q.isError && <AvisoDeError error={q.error} defecto={ta('error_cargar')} />}
      {q.data && personas.length === 0 && <EmptyState svgIcon={<CalendarDays size={26} />} title={ta('equipo_sin_ausencias')} description="" />}
      {personas.length > 0 && (
        <div className="aus-rejilla-scroll">
          <table className="aus-rejilla">
            <caption className="u-sr-only">{ta('calendario_de_equipo')}</caption>
            <thead>
              <tr><th scope="col">{ta('persona')}</th>{dias.map(d => {
                const dia = new Date(`${d}T00:00:00`)
                return <th key={d} scope="col" className={dia.getDay() % 6 === 0 ? 'aus-finde' : ''}>{dia.getDate()}</th>
              })}</tr>
            </thead>
            <tbody>
              {personas.map(([uid, p]) => (
                <tr key={uid}>
                  <th scope="row">{p.nombre}</th>
                  {dias.map(d => {
                    const a = p.items.find(x => x.start_date <= d && x.end_date >= d)
                    return <td key={d}>{a && <Barra a={a} onAbrir={onAbrir} />}</td>
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <h3 className="aus-subtitulo">{ta('cobertura_por_turno')}</h3>
      <PanelDeCobertura />
    </div>
  )
}

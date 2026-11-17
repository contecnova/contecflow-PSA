/**
 * Lista de tramos horarios inicio–fin (rev. 180): un turno partido o el
 * horario de un día de una jornada. Añadir y quitar tramos; cada uno puede
 * cruzar la medianoche (fin menor que el inicio) y se marca.
 */
import { MoonStar, Plus, Trash2 } from 'lucide-react'
import type { Tramo } from '../../../services/api/tipos-ausencias'
import { Button } from '../../ui'
import { CampoFecha } from '../../ui/SelectorDeFecha'
import { useT } from './comun'

export default function EditorDeTramos({ tramos, onChange, leyenda, minimo = 1, compacto = false }: {
  tramos: Tramo[]; onChange: (t: Tramo[]) => void; leyenda: string
  /** Tramos que deben quedar como mínimo (un turno, 1; un día de jornada, 0 = no se trabaja). */
  minimo?: number
  /** Sin leyenda visible (filas de la semana de una jornada). */
  compacto?: boolean
}) {
  const { ta } = useT()
  const cambiar = (i: number, j: 0 | 1, v: string) => onChange(tramos.map((t, k) => (k === i ? (j === 0 ? [v, t[1]] : [t[0], v]) as Tramo : t)))
  // El tramo nuevo empieza donde acaba el anterior (sin horas fijas en el código).
  const anadir = () => {
    const ultimo = tramos[tramos.length - 1]
    onChange([...tramos, [ultimo?.[1] ?? '', ''] as Tramo])
  }
  return (
    <fieldset className={`ds-grupo-opciones ausadm-fieldset${compacto ? ' ausadm-tramos--compacto' : ''}`}>
      <legend className={compacto ? 'u-sr-only' : 'ausadm-etiqueta'}>{leyenda}</legend>
      {tramos.length === 0 && <span className="ausadm-ayuda">{ta('sin_tramos')}</span>}
      {tramos.map(([a, b], i) => (
        <div key={i} className="ausadm-fila ausadm-tramo" role="group" aria-label={ta('tramo_n', { n: i + 1 })}>
          <CampoFecha modo="hora" aria-label={ta('tramo_inicio', { n: i + 1 })} className="ausadm-campo ausadm-campo--corto" required
            value={a} onChange={v => cambiar(i, 0, v)} />
          <span aria-hidden>–</span>
          <CampoFecha modo="hora" aria-label={ta('tramo_fin', { n: i + 1 })} className="ausadm-campo ausadm-campo--corto" required
            value={b} onChange={v => cambiar(i, 1, v)} />
          {a && b && b <= a && <span className="ausadm-chip"><MoonStar size={12} aria-hidden /> {ta('cruza_medianoche')}</span>}
          {tramos.length > minimo && (
            <Button size="xs" variant="ghost" icon={<Trash2 size={13} />} title={ta('quitar_tramo')}
              onClick={() => onChange(tramos.filter((_, k) => k !== i))}><span className="u-sr-only">{ta('quitar_tramo')}</span></Button>
          )}
        </div>
      ))}
      <Button size="xs" variant="ghost" icon={<Plus size={13} />} onClick={anadir}>{ta('anadir_tramo')}</Button>
    </fieldset>
  )
}

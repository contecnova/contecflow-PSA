/**
 * Saldos de ausencia (rev. 180): cada saldo (vacaciones, cupo propio, bolsa de
 * horas) en su unidad y su equivalente en la otra (días ↔ horas con la media
 * diaria de su horario), con su periodo, derecho, arrastre, ajustes, lo usado,
 * lo pedido, lo caducado y las próximas caducidades. Lo usan «Mis ausencias» y
 * la ficha de saldos de una persona en la administración.
 */
import type { ReactNode } from 'react'
import { CalendarClock } from 'lucide-react'
import type { SaldoDeAusencia } from '../../services/api/tipos-ausencias'
import { fecha, nombreDeTipo, num, useTa, useTipos } from './comun'

type Ta = (k: string, p?: Record<string, unknown>) => string

/** «3 días», «12,5 h». */
export function cantidadDeSaldo(ta: Ta, unidad: string, n: number | null | undefined): string {
  return n == null ? '—' : ta(`unidad_${unidad}`, { n: num(n) })
}

/** El nombre de un saldo: el del tipo que lo gobierna (cupo propio, bolsa) o «Vacaciones». */
export function useNombreDeSaldo() {
  const { ta, lang } = useTa()
  const tipos = useTipos().data ?? []
  return (s: Pick<SaldoDeAusencia, 'saldo' | 'tipo_id'>) => {
    const t = s.tipo_id ? tipos.find(x => x.id === s.tipo_id) : undefined
    return t && s.saldo !== 'vacaciones' ? nombreDeTipo(t, lang) : ta(`saldo_${s.saldo}`)
  }
}

/** De dónde sale el derecho («ficha», «tabla+prorrateo»…), traducido. */
export function origenDelDerecho(ta: Ta, origen: string | null | undefined): string {
  if (!origen) return ''
  return origen.split('+').map(o => ta(`derecho_de_${o}`)).join(' + ')
}

export function TarjetaDeSaldo({ s, acciones }: { s: SaldoDeAusencia; acciones?: ReactNode }) {
  const { ta } = useTa()
  const nombre = useNombreDeSaldo()
  return (
    <li className="aus-saldo">
      <span className="aus-ayuda">{nombre(s)}{s.periodo?.etiqueta ? ` · ${s.periodo.etiqueta}` : ''}</span>
      <strong className={s.restante < 0 ? 'aus-negativo' : undefined}>{cantidadDeSaldo(ta, s.unidad, s.restante)}</strong>
      {s.equivalente && (
        <span className="aus-ayuda">{ta('equivale', { n: cantidadDeSaldo(ta, s.equivalente.unidad, s.equivalente.restante) })}</span>
      )}
      <span className="aus-ayuda">{ta('saldo_detalle', {
        usado: num(s.usado), pedido: num(s.pedido), total: num(s.disponible),
      })}</span>
      <span className="aus-ayuda">
        {ta('saldo_derecho', { n: num(s.derecho) })}
        {s.derecho_origen && s.derecho_origen !== 'ninguno' ? ` (${origenDelDerecho(ta, s.derecho_origen)})` : ''}
        {s.arrastre ? ` · ${ta('saldo_arrastre', { n: num(s.arrastre) })}${s.arrastre_caduca ? ` ${ta('hasta_el', { fecha: fecha(s.arrastre_caduca) })}` : ''}` : ''}
        {s.movimientos ? ` · ${ta('saldo_ajustes', { n: num(s.movimientos) })}` : ''}
        {s.caducado ? ` · ${ta('saldo_caducado', { n: num(s.caducado) })}` : ''}
      </span>
      {s.restante_al_cierre !== s.restante && s.periodo?.hasta && (
        <span className="aus-ayuda">{ta('al_cierre', { n: cantidadDeSaldo(ta, s.unidad, s.restante_al_cierre), fecha: fecha(s.periodo.hasta) })}</span>
      )}
      {!s.retribuido && <span className="aus-chip">{ta('no_retribuido')}</span>}
      {(s.proximas_caducidades ?? []).length > 0 && (
        <ul className="aus-lista-simple" aria-label={ta('proximas_caducidades')}>
          {s.proximas_caducidades.slice(0, 3).map((c, i) => (
            <li key={`${c.fecha}-${i}`} className="aus-ayuda"><CalendarClock size={12} aria-hidden />{' '}
              {ta('caduca_el', { n: cantidadDeSaldo(ta, s.unidad, c.cantidad), fecha: fecha(c.fecha) })}
              {c.origen ? ` · ${ta(`origen_saldo_${c.origen}`)}` : ''}</li>
          ))}
        </ul>
      )}
      {acciones}
    </li>
  )
}

export default function TarjetasDeSaldo({ saldos, acciones }: {
  saldos: SaldoDeAusencia[]; acciones?: (s: SaldoDeAusencia) => ReactNode
}) {
  const { ta } = useTa()
  if (!saldos.length) return null
  return (
    <ul className="aus-saldos" aria-label={ta('saldos')}>
      {saldos.map(s => <TarjetaDeSaldo key={s.clave || `${s.saldo}-${s.tipo_id ?? ''}`} s={s} acciones={acciones?.(s)} />)}
    </ul>
  )
}

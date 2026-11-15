/**
 * Ventana de fechas que pinta el planificador de recursos (`/bookings`).
 *
 * El servidor devuelve las reservas que solapan con [date_from, date_to]
 * (`GET /bookings?date_from=&date_to=`), así que la página pide solo lo visible y
 * vuelve a pedir cuando la ventana se mueve (otro nº de semanas), en lugar de
 * cargar todas las reservas.
 */
export interface VentanaDeReservas {
  date_from: string
  date_to: string
}

const dos = (n: number) => String(n).padStart(2, '0')
/** YYYY-MM-DD en hora local (sin pasar por UTC: no desplaza el día). */
const diaLocal = (d: Date) => `${d.getFullYear()}-${dos(d.getMonth() + 1)}-${dos(d.getDate())}`

/** Desde el lunes de la primera semana hasta el domingo de la última (`semanas` ≥ 1). */
export function ventanaVisible(lunesInicial: Date, semanas: number): VentanaDeReservas {
  const fin = new Date(lunesInicial)
  fin.setDate(fin.getDate() + Math.max(1, semanas) * 7 - 1)
  return { date_from: diaLocal(lunesInicial), date_to: diaLocal(fin) }
}

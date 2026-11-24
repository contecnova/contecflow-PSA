// Atajos «G + letra» (23-11-2026). La ventana de atajos (?) anunciaba G T, G P,
// G I y G S y ningún código los atendía. Aquí la lógica pura (sin React), para
// que Layout la use y las pruebas la ejerciten sin montar la aplicación.

/** Destino de cada segunda tecla tras «G». */
export const ATAJOS_IR: Readonly<Record<string, string>> = {
  t: '/tasks',
  p: '/projects',
  i: '/imputar',
  s: '/service-desk',
}

/** Tiempo para pulsar la segunda tecla después de «G». */
export const ESPERA_SEGUNDA_TECLA_MS = 1500

/** Un campo donde se escribe: ahí las letras son texto, no atajos. */
export function esCampoDeTexto(objetivo: EventTarget | null): boolean {
  const el = objetivo as HTMLElement | null
  if (!el) return false
  const tag = el.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || !!el.isContentEditable
}

export type ResultadoSecuencia = { tipo: 'espera' } | { tipo: 'ir'; ruta: string } | null

/**
 * Estado de la secuencia «G + letra». Devuelve una función que recibe cada
 * pulsación (tecla ya en minúsculas, sin modificadores ni campo de texto) y dice
 * si hay que esperar la segunda tecla, ir a una ruta o nada.
 */
export function crearSecuenciaIr(ahora: () => number = () => Date.now()) {
  let desde = 0
  return (tecla: string): ResultadoSecuencia => {
    const t = (tecla || '').toLowerCase()
    if (desde && ahora() - desde <= ESPERA_SEGUNDA_TECLA_MS) {
      desde = 0
      const ruta = ATAJOS_IR[t]
      return ruta ? { tipo: 'ir', ruta } : null
    }
    desde = 0
    if (t === 'g') {
      desde = ahora()
      return { tipo: 'espera' }
    }
    return null
  }
}

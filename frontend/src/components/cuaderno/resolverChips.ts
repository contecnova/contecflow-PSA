/**
 * Estado vivo de los chips (`#` objetos, `@` personas): se piden en lote
 * (`POST /notebook/chips/resolve`) con una pequeña espera para juntar los de la
 * página, y se guardan un minuto. El servidor solo devuelve lo que quien lee
 * puede ver (`hidden` si no).
 */
import { cuadernoApi } from '../../services/api/cuaderno'
import type { Chip } from '../../services/api/cuaderno'

const VIGENCIA_MS = 60_000
const ESPERA_MS = 40

const cache = new Map<string, { chip: Chip; en: number }>()
let cola: { clave: string; type: string; id: string; resolver: (c: Chip) => void }[] = []
let temporizador: ReturnType<typeof setTimeout> | null = null

const claveDe = (type: string, id: string) => `${type}:${id}`

async function vaciar() {
  temporizador = null
  const lote = cola
  cola = []
  const unicos = [...new Map(lote.map(x => [x.clave, { type: x.type, id: x.id }])).values()]
  let resueltos: Chip[] = []
  try {
    resueltos = await cuadernoApi.resolverChips(unicos.slice(0, 200))
  } catch {
    resueltos = []
  }
  const por = new Map(resueltos.map(c => [claveDe(c.type, c.id), c]))
  const ahora = Date.now()
  for (const x of lote) {
    const chip = por.get(x.clave) ?? { type: x.type as Chip['type'], id: x.id, hidden: true }
    if (por.has(x.clave)) cache.set(x.clave, { chip, en: ahora })
    x.resolver(chip)
  }
}

/** El estado del chip (de la caché si es reciente). */
export function resolverChip(type: string, id: string): Promise<Chip> {
  const clave = claveDe(type, id)
  const c = cache.get(clave)
  if (c && Date.now() - c.en < VIGENCIA_MS) return Promise.resolve(c.chip)
  return new Promise(resolver => {
    cola.push({ clave, type, id, resolver })
    if (!temporizador) temporizador = setTimeout(() => { void vaciar() }, ESPERA_MS)
  })
}

/** Olvida la caché (al crear un objeto desde la nota, para que salga con su estado). */
export function olvidarChips(): void {
  cache.clear()
}

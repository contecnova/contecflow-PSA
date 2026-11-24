/**
 * «Mi cuaderno» sin conexión (docs/CUADERNO.md §Sin conexión).
 *
 * - Cada persona y empresa tiene SU base (IndexedDB `contecflow_cuaderno_<empresa>_<usuario>`):
 *   nadie más en el mismo navegador lee ni sincroniza lo de otra persona, y cambiar de
 *   empresa no mezcla notas. Fuera de sesión no hay base (todo devuelve vacío).
 * - `paginas`: copia de las últimas páginas abiertas, para volver a abrirlas sin red.
 * - `pendientes`: guardados que no llegaron al servidor (uno por página: el último).
 * - Al volver la red (`sincronizar`): se manda cada pendiente con su `base_version`;
 *   si la página cambió entretanto (409), lo escrito sin red se guarda como página nueva
 *   «(copia sin conexión)» en la misma sección: no se pierde nada ni se pisa lo de otro.
 */
import Dexie from 'dexie'
import type { Table } from 'dexie'
import { cuadernoApi } from '../../services/api/cuaderno'
import type { DocJSON, Pagina } from '../../services/api/cuaderno'

export interface Pendiente {
  page_id: string
  section_id: string
  title: string
  content: DocJSON
  base_version: number
  yjs_state?: string
  guardado_en: string
}

interface CopiaDePagina { id: string; datos: Pagina; guardada_en: string }

class BaseDelCuaderno extends Dexie {
  paginas!: Table<CopiaDePagina, string>
  pendientes!: Table<Pendiente, string>
  constructor(nombre: string) {
    super(nombre)
    this.version(1).stores({ paginas: 'id, guardada_en', pendientes: 'page_id, guardado_en' })
  }
}

let ambito: string | null = null
let base: BaseDelCuaderno | null = null
const MAX_COPIAS = 50

/** Lo fija la pantalla con la sesión: `null` al salir (cierra la base de la persona anterior). */
export function establecerAmbitoCuaderno(userId: string | null | undefined, orgId: string | null | undefined): void {
  const nuevo = userId ? `${(orgId || 'sin-empresa').replace(/[^\w-]/g, '')}_${userId.replace(/[^\w-]/g, '')}` : null
  if (nuevo === ambito) return
  base?.close()
  base = null
  ambito = nuevo
}

function bd(): BaseDelCuaderno | null {
  if (!ambito || typeof indexedDB === 'undefined') return null
  if (!base) base = new BaseDelCuaderno(`contecflow_cuaderno_${ambito}`)
  return base
}

export async function guardarCopia(p: Pagina): Promise<void> {
  const b = bd()
  if (!b) return
  try {
    await b.paginas.put({ id: p.id, datos: p, guardada_en: new Date().toISOString() })
    const n = await b.paginas.count()
    if (n > MAX_COPIAS) {
      const viejas = await b.paginas.orderBy('guardada_en').limit(n - MAX_COPIAS).primaryKeys()
      await b.paginas.bulkDelete(viejas)
    }
  } catch { /* sin IndexedDB (modo privado): se sigue sin copia */ }
}

export async function leerCopia(id: string): Promise<Pagina | null> {
  const b = bd()
  if (!b) return null
  try {
    const fila = await b.paginas.get(id)
    if (!fila) return null
    const pendiente = await b.pendientes.get(id)
    return pendiente ? { ...fila.datos, content: pendiente.content, title: pendiente.title } : fila.datos
  } catch { return null }
}

export async function encolar(p: Pendiente): Promise<boolean> {
  const b = bd()
  if (!b) return false
  try {
    const previo = await b.pendientes.get(p.page_id)
    // La versión base es la del primer guardado sin red: así se detecta lo que cambió en el servidor.
    await b.pendientes.put({ ...p, base_version: previo ? previo.base_version : p.base_version })
    return true
  } catch { return false }
}

export async function pendientes(): Promise<Pendiente[]> {
  const b = bd()
  if (!b) return []
  try { return await b.pendientes.toArray() } catch { return [] }
}

export async function hayPendiente(pageId: string): Promise<boolean> {
  const b = bd()
  if (!b) return false
  try { return !!(await b.pendientes.get(pageId)) } catch { return false }
}

function esErrorDeRed(e: unknown): boolean {
  const r = (e as { response?: unknown; code?: string })
  return !r?.response || r?.code === 'ERR_NETWORK'
}

function esConflicto(e: unknown): boolean {
  return (e as { response?: { status?: number } })?.response?.status === 409
}

export interface ResultadoDeSincronizacion { enviados: number; copias: number; fallidos: number }

let sincronizando: Promise<ResultadoDeSincronizacion> | null = null

/** Manda lo pendiente de ESTA persona y empresa. Una sola vez a la vez. */
export function sincronizar(sufijoCopia: string): Promise<ResultadoDeSincronizacion> {
  if (sincronizando) return sincronizando
  sincronizando = (async () => {
    const res: ResultadoDeSincronizacion = { enviados: 0, copias: 0, fallidos: 0 }
    const b = bd()
    if (!b) return res
    for (const p of await pendientes()) {
      try {
        await cuadernoApi.guardar(p.page_id, { content: p.content, title: p.title, base_version: p.base_version })
        res.enviados += 1
        await b.pendientes.delete(p.page_id)
      } catch (e) {
        if (esConflicto(e)) {
          try {
            await cuadernoApi.crearPagina(p.section_id, { title: `${p.title || ''} ${sufijoCopia}`.trim(), content: p.content })
            res.copias += 1
            await b.pendientes.delete(p.page_id)
          } catch { res.fallidos += 1 }
        } else if (esErrorDeRed(e)) {
          res.fallidos += 1
          break
        } else {
          // La página ya no existe o no se puede escribir: se conserva como copia nueva si se puede.
          res.fallidos += 1
        }
      }
    }
    return res
  })().finally(() => { sincronizando = null })
  return sincronizando
}

export { esErrorDeRed }

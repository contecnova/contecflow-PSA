// Catálogo de procesos BPM del sistema. Estructura (ids, orden, SLA numérico,
// diagrama) en ./estructura.ts, independiente del idioma; los textos se piden
// con import() por idioma —como los diccionarios principales— para que ni el
// castellano ni el inglés ni el chino engorden el chunk de la página.
import { buildBpmn } from '../generadorBpmn'
import { ESTRUCTURA_CATALOGO } from './estructura'
import { ESTRUCTURA_LINEAL } from './estructuraLineal'
import type { EstructuraProceso, TextoProceso, TextosCatalogo, TextosLineales } from './tipos'

export type ProcesoCatalogo = {
  id: string
  category: string
  name: string
  description: string
  owner: string
  sla: string
  steps: string[]
  bpmn: string
}

const CARGADORES: Record<string, () => Promise<{ default: TextosCatalogo }>> = {
  es: () => import('./textos/es'),
  en: () => import('./textos/en'),
  zh: () => import('./textos/zh'),
}

const CARGADORES_LINEALES: Record<string, () => Promise<{ default: TextosLineales }>> = {
  es: () => import('./textosLineales/es'),
  en: () => import('./textosLineales/en'),
  zh: () => import('./textosLineales/zh'),
}

const cache: Record<string, TextosCatalogo> = {}
const cacheLineales: Record<string, TextosLineales> = {}

/**
 * Textos del catálogo en el idioma pedido (castellano si no existe): los de los
 * procesos con diagrama propio y los de los procesos lineales.
 */
export async function cargarTextosCatalogo(
  lang: string,
): Promise<{ lang: string; textos: TextosCatalogo; lineales: TextosLineales }> {
  const codigo = lang in CARGADORES ? lang : 'es'
  if (!cache[codigo]) cache[codigo] = (await CARGADORES[codigo]()).default
  if (!cacheLineales[codigo]) cacheLineales[codigo] = (await CARGADORES_LINEALES[codigo]()).default
  return { lang: codigo, textos: cache[codigo], lineales: cacheLineales[codigo] }
}

function slaTexto(e: EstructuraProceso, x: TextoProceso, t: (k: string, p?: Record<string, unknown>) => string): string {
  if (e.slaDiasHabiles !== undefined) {
    return t(e.slaDiasHabiles === 1 ? 'bpm.sla_dia_habil' : 'bpm.sla_dias_habiles', { n: e.slaDiasHabiles })
  }
  return x.sla ?? ''
}

/** Une estructura y textos: los procesos listos para mostrar y para generar su BPMN. */
export function construirCatalogo(
  textos: TextosCatalogo,
  t: (k: string, p?: Record<string, unknown>) => string,
  lineales: TextosLineales = {},
): ProcesoCatalogo[] {
  const conDiagramaPropio = ESTRUCTURA_CATALOGO.map(e => {
    const x = textos[e.id]
    let n = 0
    const conns = e.flujos.map(([desde, hasta, etiquetado]) => (
      etiquetado ? [desde, hasta, x.flows[n++]] as [string, string, string] : [desde, hasta] as [string, string]
    ))
    return {
      id: e.id,
      category: e.category,
      name: x.name,
      description: x.description,
      owner: x.owner,
      sla: slaTexto(e, x, t),
      steps: x.steps,
      bpmn: buildBpmn(
        e.id,
        x.diagrama ?? x.name,
        e.nodos.map(({ id, type, col, row, sinNombre }) => ({ id, type, col, row, name: sinNombre ? '' : x.nodes[id] })),
        conns,
      ),
    }
  })
  return [...conDiagramaPropio, ...construirLineales(lineales)]
}

/**
 * Procesos lineales: cadena de pasos con el mismo diagrama que genera el backend
 * al sembrarlos (inicio, tareas, fin). No tienen responsable ni SLA en el origen,
 * así que van vacíos en vez de inventarse.
 */
export function construirLineales(lineales: TextosLineales): ProcesoCatalogo[] {
  return ESTRUCTURA_LINEAL.filter(e => lineales[e.id]).map(e => {
    const x = lineales[e.id]
    const nodos = x.steps.map((name, i) => ({
      id: i === 0 ? 'StartEvent_1' : i === x.steps.length - 1 ? `EndEvent_${i + 1}` : `Activity_${i + 1}`,
      type: i === 0 ? 'startEvent' : i === x.steps.length - 1 ? 'endEvent' : 'task',
      col: i,
      name,
    }))
    const conns = nodos.slice(1).map((n, i) => [nodos[i].id, n.id] as [string, string])
    return {
      id: e.id,
      category: e.category,
      name: x.name,
      description: x.description,
      owner: '',
      sla: '',
      steps: x.steps,
      bpmn: buildBpmn(e.id, x.name, nodos, conns),
    }
  })
}

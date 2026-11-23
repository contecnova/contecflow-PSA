// Tipos, etiquetas y nodo visual compartidos por el disenador de flujos. 23-11-2026: troceado de WorkflowDesignerPage sin cambio de comportamiento.
import type { CSSProperties, ReactNode } from 'react'
import type { AxiosError } from 'axios'
import type { Edge, Node, NodeProps } from '@xyflow/react'
import { NodoDeFlujo } from '../../components/flujos/LienzoDeFlujo'
import { CheckCircle, Clock, Bell, Globe, Ticket, Play, Square, Circle, Diamond } from 'lucide-react'
import type { SdBlueprint, SdDetalleDeEjecucion, SdGrafoDeFlujo, SdPlantillaDeFlujo, SdValidacionDeFlujo, SdValorDeConfigDeNodo } from '../../services/api/tipos-sd'
import type { StatusBadgeKind } from '../../components/ui/StatusBadge'
import { useAppLang } from '../../i18n/AppLangContext'

// ── Catálogo visual de los nodos (color + icono por tipo) ────────────────────
// El nombre de cada tipo se traduce al pintarlo: `workflowdesigner.nodo_<tipo>`.
// Iconos lucide (antes emojis y símbolos de texto), los mismos en paleta y lienzo.
export const NODE_VISUAL: Record<string, { color: string; icon: ReactNode }> = {
  start:         { color: 'var(--success)', icon: <Play size={12} /> },
  end:           { color: 'var(--danger)', icon: <Square size={12} /> },
  state:         { color: 'var(--accent)', icon: <Circle size={12} /> },
  decision:      { color: 'var(--warning)', icon: <Diamond size={12} /> },
  approval:      { color: 'var(--purple)', icon: <CheckCircle size={12} /> },
  wait:          { color: 'var(--text-3)', icon: <Clock size={12} /> },
  notify:        { color: 'var(--chart-teal)', icon: <Bell size={12} /> },
  http_call:     { color: 'var(--chart-pink)', icon: <Globe size={12} /> },
  create_ticket: { color: 'var(--sky-blue)', icon: <Ticket size={12} /> },
}

type Traducir = (clave: string, params?: Record<string, string | number>) => string

/** Nombre del tipo de nodo en el idioma activo (o el codigo si es un tipo desconocido). */
export const nombreDeNodo = (tipo: string, traducir: Traducir) =>
  NODE_VISUAL[tipo] ? traducir(`workflowdesigner.nodo_${tipo}`) : tipo

/** Color del dato (tipo de nodo, estado) para las clases `.wfd-*` que lo leen. */
export const colorVar = (c: string) => ({ '--wfd-c': c } as CSSProperties)

// ── Tipos: respuestas en services/api/tipos-sd.ts; aquí, los del lienzo ──
export type ValorConfig = SdValorDeConfigDeNodo

type ConfigNodo = Record<string, ValorConfig>

export type DatosNodo = { label?: string; type: string; config?: ConfigNodo }

export type NodoFlujo = Node<DatosNodo>

export type AristaFlujo = Edge<{ branch?: string }>

export type GrafoGuardado = SdGrafoDeFlujo

export type Blueprint = SdBlueprint

export type PlantillaFlujo = SdPlantillaDeFlujo

export type DetalleEjecucion = SdDetalleDeEjecucion

export type ValidacionGrafo = SdValidacionDeFlujo

/** `detail` de un error del diseñador: texto, o `{message, errors}` si el grafo no valida. */
type DetalleError = string | { message?: string; errors?: string[] }

export type ErrorDeFlujo = AxiosError<{ detail?: DetalleError }>

export const mensajeDelDetalle = (d: DetalleError | undefined) => (typeof d === 'object' ? d?.message : undefined)

export const PROCESOS = ['ticket', 'change', 'approval']

export const nombreDeProceso = (p: string, traducir: Traducir) =>
  PROCESOS.includes(p) ? traducir(`workflowdesigner.proc_${p}`) : p

// Estados de una ejecucion y de sus pasos que tienen traduccion.
const ESTADOS_DE_EJECUCION = ['running', 'waiting', 'completed', 'cancelled', 'error', 'done']

export const nombreDeEstado = (s: string, traducir: Traducir) =>
  ESTADOS_DE_EJECUCION.includes(s) ? traducir(`workflowdesigner.run_${s}`) : s

export const ESTADO_KIND: Record<string, StatusBadgeKind> = {
  running: 'accent', waiting: 'warning', completed: 'success', done: 'success', cancelled: 'neutral', error: 'danger',
}

// Ramas de una arista (valor del servidor) -> etiqueta legible.
const RAMAS = ['next', 'true', 'false', 'approved', 'rejected', 'success', 'failure']

export const nombreDeRama = (b: string, traducir: Traducir) =>
  RAMAS.includes(b) ? traducir(`workflowdesigner.rama_${b}`) : b

// Tipo de entidad de una ejecución: los procesos más «manual».
export const nombreDeEntidad = (e: string, traducir: Traducir) =>
  e === 'manual' ? traducir('workflowdesigner.manual') : nombreDeProceso(e, traducir)

// Clases compartidas de los formularios
export const labelStyle = 'wfd-label'

// ── Custom node para ReactFlow ───────────────────────────────────────────────
function WorkflowNode({ data, selected }: NodeProps<NodoFlujo>) {
  // Tarjeta compartida con el diseñador de aprobaciones (components/flujos, tarea #26).
  const { t: traducir } = useAppLang()
  const v = NODE_VISUAL[data.type] || NODE_VISUAL.state
  return <NodoDeFlujo color={v.color} icono={v.icon} tipo={nombreDeNodo(NODE_VISUAL[data.type] ? data.type : 'state', traducir)} nombre={data.label || traducir('workflowdesigner.sin_nombre')}
    seleccionado={selected} entrada={data.type !== 'start'} salidas={data.type === 'end' ? [] : undefined} />
}

export const nodeTypes = { wf: WorkflowNode }

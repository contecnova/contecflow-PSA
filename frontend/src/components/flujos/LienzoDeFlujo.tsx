/**
 * Piezas compartidas de los diseñadores de flujos sobre `@xyflow/react`
 * (Service Desk y aprobaciones, tarea #26): el nodo-tarjeta con sus asas y el
 * lienzo con rejilla, controles y minimapa. Cada diseñador pone su paleta, su
 * panel de propiedades y su catálogo de tipos de nodo.
 */
import type { ReactNode } from 'react'
import { Background, Controls, Handle, MiniMap, Position, ReactFlow } from '@xyflow/react'
import type { Edge, Node, OnConnect, OnEdgesChange, OnNodesChange } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import './flujos.css'

export interface SalidaDeNodo { id: string; etiqueta: string; posicion?: number }

/** Tarjeta de un nodo: color, icono, tipo y nombre; asas de entrada y salida(s). */
export function NodoDeFlujo({ color, icono, tipo, nombre, seleccionado, entrada = true, salidas = [{ id: '', etiqueta: '' }], error }: {
  color: string; icono: ReactNode; tipo: string; nombre: string; seleccionado?: boolean; entrada?: boolean
  salidas?: SalidaDeNodo[]; error?: string | null
}) {
  return (
    <div className={`flujo-nodo${seleccionado ? ' flujo-nodo--seleccionado' : ''}${error ? ' flujo-nodo--error' : ''}`}
      style={{ ['--flujo-color' as string]: color }} title={error ?? undefined}>
      {entrada && <Handle type="target" position={Position.Left} className="flujo-asa" />}
      <div className="flujo-nodo-tipo"><span aria-hidden>{icono}</span>{tipo}</div>
      <div className="flujo-nodo-nombre">{nombre}</div>
      {error && <div className="flujo-nodo-error" role="alert">{error}</div>}
      {salidas.map((s, i) => (
        <Handle key={s.id || i} id={s.id || undefined} type="source" position={Position.Right} className="flujo-asa"
          style={salidas.length > 1 ? { top: `${((i + 1) * 100) / (salidas.length + 1)}%` } : undefined}>
          {s.etiqueta && <span className="flujo-asa-etiqueta">{s.etiqueta}</span>}
        </Handle>
      ))}
    </div>
  )
}

/** Lienzo con las opciones comunes: rejilla de 16, borrar con Supr/Retroceso, encajar, minimapa. */
export function LienzoDeFlujo<N extends Node, E extends Edge>({ nodes, edges, onNodesChange, onEdgesChange, onConnect, nodeTypes,
  onSeleccion, colorDeNodo, etiqueta, children }: {
  nodes: N[]; edges: E[]; onNodesChange: OnNodesChange<N>; onEdgesChange: OnEdgesChange<E>; onConnect: OnConnect
  nodeTypes: Record<string, React.ComponentType<never>>; onSeleccion: (n: N | null) => void
  colorDeNodo: (n: N) => string; etiqueta: string; children?: ReactNode
}) {
  return (
    <div className="flujo-lienzo" role="application" aria-label={etiqueta}>
      <ReactFlow<N, E> nodes={nodes} edges={edges} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={onConnect}
        nodeTypes={nodeTypes as never} onSelectionChange={({ nodes: sel }) => onSeleccion((sel?.[0] as N) ?? null)}
        onNodeClick={(_, n) => onSeleccion(n)} onPaneClick={() => onSeleccion(null)} deleteKeyCode={['Delete', 'Backspace']}
        snapToGrid snapGrid={[16, 16]} fitView proOptions={{ hideAttribution: true }}>
        <Background gap={16} color="var(--surface-4)" />
        <Controls showInteractive={false} />
        <MiniMap<N> pannable zoomable nodeColor={colorDeNodo} maskColor="var(--overlay-scrim)" />
      </ReactFlow>
      {children}
    </div>
  )
}

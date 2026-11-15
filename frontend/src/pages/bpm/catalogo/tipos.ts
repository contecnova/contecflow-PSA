// Tipos del catálogo de procesos BPM (estructura sin idioma + textos por idioma).

export type NodoEstructura = {
  id: string
  type: string
  col: number
  row?: number
  /** Nodo sin etiqueta (p. ej. pasarelas paralelas). */
  sinNombre?: boolean
}

/** [origen, destino, etiquetado]: las etiquetas viven en `flows` del idioma, en este orden. */
export type FlujoEstructura = [string, string, boolean?]

export type EstructuraProceso = {
  id: string
  category: string
  /** SLA expresable como número de días hábiles (se formatea con claves `bpm.sla_*`). */
  slaDiasHabiles?: number
  /** Número de pasos de la lista de pasos (los textos deben tener el mismo). */
  pasos: number
  nodos: NodoEstructura[]
  flujos: FlujoEstructura[]
}

export type TextoProceso = {
  name: string
  description: string
  owner: string
  /** Solo si el SLA no es un número de días hábiles. */
  sla?: string
  /** Nombre del proceso dentro del diagrama, si difiere de `name`. */
  diagrama?: string
  steps: string[]
  nodes: Record<string, string>
  flows: string[]
}

export type TextosCatalogo = Record<string, TextoProceso>

/** Proceso que es una cadena lineal de pasos (inicio, tareas, fin): sin SLA ni responsable. */
export type EstructuraLineal = {
  id: string
  category: string
  /** Número de pasos (los textos de cada idioma deben tener el mismo). */
  pasos: number
}

export type TextoLineal = {
  name: string
  description: string
  steps: string[]
}

export type TextosLineales = Record<string, TextoLineal>

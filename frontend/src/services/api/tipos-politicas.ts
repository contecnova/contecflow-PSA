/**
 * Tipos del motor de políticas, reglas y flujos (tarea #26).
 * Espejo de `app/services/politicas/*` y `app/services/approval_engine/diagrama.py`.
 */

export type TipoDeCampo = 'importe' | 'numero' | 'texto' | 'enum' | 'entidad' | 'fecha' | 'pais' | 'ciudad' | 'booleano'
export type Operador =
  | 'eq' | 'ne' | 'lt' | 'lte' | 'gt' | 'gte' | 'between' | 'in' | 'not_in' | 'contains' | 'not_contains'
  | 'empty' | 'not_empty' | 'pct_over' | 'weekday_in' | 'weekday_not_in'
export type ClaseDeEntidad = 'usuario' | 'proyecto' | 'cliente' | 'rol' | 'departamento' | 'equipo' | 'grupo'

export interface Importe { cantidad: number; moneda: string }
export type ValorDeCondicion = string | number | boolean | Importe | (string | number)[] | null

export interface CampoDeDominio {
  clave: string; etiqueta: string; tipo: TipoDeCampo; operadores: Operador[]
  opciones: { valor: string; etiqueta: string }[]; entidad: ClaseDeEntidad | null; ayuda: string | null; asignable: boolean
}
export interface DominioDePoliticas { clave: string; etiqueta: string; tipo_de_aprobacion: string | null; campos: CampoDeDominio[] }

export type TipoDeResultado =
  | 'allow' | 'auto_approve' | 'warn' | 'require_justification' | 'require_attachment'
  | 'add_approval_levels' | 'notify' | 'block' | 'set_field' | 'tag'
export type TipoDeAprobador = 'role' | 'user' | 'manager' | 'manager_level' | 'any_in_department' | 'group'
export type TipoDeDestinatario = 'persona' | 'rol' | 'responsable' | 'grupo' | 'departamento' | 'solicitante'
export type Canal = 'app' | 'email' | 'canal'

export interface CatalogoDePoliticas {
  dominios: DominioDePoliticas[]
  operadores_por_tipo: Record<TipoDeCampo, Operador[]>
  resultados: TipoDeResultado[]; tipos_de_aprobador: TipoDeAprobador[]; destinatarios: TipoDeDestinatario[]
  canales: Canal[]; entidades: ClaseDeEntidad[]; max_niveles: number
}

export interface ReferenciaDeValor { tipo: 'valor' | 'campo' | 'tabla'; valor?: ValorDeCondicion; campo?: string; tabla_id?: string }

export interface CondicionSimple {
  tipo: 'condicion'; campo: string; operador: Operador
  valor?: ValorDeCondicion; valor2?: ValorDeCondicion; referencia?: ReferenciaDeValor
}
export interface GrupoDeCondiciones { tipo: 'grupo'; op: 'and' | 'or'; negar?: boolean; hijos: NodoDeCondicion[] }
export type NodoDeCondicion = CondicionSimple | GrupoDeCondiciones

export interface PasoAnadido {
  nombre?: string; approver_type: TipoDeAprobador; approver_role?: string | null; approver_user_id?: string | null
  approver_department?: string | null; approver_group_id?: string | null; approver_level?: number | null
  required_approvals?: number
}
export interface Destinatario { tipo: TipoDeDestinatario; valor?: string | null }

export interface Resultado {
  tipo: TipoDeResultado; mensaje?: string | null
  tipos_de_documento?: string[]
  niveles?: number | null; pasos?: PasoAnadido[]
  destinatarios?: Destinatario[]; canales?: Canal[]
  campo?: string; valor?: ValorDeCondicion
  etiqueta?: string
}

export interface BandaDeExceso { desde: number; hasta: number | null; resultados: Resultado[] }
export interface Exceso { campo: string; referencia: ReferenciaDeValor; bandas: BandaDeExceso[] }

export interface Regla {
  id?: string; orden?: number; nombre: string; activa: boolean; detener: boolean
  condicion: GrupoDeCondiciones | null; resultados: Resultado[]; exceso: Exceso | null
}

export interface AmbitoDePolitica {
  departamentos: string[]; equipos: string[]; roles: string[]; ubicaciones: string[]; personas: string[]
}

export type EstadoDePolitica = 'borrador' | 'publicada' | 'retirada'

export interface DocumentoDePolitica {
  dominio: string; nombre: string; descripcion?: string | null; prioridad: number; activa: boolean
  vigente_desde?: string | null; vigente_hasta?: string | null; ambito: AmbitoDePolitica
  nota_de_version?: string | null; reglas: Regla[]
}

export interface Politica extends DocumentoDePolitica {
  id: string; familia_id: string; version: number; estado: EstadoDePolitica
  created_by?: string | null; publicada_por?: string | null; publicada_en?: string | null
  created_at?: string | null; updated_at?: string | null; n_reglas: number
  creada_por_nombre?: string | null; publicada_por_nombre?: string | null
}
export interface PoliticaEnLista extends Omit<Politica, 'reglas'> {
  version_publicada: number | null; id_publicada: string | null; n_versiones: number
}

export interface ErrorDeValidacion { ruta: string; mensaje: string }

export interface FilaDeTabla {
  id?: string; pais: string | null; ciudad: string | null; categoria: string | null; valor: number
  moneda: string | null; vigente_desde: string | null; vigente_hasta: string | null
}
export interface TablaDeReferencia {
  id: string; nombre: string; descripcion?: string | null; dominio?: string | null
  tipo_de_valor: 'importe' | 'numero'; moneda?: string | null; n_filas: number; updated_at?: string | null
  filas?: FilaDeTabla[]
}

export interface OpcionesDePoliticas {
  departamentos: string[]; equipos: string[]; roles: string[]; monedas: string[]; moneda_por_defecto: string
  grupos: { id: string; nombre: string }[]; tipos_de_documento: string[]; ciudades: string[]
  tablas: TablaDeReferencia[]
}

export interface Huella {
  decision: 'block' | 'review' | 'auto_approve' | 'allow'; niveles: number; pasos: number; avisos: number
  requisitos: string[]; bloqueos: string[]; etiquetas: string[]; avisar: number
}
export interface PasoDeTraza {
  campo: string; etiqueta: string; operador: Operador; esperado: ValorDeCondicion; esperado2?: ValorDeCondicion
  real: ValorDeCondicion; cumple: boolean | null; nota: string | null
  convertido?: Importe; detalle?: Record<string, unknown>
}
export interface ExplicacionDeRegla {
  regla_id: string; regla: string; cumple: boolean | null; traza: PasoDeTraza[]; resultados: Resultado[]
  exceso?: { exceso_pct?: number; valor?: number; referencia?: number; moneda?: string; banda?: { desde: number; hasta: number | null } | null; nota?: string }
}
export interface ExplicacionDePolitica {
  politica_id: string; politica: string; version: number; prioridad: number; aplica: boolean; motivo: string
  reglas: ExplicacionDeRegla[]
}
export interface ItemDeSimulacion {
  entidad_id: string; resumen: string; fecha: string | null; cambia: boolean; antes: Huella; despues: Huella
  explicacion: ExplicacionDePolitica[] | null
}
export interface Simulacion {
  dominio: string; evaluadas: number; tope: number; cambian: number
  resumen_de_cambios: Record<'decision' | 'mas_aprobacion' | 'menos_aprobacion' | 'nuevos_bloqueos' | 'nuevos_avisos' | 'auto_aprobadas', number>
  por_decision: { antes: Record<string, number>; despues: Record<string, number> }
  items: ItemDeSimulacion[]
}

export interface Explicaciones {
  dominio: string; entidad_id: string; resumen: string
  evaluaciones: { id: string; momento: string; decision: string; created_at: string | null
    explicacion: { politicas: ExplicacionDePolitica[] } }[]
}

// ── Diseñador gráfico de flujos de aprobación ────────────────────────────────
export type TipoDeNodoDeFlujo = 'start' | 'end' | 'approve' | 'inform' | 'condition' | 'split' | 'join'
export interface DatosDeNodoDeFlujo {
  nombre?: string; approver_type?: TipoDeAprobador; approver_role?: string | null; approver_user_id?: string | null
  approver_department?: string | null; approver_group_id?: string | null; approver_level?: number | null
  required_approvals?: number; timeout_hours?: number; on_timeout?: 'escalate' | 'auto_approve' | 'reject'
  escalate_to_user_id?: string | null; reminder_hours?: number | null; requires_attachment?: boolean
  arbol?: GrupoDeCondiciones; condicion_legado?: string | null
}
export interface NodoGuardado { id: string; type: TipoDeNodoDeFlujo; position: { x: number; y: number }; data: DatosDeNodoDeFlujo }
export interface AristaGuardada { id: string; source: string; target: string; sourceHandle?: 'si' | 'no' | null }
export interface DiagramaDeFlujo {
  workflow_id: string; entity_type: string; dominio: string | null; solicitudes_pendientes: number; generado: boolean
  nodos: NodoGuardado[]; aristas: AristaGuardada[]; pasos?: number
}
export interface ComprobacionDeDiagrama { valido: boolean; errores: { nodo: string | null; mensaje: string }[]; pasos: unknown[] }

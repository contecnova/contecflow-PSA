/**
 * services/api/mcp.ts — Agentes de código por MCP (23-11-2026, docs/integraciones/MCP.md).
 *
 * Configuración → Agentes de código (MCP): estado del servidor de la empresa,
 * herramientas disponibles para quien mira y sus credenciales propias (claves
 * de API de alcance `mcp:read` o `mcp:write`, que solo abren `POST /api/v1/mcp`).
 */
import api from './_core'

export type ModoDeEscritura = 'off' | 'approval' | 'direct'

export interface EstadoMcp {
  enabled: boolean
  write_mode: ModoDeEscritura
  notebook_enabled: boolean
  rate_limit_per_minute: number
  url: string
  protocol_versions: string[]
  server_name: string
  can_admin: boolean
}

export interface HerramientaMcp {
  name: string
  title: string
  description: string
  writes: boolean
  capability: string | null
  route: string
  notebook: boolean
  available: boolean
  reason: { code: string; params: Record<string, unknown> } | null
}

export interface CredencialMcp {
  id: string
  name: string
  key_prefix: string
  scopes: string[]
  is_active: boolean
  requests_today: number
  last_used_at: string | null
  expires_at: string | null
  created_at: string | null
}

export interface CredencialCreada { id: string; name: string; key: string; key_prefix: string; scopes: string[]; expires_at: string }

// El interceptor de `_core` ya desenvuelve el sobre: `r.data` es el contenido.
const D = <T,>(p: Promise<{ data: unknown }>) => p.then(r => r.data as T)

export const CLAVES_MCP = {
  estado: ['mcp', 'estado'] as const,
  herramientas: ['mcp', 'herramientas'] as const,
  credenciales: ['mcp', 'credenciales'] as const,
}

export const mcpApi = {
  estado: () => D<EstadoMcp>(api.get('/mcp/estado')),
  cambiarEstado: (c: Partial<Pick<EstadoMcp, 'enabled' | 'write_mode' | 'notebook_enabled' | 'rate_limit_per_minute'>>) =>
    D<EstadoMcp>(api.patch('/mcp/estado', c)),
  herramientas: () => D<HerramientaMcp[]>(api.get('/mcp/herramientas')),
  credenciales: () => D<CredencialMcp[]>(api.get('/mcp/credenciales')),
  crearCredencial: (c: { name: string; scope: 'read' | 'write'; expires_in_days: number }) =>
    D<CredencialCreada>(api.post('/mcp/credenciales', c)),
  revocarCredencial: (id: string) => D<unknown>(api.delete(`/mcp/credenciales/${id}`)),
}

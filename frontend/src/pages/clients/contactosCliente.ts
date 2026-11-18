// Piezas comunes de los contactos (personas) de un cliente: la ficha, la
// pestaña Contactos y la de usuarios del portal tocan los mismos datos.
import type { QueryClient } from '@tanstack/react-query'

type Traducir = (clave: string, params?: Record<string, unknown>) => string

/** Tras cualquier cambio en contactos o en usuarios del portal: la lista de
 *  contactos, la cabecera del cliente (reflejo del principal) y el listado. */
export function invalidarContactosDelCliente(qc: QueryClient, cid: string | number): void {
  const id = String(cid)
  qc.invalidateQueries({ queryKey: ['client-contacts', id] })
  qc.invalidateQueries({ queryKey: ['client-detail', id] })
  qc.invalidateQueries({ queryKey: ['client-detail-projects', cid] })
  qc.invalidateQueries({ queryKey: ['portal-clients-org', cid] })
  qc.invalidateQueries({ queryKey: ['clients'] })
}

export const ROLES_DE_CONTACTO = ['primary', 'billing', 'technical', 'executive', 'support', 'other'] as const

const CLAVE_DE_ROL: Record<string, string> = {
  primary: 'clientstabs.rol_principal',
  billing: 'clientstabs.rol_facturacion',
  technical: 'clientstabs.rol_tecnico',
  executive: 'clientstabs.rol_ejecutivo',
  support: 'clientstabs.rol_soporte',
  other: 'clientstabs.rol_otro',
}

export function rolesDeContacto(t: Traducir): { id: string; label: string }[] {
  return ROLES_DE_CONTACTO.map(id => ({ id, label: t(CLAVE_DE_ROL[id]) }))
}

/**
 * services/api/catalogos.ts — catálogos de clave editables por empresa (19-11-2026).
 *
 * Tipos de proyecto, sectores de cliente y categorías de gasto ya no son enums
 * cerrados del backend: viven en `custom_project_types`, `custom_client_industries`
 * y `custom_expense_categories` (app/services/settings_service/catalogos_de_clave.py).
 * Estados de proyecto y de tarea también son catálogos del backend (solo lectura aquí).
 * El interceptor de `_core` ya desenvuelve `{ data, meta }`.
 */
import api from './_core'

export type NombreDeCatalogo = 'project-types' | 'client-industries' | 'expense-categories' | 'project-statuses' | 'task-statuses'
  // Proveedores (19-11-2026, migración 189): tipos de servicio gestionado y unidades de cobro.
  | 'supplier-service-types' | 'supplier-billing-units'

export interface ValorDeCatalogo {
  id: string
  value: string
  label: string
  color: string
  sort_order: number
  is_active: boolean
  is_default?: boolean
  organization_id?: string | null
}

export type ValorDeCatalogoIn = Pick<ValorDeCatalogo, 'value' | 'label' | 'color' | 'sort_order'>

const lista = (r: { data: unknown }): ValorDeCatalogo[] => {
  const d = r.data as ValorDeCatalogo[] | { items?: ValorDeCatalogo[] }
  return Array.isArray(d) ? d : (d?.items ?? [])
}

// Ruta de cada catálogo. Cada valor de `NombreDeCatalogo` tiene sus cuatro
// rutas en el backend (`app/api/v1/endpoints/settings.py`, `_rutas_de_catalogo`
// y las de proyecto/tarea), comprobado 23-11-2026 contra `app.routes`. Se arma
// aquí porque tests/test_rutas_del_frontend.py sustituye `${c}` por `x` y daba
// cuatro falsos 404 (`/settings/x`); el tipo cerrado ya impide un nombre inventado.
const ruta = (c: NombreDeCatalogo, id?: string) => (id ? `/settings/${c}/${id}` : `/settings/${c}`)

export const catalogosApi = {
  listar: (c: NombreDeCatalogo) => api.get(ruta(c)).then(lista),
  crear: (c: NombreDeCatalogo, v: ValorDeCatalogoIn) => api.post(ruta(c), v).then(r => r.data as ValorDeCatalogo),
  guardar: (c: NombreDeCatalogo, id: string, v: ValorDeCatalogoIn) => api.patch(ruta(c, id), v).then(r => r.data as ValorDeCatalogo),
  borrar: (c: NombreDeCatalogo, id: string) => api.delete(ruta(c, id)).then(r => r.data),
}

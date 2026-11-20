/**
 * useCatalogo — una sola fuente para los catálogos de clave del backend (19-11-2026).
 *
 * Tipos de proyecto, sectores, categorías de gasto y estados de proyecto/tarea
 * se leían de listas escritas en cada página (TYPE_LABELS, PROJECT_TYPES de
 * constants.json, STATUSES por página…) y no coincidían entre sí ni con lo que
 * la empresa configura. Este hook los lee de `/settings/<catalogo>` y da la
 * etiqueta traducida: `<i18n>.<clave>` si el diccionario la tiene (los valores
 * del sistema), si no la etiqueta que guardó la empresa.
 */
import { useQuery } from '@tanstack/react-query'
import { catalogosApi, type NombreDeCatalogo, type ValorDeCatalogo } from '../services/api/catalogos'
import { useAppT } from '../i18n/AppLangContext'

/** Prefijo i18n de cada catálogo (claves ya existentes en i18n/langs/{es,en,zh}.mjs). */
export const CLAVE_I18N_DE_CATALOGO: Record<NombreDeCatalogo, string> = {
  'project-types': 'tipo_proyecto.',
  'client-industries': 'clientspage.sector_',
  'expense-categories': 'expenses.cat_',
  'project-statuses': 'estado.',
  'task-statuses': 'estado.',
  // 19-11-2026: catálogos de proveedores (claves del sistema en el módulo `proveedores`).
  'supplier-service-types': 'proveedores.tipo_servicio_',
  'supplier-billing-units': 'proveedores.unidad_',
}

export const claveDeConsultaDeCatalogo = (c: NombreDeCatalogo) => ['catalogo', c] as const

export function useCatalogo(catalogo: NombreDeCatalogo) {
  const t = useAppT()
  const { data = [], isLoading } = useQuery({
    queryKey: claveDeConsultaDeCatalogo(catalogo),
    queryFn: () => catalogosApi.listar(catalogo),
    staleTime: 5 * 60_000,
  })
  const prefijo = CLAVE_I18N_DE_CATALOGO[catalogo]
  const porClave = new Map<string, ValorDeCatalogo>(data.map(v => [v.value, v]))
  // Clave de i18n si es un valor del sistema; si no, la etiqueta que guardó la empresa; si no, la clave.
  const etiqueta = (clave: string | null | undefined) => {
    if (!clave) return ''
    const respaldo = porClave.get(clave)?.label || clave
    return /^[a-z0-9_]+$/.test(clave) ? (t as unknown as (k: string, r: string) => string)(`${prefijo}${clave}`, respaldo) : respaldo
  }
  const color = (clave: string | null | undefined) => (clave && porClave.get(clave)?.color) || 'var(--text-3)'
  const opciones = data.map(v => ({ value: v.value, label: etiqueta(v.value) }))
  return { valores: data, opciones, etiqueta, color, cargando: isLoading }
}

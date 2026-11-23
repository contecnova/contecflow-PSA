/**
 * Catálogos, tipos, ayudantes y piezas visuales compartidas del módulo ALM.
 * Troceado de ALMPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import { useEffect, useState, type ReactNode } from 'react'
import type { AxiosResponse } from 'axios'
import type { ZodType } from 'zod'
import type { AlmActivo, AlmCentroDeCoste, AlmContrato, AlmLicencia, AlmProveedor } from '../../services/api/tipos-alm'
import type { MetaDeLista } from '../../services/api/tipos-plataforma'
import { KpiCard, Pulsable } from '../../components/ui'
import { ICONO_ACTIVO, ICONO_CONTRATO, ICONO_LICENCIA, ICONO_PROVEEDOR } from '../../components/alm/almFases'
import { useAppT } from '../../i18n/AppLangContext'
import { tonoDe, type Umbrales } from '../../utils/umbrales'
import DsBadge from '../../components/ui/StatusBadge'
import { SEARCH_DEBOUNCE_MS } from '../../constants/timings'
import { SMALL_PAGE_SIZE } from '../../constants/pagination'

// ── Constantes ────────────────────────────────────────────────────────────────
// Las etiquetas de cada catálogo se traducen con la clave `alm.<prefijo>_<clave>`
// (p. ej. `alm.vendor_cat_software`); aquí solo quedan icono y color.
type CatalogoIcono = { icon: ReactNode }

type CatalogoColor = { color: string }

export const VENDOR_CATS: Record<string, CatalogoIcono & CatalogoColor> = {
  software:   { icon: ICONO_PROVEEDOR.software, color: 'var(--accent)' },
  hardware:   { icon: ICONO_PROVEEDOR.hardware, color: 'var(--purple)' },
  saas:       { icon: ICONO_PROVEEDOR.saas, color: 'var(--success)' },
  cloud:      { icon: ICONO_PROVEEDOR.cloud, color: 'var(--accent)' },
  telecom:    { icon: ICONO_PROVEEDOR.telecom, color: 'var(--warning)' },
  consulting: { icon: ICONO_PROVEEDOR.consulting, color: 'var(--purple)' },
  other:      { icon: ICONO_PROVEEDOR.other, color: 'var(--text-2)' },
}

export const CONTRACT_TYPES: Record<string, CatalogoIcono> = Object.fromEntries(
  Object.entries(ICONO_CONTRATO).map(([k, icon]) => [k, { icon }]))

export const CONTRACT_STATUS: Record<string, CatalogoColor> = {
  active:    { color: 'var(--success)' },
  expired:   { color: 'var(--danger)' },
  cancelled: { color: 'var(--text-2)' },
  pending:   { color: 'var(--warning)' },
  draft:     { color: 'var(--text-3)' },
}

export const LICENSE_TYPES: Record<string, CatalogoIcono> = Object.fromEntries(
  Object.entries(ICONO_LICENCIA).map(([k, icon]) => [k, { icon }]))

export const LICENSE_STATUS_CFG: Record<string, CatalogoColor> = {
  active:        { color: 'var(--success)' },
  expired:       { color: 'var(--danger)' },
  unassigned:    { color: 'var(--text-2)' },
  overallocated: { color: 'var(--danger)' },
  cancelled:     { color: 'var(--text-3)' },
}

export const ASSET_TYPES: Record<string, CatalogoIcono> = Object.fromEntries(
  Object.entries(ICONO_ACTIVO).map(([k, icon]) => [k, { icon }]))

export const ASSET_STATUS_CFG: Record<string, CatalogoColor> = {
  ordered:   { color: 'var(--purple)' },
  available: { color: 'var(--success)' },
  in_use:    { color: 'var(--accent)' },
  on_loan:   { color: 'var(--orange)' },
  in_repair: { color: 'var(--warning)' },
  retired:   { color: 'var(--text-2)' },
  disposed:  { color: 'var(--text-3)' },
  lost:      { color: 'var(--danger)' },
  stolen:    { color: 'var(--danger)' },
}

/** Entorno de una licencia → clave de su etiqueta ('all' no se enseña). */
export const ENTORNO_KEY: Record<string, string> = {
  prod: 'alm.licenses_env_production', staging: 'alm.licenses_env_staging', dev: 'alm.licenses_env_dev',
}

/** Filas por página en proveedores, licencias y activos (#22: el backend pagina con page/page_size). */
export const ALM_PAGE_SIZE = SMALL_PAGE_SIZE

// ── Entidades (lo que devuelven los endpoints /alm/*: services/api/tipos-alm) ─
export type Vendor = AlmProveedor

export type AlmContract = AlmContrato

export type License = AlmLicencia

export type Asset = AlmActivo

export type CostCenter = AlmCentroDeCoste

export type CostCenterForm = { code: string; name: string; description: string; budget_annual: string | number; currency: string }

export type CmdbItem = { id: string; code?: string; name: string }

/** Cambio de un campo de texto, select, textarea o DateInput. */
export type CambioDeCampo = { target: { value: string } }

/** Lo que `useFormValidation(esquema)` entrega como datos válidos. */
export type DatosValidos<S> = S extends ZodType<infer T> ? T : never

export type Traductor = ReturnType<typeof useAppT>

// ── Piezas compartidas (estilos en ALMPage.css) ───────────────────────────────
/** Clase de un campo de formulario: rojo si la validación lo marcó. */
export const claseCampo = (error?: string) => (error ? 'alm-input is-invalid' : 'alm-input')

/** Etiqueta traducida de un catálogo; un valor que el catálogo no conoce se enseña tal cual. */
export const etiquetaDe = (t: Traductor, prefijo: string, catalogo: Record<string, unknown>, clave: string) =>
  (clave in catalogo ? t(`alm.${prefijo}_${clave}`) : clave)

/** Tono (clase .alm-tone--*) según días que faltan: rojo, ámbar o el de por defecto. */
/** 19-11-2026: días que faltan con UMBRAL_VENCIMIENTO_* de la empresa (antes 14/30 y 7/30 aquí). */
export const tonoPorDias = (dias: number, umbrales: Umbrales, resto: 'success' | 'muted') => {
  const tono = tonoDe('vencimiento', dias, umbrales)
  return `alm-tone--${tono === 'success' || !tono ? resto : tono}`
}

/** Respuesta paginada de /alm/*: los elementos y el total (meta.total o X-Total-Count). */
export type PaginaAlm<T> = { items: T[]; total: number }

export function aPagina<T>(r: AxiosResponse<T[]>): PaginaAlm<T> {
  const meta = (r as AxiosResponse<T[]> & { meta?: MetaDeLista }).meta
  const total = meta?.total ?? Number(r.headers?.['x-total-count'] ?? r.data.length)
  return { items: r.data, total }
}

/** El valor tras `ms` sin cambios: la búsqueda va al servidor sin una petición por tecla. */
export function useRetardado<T>(valor: T, ms = SEARCH_DEBOUNCE_MS): T {
  const [v, setV] = useState(valor)
  useEffect(() => {
    const id = setTimeout(() => setV(valor), ms)
    return () => clearTimeout(id)
  }, [valor, ms])
  return v
}

/** Si un borrado deja la página actual fuera del total, vuelve a la última que existe. */
export function useAjustarPagina(page: number, totalPages: number, setPage: (p: number) => void, listo: boolean) {
  useEffect(() => { if (listo && page > totalPages) setPage(totalPages) }, [listo, page, totalPages, setPage])
}

export const StatusBadge = ({ status, cfg, prefijo }: { status: string; cfg: Record<string, CatalogoColor>; prefijo: string }) => {
  const t = useAppT()
  return (
    <DsBadge color={cfg[status]?.color ?? 'var(--text-2)'} caps={false}>{etiquetaDe(t, prefijo, cfg, status)}</DsBadge>
  )
}

/** KPI del kit; si lleva `onClick`, la tarjeta entera abre la pestaña que resume. */
export const KPI = ({ icon, label, value, sub, alert, danger, onClick }: { icon: ReactNode; label: ReactNode; value: ReactNode; sub?: ReactNode; alert?: boolean; danger?: boolean; onClick?: () => void }) => {
  const tarjeta = <KpiCard icon={icon} label={label} value={value} sub={sub} warning={!!alert && !danger} danger={!!alert && !!danger} />
  return onClick
    ? <Pulsable type="button" onClick={onClick} className="alm-kpi-link">{tarjeta}</Pulsable>
    : tarjeta
}

export const SectionTitle = ({ children, action }: { children: ReactNode; action?: ReactNode }) => (
  <div className="u-row-between-mb16">
    <h3 className="alm-section-title">{children}</h3>
    {action}
  </div>
)

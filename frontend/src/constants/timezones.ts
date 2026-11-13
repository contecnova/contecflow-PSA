/**
 * Zonas horarias que ofrecen los selectores: una sola fuente (barrido 2026-11).
 *
 * Antes había tres listas fijas y distintas (usuarios y sedes en
 * SettingsPageSections, calendarios de SLA). Ahora se usa la lista IANA completa
 * del navegador (`Intl.supportedValuesOf('timeZone')`) y, si el navegador no la
 * da, esta lista de respaldo. La zona por defecto de la empresa sale de
 * `useOrgSettings().timezone` (ajuste `DEFAULT_TIMEZONE` del backend), nunca de aquí.
 */

/** Respaldo para navegadores sin `Intl.supportedValuesOf` (unión de las listas antiguas). */
export const FALLBACK_TIMEZONES: readonly string[] = [
  'UTC',
  'Europe/Madrid', 'Europe/London', 'Europe/Paris', 'Europe/Berlin', 'Europe/Rome',
  'Europe/Warsaw', 'Europe/Amsterdam', 'Europe/Brussels', 'Europe/Lisbon',
  'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles',
  'America/Sao_Paulo', 'America/Buenos_Aires', 'America/Mexico_City',
  'Asia/Tokyo', 'Asia/Shanghai', 'Asia/Singapore', 'Asia/Kolkata', 'Asia/Dubai',
  'Australia/Sydney', 'Pacific/Auckland',
]

let cache: string[] | null = null

/** Todas las zonas que se pueden elegir, con UTC primero. */
export function allTimezones(): string[] {
  if (cache) return cache
  let lista: string[] = []
  try {
    const intl = Intl as unknown as { supportedValuesOf?: (k: string) => string[] }
    lista = intl.supportedValuesOf ? intl.supportedValuesOf('timeZone') : []
  } catch {
    lista = []
  }
  if (!lista.length) lista = [...FALLBACK_TIMEZONES]
  cache = ['UTC', ...lista.filter(z => z !== 'UTC')]
  return cache
}

/** Las zonas para un selector, incluyendo siempre los valores ya guardados aunque no estén en la lista. */
export function timezoneOptions(...actuales: (string | null | undefined)[]): string[] {
  const base = allTimezones()
  const extra = actuales.filter((z): z is string => !!z && !base.includes(z))
  return extra.length ? [...extra, ...base] : base
}

/** La zona del navegador (respaldo mientras no responde el servidor). */
export function browserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  } catch {
    return 'UTC'
  }
}

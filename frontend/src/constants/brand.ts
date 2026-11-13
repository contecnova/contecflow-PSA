/**
 * Nombre del producto en la interfaz (barrido 2026-11): un solo sitio.
 *
 * Es el respaldo. Con sesión, la cabecera usa el nombre de la marca de la empresa
 * (`OrgBranding.app_name`, que sin marca propia devuelve el `PROJECT_NAME` del
 * backend) a través de `useAppName()`. Los prefijos de `console.*` y los nombres
 * de componentes no lo usan: son identificadores técnicos.
 */
export const PRODUCT_NAME = 'Contecflow'

/** Nombre completo, para los textos que nombran la plataforma entera. */
export const PRODUCT_FULL_NAME = `${PRODUCT_NAME} PSA`

// Fallback genérico para extractErr cuando el componente no tiene acceso a t().
// En componentes con acceso a t() preferir t('errors.generic').
// Audit #96.
export const GENERIC_ERROR_FALLBACK: string = 'Error inesperado'

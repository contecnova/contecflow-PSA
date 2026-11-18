// Fallback genérico para extractErr cuando el componente no tiene acceso a t().
// En componentes con acceso a t() preferir t('errors.generic').
// Audit #96.
// 18-11-2026: es solo la señal «usa el genérico»: extractErr lo cambia por `errors.generic` en el idioma
// del operador. No pintarlo directamente.
export const GENERIC_ERROR_FALLBACK: string = 'Error inesperado'

// Modulo virtual del plugin `i18n-respaldo-en` (vite.config.js): entradas
// inglesas de las claves que el castellano no tiene traducidas. Fichero sin
// import/export a proposito: asi la declaracion es global y no una ampliacion.
declare module 'virtual:i18n-respaldo-en' {
  const respaldo: Record<string, Record<string, unknown>>
  export default respaldo
}

/**
 * Redondeo a 2 decimales para vistas previas de importes (18-11-2026).
 * El backend usa `round(x, 2)` de Python sobre floats; `toFixed(2)` parte del mismo valor binario
 * exacto, así que coincide salvo en empates exactos (x.xx5 representable), donde Python va al par
 * y JS hacia arriba. Los importes definitivos (impuesto, total) siempre los fija el servidor.
 */
export const redondear2 = (x: number): number => Number(x.toFixed(2))

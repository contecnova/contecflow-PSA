/**
 * Pestaña «Mi cuaderno» de la bandeja de entrada y bloque de «Mi día»: casillas
 * pendientes y etiquetas de todos los cuadernos (carga su hoja de estilos).
 */
import TodasMisTareas from './TodasMisTareas'
import './cuaderno.css'

export default function BandejaDelCuaderno({ compacto = false, limite }: { compacto?: boolean; limite?: number }) {
  return <TodasMisTareas compacto={compacto} limite={limite} />
}

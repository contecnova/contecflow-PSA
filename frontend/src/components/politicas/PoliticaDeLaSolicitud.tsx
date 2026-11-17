/**
 * Lo que dijeron las políticas de una solicitud de aprobación (rev. 166, tarea
 * #27), para la bandeja de quien aprueba: indicador de exceso y niveles, si el
 * paso actual lo añadió una política y, bajo demanda, el «por qué» completo.
 */
import { useState } from 'react'
import type { ResumenDePolitica } from '../../services/api/tipos-politicas'
import IndicadorDePolitica from './IndicadorDePolitica'
import ExplicacionDeEntidad from './ExplicacionDeEntidad'
import { useTextos } from './comun'
import { Pulsable } from '../ui'

export default function PoliticaDeLaSolicitud({ resumen, entidadId, origenDelPaso }: {
  resumen: ResumenDePolitica | null | undefined; entidadId: string; origenDelPaso?: string | null
}) {
  const { t } = useTextos()
  const [abierta, setAbierta] = useState(false)
  if (!resumen) return null
  return (
    <div className="pol-fila pol-mt-xs">
      <IndicadorDePolitica resumen={resumen} />
      {origenDelPaso && <span className="pol-ayuda">{t('pol.paso_por_politica', { origen: origenDelPaso })}</span>}
      {resumen.dominio && (
        <Pulsable className="pol-boton-texto" aria-expanded={abierta} onClick={() => setAbierta(v => !v)}>
          {abierta ? t('pol.ocultar_por_que') : t('pol.ver_por_que')}
        </Pulsable>
      )}
      {abierta && resumen.dominio && <div className="pol-ancho"><ExplicacionDeEntidad dominio={resumen.dominio} entidadId={entidadId} /></div>}
    </div>
  )
}

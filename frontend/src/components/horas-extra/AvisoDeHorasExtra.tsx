/**
 * Aviso discreto en Imputar (18-11-2026): con fecha y horas, GET
 * /overtime/check (solo si las horas extra están activas). Si la imputación
 * deja horas fuera de horario sin autorizar, avisa de lo que pasará según el
 * control de la empresa (bloquear, avisar o regularizar) y enlaza a /overtime.
 */
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { horasExtraApi } from '../../services/api/horas-extra'
import { Aviso, horas, useConfigHe, useRetrasado, useTh } from './comun'

export default function AvisoDeHorasExtra({ fecha, horas: h, imputacionId }: { fecha: string; horas: number; imputacionId?: string }) {
  const { th } = useTh()
  const activo = Boolean(useConfigHe(Boolean(fecha) && h > 0).data?.activo)
  const consulta = useRetrasado({ fecha, h }, 400)
  const q = useQuery({
    queryKey: ['horas-extra', 'comprobar', consulta, imputacionId],
    queryFn: () => horasExtraApi.comprobar(consulta.fecha, consulta.h, imputacionId),
    enabled: activo && Boolean(consulta.fecha) && consulta.h > 0,
    retry: false,
  })
  const c = q.data
  if (!activo || !c || !c.activo || c.accion === 'nada' || !fecha || h <= 0) return null
  return (
    <Aviso tono={c.accion === 'bloquear' ? 'bloqueo' : 'aviso'}>
      <span>
        {th(`imputar_${c.accion}`, { n: horas(c.sin_autorizar) })}{' '}
        <Link className="hext-enlace" to="/overtime">{th('imputar_ir')}</Link>
      </span>
    </Aviso>
  )
}

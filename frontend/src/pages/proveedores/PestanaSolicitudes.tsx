/**
 * Portal del proveedor: sus solicitudes del flujo de demanda (migración 195,
 * docs/FLUJO_DE_DEMANDA.md). El proveedor pide (alta, acceso, compra… lo que la
 * empresa ofrezca en el canal `supplier_portal`) y sigue cada expediente: fases,
 * información pedida, comentarios y adjuntos. La API fuerza su canal
 * (`/demand/mine`, un externo siempre pide como `supplier_portal`).
 */
import { useState } from 'react'
import { Plus } from 'lucide-react'
import { Button } from '../../components/ui'
import DetalleDemanda from '../../components/demanda/DetalleDemanda'
import { ListaDeDemandas, NuevaSolicitud } from '../DemandaPage'
import { useAppT } from '../../i18n/AppLangContext'
import '../../components/demanda/demanda.css'

export default function PestanaSolicitudes() {
  const t = useAppT()
  const [abierta, setAbierta] = useState('')
  const [nueva, setNueva] = useState(false)
  if (abierta) return <DetalleDemanda id={abierta} onVolver={() => setAbierta('')} />
  return (
    <div className="u-stack-16">
      <div className="dem-fila">
        <Button icon={<Plus size={13} />} onClick={() => setNueva(true)}>{t('demanda.nueva_solicitud')}</Button>
      </div>
      <ListaDeDemandas mias onAbrir={setAbierta} />
      {nueva && <NuevaSolicitud mia onClose={() => setNueva(false)} onCreada={id => { setNueva(false); setAbierta(id) }} />}
    </div>
  )
}

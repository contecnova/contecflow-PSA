/**
 * Sección PIR de la ficha de un cambio o de un proyecto (migración 206, docs/PIR.md):
 * sus revisiones con filtros, «Programar PIR» (con `pir.gestionar`; las obligatorias se
 * programan solas al implantar o cerrar el cambio, y en la puesta en marcha o el cierre
 * del proyecto) y la ficha guiada de cada una.
 */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { CalendarPlus } from 'lucide-react'
import { Button } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { CLAVES_PIR, pirApi } from '../../services/api/pir'
import type { OrigenPir } from '../../services/api/pir'
import ListaDePir from './ListaDePir'
import FichaDePir from './FichaDePir'
import './Pir.css'

export default function SeccionPir({ origen, origenId, compacta }: { origen: OrigenPir; origenId: string; compacta?: boolean }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { puede } = useAuth()
  const [abierta, setAbierta] = useState<string | null>(null)
  const programar = useMutation({
    mutationFn: () => pirApi.programar({ origen_tipo: origen, origen_id: origenId }),
    onSuccess: p => { void qc.invalidateQueries({ queryKey: CLAVES_PIR.todo }); toast.success(t('pir.programada', { codigo: p.codigo })); setAbierta(p.id) },
    onError: e => toast.error(extractErr(e)),
  })
  if (!puede('pir.ver')) return null
  return (
    <section className="pir-bloque" aria-label={t('pir.seccion')}>
      <div className="u-row-center-8">
        <h3 className="pir-bloque__titulo">{t('pir.seccion')}</h3>
        {puede('pir.gestionar') && (
          <Button size="sm" variant="secondary" icon={<CalendarPlus size={14} />} loading={programar.isPending}
            onClick={() => programar.mutate()}>{t('pir.programar')}</Button>
        )}
      </div>
      {!compacta && <p className="pir-apagado">{t(origen === 'change' ? 'pir.ayuda_cambio' : 'pir.ayuda_proyecto')}</p>}
      <ListaDePir origenTipo={origen} origenId={origenId} onAbrir={setAbierta} />
      {abierta && <FichaDePir id={abierta} onClose={() => setAbierta(null)} />}
    </section>
  )
}

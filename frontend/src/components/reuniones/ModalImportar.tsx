/**
 * Traer una reunión concreta de Teams, Zoom o Meet (19-11-2026) por su
 * dirección o identificador, cuando ya terminó y la plataforma tiene su
 * transcripción. La recogida automática se activa en «Mis preferencias».
 */
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '../../context/AuthContext'
import { Download } from 'lucide-react'
import { Button, Input, Modal, Segmentado } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { reunionesApi } from '../../services/api/reuniones'
import type { PlataformaImportable } from '../../services/api/reuniones'
import { CLAVES } from './comun'
import './Reuniones.css'

interface Props {
  onClose: () => void
  onCreada?: (id: string) => void
  /** Plataformas activadas en la empresa (las demás salen deshabilitadas). */
  disponibles?: Partial<Record<PlataformaImportable, boolean>>
}

export default function ModalImportar({ onClose, onCreada, disponibles }: Props) {
  const t = useAppT()
  const toast = useToast()
  const configura = useAuth().puede('reuniones.config')
  const qc = useQueryClient()
  const [plataforma, setPlataforma] = useState<PlataformaImportable>('teams')
  const [referencia, setReferencia] = useState('')

  const importar = useMutation({
    mutationFn: () => reunionesApi.importar(plataforma, referencia.trim()),
    onSuccess: r => {
      qc.invalidateQueries({ queryKey: CLAVES.lista })
      toast.success(t('reuniones.importar.hecho'))
      onCreada?.(r.id)
      onClose()
    },
    onError: e => toast.error(extractErr(e, t('reuniones.importar.error'))),
  })

  const opciones: Array<{ valor: PlataformaImportable; etiqueta: string }> = [
    { valor: 'teams', etiqueta: t('reuniones.plataforma.teams') },
    { valor: 'zoom', etiqueta: t('reuniones.plataforma.zoom') },
    { valor: 'meet', etiqueta: t('reuniones.plataforma.meet') },
  ]

  return (
    <Modal open title={t('reuniones.importar.titulo')} subtitle={t('reuniones.importar.subtitulo')} onClose={onClose}>
      <div className="reu-form reu-form--una">
        <Segmentado aria-label={t('reuniones.campo.plataforma')} valor={plataforma} onChange={v => setPlataforma(v as PlataformaImportable)}
          opciones={opciones.map(o => ({ ...o, disabled: disponibles ? disponibles[o.valor] === false : false }))} />
        {disponibles && Object.values(disponibles).some(v => v === false) && (
          <p className="u-text3-xs" role="status">
            {t('reuniones.importar.sin_conector')}{' '}
            {configura && <Link to="/settings/reuniones" onClick={onClose}>{t('reuniones.ir_a_configuracion')}</Link>}
          </p>
        )}
        <Input label={t('reuniones.importar.referencia')} required value={referencia} onChange={e => setReferencia(e.target.value)}
          hint={t(`reuniones.importar.ayuda_${plataforma}`)} />
        <div className="reu-botonera">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button icon={<Download size={14} />} loading={importar.isPending} disabled={!referencia.trim()} onClick={() => importar.mutate()}>
            {t('reuniones.importar.traer')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

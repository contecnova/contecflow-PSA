/**
 * Invitar el bot a una reunión (19-11-2026): Teams, Zoom, Meet o Webex por su
 * dirección. El bot entra como participante, avisa en el chat de que graba
 * (texto de Configuración) y, al terminar, la transcripción llega sola.
 * Solo si la empresa lo activó con su contrato de encargo de tratamiento.
 */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Bot } from 'lucide-react'
import { Button, FormField, Input, Modal, ProjectSelect } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { reunionesApi } from '../../services/api/reuniones'
import { CLAVES } from './comun'
import './Reuniones.css'

interface Props { onClose: () => void; onCreada?: (id: string) => void }

export default function ModalInvitarBot({ onClose, onCreada }: Props) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [url, setUrl] = useState('')
  const [titulo, setTitulo] = useState('')
  const [cuando, setCuando] = useState('')
  const [proyecto, setProyecto] = useState('')

  const invitar = useMutation({
    mutationFn: () => reunionesApi.invitarBot({
      meeting_url: url.trim(),
      title: titulo.trim() || undefined,
      join_at: cuando ? new Date(cuando).toISOString() : null,
      project_id: proyecto || null,
    }),
    onSuccess: r => {
      qc.invalidateQueries({ queryKey: CLAVES.lista })
      toast.success(t('reuniones.bot.invitado'))
      onCreada?.(r.id)
      onClose()
    },
    onError: e => toast.error(extractErr(e, t('reuniones.bot.error'))),
  })

  return (
    <Modal open title={t('reuniones.bot.titulo')} subtitle={t('reuniones.bot.subtitulo')} onClose={onClose}>
      <div className="reu-form reu-form--una">
        <Input label={t('reuniones.bot.url')} required value={url} onChange={e => setUrl(e.target.value)}
          placeholder="https://" hint={t('reuniones.bot.url_ayuda')} />
        <Input label={t('reuniones.campo.titulo')} value={titulo} onChange={e => setTitulo(e.target.value)} />
        <Input label={t('reuniones.bot.cuando')} type="datetime-local" value={cuando} onChange={e => setCuando(e.target.value)}
          hint={t('reuniones.bot.cuando_ayuda')} />
        <FormField label={t('reuniones.campo.proyecto')}>
          <ProjectSelect value={proyecto} onChange={id => setProyecto(id)} />
        </FormField>
        <p className="u-text3-xs">{t('reuniones.bot.aviso_legal')}</p>
        <div className="reu-botonera">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button icon={<Bot size={14} />} loading={invitar.isPending} disabled={!url.trim()} onClick={() => invitar.mutate()}>
            {t('reuniones.bot.invitar')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

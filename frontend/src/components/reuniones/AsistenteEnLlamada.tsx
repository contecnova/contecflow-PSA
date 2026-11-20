/**
 * Asistente de reuniones dentro de una llamada del chat interno (19-11-2026,
 * cuarta vía, origen `chat_call`).
 *
 * - `useAsistenteEnLlamada`: estado (`GET /meeting-assistant/calls/{id}`,
 *   cada 5 s), activar (con el aviso confirmado), parar y consentimiento
 *   propio.
 * - `ModalActivarAsistente`: texto del aviso de la empresa y casilla
 *   obligatoria «He avisado a los asistentes de que se graba».
 * - `BannerDelAsistente`: «El asistente graba y transcribe esta reunión»,
 *   Consiento / No consiento cuando se exige y falta la respuesta, y «Parar
 *   asistente» para quien puede.
 *
 * El audio lo sube cada navegador por el camino de los subtítulos
 * (`transcribe-chunk`): el hablante es quien sube. Eso lo hace CallPage.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AudioLines, Square } from 'lucide-react'
import { Button, Checkbox, Modal } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { reunionesApi } from '../../services/api/reuniones'
import type { AsistenteDeLlamada } from '../../services/api/reuniones'
import { REFRESCO_EN_CURSO_MS } from './comun'
import './Reuniones.css'

const clave = (callId: string) => ['reuniones-llamada', callId] as const

export function useAsistenteEnLlamada(callId: string | undefined) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const id = callId ?? ''
  const { data: estado } = useQuery({
    queryKey: clave(id),
    queryFn: () => reunionesApi.llamada(id),
    enabled: !!callId,
    refetchInterval: REFRESCO_EN_CURSO_MS,
    retry: false,
  })
  const poner = (e: AsistenteDeLlamada) => qc.setQueryData(clave(id), e)
  const activar = useMutation({
    mutationFn: () => reunionesApi.activarEnLlamada(id),
    onSuccess: e => { poner(e); toast.success(t('reuniones.llamada.activado')) },
    onError: e => toast.error(extractErr(e)),
  })
  const parar = useMutation({
    mutationFn: () => reunionesApi.pararEnLlamada(id),
    onSuccess: e => { poner(e); toast.success(t('reuniones.llamada.parado')) },
    onError: e => toast.error(extractErr(e)),
  })
  const consentir = useMutation({
    mutationFn: (si: boolean) => {
      if (!estado?.meeting_id) return Promise.reject(new Error(t('reuniones.llamada.sin_reunion')))
      return reunionesApi.consentir(estado.meeting_id, { consents: si, method: 'self' })
    },
    onSuccess: (_r, si) => {
      if (estado) poner({ ...estado, my_consent: si })
      qc.invalidateQueries({ queryKey: clave(id) })
      toast.success(t('reuniones.consentimiento.anotado'))
    },
    onError: e => toast.error(extractErr(e)),
  })
  return { estado, activar, parar, consentir }
}

export function ModalActivarAsistente({ textoAviso, cargando, onActivar, onClose }: {
  textoAviso?: string | null
  cargando?: boolean
  onActivar: () => void
  onClose: () => void
}) {
  const t = useAppT()
  const [avisado, setAvisado] = useState(false)
  return (
    <Modal open title={t('reuniones.llamada.activar_titulo')} subtitle={t('reuniones.llamada.activar_subtitulo')} onClose={onClose}>
      <div className="reu-form reu-form--una">
        <div className="reu-aviso reu-aviso--warning" role="note">
          <p className="reu-aviso__texto">{textoAviso || t('reuniones.grabador.aviso_texto')}</p>
          <Checkbox checked={avisado} onChange={setAvisado} label={t('reuniones.grabador.he_avisado')} />
        </div>
        <p className="u-text3-xs">{t('reuniones.llamada.como_funciona')}</p>
        <div className="reu-botonera">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button icon={<AudioLines size={14} />} disabled={!avisado} loading={cargando} onClick={onActivar}>
            {t('reuniones.llamada.activar')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export function BannerDelAsistente({ estado, onConsentir, onParar, consintiendo, parando }: {
  estado: AsistenteDeLlamada
  onConsentir: (si: boolean) => void
  onParar: () => void
  consintiendo?: boolean
  parando?: boolean
}) {
  const t = useAppT()
  const pideConsentimiento = estado.require_consent && estado.my_consent === null
  return (
    <div className="reu-banner-llamada" role="status" data-testid="banner-asistente">
      <AudioLines size={16} aria-hidden />
      <span className="reu-banner-llamada__texto">{t('reuniones.llamada.banner')}</span>
      {estado.my_consent === false && <span className="u-text3-xs">{t('reuniones.llamada.sin_tu_audio')}</span>}
      {pideConsentimiento && (
        <span className="reu-banner-llamada__botones">
          <span>{t('reuniones.llamada.pide_consentimiento')}</span>
          <Button size="xs" disabled={consintiendo} onClick={() => onConsentir(true)}>{t('reuniones.llamada.consiento')}</Button>
          <Button size="xs" variant="secondary" disabled={consintiendo} onClick={() => onConsentir(false)}>{t('reuniones.llamada.no_consiento')}</Button>
        </span>
      )}
      {estado.can_stop !== false && (
        <Button size="xs" variant="danger" icon={<Square size={12} />} loading={parando} onClick={onParar}>
          {t('reuniones.llamada.parar')}
        </Button>
      )}
    </div>
  )
}

/**
 * Memoria de conversación de «Pregunta a los datos» (23-11-2026).
 *
 * Las preguntas se encadenan en una conversación para que las de seguimiento
 * («¿y en octubre?») se entiendan: el servidor da al modelo las últimas
 * `ASK_DATA_CONTEXT_TURNS` preguntas con su consulta. Aquí: lo preguntado en la
 * conversación actual, empezar otra, retomar una anterior y borrar (una o
 * todas). Cada persona ve y borra solo las suyas; los borrados se auditan.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { MessageSquarePlus, Trash2 } from 'lucide-react'
import { analyticsApi } from '../../services/api'
import { Button, Select } from '../ui'
import { useAppLang } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'

export default function ConversacionDeAsk({ conversacion, preguntas, conContexto, onNueva, onRetomar }: {
  conversacion: string | null
  preguntas: string[]
  conContexto: boolean
  onNueva: () => void
  onRetomar: (id: string, preguntas: string[]) => void
}) {
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const lista = useQuery({ queryKey: ['ask-conversaciones', conversacion, preguntas.length], queryFn: () => analyticsApi.askConversations().then(r => r.data.items) })
  const refrescar = () => qc.invalidateQueries({ queryKey: ['ask-conversaciones'] })
  const fallo = (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  const borrar = useMutation({
    mutationFn: (id: string | null) => id ? analyticsApi.deleteAskConversation(id) : analyticsApi.deleteAskConversations(),
    onSuccess: (_r, id) => { refrescar(); if (!id || id === conversacion) onNueva(); toast.success(t('ask_memoria.borrada')) },
    onError: fallo,
  })
  const retomar = useMutation({
    mutationFn: (id: string) => analyticsApi.askConversation(id).then(r => r.data),
    onSuccess: d => onRetomar(d.id, d.turns.map(x => x.question)),
    onError: fallo,
  })
  const otras = (lista.data ?? []).filter(c => c.id !== conversacion)
  return (
    <div className="u-stack-8" aria-live="polite">
      {preguntas.length > 0 && (
        <div className="u-text3-xs">
          {t('ask_memoria.en_esta_conversacion', { n: preguntas.length })}
          {conContexto && ` · ${t('ask_memoria.con_contexto')}`}
          <ol className="u-text2-xs">{preguntas.slice(-5).map((p, i) => <li key={`${i}-${p}`}>{p}</li>)}</ol>
        </div>
      )}
      <div className="u-wrap-center-8">
        {conversacion && <Button size="sm" variant="ghost" icon={<MessageSquarePlus size={13} />} onClick={onNueva}>{t('ask_memoria.nueva')}</Button>}
        {conversacion && (
          <Button size="sm" variant="ghost" icon={<Trash2 size={13} />} loading={borrar.isPending}
            onClick={() => openConfirmGlobal({ message: t('ask_memoria.confirmar_borrar'), onConfirm: () => borrar.mutate(conversacion) })}>
            {t('ask_memoria.borrar')}
          </Button>
        )}
        {otras.length > 0 && (
          <Select suelto placeholder={false} aria-label={t('ask_memoria.retomar')} value="" onChange={e => e.target.value && retomar.mutate(e.target.value)}>
            <option value="">{t('ask_memoria.retomar')}</option>
            {otras.map(c => <option key={c.id} value={c.id}>{c.title || '—'} ({c.turns})</option>)}
          </Select>
        )}
        {(lista.data ?? []).length > 0 && (
          <Button size="sm" variant="ghost" onClick={() => openConfirmGlobal({ message: t('ask_memoria.confirmar_borrar_todas'), onConfirm: () => borrar.mutate(null) })}>
            {t('ask_memoria.borrar_todas')}
          </Button>
        )}
      </div>
    </div>
  )
}

/**
 * «Corregir asignación» (23-11-2026): cuando la persona que eligió la IA no era la adecuada.
 *
 * Se usa en la ficha de la tarea y en la del ticket. Al confirmar:
 *  1. `POST /semantic/feedback` con la persona correcta: va a la caché de experto
 *     (niveles 1 y 2 del motor) y la sugerencia cuenta como rechazada en la precisión;
 *  2. `onCorregida(persona)`: la pantalla reasigna el ticket o la tarea con su
 *     propia llamada (la reasignación queda en su historial y auditoría habitual).
 *
 * Solo lo ve quien puede usar la asignación por IA (`ia.asignacion`).
 */
import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { UserCog } from 'lucide-react'
import { semanticApi } from '../../services/api'
import { Button, Modal, UserSelect } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'

export default function CorregirAsignacion({ itemType, itemId, asignadoActual, onCorregida }: {
  itemType: 'ticket' | 'task'
  itemId: string
  asignadoActual?: string | null
  onCorregida: (userId: string) => void | Promise<unknown>
}) {
  const t = useAppT()
  const toast = useToast()
  const { puede } = useAuth()
  const [abierto, setAbierto] = useState(false)
  const [persona, setPersona] = useState('')
  const corregir = useMutation({
    mutationFn: async () => {
      await semanticApi.feedback({ item_type: itemType, item_id: itemId, correct_user_id: persona })
      await onCorregida(persona)
    },
    onSuccess: () => { toast.success(t('bucle_ia.corregida')); setAbierto(false); setPersona('') },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  if (!puede('ia.asignacion') || !asignadoActual) return null
  return (
    <>
      <Button size="sm" variant="ghost" icon={<UserCog size={14} />} onClick={() => setAbierto(true)} title={t('bucle_ia.corregir_ayuda')}>
        {t('bucle_ia.corregir')}
      </Button>
      {abierto && (
        <Modal open onClose={() => setAbierto(false)} size="sm" title={t('bucle_ia.corregir')} subtitle={t('bucle_ia.corregir_ayuda')}>
          <form className="u-stack-12" onSubmit={e => { e.preventDefault(); if (persona && persona !== asignadoActual) corregir.mutate() }}>
            <UserSelect value={persona} onChange={(uid: string) => setPersona(uid)} placeholder={t('bucle_ia.persona_correcta')} required />
            {persona && persona === asignadoActual && <div className="u-text3-xs" role="status">{t('bucle_ia.misma_persona')}</div>}
            <div className="u-row-8">
              <Button type="submit" loading={corregir.isPending} disabled={!persona || persona === asignadoActual}>{t('bucle_ia.guardar')}</Button>
              <Button type="button" variant="ghost" onClick={() => setAbierto(false)}>{t('common.cancel')}</Button>
            </div>
          </form>
        </Modal>
      )}
    </>
  )
}

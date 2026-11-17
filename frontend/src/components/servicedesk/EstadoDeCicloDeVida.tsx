/**
 * EstadoDeCicloDeVida — el estado propio del ticket cuando su tipo tiene ciclo
 * de vida (mejoras de mercado 16-11-2026). Solo ofrece los pasos permitidos;
 * el estado base (SLA, pausas, avisos) lo pone el servidor.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { Select, StatusBadge } from '../ui'
import { slaAvanzadoApi } from '../../services/api/serviceDeskMercado'
import './sdMercado.css'

export default function EstadoDeCicloDeVida({ ticketId, onCambio }: { ticketId: string; onCambio: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { data } = useQuery({ queryKey: ['sdm-ticket-ciclo', ticketId], queryFn: () => slaAvanzadoApi.cicloDelTicket(ticketId) })
  const cambiar = useMutation({
    mutationFn: (estado: string) => slaAvanzadoApi.cambiarEstado(ticketId, estado),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sdm-ticket-ciclo', ticketId] }); onCambio(); toast.success(t('sd_mercado.estado_cambiado')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  if (!data?.lifecycle) return null
  const actual = data.states.find(s => s.key === data.current)
  return (
    <div className="u-row-center-8 u-mb-16">
      <span className="ds-eyebrow">{data.lifecycle}</span>
      {actual && <StatusBadge caps={false} color={actual.color || undefined}>{actual.label}</StatusBadge>}
      <Select suelto placeholder={false} aria-label={t('sd_mercado.cambiar_estado')} value="" disabled={cambiar.isPending}
        onChange={e => e.target.value && cambiar.mutate(e.target.value)}>
        <option value="">{t('sd_mercado.cambiar_estado')}</option>
        {data.states.filter(s => s.key !== data.current && s.allowed).map(s => <option key={s.key} value={s.key}>{s.label}</option>)}
      </Select>
    </div>
  )
}

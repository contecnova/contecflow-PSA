/**
 * Ticket ↔ activo o licencia, en los dos sentidos (licencias y hardware, fase 4).
 *
 * - `RecursoDelTicket`: en la ficha del ticket, el equipo o la licencia a la que
 *   apunta (devolución, avería, petición o compra).
 * - `TicketsDelRecurso`: en la ficha de un activo o una licencia, sus tickets.
 */
import { useQuery } from '@tanstack/react-query'
import { KeyRound, Laptop } from 'lucide-react'
import { almIntegracionApi } from '../../services/api/almIntegracion'
import { DataTable } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { fmtDate } from '../../utils/helpers'
import { Estado, etiqueta } from './almComun'
import './almIntegracion.css'

export function RecursoDelTicket({ ticketId }: { ticketId: string }) {
  const t = useAppT()
  const q = useQuery({ queryKey: ['alm-recurso-del-ticket', ticketId], queryFn: () => almIntegracionApi.recursoDelTicket(ticketId) })
  const r = q.data
  if (!r) return null
  return (
    <div className="ds-card almint-ficha">
      <span className="almint-tenue">{r.tipo === 'asset' ? t('almint.equipo_enlazado') : t('almint.licencia_enlazada')}</span>
      <div className="almint-pastillas">
        {r.tipo === 'asset' ? <Laptop size={14} aria-hidden /> : <KeyRound size={14} aria-hidden />}
        <strong>{r.name}</strong>
        {r.tipo === 'asset' && r.type && <span className="almint-tenue">{etiqueta(t, 'tipo_equipo', r.type)}</span>}
        {r.asset_tag && <span className="almint-tenue">{r.asset_tag}</span>}
        {r.serial_number && <span className="almint-tenue">{r.serial_number}</span>}
      </div>
      {r.holder_name && <span className="almint-tenue">{t('almint.lo_tiene', { nombre: r.holder_name })}</span>}
    </div>
  )
}

export function TicketsDelRecurso({ tipo, id }: { tipo: 'asset' | 'license'; id: string }) {
  const t = useAppT()
  const q = useQuery({ queryKey: ['alm-tickets-del-recurso', tipo, id], queryFn: () => almIntegracionApi.ticketsDelRecurso(tipo, id) })
  return <DataTable data={q.data ?? []} loading={q.isLoading} emptyTitle={t('almint.sin_tickets')} columns={[
    { key: 'number', label: t('almint.ticket') },
    { key: 'title', label: t('almint.col_titulo') },
    { key: 'status', label: t('almint.col_estado'), render: (_v, f) => <Estado t={t} codigo={f.status} /> },
    { key: 'created_at', label: t('almint.col_fecha'), render: (_v, f) => fmtDate(f.created_at) },
  ]} />
}

/**
 * Asignaciones y préstamos (licencias y hardware, fase 1): quién tiene qué ahora
 * (o tuvo), con filtros por estado, modo y titular; préstamos vencidos; y el
 * historial inmutable por titular («qué ha tenido esta persona o proyecto»).
 */
import { useId, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeftRight, History } from 'lucide-react'
import { Button, DataTable, EmptyState, Spinner } from '../../components/ui'
import type { ColumnaDeTabla } from '../../components/ui'
import Pagination from '../../components/ui/Pagination'
import { useAppT } from '../../i18n/AppLangContext'
import { almApi } from '../../services/api/alm'
import type { Asignacion, TipoDeTitular } from '../../services/api/alm'
import { fmtDate } from '../../utils/helpers'
import CerrarAsignacionModal from '../../components/alm/CerrarAsignacionModal'
import HistorialAlm from '../../components/alm/HistorialAlm'
import { EstadoAlm, ICONO_TITULAR, SelectorDeTitular, textoDeTitular } from '../../components/alm/almFases'

const POR_PAGINA = 25

export default function AsignacionesTab({ soloPrestamos = false, onAbrir }: {
  soloPrestamos?: boolean
  onAbrir: (a: Asignacion) => void
}) {
  const t = useAppT()
  const [estado, setEstado] = useState(soloPrestamos ? 'active' : 'active,pending')
  const [recurso, setRecurso] = useState('')
  const [vencidos, setVencidos] = useState(false)
  const [pagina, setPagina] = useState(1)
  const [cerrar, setCerrar] = useState<Asignacion | null>(null)
  const { data, isLoading } = useQuery({
    queryKey: ['alm-assignments', 'lista', soloPrestamos, estado, recurso, vencidos, pagina],
    queryFn: () => almApi.asignaciones({
      status: estado || undefined, mode: soloPrestamos ? 'loan' : undefined, overdue: vencidos || undefined,
      page: pagina, page_size: POR_PAGINA, ...(recurso ? { resource_type: recurso } : {}),
    }),
  })
  const filas = data?.items ?? []
  const columnas: ColumnaDeTabla<Asignacion>[] = [
    { key: 'resource_name', label: t('alm.resource'), render: (_v, a) => (
      <button type="button" className="alm-link-btn" onClick={() => onAbrir(a)}>{a.resource_name ?? '—'}</button>) },
    { key: 'holder_name', label: t('alm.holder'), render: (_v, a) => (
      <span className="almf-fila__nombre">{ICONO_TITULAR[a.holder_type]}{a.holder_name ?? textoDeTitular(t, a.holder_type)}</span>) },
    { key: 'mode', label: t('alm.assign_mode'), render: (_v, a) => <>{t(`alm.mode_${a.mode}`)}{a.quantity > 1 ? ` · ${a.quantity}` : ''}</> },
    { key: 'valid_from', label: t('alm.valid_from'), render: (_v, a) => fmtDate(a.valid_from) },
    { key: 'valid_to', label: soloPrestamos ? t('alm.loan_due') : t('alm.valid_to'), render: (_v, a) => a.valid_to ? fmtDate(a.valid_to) : '—' },
    { key: 'status', label: t('alm.status'), render: (_v, a) => <EstadoAlm t={t} codigo={a.status} vencido={a.overdue} /> },
    { key: 'reason', label: t('alm.reason'), render: (_v, a) => a.reason ?? '—' },
    { key: 'id', label: '', sortable: false, render: (_v, a) => (a.status === 'active' || a.status === 'pending') ? (
      <Button size="sm" variant="ghost" onClick={() => setCerrar(a)}>
        {a.status === 'pending' ? t('alm.cancel_request') : a.resource_type === 'asset' ? t('alm.end_return') : t('alm.end_action')}
      </Button>) : null },
  ]
  const paginas = Math.max(1, Math.ceil((data?.total ?? 0) / POR_PAGINA))
  return (
    <div>
      <div className="almf-filtros">
        <div className="almf-filtro">
          <label className="alm-label" htmlFor="almf-est">{t('alm.status')}</label>
          <select id="almf-est" className="alm-input" value={estado} onChange={e => { setEstado(e.target.value); setPagina(1) }}>
            <option value="active,pending">{t('alm.filter_current')}</option>
            <option value="active">{t('alm.st_active')}</option>
            <option value="pending">{t('alm.st_pending')}</option>
            <option value="ended">{t('alm.st_ended')}</option>
            <option value="rejected,cancelled">{t('alm.filter_rejected_cancelled')}</option>
            <option value="">{t('alm.filter_all')}</option>
          </select>
        </div>
        {!soloPrestamos && (
          <div className="almf-filtro">
            <label className="alm-label" htmlFor="almf-rec">{t('alm.resource')}</label>
            <select id="almf-rec" className="alm-input" value={recurso} onChange={e => { setRecurso(e.target.value); setPagina(1) }}>
              <option value="">{t('alm.filter_all')}</option>
              <option value="license">{t('alm.tab_licenses')}</option>
              <option value="asset">{t('alm.tab_assets')}</option>
            </select>
          </div>
        )}
        <label className="alm-check-row">
          <input type="checkbox" checked={vencidos} onChange={e => { setVencidos(e.target.checked); setPagina(1) }} />
          <span className="alm-check-label">{t('alm.filter_overdue')}</span>
        </label>
      </div>
      {isLoading ? <Spinner /> : filas.length === 0 ? (
        <EmptyState svgIcon={<ArrowLeftRight size={32} />} title={soloPrestamos ? t('alm.loans_empty') : t('alm.assignments_empty')} />
      ) : (
        <div className="almf-tabla-scroll"><DataTable columns={columnas} data={filas} pageSize={POR_PAGINA} /></div>
      )}
      {paginas > 1 && <div className="alm-pagination"><Pagination page={pagina} totalPages={paginas} onChange={setPagina} total={data?.total ?? 0} pageSize={POR_PAGINA} maxVisible={5} /></div>}
      {cerrar && <CerrarAsignacionModal asignacion={cerrar} onClose={() => setCerrar(null)} />}
    </div>
  )
}

/** Historial por titular: elige persona, proyecto, departamento, cliente o equipo y ve todo lo que ha tenido. */
export function HistorialPorTitularTab() {
  const t = useAppT()
  const id = useId()
  const [tipo, setTipo] = useState<TipoDeTitular>('user')
  const [titular, setTitular] = useState('')
  return (
    <div className="u-stack-14">
      <div className="alm-card almf-ficha__cuerpo">
        <SelectorDeTitular t={t} tipo={tipo} id={titular} idBase={id} onChange={(k, v) => { setTipo(k); setTitular(v) }} />
      </div>
      {titular
        ? <HistorialAlm filtro={{ holder_type: tipo, holder_id: titular }} vacio={t('alm.history_holder_empty')} />
        : <EmptyState svgIcon={<History size={32} />} title={t('alm.history_pick_holder')} description={t('alm.history_pick_holder_desc')} />}
    </div>
  )
}

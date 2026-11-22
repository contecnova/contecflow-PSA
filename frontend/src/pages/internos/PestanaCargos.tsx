/**
 * Clientes internos (22-11-2026): cargos internos (chargeback/showback).
 *
 * Lista con filtros (unidad, periodo, estado), generar el borrador de una
 * unidad y mes, y el detalle con sus líneas. Emitir, anular y exportar el CSV
 * de asientos piden `interno.cargos`; aprobar o rechazar, `can_approve` (lo
 * calcula el backend: responsable de la unidad, nunca quien generó o emitió).
 * Ver docs/CLIENTES_INTERNOS.md §4 y §10.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, Plus, Receipt } from 'lucide-react'
import { Button, EmptyState, Input, Modal, Pulsable, Select, Spinner, TablaSimple, Textarea } from '../../components/ui'
import StatusBadge from '../../components/ui/StatusBadge'
import { useToast } from '../../context/ToastContext'
import { usePermiso } from '../../permisos/usePermiso'
import { clientesInternosApi } from '../../services/api/clientesInternos'
import type { AccionDeCargo } from './logica'
import type { Cargo } from '../../services/api/clientesInternos'
import { useFormatoMoneda } from '../../hooks/useFormatoMoneda'
import { downloadBlob, extractErr, fmtDate, fmtNumber } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { useT } from './comunes'
import { ESTADOS_DE_CARGO, TONO_CARGO, accionesDeCargo, etiquetaInterna, mesActual, textoONull } from './logica'

type Unidad = { id: string; name: string }

function DetalleDeCargo({ id, onClose }: { id: string; onClose: () => void }) {
  const t = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const fmtMoneda = useFormatoMoneda()
  const puedeCargos = usePermiso('interno.cargos')
  const [nota, setNota] = useState('')
  const { data: cargo, isLoading } = useQuery({ queryKey: ['internal-clients', 'charge', id], queryFn: () => clientesInternosApi.cargo(id) })
  const accion = useMutation({
    mutationFn: (a: AccionDeCargo) => {
      const n = textoONull(nota)
      if (a === 'issue') return clientesInternosApi.emitirCargo(id)
      if (a === 'approve') return clientesInternosApi.aprobarCargo(id, n)
      if (a === 'reject') return clientesInternosApi.rechazarCargo(id, n)
      return clientesInternosApi.anularCargo(id, n)
    },
    onSuccess: (_r, a) => {
      qc.invalidateQueries({ queryKey: ['internal-clients'] })
      toast.success(t(`internos.cargo_hecho_${a}`))
      setNota('')
    },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const acciones = cargo ? accionesDeCargo(cargo.status, puedeCargos, cargo.can_approve) : []
  const necesitaNota = acciones.some(a => a !== 'issue')
  return (
    <Modal open onClose={onClose} width={760} title={cargo ? `${cargo.number || t('internos.cargo')} · ${cargo.client_name}` : t('internos.cargo')}>
      {isLoading || !cargo ? <Spinner /> : (
        <div className="u-stack-8">
          <div className="u-row-center-8">
            <StatusBadge kind={TONO_CARGO[cargo.status] || 'neutral'} caps={false}>{etiquetaInterna(t, 'cargo_estado_', cargo.status)}</StatusBadge>
            <span className="u-text2-sm">{[cargo.period, etiquetaInterna(t, 'modo_', cargo.mode)].join(' · ')}</span>
            {cargo.over_budget && <StatusBadge kind="danger" caps={false}>{t('internos.excede_presupuesto')}</StatusBadge>}
          </div>
          <div className="int-sub">
            {[
              t('internos.creado_el', { fecha: fmtDate(cargo.created_at) }),
              cargo.issued_at && t('internos.emitido_el', { fecha: fmtDate(cargo.issued_at) }),
              cargo.exported_at && t('internos.exportado_el', { fecha: fmtDate(cargo.exported_at) }),
              cargo.erp_reference && t('internos.referencia_erp', { ref: cargo.erp_reference }),
            ].filter(Boolean).join(' · ')}
          </div>
          <div className="u-scroll-x">
            <TablaSimple claseTabla="u-table" etiqueta={t('internos.lineas')}>
              <thead>
                <tr>
                  {[t('internos.col_fuente'), t('internos.col_descripcion'), t('internos.col_cantidad'), t('internos.col_precio'), t('internos.col_importe')].map(h => (
                    <th key={h} scope="col" className="int-th">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {cargo.lines.length === 0 ? (
                  <tr><td className="int-td int-td--muted" colSpan={5}>{t('internos.sin_lineas')}</td></tr>
                ) : cargo.lines.map((l, i) => (
                  <tr key={l.id || i}>
                    <td className="int-td">{etiquetaInterna(t, 'fuente_', l.source)}</td>
                    <td className="int-td int-td--muted">{[l.description, l.project_name].filter(Boolean).join(' · ') || '—'}</td>
                    <td className="int-td int-td--num">{l.quantity != null ? fmtNumber(l.quantity, 2) : '—'}</td>
                    <td className="int-td int-td--num">{l.unit_amount != null ? fmtMoneda(l.unit_amount, { moneda: cargo.currency }) : '—'}</td>
                    <td className="int-td int-td--num">{fmtMoneda(l.amount, { moneda: cargo.currency })}</td>
                  </tr>
                ))}
              </tbody>
            </TablaSimple>
          </div>
          <div className="int-total"><span>{t('internos.total')}</span><span>{fmtMoneda(cargo.total, { moneda: cargo.currency })}</span></div>
          {acciones.length > 0 && (
            <>
              {necesitaNota && (
                <Textarea label={t('internos.nota')} value={nota} onChange={e => setNota(e.target.value)} rows={2} />
              )}
              <div className="u-actions-8">
                {acciones.map(a => (
                  <Button key={a} size="sm" variant={a === 'reject' || a === 'cancel' ? 'secondary' : 'primary'}
                    loading={accion.isPending && accion.variables === a} disabled={accion.isPending}
                    onClick={() => accion.mutate(a)}>{t(`internos.accion_${a}`)}</Button>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </Modal>
  )
}

function GenerarCargo({ unidades, onClose, onCreado }: { unidades: Unidad[]; onClose: () => void; onCreado: (id: string) => void }) {
  const t = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const [unidad, setUnidad] = useState('')
  const [periodo, setPeriodo] = useState(mesActual())
  const generar = useMutation({
    mutationFn: () => clientesInternosApi.generarCargo(unidad, periodo),
    onSuccess: r => { qc.invalidateQueries({ queryKey: ['internal-clients'] }); toast.success(t('internos.cargo_generado')); onCreado(r.id) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  return (
    <Modal open onClose={onClose} width={480} title={t('internos.generar_borrador')}>
      <div className="u-stack-8">
        <p className="u-text2-sm">{t('internos.generar_borrador_d')}</p>
        <Select label={t('internos.col_unidad')} required value={unidad} onChange={e => setUnidad(e.target.value)}
          placeholder={t('internos.elegir')} options={unidades.map(u => ({ value: u.id, label: u.name }))} />
        <Input label={t('internos.periodo')} type="month" required value={periodo} onChange={e => setPeriodo(e.target.value)} />
        <div className="u-actions-8">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => generar.mutate()} loading={generar.isPending} disabled={!unidad || !periodo || generar.isPending}>{t('internos.generar')}</Button>
        </div>
      </div>
    </Modal>
  )
}

export default function PestanaCargos({ unidades }: { unidades: Unidad[] }) {
  const t = useT()
  const toast = useToast()
  const fmtMoneda = useFormatoMoneda()
  const puedeCargos = usePermiso('interno.cargos')
  const [f, setF] = useState({ client_id: '', period: '', status: '' })
  const [abierto, setAbierto] = useState<string | null>(null)
  const [generando, setGenerando] = useState(false)
  const [exportando, setExportando] = useState(false)
  const { data: cargos = [], isLoading } = useQuery({
    queryKey: ['internal-clients', 'charges', f],
    queryFn: () => clientesInternosApi.cargos(f),
  })
  const exportar = async () => {
    const periodo = f.period || mesActual()
    setExportando(true)
    try {
      downloadBlob(await clientesInternosApi.exportarCargos(periodo), `cargos-internos-${periodo}.csv`)
    } catch (e) {
      toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
    } finally {
      setExportando(false)
    }
  }
  return (
    <div className="u-stack-8">
      <div className="int-barra">
        <div className="int-barra__filtros">
          <Select label={t('internos.col_unidad')} value={f.client_id} onChange={e => setF(x => ({ ...x, client_id: e.target.value }))}
            placeholder={t('internos.todas')} options={unidades.map(u => ({ value: u.id, label: u.name }))} />
          <Input label={t('internos.periodo')} type="month" value={f.period} onChange={e => setF(x => ({ ...x, period: e.target.value }))} />
          <Select label={t('internos.col_estado')} value={f.status} onChange={e => setF(x => ({ ...x, status: e.target.value }))}
            placeholder={t('internos.todos')} options={ESTADOS_DE_CARGO.map(s => ({ value: s, label: etiquetaInterna(t, 'cargo_estado_', s) }))} />
        </div>
        <div className="u-row-6">
          {puedeCargos && (
            <Button size="sm" variant="secondary" icon={<Download size={14} />} loading={exportando} disabled={exportando} onClick={exportar}
              title={t('internos.exportar_csv_d')}>{t('internos.exportar_csv')}</Button>
          )}
          <Button size="sm" icon={<Plus size={14} />} onClick={() => setGenerando(true)}>{t('internos.generar_borrador')}</Button>
        </div>
      </div>
      {isLoading ? <Spinner /> : cargos.length === 0 ? (
        <EmptyState icon={<Receipt size={28} />} title={t('internos.sin_cargos')} description={t('internos.sin_cargos_d')} />
      ) : (
        <div className="u-scroll-x">
          <TablaSimple claseTabla="u-table" etiqueta={t('internos.tab_cargos')}>
            <thead>
              <tr>
                {[t('internos.col_numero'), t('internos.col_unidad'), t('internos.periodo'), t('internos.col_modo'), t('internos.col_importe'), t('internos.col_estado')].map(h => (
                  <th key={h} scope="col" className="int-th">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {cargos.map((c: Cargo) => (
                <tr key={c.id}>
                  <td className="int-td">
                    <Pulsable type="button" className="int-enlace" onClick={() => setAbierto(c.id)}>{c.number || t('internos.borrador')}</Pulsable>
                  </td>
                  <td className="int-td">{c.client_name}</td>
                  <td className="int-td int-td--muted">{c.period}</td>
                  <td className="int-td int-td--muted">{etiquetaInterna(t, 'modo_', c.mode)}</td>
                  <td className="int-td int-td--num">{fmtMoneda(c.total, { moneda: c.currency })}</td>
                  <td className="int-td">
                    <div className="u-row-6">
                      <StatusBadge kind={TONO_CARGO[c.status] || 'neutral'} caps={false}>{etiquetaInterna(t, 'cargo_estado_', c.status)}</StatusBadge>
                      {c.over_budget && <StatusBadge kind="danger" caps={false}>{t('internos.excede_presupuesto')}</StatusBadge>}
                      {c.can_approve && c.status === 'por_aprobar' && <StatusBadge kind="warning" caps={false}>{t('internos.te_toca_aprobar')}</StatusBadge>}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </TablaSimple>
        </div>
      )}
      {generando && <GenerarCargo unidades={unidades} onClose={() => setGenerando(false)} onCreado={id => { setGenerando(false); setAbierto(id) }} />}
      {abierto && <DetalleDeCargo id={abierto} onClose={() => setAbierto(null)} />}
    </div>
  )
}

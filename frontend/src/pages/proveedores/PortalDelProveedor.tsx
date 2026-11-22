/**
 * Portal del proveedor (`/supplier-portal`, migración 191).
 *
 * Para las personas externas (rol `subcontractor`) que la empresa marca como
 * contacto del portal de su proveedor. Solo lo de su proveedor, lo decide el
 * backend (`app/services/proveedores/portal.py`): ninguna llamada lleva el id del
 * proveedor. Pestañas:
 *
 * - Informes: subir avance de un paquete, informe periódico, parte de servicio o
 *   evidencia de SLA (con ficheros o enlaces) y ver su revisión.
 * - Paquetes de trabajo y Servicios (con el SLA medido en la cola del service desk).
 * - Consumo del periodo (lo medido por contrato) y Estados de cuenta.
 *
 * Sin la marca de contacto (`GET /supplier-portal/me` → `enabled: false`) se
 * explica cómo pedir el acceso. Con el proveedor suspendido se ve pero no se sube.
 */
import { useState } from 'react'
import type { ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Briefcase, ClipboardList, FileBarChart, Gauge, Globe, Layers, Plus, Receipt, Scale } from 'lucide-react'
import { Button, Card, EmptyState, Input, KpiCard, Modal, Select, Spinner, TablaSimple, Tabs, useErroresDeCampo, Textarea } from '../../components/ui'
import StatusBadge from '../../components/ui/StatusBadge'
import PageHeader from '../../components/layout/PageHeader'
import PageShell from '../../components/layout/PageShell'
import { useToast } from '../../context/ToastContext'
import { portalProveedorApi } from '../../services/api/proveedores'
import type { InformeIn, PaqueteDeTrabajo, ServicioDeProveedor, TipoDeInforme } from '../../services/api/tipos-proveedores'
import { useCatalogo } from '../../hooks/useCatalogo'
import { useFormatoMoneda } from '../../hooks/useFormatoMoneda'
import { extractErr, fmtDate, fmtNumber } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { TIPOS_DE_INFORME, TONO_CUENTA, TONO_PAQUETE, conRespaldo, mesDe, numeroONull, textoONull } from './logica'
import { etiquetaDe, useT } from './comunes'
import { AdjuntosDeInforme } from './PestanaPaquetes'
import PestanaSolicitudes from './PestanaSolicitudes'

type Pestana = 'reports' | 'packages' | 'services' | 'usage' | 'statements' | 'requests'

/** Destinos válidos de un tipo de informe: avance → paquete; el resto → servicio. */
export function destinosDeInforme(tipo: TipoDeInforme, paquetes: PaqueteDeTrabajo[], servicios: ServicioDeProveedor[]) {
  return tipo === 'progress'
    ? paquetes.filter(w => w.status !== 'accepted' && w.status !== 'cancelled').map(w => ({ value: w.id, label: w.title }))
    : servicios.filter(s => s.status !== 'ended').map(s => ({ value: s.id, label: s.name }))
}

function SubirInforme({ paquetes, servicios, onClose }: { paquetes: PaqueteDeTrabajo[]; servicios: ServicioDeProveedor[]; onClose: () => void }) {
  const t = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const campos = useErroresDeCampo()
  const tiposPosibles = TIPOS_DE_INFORME.filter(x => (x === 'progress' ? paquetes.length > 0 : servicios.length > 0))
  const [f, setF] = useState({
    report_type: (tiposPosibles[0] || 'progress') as TipoDeInforme, destino: '', period_start: '', period_end: '',
    progress_pct: '', summary: '', risks: '', enlace: '',
  })
  const [ficheros, setFicheros] = useState<File[]>([])
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => { campos.limpiar(k); setF(x => ({ ...x, [k]: e.target.value })) }
  const destinos = destinosDeInforme(f.report_type, paquetes, servicios)
  const subir = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: async () => {
      const d: InformeIn = {
        report_type: f.report_type,
        work_package_id: f.report_type === 'progress' ? f.destino : null,
        service_id: f.report_type === 'progress' ? null : f.destino,
        period_start: f.period_start || null, period_end: f.period_end || null,
        progress_pct: f.report_type === 'progress' ? numeroONull(f.progress_pct) : null,
        summary: f.summary.trim(), risks: textoONull(f.risks),
        attachments: f.enlace.trim() ? [{ url: f.enlace.trim() }] : null,
      }
      const r = await portalProveedorApi.crearInforme(d)
      for (const fichero of ficheros) await portalProveedorApi.adjuntar(r.data.id, fichero)
      return r
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['supplier-portal'] }); toast.success(t('proveedores.portal_informe_enviado')); onClose() },
    onError: (e: unknown) => { qc.invalidateQueries({ queryKey: ['supplier-portal'] }); if (!campos.recoger(e)) toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) },
  })
  return (
    <Modal open title={t('proveedores.portal_subir_informe')} onClose={onClose} width={600}>
      <div className="u-stack-8">
        <div className="prv-rejilla">
          <Select label={t('proveedores.tipo_de_informe')} value={f.report_type} placeholder={false}
            onChange={e => setF(x => ({ ...x, report_type: e.target.value as TipoDeInforme, destino: '' }))}
            options={tiposPosibles.map(x => ({ value: x, label: etiquetaDe(t, 'informe_tipo_', x) }))} />
          <Select label={f.report_type === 'progress' ? t('proveedores.paquete') : t('proveedores.servicio')} required value={f.destino}
            onChange={set('destino')} placeholder={t('proveedores.elegir')} options={destinos}
            error={campos.de(f.report_type === 'progress' ? 'work_package_id' : 'service_id')} />
          <Input label={t('proveedores.desde')} type="date" value={f.period_start} onChange={set('period_start')} error={campos.de('period_start')} />
          <Input label={t('proveedores.hasta')} type="date" value={f.period_end} onChange={set('period_end')} error={campos.de('period_end')} />
          {f.report_type === 'progress' && (
            <Input label={t('proveedores.avance_pct')} type="number" min={0} max={100} value={f.progress_pct} onChange={set('progress_pct')} error={campos.de('progress_pct')} />
          )}
        </div>
        <p className="u-text3-xs">{t(`proveedores.informe_tipo_${f.report_type}_d`)}</p>
        <div className="ui-field">
          <label htmlFor="prv-portal-resumen" className="uiinde-estiloetiqueta">{t('proveedores.resumen')} *</label>
          <Textarea id="prv-portal-resumen" value={f.summary} onChange={set('summary')} inputClassName="prv-textarea" />
          {campos.de('summary') && <div className="u-field-error" role="alert">{campos.de('summary')}</div>}
        </div>
        <div className="ui-field">
          <label htmlFor="prv-portal-riesgos" className="uiinde-estiloetiqueta">{t('proveedores.riesgos')}</label>
          <Textarea id="prv-portal-riesgos" value={f.risks} onChange={set('risks')} inputClassName="prv-textarea" />
        </div>
        <Input label={t('proveedores.evidencia_enlace')} value={f.enlace} onChange={set('enlace')} placeholder="https://" error={campos.de('attachments')} />
        <div className="ui-field">
          <label htmlFor="prv-portal-ficheros" className="uiinde-estiloetiqueta">{t('proveedores.evidencias')}</label>
          <input id="prv-portal-ficheros" type="file" multiple className="ds-input" onChange={e => setFicheros(Array.from(e.target.files || []))} />
        </div>
        <div className="u-actions-8">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => subir.mutate()} loading={subir.isPending} disabled={!f.summary.trim() || !f.destino || subir.isPending}>
            {t('proveedores.portal_enviar')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function Informes({ puedeEscribir, paquetes, servicios }: { puedeEscribir: boolean; paquetes: PaqueteDeTrabajo[]; servicios: ServicioDeProveedor[] }) {
  const t = useT()
  const [subiendo, setSubiendo] = useState(false)
  const { data: informes = [], isLoading } = useQuery({ queryKey: ['supplier-portal', 'reports'], queryFn: () => portalProveedorApi.informes().then(r => r.data) })
  const nombres: Record<string, string> = Object.fromEntries([...paquetes.map(w => [w.id, w.title]), ...servicios.map(s => [s.id, s.name])])
  if (isLoading) return <Spinner />
  return (
    <div className="u-stack-8">
      {puedeEscribir && (
        <div className="sub-toolbar-end">
          <Button size="sm" icon={<Plus size={14} />} disabled={!paquetes.length && !servicios.length} onClick={() => setSubiendo(true)}>{t('proveedores.portal_subir_informe')}</Button>
        </div>
      )}
      {informes.length === 0 ? (
        <EmptyState icon={<FileBarChart size={28} />} title={t('proveedores.portal_sin_informes')} description={t('proveedores.portal_sin_informes_d')} />
      ) : informes.map(r => (
        <Card key={r.id} className="sub-item">
          <div className="u-row-center-8">
            <strong>{nombres[r.work_package_id || r.service_id || ''] || '—'}</strong>
            <StatusBadge kind="neutral" caps={false}>{etiquetaDe(t, 'informe_tipo_', r.report_type)}</StatusBadge>
            <StatusBadge kind={r.status === 'reviewed' ? 'success' : 'warning'} caps={false}>{etiquetaDe(t, 'informe_estado_', r.status)}</StatusBadge>
            {r.progress_pct != null && <span className="u-text2-sm">{fmtNumber(r.progress_pct, 0)}%</span>}
          </div>
          <div className="prv-sub">{(r.period_start || r.period_end) ? `${fmtDate(r.period_start)} – ${fmtDate(r.period_end)} · ` : ''}{r.summary}</div>
          {r.review_notes && <div className="u-text3-xs">{t('proveedores.notas_revision')}: {r.review_notes}</div>}
          <AdjuntosDeInforme informe={r} abrir={portalProveedorApi.abrirAdjunto} />
        </Card>
      ))}
      {subiendo && <SubirInforme paquetes={paquetes} servicios={servicios} onClose={() => setSubiendo(false)} />}
    </div>
  )
}

function Paquetes({ paquetes }: { paquetes: PaqueteDeTrabajo[] }) {
  const t = useT()
  const fmtMoneda = useFormatoMoneda()
  if (!paquetes.length) return <EmptyState icon={<Briefcase size={28} />} title={t('proveedores.sin_paquetes')} description={t('proveedores.portal_sin_paquetes_d')} />
  return (
    <div className="u-stack-8">
      {paquetes.map(w => (
        <Card key={w.id} className="sub-item">
          <div className="u-row-center-8">
            <span className="prv-titulo-item">{w.title}</span>
            <StatusBadge kind={TONO_PAQUETE[w.status] || 'neutral'} caps={false}>{etiquetaDe(t, 'paquete_estado_', w.status)}</StatusBadge>
            <StatusBadge kind="neutral" caps={false}>{etiquetaDe(t, 'alcance_', w.scope_type)}</StatusBadge>
          </div>
          <div className="prv-sub">
            {[
              w.project_name,
              (w.planned_start || w.planned_end) && `${fmtDate(w.planned_start)} – ${fmtDate(w.planned_end)}`,
              w.price != null && fmtMoneda(w.price, { moneda: w.currency }),
              w.progress_pct != null && t('proveedores.avance_n', { pct: fmtNumber(w.progress_pct, 0) }),
              w.accepted_at && t('proveedores.aceptado_el', { fecha: fmtDate(w.accepted_at) }),
            ].filter(Boolean).join(' · ')}
          </div>
          {w.acceptance_criteria && <div className="u-text3-xs">{t('proveedores.criterios_aceptacion')}: {w.acceptance_criteria}</div>}
          {w.status === 'rejected' && w.rejection_reason && <div className="prv-aviso prv-aviso--peligro prv-mt">{w.rejection_reason}</div>}
        </Card>
      ))}
    </div>
  )
}

function Servicios({ servicios }: { servicios: ServicioDeProveedor[] }) {
  const t = useT()
  const tipos = useCatalogo('supplier-service-types')
  const mes = mesDe()
  const [elegido, setElegido] = useState<string>('')
  const { data: sla } = useQuery({
    queryKey: ['supplier-portal', 'sla', elegido, mes.desde],
    queryFn: () => portalProveedorApi.sla(elegido, { desde: mes.desde, hasta: mes.hasta }).then(r => r.data),
    enabled: !!elegido,
  })
  if (!servicios.length) return <EmptyState icon={<Layers size={28} />} title={t('proveedores.sin_servicios')} description={t('proveedores.portal_sin_servicios_d')} />
  const pct = (v: number | null | undefined) => (v == null ? '—' : `${fmtNumber(v, 1)}%`)
  return (
    <div className="u-stack-8">
      {servicios.map(s => (
        <Card key={s.id} className="sub-item">
          <div className="prv-cabecera-item">
            <div className="u-min0">
              <div className="u-row-center-8">
                <span className="prv-titulo-item">{s.name}</span>
                <StatusBadge kind="neutral" caps={false}>{tipos.etiqueta(s.service_type)}</StatusBadge>
              </div>
              <div className="prv-sub">
                {[
                  s.sla_response_hours != null && t('proveedores.respuesta_n_h', { h: fmtNumber(s.sla_response_hours, 2) }),
                  s.sla_resolution_hours != null && t('proveedores.resolucion_n_h', { h: fmtNumber(s.sla_resolution_hours, 2) }),
                  s.sla_target_pct != null && t('proveedores.objetivo_n', { pct: fmtNumber(s.sla_target_pct, 1) }),
                  s.metering_last_quantity != null && t('proveedores.ultimo_recuento', { n: fmtNumber(s.metering_last_quantity, 0), fecha: fmtDate(s.metering_last_at) }),
                ].filter(Boolean).join(' · ')}
              </div>
            </div>
            <Button size="xs" variant="secondary" icon={<Gauge size={13} />} onClick={() => setElegido(s.id)}>{t('proveedores.ver_sla')}</Button>
          </div>
          {elegido === s.id && sla && (
            <div className="ds-grid-stats prv-mt">
              <KpiCard label={t('proveedores.tickets_resueltos')} value={`${sla.tickets_resolved} / ${sla.tickets_total}`} />
              <KpiCard label={t('proveedores.cumplimiento_sla')} value={pct(sla.compliance_pct)} danger={sla.met === false} />
              <KpiCard label={t('proveedores.respuesta_en_plazo')} value={pct(sla.response_met_pct)} />
              <KpiCard label={t('proveedores.resolucion_en_plazo')} value={pct(sla.resolution_met_pct)} />
            </div>
          )}
        </Card>
      ))}
    </div>
  )
}

function Consumo() {
  const t = useT()
  const fmtMoneda = useFormatoMoneda()
  const unidades = useCatalogo('supplier-billing-units')
  const mes = mesDe()
  const [desde, setDesde] = useState(mes.desde)
  const [hasta, setHasta] = useState(mes.hasta)
  const { data, isLoading } = useQuery({
    queryKey: ['supplier-portal', 'usage', desde, hasta],
    queryFn: () => portalProveedorApi.consumo({ desde, hasta }).then(r => r.data),
    enabled: !!desde && !!hasta,
  })
  return (
    <div className="u-stack-8">
      <div className="prv-rejilla">
        <Input label={t('proveedores.desde')} type="date" value={desde} onChange={e => setDesde(e.target.value)} />
        <Input label={t('proveedores.hasta')} type="date" value={hasta} onChange={e => setHasta(e.target.value)} />
      </div>
      {isLoading ? <Spinner /> : !data?.contracts.length ? <p className="u-text2-sm">{t('proveedores.portal_sin_consumo')}</p> : data.contracts.map(c => (
        <Card key={c.contract_id} className="prv-bloque">
          <div className="prv-bloque-titulo">{c.title}</div>
          <div className="u-scroll-x">
            <TablaSimple claseTabla="u-table">
              <thead>
                <tr className="u-border-b">
                  {[t('proveedores.modelo_de_cobro'), t('subcontractors.descripcion'), t('proveedores.cantidad'), t('subcontractors.col_importe'), t('proveedores.origen')].map(h => (
                    <th key={h} scope="col" className="sub-th">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {c.lines.map((l, i) => (
                  <tr key={i} className="sub-tr">
                    <td className="sub-td">{etiquetaDe(t, 'modelo_', l.model)}</td>
                    <td className="sub-td sub-td--muted">{l.description || '—'}</td>
                    <td className="sub-td sub-td--mono">{l.quantity != null ? fmtNumber(l.quantity, 2) : '—'}{l.unit ? ` ${unidades.etiqueta(l.unit)}` : ''}</td>
                    <td className="sub-td sub-td--mono">{fmtMoneda(l.amount ?? 0, { moneda: c.currency })}</td>
                    <td className="sub-td sub-td--muted">{l.source ? conRespaldo(t, `proveedores.origen_${l.source}`, l.source) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </TablaSimple>
          </div>
          <div className="prv-datos">
            <div className="prv-dato"><div className="prv-dato-etiqueta">{t('proveedores.creditos')}</div><div className="prv-dato-valor prv-numero prv-numero--neg">{fmtMoneda(-Math.abs(c.credits), { moneda: c.currency })}</div></div>
            <div className="prv-dato"><div className="prv-dato-etiqueta">{t('proveedores.bonus')}</div><div className="prv-dato-valor prv-numero">{fmtMoneda(c.bonus, { moneda: c.currency })}</div></div>
            <div className="prv-dato"><div className="prv-dato-etiqueta">{t('proveedores.esperado')}</div><div className="prv-dato-valor prv-titulo-item prv-numero">{fmtMoneda(c.expected_amount, { moneda: c.currency })}</div></div>
          </div>
        </Card>
      ))}
    </div>
  )
}

function Estados() {
  const t = useT()
  const fmtMoneda = useFormatoMoneda()
  const { data: estados = [], isLoading } = useQuery({ queryKey: ['supplier-portal', 'statements'], queryFn: () => portalProveedorApi.estadosDeCuenta().then(r => r.data) })
  if (isLoading) return <Spinner />
  if (!estados.length) return <EmptyState icon={<Scale size={28} />} title={t('proveedores.sin_estados')} description={t('proveedores.portal_sin_estados_d')} />
  return (
    <div className="u-scroll-x">
      <TablaSimple claseTabla="u-table">
        <thead>
          <tr className="u-border-b">
            {[t('proveedores.contrato'), t('externos.col_periodo'), t('proveedores.esperado'), t('proveedores.factura'), t('externos.col_diferencia'), t('subcontractors.col_estado')].map(h => (
              <th key={h} scope="col" className="sub-th">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {estados.map(s => (
            <tr key={s.id} className="sub-tr">
              <td className="sub-td sub-td--strong">{s.contract_title || '—'}</td>
              <td className="sub-td sub-td--muted">{fmtDate(s.period_start)} – {fmtDate(s.period_end)}</td>
              <td className="sub-td sub-td--mono">{fmtMoneda(s.expected_amount, { moneda: s.currency })}</td>
              <td className="sub-td sub-td--mono">{s.invoice_amount != null ? fmtMoneda(s.invoice_amount, { moneda: s.currency }) : '—'}</td>
              <td className="sub-td sub-td--mono">{s.difference != null ? fmtMoneda(s.difference, { moneda: s.currency }) : '—'}</td>
              <td className="sub-td">
                <StatusBadge kind={TONO_CUENTA[s.status] || 'neutral'} caps={false}>{etiquetaDe(t, 'cuenta_estado_', s.status)}</StatusBadge>
                {s.dispute_reason && <div className="u-text3-xs">{conRespaldo(t, `proveedores.motivo_${s.dispute_reason}`, s.dispute_reason)}</div>}
              </td>
            </tr>
          ))}
        </tbody>
      </TablaSimple>
    </div>
  )
}

export default function PortalDelProveedor() {
  const t = useT()
  const [tab, setTab] = useState<Pestana>('reports')
  const { data: yo, isLoading } = useQuery({ queryKey: ['supplier-portal', 'me'], queryFn: () => portalProveedorApi.yo().then(r => r.data) })
  const habilitado = !!yo?.enabled
  const { data: paquetes = [] } = useQuery({ queryKey: ['supplier-portal', 'work-packages'], queryFn: () => portalProveedorApi.paquetes().then(r => r.data), enabled: habilitado })
  const { data: servicios = [] } = useQuery({ queryKey: ['supplier-portal', 'services'], queryFn: () => portalProveedorApi.servicios().then(r => r.data), enabled: habilitado })

  if (isLoading) return <PageShell><Spinner /></PageShell>
  if (!habilitado || !yo?.supplier) {
    return (
      <PageShell>
        <PageHeader icon={<Globe size={18} />} title={t('proveedores.portal_del_proveedor')} />
        <EmptyState icon={<Globe size={28} />} title={t('proveedores.portal_sin_acceso')} description={t('proveedores.portal_sin_acceso_d')} />
      </PageShell>
    )
  }
  const pestanas: { id: Pestana; label: string; icon: ReactNode }[] = [
    { id: 'reports', label: t('proveedores.informes'), icon: <FileBarChart size={14} /> },
    { id: 'packages', label: t('proveedores.tab_paquetes'), icon: <Briefcase size={14} /> },
    { id: 'services', label: t('proveedores.tab_servicios'), icon: <Layers size={14} /> },
    { id: 'usage', label: t('proveedores.consumo'), icon: <Receipt size={14} /> },
    { id: 'statements', label: t('proveedores.estados_de_cuenta'), icon: <Scale size={14} /> },
    // Flujo de demanda (migración 195): pedir y seguir sus solicitudes.
    { id: 'requests', label: t('demanda.mis_solicitudes'), icon: <ClipboardList size={14} /> },
  ]
  return (
    <PageShell>
      <PageHeader icon={<Globe size={18} />} title={t('proveedores.portal_del_proveedor')}
        subtitle={[yo.supplier.name, yo.person?.access_until ? t('proveedores.acceso_hasta', { fecha: fmtDate(yo.person.access_until) }) : null].filter(Boolean).join(' · ')}
        showListExport={false} />
      {!yo.can_write && <div className="prv-aviso">{t('proveedores.portal_solo_lectura')}</div>}
      <Tabs items={pestanas} active={tab} onChange={v => setTab(v as Pestana)} ariaLabel={t('proveedores.portal_del_proveedor')} />
      <div className="prv-mt">
        {tab === 'reports' && <Informes puedeEscribir={!!yo.can_write} paquetes={paquetes} servicios={servicios} />}
        {tab === 'packages' && <Paquetes paquetes={paquetes} />}
        {tab === 'services' && <Servicios servicios={servicios} />}
        {tab === 'usage' && <Consumo />}
        {tab === 'statements' && <Estados />}
        {tab === 'requests' && <PestanaSolicitudes />}
      </div>
    </PageShell>
  )
}

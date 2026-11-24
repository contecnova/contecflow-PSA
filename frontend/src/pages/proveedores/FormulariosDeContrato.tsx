/**
 * Contratos y líneas de precio de proveedor (19-11-2026). Los usan la ficha
 * (Contratos y precios) y Configuración → Proveedores (plantillas).
 *
 * Modelos de cobro combinables por contrato (§3 del diseño): por recurso
 * (perfil/tarifa), precio cerrado (paquete), por unidad (ticket, dispositivo…),
 * cuota con unidades incluidas y exceso, gastos y bonus; con escalados por
 * volumen (tramos), mínimo y tope por periodo y vigencia.
 */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Pencil, Plus, Trash2, X } from 'lucide-react'
import { Button, Checkbox, IconButton, Input, Modal, Select, useErroresDeCampo, Textarea } from '../../components/ui'
import { usePersonasInternas } from '../../components/externos/FormularioDeExterno'
import { etiquetaDePersona } from '../../components/ui/MarcaExterno'
import { proveedoresApi } from '../../services/api/proveedores'
import type {
  ContratoDeProveedor, ContratoIn, LineaDePrecio, LineaIn, ModeloDeCobro, ModoDeRelacion, PaqueteDeTrabajo,
  ServicioDeProveedor, TramoDePrecio,
} from '../../services/api/tipos-proveedores'
import type { SubTarifa } from '../../services/api/tipos-alm'
import { useCatalogo } from '../../hooks/useCatalogo'
import { useOrgSettings } from '../../hooks/useOrgSettings'
import { useFormatoMoneda } from '../../hooks/useFormatoMoneda'
import { useToast } from '../../context/ToastContext'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { useAppT } from '../../i18n/AppLangContext'
import { extractErr, fmtDate, fmtNumber } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { MODELOS, PERIODOS, TIPOS_DE_CONTRATO, numeroONull, texto, textoONull } from './logica'
import { FaltaConfigurar, etiquetaDe, useProyectosActivos, useReferencias, useT } from './comunes'
import { ModosDeRelacion } from './AltaDeProveedor'

const fecha = (v: string) => (v ? v : null)

// ── Contrato ─────────────────────────────────────────────────────────────────
/**
 * Alta o edición de un contrato. `subId` vacío y `plantilla` = es una plantilla
 * (`/suppliers/contract-templates`).
 */
export function FormularioDeContrato({ subId, contrato, plantilla = false, onClose }: {
  subId?: string; contrato?: ContratoDeProveedor | null; plantilla?: boolean; onClose: () => void
}) {
  const t = useT()
  const tApp = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const campos = useErroresDeCampo()
  const { currency, currencies } = useOrgSettings()
  const { personas } = usePersonasInternas()
  const proyectos = useProyectosActivos()
  const referencias = useReferencias({ subId })
  const c = contrato
  const [f, setF] = useState({
    budget_id: texto(c?.budget_id), cost_center_id: texto(c?.cost_center_id),
    title: texto(c?.title), code: texto(c?.code), contract_type: c?.contract_type || 'framework',
    modes: (c?.modes || []) as ModoDeRelacion[], start_date: texto(c?.start_date), end_date: texto(c?.end_date),
    auto_renew: !!c?.auto_renew, notice_days: texto(c?.notice_days), currency: c?.currency || currency,
    committed_minimum: texto(c?.committed_minimum), minimum_period: texto(c?.minimum_period), total_cap: texto(c?.total_cap),
    po_number: texto(c?.po_number), po_amount: texto(c?.po_amount), project_id: texto(c?.project_id),
    payment_terms_days: texto(c?.payment_terms_days), expenses_rebillable: !!c?.expenses_rebillable,
    expenses_cap: texto(c?.expenses_cap), internal_owner_id: texto(c?.internal_owner_id),
    document_url: texto(c?.document_url), notes: texto(c?.notes),
  })
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => { campos.limpiar(k); setF(x => ({ ...x, [k]: e.target.value })) }

  const guardar = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: () => {
      const d: ContratoIn = {
        title: f.title.trim(), code: textoONull(f.code), contract_type: f.contract_type as ContratoIn['contract_type'],
        modes: f.modes, start_date: fecha(f.start_date), end_date: fecha(f.end_date), auto_renew: f.auto_renew,
        notice_days: numeroONull(f.notice_days), currency: f.currency || null,
        committed_minimum: numeroONull(f.committed_minimum), minimum_period: (f.minimum_period || null) as ContratoIn['minimum_period'],
        total_cap: numeroONull(f.total_cap), po_number: textoONull(f.po_number), po_amount: numeroONull(f.po_amount),
        project_id: f.project_id || null, payment_terms_days: numeroONull(f.payment_terms_days),
        budget_id: plantilla ? null : (f.budget_id || null), cost_center_id: f.cost_center_id || null,
        expenses_rebillable: f.expenses_rebillable, expenses_cap: numeroONull(f.expenses_cap),
        internal_owner_id: f.internal_owner_id || null, document_url: textoONull(f.document_url), notes: textoONull(f.notes),
      }
      if (plantilla) return c ? proveedoresApi.editarPlantilla(c.id, d) : proveedoresApi.crearPlantilla(d)
      return c ? proveedoresApi.editarContrato(c.id, d) : proveedoresApi.crearContrato(subId || '', d)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['suppliers'] })
      toast.success(t('proveedores.contrato_guardado'))
      onClose()
    },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) },
  })

  const titulo = plantilla ? (c ? t('proveedores.editar_plantilla') : t('proveedores.nueva_plantilla')) : (c ? t('proveedores.editar_contrato') : t('proveedores.nuevo_contrato'))
  return (
    <Modal open title={titulo} onClose={onClose} width={680}>
      <div className="u-stack-8">
        <div className="prv-rejilla">
          <Input className="prv-completo" label={t('proveedores.titulo')} required value={f.title} onChange={set('title')} error={campos.de('title')} />
          <Input label={t('proveedores.referencia')} value={f.code} onChange={set('code')} error={campos.de('code')} />
          <Select label={t('proveedores.tipo_de_contrato')} value={f.contract_type} placeholder={false} onChange={set('contract_type')} error={campos.de('contract_type')}
            options={TIPOS_DE_CONTRATO.map(k => ({ value: k, label: etiquetaDe(t, 'contrato_tipo_', k) }))} />
          {!plantilla && <>
            <Input label={t('proveedores.inicio')} type="date" value={f.start_date} onChange={set('start_date')} error={campos.de('start_date')} />
            <Input label={t('proveedores.fin')} type="date" value={f.end_date} onChange={set('end_date')} error={campos.de('end_date')} />
          </>}
          <Input label={t('proveedores.preaviso_dias')} type="number" min={0} value={f.notice_days} onChange={set('notice_days')} error={campos.de('notice_days')} />
          <Select label={t('subcontractors.moneda')} value={f.currency} placeholder={false} onChange={set('currency')} error={campos.de('currency')}
            options={(currencies.includes(f.currency) ? currencies : [f.currency, ...currencies]).map(m => ({ value: m, label: m }))} />
          <Input label={t('proveedores.minimo_comprometido')} type="number" min={0} step="0.01" value={f.committed_minimum} onChange={set('committed_minimum')} error={campos.de('committed_minimum')} />
          <Select label={t('proveedores.periodo_del_minimo')} value={f.minimum_period} onChange={set('minimum_period')} placeholder={t('proveedores.sin_periodo')}
            options={PERIODOS.filter(p => p !== 'one_time').map(p => ({ value: p, label: etiquetaDe(t, 'periodo_', p) }))} />
          <Input label={t('proveedores.tope_total')} type="number" min={0} step="0.01" value={f.total_cap} onChange={set('total_cap')} error={campos.de('total_cap')} />
          <Input label={t('proveedores.condiciones_pago')} type="number" min={0} value={f.payment_terms_days} onChange={set('payment_terms_days')} error={campos.de('payment_terms_days')} />
          {!plantilla && <>
            <Input label={t('subcontractors.n_pedido_po')} value={f.po_number} onChange={set('po_number')} error={campos.de('po_number')} />
            <Input label={t('proveedores.importe_pedido')} type="number" min={0} step="0.01" value={f.po_amount} onChange={set('po_amount')} error={campos.de('po_amount')} />
            <Select label={t('proveedores.proyecto_imputacion')} value={f.project_id} onChange={set('project_id')} placeholder={t('proveedores.sin_proyecto')}
              options={proyectos.map(p => ({ value: p.id, label: `${p.code} — ${p.name}` }))} />
            <Select label={t('externos.responsable_interno')} value={f.internal_owner_id} onChange={set('internal_owner_id')} placeholder={t('externos.elegir_responsable')}
              options={personas.map(p => ({ value: p.id, label: etiquetaDePersona(tApp, p) }))} />
            <Select label={t('proveedores.presupuesto')} value={f.budget_id} onChange={set('budget_id')} error={campos.de('budget_id')}
              placeholder={t('proveedores.sin_presupuesto')} hint={t('proveedores.presupuesto_d')}
              options={referencias.budgets
                .filter(b => !f.project_id || !b.project_id || b.project_id === f.project_id)
                .map(b => ({ value: b.id, label: b.label }))} />
          </>}
          <Select label={t('proveedores.centro_de_coste')} value={f.cost_center_id} onChange={set('cost_center_id')} error={campos.de('cost_center_id')}
            placeholder={t('proveedores.sin_centro_de_coste')} options={referencias.cost_centers.map(x => ({ value: x.id, label: x.label }))} />
          <Input label={t('proveedores.tope_gastos')} type="number" min={0} step="0.01" value={f.expenses_cap} onChange={set('expenses_cap')} error={campos.de('expenses_cap')} />
          <Input label={t('proveedores.documento_url')} value={f.document_url} onChange={set('document_url')} error={campos.de('document_url')} />
        </div>
        <ModosDeRelacion valor={f.modes} onChange={m => setF(x => ({ ...x, modes: m }))} />
        <Checkbox checked={f.auto_renew} onChange={v => setF(x => ({ ...x, auto_renew: v }))} label={t('proveedores.renovacion_automatica')} />
        <Checkbox checked={f.expenses_rebillable} onChange={v => setF(x => ({ ...x, expenses_rebillable: v }))} label={t('proveedores.gastos_repercutibles')} />
        <div className="ui-field">
          <label htmlFor="prv-contrato-notas" className="uiinde-estiloetiqueta">{t('subcontractors.notes')}</label>
          <Textarea id="prv-contrato-notas" value={f.notes} onChange={set('notes')} inputClassName="prv-textarea" />
        </div>
        <div className="u-actions-8">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => guardar.mutate()} loading={guardar.isPending} disabled={!f.title.trim() || guardar.isPending}>{t('common.save')}</Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Línea de precio ──────────────────────────────────────────────────────────
type TramoForm = { from: string; to: string; price: string }

/** Tramos del formulario → cuerpo (`[{from, to, price}]`, sin filas vacías). */
export function tramosDeFormulario(tramos: TramoForm[]): TramoDePrecio[] {
  return tramos
    .filter(x => x.price.trim() !== '')
    .map(x => ({ from: numeroONull(x.from) ?? 0, to: numeroONull(x.to), price: numeroONull(x.price) ?? 0 }))
}

/** Qué campos pide cada modelo de cobro. */
export const CAMPOS_DEL_MODELO: Record<ModeloDeCobro, { tarifa?: boolean; paquete?: boolean; servicio?: boolean; unidad?: boolean; cuota?: boolean; precio?: boolean; tramos?: boolean }> = {
  per_resource: { tarifa: true, unidad: true, precio: true, tramos: true },
  fixed_price: { paquete: true, precio: true },
  per_unit: { servicio: true, unidad: true, precio: true, tramos: true },
  subscription: { servicio: true, unidad: true, cuota: true, precio: true },
  expense: {},
  bonus: { servicio: true, precio: true },
}

export function FormularioDeLinea({ contratoId, linea, tarifas = [], servicios = [], paquetes = [], onClose }: {
  contratoId: string; linea?: LineaDePrecio | null; tarifas?: SubTarifa[]; servicios?: ServicioDeProveedor[]; paquetes?: PaqueteDeTrabajo[]; onClose: () => void
}) {
  const t = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const campos = useErroresDeCampo()
  const unidades = useCatalogo('supplier-billing-units')
  const sinUnidades = !unidades.cargando && unidades.opciones.length === 0
  const l = linea
  const [f, setF] = useState({
    model: (l?.model || 'per_resource') as ModeloDeCobro, description: texto(l?.description), unit: texto(l?.unit),
    rate_id: texto(l?.rate_id), service_id: texto(l?.service_id), work_package_id: texto(l?.work_package_id),
    unit_price: texto(l?.unit_price), period: texto(l?.period), included_units: texto(l?.included_units),
    overage_price: texto(l?.overage_price), min_amount: texto(l?.min_amount), max_amount: texto(l?.max_amount),
    valid_from: texto(l?.valid_from), valid_until: texto(l?.valid_until),
  })
  const [tramos, setTramos] = useState<TramoForm[]>((l?.tiers || []).map(x => ({ from: texto(x.from), to: texto(x.to), price: texto(x.price) })))
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => { campos.limpiar(k); setF(x => ({ ...x, [k]: e.target.value })) }
  const pide = CAMPOS_DEL_MODELO[f.model]

  const guardar = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: () => {
      const d: LineaIn = {
        model: f.model, description: textoONull(f.description), unit: pide.unidad ? (f.unit || null) : (f.model === 'expense' ? 'expense' : null),
        rate_id: pide.tarifa ? (f.rate_id || null) : null, service_id: pide.servicio ? (f.service_id || null) : null,
        work_package_id: pide.paquete ? (f.work_package_id || null) : null, unit_price: numeroONull(f.unit_price),
        period: (f.period || null) as LineaIn['period'], included_units: pide.cuota ? numeroONull(f.included_units) : null,
        overage_price: pide.cuota ? numeroONull(f.overage_price) : null, tiers: pide.tramos ? tramosDeFormulario(tramos) : [],
        min_amount: numeroONull(f.min_amount), max_amount: numeroONull(f.max_amount),
        valid_from: fecha(f.valid_from), valid_until: fecha(f.valid_until),
      }
      return l ? proveedoresApi.editarLinea(l.id, d) : proveedoresApi.crearLinea(contratoId, d)
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['suppliers'] }); toast.success(t('proveedores.linea_guardada')); onClose() },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) },
  })

  return (
    <Modal open title={l ? t('proveedores.editar_linea') : t('proveedores.nueva_linea')} onClose={onClose} width={640}>
      <div className="u-stack-8">
        <div className="prv-rejilla">
          <Select label={t('proveedores.modelo_de_cobro')} value={f.model} placeholder={false} onChange={set('model')} error={campos.de('model')}
            hint={t(`proveedores.modelo_${f.model}_d`)}
            options={MODELOS.map(m => ({ value: m, label: etiquetaDe(t, 'modelo_', m) }))} />
          <Input label={t('subcontractors.descripcion')} value={f.description} onChange={set('description')} error={campos.de('description')} />
          {pide.tarifa && (
            <Select label={t('proveedores.perfil_tarifa')} value={f.rate_id} onChange={set('rate_id')} error={campos.de('rate_id')} placeholder={t('proveedores.elegir')}
              options={tarifas.map(r => ({ value: r.id, label: r.description || r.id }))} />
          )}
          {pide.paquete && (
            <Select label={t('proveedores.paquete')} value={f.work_package_id} onChange={set('work_package_id')} error={campos.de('work_package_id')} placeholder={t('proveedores.elegir')}
              options={paquetes.map(w => ({ value: w.id, label: w.title }))} />
          )}
          {pide.servicio && (
            <Select label={t('proveedores.servicio')} value={f.service_id} onChange={set('service_id')} error={campos.de('service_id')} placeholder={t('proveedores.todos_los_servicios')}
              options={servicios.map(s => ({ value: s.id, label: s.name }))} />
          )}
          {pide.unidad && (
            <Select label={t('proveedores.unidad')} value={f.unit} onChange={set('unit')} error={campos.de('unit')} placeholder={t('proveedores.elegir')}
              options={unidades.opciones} />
          )}
          {f.model !== 'expense' && (
            <Input label={f.model === 'bonus' ? t('proveedores.importe_bonus') : pide.cuota ? t('proveedores.cuota') : f.model === 'fixed_price' ? t('proveedores.precio_cerrado') : t('proveedores.precio_unitario')}
              type="number" min={0} step="0.01" value={f.unit_price} onChange={set('unit_price')} error={campos.de('unit_price')} />
          )}
          <Select label={t('proveedores.periodo')} value={f.period} onChange={set('period')} placeholder={t('proveedores.sin_periodo')}
            options={PERIODOS.map(p => ({ value: p, label: etiquetaDe(t, 'periodo_', p) }))} />
          {pide.cuota && <>
            <Input label={t('proveedores.unidades_incluidas')} type="number" min={0} value={f.included_units} onChange={set('included_units')} error={campos.de('included_units')} />
            <Input label={t('proveedores.precio_exceso')} type="number" min={0} step="0.01" value={f.overage_price} onChange={set('overage_price')} error={campos.de('overage_price')} />
          </>}
          <Input label={t('proveedores.minimo_periodo')} type="number" min={0} step="0.01" value={f.min_amount} onChange={set('min_amount')} error={campos.de('min_amount')} />
          <Input label={t('proveedores.tope_periodo')} type="number" min={0} step="0.01" value={f.max_amount} onChange={set('max_amount')} error={campos.de('max_amount')} />
          <Input label={t('proveedores.vigente_desde')} type="date" value={f.valid_from} onChange={set('valid_from')} error={campos.de('valid_from')} />
          <Input label={t('proveedores.vigente_hasta')} type="date" value={f.valid_until} onChange={set('valid_until')} error={campos.de('valid_until')} />
        </div>
        {pide.unidad && sinUnidades && <FaltaConfigurar mensaje={t('proveedores.falta_unidades')} />}
        {pide.tramos && (
          <div className="u-stack-8">
            <div className="prv-cabecera-item">
              <span className="uiinde-estiloetiqueta">{t('proveedores.tramos')}</span>
              <Button size="xs" variant="ghost" icon={<Plus size={13} />} onClick={() => setTramos(x => [...x, { from: x.length ? x[x.length - 1].to : '0', to: '', price: '' }])}>{t('proveedores.anadir_tramo')}</Button>
            </div>
            <p className="u-text3-xs">{t('proveedores.tramos_d')}</p>
            {tramos.map((x, i) => (
              <div key={i} className="prv-tramo">
                <Input label={t('proveedores.tramo_desde')} type="number" min={0} value={x.from} onChange={e => setTramos(ts => ts.map((y, j) => j === i ? { ...y, from: e.target.value } : y))} />
                <Input label={t('proveedores.tramo_hasta')} type="number" min={0} value={x.to} onChange={e => setTramos(ts => ts.map((y, j) => j === i ? { ...y, to: e.target.value } : y))} />
                <Input label={t('proveedores.tramo_precio')} type="number" min={0} step="0.01" value={x.price} onChange={e => setTramos(ts => ts.map((y, j) => j === i ? { ...y, price: e.target.value } : y))} />
                <IconButton onClick={() => setTramos(ts => ts.filter((_, j) => j !== i))} ariaLabel={t('proveedores.quitar_tramo')} title={t('proveedores.quitar_tramo')}><X size={14} aria-hidden /></IconButton>
              </div>
            ))}
          </div>
        )}
        <div className="u-actions-8">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => guardar.mutate()} loading={guardar.isPending} disabled={guardar.isPending}>{t('common.save')}</Button>
        </div>
      </div>
    </Modal>
  )
}

/** Lista de líneas de un contrato (o plantilla) con editar/quitar. */
export function ListaDeLineas({ contrato, editable, onEditar }: {
  contrato: ContratoDeProveedor; editable: boolean; onEditar: (l: LineaDePrecio) => void
}) {
  const t = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const fmtMoneda = useFormatoMoneda()
  const unidades = useCatalogo('supplier-billing-units')
  const borrar = useMutation({
    mutationFn: (id: string) => proveedoresApi.borrarLinea(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['suppliers'] }),
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  // 23-11-2026: quitar una línea de precio pide confirmación.
  const quitarLinea = (id: string) => openConfirmGlobal({
    message: t('proveedores.confirmar_quitar_linea'), confirmLabel: t('proveedores.quitar_linea'), danger: true,
    onConfirm: () => borrar.mutate(id),
  })
  const lineas = contrato.lines || []
  if (!lineas.length) return <p className="u-text3-xs prv-mt">{t('proveedores.sin_lineas')}</p>
  return (
    <div className="prv-lineas">
      {lineas.map(l => (
        <div key={l.id} className="prv-linea">
          <div className="u-min0">
            <strong>{etiquetaDe(t, 'modelo_', l.model)}</strong>
            {l.description ? ` · ${l.description}` : ''}
            {l.rate_description ? ` · ${l.rate_description}` : ''}
            <div className="u-text3-xs">
              {[
                l.unit_price != null && `${fmtMoneda(l.unit_price, { moneda: contrato.currency })}${l.unit ? ` / ${unidades.etiqueta(l.unit)}` : ''}`,
                l.period && etiquetaDe(t, 'periodo_', l.period),
                l.included_units != null && t('proveedores.incluidas_n', { n: fmtNumber(l.included_units, 0) }),
                l.overage_price != null && t('proveedores.exceso_n', { importe: fmtMoneda(l.overage_price, { moneda: contrato.currency }) }),
                l.tiers.length > 0 && t('proveedores.n_tramos', { n: l.tiers.length }),
                l.min_amount != null && t('proveedores.minimo_n', { importe: fmtMoneda(l.min_amount, { moneda: contrato.currency }) }),
                l.max_amount != null && t('proveedores.tope_n', { importe: fmtMoneda(l.max_amount, { moneda: contrato.currency }) }),
                (l.valid_from || l.valid_until) && `${fmtDate(l.valid_from)} – ${fmtDate(l.valid_until)}`,
              ].filter(Boolean).join(' · ')}
            </div>
          </div>
          {editable && (
            <div className="u-row-6">
              <IconButton variante="caja" onClick={() => onEditar(l)} ariaLabel={t('proveedores.editar_linea')} title={t('proveedores.editar_linea')}><Pencil size={14} aria-hidden /></IconButton>
              <IconButton variante="caja" tono="peligro" onClick={() => quitarLinea(l.id)} ariaLabel={t('proveedores.quitar_linea')} title={t('proveedores.quitar_linea')}><Trash2 size={14} aria-hidden /></IconButton>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

/**
 * Ficha del proveedor → Servicios gestionados (19-11-2026).
 *
 * Cada servicio (SOC, service desk externalizado, infraestructura, nóminas…)
 * se enlaza a su cola del service desk (`/sd/groups`): los tickets de esa cola
 * son su consumo y su SLA. Plazos propios de respuesta y resolución, objetivo
 * de cumplimiento, KPIs, unidades contratadas, créditos y bonus por SLA.
 *
 * Migración 191: elemento del catálogo del service desk y contrato ALM (UC)
 * elegibles con datos reales (`useReferencias`); fuente de medición de los
 * servicios cobrados por dispositivo/usuario (manual, CMDB con filtros y vista
 * previa, o sistema externo por API/importación), «Medir ahora» e importación
 * de recuentos pegados desde un CSV o la exportación de un SIEM.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Activity, FileBarChart, Gauge, Layers, Pencil, Plus, RefreshCw, Square, Upload, X } from 'lucide-react'
import { Button, Card, Checkbox, EmptyState, IconButton, Input, KpiCard, Modal, Select, Spinner, useErroresDeCampo, Textarea } from '../../components/ui'
import StatusBadge from '../../components/ui/StatusBadge'
import { usePersonasInternas } from '../../components/externos/FormularioDeExterno'
import { etiquetaDePersona } from '../../components/ui/MarcaExterno'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { useToast } from '../../context/ToastContext'
import { useAppT } from '../../i18n/AppLangContext'
import { sdGroupsApi } from '../../services/api'
import { proveedoresApi } from '../../services/api/proveedores'
import type { ConfigDeMedicion, FuenteDeMedicion, KpiDeServicio, ServicioDeProveedor, ServicioIn, VistaPreviaDeMedicion } from '../../services/api/tipos-proveedores'
import type { Subcontratista } from '../../services/api/tipos-alm'
import { useCatalogo } from '../../hooks/useCatalogo'
import { extractErr, fmtDate, fmtNumber } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { STALE_REFERENCE_DATA_MS } from '../../constants/timings'
import { AGREGACIONES, CUENTAS_DE_MEDICION, FRECUENCIAS, FUENTES_DE_MEDICION, admiteMedicion, filasDeRecuento, mesDe, numeroONull, texto, textoONull } from './logica'
import { FaltaConfigurar, etiquetaDe, usePermisosDeProveedores, useProyectosActivos, useReferencias, useT } from './comunes'
import { FormularioDeInforme, InformesDeProveedor } from './PestanaPaquetes'

type Fila = Record<string, string>

/** Editor de filas sencillo (KPIs, créditos, bonus). */
function Filas({ titulo, ayuda, filas, columnas, nueva, onChange }: {
  titulo: string; ayuda?: string; filas: Fila[]; columnas: { k: string; etiqueta: string; tipo?: 'number' | 'text'; opciones?: { value: string; label: string }[] }[]
  nueva: Fila; onChange: (f: Fila[]) => void
}) {
  const t = useT()
  return (
    <div className="u-stack-8">
      <div className="prv-cabecera-item">
        <span className="uiinde-estiloetiqueta">{titulo}</span>
        <Button size="xs" variant="ghost" icon={<Plus size={13} />} onClick={() => onChange([...filas, { ...nueva }])}>{t('proveedores.anadir')}</Button>
      </div>
      {ayuda && <p className="u-text3-xs">{ayuda}</p>}
      {filas.map((f, i) => (
        <div key={i} className="prv-tramo">
          {columnas.map(c => c.opciones ? (
            <Select key={c.k} label={c.etiqueta} value={f[c.k]} placeholder={false} options={c.opciones}
              onChange={e => onChange(filas.map((x, j) => j === i ? { ...x, [c.k]: e.target.value } : x))} />
          ) : (
            <Input key={c.k} label={c.etiqueta} type={c.tipo || 'text'} value={f[c.k]}
              onChange={e => onChange(filas.map((x, j) => j === i ? { ...x, [c.k]: e.target.value } : x))} />
          ))}
          <IconButton onClick={() => onChange(filas.filter((_, j) => j !== i))} ariaLabel={t('proveedores.quitar')} title={t('proveedores.quitar')}><X size={14} aria-hidden /></IconButton>
        </div>
      ))}
    </div>
  )
}

/** Fuente de medición de dispositivos/usuarios (CMDB con filtros o sistema externo) con vista previa. */
function FuenteDeMedicionCampos({ fuente, config, unidad, onFuente, onConfig }: {
  fuente: FuenteDeMedicion; config: ConfigDeMedicion; unidad: string; onFuente: (f: FuenteDeMedicion) => void; onConfig: (c: ConfigDeMedicion) => void
}) {
  const t = useT()
  const toast = useToast()
  const referencias = useReferencias()
  const proyectos = useProyectosActivos()
  const [prueba, setPrueba] = useState<VistaPreviaDeMedicion | null>(null)
  const probar = useMutation({
    mutationFn: () => proveedoresApi.vistaPreviaDeMedicion(fuente, config, unidad).then(r => r.data),
    onSuccess: setPrueba,
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const cambiar = (k: keyof ConfigDeMedicion, v: unknown) => { setPrueba(null); onConfig({ ...config, [k]: v }) }
  const habilitada = admiteMedicion(unidad)
  return (
    <div className="u-stack-8 prv-bloque">
      <span className="uiinde-estiloetiqueta">{t('proveedores.medicion')}</span>
      <p className="u-text3-xs">{t('proveedores.medicion_d')}</p>
      <Select label={t('proveedores.fuente_de_medicion')} value={habilitada ? fuente : 'manual'} placeholder={false} disabled={!habilitada}
        hint={habilitada ? t(`proveedores.fuente_${fuente}_d`) : t('proveedores.medicion_solo_recuento')}
        onChange={e => { setPrueba(null); onFuente(e.target.value as FuenteDeMedicion) }}
        options={FUENTES_DE_MEDICION.map(x => ({ value: x, label: etiquetaDe(t, 'fuente_', x) }))} />
      {habilitada && fuente === 'cmdb' && <>
        <div className="u-stack-4">
          <span className="u-text2-sm">{t('proveedores.medicion_tipos_ci')}</span>
          <div className="prv-insignias">
            {referencias.ci_types.map(tipo => (
              <Checkbox key={tipo} checked={(config.ci_types || []).includes(tipo)} label={conRespaldoCI(t, tipo)}
                onChange={v => cambiar('ci_types', v ? [...(config.ci_types || []), tipo] : (config.ci_types || []).filter(x => x !== tipo))} />
            ))}
          </div>
        </div>
        <div className="prv-rejilla">
          {referencias.ci_classes.length > 0 && (
            <Select label={t('proveedores.medicion_clase_ci')} value={(config.ci_classes || [])[0] || ''} placeholder={t('proveedores.todas')}
              onChange={e => cambiar('ci_classes', e.target.value ? [e.target.value] : [])}
              options={referencias.ci_classes.map(c => ({ value: c.id, label: c.label }))} />
          )}
          <Input label={t('proveedores.medicion_entorno')} value={config.environment || ''} onChange={e => cambiar('environment', e.target.value || null)} />
          <Input label={t('proveedores.medicion_fabricante')} value={config.vendor || ''} onChange={e => cambiar('vendor', e.target.value || null)} />
          <Input label={t('proveedores.medicion_ubicacion')} value={config.location || ''} onChange={e => cambiar('location', e.target.value || null)} />
          {proyectos.length > 0 && (
            <Select label={t('subcontractors.col_proyecto')} value={config.project_id || ''} placeholder={t('proveedores.todos')}
              onChange={e => cambiar('project_id', e.target.value || null)} options={proyectos.map(p => ({ value: p.id, label: `${p.code} — ${p.name}` }))} />
          )}
          <Select label={t('proveedores.medicion_software')} value={config.software_product_id || ''} placeholder={t('proveedores.medicion_sin_software')}
            hint={t('proveedores.medicion_software_d')} onChange={e => cambiar('software_product_id', e.target.value || null)}
            options={referencias.software_products.map(p => ({ value: p.id, label: p.label }))} />
          <Input label={t('proveedores.medicion_visto_dias')} type="number" min={1} value={texto(config.seen_within_days)}
            onChange={e => cambiar('seen_within_days', numeroONull(e.target.value))} />
          <Select label={t('proveedores.medicion_cuenta')} value={config.count || (unidad === 'user_month' ? 'owners' : 'devices')} placeholder={false}
            onChange={e => cambiar('count', e.target.value)} options={CUENTAS_DE_MEDICION.map(x => ({ value: x, label: etiquetaDe(t, 'cuenta_', x) }))} />
          <Select label={t('proveedores.medicion_agregacion')} value={config.aggregation || 'last'} placeholder={false}
            onChange={e => cambiar('aggregation', e.target.value)} options={AGREGACIONES.map(x => ({ value: x, label: etiquetaDe(t, 'agregacion_', x) }))} />
        </div>
        <div className="u-row-center-8">
          <Button size="xs" variant="secondary" icon={<Gauge size={13} />} loading={probar.isPending} onClick={() => probar.mutate()}>{t('proveedores.medicion_probar')}</Button>
          {prueba && (
            <span className="u-text2-sm">
              {t('proveedores.medicion_contaria', { n: fmtNumber(prueba.quantity, 0) })}
              {prueba.detail.examples?.length ? ` · ${prueba.detail.examples.join(', ')}` : ''}
            </span>
          )}
        </div>
      </>}
      {habilitada && fuente === 'external' && (
        <div className="prv-rejilla">
          <Input label={t('proveedores.medicion_sistema')} required value={config.system || ''} hint={t('proveedores.medicion_sistema_d')}
            onChange={e => cambiar('system', e.target.value)} />
          <Select label={t('proveedores.medicion_agregacion')} value={config.aggregation || 'last'} placeholder={false}
            onChange={e => cambiar('aggregation', e.target.value)} options={AGREGACIONES.map(x => ({ value: x, label: etiquetaDe(t, 'agregacion_', x) }))} />
        </div>
      )}
    </div>
  )
}

/** Etiqueta de un tipo de elemento de la CMDB (`sd.ci_type_<tipo>` si existe; si no, la clave). */
function conRespaldoCI(t: ReturnType<typeof useT>, tipo: string) {
  const clave = `proveedores.ci_tipo_${tipo}`
  const r = t(clave)
  return r === clave ? tipo : r
}

/** Recuentos pegados desde un CSV o la exportación de un SIEM (servicio;fecha;cantidad;sistema). */
function ImportarRecuentos({ sub, servicios, onClose }: { sub: Subcontratista; servicios: ServicioDeProveedor[]; onClose: () => void }) {
  const t = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const [pegado, setPegado] = useState('')
  const externos = servicios.filter(s => s.metering_source === 'external')
  const { filas, malas } = filasDeRecuento(pegado, externos)
  const importar = useMutation({
    mutationFn: () => proveedoresApi.importarRecuentos(sub.id, filas).then(r => r.data),
    onSuccess: r => {
      qc.invalidateQueries({ queryKey: ['suppliers'] })
      if (r.failed) toast.error(t('proveedores.recuentos_con_fallos', { ok: r.imported, mal: r.failed }))
      else { toast.success(t('proveedores.recuentos_importados', { n: r.imported })); onClose() }
    },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  return (
    <Modal open title={t('proveedores.importar_recuentos')} onClose={onClose} width={620}>
      <div className="u-stack-8">
        <p className="u-text2-sm">{t('proveedores.importar_recuentos_d')}</p>
        {externos.length === 0 ? <p className="u-text3-xs">{t('proveedores.sin_servicios_externos')}</p> : (
          <p className="u-text3-xs">{t('proveedores.servicios_externos_n', { lista: externos.map(s => s.name).join(', ') })}</p>
        )}
        <div className="ui-field">
          <label htmlFor="prv-recuentos" className="uiinde-estiloetiqueta">{t('proveedores.recuentos')}</label>
          <Textarea id="prv-recuentos" value={pegado} onChange={e => setPegado(e.target.value)} placeholder={'service;2026-11-30;250;SIEM'} inputClassName="prv-textarea" />
        </div>
        {malas.length > 0 && <div className="prv-aviso prv-aviso--peligro">{t('proveedores.lineas_no_validas', { lineas: malas.join(', ') })}</div>}
        <div className="u-actions-8">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button icon={<Upload size={14} />} disabled={!filas.length || importar.isPending} loading={importar.isPending} onClick={() => importar.mutate()}>
            {t('proveedores.importar_n', { n: filas.length })}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function FormularioDeServicio({ sub, servicio, onClose }: { sub: Subcontratista; servicio: ServicioDeProveedor | null; onClose: () => void }) {
  const t = useT()
  const tApp = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const campos = useErroresDeCampo()
  const tipos = useCatalogo('supplier-service-types')
  const unidades = useCatalogo('supplier-billing-units')
  const { personas } = usePersonasInternas()
  const { data: colas = [] } = useQuery({ queryKey: ['sd-groups'], queryFn: () => sdGroupsApi.list().then(r => r.data), staleTime: STALE_REFERENCE_DATA_MS, retry: false })
  const { data: contratos = [] } = useQuery({ queryKey: ['suppliers', 'contracts', sub.id], queryFn: () => proveedoresApi.contratos(sub.id).then(r => r.data) })
  const referencias = useReferencias({ subId: sub.id })
  const s = servicio
  const [fuente, setFuente] = useState<FuenteDeMedicion>(s?.metering_source || 'manual')
  const [medicion, setMedicion] = useState<ConfigDeMedicion>(s?.metering_config || {})
  const [f, setF] = useState({
    service_item_id: texto(s?.service_item_id), alm_contract_id: texto(s?.alm_contract_id),
    service_type: texto(s?.service_type), name: texto(s?.name), scope: texto(s?.scope), contract_id: texto(s?.contract_id),
    start_date: texto(s?.start_date), end_date: texto(s?.end_date), agent_group_id: texto(s?.agent_group_id),
    sla_response_hours: texto(s?.sla_response_hours), sla_resolution_hours: texto(s?.sla_resolution_hours),
    sla_target_pct: texto(s?.sla_target_pct), contracted_units: texto(s?.contracted_units), unit: texto(s?.unit),
    reporting_frequency: texto(s?.reporting_frequency), internal_owner_id: texto(s?.internal_owner_id), notes: texto(s?.notes),
  })
  const [kpis, setKpis] = useState<Fila[]>((s?.kpis || []).map(k => ({ key: k.key, label: k.label, target: texto(k.target), unit: texto(k.unit), direction: k.direction })))
  const [creditos, setCreditos] = useState<Fila[]>((s?.credit_rules || []).map(r => ({ below_pct: texto(r.below_pct), credit_pct: texto(r.credit_pct) })))
  const [bonus, setBonus] = useState<Fila[]>((s?.bonus_rules || []).map(r => ({ above_pct: texto(r.above_pct), bonus_pct: texto(r.bonus_pct) })))
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => { campos.limpiar(k); setF(x => ({ ...x, [k]: e.target.value })) }

  const guardar = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: () => {
      const d: ServicioIn = {
        service_type: f.service_type, name: f.name.trim(), scope: textoONull(f.scope), contract_id: f.contract_id || null,
        start_date: f.start_date || null, end_date: f.end_date || null, agent_group_id: f.agent_group_id || null,
        sla_response_hours: numeroONull(f.sla_response_hours), sla_resolution_hours: numeroONull(f.sla_resolution_hours),
        sla_target_pct: numeroONull(f.sla_target_pct), contracted_units: numeroONull(f.contracted_units), unit: f.unit || null,
        reporting_frequency: (f.reporting_frequency || null) as ServicioIn['reporting_frequency'],
        internal_owner_id: f.internal_owner_id || null, notes: textoONull(f.notes),
        service_item_id: f.service_item_id || null, alm_contract_id: f.alm_contract_id || null,
        metering_source: admiteMedicion(f.unit) ? fuente : 'manual',
        metering_config: admiteMedicion(f.unit) && fuente !== 'manual' ? medicion : {},
        kpis: kpis.filter(k => k.key.trim() && k.label.trim()).map(k => ({
          key: k.key.trim(), label: k.label.trim(), target: numeroONull(k.target), unit: textoONull(k.unit), direction: (k.direction === 'lower' ? 'lower' : 'higher') as KpiDeServicio['direction'],
        })),
        credit_rules: creditos.filter(r => r.below_pct && r.credit_pct).map(r => ({ below_pct: Number(r.below_pct), credit_pct: Number(r.credit_pct) })),
        bonus_rules: bonus.filter(r => r.above_pct && r.bonus_pct).map(r => ({ above_pct: Number(r.above_pct), bonus_pct: Number(r.bonus_pct) })),
      }
      return s ? proveedoresApi.editarServicio(s.id, d) : proveedoresApi.crearServicio(sub.id, d)
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['suppliers'] }); toast.success(t('proveedores.servicio_guardado')); onClose() },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) },
  })

  return (
    <Modal open title={s ? t('proveedores.editar_servicio') : t('proveedores.nuevo_servicio')} onClose={onClose} width={720}>
      <div className="u-stack-8">
        <div className="prv-rejilla">
          <Select label={t('proveedores.tipo_de_servicio')} required value={f.service_type} onChange={set('service_type')} error={campos.de('service_type')} placeholder={t('proveedores.elegir')} options={tipos.opciones} />
          <Input label={t('proveedores.nombre')} required value={f.name} onChange={set('name')} error={campos.de('name')} />
          <Select label={t('proveedores.cola_sd')} value={f.agent_group_id} onChange={set('agent_group_id')} error={campos.de('agent_group_id')}
            placeholder={t('proveedores.sin_cola')} hint={t('proveedores.cola_sd_d')} options={colas.map(g => ({ value: g.id, label: g.name }))} />
          <Select label={t('proveedores.contrato')} value={f.contract_id} onChange={set('contract_id')} placeholder={t('proveedores.sin_contrato')}
            options={contratos.map(c => ({ value: c.id, label: c.title }))} />
          <Select label={t('proveedores.elemento_catalogo_sd')} value={f.service_item_id} onChange={set('service_item_id')} error={campos.de('service_item_id')}
            placeholder={t('proveedores.sin_elemento_catalogo')} hint={t('proveedores.elemento_catalogo_sd_d')}
            options={referencias.service_items.map(x => ({ value: x.id, label: x.label }))} />
          <Select label={t('proveedores.contrato_alm')} value={f.alm_contract_id} onChange={set('alm_contract_id')} error={campos.de('alm_contract_id')}
            placeholder={t('proveedores.sin_contrato_alm')} hint={t('proveedores.contrato_alm_d')}
            options={referencias.alm_contracts.map(x => ({ value: x.id, label: x.same_vendor ? `${x.label} ★` : x.label }))} />
          <Input label={t('proveedores.inicio')} type="date" value={f.start_date} onChange={set('start_date')} error={campos.de('start_date')} />
          <Input label={t('proveedores.fin')} type="date" value={f.end_date} onChange={set('end_date')} error={campos.de('end_date')} />
          <Input label={t('proveedores.sla_respuesta_h')} type="number" min={0} step="0.25" value={f.sla_response_hours} onChange={set('sla_response_hours')} error={campos.de('sla_response_hours')} />
          <Input label={t('proveedores.sla_resolucion_h')} type="number" min={0} step="0.25" value={f.sla_resolution_hours} onChange={set('sla_resolution_hours')} error={campos.de('sla_resolution_hours')} />
          <Input label={t('proveedores.objetivo_sla_pct')} type="number" min={0} max={100} step="0.1" value={f.sla_target_pct} onChange={set('sla_target_pct')} error={campos.de('sla_target_pct')} />
          <Select label={t('proveedores.frecuencia_informe')} value={f.reporting_frequency} onChange={set('reporting_frequency')} placeholder={t('proveedores.sin_informes')}
            options={FRECUENCIAS.map(x => ({ value: x, label: etiquetaDe(t, 'frecuencia_', x) }))} />
          <Input label={t('proveedores.unidades_contratadas')} type="number" min={0} value={f.contracted_units} onChange={set('contracted_units')} error={campos.de('contracted_units')} />
          <Select label={t('proveedores.unidad')} value={f.unit} onChange={set('unit')} placeholder={t('proveedores.elegir')} options={unidades.opciones} />
          <Select className="prv-completo" label={t('externos.responsable_interno')} value={f.internal_owner_id} onChange={set('internal_owner_id')} placeholder={t('externos.elegir_responsable')}
            options={personas.map(p => ({ value: p.id, label: etiquetaDePersona(tApp, p) }))} />
        </div>
        {!tipos.cargando && tipos.opciones.length === 0 && <FaltaConfigurar mensaje={t('proveedores.falta_tipos_de_servicio')} />}
        <FuenteDeMedicionCampos fuente={fuente} config={medicion} unidad={f.unit} onFuente={setFuente} onConfig={setMedicion} />
        <div className="ui-field">
          <label htmlFor="prv-servicio-alcance" className="uiinde-estiloetiqueta">{t('proveedores.alcance')}</label>
          <Textarea id="prv-servicio-alcance" value={f.scope} onChange={set('scope')} inputClassName="prv-textarea" />
        </div>
        <Filas titulo={t('proveedores.kpis')} filas={kpis} onChange={setKpis} nueva={{ key: '', label: '', target: '', unit: '', direction: 'higher' }}
          columnas={[
            { k: 'label', etiqueta: t('proveedores.nombre') }, { k: 'key', etiqueta: t('proveedores.clave') },
            { k: 'target', etiqueta: t('proveedores.objetivo'), tipo: 'number' },
            { k: 'direction', etiqueta: t('proveedores.sentido'), opciones: [{ value: 'higher', label: t('proveedores.sentido_higher') }, { value: 'lower', label: t('proveedores.sentido_lower') }] },
          ]} />
        <Filas titulo={t('proveedores.creditos')} ayuda={t('proveedores.creditos_d')} filas={creditos} onChange={setCreditos} nueva={{ below_pct: '', credit_pct: '' }}
          columnas={[{ k: 'below_pct', etiqueta: t('proveedores.por_debajo_pct'), tipo: 'number' }, { k: 'credit_pct', etiqueta: t('proveedores.credito_pct'), tipo: 'number' }]} />
        <Filas titulo={t('proveedores.bonus')} ayuda={t('proveedores.bonus_d')} filas={bonus} onChange={setBonus} nueva={{ above_pct: '', bonus_pct: '' }}
          columnas={[{ k: 'above_pct', etiqueta: t('proveedores.por_encima_pct'), tipo: 'number' }, { k: 'bonus_pct', etiqueta: t('proveedores.bonus_pct'), tipo: 'number' }]} />
        <div className="u-actions-8">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => guardar.mutate()} loading={guardar.isPending} disabled={!f.name.trim() || !f.service_type || guardar.isPending}>{t('common.save')}</Button>
        </div>
      </div>
    </Modal>
  )
}

/** SLA del periodo de un servicio (tickets de su cola). */
function SlaDelPeriodo({ servicio, onClose }: { servicio: ServicioDeProveedor; onClose: () => void }) {
  const t = useT()
  const mes = mesDe()
  const [desde, setDesde] = useState(mes.desde)
  const [hasta, setHasta] = useState(mes.hasta)
  const { data, isLoading } = useQuery({
    queryKey: ['suppliers', 'sla', servicio.id, desde, hasta],
    queryFn: () => proveedoresApi.slaDeServicio(servicio.id, { desde, hasta }).then(r => r.data),
    enabled: !!desde && !!hasta,
  })
  const pct = (v: number | null | undefined) => (v == null ? '—' : `${fmtNumber(v, 1)}%`)
  return (
    <Modal open title={t('proveedores.sla_del_periodo')} subtitle={servicio.name} onClose={onClose} width={620}>
      <div className="u-stack-8">
        <div className="prv-rejilla">
          <Input label={t('proveedores.desde')} type="date" value={desde} onChange={e => setDesde(e.target.value)} />
          <Input label={t('proveedores.hasta')} type="date" value={hasta} onChange={e => setHasta(e.target.value)} />
        </div>
        {isLoading ? <Spinner /> : data && (
          <>
            <div className="ds-grid-stats">
              <KpiCard icon={<Activity size={16} />} label={t('proveedores.tickets_resueltos')} value={`${data.tickets_resolved} / ${data.tickets_total}`} />
              <KpiCard icon={<Gauge size={16} />} label={t('proveedores.cumplimiento_sla')} value={pct(data.compliance_pct)}
                sub={data.target_pct != null ? t('proveedores.objetivo_n', { pct: fmtNumber(data.target_pct, 1) }) : undefined}
                danger={data.met === false} />
              <KpiCard label={t('proveedores.respuesta_en_plazo')} value={pct(data.response_met_pct)} sub={t('proveedores.incumplimientos_n', { n: data.breaches_response })} />
              <KpiCard label={t('proveedores.resolucion_en_plazo')} value={pct(data.resolution_met_pct)} sub={t('proveedores.incumplimientos_n', { n: data.breaches_resolution })} />
            </div>
            {data.met != null && (
              <StatusBadge kind={data.met ? 'success' : 'danger'} caps={false}>{data.met ? t('proveedores.sla_cumplido') : t('proveedores.sla_incumplido')}</StatusBadge>
            )}
          </>
        )}
      </div>
    </Modal>
  )
}

export default function PestanaServicios({ sub }: { sub: Subcontratista }) {
  const t = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const { gestionar } = usePermisosDeProveedores()
  const tipos = useCatalogo('supplier-service-types')
  const unidades = useCatalogo('supplier-billing-units')
  const [editando, setEditando] = useState<ServicioDeProveedor | null | 'nuevo'>(null)
  const [sla, setSla] = useState<ServicioDeProveedor | null>(null)
  const [informe, setInforme] = useState<ServicioDeProveedor | null>(null)
  const [importando, setImportando] = useState(false)
  const { data: servicios = [], isLoading } = useQuery({
    queryKey: ['suppliers', 'services', sub.id],
    queryFn: () => proveedoresApi.servicios(sub.id).then(r => r.data),
  })
  const { data: colas = [] } = useQuery({ queryKey: ['sd-groups'], queryFn: () => sdGroupsApi.list().then(r => r.data), staleTime: STALE_REFERENCE_DATA_MS, retry: false })
  const nombreDeCola = (id: string | null) => (id ? colas.find(g => g.id === id)?.name || id : null)
  const terminar = useMutation({
    mutationFn: (id: string) => proveedoresApi.terminarServicio(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['suppliers'] }); toast.success(t('proveedores.servicio_terminado')) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const medir = useMutation({
    mutationFn: (id: string) => proveedoresApi.medirAhora(id).then(r => r.data),
    onSuccess: r => { qc.invalidateQueries({ queryKey: ['suppliers'] }); toast.success(t('proveedores.medido_n', { n: fmtNumber(r.usage.quantity, 0) })) },
    onError: (e: unknown) => { qc.invalidateQueries({ queryKey: ['suppliers'] }); toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) },
  })

  if (isLoading) return <Spinner />
  return (
    <div>
      {gestionar && (
        <div className="sub-toolbar-end">
          {servicios.some(s => s.metering_source === 'external') && (
            <Button size="sm" variant="secondary" icon={<Upload size={14} />} onClick={() => setImportando(true)}>{t('proveedores.importar_recuentos')}</Button>
          )}
          <Button size="sm" icon={<Plus size={14} />} onClick={() => setEditando('nuevo')}>{t('proveedores.nuevo_servicio')}</Button>
        </div>
      )}
      {servicios.length === 0 ? (
        <EmptyState icon={<Layers size={28} />} title={t('proveedores.sin_servicios')} description={t('proveedores.sin_servicios_d')} />
      ) : (
        <div className="u-stack-8">
          {servicios.map(s => (
            <Card key={s.id} className="sub-item">
              <div className="prv-cabecera-item">
                <div className="u-min0">
                  <div className="u-row-center-8">
                    <span className="prv-titulo-item">{s.name}</span>
                    <StatusBadge kind="neutral" caps={false}>{tipos.etiqueta(s.service_type)}</StatusBadge>
                    <StatusBadge kind={s.status === 'active' ? 'success' : s.status === 'paused' ? 'warning' : 'neutral'} caps={false}>{etiquetaDe(t, 'servicio_estado_', s.status)}</StatusBadge>
                  </div>
                  <div className="prv-sub">
                    {[
                      nombreDeCola(s.agent_group_id) ? t('proveedores.cola_n', { cola: nombreDeCola(s.agent_group_id) || '' }) : t('proveedores.sin_cola'),
                      s.sla_response_hours != null && t('proveedores.respuesta_n_h', { h: fmtNumber(s.sla_response_hours, 2) }),
                      s.sla_resolution_hours != null && t('proveedores.resolucion_n_h', { h: fmtNumber(s.sla_resolution_hours, 2) }),
                      s.sla_target_pct != null && t('proveedores.objetivo_n', { pct: fmtNumber(s.sla_target_pct, 1) }),
                      s.contracted_units != null && `${fmtNumber(s.contracted_units, 0)} ${s.unit ? unidades.etiqueta(s.unit) : ''}`.trim(),
                      s.kpis.length > 0 && t('proveedores.n_kpis', { n: s.kpis.length }),
                      s.credit_rules.length > 0 && t('proveedores.con_creditos'),
                      s.bonus_rules.length > 0 && t('proveedores.con_bonus'),
                      (s.start_date || s.end_date) && `${fmtDate(s.start_date)} – ${fmtDate(s.end_date)}`,
                    ].filter(Boolean).join(' · ')}
                  </div>
                  {s.metering_source !== 'manual' && (
                    <div className="u-text3-xs">
                      {[
                        t('proveedores.medido_con', { fuente: etiquetaDe(t, 'fuente_', s.metering_source) }),
                        s.metering_last_quantity != null && t('proveedores.ultimo_recuento', { n: fmtNumber(s.metering_last_quantity, 0), fecha: fmtDate(s.metering_last_at) }),
                      ].filter(Boolean).join(' · ')}
                      {s.metering_last_error && <div className="prv-aviso prv-aviso--peligro">{t('proveedores.medicion_error', { error: s.metering_last_error })}</div>}
                    </div>
                  )}
                </div>
                <div className="u-row-6">
                  <Button size="xs" variant="secondary" icon={<Gauge size={13} />} onClick={() => setSla(s)}>{t('proveedores.ver_sla')}</Button>
                  {gestionar && s.metering_source === 'cmdb' && s.status === 'active' && (
                    <Button size="xs" variant="secondary" icon={<RefreshCw size={13} />} loading={medir.isPending && medir.variables === s.id}
                      onClick={() => medir.mutate(s.id)}>{t('proveedores.medir_ahora')}</Button>
                  )}
                  {gestionar && <Button size="xs" variant="secondary" icon={<FileBarChart size={13} />} onClick={() => setInforme(s)}>{t('proveedores.informe')}</Button>}
                  {gestionar && <Button size="xs" variant="secondary" icon={<Pencil size={13} />} onClick={() => setEditando(s)}>{t('subcontractors.edit')}</Button>}
                  {gestionar && s.status !== 'ended' && (
                    <Button size="xs" variant="ghost" className="sub-borrar" icon={<Square size={13} />}
                      onClick={() => openConfirmGlobal({ message: t('proveedores.terminar_servicio_confirmar', { nombre: s.name }), danger: true, onConfirm: () => terminar.mutate(s.id) })}>
                      {t('proveedores.terminar')}
                    </Button>
                  )}
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
      {editando && <FormularioDeServicio sub={sub} servicio={editando === 'nuevo' ? null : editando} onClose={() => setEditando(null)} />}
      <InformesDeProveedor sub={sub} de="service" nombres={Object.fromEntries(servicios.map(s => [s.id, s.name]))} />
      {sla && <SlaDelPeriodo servicio={sla} onClose={() => setSla(null)} />}
      {informe && <FormularioDeInforme sub={sub} servicioId={informe.id} onClose={() => setInforme(null)} />}
      {importando && <ImportarRecuentos sub={sub} servicios={servicios} onClose={() => setImportando(false)} />}
    </div>
  )
}

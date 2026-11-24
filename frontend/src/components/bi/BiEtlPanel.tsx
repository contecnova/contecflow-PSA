/**
 * Conectores ETL de BI (revisión 2026-11): la única lista de conectores de la
 * plataforma de datos. Cada conector trae sus campos y entidades del servidor
 * (`GET /bi/etl/connectors`), así que el formulario no sabe nada de cada
 * proveedor. «Probar» conecta sin guardar; «Sincronizar» corre ahora y enseña
 * el resultado real; el error de la última pasada queda a la vista.
 */
import React, { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, CheckCircle, ChevronDown, ChevronUp, Database, FlaskConical, Plug, Plus, RefreshCw, Settings2, Trash2 } from 'lucide-react'
import { biEtlApi } from '../../services/api'
import type { ConectorEtl, FichaDeConectorEtl } from '../../services/api/tipos-bi'
import { useAppT } from '../../i18n/AppLangContext'
import { Button, Card, EmptyState, IconButton, Modal, Spinner, Select, Input } from '../ui'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { useToast } from '../../context/ToastContext'
import { confirmar } from '../../context/ConfirmContext'
import { extractErr, fmtDateTime, fmtNumber } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import './BiEtlPanel.css'
import { chipColor } from '../../utils/estilos'

type Ficha = FichaDeConectorEtl
type Conector = ConectorEtl

const COLOR: Record<Conector['status'], string> = { connected: 'var(--success)', error: 'var(--danger)', disconnected: 'var(--text-3)' }
/** Nombre legible de un campo del conector: traducido si existe `etl.campo.<clave>`; si no, la clave sin guiones bajos. */
const legible = (clave: string) => { const s = clave.replace(/_/g, ' '); return s.charAt(0).toUpperCase() + s.slice(1) }
/** Formulario de campos declarados: el mismo para configurar un conector y para dar de alta una fuente REST. */
function Campos({ ficha, valores, puestos, onChange }: { ficha: Ficha; valores: Record<string, string>; puestos: string[]; onChange: (k: string, v: string) => void }) {
  const t = useAppT()
  return (
    <div className="bietpa-grid-1">
      {ficha.campos.map(c => (
        <label key={c.clave} className="bietpa-grid-2">
          <span>{etiquetaCodigo(t, 'etl.campo', c.clave, legible(c.clave))}</span>
          <Input type={c.secreto ? 'password' : 'text'} aria-label={etiquetaCodigo(t, 'etl.campo', c.clave, legible(c.clave))} autoComplete="off" value={valores[c.clave] ?? ''} placeholder={c.secreto && puestos.includes(c.clave) ? t('etl.secreto_puesto') : ''} onChange={e => onChange(c.clave, e.target.value)} className="bietpa-campo" />
        </label>
      ))}
    </div>
  )
}

function Configurar({ conector, onClose }: { conector: Conector; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [valores, setValores] = useState<Record<string, string>>({ ...conector.config })
  const [entidad, setEntidad] = useState(conector.entity)
  const [guardando, setGuardando] = useState(false)
  const guardar = async () => {
    setGuardando(true)
    try {
      await biEtlApi.configure(conector.connector_id, { entity: entidad, config: valores })
      toast.success(t('etl.guardado'))
      qc.invalidateQueries({ queryKey: ['bi-etl-connectors'] })
      onClose()
    } catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) } finally { setGuardando(false) }
  }
  return (
    <Modal open onClose={onClose} size="lg" title={t('etl.configurar_x', { x: conector.nombre })} subtitle={t('etl.secretos_ayuda')}>
      <div className="bietpa-grid-3">
        {conector.entidades.length > 1 && (
          <label className="bietpa-grid-2">
            {t('etl.entidad')}
            <Select suelto className="bietpa-campo" value={entidad} onChange={e => setEntidad(e.target.value)} placeholder={false}>
              {conector.entidades.map(e => <option key={e} value={e}>{etiquetaCodigo(t, 'etl.entidad_tipo', e, legible(e))}</option>)}
            </Select>
          </label>
        )}
        <Campos ficha={conector} valores={valores} puestos={conector.secretos_puestos} onChange={(k, v) => setValores(x => ({ ...x, [k]: v }))} />
        <div className="u-actions-8">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button loading={guardando} onClick={guardar}>{t('common.save')}</Button>
        </div>
      </div>
    </Modal>
  )
}

function NuevaFuente({ ficha, onClose }: { ficha: Ficha; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [nombre, setNombre] = useState('')
  const [valores, setValores] = useState<Record<string, string>>({ method: 'GET' })
  const [guardando, setGuardando] = useState(false)
  const crear = async () => {
    setGuardando(true)
    try {
      await biEtlApi.crearFuente({ nombre, config: valores })
      toast.success(t('etl.fuente_creada'))
      qc.invalidateQueries({ queryKey: ['bi-etl-connectors'] })
      onClose()
    } catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) } finally { setGuardando(false) }
  }
  return (
    <Modal open onClose={onClose} size="lg" title={t('etl.nueva_fuente')} subtitle={t('etl.nueva_fuente_ayuda')}>
      <div className="bietpa-grid-3">
        <label className="bietpa-grid-2">
          {t('etl.nombre')}
          <Input aria-label={t('etl.nombre')} value={nombre} onChange={e => setNombre(e.target.value)} inputClassName="bietpa-campo" />
        </label>
        <Campos ficha={ficha} valores={valores} puestos={[]} onChange={(k, v) => setValores(x => ({ ...x, [k]: v }))} />
        <div className="u-actions-8">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button loading={guardando} disabled={!nombre.trim() || !valores.endpoint_url} onClick={crear}>{t('etl.crear')}</Button>
        </div>
      </div>
    </Modal>
  )
}

function Tarjeta({ c, onConfigurar }: { c: Conector; onConfigurar: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [ocupado, setOcupado] = useState<'' | 'test' | 'sync' | 'toggle'>('')
  const [verLog, setVerLog] = useState(false)
  const log = useQuery({
    queryKey: ['bi-etl-log', c.connector_id],
    queryFn: () => biEtlApi.getLog(c.connector_id).then(r => r.data),
    enabled: verLog,
  })
  const refrescar = () => {
    qc.invalidateQueries({ queryKey: ['bi-etl-connectors'] })
    qc.invalidateQueries({ queryKey: ['bi-etl-log', c.connector_id] })
  }
  const accion = async (tipo: 'test' | 'sync' | 'toggle') => {
    setOcupado(tipo)
    try {
      if (tipo === 'toggle') {
        await biEtlApi.configure(c.connector_id, { enabled: !c.enabled })
      } else {
        // Probar devuelve `records`; sincronizar, `records_ingested`.
        const r = tipo === 'test'
          ? await biEtlApi.test(c.connector_id).then(x => ({ ok: x.data.ok, n: x.data.records ?? 0, error: x.data.error }))
          : await biEtlApi.sync(c.connector_id).then(x => ({ ok: x.data.ok, n: x.data.records_ingested, error: x.data.error }))
        const n = fmtNumber(r.n, 0)
        if (r.ok) toast.success(t(tipo === 'test' ? 'etl.prueba_ok' : 'etl.sync_ok', { n }))
        else toast.error(t('etl.fallo', { error: r.error ?? '' }))
      }
      refrescar()
    } catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) } finally { setOcupado('') }
  }
  const quitar = async () => {
    try { await biEtlApi.borrarFuente(c.connector_id); refrescar() } catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) }
  }
  const Icono = c.status === 'error' ? AlertCircle : CheckCircle
  return (
    <div className="bietpa-grid-4">
      <div className="bietpa-row-1">
        <Icono size={16} className="u-dato-color u-shrink0" style={{ '--dato-color': COLOR[c.status] } as React.CSSProperties} />
        <div className="u-flex1-min0">
          <div className="u-text1-sm-600">{c.nombre}</div>
          <div className="u-text3-xs">{etiquetaCodigo(t, 'etl.entidad_tipo', c.entity, legible(c.entity))}</div>
        </div>
        <span className="chip-dato" style={chipColor(COLOR[c.status])}>{t(`etl.estado_${c.status}`)}</span>
      </div>
      {c.falta && <div className="bietpa-txt-1">{t('etl.falta_paquete')} <code className="u-mono">{c.falta}</code></div>}
      {c.last_error && <div role="alert" className="bietpa-txt-2">{c.last_error}</div>}
      <div className="bietpa-row-2">
        <span>{t('etl.ultimo_sync')}: <span className="u-text2">{c.last_sync_at ? fmtDateTime(c.last_sync_at) : t('etl.nunca')}</span></span>
        <span>{t('etl.registros')}: <span className="bietpa-txt-3">{fmtNumber(c.last_records ?? 0, 0)}</span></span>
      </div>
      <div className="u-wrap-6">
        <Button size="xs" variant={c.enabled ? 'secondary' : 'primary'} loading={ocupado === 'toggle'} disabled={!c.enabled && !!c.falta} onClick={() => accion('toggle')}>{t(c.enabled ? 'etl.desactivar' : 'etl.activar')}</Button>
        <Button size="xs" variant="secondary" icon={<Settings2 size={12} />} onClick={onConfigurar}>{t('etl.configurar')}</Button>
        <Button size="xs" variant="secondary" icon={<FlaskConical size={12} />} loading={ocupado === 'test'} onClick={() => accion('test')}>{t('etl.probar')}</Button>
        <Button size="xs" variant="secondary" icon={<RefreshCw size={12} />} loading={ocupado === 'sync'} disabled={!c.enabled} title={c.enabled ? undefined : t('etl.activalo_antes')} onClick={() => accion('sync')}>{t('etl.sincronizar')}</Button>
        {c.personalizado && <IconButton variante="caja" tono="peligro" ariaLabel={t('etl.quitar')} onClick={async () => {
          // 23-11-2026: confirmación única (ConfirmContext), antes `ui/Confirm`.
          if (await confirmar({ title: t('etl.quitar_x', { x: c.nombre }), message: t('etl.quitar_ayuda'), danger: true })) quitar()
        }}><Trash2 size={13} /></IconButton>}
        <Button size="xs" variant="ghost" icon={verLog ? <ChevronUp size={12} /> : <ChevronDown size={12} />} onClick={() => setVerLog(v => !v)}>
          {t(verLog ? 'etl.ocultar_registro' : 'etl.ver_registro')}
        </Button>
      </div>
      {verLog && (
        <div className="bietpa-grid-5">
          {log.isLoading ? <Spinner size={16} /> : (log.data?.entries ?? []).length === 0
            ? <div className="bietpa-txt-4">{t('etl.registro_vacio')}</div>
            : log.data!.entries.map((e, i) => (
              <div key={i} className="bietpa-row-4">
                <span className="chip-dato" style={chipColor(e.ok ? 'var(--success)' : 'var(--danger)')}>{t(e.ok ? 'etl.ok' : 'etl.error')}</span>
                <span className="bietpa-box-1">{e.finished_at ? fmtDateTime(e.finished_at) : ''}</span>
                <span className="bietpa-box-2">{e.ok ? t('etl.n_registros', { n: fmtNumber(e.records_ingested ?? 0, 0) }) : e.error}</span>
              </div>
            ))}
        </div>
      )}
    </div>
  )
}

export default function BiEtlPanel() {
  const t = useAppT()
  const qc = useQueryClient()
  const [configurando, setConfigurando] = useState<Conector | null>(null)
  const [nueva, setNueva] = useState(false)
  const { data, isLoading } = useQuery({
    queryKey: ['bi-etl-connectors'],
    queryFn: () => biEtlApi.listConnectors().then(r => r.data),
  })
  const conectores = data?.connectors ?? []
  const activos = conectores.filter(c => c.enabled).length
  const conError = conectores.filter(c => c.status === 'error').length
  // Activos primero: con 21 proveedores, lo que la empresa usa no puede quedar al final.
  const orden = [...conectores].sort((a, b) => Number(b.enabled) - Number(a.enabled) || Number(b.personalizado) - Number(a.personalizado) || Number(!b.falta) - Number(!a.falta))

  return (
    <Card className="bietlpan-sx1">
      <div className="bietpa-row-5">
        <div className="u-row-center-8">
          <Database size={18} className="bietlpan-sx2" />
          <h2 className="bietpa-box-3">{t('etl.titulo')}</h2>
        </div>
        <div className="bietpa-row-6">
          <span className="chip-dato" style={chipColor('var(--success)')}>{t('etl.n_activos', { n: activos })}</span>
          {conError > 0 && <span className="chip-dato" style={chipColor('var(--danger)')}>{t('etl.n_con_error', { n: conError })}</span>}
          <Button size="sm" variant="ghost" icon={<RefreshCw size={13} />} onClick={() => qc.invalidateQueries({ queryKey: ['bi-etl-connectors'] })}>{t('etl.refrescar')}</Button>
          {data?.generico && <Button size="sm" icon={<Plus size={13} />} onClick={() => setNueva(true)}>{t('etl.nueva_fuente')}</Button>}
        </div>
      </div>
      {isLoading ? <div className="bietpa-row-7"><Spinner /></div>
        : conectores.length === 0 ? <EmptyState icon={<Plug size={28} />} title={t('etl.sin_conectores')} />
        : (
          <div className="bietpa-grid-6">
            {orden.map(c => <Tarjeta key={c.connector_id} c={c} onConfigurar={() => setConfigurando(c)} />)}
          </div>
        )}
      {configurando && <Configurar conector={configurando} onClose={() => setConfigurando(null)} />}
      {nueva && data?.generico && <NuevaFuente ficha={data.generico} onClose={() => setNueva(false)} />}
    </Card>
  )
}

/**
 * Conectores ETL de BI (revisión 2026-11): la única lista de conectores de la
 * plataforma de datos. Cada conector trae sus campos y entidades del servidor
 * (`GET /bi/etl/connectors`), así que el formulario no sabe nada de cada
 * proveedor. «Probar» conecta sin guardar; «Sincronizar» corre ahora y enseña
 * el resultado real; el error de la última pasada queda a la vista.
 */
import React, { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, CheckCircle, ChevronDown, ChevronUp, Database, FlaskConical, Plus, RefreshCw, Settings2, Trash2 } from 'lucide-react'
import { biEtlApi } from '../../services/api'
import { useAppT } from '../../i18n/AppLangContext'
import { Button, Card, Confirm, EmptyState, Modal, Spinner } from '../ui'
import { useToast } from '../../context/ToastContext'
import { extractErr, localeActivo } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'

interface Campo { clave: string; secreto: boolean }
interface Ficha { etiqueta?: string; falta?: string | null; campos: Campo[]; entidades: string[] }
interface Conector extends Ficha {
  connector_id: string
  nombre: string
  personalizado: boolean
  enabled: boolean
  status: 'connected' | 'error' | 'disconnected'
  last_sync_at?: string | null
  last_records?: number
  last_error?: string | null
  entity: string
  config: Record<string, string>
  secretos_puestos: string[]
}
interface Entrada { ok: boolean; records_ingested?: number; error?: string | null; finished_at?: string | null }
interface Resultado { ok: boolean; records?: number; records_ingested?: number; error?: string }

const COLOR: Record<Conector['status'], string> = { connected: 'var(--success)', error: 'var(--danger)', disconnected: 'var(--text-3)' }
const chip = (color: string): React.CSSProperties => ({
  fontSize: 'var(--text-2xs)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color,
  background: `color-mix(in srgb, ${color} 15%, transparent)`, border: `1px solid color-mix(in srgb, ${color} 30%, transparent)`,
  borderRadius: 'var(--radius-full)', padding: '2px 9px', whiteSpace: 'nowrap',
})
const campo: React.CSSProperties = { background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 10px', color: 'var(--text-1)', fontSize: 'var(--text-sm)', fontFamily: 'inherit', width: '100%', boxSizing: 'border-box' }

/** Formulario de campos declarados: el mismo para configurar un conector y para dar de alta una fuente REST. */
function Campos({ ficha, valores, puestos, onChange }: { ficha: Ficha; valores: Record<string, string>; puestos: string[]; onChange: (k: string, v: string) => void }) {
  const t = useAppT()
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 10 }}>
      {ficha.campos.map(c => (
        <label key={c.clave} style={{ display: 'grid', gap: 4, fontSize: 'var(--text-xs)', color: 'var(--text-2)' }}>
          <span className="u-mono">{c.clave}</span>
          <input type={c.secreto ? 'password' : 'text'} autoComplete="off" style={campo} value={valores[c.clave] ?? ''}
            placeholder={c.secreto && puestos.includes(c.clave) ? t('etl.secreto_puesto') : ''}
            onChange={e => onChange(c.clave, e.target.value)} />
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
      <div style={{ display: 'grid', gap: 14 }}>
        {conector.entidades.length > 1 && (
          <label style={{ display: 'grid', gap: 4, fontSize: 'var(--text-xs)', color: 'var(--text-2)' }}>
            {t('etl.entidad')}
            <select style={campo} value={entidad} onChange={e => setEntidad(e.target.value)}>
              {conector.entidades.map(e => <option key={e} value={e}>{e}</option>)}
            </select>
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
      <div style={{ display: 'grid', gap: 14 }}>
        <label style={{ display: 'grid', gap: 4, fontSize: 'var(--text-xs)', color: 'var(--text-2)' }}>
          {t('etl.nombre')}
          <input style={campo} value={nombre} onChange={e => setNombre(e.target.value)} />
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
  const [borrar, setBorrar] = useState(false)
  const log = useQuery<{ entries: Entrada[] }>({
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
        const r = (await (tipo === 'test' ? biEtlApi.test(c.connector_id) : biEtlApi.sync(c.connector_id))).data as Resultado
        const n = (r.records ?? r.records_ingested ?? 0).toLocaleString(localeActivo())
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
    <div style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)', padding: '14px 16px', display: 'grid', gap: 10 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <Icono size={16} style={{ color: COLOR[c.status], flexShrink: 0 }} />
        <div className="u-flex1-min0">
          <div className="u-text1-sm-600">{c.nombre}</div>
          <div className="u-text3-mono-xs">{c.connector_id} · {c.entity}</div>
        </div>
        <span style={chip(COLOR[c.status])}>{t(`etl.estado_${c.status}`)}</span>
      </div>
      {c.falta && <div style={{ fontSize: 'var(--text-xs)', color: 'var(--warning)' }}>{t('etl.falta_paquete')} <code className="u-mono">{c.falta}</code></div>}
      {c.last_error && <div role="alert" style={{ fontSize: 'var(--text-xs)', color: 'var(--danger)', overflowWrap: 'anywhere' }}>{c.last_error}</div>}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 14, fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>
        <span>{t('etl.ultimo_sync')}: <span className="u-text2">{c.last_sync_at ? new Date(c.last_sync_at).toLocaleString(localeActivo()) : t('etl.nunca')}</span></span>
        <span>{t('etl.registros')}: <span style={{ color: 'var(--text-2)', fontFamily: 'var(--font-mono)' }}>{(c.last_records ?? 0).toLocaleString(localeActivo())}</span></span>
      </div>
      <div className="u-wrap-6">
        <Button size="xs" variant={c.enabled ? 'secondary' : 'primary'} loading={ocupado === 'toggle'} disabled={!c.enabled && !!c.falta} onClick={() => accion('toggle')}>{t(c.enabled ? 'etl.desactivar' : 'etl.activar')}</Button>
        <Button size="xs" variant="secondary" icon={<Settings2 size={12} />} onClick={onConfigurar}>{t('etl.configurar')}</Button>
        <Button size="xs" variant="secondary" icon={<FlaskConical size={12} />} loading={ocupado === 'test'} onClick={() => accion('test')}>{t('etl.probar')}</Button>
        <Button size="xs" variant="secondary" icon={<RefreshCw size={12} />} loading={ocupado === 'sync'} disabled={!c.enabled} title={c.enabled ? undefined : t('etl.activalo_antes')} onClick={() => accion('sync')}>{t('etl.sincronizar')}</Button>
        {c.personalizado && <Button size="xs" variant="ghost" icon={<Trash2 size={12} />} title={t('etl.quitar')} onClick={() => setBorrar(true)}>{''}</Button>}
        <button type="button" onClick={() => setVerLog(v => !v)} style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--accent)', fontSize: 'var(--text-xs)', fontFamily: 'inherit', display: 'inline-flex', alignItems: 'center', gap: 4, padding: 0 }}>
          {verLog ? <ChevronUp size={12} /> : <ChevronDown size={12} />}{t(verLog ? 'etl.ocultar_registro' : 'etl.ver_registro')}
        </button>
      </div>
      {verLog && (
        <div style={{ background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: 10, maxHeight: 220, overflowY: 'auto', display: 'grid', gap: 4 }}>
          {log.isLoading ? <Spinner size={16} /> : (log.data?.entries ?? []).length === 0
            ? <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', textAlign: 'center' }}>{t('etl.registro_vacio')}</div>
            : log.data!.entries.map((e, i) => (
              <div key={i} style={{ display: 'flex', gap: 10, fontSize: 'var(--text-xs)', color: 'var(--text-2)', alignItems: 'baseline' }}>
                <span style={chip(e.ok ? 'var(--success)' : 'var(--danger)')}>{t(e.ok ? 'etl.ok' : 'etl.error')}</span>
                <span style={{ color: 'var(--text-3)', fontFamily: 'var(--font-mono)', flexShrink: 0 }}>{e.finished_at ? new Date(e.finished_at).toLocaleString(localeActivo()) : ''}</span>
                <span style={{ minWidth: 0, overflowWrap: 'anywhere' }}>{e.ok ? t('etl.n_registros', { n: (e.records_ingested ?? 0).toLocaleString(localeActivo()) }) : e.error}</span>
              </div>
            ))}
        </div>
      )}
      <Confirm open={borrar} onCancel={() => setBorrar(false)} onConfirm={() => { setBorrar(false); quitar() }}
        title={t('etl.quitar_x', { x: c.nombre })} description={t('etl.quitar_ayuda')} />
    </div>
  )
}

export default function BiEtlPanel() {
  const t = useAppT()
  const qc = useQueryClient()
  const [configurando, setConfigurando] = useState<Conector | null>(null)
  const [nueva, setNueva] = useState(false)
  const { data, isLoading } = useQuery<{ connectors: Conector[]; generico: Ficha }>({
    queryKey: ['bi-etl-connectors'],
    queryFn: () => biEtlApi.listConnectors().then(r => r.data),
  })
  const conectores = data?.connectors ?? []
  const activos = conectores.filter(c => c.enabled).length
  const conError = conectores.filter(c => c.status === 'error').length
  // Activos primero: con 21 proveedores, lo que la empresa usa no puede quedar al final.
  const orden = [...conectores].sort((a, b) => Number(b.enabled) - Number(a.enabled) || Number(b.personalizado) - Number(a.personalizado) || Number(!b.falta) - Number(!a.falta))

  return (
    <Card style={{ padding: '20px 22px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14, gap: 12, flexWrap: 'wrap' }}>
        <div className="u-row-center-8">
          <Database size={18} style={{ color: 'var(--accent)' }} />
          <h2 style={{ fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--text-1)', margin: 0 }}>{t('etl.titulo')}</h2>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          <span style={chip('var(--success)')}>{t('etl.n_activos', { n: activos })}</span>
          {conError > 0 && <span style={chip('var(--danger)')}>{t('etl.n_con_error', { n: conError })}</span>}
          <Button size="sm" variant="ghost" icon={<RefreshCw size={13} />} onClick={() => qc.invalidateQueries({ queryKey: ['bi-etl-connectors'] })}>{t('etl.refrescar')}</Button>
          {data?.generico && <Button size="sm" icon={<Plus size={13} />} onClick={() => setNueva(true)}>{t('etl.nueva_fuente')}</Button>}
        </div>
      </div>
      {isLoading ? <div style={{ display: 'flex', justifyContent: 'center', padding: 32 }}><Spinner /></div>
        : conectores.length === 0 ? <EmptyState icon="🔌" title={t('etl.sin_conectores')} />
        : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(320px, 100%), 1fr))', gap: 10 }}>
            {orden.map(c => <Tarjeta key={c.connector_id} c={c} onConfigurar={() => setConfigurando(c)} />)}
          </div>
        )}
      {configurando && <Configurar conector={configurando} onClose={() => setConfigurando(null)} />}
      {nueva && data?.generico && <NuevaFuente ficha={data.generico} onClose={() => setNueva(false)} />}
    </Card>
  )
}

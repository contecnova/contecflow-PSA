/**
 * Conexiones de escaneo de la CMDB de software (19-11-2026): SSH (Linux),
 * WinRM (Windows) e inventario por API (EDR/RMM).
 *
 * - `ConexionesDeEscaneo`: alta, edición, prueba y borrado. Va en
 *   Configuración → Software y vulnerabilidades (admin; las credenciales se
 *   guardan cifradas y no se vuelven a mostrar: vacío = no cambia,
 *   «Quitar» = `'__borrar__'`).
 * - `PanelDeEscaneos`: lo operativo en la CMDB (`software.gestionar`):
 *   último estado, próxima ejecución, «Escanear ahora» y el historial.
 * - `AvisoDeConfiguracion`: aviso contextual cuando algo no funciona por falta
 *   de configuración. Los módulos no llevan botón «Configurar»: el enlace a
 *   Configuración solo sale a quien tiene `software.config`.
 */
import { useState } from 'react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, History, Play, PlugZap, Plus, Radar, Trash2 } from 'lucide-react'
import { useAppT } from '../../../i18n/AppLangContext'
import { useToast } from '../../../context/ToastContext'
import { useAuth } from '../../../context/AuthContext'
import { confirmar } from '../../../context/ConfirmContext'
import { fmtDateTime } from '../../../utils/helpers'
import { etiquetaCodigo } from '../../../i18n/etiquetaCodigo'
import { cmdbSoftwareApi } from '../../../services/api/cmdbSoftware'
import type { ConexionDeEscaneo, ResultadoDeEscaneo, TipoDeConexion } from '../../../services/api/cmdbSoftware'
import { Button, Checkbox, EmptyState, IconButton, Modal, Section, Select, Spinner, StatusBadge, TablaSimple, Textarea, Input } from '../../ui'
import { ListaKv, useErr, useEtiquetaSw, useMetaSw } from './comun'
import '../../servicedesk/sdMercado.css'
import './software.css'

const TIPOS: TipoDeConexion[] = ['sw_ssh', 'sw_winrm', 'sw_api',
  // Índice de riesgo (22-11-2026): consolas de vulnerabilidades de terceros e intentos de explotación.
  'sw_vm_trendmicro', 'sw_vm_defender', 'sw_vm_qualys', 'sw_vm_tenable', 'sw_vm_rapid7', 'sw_siem']
const BOOLEANOS = new Set(['accept_unknown_host_keys', 'sudo', 'read_configs', 'all_packages', 'create_cis', 'use_ssl', 'verify_ssl', 'include_services', 'complete', 'with_kb'])
const NUMEROS = new Set(['port', 'timeout', 'max_pages', 'days'])
const TEXTOS_LARGOS = new Set(['hosts', 'private_key', 'known_hosts'])
const ENUMERADOS: Record<string, 'transport' | 'environments' | 'exposures'> = { transport: 'transport', environment: 'environments', exposure: 'exposures' }
const TRANSPORTES = ['ntlm', 'kerberos', 'basic']
const BORRAR = '__borrar__'
const INTERVALO_MIN = 15

/** Texto de una clave que puede no existir: vacío si falta. */
function useTextoOpcional() {
  const t = useAppT()
  return (clave: string) => { const r = t(clave); return r === clave ? '' : r }
}

/** Aviso contextual: lo que falta y, a quien puede, el enlace a Configuración. */
export function AvisoDeConfiguracion({ children, tono = 'warning' }: { children: ReactNode; tono?: 'warning' | 'danger' }) {
  const t = useAppT()
  const { puede } = useAuth()
  return (
    <div className={`sw-aviso-config sw-aviso-config--${tono}`} role="status">
      <AlertTriangle size={14} />
      <div className="u-flex1-min0">
        {children}{' '}
        {puede('software.config')
          ? <Link to="/settings/cmdb-software" className="sw-aviso-config__enlace">{t('sw.ir_a_configuracion')}</Link>
          : <span className="u-text3-xs">{t('sw.pide_a_la_direccion')}</span>}
      </div>
    </div>
  )
}

// ── Configuración: alta, edición y prueba ────────────────────────────────────

export function ConexionesDeEscaneo() {
  const t = useAppT()
  const e = useEtiquetaSw()
  const toast = useToast()
  const qc = useQueryClient()
  const err = useErr()
  const [editando, setEditando] = useState<ConexionDeEscaneo | 'nueva' | null>(null)
  const { data, isLoading } = useQuery({ queryKey: ['sw', 'conexiones'], queryFn: cmdbSoftwareApi.conexiones })
  const refrescar = () => qc.invalidateQueries({ queryKey: ['sw'] })
  const probar = useMutation({
    mutationFn: cmdbSoftwareApi.probarConexion,
    onSuccess: r => r.ok
      ? toast.success(t('sw.esc_prueba_ok', { host: r.host ?? (r.devices != null ? t('sw.esc_n_equipos', { n: r.devices }) : '') }))
      : toast.error(t('sw.esc_prueba_mal', { detalle: r.error ?? '' })),
    onError: err,
  })
  const borrar = useMutation({ mutationFn: cmdbSoftwareApi.borrarConexion, onSuccess: refrescar, onError: err })
  return (
    <Section title={t('sw.esc_conexiones')} subtitle={t('sw.esc_conexiones_desc')}
      actions={<Button size="sm" icon={<Plus size={14} />} onClick={() => setEditando('nueva')}>{t('sw.esc_nueva')}</Button>}>
      <div className="u-stack-12">
        <div className="sw-aviso">{t('sw.esc_aviso_credenciales')}</div>
        {isLoading ? <Spinner /> : (data ?? []).length === 0 ? <EmptyState icon={<Radar size={28} />} title={t('sw.esc_sin_conexiones')} /> : (
          <ul className="sdm-list">
            {(data ?? []).map(c => (
              <li key={c.id} className="sdm-list__item">
                <div className="u-flex1-min0 u-stack-6">
                  <div className="u-wrap-8">
                    <span className="u-text1-sm-600">{c.name}</span>
                    <StatusBadge caps={false}>{e('tipo_conexion', c.type)}</StatusBadge>
                    <StatusBadge kind={c.is_active ? 'success' : 'neutral'} caps={false}>{t(c.is_active ? 'sw.esc_activa' : 'sw.esc_apagada')}</StatusBadge>
                    {c.last_run_status && <EstadoDeEjecucion estado={c.last_run_status} />}
                  </div>
                  <div className="u-text3-xs">{t('sw.esc_cada_min', { n: c.scan_interval_minutes })} · {t('sw.esc_ultima')}: {fmtDateTime(c.last_run_at)} · {t('sw.esc_proxima')}: {fmtDateTime(c.next_run_at)}</div>
                </div>
                <div className="u-actions-8">
                  <Button size="xs" variant="secondary" icon={<PlugZap size={12} />} loading={probar.isPending && probar.variables === c.id} onClick={() => probar.mutate(c.id)}>{t('sw.cfg_probar')}</Button>
                  <Button size="xs" variant="ghost" onClick={() => setEditando(c)}>{t('sw.editar')}</Button>
                  <IconButton ariaLabel={t('sw.borrar')} onClick={async () => { if (await confirmar({ message: t('sw.esc_borrar_confirmar', { nombre: c.name }), danger: true })) borrar.mutate(c.id) }}><Trash2 size={14} /></IconButton>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
      {editando && <ConexionModal inicial={editando === 'nueva' ? null : editando} onClose={() => setEditando(null)} onSaved={() => { setEditando(null); refrescar() }} />}
    </Section>
  )
}

function ConexionModal({ inicial, onClose, onSaved }: { inicial: ConexionDeEscaneo | null; onClose: () => void; onSaved: () => void }) {
  const t = useAppT()
  const e = useEtiquetaSw()
  const ayuda = useTextoOpcional()
  const toast = useToast()
  const err = useErr()
  const meta = useMetaSw()
  const campos = useQuery({ queryKey: ['sw', 'campos-conexion'], queryFn: cmdbSoftwareApi.camposDeConexion })
  const [nombre, setNombre] = useState(inicial?.name ?? '')
  const [tipo, setTipo] = useState<TipoDeConexion>(inicial?.type ?? 'sw_ssh')
  const [intervalo, setIntervalo] = useState(inicial?.scan_interval_minutes ?? 1440)
  const [activa, setActiva] = useState(inicial?.is_active ?? true)
  const [config, setConfig] = useState<Record<string, unknown>>({ ...(inicial?.config ?? {}) })
  const [secretos, setSecretos] = useState<Record<string, string>>({})
  const puestos = new Set(inicial?.secrets_set ?? [])
  const lista = campos.data?.[tipo] ?? []
  const etiqueta = (k: string) => etiquetaCodigo(t, 'sw.campo', k)
  const datos = (extra?: Record<string, string>) => {
    const permitidas = new Set(lista.map(c => c.key))
    const conf = Object.fromEntries(Object.entries(config).filter(([k]) => permitidas.has(k)))
    const sec = Object.fromEntries(Object.entries({ ...secretos, ...extra }).filter(([k, v]) => permitidas.has(k) && v))
    return { name: nombre.trim(), type: tipo, config: { ...conf, ...sec }, scan_interval_minutes: intervalo, is_active: activa }
  }
  const guardar = useMutation({
    mutationFn: () => (inicial ? cmdbSoftwareApi.editarConexion(inicial.id, datos()) : cmdbSoftwareApi.crearConexion(datos())),
    onSuccess: () => { toast.success(t('sw.guardado')); onSaved() }, onError: err,
  })
  const quitar = useMutation({
    mutationFn: (k: string) => cmdbSoftwareApi.editarConexion(inicial!.id, { config: { [k]: BORRAR } }),
    onSuccess: () => { toast.success(t('sw.guardado')); onSaved() }, onError: err,
  })
  const opciones = (k: string) => {
    const fuente = ENUMERADOS[k]
    if (fuente === 'transport') return TRANSPORTES.map(v => <option key={v} value={v}>{e('transporte', v)}</option>)
    const valores = fuente === 'environments' ? meta.data?.environments : meta.data?.exposures
    return (valores ?? []).map(v => <option key={v} value={v}>{e(fuente === 'environments' ? 'entorno' : 'expo', v)}</option>)
  }
  const campo = (k: string, secreto: boolean) => {
    const texto = ayuda(`sw.ayuda_campo.${k}`)
    const pie = texto ? <span className="u-text3-xs">{texto}</span> : null
    if (BOOLEANOS.has(k)) {
      return <div key={k} className="sdm-field"><Checkbox checked={!!config[k]} onChange={v => setConfig({ ...config, [k]: v })} label={etiqueta(k)} ayuda={texto || undefined} /></div>
    }
    if (secreto) {
      return (
        <label key={k} className="sdm-field"><span>{etiqueta(k)}{puestos.has(k) && <> <StatusBadge kind="success" caps={false}>{t('sw.esc_puesta')}</StatusBadge></>}</span>
          {k === 'private_key'
            ? <Textarea rows={4} autoComplete="off" value={secretos[k] ?? ''} placeholder={puestos.has(k) ? t('sw.cfg_puesta_no_cambia') : ''} onChange={ev => setSecretos({ ...secretos, [k]: ev.target.value })} inputClassName="u-mono" />
            : <Input type="password" autoComplete="off" value={secretos[k] ?? ''} placeholder={puestos.has(k) ? t('sw.cfg_puesta_no_cambia') : ''} onChange={ev => setSecretos({ ...secretos, [k]: ev.target.value })} />}
          {pie}
          {inicial && puestos.has(k) && <span><Button size="xs" variant="ghost" loading={quitar.isPending && quitar.variables === k} onClick={() => quitar.mutate(k)}>{t('sw.cfg_quitar')}</Button></span>}
        </label>
      )
    }
    if (ENUMERADOS[k]) {
      return (
        <label key={k} className="sdm-field"><span>{etiqueta(k)}</span>
          <Select suelto placeholder={false} value={String(config[k] ?? '')} onChange={ev => setConfig({ ...config, [k]: ev.target.value || null })}>
            <option value="">{t('sw.esc_por_defecto')}</option>{opciones(k)}
          </Select>{pie}</label>
      )
    }
    if (NUMEROS.has(k)) {
      return (
        <label key={k} className="sdm-field"><span>{etiqueta(k)}</span>
          <Input type="number" min={1} value={config[k] == null ? '' : String(config[k])} onChange={ev => setConfig({ ...config, [k]: ev.target.value === '' ? null : Number(ev.target.value) })} />{pie}</label>
      )
    }
    if (TEXTOS_LARGOS.has(k)) {
      return (
        <label key={k} className="sdm-field sw-campo-ancho"><span>{etiqueta(k)}</span>
          <Textarea rows={k === 'hosts' ? 2 : 3} value={config[k] == null ? '' : Array.isArray(config[k]) ? (config[k] as unknown[]).join(', ') : String(config[k])} onChange={ev => setConfig({ ...config, [k]: ev.target.value })} inputClassName="u-mono" />{pie}</label>
      )
    }
    return (
      <label key={k} className="sdm-field"><span>{etiqueta(k)}</span>
        <Input value={config[k] == null ? '' : String(config[k])} onChange={ev => setConfig({ ...config, [k]: ev.target.value })} inputClassName="u-mono" />{pie}</label>
    )
  }
  return (
    <Modal open size="lg" onClose={onClose} title={inicial ? t('sw.esc_editar') : t('sw.esc_nueva')}>
      <div className="u-stack-12">
        <div className="sdm-form">
          <Input label={t('sw.col_nombre')} value={nombre} onChange={ev => setNombre(ev.target.value)} />
          <label className="sdm-field"><span>{t('sw.tipo')}</span>
            <Select suelto placeholder={false} value={tipo} disabled={!!inicial} onChange={ev => setTipo(ev.target.value as TipoDeConexion)}>
              {TIPOS.map(x => <option key={x} value={x}>{e('tipo_conexion', x)}</option>)}
            </Select></label>
          <label className="sdm-field"><span>{t('sw.esc_intervalo')}</span>
            <Input type="number" min={INTERVALO_MIN} value={intervalo} onChange={ev => setIntervalo(Math.max(INTERVALO_MIN, Number(ev.target.value) || INTERVALO_MIN))} />
            <span className="u-text3-xs">{t('sw.esc_intervalo_ayuda')}</span></label>
          <div className="sdm-field"><Checkbox checked={activa} onChange={setActiva} label={t('sw.esc_activa')} /></div>
        </div>
        <div className="u-text3-xs">{t(`sw.esc_tipo_ayuda_${tipo}`)}</div>
        {campos.isLoading ? <Spinner size={16} /> : <div className="sdm-form">{lista.map(c => campo(c.key, c.secret))}</div>}
        {config.accept_unknown_host_keys === true && <AvisoSimple>{t('sw.esc_aviso_huellas')}</AvisoSimple>}
        <div className="u-text3-xs">{t('sw.esc_aviso_credenciales')}</div>
        <div className="u-actions-10">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button loading={guardar.isPending} disabled={nombre.trim().length < 2} onClick={() => guardar.mutate()}>{t('common.save')}</Button>
        </div>
      </div>
    </Modal>
  )
}

function AvisoSimple({ children }: { children: ReactNode }) {
  return <div className="sw-aviso-config sw-aviso-config--warning" role="status"><AlertTriangle size={14} /><div className="u-flex1-min0">{children}</div></div>
}

function EstadoDeEjecucion({ estado }: { estado: string }) {
  const e = useEtiquetaSw()
  return <StatusBadge kind={estado === 'ok' ? 'success' : estado === 'error' ? 'danger' : estado === 'partial' ? 'warning' : 'info'} caps={false}>{e('ejec', estado)}</StatusBadge>
}

// ── Operativo: escanear ahora e historial ────────────────────────────────────

export function PanelDeEscaneos() {
  const t = useAppT()
  const e = useEtiquetaSw()
  const qc = useQueryClient()
  const err = useErr()
  const [resultado, setResultado] = useState<{ nombre: string; r: ResultadoDeEscaneo } | null>(null)
  const [historial, setHistorial] = useState<ConexionDeEscaneo | null>(null)
  const { data, isLoading } = useQuery({ queryKey: ['sw', 'conexiones'], queryFn: cmdbSoftwareApi.conexiones })
  const escanear = useMutation({
    mutationFn: (c: ConexionDeEscaneo) => cmdbSoftwareApi.escanear(c.id).then(r => ({ nombre: c.name, r })),
    onSuccess: x => { setResultado(x); qc.invalidateQueries({ queryKey: ['sw'] }) },
    onError: err,
  })
  const conexiones = data ?? []
  const conError = conexiones.filter(c => c.last_run_status === 'error')
  return (
    <Section title={t('sw.esc_titulo')} subtitle={t('sw.esc_titulo_desc')}>
      <div className="u-stack-12">
        {isLoading ? <Spinner size={16} /> : conexiones.length === 0
          ? <AvisoDeConfiguracion>{t('sw.esc_sin_conexiones_aviso')}</AvisoDeConfiguracion>
          : <>
            {conError.map(c => <UltimoError key={c.id} conexion={c} />)}
            <TablaSimple etiqueta={t('sw.esc_titulo')} densidad="compacta">
              <thead><tr><th>{t('sw.col_nombre')}</th><th>{t('sw.tipo')}</th><th>{t('sw.estado')}</th><th>{t('sw.esc_ultima')}</th><th>{t('sw.esc_proxima')}</th><th><span className="u-sr-only">{t('sw.acciones')}</span></th></tr></thead>
              <tbody>{conexiones.map(c => (
                <tr key={c.id}>
                  <td>{c.name}{!c.is_active && <> <StatusBadge caps={false}>{t('sw.esc_apagada')}</StatusBadge></>}</td>
                  <td>{e('tipo_conexion', c.type)}</td>
                  <td>{c.last_run_status ? <EstadoDeEjecucion estado={c.last_run_status} /> : <span className="u-text3-xs">{t('sw.nunca')}</span>}</td>
                  <td>{fmtDateTime(c.last_run_at)}</td>
                  <td>{c.is_active ? fmtDateTime(c.next_run_at) : '—'}</td>
                  <td><div className="u-row-center-6">
                    <Button size="xs" variant="secondary" icon={<Play size={12} />} loading={escanear.isPending && escanear.variables?.id === c.id} disabled={escanear.isPending}
                      onClick={() => escanear.mutate(c)}>{t('sw.esc_escanear')}</Button>
                    <Button size="xs" variant="ghost" icon={<History size={12} />} onClick={() => setHistorial(c)}>{t('sw.esc_ejecuciones')}</Button>
                  </div></td>
                </tr>
              ))}</tbody>
            </TablaSimple>
          </>}
      </div>
      {resultado && <ResumenDeEscaneo nombre={resultado.nombre} r={resultado.r} onClose={() => setResultado(null)} />}
      {historial && <HistorialDeEscaneo conexion={historial} onClose={() => setHistorial(null)} />}
    </Section>
  )
}

/** Aviso de una conexión que falló, con el error de su última ejecución. */
function UltimoError({ conexion }: { conexion: ConexionDeEscaneo }) {
  const t = useAppT()
  const { data } = useQuery({ queryKey: ['sw', 'ejecuciones-conexion', conexion.id], queryFn: () => cmdbSoftwareApi.ejecucionesDeConexion(conexion.id) })
  const ultimo = data?.find(x => x.error)?.error
  return (
    <AvisoDeConfiguracion tono="danger">
      {t('sw.esc_fallo', { nombre: conexion.name })}{ultimo ? `: ${ultimo}` : ''}
    </AvisoDeConfiguracion>
  )
}

function ResumenDeEscaneo({ nombre, r, onClose }: { nombre: string; r: ResultadoDeEscaneo; onClose: () => void }) {
  const t = useAppT()
  return (
    <Modal open onClose={onClose} title={t('sw.esc_resumen', { nombre })}>
      <div className="u-stack-12">
        <ListaKv filas={[
          [t('sw.estado'), <EstadoDeEjecucion key="e" estado={r.status} />],
          [t('sw.esc_equipos'), r.hosts],
          [t('sw.esc_instancias_nuevas'), r.created],
          [t('sw.esc_instancias_actualizadas'), r.updated],
          [t('sw.esc_instancias_paradas'), r.stopped],
          [t('sw.componentes'), r.components],
          [t('sw.esc_cis_creados'), r.cis_created],
          [t('sw.esc_sin_ci'), r.without_ci],
          [t('sw.esc_hallazgos_nuevos'), r.findings_new],
          [t('sw.resueltos'), r.findings_resolved],
        ]} />
        {r.errors.length > 0 && (
          <div className="u-stack-6">
            <div className="ds-eyebrow">{t('sw.esc_errores', { n: r.errors.length })}</div>
            <ul className="sw-lista-simple">{r.errors.map((x, i) => <li key={i}><span className="u-mono">{x.target}</span>: {x.error}</li>)}</ul>
          </div>
        )}
        <div className="u-actions-10"><Button onClick={onClose}>{t('sw.cerrar')}</Button></div>
      </div>
    </Modal>
  )
}

function HistorialDeEscaneo({ conexion, onClose }: { conexion: ConexionDeEscaneo; onClose: () => void }) {
  const t = useAppT()
  const { data, isLoading } = useQuery({ queryKey: ['sw', 'ejecuciones-conexion', conexion.id], queryFn: () => cmdbSoftwareApi.ejecucionesDeConexion(conexion.id) })
  return (
    <Modal open size="lg" onClose={onClose} title={t('sw.esc_historial', { nombre: conexion.name })}>
      {isLoading ? <Spinner /> : (data ?? []).length === 0 ? <EmptyState icon={<History size={28} />} title={t('sw.sin_ejecuciones')} /> : (
        <TablaSimple etiqueta={t('sw.esc_ejecuciones')} densidad="compacta">
          <thead><tr><th>{t('sw.inicio')}</th><th>{t('sw.esc_fin')}</th><th>{t('sw.estado')}</th><th>{t('sw.esc_lanzada_por')}</th><th>{t('sw.esc_resultado')}</th></tr></thead>
          <tbody>{(data ?? []).map(x => (
            <tr key={x.id}>
              <td>{fmtDateTime(x.started_at)}</td><td>{fmtDateTime(x.finished_at)}</td>
              <td><EstadoDeEjecucion estado={x.status} /></td>
              <td>{x.triggered_by ? etiquetaCodigo(t, 'sw.v_disparo', x.triggered_by) : '—'}</td>
              <td className="u-text3-xs sdm-wrap">
                {x.summary ? t('sw.esc_resumen_corto', { equipos: Number(x.summary.hosts ?? 0), nuevas: Number(x.summary.created ?? 0), actualizadas: Number(x.summary.updated ?? 0) }) : ''}
                {x.error && <div className="u-danger">{x.error}</div>}
              </td>
            </tr>
          ))}</tbody>
        </TablaSimple>
      )}
    </Modal>
  )
}

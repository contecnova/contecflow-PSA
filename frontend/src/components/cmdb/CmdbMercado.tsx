/**
 * CmdbMercado — lo que la CMDB tenía solo por API (mejoras de mercado 16-11-2026):
 * proveedores de descubrimiento (AWS, Azure, GCP, Kubernetes, vSphere, SNMP),
 * reconciliación de duplicados, deriva de configuración, radio de impacto y
 * retirada de un CI, y clases de CI propias de la empresa.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Play, Plus, Radar, Shapes, Trash2 } from 'lucide-react'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { confirmar } from '../../context/ConfirmContext'
import { extractErr, fmtDate } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { Button, Checkbox, EmptyState, Modal, Section, SelectorDePeriodo, Select, Spinner, StatusBadge } from '../ui'
import { usePeriodo } from '../../hooks/usePeriodo'
import { CON_HORA, codigoDeErrorDePeriodo } from '../../utils/periodo'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { cmdbApi } from '../../services/api'
import { cmdbMercadoApi } from '../../services/api/serviceDeskMercado'
import type { ClaseDeCi, ProveedorDeDescubrimiento } from '../../services/api/serviceDeskMercado'
import VistaDeDatos from '../servicedesk/VistaDeDatos'
import '../servicedesk/sdMercado.css'

const TIPOS_DE_PROVEEDOR = ['aws', 'azure', 'gcp', 'kubernetes', 'vsphere', 'snmp']
/** Claves de configuración que pide cada proveedor (las lee `app/services/cmdb/`). */
const CAMPOS_DE_PROVEEDOR: Record<string, string[]> = {
  aws: ['access_key_id', 'secret_access_key', 'region'],
  azure: ['tenant_id', 'client_id', 'client_secret', 'subscription_id'],
  gcp: ['project_id', 'service_account_json'],
  kubernetes: ['api_server', 'token', 'namespace'],
  vsphere: ['host', 'username', 'password'],
  snmp: ['hosts', 'community', 'port'],
}
const esSecreto = (k: string) => /secret|password|token|key|credential|community|json/i.test(k)

function useErr() {
  const toast = useToast()
  return (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
}

export function DescubrimientoTab() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const err = useErr()
  const [editando, setEditando] = useState<ProveedorDeDescubrimiento | 'nuevo' | null>(null)
  const [verJobs, setVerJobs] = useState<string | null>(null)
  const proveedores = useQuery({ queryKey: ['sdm-discovery'], queryFn: cmdbMercadoApi.proveedores })
  const jobs = useQuery({ queryKey: ['sdm-discovery-jobs', verJobs], queryFn: () => cmdbMercadoApi.ejecuciones(verJobs as string), enabled: !!verJobs })
  const refrescar = () => qc.invalidateQueries({ queryKey: ['sdm-discovery'] })
  const lanzar = useMutation({ mutationFn: cmdbMercadoApi.lanzar, onSuccess: () => { toast.success(t('sd_mercado.lanzado')); refrescar() }, onError: err })
  const lanzarTodos = useMutation({ mutationFn: cmdbMercadoApi.lanzarTodos, onSuccess: () => { toast.success(t('sd_mercado.lanzado')); refrescar() }, onError: err })
  const lineaBase = useMutation({ mutationFn: cmdbMercadoApi.aprobarLineaBase, onSuccess: () => toast.success(t('sd_mercado.linea_base_aprobada')), onError: err })
  const activar = useMutation({ mutationFn: (p: ProveedorDeDescubrimiento) => cmdbMercadoApi.editarProveedor(p.id, { is_active: !p.is_active }), onSuccess: refrescar, onError: err })
  return (
    <div className="u-stack-20">
      <Section title={t('sd_mercado.proveedores')} subtitle={t('sd_mercado.proveedores_desc')}
        actions={<>
          <Button size="sm" variant="secondary" icon={<Play size={14} />} onClick={() => lanzarTodos.mutate()} loading={lanzarTodos.isPending}>{t('sd_mercado.lanzar_todos')}</Button>
          <Button size="sm" icon={<Plus size={14} />} onClick={() => setEditando('nuevo')}>{t('sd_mercado.proveedor_nuevo')}</Button>
        </>}>
        {proveedores.isLoading ? <Spinner /> : (proveedores.data ?? []).length === 0 ? <EmptyState icon={<Radar size={28} />} title={t('sd_mercado.sin_proveedores')} /> : (
          <ul className="sdm-list">
            {(proveedores.data ?? []).map(p => (
              <li key={p.id} className="sdm-list__item">
                <div className="u-flex1-min0 u-stack-6">
                  <div className="u-wrap-8"><span className="u-text1-sm-600">{p.name}</span>
                    <StatusBadge caps={false}>{etiquetaCodigo(t, 'sd_mercado.proveedor', p.provider_type)}</StatusBadge>
                    <StatusBadge kind={p.is_active ? 'success' : 'neutral'} caps={false}>{t(p.is_active ? 'sd_mercado.activo' : 'sd_mercado.apagado')}</StatusBadge>
                    {p.last_run_status && <StatusBadge kind={p.last_run_status === 'ok' ? 'success' : p.last_run_status === 'error' ? 'danger' : 'info'} caps={false}>{etiquetaCodigo(t, 'sd_mercado.ejecucion', p.last_run_status)}</StatusBadge>}
                  </div>
                  <div className="u-text3-xs">{t('sd_mercado.cada_min', { n: p.scan_interval_minutes })} · {t('sd_mercado.ultima_vez')}: {p.last_run_at ? fmtDate(p.last_run_at) : '—'}</div>
                </div>
                <div className="u-actions-8">
                  <Button size="xs" variant="secondary" onClick={() => lanzar.mutate(p.id)} disabled={lanzar.isPending || !p.is_active}>{t('sd_mercado.lanzar')}</Button>
                  <Button size="xs" variant="ghost" onClick={() => setVerJobs(verJobs === p.id ? null : p.id)}>{t('sd_mercado.ejecuciones')}</Button>
                  <Button size="xs" variant="ghost" onClick={async () => { if (await confirmar({ message: t('sd_mercado.linea_base_confirmar') })) lineaBase.mutate(p.id) }}>{t('sd_mercado.aprobar_linea_base')}</Button>
                  <Button size="xs" variant="ghost" onClick={() => setEditando(p)}>{t('sd_mercado.editar')}</Button>
                  <Button size="xs" variant="ghost" onClick={() => activar.mutate(p)}>{t(p.is_active ? 'sd_mercado.desactivar' : 'sd_mercado.activar')}</Button>
                </div>
              </li>
            ))}
          </ul>
        )}
        {verJobs && (jobs.isLoading ? <Spinner size={16} /> : <VistaDeDatos datos={jobs.data ?? []} />)}
      </Section>
      <Reconciliacion />
      <Deriva />
      {editando && <ProveedorModal inicial={editando === 'nuevo' ? null : editando} onClose={() => setEditando(null)} onSaved={() => { setEditando(null); refrescar() }} />}
    </div>
  )
}

function ProveedorModal({ inicial, onClose, onSaved }: { inicial: ProveedorDeDescubrimiento | null; onClose: () => void; onSaved: () => void }) {
  const t = useAppT()
  const err = useErr()
  const [nombre, setNombre] = useState(inicial?.name ?? '')
  const [tipo, setTipo] = useState(inicial?.provider_type ?? 'aws')
  const [intervalo, setIntervalo] = useState(inicial?.scan_interval_minutes ?? 60)
  const [config, setConfig] = useState<Record<string, string>>(Object.fromEntries(Object.entries(inicial?.config ?? {}).map(([k, v]) => [k, String(v ?? '')])))
  const campos = Array.from(new Set([...(CAMPOS_DE_PROVEEDOR[tipo] ?? []), ...Object.keys(config)]))
  const guardar = useMutation({
    mutationFn: () => inicial
      ? cmdbMercadoApi.editarProveedor(inicial.id, { name: nombre, config, scan_interval_minutes: intervalo })
      : cmdbMercadoApi.crearProveedor({ name: nombre, provider_type: tipo, config, is_active: true, scan_interval_minutes: intervalo }),
    onSuccess: onSaved, onError: err,
  })
  return (
    <Modal open size="lg" onClose={onClose} title={inicial ? t('sd_mercado.proveedor_editar') : t('sd_mercado.proveedor_nuevo')}>
      <div className="u-stack-12">
        <div className="sdm-form">
          <label className="sdm-field"><span>{t('sd_mercado.nombre')}</span><input className="ds-input" value={nombre} onChange={e => setNombre(e.target.value)} /></label>
          <label className="sdm-field"><span>{t('sd_mercado.tipo')}</span>
            <Select suelto placeholder={false} value={tipo} disabled={!!inicial} onChange={e => setTipo(e.target.value)}>
              {TIPOS_DE_PROVEEDOR.map(x => <option key={x} value={x}>{etiquetaCodigo(t, 'sd_mercado.proveedor', x)}</option>)}
            </Select></label>
          <label className="sdm-field"><span>{t('sd_mercado.intervalo_min')}</span><input className="ds-input" type="number" min={5} value={intervalo} onChange={e => setIntervalo(Number(e.target.value) || 60)} /></label>
        </div>
        <div className="ds-eyebrow">{t('sd_mercado.configuracion')}</div>
        <div className="sdm-form">
          {campos.map(k => (
            <label key={k} className="sdm-field"><span className="u-mono">{k}</span>
              <input className="ds-input" type={esSecreto(k) ? 'password' : 'text'} autoComplete="off" value={config[k] ?? ''} onChange={e => setConfig({ ...config, [k]: e.target.value })} /></label>
          ))}
        </div>
        <div className="u-text3-xs">{t('sd_mercado.secretos_cifrados')}</div>
        <div className="u-actions-10">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => guardar.mutate()} loading={guardar.isPending} disabled={nombre.trim().length < 2}>{t('common.save')}</Button>
        </div>
      </div>
    </Modal>
  )
}

function Reconciliacion() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const err = useErr()
  const [minimo, setMinimo] = useState(0.9)
  const salud = useQuery({ queryKey: ['sdm-recon-health'], queryFn: cmdbMercadoApi.saludDeReconciliacion })
  const candidatos = useQuery({ queryKey: ['sdm-recon', minimo], queryFn: () => cmdbMercadoApi.candidatosDeReconciliacion(minimo) })
  const fusionar = useMutation({
    mutationFn: () => cmdbMercadoApi.fusionarDuplicados(minimo),
    onSuccess: () => { toast.success(t('sd_mercado.fusionados')); qc.invalidateQueries({ queryKey: ['sdm-recon'] }); qc.invalidateQueries({ queryKey: ['sdm-recon-health'] }) },
    onError: err,
  })
  return (
    <Section title={t('sd_mercado.reconciliacion')} subtitle={t('sd_mercado.reconciliacion_desc')}
      actions={<Button size="sm" variant="danger" disabled={!candidatos.data?.count} loading={fusionar.isPending}
        onClick={async () => { if (await confirmar({ message: t('sd_mercado.fusionar_ci_confirmar', { n: candidatos.data?.count ?? 0 }), danger: true })) fusionar.mutate() }}>
        {t('sd_mercado.fusionar_duplicados')}</Button>}>
      <div className="u-stack-12">
        {salud.data && <VistaDeDatos datos={salud.data} />}
        <label className="sdm-field"><span>{t('sd_mercado.confianza_minima')}</span>
          <input className="ds-input" type="number" min={0.5} max={1} step={0.05} value={minimo} onChange={e => setMinimo(Math.min(1, Math.max(0.5, Number(e.target.value) || 0.9)))} /></label>
        {candidatos.isLoading ? <Spinner size={16} /> : (candidatos.data?.items ?? []).length === 0
          ? <div className="u-text3-xs">{t('sd_mercado.sin_duplicados_ci')}</div>
          : <VistaDeDatos datos={candidatos.data?.items ?? []} />}
      </div>
    </Section>
  )
}

function Deriva() {
  const t = useAppT()
  // Periodo libre (16-11-2026): antes 24/72/168/720 horas propio. La deriva es
  // un instante: admite hora. Prefijo propio (la pestaña convive con otras).
  const periodo = usePeriodo({ defecto: '24h', granularidades: CON_HORA, prefijo: 'deriva' })
  const { data, isLoading, error } = useQuery({
    queryKey: ['sdm-drift', periodo.params],
    queryFn: () => cmdbMercadoApi.deriva(periodo.params),
    retry: (n, e) => !codigoDeErrorDePeriodo(e) && n < 2,
  })
  const errorDePeriodo = codigoDeErrorDePeriodo(error)
  return (
    <Section title={t('sd_mercado.deriva')} subtitle={t('sd_mercado.deriva_desc')}>
      <div className="u-stack-12">
        <SelectorDePeriodo {...periodo.selector} sinGranularidad />
        {isLoading ? <Spinner size={16} />
          : errorDePeriodo ? <EmptyState title={t(`periodo_err.${errorDePeriodo.motivo}`, errorDePeriodo.params)} />
          : <VistaDeDatos datos={data ?? {}} />}
      </div>
    </Section>
  )
}

export function ImpactoTab() {
  const t = useAppT()
  const [busqueda, setBusqueda] = useState('')
  const [ci, setCi] = useState<string | null>(null)
  const cis = useQuery({ queryKey: ['sdm-ci-busca', busqueda], queryFn: () => cmdbApi.sdList({ q: busqueda, page: 1, page_size: 10 }).then(r => r.data), enabled: busqueda.trim().length >= 2 })
  const radio = useQuery({ queryKey: ['sdm-ci-radio', ci], queryFn: () => cmdbMercadoApi.radio(ci as string), enabled: !!ci, retry: false })
  const retirada = useQuery({ queryKey: ['sdm-ci-retirada', ci], queryFn: () => cmdbMercadoApi.retirada(ci as string), enabled: !!ci, retry: false })
  return (
    <Section title={t('sd_mercado.impacto_ci')} subtitle={t('sd_mercado.impacto_ci_desc')}>
      <div className="u-stack-12">
        <label className="sdm-field"><span>{t('sd_mercado.buscar_ci')}</span><input className="ds-input" value={busqueda} onChange={e => setBusqueda(e.target.value)} /></label>
        <div className="u-wrap-6">{(cis.data ?? []).map(c => (
          <Button key={c.id} size="sm" variant={ci === c.id ? 'primary' : 'secondary'} onClick={() => setCi(c.id)}><span className="u-mono">{c.code}</span> {c.name}</Button>
        ))}</div>
        {ci && (
          <div className="sdm-grid">
            <div className="ds-card sdm-card"><div className="sdm-card__head">{t('sd_mercado.radio_impacto')}</div>
              {radio.isLoading ? <Spinner size={16} /> : <VistaDeDatos datos={radio.data ?? {}} />}</div>
            <div className="ds-card sdm-card"><div className="sdm-card__head">{t('sd_mercado.si_se_retira')}</div>
              {retirada.isLoading ? <Spinner size={16} /> : <VistaDeDatos datos={retirada.data ?? {}} />}</div>
          </div>
        )}
      </div>
    </Section>
  )
}

const VACIA = { key: '', label: '', base_type: 'server', description: null as string | null, is_active: true, sort_order: 0 }

export function ClasesPropiasTab() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const err = useErr()
  const { data, isLoading } = useQuery({ queryKey: ['sdm-ci-classes'], queryFn: cmdbMercadoApi.clases })
  const [editando, setEditando] = useState<(Omit<ClaseDeCi, 'id' | 'ci_count'> & { id?: string }) | null>(null)
  const refrescar = () => qc.invalidateQueries({ queryKey: ['sdm-ci-classes'] })
  const guardar = useMutation({
    mutationFn: () => {
      const { id, ...c } = editando as ClaseDeCi
      return id ? cmdbMercadoApi.editarClase(id, c) : cmdbMercadoApi.crearClase(c)
    },
    onSuccess: () => { setEditando(null); refrescar(); toast.success(t('sd_mercado.guardado')) },
    onError: err,
  })
  const borrar = useMutation({ mutationFn: cmdbMercadoApi.borrarClase, onSuccess: refrescar, onError: err })
  return (
    <Section title={t('sd_mercado.clases_ci')} subtitle={t('sd_mercado.clases_ci_desc')}
      actions={<Button size="sm" icon={<Plus size={14} />} onClick={() => setEditando({ ...VACIA })}>{t('sd_mercado.clase_nueva')}</Button>}>
      {isLoading ? <Spinner /> : (data?.classes ?? []).length === 0 ? <EmptyState icon={<Shapes size={28} />} title={t('sd_mercado.sin_clases')} /> : (
        <ul className="sdm-list">
          {(data?.classes ?? []).map(c => (
            <li key={c.id} className="sdm-list__item">
              <div className="u-flex1-min0">
                <div className="u-wrap-8"><span className="u-text1-sm-600">{c.label}</span><span className="u-mono u-text3-xs">{c.key}</span>
                  <StatusBadge caps={false}>{etiquetaCodigo(t, 'sd_mercado.clase_base', c.base_type)}</StatusBadge>
                  {!c.is_active && <StatusBadge caps={false}>{t('sd_mercado.apagado')}</StatusBadge>}</div>
                <div className="u-text3-xs">{t('sd_mercado.n_cis', { n: c.ci_count })}</div>
              </div>
              <div className="u-actions-8">
                <Button size="xs" variant="secondary" onClick={() => setEditando(c)}>{t('sd_mercado.editar')}</Button>
                {c.is_active && <Button size="xs" variant="ghost" icon={<Trash2 size={12} />} onClick={async () => { if (await confirmar({ message: t('sd_mercado.clase_desactivar', { n: c.label }), danger: true })) borrar.mutate(c.id) }}>{t('sd_mercado.desactivar')}</Button>}
              </div>
            </li>
          ))}
        </ul>
      )}
      {editando && (
        <Modal open onClose={() => setEditando(null)} title={editando.id ? t('sd_mercado.clase_editar') : t('sd_mercado.clase_nueva')}>
          <div className="u-stack-12">
            <div className="sdm-form">
              <label className="sdm-field"><span>{t('sd_mercado.clave')}</span><input className="ds-input" value={editando.key} disabled={!!editando.id} onChange={e => setEditando({ ...editando, key: e.target.value.toLowerCase() })} /></label>
              <label className="sdm-field"><span>{t('sd_mercado.nombre')}</span><input className="ds-input" value={editando.label} onChange={e => setEditando({ ...editando, label: e.target.value })} /></label>
              <label className="sdm-field"><span>{t('sd_mercado.clase_base_label')}</span>
                <Select suelto placeholder={false} value={editando.base_type} onChange={e => setEditando({ ...editando, base_type: e.target.value })}>
                  {(data?.base_types ?? []).map(b => <option key={b} value={b}>{etiquetaCodigo(t, 'sd_mercado.clase_base', b)}</option>)}
                </Select></label>
              <label className="sdm-field"><span>{t('sd_mercado.orden')}</span><input className="ds-input" type="number" min={0} value={editando.sort_order} onChange={e => setEditando({ ...editando, sort_order: Number(e.target.value) || 0 })} /></label>
            </div>
            <label className="sdm-field"><span>{t('sd_mercado.descripcion')}</span><input className="ds-input" value={editando.description ?? ''} onChange={e => setEditando({ ...editando, description: e.target.value || null })} /></label>
            <Checkbox className="u-row-center-8" checked={!!editando.is_active} onChange={v => setEditando({ ...editando, is_active: v })} label={t('sd_mercado.activo')} />
            <div className="u-text3-xs">{t('sd_mercado.clase_hint')}</div>
            <div className="u-actions-10">
              <Button variant="secondary" onClick={() => setEditando(null)}>{t('common.cancel')}</Button>
              <Button onClick={() => guardar.mutate()} loading={guardar.isPending} disabled={!/^[a-z0-9_]{2,50}$/.test(editando.key) || !editando.label.trim()}>{t('common.save')}</Button>
            </div>
          </div>
        </Modal>
      )}
    </Section>
  )
}

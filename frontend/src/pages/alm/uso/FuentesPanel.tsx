/** Conexiones de fuentes de uso: credenciales, prueba, sincronización, registro y mapeo de productos. */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, EyeOff, History, KeyRound, Link2, PlugZap, RefreshCw, Settings2 } from 'lucide-react'
import { Button, DataTable, EmptyState, Modal, Section, Spinner, Select, Checkbox, Textarea, Input } from '../../../components/ui'
import type { ColumnaDeTabla } from '../../../components/ui'
import { useToast } from '../../../context/ToastContext'
import { useAppT } from '../../../i18n/AppLangContext'
import { etiquetaCodigo } from '../../../i18n/etiquetaCodigo'
import { licensesApi } from '../../../services/api'
import { almUsoApi } from '../../../services/api/almUso'
import type { Conexion, ProductoDeFuente, Sincronizacion } from '../../../services/api/almUso'
import { fmtDateTime } from '../../../utils/helpers'
import { Estado, FiabilidadBadge, nombreDeFuente, useErrorDeUso } from './comun'

function leerOpcion(texto: string): unknown {
  const s = texto.trim()
  if (!s) return undefined
  if (s.startsWith('[') || s.startsWith('{')) {
    try { return JSON.parse(s) } catch { return s }
  }
  return /^\d+$/.test(s) ? Number(s) : s
}

function Configurar({ c, onClose }: { c: Conexion; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const fallo = useErrorDeUso()
  const qc = useQueryClient()
  const [creds, setCreds] = useState<Record<string, string>>({})
  const [fiabilidad, setFiabilidad] = useState<string>(c.fiabilidad_propia ?? '')
  const [opciones, setOpciones] = useState<Record<string, string>>(
    Object.fromEntries(c.opciones.map(o => {
      const v = c.configuracion[o.clave]
      return [o.clave, v == null ? '' : typeof v === 'string' ? v : JSON.stringify(v)]
    })))
  const guardar = useMutation({
    mutationFn: () => almUsoApi.guardarConexion(c.clave, {
      fiabilidad: fiabilidad || null,
      configuracion: Object.fromEntries(Object.entries(opciones).map(([k, v]) => [k, leerOpcion(v)]).filter(([, v]) => v !== undefined)),
      ...(Object.keys(creds).length ? { credenciales: creds } : {}),
    }),
    onSuccess: () => { toast.success(t('alm_uso.hecho')); qc.invalidateQueries({ queryKey: ['alm-uso-conexiones'] }); onClose() },
    onError: fallo,
  })
  return (
    <Modal open onClose={onClose} title={t('alm_uso.configurar_titulo', { fuente: nombreDeFuente(t, c.clave) })} size="lg">
      <div className="u-stack-14">
        {c.credenciales.length > 0 && (
          <fieldset className="ds-grupo-opciones almu-servicios">
            <legend>{t('alm_uso.credenciales')}</legend>
            <p className="u-text2-xs">{t('alm_uso.credenciales_ayuda')}</p>
            <div className="u-grid2-12">
              {c.credenciales.map(f => (
                <label key={f.clave} className="almu-campo">{etiquetaCodigo(t, 'alm_uso.credencial', f.clave, f.etiqueta)}
                  {f.clave === 'service_account_json'
                    ? <Textarea rows={4} autoComplete="off" placeholder={f.configurado ? t('alm_uso.configurado_sin_cambios') : ''} value={creds[f.clave] ?? ''} onChange={e => setCreds({ ...creds, [f.clave]: e.target.value })} inputClassName="ds-codigo alm-input alm-input--mono ds-campo-codigo" />
                    : <Input aria-label={etiquetaCodigo(t, 'alm_uso.credencial', f.clave, f.etiqueta)} inputClassName="alm-input" type={f.secreto ? 'password' : 'text'} autoComplete="off"
                        placeholder={f.secreto && f.configurado ? t('alm_uso.configurado_sin_cambios') : ''}
                        value={creds[f.clave] ?? (f.secreto ? '' : (f.valor ?? ''))}
                        onChange={e => setCreds({ ...creds, [f.clave]: e.target.value })} />}
                </label>
              ))}
            </div>
          </fieldset>
        )}
        <Select label={t('alm_uso.fiabilidad_col')} placeholder={false} value={fiabilidad} onChange={e => setFiabilidad(e.target.value)}>
            <option value="">{t('alm_uso.fiabilidad_por_defecto', { valor: etiquetaCodigo(t, 'alm_uso.fiabilidad', c.fiabilidad) })}</option>
            {['alta', 'media', 'baja'].map(f => <option key={f} value={f}>{etiquetaCodigo(t, 'alm_uso.fiabilidad', f)}</option>)}
          </Select>
        {c.opciones.length > 0 && (
          <fieldset className="ds-grupo-opciones almu-servicios">
            <legend>{t('alm_uso.opciones')}</legend>
            {c.opciones.map(o => (
              <Input key={o.clave} label={etiquetaCodigo(t, 'alm_uso.opcion', o.clave, o.descripcion)} value={opciones[o.clave] ?? ''} onChange={e => setOpciones({ ...opciones, [o.clave]: e.target.value })} inputClassName="ds-codigo ds-campo-codigo" />
            ))}
          </fieldset>
        )}
        {c.permisos.length > 0 && (
          <div className="almu-permisos">
            <span className="u-text2-sm">{t('alm_uso.permisos_necesarios')}</span>
            <ul>{c.permisos.map(p => <li key={p}>{p}</li>)}</ul>
          </div>
        )}
        <div className="u-row-end almu-acciones">
          <Button variant="ghost" onClick={onClose}>{t('common.cancel')}</Button>
          <Button loading={guardar.isPending} onClick={() => guardar.mutate()}>{t('common.save')}</Button>
        </div>
      </div>
    </Modal>
  )
}

function Historial({ conexionId }: { conexionId: string }) {
  const t = useAppT()
  const { data = [], isLoading } = useQuery({ queryKey: ['alm-uso-sincronizaciones', conexionId],
    queryFn: () => almUsoApi.sincronizaciones(conexionId) })
  const columnas: ColumnaDeTabla<Sincronizacion>[] = [
    { key: 'iniciada_at', label: t('alm_uso.cuando'), render: (_v, s) => fmtDateTime(s.iniciada_at) },
    { key: 'origen', label: t('alm_uso.origen'), render: (_v, s) => etiquetaCodigo(t, 'alm_uso.origen_sinc', s.origen) },
    { key: 'estado', label: t('alm_uso.estado_col'), render: (_v, s) => <Estado codigo={s.estado} catalogo="alm_uso.sinc" /> },
    { key: 'leidos', label: t('alm_uso.leidos') },
    { key: 'nuevas', label: t('alm_uso.nuevas') },
    { key: 'sin_titular', label: t('alm_uso.sin_titular') },
    { key: 'sin_licencia', label: t('alm_uso.sin_licencia') },
    { key: 'errores', label: t('alm_uso.incidencias'), sortable: false, render: (_v, s) => (
      <div className="almu-notas">
        {[...s.errores, ...s.avisos].map((e, i) => (
          <span key={i} className={s.errores.includes(e) ? 'u-danger' : 'u-warning'}>{etiquetaCodigo(t, 'alm_uso.err_fuente', e.codigo, e.mensaje)}</span>
        ))}
      </div>
    ) },
  ]
  return <DataTable columns={columnas} data={data} loading={isLoading} emptyTitle={t('alm_uso.sin_sincronizaciones')} />
}

function Productos() {
  const t = useAppT()
  const toast = useToast()
  const fallo = useErrorDeUso()
  const qc = useQueryClient()
  const [soloSin, setSoloSin] = useState(true)
  const { data = [], isLoading } = useQuery({ queryKey: ['alm-uso-productos', soloSin], queryFn: () => almUsoApi.productos(soloSin) })
  const { data: licencias = [] } = useQuery({ queryKey: ['alm-licencias-todas'], queryFn: () => licensesApi.list().then(r => r.data) })
  const mapear = useMutation({
    mutationFn: (d: { fuente: string; producto: string; license_id: string | null; ignorar: boolean }) => almUsoApi.mapear(d),
    onSuccess: r => { toast.success(t('alm_uso.mapeado', { n: r.evidencias })); qc.invalidateQueries({ queryKey: ['alm-uso-productos'] })
      qc.invalidateQueries({ queryKey: ['alm-uso-licencias'] }); qc.invalidateQueries({ queryKey: ['alm-uso-panel'] }) },
    onError: fallo,
  })
  const columnas: ColumnaDeTabla<ProductoDeFuente>[] = [
    { key: 'fuente', label: t('alm_uso.fuente_col'), render: (_v, p) => nombreDeFuente(t, p.fuente) },
    { key: 'nombre', label: t('alm_uso.producto') },
    { key: 'titulares', label: t('alm_uso.titulares') },
    { key: 'license_id', label: t('alm_uso.licencia'), sortable: false, render: (_v, p) => (
      <Select suelto placeholder={false} className="alm-input alm-input--compact" aria-label={t('alm_uso.licencia_de', { producto: p.nombre })}
        value={p.license_id ?? ''} onChange={e => mapear.mutate({ fuente: p.fuente, producto: p.producto, license_id: e.target.value || null, ignorar: false })}>
        <option value="">{p.mapeo === 'ignorado' ? t('alm_uso.ignorado') : t('alm_uso.sin_licencia')}</option>
        {licencias.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
      </Select>
    ) },
    { key: 'sugerencia', label: t('alm_uso.sugerida'), sortable: false, render: (_v, p) => p.sugerencia ? (
      <Button size="xs" variant="secondary" icon={<Link2 size={12} />}
        onClick={() => mapear.mutate({ fuente: p.fuente, producto: p.producto, license_id: p.sugerencia!.license_id, ignorar: false })}>
        {p.sugerencia.nombre}
      </Button>
    ) : '—' },
    { key: 'mapeo', label: t('alm_uso.acciones'), sortable: false, render: (_v, p) => p.mapeo !== 'ignorado' ? (
      <Button size="xs" variant="ghost" icon={<EyeOff size={12} />}
        onClick={() => mapear.mutate({ fuente: p.fuente, producto: p.producto, license_id: null, ignorar: true })}>{t('alm_uso.no_controlar')}</Button>
    ) : etiquetaCodigo(t, 'alm_uso.mapeo', 'ignorado') },
  ]
  return (
    <Section title={t('alm_uso.productos_titulo')} subtitle={t('alm_uso.productos_desc')}
      actions={<label className="almu-check"><Checkbox checked={soloSin} onChange={(_, e) => setSoloSin(e.target.checked)} />{t('alm_uso.solo_sin_licencia')}</label>}>
      <DataTable columns={columnas} data={data} loading={isLoading} emptyTitle={t('alm_uso.sin_productos')} />
    </Section>
  )
}

export default function FuentesPanel() {
  const t = useAppT()
  const toast = useToast()
  const fallo = useErrorDeUso()
  const qc = useQueryClient()
  const [configurando, setConfigurando] = useState<Conexion | null>(null)
  const [historial, setHistorial] = useState<string | null>(null)
  const { data = [], isLoading } = useQuery({ queryKey: ['alm-uso-conexiones'], queryFn: () => almUsoApi.conexiones() })
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['alm-uso-conexiones'] }); qc.invalidateQueries({ queryKey: ['alm-uso-panel'] }) }
  const activar = useMutation({ mutationFn: (c: Conexion) => almUsoApi.guardarConexion(c.clave, { activa: !c.activa }),
    onSuccess: refrescar, onError: fallo })
  const probar = useMutation({ mutationFn: (c: Conexion) => almUsoApi.probar(c.clave),
    onSuccess: r => r.ok ? toast.success(t('alm_uso.prueba_ok')) : toast.error(etiquetaCodigo(t, 'alm_uso.err_fuente', r.codigo, r.mensaje)),
    onError: fallo })
  const sincronizar = useMutation({ mutationFn: (c: Conexion) => almUsoApi.sincronizar(c.conexion_id as string),
    onSuccess: s => { toast.success(etiquetaCodigo(t, 'alm_uso.sinc_resultado', s.estado)); refrescar()
      qc.invalidateQueries({ queryKey: ['alm-uso-licencias'] }) },
    onError: fallo })
  if (isLoading) return <Spinner />
  return (
    <div className="u-stack-16">
      <p className="u-text2-sm">{t('alm_uso.fuentes_intro')}</p>
      {data.length === 0 && <EmptyState svgIcon={<PlugZap size={28} aria-hidden="true" />} title={t('alm_uso.sin_fuentes_titulo')} />}
      <div className="almu-fuentes">
        {data.map(c => (
          <article key={c.clave} className="alm-card almu-fuente" aria-label={nombreDeFuente(t, c.clave)}>
            <header className="u-row-between">
              <div className="u-stack-6 u-min0">
                <h4 className="almu-fuente__titulo">{nombreDeFuente(t, c.clave)}</h4>
                <span className="u-text3-xs">{etiquetaCodigo(t, 'alm_uso.tipo_fuente', c.tipo)} · {c.aporta.map(a => etiquetaCodigo(t, 'alm_uso.aporta', a)).join(', ')}</span>
              </div>
              <Estado codigo={c.activa ? c.ultimo_estado : 'nunca'} catalogo="alm_uso.sinc" />
            </header>
            <dl className="almu-fuente__datos">
              <dt>{t('alm_uso.fiabilidad_col')}</dt><dd><FiabilidadBadge valor={c.fiabilidad_efectiva} /></dd>
              <dt>{t('alm_uso.ultima_sincronizacion')}</dt><dd>{c.ultima_sincronizacion_at ? fmtDateTime(c.ultima_sincronizacion_at) : t('alm_uso.nunca')}</dd>
              {c.ultima && <><dt>{t('alm_uso.leidos')}</dt><dd>{c.ultima.leidos}</dd></>}
              {c.credencial && <><dt>{t('alm_uso.credenciales')}</dt>
                <dd className={c.lista ? 'u-success' : 'u-warning'}>{c.lista ? t('alm_uso.credenciales_completas')
                  : t('alm_uso.faltan', { campos: c.faltan.map(f => etiquetaCodigo(t, 'alm_uso.credencial', f)).join(', ') })}</dd></>}
            </dl>
            {c.ultimo_error && <p className="u-danger almu-error">{c.ultimo_error}</p>}
            {(c.ultima?.avisos.length ?? 0) > 0 && (
              <ul className="almu-avisos">{c.ultima?.avisos.map((a, i) => <li key={i}>{etiquetaCodigo(t, 'alm_uso.err_fuente', a.codigo, a.mensaje)}</li>)}</ul>
            )}
            <div className="almu-acciones">
              <Button size="xs" variant={c.activa ? 'secondary' : 'primary'} icon={<CheckCircle2 size={12} />}
                disabled={!c.activa && !c.lista} title={!c.activa && !c.lista ? t('alm_uso.configura_primero') : undefined}
                onClick={() => activar.mutate(c)}>{c.activa ? t('alm_uso.desactivar') : t('alm_uso.activar')}</Button>
              <Button size="xs" variant="ghost" icon={c.credencial ? <KeyRound size={12} /> : <Settings2 size={12} />}
                onClick={() => setConfigurando(c)}>{t('alm_uso.configurar')}</Button>
              {c.tipo !== 'interno' && c.lista && (
                <Button size="xs" variant="ghost" icon={<PlugZap size={12} />} loading={probar.isPending && probar.variables?.clave === c.clave}
                  onClick={() => probar.mutate(c)}>{t('alm_uso.probar')}</Button>
              )}
              {c.activa && c.tipo !== 'agente' && c.conexion_id && (
                <Button size="xs" variant="ghost" icon={<RefreshCw size={12} />}
                  loading={sincronizar.isPending && sincronizar.variables?.clave === c.clave}
                  onClick={() => sincronizar.mutate(c)}>{t('alm_uso.sincronizar')}</Button>
              )}
              {c.conexion_id && (
                <Button size="xs" variant="ghost" icon={<History size={12} />} aria-expanded={historial === c.conexion_id}
                  onClick={() => setHistorial(historial === c.conexion_id ? null : c.conexion_id)}>{t('alm_uso.historial')}</Button>
              )}
            </div>
          </article>
        ))}
      </div>
      {historial && (
        <Section title={t('alm_uso.historial_de', { fuente: nombreDeFuente(t, data.find(c => c.conexion_id === historial)?.clave) })}>
          <Historial conexionId={historial} />
        </Section>
      )}
      <Productos />
      {configurando && <Configurar c={configurando} onClose={() => setConfigurando(null)} />}
    </div>
  )
}

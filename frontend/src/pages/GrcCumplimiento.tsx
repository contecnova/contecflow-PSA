// Pestañas de retencion, evidencias, informe de cumplimiento y explicacion de acceso de GRC. 23-11-2026: troceado de GrcPage sin cambio de comportamiento.
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { openConfirmGlobal, confirmar } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useToast } from '../context/ToastContext'
import { grcApi, governanceApi, esFichaCompleta } from '../services/api'
import { useListaDeUsuarios } from '../hooks/useListas'
import { PREFIJO_API_SERVIDOR } from '../services/api/urls'
import type { CapaDeAcceso, ExplicacionDeAcceso as Explicacion, InformeDeCumplimiento, PoliticaDeRetencion, BloqueoLegal as Bloqueo, VistaPreviaDeRetencion, MarcosDeCumplimiento, EstadoDeControlesDelMarco, EvidenciaDeCumplimiento } from '../services/api/tipos-grc'
import type { AxiosResponse } from 'axios'
import Pagination from '../components/ui/Pagination'
import { SMALL_PAGE_SIZE } from '../constants/pagination'
import { RefreshCw } from 'lucide-react'
import { Button, Spinner, KpiCard, Select, TablaSimple, Input } from '../components/ui'
import { extractErr, downloadBlob, fmtDate, fmtDateTime } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useAppT } from '../i18n/AppLangContext'
import { alpha } from '../constants/theme'

const COLOR_VEREDICTO: Record<string, string> = { allow: 'var(--success)', deny: 'var(--danger)', unknown: 'var(--warning)', not_applicable: 'var(--text-3)' }

const COLOR_CONTROL: Record<string, string> = { pass: 'var(--success)', attention: 'var(--danger)', info: 'var(--accent)', not_measurable: 'var(--text-3)' }

/** Retención por tipo de registro y bloqueo legal (revisión 2026-11). */
export function RetencionTab() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { data } = useQuery<{ policies: PoliticaDeRetencion[]; min_days: number }>({
    // Revisión GRC 16-11-2026: ['retention'] y ['legal-holds'] eran también las claves del
    // chat (ChatAdminPage, otra forma de datos): la caché de una pantalla rompía la otra.
    queryKey: ['grc-retention'], queryFn: () => governanceApi.retentionPolicies().then(r => r.data),
  })
  const { data: bloqueos = [] } = useQuery<Bloqueo[]>({ queryKey: ['grc-legal-holds'], queryFn: () => governanceApi.legalHolds().then(r => r.data) })
  const [dias, setDias] = useState<Record<string, string>>({})
  const [previas, setPrevias] = useState<Record<string, VistaPreviaDeRetencion>>({})
  const [nuevo, setNuevo] = useState({ case_reference: '', reason: '', entity: '*', field: 'client_id', value: '' })
  const error = (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['grc-retention'] }); qc.invalidateQueries({ queryKey: ['grc-legal-holds'] }) }
  const diasDe = (p: PoliticaDeRetencion) => Number(dias[p.entity] ?? p.keep_days ?? 365)
  const previa = async (p: PoliticaDeRetencion) => {
    try { const r = await governanceApi.retentionPreview(p.entity, diasDe(p)); setPrevias(v => ({ ...v, [p.entity]: r.data })) } catch (e) { error(e) }
  }
  const guardar = async (p: PoliticaDeRetencion, activa: boolean) => {
    try { await governanceApi.saveRetention(p.entity, { keep_days: diasDe(p), is_active: activa }); toast.success(t('grc.retencion_guardada')); refrescar() } catch (e) { error(e) }
  }
  const aplicar = async () => {
    if (!await confirmar({ message: t('grc.retencion_confirmar_aplicar'), danger: true })) return
    try {
      const r = await governanceApi.retentionRun()
      const total = Object.values(r.data).reduce((a, x) => a + x.deleted, 0)
      toast.success(t('grc.retencion_aplicada', { n: total })); refrescar()
    } catch (e) { error(e) }
  }
  const crear = async () => {
    try { await governanceApi.createLegalHold(nuevo); setNuevo({ ...nuevo, case_reference: '', reason: '', value: '' }); refrescar() } catch (e) { error(e) }
  }
  const camposDe = (entidad: string) => Array.from(new Set((data?.policies || []).filter(p => entidad === '*' || p.entity === entidad).flatMap(p => p.hold_fields)))
  const campos = camposDe(nuevo.entity)
  // Revisión GRC 16-11-2026: al cambiar de tipo, el campo elegido podía no existir en él
  // (el desplegable mostraba otro y la API devolvía 422).
  const cambiarTipo = (entidad: string) => {
    const validos = camposDe(entidad)
    setNuevo(n => ({ ...n, entity: entidad, field: validos.includes(n.field) ? n.field : (validos[0] || '') }))
  }
  const levantar = (id: string) => openConfirmGlobal({ message: t('grc.bloqueo_confirmar_levantar'), danger: true,
    onConfirm: async () => { try { await governanceApi.releaseLegalHold(id); refrescar() } catch (e) { error(e) } } })

    if (!data) return <Spinner />
  return (
    <div className="grc-grid-4">
      <section>
        <div className="grc-row-18">
          <h3 className="grc-title">{t('grc.retencion_titulo')}</h3>
          <Button size="sm" variant="secondary" onClick={aplicar}>{t('grc.retencion_aplicar_ya')}</Button>
        </div>
        <p className="grc-text">{t('grc.retencion_intro', { min: data.min_days })}</p>
        <TablaSimple claseTabla="u-table-sm">
          <thead><tr><th className="grc-page-e20">{t('grc.retencion_tipo')}</th><th className="grc-page-e20">{t('grc.retencion_dias')}</th><th className="grc-page-e20">{t('grc.retencion_previa')}</th><th className="grc-page-e20">{t('grc.retencion_estado')}</th><th className="grc-page-e20"><span className="u-sr-only">{t('pagina_grc.acciones')}</span></th></tr></thead>
          <tbody>
            {data.policies.map(p => {
              const v = previas[p.entity]
              return (
                <tr key={p.entity} className="grc-row-19">
                  <td className="grc-td-4">{t(`grc.retencion_tipo_${p.entity}`)}</td>
                  <td className="grc-td-5">
                    <Input type="number" min={data.min_days} aria-label={t('grc.retencion_dias')} value={dias[p.entity] ?? p.keep_days ?? ''} placeholder="365" onChange={e => setDias(d => ({ ...d, [p.entity]: e.target.value }))} inputClassName="grc-page-e14" />
                  </td>
                  <td className="grc-td-6">
                    {v ? t('grc.retencion_previa_resultado', { borraria: v.would_delete, retenidos: v.held, vencidos: v.expired })
                      : <Button size="sm" variant="ghost" onClick={() => previa(p)}>{t('grc.retencion_ver_previa')}</Button>}
                  </td>
                  <td className={`grc-td-5 ${p.is_active ? 'grcpage-sx10' : 'grcpage-sx13'}`}>
                    {p.is_active ? t('grc.retencion_activa') : t('grc.retencion_apagada')}
                    {p.last_run_at && <div className="u-text3-xs">{t('grc.retencion_ultima', { n: p.last_deleted ?? 0, fecha: fmtDateTime(p.last_run_at) })}</div>}
                  </td>
                  <td className="grc-td-7">
                    <Button size="sm" variant={p.is_active ? 'secondary' : 'primary'} onClick={() => guardar(p, !p.is_active)}>
                      {p.is_active ? t('grc.retencion_apagar') : t('grc.retencion_activar')}
                    </Button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </TablaSimple>
      </section>
      <section>
        <h3 className="grc-title-2">{t('grc.bloqueo_titulo')}</h3>
        <p className="grc-text">{t('grc.bloqueo_intro')}</p>
        <div className="grc-row-20">
          <Input aria-label={t('grc.bloqueo_caso')} placeholder={t('grc.bloqueo_caso')} value={nuevo.case_reference} onChange={e => setNuevo({ ...nuevo, case_reference: e.target.value })} inputClassName="grc-page-e21" />
          <Select suelto placeholder={false} aria-label={t('grc.retencion_tipo')} value={nuevo.entity} onChange={e => cambiarTipo(e.target.value)} className="grc-page-e21">
            <option value="*">{t('grc.bloqueo_todos')}</option>
            {data.policies.map(p => <option key={p.entity} value={p.entity}>{t(`grc.retencion_tipo_${p.entity}`)}</option>)}
          </Select>
          <Select suelto placeholder={false} aria-label={t('grc.bloqueo_campo')} value={nuevo.field} onChange={e => setNuevo({ ...nuevo, field: e.target.value })} className="grc-page-e21">
            {campos.map(c => <option key={c} value={c}>{t(`grc.bloqueo_campo_${c}`)}</option>)}
          </Select>
          <Input aria-label={t('grc.bloqueo_valor')} placeholder={t('grc.bloqueo_valor')} value={nuevo.value} onChange={e => setNuevo({ ...nuevo, value: e.target.value })} inputClassName="ds-codigo grc-page-e15" />
          <Button size="sm" onClick={crear} disabled={!nuevo.case_reference.trim() || !nuevo.value.trim()}>{t('grc.bloqueo_crear')}</Button>
        </div>
        {bloqueos.length === 0 ? <div className="u-text3-sm">{t('grc.bloqueo_ninguno')}</div> : (
          <TablaSimple claseTabla="u-table-sm">
            <tbody>
              {bloqueos.map(b => (
                <tr key={b.id} className={`grc-row-19 ${b.is_active ? 'grcpage-sx7' : 'grcpage-sx14'}`}>
                  <td className="grc-td-4">{b.case_reference}</td>
                  <td className="grc-td-5">{b.entity === '*' ? t('grc.bloqueo_todos') : t(`grc.retencion_tipo_${b.entity}`)}</td>
                  <td className="grc-td-8">{t(`grc.bloqueo_campo_${b.field}`)} = {b.value}</td>
                  <td className={`grc-td-5 ${b.is_active ? 'grcpage-sx15' : 'grcpage-sx13'}`}>{b.is_active ? t('grc.bloqueo_activo') : t('grc.bloqueo_levantado')}</td>
                  <td className="grc-td-9">
                    {b.is_active && <Button size="sm" variant="secondary" onClick={() => levantar(b.id)}>{t('grc.bloqueo_levantar')}</Button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </TablaSimple>
        )}
      </section>
    </div>
  )
}

/** Sufijo de la clave del título de un control (`marcos_de_cumplimiento.clave_de_texto`). */
const claveDeControl = (id: string) => id.replace(/[^A-Za-z0-9]/g, '_')

/**
 * Marcos (SOC 2, ISO 27001), estado de cada control y evidencias (revisión GRC 16-11-2026).
 * La API existía (`/governance/compliance/*`) y ninguna pantalla la usaba. El estado
 * cruza la evidencia subida con lo que mide el informe: un control medido en rojo
 * pide atención aunque tenga evidencias.
 */
export function EvidenciasTab() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: marcos } = useQuery<MarcosDeCumplimiento>({
    queryKey: ['grc-frameworks'], queryFn: () => governanceApi.frameworks().then(r => r.data),
  })
  const nombres = Object.keys(marcos?.frameworks || {})
  const [elegido, setElegido] = useState('')
  const marco = elegido || nombres[0] || ''
  const controles = marcos?.frameworks[marco] || []
  const { data: estado, isLoading: cargandoEstado } = useQuery<EstadoDeControlesDelMarco>({
    queryKey: ['grc-controls-status', marco], enabled: !!marco,
    queryFn: () => governanceApi.controlsStatus(marco).then(r => r.data),
  })
  const [page, setPage] = useState(1)
  const { data: pagina } = useQuery<{ items: EvidenciaDeCumplimiento[]; total: number }>({
    queryKey: ['grc-evidence', marco, page], enabled: !!marco,
    queryFn: () => governanceApi.evidence({ framework: marco, page, page_size: SMALL_PAGE_SIZE })
      .then((r: AxiosResponse<EvidenciaDeCumplimiento[]> & { meta?: { total?: number } }) =>
        ({ items: r.data, total: Number(r.meta?.total ?? r.data.length) })),
  })
  const paginas = Math.max(1, Math.ceil((pagina?.total ?? 0) / SMALL_PAGE_SIZE))
  const vacia = { control_id: '', evidence_type: 'policy', title: '', artifact_uri: '', artifact_sha256: '' }
  const [nueva, setNueva] = useState(vacia)
  const control = nueva.control_id || controles[0] || ''
  const shaValido = !nueva.artifact_sha256 || /^[0-9a-fA-F]{64}$/.test(nueva.artifact_sha256)

  const { mutate: registrar, isPending } = useMutation({
    mutationFn: () => governanceApi.createEvidence({
      framework: marco, control_id: control, evidence_type: nueva.evidence_type, title: nueva.title.trim(),
      artifact_uri: nueva.artifact_uri.trim() || undefined, artifact_sha256: nueva.artifact_sha256.trim() || undefined,
    }),
    onSuccess: () => {
      setNueva(vacia)
      qc.invalidateQueries({ queryKey: ['grc-controls-status'] })
      qc.invalidateQueries({ queryKey: ['grc-evidence'] })
      toast.success(t('grc.evidencias_registrada'))
    },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const cambiarMarco = (m: string) => { setElegido(m); setPage(1); setNueva(vacia) }

  if (!marcos) return <Spinner />
  return (
    <div className="grc-grid-4">
      <p className="grc-text">{t('grc.evidencias_intro')}</p>
      <div className="grc-row-11">
        {nombres.map(m => (
          <Button key={m} size="sm" variant={marco === m ? 'primary' : 'secondary'} onClick={() => cambiarMarco(m)}>
            {m}
          </Button>
        ))}
      </div>

      <section>
        {cargandoEstado || !estado ? <Spinner /> : (
          <TablaSimple claseTabla="u-table-sm">
            <thead><tr className="grc-row-23">
              <th className="grc-th-5">{t('grc.informe_col_estado')}</th><th className="grc-th-5">{t('grc.evidencias_col_control')}</th>
              <th className="grc-th-5">{t('grc.evidencias_col_evidencias')}</th><th className="grc-th-5">{t('grc.evidencias_col_medido')}</th>
            </tr></thead>
            <tbody>
              {estado.controls.map(c => (
                <tr key={c.control_id} className="grc-row-24">
                  <td className="grc-td-10 grc-page-e4" style={{ '--grc-page-color': COLOR_CONTROL[c.status] } as CSSProperties}>{t(`grc.informe_estado_${c.status}`)}</td>
                  <td className="grc-td-5">
                    <div className="u-600">{t(`grc.marco_control_${claveDeControl(c.control_id)}`)}</div>
                    <div className="u-text3-xs">{c.control_id}</div>
                  </td>
                  <td className="grc-td-5">{c.evidence_count}</td>
                  <td className="grc-td-11">
                    {c.measured.length === 0 ? '—' : c.measured.map(m => (
                      <div key={m.id} className="grc-page-e4" style={{ '--grc-page-color': COLOR_CONTROL[m.status] } as CSSProperties}>
                        {t(`grc.informe_control_${m.id}`)}: {t(`grc.informe_estado_${m.status}`)}
                      </div>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </TablaSimple>
        )}
      </section>

      <section>
        <h3 className="grc-title-2">{t('grc.evidencias_registrar')}</h3>
        <div className="grc-row-20">
          <Select suelto placeholder={false} aria-label={t('grc.evidencias_control')} value={control} onChange={e => setNueva({ ...nueva, control_id: e.target.value })} className="grc-page-e21">
            {controles.map(c => <option key={c} value={c}>{c} — {t(`grc.marco_control_${claveDeControl(c)}`)}</option>)}
          </Select>
          <Select suelto placeholder={false} aria-label={t('grc.evidencias_tipo')} value={nueva.evidence_type} onChange={e => setNueva({ ...nueva, evidence_type: e.target.value })} className="grc-page-e21">
            {marcos.evidence_types.map(x => <option key={x} value={x}>{t(`grc.evidencia_tipo_${x}`)}</option>)}
          </Select>
          <Input aria-label={t('grc.evidencias_titulo')} placeholder={t('grc.evidencias_titulo')} maxLength={255} value={nueva.title} onChange={e => setNueva({ ...nueva, title: e.target.value })} inputClassName="grc-page-e21" />
          <Input aria-label={t('grc.evidencias_uri')} placeholder={t('grc.evidencias_uri')} maxLength={1000} value={nueva.artifact_uri} onChange={e => setNueva({ ...nueva, artifact_uri: e.target.value })} inputClassName="grc-page-e21" />
          <Input aria-label={t('grc.evidencias_sha256')} placeholder={t('grc.evidencias_sha256')} maxLength={64} value={nueva.artifact_sha256} onChange={e => setNueva({ ...nueva, artifact_sha256: e.target.value })} inputClassName="ds-codigo grc-page-e15" error={!shaValido ? t('grc.evidencias_sha256_invalido') : undefined} />
          <Button size="sm" onClick={() => registrar()} loading={isPending} disabled={isPending || !control || !nueva.title.trim() || !shaValido}>{t('grc.evidencias_registrar')}</Button>
        </div>
        {(pagina?.items.length ?? 0) === 0 ? <div className="u-text3-sm">{t('grc.evidencias_ninguna')}</div> : (
          <TablaSimple claseTabla="u-table-sm">
            <tbody>
              {pagina?.items.map(ev => (
                <tr key={ev.id} className="grc-row-19">
                  <td className="grc-td-5">{fmtDate(ev.created_at)}</td>
                  <td className="grc-td-5">{ev.control_id}</td>
                  <td className="grc-td-5">{t(`grc.evidencia_tipo_${ev.evidence_type}`)}</td>
                  <td className="grc-td-4">{ev.title}</td>
                  <td className="grc-td-8"><code className="ds-codigo">{ev.artifact_uri || '—'}{ev.artifact_hash ? ` · sha256 ${ev.artifact_hash.slice(0, 12)}…` : ''}</code></td>
                </tr>
              ))}
            </tbody>
          </TablaSimple>
        )}
        {paginas > 1 && <Pagination page={page} totalPages={paginas} onChange={setPage} />}
      </section>
    </div>
  )
}

/** Informe de evidencias medido sobre el sistema vivo (revisión 2026-11). */
export function InformeDeCumplimientoTab() {
  const t = useAppT()
  const toast = useToast()
  const [bajando, setBajando] = useState(false)
  const { data, isFetching, refetch } = useQuery<InformeDeCumplimiento>({
    queryKey: ['grc-compliance-report'], queryFn: () => grcApi.complianceReport().then(r => r.data),
  })
  const descargar = async () => {
    setBajando(true)
    try { downloadBlob((await grcApi.complianceReportSigned()).data, `compliance-report-${new Date().toISOString().slice(0, 10)}.json`) }
    catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) } finally { setBajando(false) }
  }
  const valor = (v: unknown): string => v === null || v === undefined ? '—' : typeof v === 'object' ? JSON.stringify(v) : String(v)
  return (
    <div>
      <div className="grc-row-21">
        <p className="grc-text-2">{t('grc.informe_intro')}</p>
        <Button size="sm" variant="secondary" icon={<RefreshCw size={14} />} onClick={() => refetch()} loading={isFetching}>{t('grc.informe_regenerar')}</Button>
        <Button size="sm" onClick={descargar} loading={bajando}>{t('grc.informe_descargar')}</Button>
        <Button size="sm" variant="ghost" onClick={() => window.print()}>{t('grc.informe_imprimir')}</Button>
      </div>
      {!data ? <div className="grc-box-8"><Spinner /></div> : (
        <>
          <div className="ds-grid-stats grc-mb">
            <KpiCard label={t('grc.informe_estado_pass')} value={data.summary.pass ?? 0} />
            <KpiCard label={t('grc.informe_estado_attention')} value={data.summary.attention ?? 0} danger={(data.summary.attention ?? 0) > 0} />
            <KpiCard label={t('grc.informe_estado_info')} value={data.summary.info ?? 0} />
            <KpiCard label={t('grc.informe_estado_not_measurable')} value={data.summary.not_measurable ?? 0} />
          </div>
          <div className="grc-box-12">
            {t('grc.informe_generado', { fecha: fmtDateTime(data.generated_at) })}
          </div>
          <TablaSimple claseTabla="u-table-sm">
            <thead><tr className="grc-row-23">
              <th className="grc-th-5">{t('grc.informe_col_estado')}</th><th className="grc-th-5">{t('grc.informe_col_control')}</th>
              <th className="grc-th-5">{t('grc.informe_col_medido')}</th><th className="grc-th-5">{t('grc.informe_col_marcos')}</th>
            </tr></thead>
            <tbody>
              {data.controls.map(c => (
                <tr key={c.id} className="grc-row-24">
                  <td className="grc-td-10 grc-page-e4" style={{ '--grc-page-color': COLOR_CONTROL[c.status] } as CSSProperties}>{t(`grc.informe_estado_${c.status}`)}</td>
                  <td className="grc-td-5">
                    <div className="u-600">{t(`grc.informe_control_${c.id}`)}</div>
                    <div className="u-text3-xs">{c.source}</div>
                  </td>
                  <td className="grc-td-11">
                    {Object.entries(c.measured).map(([k, v]) => <div key={k}>{k}: {valor(v)}</div>)}
                  </td>
                  <td className="grc-td-12">{c.frameworks.join(' · ') || '—'}</td>
                </tr>
              ))}
            </tbody>
          </TablaSimple>
        </>
      )}
    </div>
  )
}

/** ¿Puede este usuario hacer esto y qué capa lo decide? (revisión 2026-11) */
export function ExplicarAccesoTab() {
  const t = useAppT()
  const toast = useToast()
  const [usuario, setUsuario] = useState('')
  const [metodo, setMetodo] = useState('GET')
  // No es una URL que pida el cliente: es la ruta del servidor que se quiere explicar (las de `rutas` llevan el mismo prefijo).
  const [camino, setCamino] = useState(`${PREFIJO_API_SERVIDOR}/projects`)
  const [res, setRes] = useState<Explicacion | null>(null)
  const [cargando, setCargando] = useState(false)
  // 23-11-2026 (04 A8): lista compartida de personas.
  const { data: usuarios = [] } = useListaDeUsuarios()
  const { data: rutas = [] } = useQuery<{ method: string; path: string }[]>({
    queryKey: ['grc-explainer-routes'], queryFn: () => grcApi.explainerRoutes().then(r => r.data),
  })
  const explicar = async () => {
    if (!usuario || !camino.trim()) return
    setCargando(true)
    try { setRes((await grcApi.explainAccess({ user_id: usuario, method: metodo, path: camino.trim() })).data) }
    catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) } finally { setCargando(false) }
  }
  
  const detalle = (c: CapaDeAcceso) => {
    const extra = ['module', 'action', 'role', 'required', 'level', 'project_id', 'guards', 'resource_type', 'allowed_methods']
      .filter(k => c[k] !== undefined && c[k] !== null && c[k] !== '')
      .map(k => `${k}: ${Array.isArray(c[k]) ? (c[k] as string[]).join(', ') : String(c[k])}`)
    const texto = t(`grc.acceso_detalle_${c.detail}`)
    return (texto.startsWith('grc.') ? c.detail : texto) + (extra.length ? ` — ${extra.join(' · ')}` : '')
  }
  return (
    <div>
      <p className="grc-text-3">{t('grc.acceso_intro')}</p>
      <div className="u-wrap-center-8">
        <Select suelto placeholder={false} aria-label={t('grc.acceso_usuario')} value={usuario} onChange={e => setUsuario(e.target.value)} className="grc-page-e16">
          <option value="">{t('grc.acceso_usuario')}</option>
          {usuarios.map(u => <option key={u.id} value={u.id}>{u.full_name || (esFichaCompleta(u) ? u.email : '')} {u.role ? `(${u.role})` : ''}</option>)}
        </Select>
        <Select suelto placeholder={false} aria-label="HTTP" value={metodo} onChange={e => setMetodo(e.target.value)} className="grc-page-e22">
          {['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map(m => <option key={m}>{m}</option>)}
        </Select>
        <Input aria-label={t('grc.acceso_ruta')} list="grc-rutas" value={camino} onChange={e => setCamino(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') explicar() }} inputClassName="ds-codigo grc-page-e17" />
        <datalist id="grc-rutas">
          {rutas.filter(r => r.method === metodo).slice(0, 3000).map(r => <option key={r.path} value={r.path} aria-label={r.path} />)}
        </datalist>
        <Button onClick={explicar} disabled={!usuario} loading={cargando}>{t('grc.acceso_explicar')}</Button>
      </div>
      <div className="grc-box-13">{t('grc.acceso_ayuda_ruta')}</div>
      {res && (
        <div className="grc-box-14">
          <div role="status" className="grc-box-15 grcpage-sx17 grc-page-e13" style={{ '--grc-page-border': `1px solid ${COLOR_VEREDICTO[res.verdict]}`, '--grc-page-background': alpha(COLOR_VEREDICTO[res.verdict], '12') } as CSSProperties}>
            <div className="grc-box-16 grc-page-e4" style={{ '--grc-page-color': COLOR_VEREDICTO[res.verdict] } as CSSProperties}>
              {t(`grc.acceso_veredicto_${res.verdict}`)}{res.decided_by ? ` — ${t(`grc.acceso_capa_${res.decided_by}`)}` : ''}
            </div>
            <div className="ds-codigo grc-box-17">
              {res.method} {res.template || res.path}
            </div>
          </div>
          <ol className="grc-box-18">
            {res.layers.map(c => (
              <li key={c.layer} className={`grc-row-25 ${c.verdict === 'not_applicable' ? 'grcpage-sx18' : 'grcpage-sx7'}`}>
                <span className="grc-label-14 grc-page-e4" style={{ '--grc-page-color': COLOR_VEREDICTO[c.verdict] } as CSSProperties}>
                  {t(`grc.acceso_estado_${c.verdict}`)}
                </span>
                <span className="grc-label-15">{t(`grc.acceso_capa_${c.layer}`)}</span>
                <span className="u-text2-sm">{detalle(c)}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  )
}

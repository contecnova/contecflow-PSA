/**
 * Pestaña Riesgo → Superficies (22-11-2026): recuento por superficie (interna,
 * Internet, contenedores, VMs en la nube, serverless), lista de vulnerabilidades
 * filtrable y agrupable por CVE o por activo, columnas configurables, vistas
 * guardadas (propias o compartidas), «Detectar exposición» y marcar la
 * exposición de un CI.
 *
 * Diseño: docs/CMDB_SOFTWARE_Y_VULNERABILIDADES.md §11.7.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Columns3, Globe, Radar, Save, ShieldCheck, Trash2 } from 'lucide-react'
import { useAppT } from '../../../../i18n/AppLangContext'
import { useToast } from '../../../../context/ToastContext'
import { useAuth } from '../../../../context/AuthContext'
import { confirmar } from '../../../../context/ConfirmContext'
import { cmdbRiesgoApi } from '../../../../services/api/cmdbRiesgo'
import type { Agrupacion, Exposicion, FiltroDeSuperficie, HallazgoDeSuperficie, Superficie, VistaGuardada } from '../../../../services/api/cmdbRiesgo'
import { Buscador, Button, Checkbox, EmptyState, IconButton, Input, Modal, Section, Segmentado, Select, Spinner, StatusBadge, TablaSimple } from '../../../ui'
import Pagination from '../../../ui/Pagination'
import { ESTADO_KIND, Opciones, Semaforo, SeveridadBadge, VersionTexto, useErr, useEtiquetaSw, useMetaSw } from '../comun'
import DetalleDeHallazgo from '../DetalleDeHallazgo'
import { ControlModal } from './Controles'
import type { HallazgoBreve } from './Controles'
import { redondeo, useEtiquetaSwr } from './comunRiesgo'

const TAMANO = 50
const SUPERFICIES: Superficie[] = ['internal', 'internet', 'container', 'cloud_vm', 'serverless']
const COLUMNAS = ['riesgo', 'aviso', 'severidad', 'cvss', 'epss', 'sla', 'software', 'maquina', 'superficie', 'detectado_por', 'controles', 'intentos', 'estado'] as const
type Columna = typeof COLUMNAS[number]
const POR_DEFECTO: Columna[] = ['riesgo', 'aviso', 'severidad', 'cvss', 'sla', 'software', 'maquina', 'superficie', 'detectado_por', 'estado']
const EXPOSICIONES: Exposicion[] = ['internet', 'internal', 'isolated']

export default function Superficies() {
  const t = useAppT()
  const e = useEtiquetaSwr()
  const es = useEtiquetaSw()
  const toast = useToast()
  const qc = useQueryClient()
  const err = useErr()
  const { puede } = useAuth()
  const gestiona = puede('software.gestionar')
  const metaSw = useMetaSw()
  const [superficie, setSuperficie] = useState('')
  const [agrupar, setAgrupar] = useState<Agrupacion>('none')
  const [severidad, setSeveridad] = useState('')
  const [estado, setEstado] = useState('live')
  const [kev, setKev] = useState(false)
  const [q, setQ] = useState('')
  const [pagina, setPagina] = useState(1)
  const [columnas, setColumnas] = useState<Columna[]>(POR_DEFECTO)
  const [verColumnas, setVerColumnas] = useState(false)
  const [vistaId, setVistaId] = useState('')
  const [guardando, setGuardando] = useState(false)
  const [elegidos, setElegidos] = useState<Record<string, HallazgoBreve>>({})
  const [control, setControl] = useState(false)
  const [abierto, setAbierto] = useState<string | null>(null)

  const filtro: FiltroDeSuperficie = { surface: superficie || undefined, severity: severidad || undefined, status: estado || undefined, kev: kev || undefined, q: q.trim() || undefined, page: pagina, page_size: TAMANO }
  const clave = ['swr', 'superficie-lista', agrupar, superficie, severidad, estado, kev, q.trim(), pagina]
  const recuento = useQuery({ queryKey: ['swr', 'superficies'], queryFn: cmdbRiesgoApi.superficies })
  const lista = useQuery({ queryKey: [...clave, 'none'], queryFn: () => cmdbRiesgoApi.hallazgos({ ...filtro, group_by: 'none' }), enabled: agrupar === 'none' })
  const porCve = useQuery({ queryKey: [...clave, 'cve'], queryFn: () => cmdbRiesgoApi.hallazgosPorCve(filtro), enabled: agrupar === 'cve' })
  const porActivo = useQuery({ queryKey: [...clave, 'asset'], queryFn: () => cmdbRiesgoApi.hallazgosPorActivo(filtro), enabled: agrupar === 'asset' })
  const vistas = useQuery({ queryKey: ['swr', 'vistas'], queryFn: cmdbRiesgoApi.vistas })
  const detectar = useMutation({
    mutationFn: cmdbRiesgoApi.detectarExposicion,
    onSuccess: r => { toast.success(t('swr.exposicion_detectada', { revisados: r.checked, internet: r.set_internet, igual: r.unchanged })); qc.invalidateQueries({ queryKey: ['swr'] }) },
    onError: err,
  })
  const marcar = useMutation({
    mutationFn: ({ ciId, valor }: { ciId: string; valor: Exposicion | null }) => cmdbRiesgoApi.marcarExposicionDeCi(ciId, valor),
    onSuccess: () => { toast.success(t('swr.guardado')); qc.invalidateQueries({ queryKey: ['swr'] }) },
    onError: err,
  })
  const borrarVista = useMutation({
    mutationFn: cmdbRiesgoApi.borrarVista,
    onSuccess: () => { setVistaId(''); qc.invalidateQueries({ queryKey: ['swr', 'vistas'] }) },
    onError: err,
  })

  const cambia = <T,>(fn: (v: T) => void) => (v: T) => { fn(v); setPagina(1) }
  const aplicarVista = (v: VistaGuardada) => {
    const f = v.filters ?? {}
    setSuperficie(v.surface ?? '')
    setAgrupar((v.group_by ?? 'none') as Agrupacion)
    setSeveridad(f.severity ?? '')
    setEstado(f.status ?? 'live')
    setKev(f.kev === 'true')
    setQ(f.q ?? '')
    const cols = (v.columns ?? []).filter((c): c is Columna => (COLUMNAS as readonly string[]).includes(c))
    setColumnas(cols.length ? cols : POR_DEFECTO)
    setPagina(1)
  }
  const vistaActual = (vistas.data ?? []).find(v => v.id === vistaId)
  const ver = (c: Columna) => columnas.includes(c)
  const actual = agrupar === 'none' ? lista : agrupar === 'cve' ? porCve : porActivo
  const total = actual.data?.total ?? 0
  const items = lista.data?.items ?? []
  const nElegidos = Object.keys(elegidos).length
  const alternar = (h: HallazgoDeSuperficie, si: boolean) => {
    const n = { ...elegidos }
    if (si) n[h.id] = { id: h.id, vuln_id: h.vuln_id, product_name: h.product_name, ci_name: h.ci_name }
    else delete n[h.id]
    setElegidos(n)
  }

  return (
    <div className="u-stack-20">
      {recuento.isLoading ? <Spinner size={16} /> : recuento.data && (
        <div className="swr-superficies">
          {SUPERFICIES.map(s => {
            const r = recuento.data?.[s] ?? { assets: 0, findings: 0, critical_high: 0 }
            return (
              <Button key={s} variant="secondary" className="swr-superficie" aria-pressed={superficie === s} onClick={() => cambia(setSuperficie)(superficie === s ? '' : s)}>
                <span className="ds-eyebrow">{e('superficie', s)}</span>
                <span className="swr-superficie__n">{r.findings}</span>
                <span className="u-text3-xs">{t('swr.superficie_resumen', { activos: r.assets, graves: r.critical_high })}</span>
              </Button>
            )
          })}
        </div>
      )}

      <Section title={t('swr.vulnerabilidades')} subtitle={t('swr.vulnerabilidades_desc')}
        actions={<div className="u-wrap-8">
          {gestiona && <Button size="sm" variant="secondary" icon={<Radar size={14} />} loading={detectar.isPending} onClick={() => detectar.mutate()}>{t('swr.detectar_exposicion')}</Button>}
          {gestiona && agrupar === 'none' && <Button size="sm" variant="secondary" icon={<ShieldCheck size={14} />} disabled={nElegidos === 0} onClick={() => setControl(true)}>{t('swr.control_sobre', { n: nElegidos })}</Button>}
        </div>}>
        <div className="u-stack-12">
          <div className="sdm-form">
            <Buscador label={t('swr.buscar')} value={q} placeholder={t('swr.buscar_ph')} onChange={v => cambia(setQ)(v)} />
            <label className="sdm-field"><span>{t('swr.superficie')}</span>
              <Select suelto placeholder={false} value={superficie} onChange={ev => cambia(setSuperficie)(ev.target.value)}>
                <option value="">{t('swr.todas')}</option>
                {SUPERFICIES.map(s => <option key={s} value={s}>{e('superficie', s)}</option>)}
              </Select></label>
            <label className="sdm-field"><span>{t('sw.severidad')}</span>
              <Select suelto placeholder={false} value={severidad} onChange={ev => cambia(setSeveridad)(ev.target.value)}>
                <Opciones valores={metaSw.data?.severities} catalogo="sev" todos={t('swr.todas')} /></Select></label>
            <label className="sdm-field"><span>{t('swr.estado')}</span>
              <Select suelto placeholder={false} value={estado} onChange={ev => cambia(setEstado)(ev.target.value)}>
                <option value="live">{t('swr.vivos')}</option>
                <option value="">{t('swr.todos')}</option>
                {(metaSw.data?.finding_statuses ?? []).map(s => <option key={s} value={s}>{es('estado', s)}</option>)}
              </Select></label>
            <div className="u-wrap-10 sw-casillas"><Checkbox checked={kev} onChange={cambia(setKev)} label={t('swr.solo_kev')} /></div>
          </div>
          <div className="u-wrap-8">
            <Segmentado aria-label={t('swr.agrupar')} valor={agrupar} onChange={v => cambia(setAgrupar)(v as Agrupacion)}
              opciones={(['none', 'cve', 'asset'] as const).map(g => ({ valor: g, etiqueta: t(`swr.agrupar_${g}`) }))} />
            {agrupar === 'none' && <Button size="sm" variant="ghost" icon={<Columns3 size={14} />} aria-expanded={verColumnas} onClick={() => setVerColumnas(!verColumnas)}>{t('swr.columnas')}</Button>}
            <Select suelto placeholder={false} className="sdm-select-accion" aria-label={t('swr.vistas')} value={vistaId}
              onChange={ev => { setVistaId(ev.target.value); const v = (vistas.data ?? []).find(x => x.id === ev.target.value); if (v) aplicarVista(v) }}>
              <option value="">{t('swr.vista_elige')}</option>
              {(vistas.data ?? []).map(v => <option key={v.id} value={v.id}>{v.name}{v.shared ? ` · ${t('swr.compartida')}` : ''}</option>)}
            </Select>
            {gestiona && <Button size="sm" variant="secondary" icon={<Save size={14} />} onClick={() => setGuardando(true)}>{t('swr.guardar_vista')}</Button>}
            {vistaActual?.mine && <IconButton ariaLabel={t('swr.borrar_vista')} onClick={async () => { if (await confirmar({ message: t('swr.borrar_vista_confirmar', { nombre: vistaActual.name }), danger: true })) borrarVista.mutate(vistaActual.id) }}><Trash2 size={14} /></IconButton>}
          </div>
          {verColumnas && agrupar === 'none' && (
            <div className="swr-columnas" role="group" aria-label={t('swr.columnas')}>
              {COLUMNAS.map(c => <Checkbox key={c} checked={ver(c)} label={t(`swr.colv_${c}`)}
                onChange={si => setColumnas(si ? COLUMNAS.filter(x => x === c || columnas.includes(x)) : columnas.filter(x => x !== c))} />)}
            </div>
          )}

          {actual.isLoading ? <Spinner /> : total === 0 ? <EmptyState icon={<Globe size={28} />} title={t('swr.sin_vulnerabilidades')} /> : agrupar === 'none' ? (
            <TablaSimple etiqueta={t('swr.vulnerabilidades')} densidad="compacta">
              <thead><tr>
                {gestiona && <th><span className="u-sr-only">{t('swr.elegir')}</span></th>}
                {ver('riesgo') && <th className="sw-num">{t('swr.colv_riesgo')}</th>}
                {ver('aviso') && <th>{t('swr.colv_aviso')}</th>}
                {ver('severidad') && <th>{t('swr.colv_severidad')}</th>}
                {ver('cvss') && <th className="sw-num">CVSS</th>}
                {ver('epss') && <th className="sw-num">EPSS</th>}
                {ver('sla') && <th>{t('swr.colv_sla')}</th>}
                {ver('software') && <th>{t('swr.colv_software')}</th>}
                {ver('maquina') && <th>{t('swr.colv_maquina')}</th>}
                {ver('superficie') && <th>{t('swr.colv_superficie')}</th>}
                {ver('detectado_por') && <th>{t('swr.colv_detectado_por')}</th>}
                {ver('controles') && <th className="sw-num">{t('swr.colv_controles')}</th>}
                {ver('intentos') && <th className="sw-num">{t('swr.colv_intentos')}</th>}
                {ver('estado') && <th>{t('swr.colv_estado')}</th>}
              </tr></thead>
              <tbody>{items.map(h => (
                <tr key={h.id}>
                  {gestiona && <td><Checkbox checked={!!elegidos[h.id]} onChange={si => alternar(h, si)} aria-label={t('swr.elegir_hallazgo', { vuln: h.vuln_id ?? '' })} /></td>}
                  {ver('riesgo') && <td className="sw-num u-600">{redondeo(h.risk_points)}</td>}
                  {ver('aviso') && <td>
                    <Button variant="link" className="sw-enlace u-mono" onClick={() => setAbierto(h.id)}>{h.vuln_id ?? '—'}</Button>
                    {h.kev && <> <StatusBadge kind="danger" caps={false} title={t('sw.kev_ayuda')}>KEV</StatusBadge></>}
                    {h.title && <div className="u-text3-xs sw-recorte" title={h.title}>{h.title}</div>}
                  </td>}
                  {ver('severidad') && <td><SeveridadBadge s={h.severity} /></td>}
                  {ver('cvss') && <td className="sw-num">{h.cvss_score != null ? h.cvss_score.toFixed(1) : '—'}</td>}
                  {ver('epss') && <td className="sw-num">{h.epss_score != null ? `${(h.epss_score * 100).toFixed(1)} %` : '—'}</td>}
                  {ver('sla') && <td><Semaforo h={h} /></td>}
                  {ver('software') && <td>{h.product_name ?? '—'} <span className="u-text3-xs"><VersionTexto v={h.affected_version} /></span></td>}
                  {ver('maquina') && <td>{h.ci_name ?? h.instance_name ?? '—'}</td>}
                  {ver('superficie') && <td>{e('superficie', h.surface)}</td>}
                  {ver('detectado_por') && <td><div className="u-wrap-6">{(h.detected_by ?? []).map(d => <StatusBadge key={d} caps={false}>{e('fuente', d)}</StatusBadge>)}</div></td>}
                  {ver('controles') && <td className="sw-num">{h.controls_active || '—'}</td>}
                  {ver('intentos') && <td className="sw-num">{h.exploit_attempts || '—'}</td>}
                  {ver('estado') && <td><StatusBadge kind={ESTADO_KIND[h.status] ?? 'neutral'} caps={false}>{es('estado', h.status)}</StatusBadge></td>}
                </tr>
              ))}</tbody>
            </TablaSimple>
          ) : agrupar === 'cve' ? (
            <TablaSimple etiqueta={t('swr.agrupar_cve')} densidad="compacta">
              <thead><tr>
                <th>{t('swr.colv_aviso')}</th><th>{t('swr.colv_severidad')}</th><th className="sw-num">CVSS</th><th className="sw-num">EPSS</th>
                <th className="sw-num">{t('swr.activos')}</th><th className="sw-num">{t('swr.col_hallazgos')}</th><th className="sw-num">{t('swr.peor_riesgo')}</th><th>{t('swr.colv_software')}</th>
              </tr></thead>
              <tbody>{(porCve.data?.items ?? []).map(g => (
                <tr key={g.vulnerability_id}>
                  <td><span className="u-mono">{g.vuln_id ?? '—'}</span>{g.kev && <> <StatusBadge kind="danger" caps={false}>KEV</StatusBadge></>}
                    {g.title && <div className="u-text3-xs sw-recorte" title={g.title}>{g.title}</div>}</td>
                  <td><SeveridadBadge s={g.severity} /></td>
                  <td className="sw-num">{g.cvss_score != null ? g.cvss_score.toFixed(1) : '—'}</td>
                  <td className="sw-num">{g.epss_score != null ? `${(g.epss_score * 100).toFixed(1)} %` : '—'}</td>
                  <td className="sw-num">{g.assets}</td><td className="sw-num">{g.findings}</td>
                  <td className="sw-num u-600">{redondeo(g.max_risk)}</td>
                  <td className="u-text3-xs">{g.products.join(', ') || '—'}</td>
                </tr>
              ))}</tbody>
            </TablaSimple>
          ) : (
            <TablaSimple etiqueta={t('swr.agrupar_asset')} densidad="compacta">
              <thead><tr>
                <th>{t('swr.colv_maquina')}</th><th>{t('swr.colv_superficie')}</th><th>{t('swr.exposicion')}</th>
                <th className="sw-num">{t('swr.col_hallazgos')}</th><th className="sw-num">{es('sev', 'critical')}</th><th className="sw-num">{es('sev', 'high')}</th><th className="sw-num">{t('swr.peor_riesgo')}</th>
              </tr></thead>
              <tbody>{(porActivo.data?.items ?? []).map(g => (
                <tr key={g.ci_id}>
                  <td>{g.ci_name ?? '—'}{g.ci_hostname && <div className="u-text3-xs u-mono">{g.ci_hostname}</div>}</td>
                  <td>{e('superficie', g.surface)}</td>
                  <td>{gestiona ? (
                    <Select suelto placeholder={false} tamano="sm" aria-label={t('swr.exposicion_de', { nombre: g.ci_name ?? '' })} value={g.exposure ?? ''}
                      disabled={marcar.isPending} onChange={ev => marcar.mutate({ ciId: g.ci_id, valor: (ev.target.value || null) as Exposicion | null })}>
                      <option value="">{t('swr.exposicion_auto')}</option>
                      {EXPOSICIONES.map(x => <option key={x} value={x}>{e('exposicion', x)}</option>)}
                    </Select>
                  ) : e('exposicion', g.exposure)}</td>
                  <td className="sw-num">{g.findings}</td><td className="sw-num">{g.critical}</td><td className="sw-num">{g.high}</td>
                  <td className="sw-num u-600">{redondeo(g.max_risk)}</td>
                </tr>
              ))}</tbody>
            </TablaSimple>
          )}
          <Pagination page={pagina} totalPages={Math.max(1, Math.ceil(total / TAMANO))} onChange={setPagina} total={total} pageSize={TAMANO} />
        </div>
      </Section>

      {guardando && <GuardarVistaModal onClose={() => setGuardando(false)} onSaved={v => { setGuardando(false); setVistaId(v.id) }}
        datos={{ surface: superficie || null, group_by: agrupar, columns: columnas,
          filters: Object.fromEntries(Object.entries({ severity: severidad, status: estado, kev: kev ? 'true' : '', q: q.trim() }).filter(([, v]) => v)) }} />}
      {control && <ControlModal inicial={Object.values(elegidos)} onClose={() => setControl(false)} onSaved={() => { setControl(false); setElegidos({}) }} />}
      {abierto && <DetalleDeHallazgo id={abierto} onClose={() => setAbierto(null)} />}
    </div>
  )
}

function GuardarVistaModal({ datos, onClose, onSaved }: {
  datos: { surface: string | null; group_by: Agrupacion; columns: string[]; filters: Record<string, string> }
  onClose: () => void; onSaved: (v: VistaGuardada) => void
}) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const err = useErr()
  const [nombre, setNombre] = useState('')
  const [compartida, setCompartida] = useState(false)
  const guardar = useMutation({
    mutationFn: () => cmdbRiesgoApi.crearVista({ name: nombre.trim(), shared: compartida, ...datos }),
    onSuccess: v => { toast.success(t('swr.vista_guardada')); qc.invalidateQueries({ queryKey: ['swr', 'vistas'] }); onSaved(v) },
    onError: err,
  })
  return (
    <Modal open onClose={onClose} title={t('swr.guardar_vista')}>
      <div className="u-stack-12">
        <Input label={t('swr.col_nombre')} value={nombre} autoFocus onChange={ev => setNombre(ev.target.value)} />
        <Checkbox checked={compartida} onChange={setCompartida} label={t('swr.compartir_vista')} ayuda={t('swr.compartir_vista_ayuda')} />
        <div className="u-actions-10">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button disabled={nombre.trim().length < 2} loading={guardar.isPending} onClick={() => guardar.mutate()}>{t('common.save')}</Button>
        </div>
      </div>
    </Modal>
  )
}

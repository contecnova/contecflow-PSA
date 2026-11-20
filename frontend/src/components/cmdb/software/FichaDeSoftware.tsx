/**
 * Ficha de un software del catálogo (19-11-2026): resumen e identificadores
 * (purl, CPE), versiones con fin de soporte, composición (árbol de
 * dependencias), instancias con su configuración, dónde se usa,
 * vulnerabilidades, licencias de Activos, líneas base y grafo.
 *
 * También exporta los formularios de alta/edición de software y de instancia,
 * que usan las pestañas de la CMDB. Diseño: docs/CMDB_SOFTWARE_Y_VULNERABILIDADES.md.
 */
import { lazy, Suspense, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, FileUp, Layers, Link2, Plus, ShieldCheck, Trash2, Unlink } from 'lucide-react'
import { useAppT } from '../../../i18n/AppLangContext'
import { useToast } from '../../../context/ToastContext'
import { useAuth } from '../../../context/AuthContext'
import { confirmar } from '../../../context/ConfirmContext'
import { fmtDate, fmtDateTime } from '../../../utils/helpers'
import { FULL_LIST_SIZE } from '../../../constants/pagination'
import { cmdbApi, licensesApi, usersApi } from '../../../services/api'
import { cmdbSoftwareApi } from '../../../services/api/cmdbSoftware'
import type { SdCi } from '../../../services/api/tipos-sd'
import type { InstanciaSw, LineaBase, NodoDeArbol, ProductoSw, ProductoSwIn, ReglaDeLineaBase, VersionSw } from '../../../services/api/cmdbSoftware'
import type { RawEdge, RawNode } from '../CMDBTopologyGraph'
import { Button, Checkbox, DateInput, EmptyState, IconButton, Modal, Section, Select, Spinner, StatusBadge, TablaSimple, Tabs } from '../../ui'
import { BotonFichero, CicloBadge, ListaKv, Opciones, SeveridadBadge, VersionTexto, useAvisoDeImportacion, useErr, useEtiquetaSw, useMetaSw, valorLegible } from './comun'
import { TablaHallazgos, TablaInstancias } from './tablas'
import DetalleDeHallazgo from './DetalleDeHallazgo'
import '../../servicedesk/sdMercado.css'
import './software.css'

const CMDBTopologyGraph = lazy(() => import('../CMDBTopologyGraph'))

const nulo = (v: string) => (v.trim() ? v.trim() : null)

export default function FichaDeSoftware({ id, onClose }: { id: string; onClose: () => void }) {
  const t = useAppT()
  const e = useEtiquetaSw()
  const toast = useToast()
  const qc = useQueryClient()
  const err = useErr()
  const { puede } = useAuth()
  const gestiona = puede('software.gestionar')
  const [pestana, setPestana] = useState('resumen')
  const [editando, setEditando] = useState(false)
  const { data: f, isLoading } = useQuery({ queryKey: ['sw', 'ficha', id], queryFn: () => cmdbSoftwareApi.ficha(id) })
  const retirar = useMutation({
    mutationFn: () => cmdbSoftwareApi.retirarProducto(id),
    onSuccess: () => { toast.success(t('sw.retirado')); qc.invalidateQueries({ queryKey: ['sw'] }); onClose() },
    onError: err,
  })
  const p = f?.product
  const hallazgos = Object.values(f?.findings_by_severity ?? {}).reduce((a, b) => a + (b ?? 0), 0)
  return (
    <Modal open size="xl" onClose={onClose} title={p?.name ?? t('sw.software')}
      subtitle={p ? [p.vendor_name, e('cat', p.category), e('origen', p.origin)].filter(Boolean).join(' · ') : undefined}>
      {isLoading || !f || !p ? <Spinner /> : (
        <div className="u-stack-14">
          <Tabs ariaLabel={p.name} active={pestana} onChange={setPestana} items={[
            { id: 'resumen', label: t('sw.resumen') },
            { id: 'versiones', label: t('sw.versiones'), count: f.versions.length },
            { id: 'composicion', label: t('sw.composicion') },
            { id: 'instancias', label: t('sw.instancias'), count: f.instances.length },
            { id: 'donde', label: t('sw.donde_se_usa'), count: f.used_in.length },
            { id: 'vulns', label: t('sw.vulnerabilidades'), count: hallazgos },
            { id: 'licencias', label: t('sw.licencias'), count: f.licenses.length },
            { id: 'lineas', label: t('sw.lineas_base'), count: f.baselines.length },
            { id: 'grafo', label: t('sw.grafo') },
          ]} />
          {pestana === 'resumen' && (
            <div className="u-stack-12">
              <div className="u-wrap-8">
                <StatusBadge caps={false} kind={p.lifecycle_status === 'retired' ? 'neutral' : p.lifecycle_status === 'deprecated' ? 'warning' : 'success'}>{e('ciclo', p.lifecycle_status)}</StatusBadge>
                <StatusBadge caps={false}>{t('sw.criticidad')}: {e('crit', p.criticality)}</StatusBadge>
                {(['critical', 'high', 'medium', 'low'] as const).filter(s => f.findings_by_severity[s]).map(s => (
                  <StatusBadge key={s} caps={false} kind={s === 'critical' ? 'danger' : s === 'high' ? 'orange' : s === 'medium' ? 'warning' : 'info'}>{e('sev', s)}: {f.findings_by_severity[s]}</StatusBadge>
                ))}
              </div>
              {p.description && <div className="u-text2-sm sdm-pre">{p.description}</div>}
              <ListaKv filas={[
                [t('sw.fabricante'), p.vendor_name],
                [t('sw.categoria'), e('cat', p.category)],
                [t('sw.origen'), e('origen', p.origin)],
                [t('sw.distribucion'), p.distribution ? e('dist', p.distribution) : '—'],
                [t('sw.licencia'), p.license_spdx ? <span className="u-mono">{p.license_spdx}</span> : '—'],
                ['purl', p.purl ? <span className="u-mono sdm-wrap">{p.purl}</span> : '—'],
                ['CPE', p.cpe ? <span className="u-mono sdm-wrap">{p.cpe}</span> : '—'],
                [t('sw.clave_de_cruce'), <span key="k" className="u-mono sdm-wrap">{p.match_key}</span>],
                [t('sw.alias'), p.aliases.length ? p.aliases.join(', ') : '—'],
                [t('sw.responsable'), p.owner_name ?? '—'],
                [t('sw.repositorio'), p.repository_url ? <a href={p.repository_url} target="_blank" rel="noopener noreferrer" className="sdm-wrap">{p.repository_url}</a> : '—'],
                [t('sw.web'), p.homepage ? <a href={p.homepage} target="_blank" rel="noopener noreferrer" className="sdm-wrap">{p.homepage}</a> : '—'],
                [t('sw.alta'), fmtDateTime(p.created_at)],
                [t('sw.actualizado'), fmtDateTime(p.updated_at)],
              ]} />
              {gestiona && (
                <div className="u-actions-10">
                  {p.is_active && <Button variant="ghost" loading={retirar.isPending}
                    onClick={async () => { if (await confirmar({ message: t('sw.retirar_confirmar', { nombre: p.name }), danger: true })) retirar.mutate() }}>{t('sw.retirar')}</Button>}
                  <Button onClick={() => setEditando(true)}>{t('sw.editar')}</Button>
                </div>
              )}
            </div>
          )}
          {pestana === 'versiones' && <Versiones producto={p} versiones={f.versions} />}
          {pestana === 'composicion' && <Composicion versiones={f.versions} />}
          {pestana === 'instancias' && <Instancias producto={p} instancias={f.instances} />}
          {pestana === 'donde' && (f.used_in.length === 0 ? <EmptyState icon={<Layers size={28} />} title={t('sw.no_se_usa_en')} /> : (
            <TablaSimple etiqueta={t('sw.donde_se_usa')}>
              <thead><tr><th>{t('sw.software')}</th><th>{t('sw.version')}</th><th>{t('sw.version_del_componente')}</th><th>{t('sw.relacion')}</th><th>{t('sw.ciclo_vida')}</th></tr></thead>
              <tbody>{f.used_in.map(u => (
                <tr key={`${u.version_id}-${u.product_id}-${u.component_version ?? ''}`}>
                  <td>{u.product_name}</td><td className="u-mono">{u.version}</td>
                  <td className="u-mono">{u.component_version ?? '—'} · {t(u.direct ? 'sw.directo' : 'sw.transitivo')}</td>
                  <td>{e('rel_comp', u.relation)}</td><td><CicloBadge c={u.lifecycle} fecha={u.eol_date} /></td>
                </tr>
              ))}</tbody>
            </TablaSimple>
          ))}
          {pestana === 'vulns' && <VulnsDelProducto productId={p.id} />}
          {pestana === 'licencias' && <Licencias producto={p} licencias={f.licenses} />}
          {pestana === 'lineas' && <LineasBase producto={p} lineas={f.baselines} />}
          {pestana === 'grafo' && <Grafo productId={p.id} nombre={p.name} />}
        </div>
      )}
      {editando && p && <EditarProductoModal producto={p} onClose={() => setEditando(false)} onSaved={() => { setEditando(false); qc.invalidateQueries({ queryKey: ['sw'] }) }} />}
    </Modal>
  )
}

// ── Alta / edición de software ────────────────────────────────────────────────

export function EditarProductoModal({ producto, onClose, onSaved }: { producto: ProductoSw | null; onClose: () => void; onSaved: (p: ProductoSw) => void }) {
  const t = useAppT()
  const err = useErr()
  const meta = useMetaSw()
  const usuarios = useQuery({ queryKey: ['users'], queryFn: () => usersApi.list().then(r => r.data) })
  const [d, setD] = useState({
    name: producto?.name ?? '', vendor_name: producto?.vendor_name ?? '', category: producto?.category ?? 'application',
    origin: producto?.origin ?? 'purchased', distribution: producto?.distribution ?? '', criticality: producto?.criticality ?? 'medium',
    lifecycle_status: producto?.lifecycle_status ?? 'active', license_spdx: producto?.license_spdx ?? '', purl: producto?.purl ?? '',
    cpe: producto?.cpe ?? '', owner_user_id: producto?.owner_user_id ?? '', repository_url: producto?.repository_url ?? '',
    description: producto?.description ?? '',
  })
  const set = (k: keyof typeof d) => (v: string) => setD(x => ({ ...x, [k]: v }))
  const guardar = useMutation({
    mutationFn: () => {
      const datos: ProductoSwIn = {
        name: d.name.trim(), vendor_name: nulo(d.vendor_name), category: d.category, origin: d.origin,
        distribution: nulo(d.distribution), criticality: d.criticality, lifecycle_status: d.lifecycle_status,
        license_spdx: nulo(d.license_spdx), purl: nulo(d.purl), cpe: nulo(d.cpe), owner_user_id: nulo(d.owner_user_id),
        repository_url: nulo(d.repository_url), description: nulo(d.description),
      }
      return producto ? cmdbSoftwareApi.editarProducto(producto.id, datos) : cmdbSoftwareApi.crearProducto(datos)
    },
    onSuccess: onSaved, onError: err,
  })
  const texto = (k: keyof typeof d, etiqueta: string, ph?: string, mono?: boolean) => (
    <label className="sdm-field"><span>{etiqueta}</span>
      <input className={`ds-input${mono ? ' u-mono' : ''}`} value={d[k]} placeholder={ph} onChange={ev => set(k)(ev.target.value)} /></label>
  )
  const lista = (k: keyof typeof d, etiqueta: string, valores: readonly string[] | undefined, catalogo: string, vacio?: string) => (
    <label className="sdm-field"><span>{etiqueta}</span>
      <Select suelto placeholder={false} value={d[k]} onChange={ev => set(k)(ev.target.value)}>
        <Opciones valores={valores} catalogo={catalogo} todos={vacio} /></Select></label>
  )
  return (
    <Modal open size="lg" onClose={onClose} title={producto ? t('sw.editar_software') : t('sw.nuevo_software')}>
      <div className="u-stack-12">
        <div className="sdm-form">
          {texto('name', t('sw.col_nombre'))}
          {texto('vendor_name', t('sw.fabricante'))}
          {lista('category', t('sw.categoria'), meta.data?.categories, 'cat')}
          {lista('origin', t('sw.origen'), meta.data?.origins, 'origen')}
          {lista('distribution', t('sw.distribucion'), meta.data?.distributions, 'dist', t('sw.sin_indicar'))}
          {lista('criticality', t('sw.criticidad'), meta.data?.criticalities, 'crit')}
          {lista('lifecycle_status', t('sw.ciclo'), meta.data?.lifecycles, 'ciclo')}
          {texto('license_spdx', t('sw.licencia_spdx'), 'MIT, Apache-2.0…', true)}
        </div>
        <div className="sdm-form">
          {texto('purl', 'purl', 'pkg:npm/lodash', true)}
          {texto('cpe', 'CPE', 'cpe:2.3:a:nginx:nginx:*', true)}
        </div>
        <div className="u-text3-xs">{t('sw.identificadores_ayuda')}</div>
        <div className="sdm-form">
          <label className="sdm-field"><span>{t('sw.responsable')}</span>
            <Select suelto placeholder={false} value={d.owner_user_id} onChange={ev => set('owner_user_id')(ev.target.value)}>
              <option value="">{t('sw.sin_responsable')}</option>
              {(usuarios.data ?? []).map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
            </Select></label>
          {texto('repository_url', t('sw.repositorio'), 'https://')}
        </div>
        <label className="sdm-field"><span>{t('sw.descripcion')}</span>
          <textarea className="ds-input" rows={3} value={d.description} onChange={ev => set('description')(ev.target.value)} /></label>
        <div className="u-actions-10">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button loading={guardar.isPending} disabled={d.name.trim().length < 2} onClick={() => guardar.mutate()}>{t('common.save')}</Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Versiones ─────────────────────────────────────────────────────────────────

type VersionForm = { id?: string; version: string; cycle: string; release_date: string; support_end: string; eol_date: string; extended_support_end: string; is_latest: boolean; notes: string }
const versionVacia: VersionForm = { version: '', cycle: '', release_date: '', support_end: '', eol_date: '', extended_support_end: '', is_latest: false, notes: '' }

function Versiones({ producto, versiones }: { producto: ProductoSw; versiones: VersionSw[] }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const err = useErr()
  const { puede } = useAuth()
  const gestiona = puede('software.gestionar')
  const [form, setForm] = useState<VersionForm | null>(null)
  const refrescar = () => qc.invalidateQueries({ queryKey: ['sw'] })
  const guardar = useMutation({
    mutationFn: (v: VersionForm) => {
      const datos = { version: v.version.trim(), cycle: nulo(v.cycle), release_date: nulo(v.release_date), support_end: nulo(v.support_end),
        eol_date: nulo(v.eol_date), extended_support_end: nulo(v.extended_support_end), is_latest: v.is_latest, notes: nulo(v.notes) }
      return v.id ? cmdbSoftwareApi.editarVersion(v.id, datos) : cmdbSoftwareApi.crearVersion(producto.id, datos)
    },
    onSuccess: () => { setForm(null); toast.success(t('sw.guardado')); refrescar() },
    onError: err,
  })
  const borrar = useMutation({ mutationFn: cmdbSoftwareApi.borrarVersion, onSuccess: refrescar, onError: err })
  const ciclos = useMutation({
    mutationFn: async (f: File) => {
      let datos: unknown
      try { datos = JSON.parse(await f.text()) } catch { throw new Error(t('sw.json_no_valido')) }
      if (!Array.isArray(datos)) throw new Error(t('sw.json_no_valido'))
      return cmdbSoftwareApi.importarCiclos(producto.id, datos as Record<string, unknown>[])
    },
    onSuccess: r => { toast.success(t('sw.ciclos_importados', { n: r.cycles })); refrescar() },
    onError: err,
  })
  return (
    <div className="u-stack-12">
      {gestiona && (
        <div className="u-wrap-8">
          <Button size="sm" icon={<Plus size={14} />} onClick={() => setForm({ ...versionVacia })}>{t('sw.version_nueva')}</Button>
          <BotonFichero accept=".json,application/json" icon={<FileUp size={14} />} loading={ciclos.isPending} onFichero={f => ciclos.mutate(f)}>{t('sw.importar_ciclos')}</BotonFichero>
        </div>
      )}
      {gestiona && <div className="u-text3-xs">{t('sw.importar_ciclos_ayuda')}</div>}
      {versiones.length === 0 ? <EmptyState icon={<Layers size={28} />} title={t('sw.sin_versiones')} /> : (
        <TablaSimple etiqueta={t('sw.versiones')}>
          <thead><tr><th>{t('sw.version')}</th><th>{t('sw.rama')}</th><th>{t('sw.publicada')}</th><th>{t('sw.fin_soporte')}</th><th>{t('sw.fin_vida')}</th>
            <th>{t('sw.ciclo_vida')}</th><th className="sw-num">{t('sw.col_instancias')}</th><th className="sw-num">{t('sw.componentes')}</th><th className="sw-num">{t('sw.col_hallazgos')}</th>{gestiona && <th><span className="u-sr-only">{t('sw.acciones')}</span></th>}</tr></thead>
          <tbody>{versiones.map(v => (
            <tr key={v.id}>
              <td className="u-mono">{v.version}{v.is_latest && <> <StatusBadge kind="success" caps={false}>{t('sw.ultima')}</StatusBadge></>}</td>
              <td className="u-mono">{v.cycle ?? '—'}</td>
              <td>{fmtDate(v.release_date)}</td><td>{fmtDate(v.support_end)}</td><td>{fmtDate(v.eol_date)}</td>
              <td><CicloBadge c={v.lifecycle} fecha={v.eol_date} />{v.lifecycle_source && <div className="u-text3-xs">{v.lifecycle_source}</div>}</td>
              <td className="sw-num">{v.instances_count ?? 0}</td><td className="sw-num">{v.components_count ?? 0}</td><td className="sw-num">{v.open_findings ?? 0}</td>
              {gestiona && <td><div className="u-row-center-6">
                <Button size="xs" variant="ghost" onClick={() => setForm({ id: v.id, version: v.version, cycle: v.cycle ?? '', release_date: v.release_date ?? '', support_end: v.support_end ?? '', eol_date: v.eol_date ?? '', extended_support_end: v.extended_support_end ?? '', is_latest: v.is_latest, notes: v.notes ?? '' })}>{t('sw.editar')}</Button>
                <IconButton ariaLabel={t('sw.borrar')} onClick={async () => { if (await confirmar({ message: t('sw.borrar_version_confirmar', { version: v.version }), danger: true })) borrar.mutate(v.id) }}><Trash2 size={14} /></IconButton>
              </div></td>}
            </tr>
          ))}</tbody>
        </TablaSimple>
      )}
      {form && (
        <Modal open onClose={() => setForm(null)} title={form.id ? t('sw.version_editar') : t('sw.version_nueva')}>
          <div className="u-stack-12">
            <div className="sdm-form">
              <label className="sdm-field"><span>{t('sw.version')}</span><input className="ds-input u-mono" value={form.version} disabled={!!form.id} onChange={ev => setForm({ ...form, version: ev.target.value })} /></label>
              <label className="sdm-field"><span>{t('sw.rama')}</span><input className="ds-input u-mono" value={form.cycle} placeholder="1.24" onChange={ev => setForm({ ...form, cycle: ev.target.value })} /></label>
              {(['release_date', 'support_end', 'eol_date', 'extended_support_end'] as const).map(k => (
                <label key={k} className="sdm-field"><span>{t(`sw.f_${k}`)}</span><DateInput className="ds-input" value={form[k]} onChange={ev => setForm({ ...form, [k]: ev.target.value })} /></label>
              ))}
            </div>
            <Checkbox checked={form.is_latest} onChange={v => setForm({ ...form, is_latest: v })} label={t('sw.es_la_ultima')} />
            <label className="sdm-field"><span>{t('sw.notas')}</span><textarea className="ds-input" rows={2} value={form.notes} onChange={ev => setForm({ ...form, notes: ev.target.value })} /></label>
            <div className="u-actions-10">
              <Button variant="secondary" onClick={() => setForm(null)}>{t('common.cancel')}</Button>
              <Button loading={guardar.isPending} disabled={!form.version.trim()} onClick={() => guardar.mutate(form)}>{t('common.save')}</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

// ── Composición ───────────────────────────────────────────────────────────────

function Composicion({ versiones }: { versiones: VersionSw[] }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const err = useErr()
  const meta = useMetaSw()
  const avisoImportacion = useAvisoDeImportacion()
  const { puede } = useAuth()
  const gestiona = puede('software.gestionar')
  const [versionId, setVersionId] = useState(versiones.find(v => v.is_latest)?.id ?? versiones[0]?.id ?? '')
  const [formato, setFormato] = useState('')
  const [reemplazar, setReemplazar] = useState(false)
  const [nuevo, setNuevo] = useState<{ name: string; component_version: string; purl: string; relation: string; scope: string; direct: boolean; license_spdx: string } | null>(null)
  const arbol = useQuery({ queryKey: ['sw', 'arbol', versionId], queryFn: () => cmdbSoftwareApi.arbol(versionId), enabled: !!versionId })
  const refrescar = () => qc.invalidateQueries({ queryKey: ['sw'] })
  const importar = useMutation({
    mutationFn: (f: File[]) => cmdbSoftwareApi.importarComponentes(versionId, f.length === 1 ? f[0] : f, { format: formato || undefined, replace: reemplazar }),
    onSuccess: r => { avisoImportacion(r); refrescar() }, onError: err,
  })
  const anadir = useMutation({
    mutationFn: () => {
      const n = nuevo!
      return cmdbSoftwareApi.anadirComponente(versionId, { name: nulo(n.name) ?? undefined, purl: nulo(n.purl) ?? undefined, component_version: nulo(n.component_version) ?? undefined,
        relation: n.relation, scope: n.scope, direct: n.direct, license_spdx: nulo(n.license_spdx) ?? undefined })
    },
    onSuccess: () => { setNuevo(null); toast.success(t('sw.guardado')); refrescar() }, onError: err,
  })
  const quitar = useMutation({ mutationFn: cmdbSoftwareApi.quitarComponente, onSuccess: refrescar, onError: err })
  if (versiones.length === 0) return <EmptyState icon={<Layers size={28} />} title={t('sw.sin_versiones')} description={t('sw.composicion_sin_versiones')} />
  const a = arbol.data
  return (
    <div className="u-stack-12">
      <div className="sdm-form">
        <label className="sdm-field"><span>{t('sw.version')}</span>
          <Select suelto placeholder={false} value={versionId} onChange={ev => setVersionId(ev.target.value)}>
            {versiones.map(v => <option key={v.id} value={v.id}>{v.version}</option>)}
          </Select></label>
        {gestiona && <>
          <label className="sdm-field"><span>{t('sw.formato')}</span>
            <Select suelto placeholder={false} value={formato} onChange={ev => setFormato(ev.target.value)}>
              <option value="">{t('sw.formato_auto')}</option>
              {(meta.data?.sbom_formats ?? []).map(x => <option key={x} value={x}>{x}</option>)}
            </Select></label>
          <div className="u-wrap-8 sw-casillas">
            <Checkbox checked={reemplazar} onChange={setReemplazar} label={t('sw.reemplazar')} />
            <BotonFichero multiple accept=".json,.xml,.txt,.lock,.toml,.mod,.sum,.spdx,.cdx,.zip,application/zip" icon={<FileUp size={14} />} loading={importar.isPending} onFicheros={f => importar.mutate(f)}>{t('sw.importar_sbom')}</BotonFichero>
            <Button size="sm" variant="secondary" icon={<Plus size={14} />} onClick={() => setNuevo({ name: '', component_version: '', purl: '', relation: 'library', scope: 'required', direct: true, license_spdx: '' })}>{t('sw.componente_nuevo')}</Button>
          </div>
        </>}
      </div>
      {gestiona && <div className="u-text3-xs">{t('sw.importar_sbom_ayuda')} {t('sw.importar_varios_ayuda')}</div>}
      {arbol.isLoading ? <Spinner /> : a && (
        <>
          <div className="u-wrap-8">
            <StatusBadge caps={false}>{t('sw.n_componentes', { n: a.summary.components })}</StatusBadge>
            <StatusBadge caps={false} kind="accent">{t('sw.n_directos', { n: a.summary.direct })}</StatusBadge>
            <StatusBadge caps={false}>{t('sw.n_transitivos', { n: a.summary.transitive })}</StatusBadge>
            {a.deployed_on.length > 0 && <span className="u-text3-xs">{t('sw.desplegada_en')}: {a.deployed_on.map(i => i.ci_name ?? i.name).filter(Boolean).join(', ')}</span>}
          </div>
          {a.tree.length === 0 ? <EmptyState icon={<Layers size={28} />} title={t('sw.sin_componentes')} /> : (
            <ul className="sw-arbol" role="tree" aria-label={t('sw.composicion')}>
              {a.tree.map(n => <Nodo key={n.id} n={n} nivel={0} onQuitar={gestiona ? (id, nombre) => { void confirmar({ message: t('sw.quitar_componente_confirmar', { nombre }), danger: true }).then(ok => { if (ok) quitar.mutate(id) }) } : undefined} />)}
            </ul>
          )}
        </>
      )}
      {nuevo && (
        <Modal open onClose={() => setNuevo(null)} title={t('sw.componente_nuevo')}>
          <div className="u-stack-12">
            <div className="sdm-form">
              <label className="sdm-field"><span>{t('sw.col_nombre')}</span><input className="ds-input" value={nuevo.name} onChange={ev => setNuevo({ ...nuevo, name: ev.target.value })} /></label>
              <label className="sdm-field"><span>{t('sw.version')}</span><input className="ds-input u-mono" value={nuevo.component_version} onChange={ev => setNuevo({ ...nuevo, component_version: ev.target.value })} /></label>
              <label className="sdm-field"><span>purl</span><input className="ds-input u-mono" value={nuevo.purl} placeholder="pkg:npm/lodash@4.17.21" onChange={ev => setNuevo({ ...nuevo, purl: ev.target.value })} /></label>
              <label className="sdm-field"><span>{t('sw.relacion')}</span>
                <Select suelto placeholder={false} value={nuevo.relation} onChange={ev => setNuevo({ ...nuevo, relation: ev.target.value })}>
                  <Opciones valores={meta.data?.component_relations} catalogo="rel_comp" /></Select></label>
              <label className="sdm-field"><span>{t('sw.ambito')}</span>
                <Select suelto placeholder={false} value={nuevo.scope} onChange={ev => setNuevo({ ...nuevo, scope: ev.target.value })}>
                  <Opciones valores={meta.data?.scopes} catalogo="ambito" /></Select></label>
              <label className="sdm-field"><span>{t('sw.licencia_spdx')}</span><input className="ds-input u-mono" value={nuevo.license_spdx} onChange={ev => setNuevo({ ...nuevo, license_spdx: ev.target.value })} /></label>
            </div>
            <Checkbox checked={nuevo.direct} onChange={v => setNuevo({ ...nuevo, direct: v })} label={t('sw.dependencia_directa')} />
            <div className="u-actions-10">
              <Button variant="secondary" onClick={() => setNuevo(null)}>{t('common.cancel')}</Button>
              <Button loading={anadir.isPending} disabled={!nuevo.name.trim() && !nuevo.purl.trim()} onClick={() => anadir.mutate()}>{t('common.save')}</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

function Nodo({ n, nivel, onQuitar }: { n: NodoDeArbol; nivel: number; onQuitar?: (id: string, nombre: string) => void }) {
  const t = useAppT()
  const e = useEtiquetaSw()
  const [abierto, setAbierto] = useState(nivel < 1)
  const hijos = n.children.length > 0
  return (
    <li role="treeitem" aria-expanded={hijos ? abierto : undefined} className="sw-nodo">
      <div className="sw-nodo__fila">
        {hijos
          ? <IconButton ariaLabel={t(abierto ? 'sw.plegar' : 'sw.desplegar')} onClick={() => setAbierto(!abierto)}>{abierto ? <ChevronDown size={14} /> : <ChevronRight size={14} />}</IconButton>
          : <span className="sw-nodo__hueco" />}
        <span className="u-text1-sm-600">{n.name ?? n.purl ?? '—'}</span>
        <span className="u-text3-xs"><VersionTexto v={n.version} /></span>
        <StatusBadge caps={false} kind={n.direct ? 'accent' : 'neutral'}>{e('rel_comp', n.relation)}</StatusBadge>
        {n.scope !== 'required' && <StatusBadge caps={false}>{e('ambito', n.scope)}</StatusBadge>}
        {n.license && <StatusBadge caps={false} kind={n.license_issue ? (n.license_issue.level === 'conflict' ? 'danger' : 'warning') : 'neutral'}
          title={n.license_issue ? e('motivo_lic', n.license_issue.reason) : e('familia', n.license_family)}>{n.license}</StatusBadge>}
        {!n.license && <StatusBadge caps={false} kind="warning">{t('sw.sin_licencia')}</StatusBadge>}
        <CicloBadge c={n.lifecycle} fecha={n.eol_date} />
        {n.open_findings > 0 && <><StatusBadge kind="danger" caps={false}>{t('sw.n_hallazgos', { n: n.open_findings })}</StatusBadge><SeveridadBadge s={n.worst_severity} /></>}
        {onQuitar && <IconButton className="sw-nodo__quitar" ariaLabel={t('sw.quitar_componente')} onClick={() => onQuitar(n.id, n.name ?? '')}><Trash2 size={12} /></IconButton>}
      </div>
      {n.license_issue && <div className="u-text3-xs sw-nodo__aviso">{e('familia', n.license_issue.family)} · {e('motivo_lic', n.license_issue.reason)}</div>}
      {hijos && abierto && <ul role="group">{n.children.map(h => <Nodo key={h.id} n={h} nivel={nivel + 1} onQuitar={onQuitar} />)}</ul>}
    </li>
  )
}

// ── Instancias ────────────────────────────────────────────────────────────────

function Instancias({ producto, instancias }: { producto: ProductoSw; instancias: InstanciaSw[] }) {
  const t = useAppT()
  const qc = useQueryClient()
  const { puede } = useAuth()
  const [editando, setEditando] = useState<InstanciaSw | 'nueva' | null>(null)
  return (
    <div className="u-stack-12">
      {puede('software.gestionar') && <div><Button size="sm" icon={<Plus size={14} />} onClick={() => setEditando('nueva')}>{t('sw.instancia_nueva')}</Button></div>}
      {instancias.length === 0 ? <EmptyState icon={<Layers size={28} />} title={t('sw.sin_instancias')} /> : (
        <TablaInstancias instancias={instancias} onAbrir={puede('software.gestionar') ? i => setEditando(i) : undefined} />
      )}
      {editando && <InstanciaModal inicial={editando === 'nueva' ? null : editando} productId={producto.id}
        onClose={() => setEditando(null)} onSaved={() => { setEditando(null); qc.invalidateQueries({ queryKey: ['sw'] }) }} />}
    </div>
  )
}

type CiDeLista = Pick<SdCi, 'id' | 'code' | 'name' | 'ci_type' | 'hostname' | 'ip_address'>

/** Alta o edición de una instancia: dónde corre, versión, rutas, puertos, exposición y configuración. */
export function InstanciaModal({ inicial, productId, ciId, onClose, onSaved }: {
  inicial: InstanciaSw | null; productId?: string; ciId?: string; onClose: () => void; onSaved: () => void
}) {
  const t = useAppT()
  const e = useEtiquetaSw()
  const toast = useToast()
  const qc = useQueryClient()
  const err = useErr()
  const meta = useMetaSw()
  const [pestana, setPestana] = useState('datos')
  const [d, setD] = useState({
    product_id: inicial?.product_id ?? productId ?? '', ci_id: inicial?.ci_id ?? ciId ?? '', version: inicial?.version ?? '',
    name: inicial?.name ?? '', environment: inicial?.environment ?? 'prod', status: inicial?.status ?? 'running',
    install_path: inicial?.install_path ?? '', config_path: inicial?.config_path ?? '', ports: (inicial?.ports ?? []).join(', '),
    exposure: inicial?.exposure ?? 'internal', config_format: inicial?.config_format ?? '', config_text: '', notes: inicial?.notes ?? '',
  })
  const set = (k: keyof typeof d) => (v: string) => setD(x => ({ ...x, [k]: v }))
  const productos = useQuery({ queryKey: ['sw', 'productos-selector'], queryFn: () => cmdbSoftwareApi.productos({ page_size: 500 }), enabled: !productId && !inicial })
  const cis = useQuery<CiDeLista[]>({ queryKey: ['cmdb-items', 'todos'], queryFn: () => cmdbApi.sdList({ page_size: FULL_LIST_SIZE }).then(r => r.data ?? []) })
  const versiones = useQuery({ queryKey: ['sw', 'ficha', d.product_id], queryFn: () => cmdbSoftwareApi.ficha(d.product_id), enabled: !!d.product_id })
  const detalle = useQuery({ queryKey: ['sw', 'instancia', inicial?.id], queryFn: () => cmdbSoftwareApi.instancia(inicial!.id), enabled: !!inicial })
  const guardar = useMutation({
    mutationFn: () => {
      const puertos = d.ports.split(/[\s,;]+/).map(Number).filter(n => Number.isInteger(n) && n > 0 && n < 65536)
      const datos = {
        product_id: d.product_id, ci_id: nulo(d.ci_id), version: nulo(d.version), name: nulo(d.name), environment: d.environment,
        status: d.status, install_path: nulo(d.install_path), config_path: nulo(d.config_path), ports: puertos, exposure: d.exposure,
        config_format: nulo(d.config_format), notes: nulo(d.notes),
        ...(d.config_text.trim() ? { config_text: d.config_text } : {}),
      }
      return inicial ? cmdbSoftwareApi.editarInstancia(inicial.id, datos) : cmdbSoftwareApi.crearInstancia(datos)
    },
    onSuccess: () => { toast.success(t('sw.guardado')); onSaved() }, onError: err,
  })
  const retirar = useMutation({ mutationFn: () => cmdbSoftwareApi.retirarInstancia(inicial!.id), onSuccess: () => { toast.success(t('sw.retirado')); onSaved() }, onError: err })
  const det = detalle.data
  const refrescarDetalle = () => qc.invalidateQueries({ queryKey: ['sw', 'instancia', inicial?.id] })
  return (
    <Modal open size="lg" onClose={onClose} title={inicial ? t('sw.instancia_editar', { nombre: inicial.product_name ?? inicial.name ?? '' }) : t('sw.instancia_nueva')}>
      <div className="u-stack-12">
        {inicial && <Tabs ariaLabel={t('sw.instancia')} active={pestana} onChange={setPestana} items={[
          { id: 'datos', label: t('sw.datos') },
          { id: 'relaciones', label: t('sw.relaciones'), count: det?.relations?.length },
          { id: 'historial', label: t('sw.historial_config'), count: det?.config_history?.length },
        ]} />}
        {pestana === 'datos' && <>
          <div className="sdm-form">
            {!productId && !inicial && (
              <label className="sdm-field"><span>{t('sw.software')}</span>
                <Select suelto placeholder={false} value={d.product_id} onChange={ev => set('product_id')(ev.target.value)}>
                  <option value="">{t('sw.elige_software')}</option>
                  {(productos.data?.items ?? []).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                </Select></label>
            )}
            <label className="sdm-field"><span>{t('sw.maquina')}</span>
              <Select suelto placeholder={false} value={d.ci_id} onChange={ev => set('ci_id')(ev.target.value)}>
                <option value="">{t('sw.sin_maquina')}</option>
                {(cis.data ?? []).map(c => <option key={c.id} value={c.id}>{c.code ? `${c.code} · ` : ''}{c.name}{c.ip_address ? ` (${c.ip_address})` : ''}</option>)}
              </Select></label>
            <label className="sdm-field"><span>{t('sw.version')}</span>
              <input className="ds-input u-mono" list="sw-versiones" value={d.version} onChange={ev => set('version')(ev.target.value)} />
              <datalist id="sw-versiones">{(versiones.data?.versions ?? []).map(v => <option key={v.id} value={v.version} />)}</datalist></label>
            <label className="sdm-field"><span>{t('sw.col_nombre')}</span><input className="ds-input" value={d.name} placeholder={t('sw.nombre_instancia_ph')} onChange={ev => set('name')(ev.target.value)} /></label>
            <label className="sdm-field"><span>{t('sw.entorno')}</span>
              <Select suelto placeholder={false} value={d.environment} onChange={ev => set('environment')(ev.target.value)}><Opciones valores={meta.data?.environments} catalogo="entorno" /></Select></label>
            <label className="sdm-field"><span>{t('sw.estado')}</span>
              <Select suelto placeholder={false} value={d.status} onChange={ev => set('status')(ev.target.value)}><Opciones valores={meta.data?.instance_statuses} catalogo="est_inst" /></Select></label>
            <label className="sdm-field"><span>{t('sw.exposicion')}</span>
              <Select suelto placeholder={false} value={d.exposure} onChange={ev => set('exposure')(ev.target.value)}><Opciones valores={meta.data?.exposures} catalogo="expo" /></Select></label>
            <label className="sdm-field"><span>{t('sw.puertos')}</span><input className="ds-input u-mono" value={d.ports} placeholder="80, 443" onChange={ev => set('ports')(ev.target.value)} /></label>
            <label className="sdm-field"><span>{t('sw.ruta_instalacion')}</span><input className="ds-input u-mono" value={d.install_path} onChange={ev => set('install_path')(ev.target.value)} /></label>
            <label className="sdm-field"><span>{t('sw.ruta_configuracion')}</span><input className="ds-input u-mono" value={d.config_path} placeholder="/etc/nginx/nginx.conf" onChange={ev => set('config_path')(ev.target.value)} /></label>
          </div>
          <div className="ds-eyebrow">{t('sw.configuracion')}</div>
          <div className="sdm-form">
            <label className="sdm-field"><span>{t('sw.formato_config')}</span>
              <Select suelto placeholder={false} value={d.config_format} onChange={ev => set('config_format')(ev.target.value)}>
                <option value="">{t('sw.formato_auto')}</option>
                {(meta.data?.config_formats ?? []).map(x => <option key={x} value={x}>{e('formato_cfg', x)}</option>)}
              </Select></label>
          </div>
          <label className="sdm-field"><span>{t('sw.config_texto')}</span>
            <textarea className="ds-input u-mono" rows={8} value={d.config_text} placeholder={t('sw.config_texto_ph')} onChange={ev => set('config_text')(ev.target.value)} /></label>
          <div className="u-text3-xs">{t('sw.config_ayuda')}</div>
          {inicial?.config && Object.keys(inicial.config).length > 0 && (
            <details className="sw-detalles"><summary>{t('sw.configuracion_actual', { n: Object.keys(inicial.config).length })}</summary>
              <ListaKv filas={Object.entries(inicial.config).map(([k, v]) => [<span key={k} className="u-mono">{k}</span>, <span key={`${k}-v`} className="u-mono">{valorLegible(v)}</span>])} />
            </details>
          )}
          <label className="sdm-field"><span>{t('sw.notas')}</span><textarea className="ds-input" rows={2} value={d.notes} onChange={ev => set('notes')(ev.target.value)} /></label>
          <div className="u-actions-10">
            {inicial && <Button variant="ghost" loading={retirar.isPending} onClick={async () => { if (await confirmar({ message: t('sw.retirar_instancia_confirmar'), danger: true })) retirar.mutate() }}>{t('sw.retirar')}</Button>}
            <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
            <Button loading={guardar.isPending} disabled={!d.product_id} onClick={() => guardar.mutate()}>{t('common.save')}</Button>
          </div>
        </>}
        {pestana === 'relaciones' && inicial && <RelacionesDeInstancia instancia={inicial} relaciones={det?.relations ?? []} onCambio={refrescarDetalle} cis={cis.data ?? []} />}
        {pestana === 'historial' && (detalle.isLoading ? <Spinner /> : (det?.config_history ?? []).length === 0 ? <EmptyState title={t('sw.sin_historial')} /> : (
          <ul className="sdm-list">{(det?.config_history ?? []).map(h => (
            <li key={h.id} className="sdm-list__item"><div className="u-flex1-min0 u-stack-6">
              <div className="u-wrap-8"><span className="u-text1-sm-600">{fmtDateTime(h.created_at)}</span>
                {h.version && <span className="u-mono u-text3-xs">{h.version}</span>}
                <StatusBadge caps={false}>{e('origen_dato', h.source)}</StatusBadge></div>
              <div className="u-text3-xs">{t('sw.claves_cambiadas')}: <span className="u-mono">{h.changed_keys.join(', ') || '—'}</span></div>
              {h.config && <details className="sw-detalles"><summary>{t('sw.ver_configuracion')}</summary>
                <ListaKv filas={Object.entries(h.config).map(([k, v]) => [<span key={k} className="u-mono">{k}</span>, <span key={`${k}-v`} className="u-mono">{valorLegible(v)}</span>])} /></details>}
            </div></li>
          ))}</ul>
        ))}
      </div>
    </Modal>
  )
}

function RelacionesDeInstancia({ instancia, relaciones, onCambio, cis }: { instancia: InstanciaSw; relaciones: NonNullable<InstanciaSw['relations']>; onCambio: () => void; cis: CiDeLista[] }) {
  const t = useAppT()
  const e = useEtiquetaSw()
  const err = useErr()
  const qc = useQueryClient()
  const meta = useMetaSw()
  const [tipo, setTipo] = useState('depends_on')
  const [destino, setDestino] = useState('')
  const otras = useQuery({ queryKey: ['sw', 'instancias-todas'], queryFn: () => cmdbSoftwareApi.instancias() })
  const nombreInst = (id: string | null) => { const i = (otras.data ?? []).find(x => x.id === id); return i ? `${i.product_name ?? i.name} ${i.version ?? ''} · ${i.ci_name ?? ''}` : id ?? '—' }
  const nombreCi = (id: string | null) => cis.find(c => c.id === id)?.name ?? id ?? '—'
  const hecho = () => { onCambio(); qc.invalidateQueries({ queryKey: ['sw'] }) }
  const crear = useMutation({
    mutationFn: () => cmdbSoftwareApi.crearRelacion({ source_instance_id: instancia.id, relation_type: tipo,
      ...(destino.startsWith('ci:') ? { target_ci_id: destino.slice(3) } : { target_instance_id: destino.slice(4) }) }),
    onSuccess: () => { setDestino(''); hecho() }, onError: err,
  })
  const quitar = useMutation({ mutationFn: cmdbSoftwareApi.quitarRelacion, onSuccess: hecho, onError: err })
  return (
    <div className="u-stack-12">
      {relaciones.length === 0 ? <EmptyState icon={<Link2 size={28} />} title={t('sw.sin_relaciones')} /> : (
        <ul className="sdm-list">{relaciones.map(r => (
          <li key={r.id} className="sdm-list__item">
            <div className="u-flex1-min0">{e('rel', r.relation_type)} <strong>{r.target_instance_id ? nombreInst(r.target_instance_id) : nombreCi(r.target_ci_id)}</strong>
              {r.details && <div className="u-text3-xs">{r.details}</div>}</div>
            <IconButton ariaLabel={t('sw.quitar_relacion')} onClick={async () => { if (await confirmar({ message: t('sw.quitar_relacion_confirmar'), danger: true })) quitar.mutate(r.id) }}><Unlink size={14} /></IconButton>
          </li>
        ))}</ul>
      )}
      <div className="sdm-form">
        <label className="sdm-field"><span>{t('sw.relacion')}</span>
          <Select suelto placeholder={false} value={tipo} onChange={ev => setTipo(ev.target.value)}><Opciones valores={meta.data?.relations} catalogo="rel" /></Select></label>
        <label className="sdm-field"><span>{t('sw.destino')}</span>
          <Select suelto placeholder={false} value={destino} onChange={ev => setDestino(ev.target.value)}>
            <option value="">{t('sw.elige_destino')}</option>
            <optgroup label={t('sw.instancias')}>
              {(otras.data ?? []).filter(i => i.id !== instancia.id).map(i => <option key={i.id} value={`ins:${i.id}`}>{nombreInst(i.id)}</option>)}
            </optgroup>
            <optgroup label={t('sw.elementos_cmdb')}>
              {cis.map(c => <option key={c.id} value={`ci:${c.id}`}>{c.name}</option>)}
            </optgroup>
          </Select></label>
        <div><Button icon={<Plus size={14} />} disabled={!destino} loading={crear.isPending} onClick={() => crear.mutate()}>{t('sw.anadir_relacion')}</Button></div>
      </div>
    </div>
  )
}

// ── Vulnerabilidades, licencias, líneas base y grafo ─────────────────────────

function VulnsDelProducto({ productId }: { productId: string }) {
  const t = useAppT()
  const [abierto, setAbierto] = useState<string | null>(null)
  const { data, isLoading } = useQuery({ queryKey: ['sw', 'hallazgos-producto', productId], queryFn: () => cmdbSoftwareApi.hallazgos({ product_id: productId, page_size: 500 }) })
  if (isLoading) return <Spinner />
  return (
    <>
      {(data?.items ?? []).length === 0 ? <EmptyState icon={<ShieldCheck size={28} />} title={t('sw.sin_hallazgos')} /> : <TablaHallazgos hallazgos={data?.items ?? []} onAbrir={h => setAbierto(h.id)} />}
      {abierto && <DetalleDeHallazgo id={abierto} onClose={() => setAbierto(null)} />}
    </>
  )
}

function Licencias({ producto, licencias }: { producto: ProductoSw; licencias: { id: string; name: string; product_name: string | null; version: string | null; edition: string | null; type: string; status: string; total_seats: number | null; expiry_date: string | null }[] }) {
  const t = useAppT()
  const qc = useQueryClient()
  const err = useErr()
  const { puede } = useAuth()
  const gestiona = puede('software.gestionar')
  const [elegida, setElegida] = useState('')
  const todas = useQuery({ queryKey: ['alm-licencias-para-software'], queryFn: () => licensesApi.list({ page_size: 500 }).then(r => r.data), enabled: gestiona })
  const refrescar = () => qc.invalidateQueries({ queryKey: ['sw'] })
  const vincular = useMutation({ mutationFn: () => cmdbSoftwareApi.vincularLicencia(producto.id, elegida), onSuccess: () => { setElegida(''); refrescar() }, onError: err })
  const desvincular = useMutation({ mutationFn: (id: string) => cmdbSoftwareApi.desvincularLicencia(producto.id, id), onSuccess: refrescar, onError: err })
  const ya = new Set(licencias.map(l => l.id))
  return (
    <div className="u-stack-12">
      <div className="u-text3-xs">{t('sw.licencias_ayuda')}</div>
      {licencias.length === 0 ? <EmptyState icon={<Link2 size={28} />} title={t('sw.sin_licencias')} /> : (
        <TablaSimple etiqueta={t('sw.licencias')}>
          <thead><tr><th>{t('sw.col_nombre')}</th><th>{t('sw.edicion')}</th><th>{t('sw.tipo')}</th><th>{t('sw.estado')}</th><th className="sw-num">{t('sw.puestos')}</th><th>{t('sw.caduca')}</th>{gestiona && <th><span className="u-sr-only">{t('sw.acciones')}</span></th>}</tr></thead>
          <tbody>{licencias.map(l => (
            <tr key={l.id}>
              <td>{l.name}{l.product_name && <div className="u-text3-xs">{l.product_name} {l.version ?? ''}</div>}</td>
              <td>{l.edition ?? '—'}</td><td>{l.type}</td><td>{l.status}</td><td className="sw-num">{l.total_seats ?? '—'}</td><td>{fmtDate(l.expiry_date)}</td>
              {gestiona && <td><IconButton ariaLabel={t('sw.desvincular')} onClick={async () => { if (await confirmar({ message: t('sw.desvincular_confirmar', { nombre: l.name }) })) desvincular.mutate(l.id) }}><Unlink size={14} /></IconButton></td>}
            </tr>
          ))}</tbody>
        </TablaSimple>
      )}
      {gestiona && (
        <div className="sdm-form">
          <label className="sdm-field"><span>{t('sw.vincular_licencia')}</span>
            <Select suelto placeholder={false} value={elegida} onChange={ev => setElegida(ev.target.value)}>
              <option value="">{t('sw.elige_licencia')}</option>
              {(todas.data ?? []).filter(l => !ya.has(l.id)).map(l => <option key={l.id} value={l.id}>{l.name}{l.version ? ` ${l.version}` : ''}</option>)}
            </Select></label>
          <div><Button icon={<Link2 size={14} />} disabled={!elegida} loading={vincular.isPending} onClick={() => vincular.mutate()}>{t('sw.vincular')}</Button></div>
        </div>
      )}
    </div>
  )
}

type LineaForm = { id?: string; name: string; environment: string; rules: ReglaDeLineaBase[] }

function LineasBase({ producto, lineas }: { producto: ProductoSw; lineas: LineaBase[] }) {
  const t = useAppT()
  const e = useEtiquetaSw()
  const toast = useToast()
  const qc = useQueryClient()
  const err = useErr()
  const meta = useMetaSw()
  const { puede } = useAuth()
  const gestiona = puede('software.gestionar')
  const [form, setForm] = useState<LineaForm | null>(null)
  const refrescar = () => qc.invalidateQueries({ queryKey: ['sw'] })
  const guardar = useMutation({
    mutationFn: (f: LineaForm) => {
      const datos = { name: f.name.trim(), environment: f.environment || null, rules: f.rules.filter(r => r.key.trim()).map(r => ({ ...r, key: r.key.trim() })) }
      return f.id ? cmdbSoftwareApi.editarLineaBase(f.id, datos) : cmdbSoftwareApi.crearLineaBase(producto.id, datos)
    },
    onSuccess: () => { setForm(null); toast.success(t('sw.guardado')); refrescar() }, onError: err,
  })
  const aprobar = useMutation({ mutationFn: cmdbSoftwareApi.aprobarLineaBase, onSuccess: () => { toast.success(t('sw.linea_base_aprobada')); refrescar() }, onError: err })
  const borrar = useMutation({ mutationFn: cmdbSoftwareApi.borrarLineaBase, onSuccess: refrescar, onError: err })
  const cambiarRegla = (i: number, c: Partial<ReglaDeLineaBase>) => form && setForm({ ...form, rules: form.rules.map((r, j) => (j === i ? { ...r, ...c } : r)) })
  return (
    <div className="u-stack-12">
      <div className="u-text3-xs">{t('sw.lineas_base_ayuda')}</div>
      {gestiona && <div><Button size="sm" icon={<Plus size={14} />} onClick={() => setForm({ name: '', environment: '', rules: [{ key: '', op: 'eq', value: '', severity: 'medium' }] })}>{t('sw.linea_base_nueva')}</Button></div>}
      {lineas.length === 0 ? <EmptyState icon={<ShieldCheck size={28} />} title={t('sw.sin_lineas_base')} /> : (
        <ul className="sdm-list">{lineas.map(l => (
          <li key={l.id} className="sdm-list__item">
            <div className="u-flex1-min0 u-stack-6">
              <div className="u-wrap-8"><span className="u-text1-sm-600">{l.name}</span>
                {l.environment && <StatusBadge caps={false}>{e('entorno', l.environment)}</StatusBadge>}
                <StatusBadge caps={false} kind={l.approved_at ? 'success' : 'warning'}>{l.approved_at ? t('sw.aprobada_el', { fecha: fmtDate(l.approved_at) }) : t('sw.sin_aprobar')}</StatusBadge>
                {!l.is_active && <StatusBadge caps={false}>{t('sw.inactiva')}</StatusBadge>}</div>
              <ul className="sw-lista-simple">{l.rules.map((r, i) => (
                <li key={i}><span className="u-mono">{r.key}</span> {e('op', r.op)} {r.value !== undefined && r.value !== '' && <span className="u-mono">{valorLegible(r.value)}</span>} <SeveridadBadge s={r.severity} />{r.description ? ` · ${r.description}` : ''}</li>
              ))}</ul>
            </div>
            <div className="u-actions-8">
              {puede('software.aprobar') && !l.approved_at && <Button size="xs" variant="secondary" loading={aprobar.isPending} onClick={() => aprobar.mutate(l.id)}>{t('sw.aprobar')}</Button>}
              {gestiona && <Button size="xs" variant="ghost" onClick={() => setForm({ id: l.id, name: l.name, environment: l.environment ?? '', rules: l.rules.map(r => ({ ...r })) })}>{t('sw.editar')}</Button>}
              {gestiona && <IconButton ariaLabel={t('sw.borrar')} onClick={async () => { if (await confirmar({ message: t('sw.borrar_linea_base_confirmar', { nombre: l.name }), danger: true })) borrar.mutate(l.id) }}><Trash2 size={14} /></IconButton>}
            </div>
          </li>
        ))}</ul>
      )}
      {form && (
        <Modal open size="lg" onClose={() => setForm(null)} title={form.id ? t('sw.linea_base_editar') : t('sw.linea_base_nueva')}>
          <div className="u-stack-12">
            <div className="sdm-form">
              <label className="sdm-field"><span>{t('sw.col_nombre')}</span><input className="ds-input" value={form.name} onChange={ev => setForm({ ...form, name: ev.target.value })} /></label>
              <label className="sdm-field"><span>{t('sw.entorno')}</span>
                <Select suelto placeholder={false} value={form.environment} onChange={ev => setForm({ ...form, environment: ev.target.value })}>
                  <Opciones valores={meta.data?.environments} catalogo="entorno" todos={t('sw.todos')} /></Select></label>
            </div>
            <div className="ds-eyebrow">{t('sw.reglas')}</div>
            {form.rules.map((r, i) => (
              <div key={i} className="sw-regla">
                <input className="ds-input u-mono" aria-label={t('sw.clave')} placeholder={t('sw.clave')} value={r.key} onChange={ev => cambiarRegla(i, { key: ev.target.value })} />
                <Select suelto placeholder={false} aria-label={t('sw.operador')} value={r.op} onChange={ev => cambiarRegla(i, { op: ev.target.value })}><Opciones valores={meta.data?.baseline_ops} catalogo="op" /></Select>
                <input className="ds-input u-mono" aria-label={t('sw.valor')} placeholder={t('sw.valor')} value={r.value == null ? '' : typeof r.value === 'object' ? JSON.stringify(r.value) : String(r.value)} disabled={r.op === 'present' || r.op === 'absent'} onChange={ev => cambiarRegla(i, { value: ev.target.value })} />
                <Select suelto placeholder={false} aria-label={t('sw.severidad')} value={r.severity} onChange={ev => cambiarRegla(i, { severity: ev.target.value })}>
                  {['critical', 'high', 'medium', 'low'].map(s => <option key={s} value={s}>{e('sev', s)}</option>)}</Select>
                <IconButton ariaLabel={t('sw.quitar_regla')} onClick={() => setForm({ ...form, rules: form.rules.filter((_, j) => j !== i) })}><Trash2 size={14} /></IconButton>
              </div>
            ))}
            <div><Button size="sm" variant="secondary" icon={<Plus size={14} />} onClick={() => setForm({ ...form, rules: [...form.rules, { key: '', op: 'eq', value: '', severity: 'medium' }] })}>{t('sw.anadir_regla')}</Button></div>
            <div className="u-text3-xs">{t('sw.reglas_ayuda')}</div>
            <div className="u-actions-10">
              <Button variant="secondary" onClick={() => setForm(null)}>{t('common.cancel')}</Button>
              <Button loading={guardar.isPending} disabled={!form.name.trim() || !form.rules.some(r => r.key.trim())} onClick={() => guardar.mutate(form)}>{t('common.save')}</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

function Grafo({ productId, nombre }: { productId: string; nombre: string }) {
  const { data, isLoading } = useQuery({ queryKey: ['sw', 'grafo', productId], queryFn: () => cmdbSoftwareApi.grafo({ product_id: productId }) })
  if (isLoading) return <Spinner />
  return (
    <Section>
      <Suspense fallback={<Spinner />}>
        <CMDBTopologyGraph nodes={(data?.nodes ?? []) as unknown as RawNode[]} edges={(data?.edges ?? []) as unknown as RawEdge[]} centerName={nombre} />
      </Suspense>
    </Section>
  )
}

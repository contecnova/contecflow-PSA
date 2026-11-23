/**
 * Pestaña Riesgo → Controles e intentos (22-11-2026): controles compensatorios
 * (WAF, IPS, parche virtual, aislamiento…) sobre uno o varios hallazgos, con
 * caducidad obligatoria y revocación con motivo; e intentos de explotación
 * importados de un SIEM/EDR/IPS (fichero CSV o JSON).
 *
 * Un control no cierra el hallazgo: rebaja su riesgo y su prioridad mientras
 * está activo. Diseño: docs/CMDB_SOFTWARE_Y_VULNERABILIDADES.md §11.8.
 */
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FileUp, Plus, ShieldCheck, Siren } from 'lucide-react'
import { useAppT } from '../../../../i18n/AppLangContext'
import { useToast } from '../../../../context/ToastContext'
import { useAuth } from '../../../../context/AuthContext'
import { pedirTexto } from '../../../../context/ConfirmContext'
import { fmtDate, fmtDateTime } from '../../../../utils/helpers'
import { cmdbRiesgoApi } from '../../../../services/api/cmdbRiesgo'
import type { ControlCompensatorio } from '../../../../services/api/cmdbRiesgo'
import type { StatusBadgeKind } from '../../../ui'
import { Buscador, Button, Checkbox, EmptyState, Input, Modal, Section, Segmentado, Select, Spinner, StatusBadge, TablaSimple, Textarea } from '../../../ui'
import Pagination from '../../../ui/Pagination'
import { BotonFichero, SeveridadBadge, useErr } from '../comun'
import DetalleDeHallazgo from '../DetalleDeHallazgo'
import { enDias, useEtiquetaSwr, useMetaRiesgo } from './comunRiesgo'

const CONTROL_KIND: Record<string, StatusBadgeKind> = { active: 'success', expired: 'neutral', revoked: 'neutral' }
const ACCION_KIND: Record<string, StatusBadgeKind> = { blocked: 'success', detected: 'warning', allowed: 'danger' }
const TAMANO = 25

/** Lo mínimo de un hallazgo para elegirlo como destino de un control. */
export interface HallazgoBreve { id: string; vuln_id: string | null; product_name: string | null; ci_name: string | null }

export default function Controles() {
  const t = useAppT()
  return (
    <div className="u-stack-20">
      <ListaDeControles />
      <IntentosDeExplotacion />
      <div className="u-text3-xs">{t('swr.controles_nota')}</div>
    </div>
  )
}

function ListaDeControles() {
  const t = useAppT()
  const e = useEtiquetaSwr()
  const toast = useToast()
  const qc = useQueryClient()
  const err = useErr()
  const { puede } = useAuth()
  const [estado, setEstado] = useState('active')
  const [nuevo, setNuevo] = useState(false)
  const [abierto, setAbierto] = useState<string | null>(null)
  const { data, isLoading } = useQuery({ queryKey: ['swr', 'controles', estado], queryFn: () => cmdbRiesgoApi.controles({ status: estado || undefined }) })
  const revocar = useMutation({
    mutationFn: ({ id, motivo }: { id: string; motivo: string }) => cmdbRiesgoApi.revocarControl(id, motivo),
    onSuccess: () => { toast.success(t('swr.control_revocado')); qc.invalidateQueries({ queryKey: ['swr'] }) },
    onError: err,
  })
  const pedirMotivo = async (c: ControlCompensatorio) => {
    const motivo = await pedirTexto({ title: t('swr.revocar_control'), message: t('swr.revocar_control_msg', { vuln: c.vuln_id ?? '' }), label: t('swr.motivo'), required: true, multiline: true })
    if (motivo && motivo.trim()) revocar.mutate({ id: c.id, motivo: motivo.trim() })
  }
  const lista = data ?? []
  return (
    <Section title={t('swr.controles')} subtitle={t('swr.controles_desc')}
      actions={<div className="u-wrap-8">
        <Select suelto placeholder={false} className="sdm-select-accion" aria-label={t('swr.estado')} value={estado} onChange={ev => setEstado(ev.target.value)}>
          <option value="">{t('swr.todos')}</option>
          {['active', 'expired', 'revoked'].map(s => <option key={s} value={s}>{e('estado_control', s)}</option>)}
        </Select>
        {puede('software.gestionar') && <Button size="sm" icon={<Plus size={14} />} onClick={() => setNuevo(true)}>{t('swr.nuevo_control')}</Button>}
      </div>}>
      {isLoading ? <Spinner size={16} /> : lista.length === 0 ? <EmptyState icon={<ShieldCheck size={28} />} title={t('swr.sin_controles')} /> : (
        <TablaSimple etiqueta={t('swr.controles')} densidad="compacta">
          <thead><tr>
            <th>{t('sw.aviso')}</th><th>{t('swr.col_donde')}</th><th>{t('swr.tipo_control')}</th><th className="sw-num">{t('swr.reduccion')}</th>
            <th>{t('swr.caduca')}</th><th>{t('swr.estado')}</th><th>{t('swr.registrado_por')}</th><th><span className="u-sr-only">{t('swr.acciones')}</span></th>
          </tr></thead>
          <tbody>{lista.map(c => (
            <tr key={c.id}>
              <td><Button variant="link" className="sw-enlace u-mono" onClick={() => setAbierto(c.finding_id)}>{c.vuln_id ?? '—'}</Button></td>
              <td>{c.product_name ?? '—'}{c.ci_name && <div className="u-text3-xs">{c.ci_name}</div>}</td>
              <td>{e('control', c.control_type)}
                <div className="u-text3-xs sw-recorte" title={c.description}>{c.description}</div>
                {c.evidence && <div className="u-text3-xs sw-recorte" title={c.evidence}>{t('swr.evidencia')}: {c.evidence}</div>}
              </td>
              <td className="sw-num">{Math.round(c.reduction * 100)} %</td>
              <td>{fmtDate(c.expires_at)}</td>
              <td><StatusBadge kind={CONTROL_KIND[c.status] ?? 'neutral'} caps={false}>{e('estado_control', c.status)}</StatusBadge>
                {c.revoke_reason && <div className="u-text3-xs sw-recorte" title={c.revoke_reason}>{c.revoke_reason}</div>}</td>
              <td className="u-text3-xs">{c.created_by_name ?? '—'}{c.created_at && <div>{fmtDate(c.created_at)}</div>}</td>
              <td>{puede('software.gestionar') && c.status === 'active' && (
                <Button size="xs" variant="ghost" loading={revocar.isPending && revocar.variables?.id === c.id} onClick={() => pedirMotivo(c)}>{t('swr.revocar')}</Button>
              )}</td>
            </tr>
          ))}</tbody>
        </TablaSimple>
      )}
      {nuevo && <ControlModal inicial={[]} onClose={() => setNuevo(false)} onSaved={() => setNuevo(false)} />}
      {abierto && <DetalleDeHallazgo id={abierto} onClose={() => setAbierto(null)} />}
    </Section>
  )
}

/** Alta de un control compensatorio sobre los hallazgos elegidos (se pueden añadir buscando). */
export function ControlModal({ inicial, onClose, onSaved }: { inicial: HallazgoBreve[]; onClose: () => void; onSaved: () => void }) {
  const t = useAppT()
  const e = useEtiquetaSwr()
  const toast = useToast()
  const qc = useQueryClient()
  const err = useErr()
  const meta = useMetaRiesgo()
  const [elegidos, setElegidos] = useState<HallazgoBreve[]>(inicial)
  const [buscar, setBuscar] = useState('')
  const [tipo, setTipo] = useState('')
  const [descripcion, setDescripcion] = useState('')
  const [evidencia, setEvidencia] = useState('')
  const [reduccion, setReduccion] = useState('')
  const [caduca, setCaduca] = useState(enDias(30))
  const tipos = meta.data?.control_types ?? []
  const primerTipo = tipos[0]
  useEffect(() => { if (!tipo && primerTipo) setTipo(primerTipo) }, [tipo, primerTipo])
  const porDefecto = tipo ? meta.data?.control_reductions?.[tipo] : undefined
  const candidatos = useQuery({
    queryKey: ['swr', 'candidatos-control', buscar],
    queryFn: () => cmdbRiesgoApi.hallazgos({ status: 'live', q: buscar.trim() || undefined, page_size: 20 }),
    enabled: buscar.trim().length >= 2,
  })
  const ids = new Set(elegidos.map(h => h.id))
  const crear = useMutation({
    mutationFn: () => cmdbRiesgoApi.crearControles({
      finding_ids: elegidos.map(h => h.id), control_type: tipo, description: descripcion.trim(),
      evidence: evidencia.trim() || undefined, reduction: reduccion.trim() ? Number(reduccion) / 100 : undefined, expires_at: caduca,
    }),
    onSuccess: r => { toast.success(t('swr.controles_creados', { n: r.length })); qc.invalidateQueries({ queryKey: ['swr'] }); qc.invalidateQueries({ queryKey: ['sw'] }); onSaved() },
    onError: err,
  })
  const reduccionValida = !reduccion.trim() || (Number(reduccion) >= 10 && Number(reduccion) <= 90)
  const listo = elegidos.length > 0 && !!tipo && descripcion.trim().length >= 5 && !!caduca && reduccionValida
  return (
    <Modal open size="lg" onClose={onClose} title={t('swr.nuevo_control')} subtitle={t('swr.nuevo_control_desc')}>
      <div className="u-stack-12">
        <div className="u-stack-6">
          <div className="ds-eyebrow">{t('swr.hallazgos_elegidos', { n: elegidos.length })}</div>
          {elegidos.length === 0 ? <div className="u-text3-xs">{t('swr.elige_hallazgos')}</div> : (
            <div className="u-wrap-6">{elegidos.map(h => (
              <Checkbox key={h.id} checked onChange={() => setElegidos(elegidos.filter(x => x.id !== h.id))}
                label={`${h.vuln_id ?? '—'} · ${h.product_name ?? ''}${h.ci_name ? ` · ${h.ci_name}` : ''}`} />
            ))}</div>
          )}
          <Buscador label={t('swr.buscar_hallazgos')} value={buscar} placeholder={t('swr.buscar_hallazgos_ph')} onChange={setBuscar} />
          {candidatos.isFetching ? <Spinner size={16} /> : (candidatos.data?.items ?? []).filter(h => !ids.has(h.id)).slice(0, 10).map(h => (
            <Checkbox key={h.id} checked={false} onChange={() => setElegidos([...elegidos, { id: h.id, vuln_id: h.vuln_id, product_name: h.product_name, ci_name: h.ci_name }])}
              label={<span>{h.vuln_id ?? '—'} <SeveridadBadge s={h.severity} /> <span className="u-text3-xs">{h.product_name ?? ''}{h.ci_name ? ` · ${h.ci_name}` : ''}</span></span>} />
          ))}
        </div>
        <div className="sdm-form">
          <label className="sdm-field"><span>{t('swr.tipo_control')}</span>
            <Select suelto placeholder={false} value={tipo} onChange={ev => { setTipo(ev.target.value); setReduccion('') }}>
              {tipos.map(x => <option key={x} value={x}>{e('control', x)}</option>)}
            </Select></label>
          <Input label={t('swr.reduccion_pct')} type="number" min={10} max={90} step={5} value={reduccion}
            placeholder={porDefecto != null ? String(Math.round(porDefecto * 100)) : ''}
            hint={porDefecto != null ? t('swr.reduccion_defecto', { n: Math.round(porDefecto * 100) }) : undefined}
            error={reduccionValida ? undefined : t('swr.reduccion_rango')} onChange={ev => setReduccion(ev.target.value)} />
          <Input label={t('swr.caduca')} type="date" min={enDias(1)} value={caduca} onChange={ev => setCaduca(ev.target.value)} />
        </div>
        <Textarea label={t('swr.descripcion_control')} rows={3} value={descripcion} onChange={ev => setDescripcion(ev.target.value)} hint={t('swr.descripcion_control_ayuda')} />
        <Input label={t('swr.evidencia')} value={evidencia} placeholder={t('swr.evidencia_ph')} onChange={ev => setEvidencia(ev.target.value)} />
        <div className="u-actions-10">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button icon={<ShieldCheck size={14} />} disabled={!listo} loading={crear.isPending} onClick={() => crear.mutate()}>{t('swr.registrar_control')}</Button>
        </div>
      </div>
    </Modal>
  )
}

function IntentosDeExplotacion() {
  const t = useAppT()
  const e = useEtiquetaSwr()
  const toast = useToast()
  const qc = useQueryClient()
  const err = useErr()
  const { puede } = useAuth()
  const [dias, setDias] = useState(30)
  const [pagina, setPagina] = useState(1)
  const [abierto, setAbierto] = useState<string | null>(null)
  const [errores, setErrores] = useState<{ row: number; error: string }[]>([])
  const { data, isLoading } = useQuery({
    queryKey: ['swr', 'intentos', dias, pagina],
    queryFn: () => cmdbRiesgoApi.intentos({ days: dias, page: pagina, page_size: TAMANO }),
  })
  const importar = useMutation({
    mutationFn: cmdbRiesgoApi.importarIntentos,
    onSuccess: r => {
      toast.success(t('swr.intentos_importados', { filas: r.rows, nuevos: r.created, duplicados: r.duplicates, casados: r.matched }))
      setErrores(r.errors ?? [])
      qc.invalidateQueries({ queryKey: ['swr'] })
    },
    onError: err,
  })
  const items = data?.items ?? []
  const total = data?.total ?? 0
  return (
    <Section title={t('swr.intentos')} subtitle={t('swr.intentos_desc')}
      actions={<div className="u-wrap-8">
        <Segmentado aria-label={t('swr.periodo')} valor={String(dias)} onChange={v => { setDias(Number(v)); setPagina(1) }}
          opciones={[7, 30, 90].map(d => ({ valor: String(d), etiqueta: t('swr.n_dias', { n: d }) }))} />
        {puede('software.gestionar') && <BotonFichero accept=".csv,.json,text/csv,application/json" icon={<FileUp size={14} />} loading={importar.isPending} onFichero={f => importar.mutate(f)}>{t('swr.importar_intentos')}</BotonFichero>}
      </div>}>
      <div className="u-stack-12">
        {puede('software.gestionar') && <div className="u-text3-xs">{t('swr.importar_intentos_ayuda')}</div>}
        {errores.length > 0 && (
          <div className="sw-aviso-config sw-aviso-config--warning" role="status">
            <div className="u-flex1-min0">
              <div>{t('swr.errores_de_fila', { n: errores.length })}</div>
              <ul className="sw-lista-simple">{errores.slice(0, 20).map((x, i) => <li key={i}>{t('swr.fila_n', { n: x.row })}: {x.error}</li>)}</ul>
            </div>
          </div>
        )}
        {isLoading ? <Spinner size={16} /> : items.length === 0 ? <EmptyState icon={<Siren size={28} />} title={t('swr.sin_intentos')} /> : (
          <TablaSimple etiqueta={t('swr.intentos')} densidad="compacta">
            <thead><tr>
              <th>{t('swr.col_fecha')}</th><th>{t('swr.fuente')}</th><th>{t('sw.aviso')}</th><th>{t('sw.maquina')}</th>
              <th>{t('swr.accion')}</th><th className="sw-num">{t('swr.veces')}</th><th>{t('swr.hallazgo')}</th>
            </tr></thead>
            <tbody>{items.map(x => (
              <tr key={x.id}>
                <td className="u-text3-xs">{x.observed_at ? fmtDateTime(x.observed_at) : '—'}</td>
                <td>{x.source}</td>
                <td className="u-mono">{x.vuln_id ?? '—'}</td>
                <td>{x.ci_name ?? x.host ?? '—'}{x.ip && <div className="u-text3-xs u-mono">{x.ip}</div>}</td>
                <td><StatusBadge kind={ACCION_KIND[x.action] ?? 'neutral'} caps={false}>{e('accion_exploit', x.action)}</StatusBadge></td>
                <td className="sw-num">{x.count}</td>
                <td>{x.finding_id ? <Button variant="link" className="sw-enlace" onClick={() => setAbierto(x.finding_id as string)}>{t('swr.ver')}</Button> : <span className="u-text3-xs">{t('swr.sin_casar')}</span>}</td>
              </tr>
            ))}</tbody>
          </TablaSimple>
        )}
        <Pagination page={pagina} totalPages={Math.max(1, Math.ceil(total / TAMANO))} onChange={setPagina} total={total} pageSize={TAMANO} />
      </div>
      {abierto && <DetalleDeHallazgo id={abierto} onClose={() => setAbierto(null)} />}
    </Section>
  )
}

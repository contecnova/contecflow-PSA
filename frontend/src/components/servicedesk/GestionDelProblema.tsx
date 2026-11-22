/**
 * GestionDelProblema — el ciclo completo de un problema en pantalla
 * (mejoras de mercado 16-11-2026): incidentes vinculados, aprobación del RCA,
 * crear el cambio que lo arregla y el error conocido (KEDB) con su revisión y
 * su efectividad. Las rutas existían solo por API.
 *
 * Aprobar el RCA, vincular, crear el cambio y la KEDB son de administrador
 * (la guarda la pone el servidor); aquí se ocultan los botones a quien no lo es.
 *
 * 16-11-2026 (pasada de diseño): vacíos con icono lucide; fechas con DateInput
 * (antes `datetime-local` nativo); «solo administrador» como estado vacío con
 * candado en vez de texto gris suelto.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, GitPullRequest, Link2, ListChecks, Lock, ShieldCheck } from 'lucide-react'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { useAuth } from '../../context/AuthContext'
import { extractErr, fmtDate } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { Button, Checkbox, EmptyState, Modal, Select, Spinner, StatusBadge, Tabs, Input, Textarea } from '../ui'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { ticketsApi } from '../../services/api'
import { problemasApi } from '../../services/api/serviceDeskMercado'
import RcaWizardModal from './RcaWizardModal'
import { etiquetaSd } from '../../pages/service-desk/sdUtils'
import DateInput from '../ui/DateInput'
import './sdMercado.css'

/** Lo que hace falta del problema (vale el de la lista de problemas y el `SdProblema`). */
interface SdProblema {
  id: string | number; number?: string; title: string
  root_cause?: string | null; workaround?: string | null; fix_description?: string | null
}

export default function GestionDelProblema({ problema, onClose }: { problema: SdProblema; onClose: () => void }) {
  const t = useAppT()
  const [vista, setVista] = useState('incidentes')
  const { puede } = useAuth()
  const esAdmin = puede('sd.administrar')
  return (
    <Modal open size="lg" onClose={onClose} title={[problema.number, problema.title].filter(Boolean).join(" · ")}>
      <Tabs active={vista} onChange={setVista} ariaLabel={t('sd_mercado.problema')} items={[
        { id: 'incidentes', label: t('sd_mercado.prob_incidentes'), icon: <Link2 size={14} /> },
        { id: 'rca', label: t('sd_mercado.prob_rca'), icon: <ListChecks size={14} /> },
        { id: 'cambio', label: t('sd_mercado.prob_cambio'), icon: <GitPullRequest size={14} /> },
        { id: 'kedb', label: t('sd_mercado.prob_kedb'), icon: <ShieldCheck size={14} /> },
      ]} />
      <div className="u-mb-12" />
      {vista === 'incidentes' && <Incidentes problema={problema} esAdmin={esAdmin} />}
      {vista === 'rca' && <Rca problema={problema} esAdmin={esAdmin} />}
      {vista === 'cambio' && <CrearCambio problema={problema} esAdmin={esAdmin} />}
      {vista === 'kedb' && <Kedb problema={problema} esAdmin={esAdmin} />}
    </Modal>
  )
}

function useErr() {
  const toast = useToast()
  return (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
}

function Incidentes({ problema, esAdmin }: { problema: SdProblema; esAdmin: boolean }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const err = useErr()
  const [busqueda, setBusqueda] = useState('')
  const [elegidos, setElegidos] = useState<string[]>([])
  const { data = [], isLoading } = useQuery({ queryKey: ['sdm-prob-inc', problema.id], queryFn: () => problemasApi.incidentes(String(problema.id)) })
  const resultados = useQuery({
    queryKey: ['sdm-prob-busca', busqueda],
    queryFn: () => ticketsApi.list({ search: busqueda, page: 1, page_size: 10 }).then(r => r.data),
    enabled: esAdmin && busqueda.trim().length >= 2,
  })
  const vincular = useMutation({
    mutationFn: () => problemasApi.vincular(String(problema.id), elegidos),
    onSuccess: () => { setElegidos([]); setBusqueda(''); qc.invalidateQueries({ queryKey: ['sdm-prob-inc', problema.id] }); toast.success(t('sd_mercado.vinculados')) },
    onError: err,
  })
  const yaVinculados = new Set(data.map(d => d.id))
  return (
    <div className="u-stack-12">
      {isLoading ? <Spinner /> : data.length === 0 ? <EmptyState icon={<Link2 size={28} />} title={t('sd_mercado.sin_incidentes')} /> : (
        <ul className="sdm-list">
          {data.map(i => (
            <li key={i.id} className="sdm-list__item">
              <div className="u-flex1-min0">
                <div className="u-text1-sm-600 sdm-wrap"><span className="u-mono">{i.number}</span> {i.title}</div>
                <div className="u-wrap-6 u-text3-xs">
                  <StatusBadge caps={false}>{etiquetaCodigo(t, 'estado', i.status)}</StatusBadge>
                  <StatusBadge caps={false}>{etiquetaCodigo(t, 'estado', i.priority)}</StatusBadge>
                  {i.is_causal && <StatusBadge kind="warning" caps={false}>{t('sd_mercado.causal')}</StatusBadge>}
                  {i.linked_at && <span>{fmtDate(i.linked_at)}</span>}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
      {esAdmin && (
        <div className="ds-card sdm-card">
          <Input label={t('sd_mercado.buscar_incidentes')} value={busqueda} onChange={e => setBusqueda(e.target.value)} />
          {(resultados.data ?? []).filter(r => !yaVinculados.has(r.id)).map(r => (
            <Checkbox key={r.id} className="u-row-center-8 sdm-wrap" checked={elegidos.includes(r.id)}
              onChange={v => setElegidos(v ? [...elegidos, r.id] : elegidos.filter(x => x !== r.id))}
              label={<><span className="u-mono">{r.number}</span> {r.title}</>} />
          ))}
          <div className="u-row-end"><Button size="sm" onClick={() => vincular.mutate()} loading={vincular.isPending} disabled={elegidos.length === 0}>{t('sd_mercado.vincular_n', { n: elegidos.length })}</Button></div>
        </div>
      )}
    </div>
  )
}

function Rca({ problema, esAdmin }: { problema: SdProblema; esAdmin: boolean }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const err = useErr()
  const [asistente, setAsistente] = useState(false)
  const [evidencia, setEvidencia] = useState('')
  const aprobar = useMutation({
    mutationFn: () => problemasApi.aprobarRca(String(problema.id), evidencia.trim() || undefined),
    onSuccess: () => { setEvidencia(''); qc.invalidateQueries({ queryKey: ['sd-problems'] }); toast.success(t('sd_mercado.rca_aprobado')) },
    onError: err,
  })
  return (
    <div className="u-stack-12">
      <dl className="sdm-kv">
        <dt>{t('sd_mercado.causa_raiz')}</dt><dd>{problema.root_cause || '—'}</dd>
        <dt>{t('sd_mercado.solucion_temporal')}</dt><dd>{problema.workaround || '—'}</dd>
        <dt>{t('sd_mercado.solucion')}</dt><dd>{problema.fix_description || '—'}</dd>
      </dl>
      <div><Button variant="secondary" onClick={() => setAsistente(true)}>{t('sd_mercado.rca_asistente')}</Button></div>
      {esAdmin && (
        <div className="ds-card sdm-card">
          <div className="sdm-card__head"><CheckCircle2 size={14} aria-hidden="true" />{t('sd_mercado.rca_aprobar')}</div>
          <Textarea label={t('sd_mercado.evidencia')} rows={3} value={evidencia} onChange={e => setEvidencia(e.target.value)} />
          <div className="u-text2-xs">{t('sd_mercado.rca_aprobar_hint')}</div>
          <div className="u-row-end"><Button size="sm" onClick={() => aprobar.mutate()} loading={aprobar.isPending} disabled={!problema.root_cause}>{t('sd_mercado.aprobar')}</Button></div>
        </div>
      )}
      {asistente && <RcaWizardModal problem={problema} onClose={() => setAsistente(false)} onCompleted={() => { setAsistente(false); qc.invalidateQueries({ queryKey: ['sd-problems'] }) }} />}
    </div>
  )
}

function CrearCambio({ problema, esAdmin }: { problema: SdProblema; esAdmin: boolean }) {
  const t = useAppT()
  const toast = useToast()
  const err = useErr()
  const [tipo, setTipo] = useState('normal')
  const [inicio, setInicio] = useState('')
  const [fin, setFin] = useState('')
  const [creado, setCreado] = useState<string | null>(null)
  const crear = useMutation({
    mutationFn: () => problemasApi.crearCambio(String(problema.id), {
      change_type: tipo,
      planned_start: inicio ? new Date(inicio).toISOString() : undefined,
      planned_end: fin ? new Date(fin).toISOString() : undefined,
    }),
    onSuccess: d => { setCreado(d.number || d.id); toast.success(t('sd_mercado.cambio_creado')) },
    onError: err,
  })
  if (!esAdmin) return <EmptyState icon={<Lock size={28} />} title={t('sd_mercado.solo_admin')} />
  return (
    <div className="u-stack-12">
      <div className="u-text2-xs">{t('sd_mercado.cambio_desde_problema_desc')}</div>
      <div className="sdm-form">
        <label className="sdm-field"><span>{t('sd_mercado.tipo_cambio')}</span>
          <Select suelto placeholder={false} value={tipo} onChange={e => setTipo(e.target.value)}>
            {['standard', 'normal', 'emergency'].map(x => <option key={x} value={x}>{etiquetaSd('chg_type', x)}</option>)}
          </Select></label>
        <label className="sdm-field"><span>{t('sd_mercado.inicio_previsto')}</span><DateInput className="ds-input" withTime value={inicio} onChange={e => setInicio(e.target.value)} /></label>
        <label className="sdm-field"><span>{t('sd_mercado.fin_previsto')}</span><DateInput className="ds-input" withTime value={fin} onChange={e => setFin(e.target.value)} /></label>
      </div>
      {creado && <StatusBadge kind="success" caps={false}>{t('sd_mercado.cambio_creado_n', { n: creado })}</StatusBadge>}
      <div className="u-row-end"><Button onClick={() => crear.mutate()} loading={crear.isPending}>{t('sd_mercado.crear_cambio')}</Button></div>
    </div>
  )
}

function Kedb({ problema, esAdmin }: { problema: SdProblema; esAdmin: boolean }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const err = useErr()
  const [workaround, setWorkaround] = useState(problema.workaround || '')
  const [dias, setDias] = useState('')
  const [autoKb, setAutoKb] = useState(true)
  const efectividad = useQuery({ queryKey: ['sdm-kedb-ef', problema.id], queryFn: () => problemasApi.efectividadKedb(String(problema.id)), retry: false })
  const diasNum = dias ? Number(dias) : undefined
  const promover = useMutation({
    mutationFn: () => problemasApi.promoverKedb(String(problema.id), { workaround: workaround || undefined, review_days: diasNum, auto_kb: autoKb }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sd-problems'] }); qc.invalidateQueries({ queryKey: ['sdm-kedb-ef', problema.id] }); toast.success(t('sd_mercado.kedb_publicado')) },
    onError: err,
  })
  const revisar = useMutation({
    mutationFn: () => problemasApi.revisarKedb(String(problema.id), diasNum),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sdm-kedb-ef', problema.id] }); toast.success(t('sd_mercado.kedb_revisado')) },
    onError: err,
  })
  const ef = efectividad.data?.effectiveness_score
  return (
    <div className="u-stack-12">
      <div className="ds-card sdm-card">
        <div className="sdm-card__head">{t('sd_mercado.efectividad')}</div>
        {efectividad.isLoading ? <Spinner size={16} /> : ef == null
          ? <div className="u-text2-xs">{t('sd_mercado.efectividad_sin_datos')}</div>
          : <div className="u-row-center-8"><span className="u-md-700">{Math.round(ef * 100)} %</span><span className="u-text2-xs">{t('sd_mercado.efectividad_desc')}</span></div>}
      </div>
      {esAdmin ? (
        <>
          <Textarea label={t('sd_mercado.solucion_temporal')} rows={3} value={workaround} onChange={e => setWorkaround(e.target.value)} />
          <div className="sdm-form">
            <Input label={t('sd_mercado.dias_revision')} type="number" min={7} max={365} value={dias} placeholder={t('sd_mercado.dias_revision_defecto')} onChange={e => setDias(e.target.value)} />
            <Checkbox className="u-row-center-8" checked={!!autoKb} onChange={setAutoKb} label={t('sd_mercado.crear_articulo_kb')} />
          </div>
          <div className="u-actions-8">
            <Button variant="secondary" onClick={() => revisar.mutate()} loading={revisar.isPending}>{t('sd_mercado.marcar_revisado')}</Button>
            <Button onClick={() => promover.mutate()} loading={promover.isPending} disabled={!workaround.trim()}>{t('sd_mercado.publicar_kedb')}</Button>
          </div>
        </>
      ) : <EmptyState icon={<Lock size={28} />} title={t('sd_mercado.solo_admin')} />}
    </div>
  )
}

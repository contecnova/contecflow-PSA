/**
 * DemandaPage — /demand (22-11-2026): pantalla de trabajo del motor de flujos de
 * demanda (docs/FLUJO_DE_DEMANDA.md). Métricas, lista con filtros y expediente.
 * El expediente abierto va en `?id=` para poder enlazarlo. La configuración
 * (tipos y flujos) vive en Configuración → Aprobaciones y políticas → Flujos de demanda.
 */
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ClipboardList, Info, Plus } from 'lucide-react'
import Page from '../components/ui/Page'
import { Buscador, Button, Checkbox, EmptyState, Tabs, Input, Modal, ProjectSelect, Pulsable, Select, Spinner, TablaSimple } from '../components/ui'
import DetalleDemanda from '../components/demanda/DetalleDemanda'
import { EstadoDeDemandaBadge, SlaBadge, etiquetaDe, opcionesDe, useCatalogoDemanda } from '../components/demanda/comunes'
import { EntradaDeCampo } from '../components/demanda/PestanasDemanda'
import { valorParaGuardar } from '../components/demanda/utilDemanda'
import { demandaApi, ESTADOS_DE_DEMANDA, type FiltrosDeDemanda, type MetricasDeDemanda } from '../services/api/demanda'
import { useAppT } from '../i18n/AppLangContext'
import { useToast } from '../context/ToastContext'
import { useAuth } from '../context/AuthContext'
import { extractErr, fmtDate } from '../utils/helpers'
import '../components/planificador/planificador.css'
import '../components/demanda/demanda.css'

/** Claves de métricas conocidas y su texto; el resto se enseña con la clave legible. */
const METRICAS_CONOCIDAS = ['total', 'open', 'pending_info', 'stalled', 'at_risk', 'bypass', 'avg_effective_hours', 'pending_for_me', 'by_status', 'by_phase']

function legible(k: string) { return k.replace(/_/g, ' ') }

/** Normaliza un valor de métrica a pares «etiqueta, valor»; null si es un escalar. */
function paresDe(v: unknown): Array<[string, string]> | null {
  if (Array.isArray(v)) {
    return v.map((x, i): [string, string] => {
      if (x && typeof x === 'object') {
        const o = x as Record<string, unknown>
        const nombre = o.name ?? o.phase_name ?? o.phase ?? o.key ?? o.status ?? String(i + 1)
        const n = o.count ?? o.total ?? o.value ?? ''
        return [String(nombre), String(n)]
      }
      return [String(i + 1), String(x)]
    })
  }
  if (v && typeof v === 'object') return Object.entries(v as Record<string, unknown>).map(([k, x]) => [k, typeof x === 'object' ? JSON.stringify(x) : String(x)])
  return null
}

function Metricas() {
  const t = useAppT()
  const { data, isLoading } = useQuery<MetricasDeDemanda>({ queryKey: ['demand-metrics'], queryFn: demandaApi.metricas, refetchInterval: 60_000 })
  if (isLoading || !data) return null
  const claves = [...METRICAS_CONOCIDAS.filter(k => k in data), ...Object.keys(data).filter(k => !METRICAS_CONOCIDAS.includes(k))]
  if (claves.length === 0) return null
  return (
    <div className="dem-metricas">
      {claves.map(k => {
        const v = data[k]
        const pares = paresDe(v)
        const clave = `demanda.m_${k}`
        const texto = t(clave)
        const etiqueta = texto === clave ? legible(k) : texto
        return (
          <div key={k} className="ds-card dem-metrica">
            <span className="ds-eyebrow dem-metrica__etiqueta">{etiqueta}</span>
            {pares ? (
              pares.length === 0 ? <span className="dem-metrica__valor">0</span>
                : pares.map(([n, c]) => <span key={n} className="dem-metrica__sub">{etiquetaDe(t, 'estado', n)}: {c}</span>)
            ) : (
              <span className="dem-metrica__valor">{typeof v === 'number' ? (Number.isInteger(v) ? v : v.toFixed(1)) : String(v ?? '—')}</span>
            )}
          </div>
        )
      })}
    </div>
  )
}

/** También la usa el portal del proveedor (`pages/proveedores/PestanaSolicitudes.tsx`). */
export function NuevaSolicitud({ onClose, onCreada, mia }: { onClose: () => void; onCreada: (id: string) => void; mia?: boolean }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const catalogo = useCatalogoDemanda()
  const puedeGestionar = useAuth().puede('demanda.gestionar')
  const { data: oferta } = useQuery({ queryKey: ['demand-mine-types'], queryFn: () => demandaApi.tiposParaSolicitar('operator') })
  const tipos = (Array.isArray(oferta) ? oferta : oferta?.types) ?? []
  const [tipo, setTipo] = useState('')
  const [titulo, setTitulo] = useState('')
  const [ambito, setAmbito] = useState('')
  const [proyecto, setProyecto] = useState('')
  const [refAmbito, setRefAmbito] = useState('')
  const [enNombreDe, setEnNombreDe] = useState('')
  const [valores, setValores] = useState<Record<string, string>>({})
  const elegido = tipos.find(x => x.key === tipo)
  const ambitos = elegido?.scopes?.length ? elegido.scopes : ['project']
  const ambitoActual = ambito && ambitos.includes(ambito) ? ambito : ambitos[0]
  const alcanceConRef = ambitoActual === 'service' || ambitoActual === 'asset'
  const { data: opcionesDeAlcance = [], isLoading: cargandoAlcance } = useQuery({
    queryKey: ['demand-scope-options', ambitoActual],
    queryFn: () => demandaApi.opcionesDeAlcance(ambitoActual as 'service' | 'asset'),
    enabled: alcanceConRef,
  })
  const faltantes = (elegido?.submit_required || []).filter(k => k === 'title' ? !titulo.trim() : !(valores[k] ?? '').trim())
  const faltaAmbito = (ambitoActual === 'project' && !!elegido?.requires_project && !proyecto) || ((ambitoActual === 'service' || ambitoActual === 'asset') && !refAmbito.trim())
  const crear = useMutation({
    mutationFn: (enviar: boolean) => {
      const data: Record<string, unknown> = {}
      for (const c of elegido?.fields || []) if ((valores[c.key] ?? '') !== '') data[c.key] = valorParaGuardar(c.type, valores[c.key])
      const cuerpo = {
        type_key: tipo, title: titulo.trim(), data, submit: enviar,
        project_id: ambitoActual === 'project' ? proyecto || null : null,
        scope_kind: ambitoActual, scope_ref_id: ambitoActual === 'service' || ambitoActual === 'asset' ? refAmbito.trim() || null : null,
        ...(!mia && enNombreDe ? { requester_user_id: enNombreDe } : {}),
      }
      return mia ? demandaApi.crearMia(cuerpo, 'operator') : demandaApi.crear(cuerpo)
    },
    onSuccess: (d, enviar) => { toast.success(t(enviar ? 'demanda.enviada' : 'demanda.creada')); qc.invalidateQueries({ queryKey: ['demand-requests'] }); qc.invalidateQueries({ queryKey: ['demand-mine'] }); onCreada(d.id) },
    onError: (e: unknown) => toast.error(extractErr(e, t('demanda.error'))),
  })
  const falta = !tipo || !titulo.trim() || faltaAmbito
  return (
    <Modal open onClose={onClose} size="lg" title={t('demanda.nueva_solicitud')} subtitle={t('demanda.nueva_ayuda')}>
      <div className="u-stack-16">
        <Select label={t('demanda.tipo')} required value={tipo} onChange={e => { setTipo(e.target.value); setValores({}) }} options={tipos.map(x => ({ value: x.key, label: x.name }))} />
        <Input label={t('demanda.campo_titulo')} required value={titulo} onChange={e => setTitulo(e.target.value)} />
        {elegido && (
          <>
            {ambitos.length > 1 && <Select label={t('demanda.sobre_que')} placeholder={false} value={ambitoActual} onChange={e => setAmbito(e.target.value)} options={opcionesDe(t, 'ambito', ambitos)} />}
            {ambitoActual === 'project' && (
              <ProjectSelect label={<>{t('demanda.proyecto')}{elegido.requires_project && <span className="u-danger"> *</span>}</>} value={proyecto} onChange={id => setProyecto(id)} />
            )}
            {alcanceConRef && <Select label={t('demanda.referencia_ambito')} required value={refAmbito} onChange={e => setRefAmbito(e.target.value)} options={opcionesDeAlcance} disabled={cargandoAlcance} />}
            {!mia && puedeGestionar && catalogo.users.length > 0 && (
              <Select label={t('demanda.en_nombre_de')} hint={t('demanda.en_nombre_de_ayuda')} value={enNombreDe} onChange={e => setEnNombreDe(e.target.value)} options={catalogo.users} />
            )}
            <div className="dem-campos">
              {elegido.fields.map(c => (
                <div key={c.key} className={c.type === 'textarea' ? 'dem-campo--ancho' : ''}>
                  <EntradaDeCampo campo={{ key: c.key, label: c.label, type: c.type, options: c.options, critical: !!c.critical, owner: 'client', editable: true, required_now: elegido.submit_required.includes(c.key) }}
                    valor={valores[c.key] ?? ''} onChange={v => setValores(x => ({ ...x, [c.key]: v }))} />
                </div>
              ))}
            </div>
            {faltantes.length > 0 && <p className="plan-muted">{t('demanda.faltan_para_enviar')}</p>}
          </>
        )}
        <div className="dem-acciones">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button variant="secondary" loading={crear.isPending} disabled={falta} onClick={() => crear.mutate(false)}>{t('demanda.guardar_borrador')}</Button>
          <Button loading={crear.isPending} disabled={falta || faltantes.length > 0} onClick={() => crear.mutate(true)}>{t('demanda.enviar')}</Button>
        </div>
      </div>
    </Modal>
  )
}

/** También la usa el portal del proveedor (`pages/proveedores/PestanaSolicitudes.tsx`). */
export function ListaDeDemandas({ onAbrir, mias }: { onAbrir: (id: string) => void; mias?: boolean }) {
  const t = useAppT()
  const [f, setF] = useState<FiltrosDeDemanda>({})
  const [busqueda, setBusqueda] = useState('')
  const { data: tipos = [] } = useQuery({ queryKey: ['demand-types'], queryFn: demandaApi.tipos })
  const { data: filas = [], isLoading } = useQuery({ queryKey: mias ? ['demand-mine'] : ['demand-requests', f], queryFn: () => mias ? demandaApi.mias() : demandaApi.solicitudes(f) })
  const fases = [...new Map(filas.filter(x => x.current_phase_key).map(x => [x.current_phase_key as string, x.current_phase_name || (x.current_phase_key as string)])).entries()]
  const poner = (parche: FiltrosDeDemanda) => setF(x => ({ ...x, ...parche }))
  return (
    <div className="u-stack-16">
      {!mias && <div className="dem-filtros">
        <Select suelto placeholder={false} className="ds-input dem-filtro" aria-label={t('demanda.filtro_estado')} value={f.status ?? ''} onChange={e => poner({ status: e.target.value })}>
          <option value="">{t('demanda.todos_los_estados')}</option>
          {opcionesDe(t, 'estado', ESTADOS_DE_DEMANDA).map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </Select>
        <Select suelto placeholder={false} className="ds-input dem-filtro" aria-label={t('demanda.filtro_fase')} value={f.phase ?? ''} onChange={e => poner({ phase: e.target.value })}>
          <option value="">{t('demanda.todas_las_fases')}</option>
          {fases.map(([k, n]) => <option key={k} value={k}>{n}</option>)}
        </Select>
        <Select suelto placeholder={false} className="ds-input dem-filtro" aria-label={t('demanda.filtro_tipo')} value={f.type ?? ''} onChange={e => poner({ type: e.target.value })}>
          <option value="">{t('demanda.todos_los_tipos')}</option>
          {tipos.map(x => <option key={x.key} value={x.key}>{x.name}</option>)}
        </Select>
        <Checkbox label={t('demanda.pendientes_para_mi')} checked={!!f.pending_for_me} onChange={ok => poner({ pending_for_me: ok })} />
        <form className="dem-fila" onSubmit={e => { e.preventDefault(); poner({ q: busqueda.trim() }) }}>
          <Buscador className="dem-buscar" aria-label={t('demanda.buscar')} placeholder={t('demanda.buscar')} value={busqueda} onChange={setBusqueda} />
          <Button type="submit" size="sm" variant="secondary">{t('demanda.buscar')}</Button>
        </form>
      </div>}
      {isLoading ? <Spinner /> : filas.length === 0 ? (
        <EmptyState icon={<ClipboardList size={28} />} title={t('demanda.sin_solicitudes')} description={t('demanda.sin_solicitudes_desc')} />
      ) : (
        <div className="ds-card plan-tabla-scroll">
          <TablaSimple claseTabla="plan-tabla">
            <thead>
              <tr>
                <th>{t('demanda.col_codigo')}</th><th>{t('demanda.col_titulo')}</th><th>{t('demanda.tipo')}</th><th>{t('demanda.col_estado')}</th>
                <th>{t('demanda.col_fase')}</th><th>{t('demanda.proyecto')}</th><th>{t('demanda.solicitante')}</th><th>{t('demanda.col_plazo')}</th>
              </tr>
            </thead>
            <tbody>
              {filas.map(x => (
                <tr key={x.id}>
                  <td className="dem-mono">{x.code}</td>
                  <td><Pulsable type="button" className="plan-chip" onClick={() => onAbrir(x.id)}>{x.title}</Pulsable></td>
                  <td>{x.type_name}</td>
                  <td><EstadoDeDemandaBadge estado={x.status} /></td>
                  <td>{x.current_phase_name ?? '—'}</td>
                  <td>{x.project_name ?? (x.standalone ? t('demanda.iniciativa_independiente') : '—')}</td>
                  <td>{x.requester_name ?? '—'}</td>
                  <td><span className="dem-fila">{x.sla_due_at ? fmtDate(x.sla_due_at) : '—'}<SlaBadge estado={x.sla_state} /></span></td>
                </tr>
              ))}
            </tbody>
          </TablaSimple>
        </div>
      )}
    </div>
  )
}

export default function DemandaPage() {
  const t = useAppT()
  const auth = useAuth()
  const [params, setParams] = useSearchParams()
  // 23-11-2026 (A7 del 04): sin botón «Configurar» en el módulo. Si no hay tipos de
  // solicitud, un aviso lo explica y enlaza a Configuración solo para quien puede.
  const { data: tiposDeDemanda, isSuccess: tiposCargados } = useQuery({ queryKey: ['demand-types'], queryFn: demandaApi.tipos })
  const sinTipos = tiposCargados && (tiposDeDemanda ?? []).length === 0
  const [nueva, setNueva] = useState(false)
  const [vista, setVista] = useState<'todas' | 'mias'>('mias')
  const abierta = params.get('id') || ''
  const abrir = (id: string) => setParams(id ? { id } : {})
  const gestiona = auth.puede('demanda.gestionar')
  const verTodas = auth.puede('demanda.ver')
  const vistaActual = verTodas ? vista : 'mias'
  return (
    <Page icon={<ClipboardList size={18} />} title={t('demanda.titulo')} subtitle={t('demanda.subtitulo')}
      actions={(
        <span className="dem-fila">
          <Button icon={<Plus size={13} />} onClick={() => setNueva(true)}>{t('demanda.nueva_solicitud')}</Button>
        </span>
      )}>
      {sinTipos && (
        <div className="dem-aviso" role="note">
          <Info size={13} aria-hidden /> {t('demanda.sin_tipos_configurados')}
          {auth.puede('demanda.config') && <> <Link to="/settings/demanda">{t('demanda.ir_a_configuracion')}</Link></>}
        </div>
      )}
      {abierta ? <DetalleDemanda id={abierta} onVolver={() => abrir('')} /> : (
        <div className="u-stack-16">
          {verTodas && <Tabs ariaLabel={t('demanda.vistas')} active={vistaActual} onChange={v => setVista(v as 'todas' | 'mias')}
            items={[{ id: 'mias', label: t('demanda.mis_solicitudes') }, { id: 'todas', label: t('demanda.todas_las_solicitudes') }]} />}
          {vistaActual === 'todas' && <Metricas />}
          <ListaDeDemandas key={vistaActual} onAbrir={abrir} mias={vistaActual === 'mias'} />
        </div>
      )}
      {nueva && <NuevaSolicitud mia={!gestiona} onClose={() => setNueva(false)} onCreada={id => { setNueva(false); abrir(id) }} />}
    </Page>
  )
}

/**
 * Portal interno (`/mi-departamento`, 22-11-2026): secciones de una unidad.
 * Todo lo acota el backend (`portal.py`) a las unidades de quien llama; firmar
 * hitos y UAT según `can_sign`, coste y cargos solo con `can_see_costs`.
 * Ver docs/CLIENTES_INTERNOS.md §5.
 */
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, FolderKanban, Plus, Send, Star, X } from 'lucide-react'
import { Button, Card, EmptyState, Input, KpiCard, LoadBar, Modal, Segmentado, Select, Spinner, TablaSimple, Textarea } from '../../components/ui'
import StatusBadge from '../../components/ui/StatusBadge'
import { useToast } from '../../context/ToastContext'
import { portalInternoApi } from '../../services/api/clientesInternos'
import type { PeticionIn, TipoDeEncuesta, UnidadDelPortal } from '../../services/api/clientesInternos'
import { useFormatoMoneda } from '../../hooks/useFormatoMoneda'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { useAppT } from '../../i18n/AppLangContext'
import { extractErr, fmtDate, fmtNumber } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { AvisosInternos, Semaforo, useT } from './comunes'
import { FUENTES_DE_COSTE, TONO_CARGO, etiquetaInterna, numeroONull, textoONull } from './logica'
import { ListaDeAdopcion } from './FichaDeUnidad'
import { ListaDeBeneficios } from './BeneficiosDeProyecto'

const clave = (cid: string, ...resto: string[]) => ['internal-portal', cid, ...resto]
const err = (toast: ReturnType<typeof useToast>) => (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))

/** Estado o prioridad con la etiqueta común de códigos. */
function useEstado() {
  const tApp = useAppT()
  return (codigo: string | null | undefined) => (codigo ? etiquetaCodigo(tApp, 'estado', codigo) : '—')
}

function Valorar({ cid, onClose }: { cid: string; onClose: () => void }) {
  const t = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const [tipo, setTipo] = useState<TipoDeEncuesta>('nps')
  const [nota, setNota] = useState<number | null>(null)
  const [comentario, setComentario] = useState('')
  const escala = tipo === 'nps' ? Array.from({ length: 11 }, (_, i) => i) : [1, 2, 3, 4, 5]
  const enviar = useMutation({
    mutationFn: () => portalInternoApi.valorar(cid, { score: nota as number, comment: textoONull(comentario), survey_type: tipo }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: clave(cid) }); toast.success(t('internos.gracias_valoracion')); onClose() },
    onError: err(toast),
  })
  return (
    <Modal open onClose={onClose} width={560} title={t('internos.valorar')}>
      <div className="u-stack-8">
        <Segmentado aria-label={t('internos.tipo_encuesta')} valor={tipo} onChange={v => { setTipo(v as TipoDeEncuesta); setNota(null) }}
          opciones={[{ valor: 'nps', etiqueta: t('internos.nps') }, { valor: 'csat', etiqueta: t('internos.csat') }]} />
        <p className="u-text2-sm">{tipo === 'nps' ? t('internos.pregunta_nps') : t('internos.pregunta_csat')}</p>
        <div className="int-escala" role="group" aria-label={t('internos.puntuacion')}>
          {escala.map(n => (
            <Button key={n} size="sm" variant={nota === n ? 'primary' : 'secondary'} aria-pressed={nota === n} onClick={() => setNota(n)}>{String(n)}</Button>
          ))}
        </div>
        <Textarea label={t('internos.comentario')} value={comentario} onChange={e => setComentario(e.target.value)} rows={3} />
        <p className="int-nota">{t('internos.valoracion_privacidad')}</p>
        <div className="u-actions-8">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button icon={<Star size={14} />} onClick={() => enviar.mutate()} loading={enviar.isPending} disabled={nota == null || enviar.isPending}>{t('internos.enviar')}</Button>
        </div>
      </div>
    </Modal>
  )
}

export function Resumen({ unidad }: { unidad: UnidadDelPortal }) {
  const t = useT()
  const fmtMoneda = useFormatoMoneda()
  const [valorando, setValorando] = useState(false)
  const { data: r, isLoading } = useQuery({ queryKey: clave(unidad.id, 'summary'), queryFn: () => portalInternoApi.resumen(unidad.id) })
  if (isLoading || !r) return <Spinner />
  return (
    <div className="u-stack-8">
      {unidad.can_see_costs && <AvisosInternos avisos={r.warnings} />}
      <div className="ds-grid-stats">
        <KpiCard label={t('internos.proyectos_activos')} value={r.projects_active} />
        <KpiCard label={t('internos.hitos_pendientes')} value={r.milestones_pending} warning={r.milestones_pending > 0} />
        <KpiCard label={t('internos.uat_pendientes')} value={r.uat_pending} warning={r.uat_pending > 0} />
        <KpiCard label={t('internos.tickets_abiertos')} value={r.tickets_open} />
        <KpiCard label={t('internos.sla_en_plazo')} value={<Semaforo pct={r.sla.pct} tono={r.sla.tone} />} sub={t('internos.n_tickets', { n: r.sla.total })} />
        <KpiCard label={t('internos.nps')} value={r.satisfaction.nps != null ? <Semaforo pct={r.satisfaction.nps} tono={r.satisfaction.tone}>{fmtNumber(r.satisfaction.nps, 0)}</Semaforo> : '—'}
          sub={t('internos.n_respuestas', { n: r.satisfaction.responses })} />
        {r.budget && (
          <KpiCard label={t('internos.presupuesto_anio', { anio: r.budget.year })}
            value={<Semaforo pct={r.budget.pct} tono={r.budget.tone} />}
            sub={`${fmtMoneda(r.budget.consumed, { moneda: r.budget.currency })} / ${fmtMoneda(r.budget.budget, { moneda: r.budget.currency })}`} />
        )}
      </div>
      <Card className="int-bloque">
        <div className="int-barra">
          <div>
            <div className="int-bloque__titulo">{t('internos.tu_opinion')}</div>
            <div className="int-sub">{t('internos.tu_opinion_d')}</div>
          </div>
          <Button size="sm" icon={<Star size={14} />} onClick={() => setValorando(true)}>{t('internos.valorar')}</Button>
        </div>
      </Card>
      {valorando && <Valorar cid={unidad.id} onClose={() => setValorando(false)} />}
    </div>
  )
}

export function Proyectos({ cid }: { cid: string }) {
  const t = useT()
  const estado = useEstado()
  const { data = [], isLoading } = useQuery({ queryKey: clave(cid, 'projects'), queryFn: () => portalInternoApi.proyectos(cid) })
  if (isLoading) return <Spinner />
  if (!data.length) return <EmptyState icon={<FolderKanban size={28} />} title={t('internos.sin_proyectos')} />
  return (
    <div className="u-stack-8">
      {data.map(p => (
        <Card key={p.id} className="int-item">
          <div className="u-min0 u-flex1">
            <div className="u-row-center-8">
              <span className="int-item__titulo">{p.code ? `${p.code} · ${p.name}` : p.name}</span>
              <StatusBadge kind="neutral" caps={false}>{estado(p.status)}</StatusBadge>
              {p.milestones_pending > 0 && <StatusBadge kind="warning" caps={false}>{t('internos.n_hitos_pendientes', { n: p.milestones_pending })}</StatusBadge>}
            </div>
            <div className="int-sub">{fmtDate(p.start_date)} – {fmtDate(p.end_date)}</div>
            {p.progress != null && <LoadBar value={p.progress} label={`${fmtNumber(p.progress, 0)}%`} />}
          </div>
        </Card>
      ))}
    </div>
  )
}

/** Firmar o rechazar con nota (hitos y UAT). */
function Firma({ titulo, opciones, onFirmar, onClose, cargando }: {
  titulo: string; opciones: { valor: string; etiqueta: string; peligro?: boolean }[]; onFirmar: (valor: string, nota: string | null) => void; onClose: () => void; cargando: boolean
}) {
  const t = useT()
  const [nota, setNota] = useState('')
  return (
    <Modal open onClose={onClose} width={480} title={titulo}>
      <div className="u-stack-8">
        <Textarea label={t('internos.nota')} value={nota} onChange={e => setNota(e.target.value)} rows={3} />
        <div className="u-actions-8">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          {opciones.map(o => (
            <Button key={o.valor} variant={o.peligro ? 'secondary' : 'primary'} icon={o.peligro ? <X size={14} /> : <Check size={14} />}
              disabled={cargando} onClick={() => onFirmar(o.valor, textoONull(nota))}>{o.etiqueta}</Button>
          ))}
        </div>
      </div>
    </Modal>
  )
}

export function Hitos({ cid }: { cid: string }) {
  const t = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const estado = useEstado()
  const [firmando, setFirmando] = useState<{ id: string; name: string } | null>(null)
  const { data = [], isLoading } = useQuery({ queryKey: clave(cid, 'milestones'), queryFn: () => portalInternoApi.hitos(cid) })
  const firmar = useMutation({
    mutationFn: ({ id, approve, note }: { id: string; approve: boolean; note: string | null }) => portalInternoApi.firmarHito(id, approve, note),
    onSuccess: (_r, v) => { qc.invalidateQueries({ queryKey: clave(cid) }); toast.success(v.approve ? t('internos.hito_firmado') : t('internos.hito_rechazado')); setFirmando(null) },
    onError: err(toast),
  })
  if (isLoading) return <Spinner />
  if (!data.length) return <p className="u-text2-sm">{t('internos.sin_hitos')}</p>
  return (
    <div className="u-stack-8">
      {data.map(h => (
        <Card key={h.id} className="int-item">
          <div className="u-min0">
            <div className="u-row-center-8">
              <span className="int-item__titulo">{h.name}</span>
              {h.billing_status && <StatusBadge kind="neutral" caps={false}>{estado(h.billing_status)}</StatusBadge>}
            </div>
            <div className="int-sub">
              {[h.project_name, h.due_date && t('internos.para_el', { fecha: fmtDate(h.due_date) }),
                h.approval_requested_at && t('internos.pedida_el', { fecha: fmtDate(h.approval_requested_at) })].filter(Boolean).join(' · ')}
            </div>
          </div>
          {h.can_sign && <Button size="sm" onClick={() => setFirmando({ id: h.id, name: h.name })}>{t('internos.firmar')}</Button>}
        </Card>
      ))}
      {firmando && (
        <Firma titulo={t('internos.firmar_hito', { nombre: firmando.name })} cargando={firmar.isPending} onClose={() => setFirmando(null)}
          opciones={[{ valor: 'no', etiqueta: t('internos.rechazar'), peligro: true }, { valor: 'si', etiqueta: t('internos.aprobar') }]}
          onFirmar={(v, note) => firmar.mutate({ id: firmando.id, approve: v === 'si', note })} />
      )}
    </div>
  )
}

export function Uat({ cid }: { cid: string }) {
  const t = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const estado = useEstado()
  const [firmando, setFirmando] = useState<{ id: string; title: string } | null>(null)
  const { data = [], isLoading } = useQuery({ queryKey: clave(cid, 'uat'), queryFn: () => portalInternoApi.uat(cid) })
  const firmar = useMutation({
    mutationFn: ({ id, result, notes }: { id: string; result: 'passed' | 'failed'; notes: string | null }) => portalInternoApi.firmarUat(id, result, notes),
    onSuccess: () => { qc.invalidateQueries({ queryKey: clave(cid) }); toast.success(t('internos.uat_firmada')); setFirmando(null) },
    onError: err(toast),
  })
  if (isLoading) return <Spinner />
  if (!data.length) return <p className="u-text2-sm">{t('internos.sin_uat')}</p>
  return (
    <div className="u-stack-8">
      {data.map(s => (
        <Card key={s.id} className="int-item">
          <div className="u-min0">
            <div className="u-row-center-8">
              <span className="int-item__titulo">{s.code ? `${s.code} · ${s.title}` : s.title}</span>
              <StatusBadge kind="neutral" caps={false}>{estado(s.status)}</StatusBadge>
              {s.signed && <StatusBadge kind="success" caps={false}>{t('internos.firmada')}</StatusBadge>}
            </div>
            <div className="int-sub">
              {[s.project_name, s.deadline && t('internos.para_el', { fecha: fmtDate(s.deadline) }), s.test_environment].filter(Boolean).join(' · ')}
            </div>
          </div>
          {s.can_sign && !s.signed && <Button size="sm" onClick={() => setFirmando({ id: s.id, title: s.title })}>{t('internos.firmar')}</Button>}
        </Card>
      ))}
      {firmando && (
        <Firma titulo={t('internos.firmar_uat', { nombre: firmando.title })} cargando={firmar.isPending} onClose={() => setFirmando(null)}
          opciones={[{ valor: 'failed', etiqueta: t('internos.uat_fallida'), peligro: true }, { valor: 'passed', etiqueta: t('internos.uat_superada') }]}
          onFirmar={(v, notes) => firmar.mutate({ id: firmando.id, result: v as 'passed' | 'failed', notes })} />
      )}
    </div>
  )
}

export function TicketsYSla({ cid }: { cid: string }) {
  const t = useT()
  const estado = useEstado()
  const { data: tickets = [], isLoading } = useQuery({ queryKey: clave(cid, 'tickets'), queryFn: () => portalInternoApi.tickets(cid) })
  const { data: sla } = useQuery({ queryKey: clave(cid, 'sla'), queryFn: () => portalInternoApi.sla(cid), retry: false })
  return (
    <div className="u-stack-8">
      {sla && (
        <div className="ds-grid-stats">
          <KpiCard label={t('internos.sla_en_plazo')} value={<Semaforo pct={sla.pct} tono={sla.tone} />} sub={`${fmtDate(sla.from)} – ${fmtDate(sla.to)}`} />
          <KpiCard label={t('internos.tickets_resueltos')} value={`${sla.resolved} / ${sla.total}`} />
          <KpiCard label={t('internos.col_en_plazo')} value={sla.on_time} />
          <KpiCard label={t('internos.ola_incumplidos')} value={sla.ola_breached} danger={sla.ola_breached > 0} />
        </div>
      )}
      {isLoading ? <Spinner /> : !tickets.length ? <p className="u-text2-sm">{t('internos.sin_tickets')}</p> : (
        <div className="u-scroll-x">
          <TablaSimple claseTabla="u-table" etiqueta={t('internos.tab_tickets')}>
            <thead>
              <tr>{[t('internos.col_numero'), t('internos.titulo'), t('internos.col_prioridad'), t('internos.col_estado'), t('internos.col_creado'), t('internos.col_sla')].map(h => <th key={h} scope="col" className="int-th">{h}</th>)}</tr>
            </thead>
            <tbody>
              {tickets.map(k => (
                <tr key={k.id}>
                  <td className="int-td int-td--muted">{k.number || '—'}</td>
                  <td className="int-td">{k.title}</td>
                  <td className="int-td">{estado(k.priority)}</td>
                  <td className="int-td">{estado(k.status)}</td>
                  <td className="int-td int-td--muted">{fmtDate(k.created_at)}</td>
                  <td className="int-td">
                    {k.sla_resolution_breached == null ? '—' : (
                      <StatusBadge kind={k.sla_resolution_breached ? 'danger' : 'success'} caps={false}>
                        {k.sla_resolution_breached ? t('internos.fuera_de_plazo') : t('internos.en_plazo')}
                      </StatusBadge>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </TablaSimple>
        </div>
      )}
    </div>
  )
}

export function CosteYCargos({ cid }: { cid: string }) {
  const t = useT()
  const fmtMoneda = useFormatoMoneda()
  const [year, setYear] = useState(new Date().getFullYear())
  const { data: coste, isLoading } = useQuery({ queryKey: clave(cid, 'cost', String(year)), queryFn: () => portalInternoApi.coste(cid, year) })
  const { data: cargos = [] } = useQuery({ queryKey: clave(cid, 'charges'), queryFn: () => portalInternoApi.cargos(cid) })
  const m = (n: number | null | undefined, moneda?: string) => (n == null ? '—' : fmtMoneda(n, { moneda: moneda || coste?.currency }))
  return (
    <div className="u-stack-8">
      <div className="int-barra__filtros">
        <Input label={t('internos.anio')} type="number" min={2000} max={2100} value={String(year)}
          onChange={e => { const n = Number(e.target.value); if (Number.isFinite(n) && n > 1999) setYear(n) }} />
      </div>
      {isLoading ? <Spinner /> : coste && (
        <div className="ds-grid-stats">
          <KpiCard label={t('internos.coste_total')} value={m(coste.total)} accent />
          {coste.budget && (
            <KpiCard label={t('internos.presupuesto_anio', { anio: coste.budget.year })} value={m(coste.budget.budget, coste.budget.currency)}
              sub={<Semaforo pct={coste.budget.pct} tono={coste.budget.tone} />} />
          )}
          {FUENTES_DE_COSTE.filter(s => (coste.by_source[s] ?? 0) !== 0).map(s => (
            <KpiCard key={s} label={etiquetaInterna(t, 'fuente_', s)} value={m(coste.by_source[s])} />
          ))}
        </div>
      )}
      <Card className="int-bloque">
        <div className="int-bloque__titulo">{t('internos.tab_cargos')}</div>
        {!cargos.length ? <p className="u-text2-sm">{t('internos.sin_cargos')}</p> : (
          <div className="u-scroll-x">
            <TablaSimple claseTabla="u-table" etiqueta={t('internos.tab_cargos')}>
              <thead><tr>{[t('internos.col_numero'), t('internos.periodo'), t('internos.col_importe'), t('internos.col_estado')].map(h => <th key={h} scope="col" className="int-th">{h}</th>)}</tr></thead>
              <tbody>
                {cargos.map(c => (
                  <tr key={c.id}>
                    <td className="int-td">{c.number || '—'}</td>
                    <td className="int-td int-td--muted">{c.period}</td>
                    <td className="int-td int-td--num">{m(c.total, c.currency)}</td>
                    <td className="int-td"><StatusBadge kind={TONO_CARGO[c.status] || 'neutral'} caps={false}>{etiquetaInterna(t, 'cargo_estado_', c.status)}</StatusBadge></td>
                  </tr>
                ))}
              </tbody>
            </TablaSimple>
          </div>
        )}
      </Card>
    </div>
  )
}

function Pedir({ cid, onClose }: { cid: string; onClose: () => void }) {
  const t = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const [f, setF] = useState({ title: '', description: '', kind: 'proyecto', estimated_budget: '', wanted_start: '', wanted_end: '' })
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF(x => ({ ...x, [k]: e.target.value }))
  const enviar = useMutation({
    mutationFn: () => {
      const d: PeticionIn = {
        title: f.title.trim(), description: f.description.trim(), kind: f.kind as PeticionIn['kind'],
        estimated_budget: numeroONull(f.estimated_budget), wanted_start: f.wanted_start || null, wanted_end: f.wanted_end || null,
      }
      return portalInternoApi.pedir(cid, d)
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: clave(cid, 'requests') }); toast.success(t('internos.peticion_enviada')); onClose() },
    onError: err(toast),
  })
  return (
    <Modal open onClose={onClose} width={600} title={t('internos.pedir')}>
      <div className="u-stack-8">
        <Select label={t('internos.col_tipo')} value={f.kind} placeholder={false} onChange={set('kind')}
          options={[{ value: 'proyecto', label: t('internos.pedir_proyecto') }, { value: 'servicio', label: t('internos.pedir_servicio') }]} />
        {f.kind === 'servicio' && (
          <p className="int-nota">{t('internos.servicio_catalogo')} <Link to="/service-desk?create=1">{t('internos.abrir_catalogo')}</Link></p>
        )}
        <Input label={t('internos.titulo')} required value={f.title} onChange={set('title')} />
        <Textarea label={t('internos.descripcion')} required value={f.description} onChange={set('description')} rows={4} />
        <div className="int-rejilla">
          <Input label={t('internos.presupuesto_estimado')} type="number" min={0} step="any" value={f.estimated_budget} onChange={set('estimated_budget')} />
          <Input label={t('internos.inicio_deseado')} type="date" value={f.wanted_start} onChange={set('wanted_start')} />
          <Input label={t('internos.fin_deseado')} type="date" value={f.wanted_end} onChange={set('wanted_end')} />
        </div>
        <div className="u-actions-8">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button icon={<Send size={14} />} onClick={() => enviar.mutate()} loading={enviar.isPending}
            disabled={!f.title.trim() || !f.description.trim() || enviar.isPending}>{t('internos.enviar')}</Button>
        </div>
      </div>
    </Modal>
  )
}

export function Peticiones({ cid }: { cid: string }) {
  const t = useT()
  const estado = useEstado()
  const [pidiendo, setPidiendo] = useState(false)
  const { data, isLoading } = useQuery({ queryKey: clave(cid, 'requests'), queryFn: () => portalInternoApi.peticiones(cid) })
  return (
    <div className="u-stack-8">
      <div className="int-barra">
        <span className="int-nota">{data ? t(`internos.peticiones_origen_${data.source}`) : ''}</span>
        <Button size="sm" icon={<Plus size={14} />} onClick={() => setPidiendo(true)}>{t('internos.pedir')}</Button>
      </div>
      {isLoading ? <Spinner /> : !data?.items.length ? <p className="u-text2-sm">{t('internos.sin_peticiones')}</p> : (
        <div className="u-stack-8">
          {data.items.map(p => (
            <Card key={p.id} className="int-item">
              <div className="u-min0">
                <span className="int-item__titulo">{p.title}</span>
                <div className="int-sub">{fmtDate(p.created_at)}</div>
              </div>
              <StatusBadge kind="neutral" caps={false}>{estado(p.status)}</StatusBadge>
            </Card>
          ))}
        </div>
      )}
      {pidiendo && <Pedir cid={cid} onClose={() => setPidiendo(false)} />}
    </div>
  )
}

export function AdopcionYBeneficios({ cid }: { cid: string }) {
  const t = useT()
  const { data: adopcion = [], isLoading } = useQuery({ queryKey: clave(cid, 'adoption'), queryFn: () => portalInternoApi.adopcion(cid) })
  const { data: beneficios = [] } = useQuery({ queryKey: clave(cid, 'benefits'), queryFn: () => portalInternoApi.beneficios(cid) })
  return (
    <div className="u-stack-8">
      <Card className="int-bloque">
        <div className="int-bloque__titulo">{t('internos.adopcion')}</div>
        {isLoading ? <Spinner /> : <ListaDeAdopcion items={adopcion} />}
      </Card>
      <Card className="int-bloque">
        <div className="int-bloque__titulo">{t('internos.beneficios')}</div>
        <ListaDeBeneficios items={beneficios} conProyecto />
      </Card>
    </div>
  )
}

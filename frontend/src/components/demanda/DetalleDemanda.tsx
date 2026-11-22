/**
 * Expediente de demanda del operador (22-11-2026): cabecera con estado y plazo,
 * línea de fases con sus pasos, botones de decisión (según `steps[].decisions` y
 * `can_decide`) con justificación obligatoria donde toca, y las pestañas.
 * Toda decisión queda en el historial inmutable del servidor con su actor.
 */
import { useState, type ReactNode } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { ArrowLeft, Check, CornerUpLeft, FastForward, HelpCircle, Pause, SkipForward, Users, X, Send } from 'lucide-react'
import { Button, Modal, Select, Spinner, Tabs, Textarea } from '../ui'
import { demandaApi, type DetalleDeDemanda, type FaseDeExpediente, type PasoDeExpediente } from '../../services/api/demanda'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { useConfirm } from '../../context/ConfirmContext'
import { extractErr, fmtDateTime } from '../../utils/helpers'
import { decisionConDestino, justificacionObligatoria } from './utilDemanda'
import { EstadoDeDemandaBadge, SlaBadge, etiquetaDe } from './comunes'
import {
  ComentariosDemanda, ComiteDemanda, DocumentosDemanda, EjecutarDemanda, FichaDemanda, HistorialDemanda, VersionesDemanda, useRefrescarDemanda,
} from './PestanasDemanda'
import './demanda.css'

const ICONO_DECISION: Record<string, ReactNode> = {
  approve: <Check size={12} />, complete: <Check size={12} />, reject: <X size={12} />, return: <CornerUpLeft size={12} />,
  request_info: <HelpCircle size={12} />, skip: <SkipForward size={12} />, fast_track: <FastForward size={12} />,
  to_committee: <Users size={12} />, hold: <Pause size={12} />,
}
const VARIANTE: Record<string, 'primary' | 'secondary' | 'danger' | 'subtle'> = {
  approve: 'primary', complete: 'primary', fast_track: 'primary', to_committee: 'secondary', reject: 'danger',
}

interface DecisionEnCurso { fase: FaseDeExpediente; paso: PasoDeExpediente; decision: string }

/** Fases a las que se puede devolver: las que el servidor indique o, si no, las anteriores a la actual. */
function destinosDeDevolucion(d: DetalleDeDemanda, fase: FaseDeExpediente): FaseDeExpediente[] {
  const indice = d.phases.findIndex(f => f.key === fase.key)
  const previas = d.phases.filter((_, i) => i < indice)
  if (fase.return_targets?.length) return d.phases.filter(f => fase.return_targets?.includes(f.key))
  return previas
}

function DialogoDeDecision({ d, en, onClose }: { d: DetalleDeDemanda; en: DecisionEnCurso; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const refrescar = useRefrescarDemanda(d.id)
  const destinos = decisionConDestino(en.decision) ? destinosDeDevolucion(d, en.fase) : []
  const [destino, setDestino] = useState(destinos[destinos.length - 1]?.key ?? '')
  const [justificacion, setJustificacion] = useState('')
  const obligatoria = justificacionObligatoria(en.decision, d.committee.required)
  const esBypass = en.decision === 'fast_track' && d.committee.required
  const falta = (obligatoria && !justificacion.trim()) || (decisionConDestino(en.decision) && !destino)
  const decidir = useMutation({
    mutationFn: () => demandaApi.decidir(d.id, {
      step_key: en.paso.key, decision: en.decision,
      target_phase: decisionConDestino(en.decision) ? destino : undefined,
      justification: justificacion.trim() || undefined,
    }),
    onSuccess: () => { toast.success(t('demanda.decision_registrada')); refrescar(); onClose() },
    onError: (e: unknown) => toast.error(extractErr(e, t('demanda.error'))),
  })
  return (
    <Modal open onClose={onClose} title={`${etiquetaDe(t, 'dec', en.decision)} · ${en.paso.name}`} subtitle={en.fase.name}>
      <div className="u-stack-16">
        {esBypass && <div className="dem-aviso">{t('demanda.aviso_bypass')}{d.committee.reasons.length > 0 && `: ${d.committee.reasons.join('; ')}`}</div>}
        {decisionConDestino(en.decision) && (
          destinos.length === 0 ? <p className="plan-muted">{t('demanda.sin_destinos')}</p> : (
            <Select label={t('demanda.devolver_a')} placeholder={false} value={destino} onChange={e => setDestino(e.target.value)} options={destinos.map(f => ({ value: f.key, label: f.name }))} />
          )
        )}
        <Textarea label={t('demanda.justificacion')} required={obligatoria} rows={4} value={justificacion}
          hint={obligatoria ? t('demanda.justificacion_obligatoria') : t('demanda.justificacion_opcional')}
          onChange={e => setJustificacion(e.target.value)} />
        <div className="dem-acciones">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button variant={en.decision === 'reject' ? 'danger' : 'primary'} loading={decidir.isPending} disabled={falta} onClick={() => decidir.mutate()}>{etiquetaDe(t, 'dec', en.decision)}</Button>
        </div>
      </div>
    </Modal>
  )
}

function LineaDeFases({ d, onDecidir }: { d: DetalleDeDemanda; onDecidir: (e: DecisionEnCurso) => void }) {
  const t = useAppT()
  return (
    <div className="dem-lineafases" role="list" aria-label={t('demanda.fases')}>
      {d.phases.map(f => (
        <div key={f.key} role="listitem" className={`dem-fase dem-fase--${f.status}`}>
          <div className="dem-fase__nombre">{f.name}</div>
          <div className="dem-fase__meta">{etiquetaDe(t, 'fase_estado', f.status)} · {etiquetaDe(t, 'kind', f.kind)}</div>
          {f.sla_due_at && f.status === 'current' && <div className="dem-fase__meta">{t('demanda.vence')}: {fmtDateTime(f.sla_due_at)}</div>}
          {f.steps.map(p => (
            <div key={p.key} className="dem-paso">
              <div><strong>{p.name}</strong> · {etiquetaDe(t, 'paso_estado', p.status)}</div>
              {p.assignee_label && <div className="dem-fase__meta">{p.assignee_label}</div>}
              {p.votes != null && typeof p.votes === 'object' && Object.keys(p.votes as object).length > 0 && (
                <div className="dem-fase__meta">{t('demanda.votos')}: {Object.entries(p.votes as Record<string, unknown>).map(([k, v]) => `${k} ${String(v)}`).join(', ')}</div>
              )}
              {p.votes != null && typeof p.votes !== 'object' && <div className="dem-fase__meta">{t('demanda.votos')}: {String(p.votes)}</div>}
              {p.decided_by_name && <div className="dem-fase__meta">{p.decided_by_name}{p.decided_at ? ` · ${fmtDateTime(p.decided_at)}` : ''}</div>}
              {p.note && <div className="dem-justificacion">{p.note}</div>}
              {p.can_decide && p.decisions.length > 0 && (
                <div className="dem-paso__acciones">
                  {p.decisions.map(dec => (
                    <Button key={dec} size="xs" variant={VARIANTE[dec] ?? 'subtle'} icon={ICONO_DECISION[dec]} onClick={() => onDecidir({ fase: f, paso: p, decision: dec })}>
                      {etiquetaDe(t, 'dec', dec)}
                    </Button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

const PESTANAS = ['ficha', 'historial', 'versiones', 'documentos', 'comentarios', 'comite', 'ejecutar'] as const
type Pestana = typeof PESTANAS[number]

export default function DetalleDemanda({ id, onVolver }: { id: string; onVolver: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const refrescar = useRefrescarDemanda(id)
  const { pedirTexto } = useConfirm()
  const [pestana, setPestana] = useState<Pestana>('ficha')
  const [decision, setDecision] = useState<DecisionEnCurso | null>(null)
  const { data: d, isLoading, isError } = useQuery({ queryKey: ['demand-detail', id], queryFn: () => demandaApi.detalle(id) })
  const enviar = useMutation({
    mutationFn: () => demandaApi.enviar(id),
    onSuccess: () => { toast.success(t('demanda.enviada')); refrescar() },
    onError: (e: unknown) => toast.error(extractErr(e, t('demanda.error'))),
  })
  const retirar = useMutation({
    mutationFn: (reason: string) => demandaApi.retirar(id, reason),
    onSuccess: () => { toast.success(t('demanda.retirada')); refrescar() },
    onError: (e: unknown) => toast.error(extractErr(e, t('demanda.error'))),
  })
  if (isLoading) return <Spinner />
  if (isError || !d) return <div className="u-stack-16"><Button variant="subtle" icon={<ArrowLeft size={13} />} onClick={onVolver}>{t('demanda.volver')}</Button><p className="plan-muted">{t('demanda.error')}</p></div>
  const items = PESTANAS.map(p => ({
    id: p, label: t(`demanda.tab_${p}`),
    count: p === 'documentos' ? d.documents.length : p === 'comentarios' ? d.comments.length : p === 'historial' ? d.transitions.length : undefined,
  }))
  return (
    <div className="u-stack-16">
      <div><Button variant="subtle" icon={<ArrowLeft size={13} />} onClick={onVolver}>{t('demanda.volver')}</Button></div>
      <div className="ds-card u-stack-12">
        <div className="dem-cabecera">
          <div className="dem-cabecera__titulo">
            <span className="u-mono dem-codigo">{d.code} · {d.type_name}</span>
            <h2 className="plan-card__titulo">{d.title}</h2>
            <span className="plan-muted">
              {d.project_name ? `${t('demanda.proyecto')}: ${d.project_name}` : t('demanda.iniciativa_independiente')}
              {d.requester_name ? ` · ${t('demanda.solicitante')}: ${d.requester_name}` : ''} · {etiquetaDe(t, 'origen', d.origin)}
            </span>
          </div>
          <div className="dem-fila">
            <EstadoDeDemandaBadge estado={d.status} />
            <SlaBadge estado={d.sla_state} />
            {d.current_phase_name && <span className="plan-muted">{t('demanda.fase_actual')}: {d.current_phase_name}</span>}
            {d.sla_due_at && <span className="plan-muted">{t('demanda.vence')}: {fmtDateTime(d.sla_due_at)}</span>}
            {d.actions.can_withdraw && <Button variant="danger" size="sm" onClick={async () => { const m = await pedirTexto({ message: t('demanda.motivo_retirada') }); if (m !== null) retirar.mutate(m.trim()) }}>{t('demanda.retirar')}</Button>}
            {d.actions.can_submit && <Button icon={<Send size={13} />} loading={enviar.isPending} onClick={() => enviar.mutate()}>{t('demanda.enviar')}</Button>}
          </div>
        </div>
        {d.status === 'pending_info' && <div className="dem-aviso">{t('demanda.pendiente_info_aviso')}</div>}
        {d.metrics && (d.metrics.effective_hours != null || d.metrics.paused_hours != null) && (
          <span className="plan-muted">
            {t('demanda.horas_efectivas')}: {d.metrics.effective_hours ?? '—'} · {t('demanda.horas_pausadas')}: {d.metrics.paused_hours ?? '—'}
          </span>
        )}
        <LineaDeFases d={d} onDecidir={setDecision} />
      </div>
      <Tabs items={items} active={pestana} onChange={id2 => setPestana(id2 as Pestana)} ariaLabel={t('demanda.pestanas')} />
      <div className="ds-card">
        {pestana === 'ficha' && <FichaDemanda d={d} />}
        {pestana === 'historial' && <HistorialDemanda d={d} />}
        {pestana === 'versiones' && <VersionesDemanda d={d} />}
        {pestana === 'documentos' && <DocumentosDemanda d={d} />}
        {pestana === 'comentarios' && <ComentariosDemanda d={d} />}
        {pestana === 'comite' && <ComiteDemanda d={d} />}
        {pestana === 'ejecutar' && <EjecutarDemanda d={d} />}
      </div>
      {decision && <DialogoDeDecision d={d} en={decision} onClose={() => setDecision(null)} />}
    </div>
  )
}

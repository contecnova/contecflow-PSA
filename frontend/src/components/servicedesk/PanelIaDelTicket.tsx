/**
 * PanelIaDelTicket — la IA del ticket en pantalla (mejoras de mercado 16-11-2026).
 *
 * Predicción de incumplimiento del SLA, triaje con aceptación, candidatos a
 * duplicado con fusión, análisis y explicación de la IA, y asignación
 * inteligente con los candidatos y su puntuación. Todo usa rutas del backend
 * que ya existían sin pantalla, más `duplicate-candidates`.
 */
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Brain, GitMerge, ShieldAlert, Sparkles, UserCheck, Wand2 } from 'lucide-react'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { confirmar } from '../../context/ConfirmContext'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { Button, Spinner, StatusBadge, Section } from '../ui'
import type { StatusBadgeKind } from '../ui/StatusBadge'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { iaDelTicketApi } from '../../services/api/serviceDeskMercado'
import type { AnalisisIa, ExplicacionIa, TriajeIa } from '../../services/api/serviceDeskMercado'
import './sdMercado.css'

const pct = (v: number | null | undefined) => (v == null ? '—' : `${Math.round(v * 100)} %`)
const NIVEL: Record<string, StatusBadgeKind> = { critical: 'danger', high: 'danger', medium: 'warning', low: 'success', breached: 'danger' }

/** Barra de 0 a 1 para una puntuación; el ancho va en una variable CSS. */
function Barra({ valor, etiqueta }: { valor: number; etiqueta: string }) {
  const v = Math.max(0, Math.min(1, valor || 0))
  return (
    <div className="sdm-bar" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(v * 100)} aria-label={etiqueta}>
      <span className="sdm-bar__fill" style={{ '--sdm-w': `${v * 100}%` } as CSSProperties} />
    </div>
  )
}

export default function PanelIaDelTicket({ ticketId, tieneGrupo, onCambio }: { ticketId: string; tieneGrupo: boolean; onCambio: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [triaje, setTriaje] = useState<TriajeIa | null>(null)
  const [analisis, setAnalisis] = useState<AnalisisIa | null>(null)
  const [explicacion, setExplicacion] = useState<ExplicacionIa | null>(null)
  const err = (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))

  const sla = useQuery({ queryKey: ['sdm-sla-pred', ticketId], queryFn: () => iaDelTicketApi.prediccionSla(ticketId), retry: false })
  const dup = useQuery({ queryKey: ['sdm-dups', ticketId], queryFn: () => iaDelTicketApi.duplicados(ticketId), retry: false })
  const cand = useQuery({ queryKey: ['sdm-cands', ticketId], queryFn: () => iaDelTicketApi.candidatos(ticketId), enabled: tieneGrupo, retry: false })

  const refrescar = () => { onCambio(); qc.invalidateQueries({ queryKey: ['sdm-cands', ticketId] }); qc.invalidateQueries({ queryKey: ['sdm-dups', ticketId] }) }

  const pedirTriaje = useMutation({ mutationFn: () => iaDelTicketApi.triaje(ticketId), onSuccess: setTriaje, onError: err })
  const decidirTriaje = useMutation({
    mutationFn: (ok: boolean) => iaDelTicketApi.aceptarTriaje(ticketId, ok),
    onSuccess: (_d, ok) => { setTriaje(null); toast.success(t(ok ? 'sd_mercado.triaje_aplicado' : 'sd_mercado.triaje_descartado')); if (ok) refrescar() },
    onError: err,
  })
  const analizar = useMutation({ mutationFn: () => iaDelTicketApi.analizar(ticketId), onSuccess: setAnalisis, onError: err })
  const explicar = useMutation({ mutationFn: () => iaDelTicketApi.explicar(ticketId), onSuccess: setExplicacion, onError: err })
  const fusionar = useMutation({
    mutationFn: (destino: string) => iaDelTicketApi.fusionar(destino, ticketId, t('sd_mercado.fusion_motivo')),
    onSuccess: () => { toast.success(t('sd_mercado.fusionado')); refrescar() },
    onError: err,
  })
  const asignar = useMutation({
    mutationFn: (userId: string | null) => userId ? iaDelTicketApi.asignarA(ticketId, userId) : iaDelTicketApi.asignarMejor(ticketId),
    onSuccess: () => { toast.success(t('sd_mercado.asignado')); refrescar() },
    onError: err,
  })

  const s = sla.data
  const nivel = s ? (s.already_breached ? 'breached' : s.risk_level) : null

  return (
    <Section title={<span className="u-row-center-6"><Brain size={16} aria-hidden="true" />{t('sd_mercado.ia_titulo')}</span>} className="u-mb-20">
      <div className="u-stack-12">
        {/* Predicción de incumplimiento del SLA */}
        <div className="ds-card sdm-card">
          <div className="sdm-card__head"><ShieldAlert size={14} aria-hidden="true" />{t('sd_mercado.sla_prediccion')}</div>
          {sla.isLoading ? <Spinner size={16} /> : sla.isError || !s ? (
            <div className="u-text3-xs">{t('sd_mercado.sla_sin_datos')}</div>
          ) : (
            <div className="u-stack-6">
              <div className="u-wrap-8">
                <StatusBadge kind={NIVEL[nivel || ''] || 'neutral'}>{etiquetaCodigo(t, 'sd_mercado.nivel_riesgo', nivel)}</StatusBadge>
                <span className="u-text2-xs">{t('sd_mercado.sla_probabilidad', { p: pct(s.breach_probability) })}</span>
                {s.minutes_until_resolution_due != null && <span className="u-text2-xs">{t('sd_mercado.sla_quedan', { m: s.minutes_until_resolution_due })}</span>}
                {s.predicted_resolution_min != null && <span className="u-text2-xs">{t('sd_mercado.sla_prevision', { m: s.predicted_resolution_min })}</span>}
              </div>
              <Barra valor={s.breach_probability} etiqueta={t('sd_mercado.sla_prediccion')} />
              {s.recommendation && <div className="u-text2-xs">{s.recommendation}</div>}
            </div>
          )}
        </div>

        {/* Triaje */}
        <div className="ds-card sdm-card">
          <div className="sdm-card__head"><Wand2 size={14} aria-hidden="true" />{t('sd_mercado.triaje')}
            <span className="ds-toolbar__spacer" />
            <Button size="xs" variant="secondary" onClick={() => pedirTriaje.mutate()} loading={pedirTriaje.isPending}>{t('sd_mercado.triaje_pedir')}</Button>
          </div>
          {triaje && (
            <div className="u-stack-6">
              <div className="u-grid2-10">
                <div><div className="ds-eyebrow">{t('sd_mercado.categoria')}</div><div className="u-text1-sm-600">{triaje.suggested_category}</div></div>
                <div><div className="ds-eyebrow">{t('sd_mercado.prioridad')}</div><div className="u-text1-sm-600">{etiquetaCodigo(t, 'sd_mercado.prioridad_triaje', triaje.suggested_priority)}</div></div>
                <div><div className="ds-eyebrow">{t('sd_mercado.agente')}</div><div className="u-text1-sm-600">{triaje.suggested_agent || '—'}</div></div>
                <div><div className="ds-eyebrow">{t('sd_mercado.confianza')}</div><div className="u-text1-sm-600">{triaje.confidence_pct == null ? '—' : `${triaje.confidence_pct} %`}</div></div>
              </div>
              {triaje.reasoning && <div className="u-text2-xs">{triaje.reasoning}</div>}
              <div className="u-actions-8">
                <Button size="sm" variant="secondary" onClick={() => decidirTriaje.mutate(false)} disabled={decidirTriaje.isPending}>{t('sd_mercado.descartar')}</Button>
                <Button size="sm" onClick={() => decidirTriaje.mutate(true)} loading={decidirTriaje.isPending}>{t('sd_mercado.aplicar')}</Button>
              </div>
            </div>
          )}
        </div>

        {/* Duplicados */}
        <div className="ds-card sdm-card">
          <div className="sdm-card__head"><GitMerge size={14} aria-hidden="true" />{t('sd_mercado.duplicados')}</div>
          {dup.isLoading ? <Spinner size={16} /> : !dup.data || dup.data.candidates.length === 0 ? (
            <div className="u-text3-xs">{t('sd_mercado.sin_duplicados')}</div>
          ) : (
            <ul className="sdm-list">
              {dup.data.candidates.map(c => (
                <li key={c.id} className="sdm-list__item">
                  <div className="u-flex1-min0">
                    <div className="u-text1-sm-600 sdm-wrap"><span className="u-mono">{c.number}</span> {c.title}</div>
                    <div className="u-wrap-6 u-text3-xs">
                      <span>{t('sd_mercado.parecido', { p: pct(c.score) })}</span>
                      {c.reasons.map(r => <StatusBadge key={r} kind="info" caps={false}>{etiquetaCodigo(t, 'sd_mercado.motivo_dup', r)}</StatusBadge>)}
                      <StatusBadge caps={false}>{etiquetaCodigo(t, 'estado', c.status)}</StatusBadge>
                    </div>
                  </div>
                  <Button size="xs" variant="secondary" loading={fusionar.isPending && fusionar.variables === c.id}
                    onClick={async () => {
                      if (await confirmar({ message: t('sd_mercado.fusion_confirmar', { n: c.number }), danger: true })) fusionar.mutate(c.id)
                    }}>{t('sd_mercado.fusionar_en', { n: c.number })}</Button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Análisis y explicación */}
        <div className="ds-card sdm-card">
          <div className="sdm-card__head"><Sparkles size={14} aria-hidden="true" />{t('sd_mercado.analisis')}
            <span className="ds-toolbar__spacer" />
            <Button size="xs" variant="secondary" onClick={() => analizar.mutate()} loading={analizar.isPending}>{t('sd_mercado.analizar')}</Button>
            <Button size="xs" variant="ghost" onClick={() => explicar.mutate()} loading={explicar.isPending}>{t('sd_mercado.explicar')}</Button>
          </div>
          {analisis && (
            <div className="u-stack-6">
              <div className="u-wrap-8"><span className="u-text2-xs">{t('sd_mercado.confianza')}: {pct(analisis.confidence)}</span>
                <StatusBadge caps={false}>{etiquetaCodigo(t, 'sd_mercado.accion_ia', analisis.action_taken)}</StatusBadge></div>
              {analisis.analysis && <div className="u-text2-xs sdm-pre">{analisis.analysis}</div>}
              {analisis.suggestion && <div className="sdm-suggestion sdm-pre">{analisis.suggestion}</div>}
              {analisis.kb_sources?.length > 0 && (
                <div className="u-wrap-6">{analisis.kb_sources.map(k => <StatusBadge key={k.id} kind="accent" caps={false}>{k.number ? `${k.number} · ` : ''}{k.title}</StatusBadge>)}</div>
              )}
            </div>
          )}
          {explicacion && (
            <div className="u-stack-6 u-mb-10">
              <div className="ds-eyebrow">{t('sd_mercado.explicacion')}</div>
              <div className="u-text2-xs">{t('sd_mercado.autorresolucion', {
                p: pct(Number(explicacion.auto_resolution?.score ?? 0)), u: pct(explicacion.confidence_trace?.auto_resolution_threshold),
              })}</div>
              <Barra valor={Number(explicacion.auto_resolution?.score ?? 0)} etiqueta={t('sd_mercado.explicacion')} />
            </div>
          )}
        </div>

        {/* Asignación inteligente */}
        <div className="ds-card sdm-card">
          <div className="sdm-card__head"><UserCheck size={14} aria-hidden="true" />{t('sd_mercado.asignacion')}
            <span className="ds-toolbar__spacer" />
            {tieneGrupo && <Button size="xs" onClick={() => asignar.mutate(null)} loading={asignar.isPending && asignar.variables === null}>{t('sd_mercado.asignar_mejor')}</Button>}
          </div>
          {!tieneGrupo ? <div className="u-text3-xs">{t('sd_mercado.sin_grupo')}</div>
            : cand.isLoading ? <Spinner size={16} />
            : !cand.data || cand.data.candidates.length === 0 ? <div className="u-text3-xs">{t('sd_mercado.sin_candidatos')}</div>
            : (
              <ul className="sdm-list">
                {cand.data.candidates.map(c => (
                  <li key={c.user_id} className="sdm-list__item">
                    <div className="u-flex1-min0 u-stack-6">
                      <div className="u-row-center-8"><span className="u-text1-sm-600">{c.user_name}</span>
                        <StatusBadge kind={c.available ? 'success' : 'neutral'} caps={false}>{t(c.available ? 'sd_mercado.disponible' : 'sd_mercado.no_disponible')}</StatusBadge>
                        <span className="u-text2-xs">{pct(c.composite_score)}</span></div>
                      <div className="sdm-components">
                        {(Object.keys(c.components) as (keyof typeof c.components)[]).map(k => (
                          <div key={k} className="sdm-component"><span className="u-text3-2xs">{t(`sd_mercado.comp_${k}`)}</span><Barra valor={c.components[k]} etiqueta={t(`sd_mercado.comp_${k}`)} /></div>
                        ))}
                      </div>
                    </div>
                    <Button size="xs" variant="secondary" onClick={() => asignar.mutate(c.user_id)} loading={asignar.isPending && asignar.variables === c.user_id}>{t('sd_mercado.asignar')}</Button>
                  </li>
                ))}
              </ul>
            )}
        </div>
      </div>
    </Section>
  )
}

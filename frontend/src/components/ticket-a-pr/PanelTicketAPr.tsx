/**
 * «Del ticket al PR» en el ticket o la tarea (migración 203, docs/integraciones/TICKET_A_PR.md).
 *
 * - Botón «Proponer arreglo con IA»: solo si el módulo está activo en la empresa,
 *   el proyecto tiene un repositorio permitido y la persona tiene `ticket_pr.lanzar`.
 * - Diálogo: repositorio, rama base e instrucción (propuesta a partir del ticket con
 *   los datos personales ocultos; editable, se vuelve a ocultar al lanzar).
 * - Ejecuciones: estado, plan para aprobar o rechazar (`ticket_pr.aprobar_plan`),
 *   bloqueos y fallos con su motivo, PR, cambio y CAB, tests, horas del agente y
 *   coste de IA, log del contenedor y cancelación. Se refresca sola mientras corre.
 *
 * Sin el módulo y sin ejecuciones anteriores no pinta nada.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bot, ExternalLink, FileText, GitPullRequest, RefreshCw, X } from 'lucide-react'
import { Button, Card, Input, Modal, Select, Spinner, StatusBadge, Textarea } from '../ui'
import type { StatusBadgeKind } from '../ui'
import MarkdownText from '../ui/MarkdownText'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { confirmar } from '../../context/ConfirmContext'
import { extractErr, fmtDateTime, fmtNumber } from '../../utils/helpers'
import { CLAVES_TICKET_A_PR, ESTADOS_EN_MARCHA, ticketAPrApi } from '../../services/api/ticketAPr'
import type { EjecucionTicketAPr, EstadoDeEjecucion, OrigenTicketAPr, PanelTicketAPr as Panel } from '../../services/api/ticketAPr'

const REFRESCO_MS = 5000

const TONO: Record<EstadoDeEjecucion, StatusBadgeKind> = {
  queued_plan: 'info', planning: 'info', awaiting_approval: 'warning', rejected: 'neutral', queued_build: 'info',
  building: 'info', blocked: 'danger', failed: 'danger', cancelled: 'neutral', awaiting_cab: 'warning',
  cab_approved: 'success', cab_rejected: 'danger', merged: 'success', closed: 'neutral',
}

function Lanzar({ tipo, id, panel, onClose }: { tipo: OrigenTicketAPr; id: string; panel: Panel; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [repoId, setRepoId] = useState(panel.repos[0]?.id ?? '')
  const repo = panel.repos.find(r => r.id === repoId)
  const [rama, setRama] = useState(repo?.default_branch ?? 'main')
  const [instruccion, setInstruccion] = useState('')
  const proponer = useMutation({
    mutationFn: () => ticketAPrApi.proponer(tipo, id, { repo_id: repoId, base_branch: rama }),
    onSuccess: r => setInstruccion(r.instruction),
    onError: e => toast.error(extractErr(e)),
  })
  const lanzar = useMutation({
    mutationFn: () => ticketAPrApi.lanzar(tipo, id, { repo_id: repoId, base_branch: rama, instruction: instruccion }),
    onSuccess: () => {
      toast.success(t('ticket_pr.lanzado'))
      void qc.invalidateQueries({ queryKey: CLAVES_TICKET_A_PR.panel(tipo, id) })
      onClose()
    },
    onError: e => toast.error(extractErr(e)),
  })
  return (
    <Modal open onClose={onClose} title={t('ticket_pr.proponer')} size="lg">
      <div className="u-stack-12">
        <p className="u-text2-sm">{t('ticket_pr.proponer_intro')}</p>
        <div className="u-wrap-8">
          <Select label={t('ticket_pr.repositorio')} value={repoId} placeholder={false}
            onChange={e => {
              setRepoId(e.target.value)
              setRama(panel.repos.find(r => r.id === e.target.value)?.default_branch ?? 'main')
              setInstruccion('')
            }}
            options={panel.repos.map(r => ({ value: r.id, label: `${r.provider === 'github' ? 'GitHub' : 'GitLab'} · ${r.repo_full_name}` }))} />
          <Input label={t('ticket_pr.rama_base')} value={rama} maxLength={200} onChange={e => setRama(e.target.value)} />
        </div>
        <div className="u-actions-8">
          <Button variant="secondary" onClick={() => proponer.mutate()} loading={proponer.isPending} disabled={!repoId}>
            {instruccion ? t('ticket_pr.regenerar') : t('ticket_pr.generar_instruccion')}
          </Button>
        </div>
        {instruccion && (
          <Textarea label={t('ticket_pr.instruccion')} value={instruccion} rows={12} maxLength={12000}
            onChange={e => setInstruccion(e.target.value)} hint={t('ticket_pr.instruccion_ayuda')} />
        )}
        <p className="u-text2-xs">{t('ticket_pr.aviso_aislamiento')}</p>
        <div className="u-actions-8">
          <Button variant="secondary" onClick={onClose}>{t('ticket_pr.cerrar')}</Button>
          <Button icon={<Bot size={14} />} onClick={() => lanzar.mutate()} loading={lanzar.isPending}
            disabled={!repoId || !instruccion.trim()}>{t('ticket_pr.lanzar_plan')}</Button>
        </div>
      </div>
    </Modal>
  )
}

function Log({ runId, onClose }: { runId: string; onClose: () => void }) {
  const t = useAppT()
  const { data, isLoading } = useQuery({ queryKey: CLAVES_TICKET_A_PR.log(runId), queryFn: () => ticketAPrApi.log(runId) })
  return (
    <Modal open onClose={onClose} title={t('ticket_pr.log')} size="xl" avisarSinGuardar={false}>
      {isLoading ? <Spinner /> : <pre className="ds-codigo ds-codigo--bloque">{data?.log || t('ticket_pr.log_vacio')}</pre>}
    </Modal>
  )
}

function Ejecucion({ run, tipo, id }: { run: EjecucionTicketAPr; tipo: OrigenTicketAPr; id: string }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [nota, setNota] = useState('')
  const [verLog, setVerLog] = useState(false)
  const refrescar = () => void qc.invalidateQueries({ queryKey: CLAVES_TICKET_A_PR.panel(tipo, id) })
  const decidir = useMutation({
    mutationFn: (aprobar: boolean) => ticketAPrApi.decidir(run.id, { approve: aprobar, note: nota.trim() || undefined }),
    onSuccess: (_r, aprobar) => { toast.success(aprobar ? t('ticket_pr.plan_aprobado') : t('ticket_pr.plan_rechazado')); refrescar() },
    onError: e => toast.error(extractErr(e)),
  })
  const cancelar = useMutation({
    mutationFn: () => ticketAPrApi.cancelar(run.id),
    onSuccess: () => { toast.success(t('ticket_pr.cancelada')); refrescar() },
    onError: e => toast.error(extractErr(e)),
  })
  const sincronizar = useMutation({
    mutationFn: () => ticketAPrApi.sincronizar(run.id),
    onSuccess: refrescar,
    onError: e => toast.error(extractErr(e)),
  })
  const enMarcha = ESTADOS_EN_MARCHA.includes(run.status)
  return (
    <div className="u-stack-8">
      <div className="u-row-center-8 u-wrap-8">
        <StatusBadge kind={TONO[run.status]} dot={enMarcha}>{t(`ticket_pr.estado_${run.status}`)}</StatusBadge>
        <span className="u-text2-sm"><code className="u-mono">{run.repo_full_name}</code> · {run.base_branch}</span>
        <span className="u-text3-xs">{run.created_at ? fmtDateTime(run.created_at) : ''}{run.launched_by_name ? ` · ${run.launched_by_name}` : ''}</span>
        {enMarcha && <Spinner size={14} />}
      </div>
      {run.status_code && (
        <p className="u-text2-sm" role="status">{t(`err_srv.${run.status_code}`, run.status_params)}</p>
      )}
      {run.plan_text && (
        <details open={run.status === 'awaiting_approval'}>
          <summary className="u-text2-sm">{t('ticket_pr.plan')}</summary>
          <MarkdownText text={run.plan_text} />
          {run.plan_files.length > 0 && (
            <p className="u-text3-xs">{t('ticket_pr.ficheros_del_plan')}: {run.plan_files.slice(0, 20).join(', ')}</p>
          )}
        </details>
      )}
      {run.can_decide && (
        <div className="u-stack-6">
          <Input label={t('ticket_pr.nota')} value={nota} maxLength={1000} onChange={e => setNota(e.target.value)} />
          <div className="u-actions-8">
            <Button variant="secondary" onClick={() => decidir.mutate(false)} loading={decidir.isPending}>{t('ticket_pr.rechazar_plan')}</Button>
            <Button onClick={async () => { if (await confirmar({ message: t('ticket_pr.aprobar_confirmar') })) decidir.mutate(true) }}
              loading={decidir.isPending}>{t('ticket_pr.aprobar_plan')}</Button>
          </div>
        </div>
      )}
      {run.plan_decided_by_name && (
        <p className="u-text3-xs">{t('ticket_pr.decidido_por', { nombre: run.plan_decided_by_name, fecha: run.plan_decided_at ? fmtDateTime(run.plan_decided_at) : '' })}
          {run.plan_decision_note ? ` — ${run.plan_decision_note}` : ''}</p>
      )}
      {run.diff_summary && (
        <p className="u-text2-sm">{t('ticket_pr.diff', { n: run.diff_summary.files.length, mas: run.diff_summary.added, menos: run.diff_summary.removed })}
          {run.tests_ran ? ` · ${run.tests_passed ? t('ticket_pr.tests_ok') : t('ticket_pr.tests_fallan')}` : ''}</p>
      )}
      {run.reasoning_summary && (
        <details>
          <summary className="u-text2-sm">{t('ticket_pr.razonamiento')}</summary>
          <MarkdownText text={run.reasoning_summary} />
        </details>
      )}
      <div className="u-row-center-8 u-wrap-8">
        {run.pr_url && (
          <a className="u-row-center-8" href={run.pr_url} target="_blank" rel="noopener noreferrer">
            <GitPullRequest size={14} aria-hidden />{t('ticket_pr.pr', { n: run.pr_number ?? '' })}<ExternalLink size={12} aria-hidden />
          </a>
        )}
        {run.pr_status_state && <StatusBadge kind={run.pr_status_state === 'success' ? 'success' : run.pr_status_state === 'failure' ? 'danger' : 'warning'}>
          {t(`ticket_pr.merge_${run.pr_status_state}`)}</StatusBadge>}
        {run.change && <span className="u-text2-sm">{t('ticket_pr.cambio', { numero: run.change.number, estado: t(`ticket_pr.cambio_${run.change.status}`) })}</span>}
      </div>
      <p className="u-text3-xs">{t('ticket_pr.consumo', { horas: fmtNumber(run.agent_hours, 2), coste: fmtNumber(run.cost_usd, 4), tokens: fmtNumber(run.tokens_in + run.tokens_out, 0) })}
        {run.model ? ` · ${run.model}` : ''}</p>
      <div className="u-actions-8">
        <Button size="sm" variant="secondary" icon={<FileText size={14} />} onClick={() => setVerLog(true)}>{t('ticket_pr.ver_log')}</Button>
        {(run.status === 'awaiting_cab' || run.status === 'cab_approved') && (
          <Button size="sm" variant="secondary" icon={<RefreshCw size={14} />} onClick={() => sincronizar.mutate()}
            loading={sincronizar.isPending}>{t('ticket_pr.sincronizar')}</Button>
        )}
        {run.can_cancel && (
          <Button size="sm" variant="secondary" icon={<X size={14} />} loading={cancelar.isPending}
            onClick={async () => { if (await confirmar({ message: t('ticket_pr.cancelar_confirmar'), danger: true })) cancelar.mutate() }}>
            {t('ticket_pr.cancelar')}</Button>
        )}
      </div>
      {verLog && <Log runId={run.id} onClose={() => setVerLog(false)} />}
    </div>
  )
}

export default function PanelTicketAPr({ tipo, id }: { tipo: OrigenTicketAPr; id: string }): JSX.Element | null {
  const t = useAppT()
  const [abierto, setAbierto] = useState(false)
  const { data: panel } = useQuery({
    queryKey: CLAVES_TICKET_A_PR.panel(tipo, id),
    queryFn: () => ticketAPrApi.panel(tipo, id),
    // Mientras una ejecución corre, se refresca sola.
    refetchInterval: q => (q.state.data?.runs.some(r => ESTADOS_EN_MARCHA.includes(r.status)) ? REFRESCO_MS : false),
    retry: false,
  })
  if (!panel || (!panel.enabled && panel.runs.length === 0)) return null
  return (
    <Card>
      <div className="u-row-center-8">
        <h3 className="u-row-center-8 u-flex1"><GitPullRequest size={16} aria-hidden />{t('ticket_pr.titulo')}</h3>
        {panel.can_launch && (
          <Button size="sm" icon={<Bot size={14} />} onClick={() => setAbierto(true)}>{t('ticket_pr.proponer')}</Button>
        )}
      </div>
      {panel.enabled && !panel.can_launch && panel.reason && panel.reason !== 'ticket_pr_sin_capacidad' && (
        <p className="u-text3-xs">{t(`err_srv.${panel.reason}`)}</p>
      )}
      <div className="u-stack-14">
        {panel.runs.length === 0
          ? <p className="u-text2-sm">{t('ticket_pr.sin_ejecuciones')}</p>
          : panel.runs.map(r => <Ejecucion key={r.id} run={r} tipo={tipo} id={id} />)}
      </div>
      {abierto && <Lanzar tipo={tipo} id={id} panel={panel} onClose={() => setAbierto(false)} />}
    </Card>
  )
}

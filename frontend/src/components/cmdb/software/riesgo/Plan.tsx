/**
 * Pestaña Riesgo → Plan de reducción (22-11-2026): de X (actual) a Y
 * (objetivo), pasos ordenados por impacto con sus acciones de remediación, el
 * ticket/cambio/tarea si ya existe (o crearlo, como en el detalle del hallazgo)
 * y la lista completa de eventos de riesgo del ámbito.
 *
 * Diseño: docs/CMDB_SOFTWARE_Y_VULNERABILIDADES.md §11.5.
 */
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, ListOrdered, Target } from 'lucide-react'
import { useAppT } from '../../../../i18n/AppLangContext'
import { useToast } from '../../../../context/ToastContext'
import { useAuth } from '../../../../context/AuthContext'
import { fmtDateTime } from '../../../../utils/helpers'
import { cmdbSoftwareApi } from '../../../../services/api/cmdbSoftware'
import { cmdbRiesgoApi } from '../../../../services/api/cmdbRiesgo'
import type { Ambito, PasoDelPlan } from '../../../../services/api/cmdbRiesgo'
import { Button, EmptyState, Input, Modal, Section, Select, Spinner, StatusBadge, TablaSimple } from '../../../ui'
import Pagination from '../../../ui/Pagination'
import { SeveridadBadge, VersionTexto, useErr, useEtiquetaSw } from '../comun'
import DetalleDeHallazgo from '../DetalleDeHallazgo'
import { redondeo, useEtiquetaSwr } from './comunRiesgo'

const TAMANO = 25
const TIPOS_DE_EVENTO = ['finding', 'drift', 'violation', 'eol', 'exploit']

export default function Plan({ ambito }: { ambito: Ambito }) {
  const t = useAppT()
  const [objetivo, setObjetivo] = useState('')
  const [aplicado, setAplicado] = useState<number | undefined>(undefined)
  const [abierto, setAbierto] = useState<string | null>(null)
  const [verEventos, setVerEventos] = useState(false)
  const plan = useQuery({
    queryKey: ['swr', 'plan', ambito.scope_type, ambito.scope_id ?? '', aplicado ?? ''],
    queryFn: () => cmdbRiesgoApi.plan(ambito, aplicado),
  })
  const p = plan.data
  const valido = objetivo.trim() !== '' && Number(objetivo) >= 0 && Number(objetivo) <= 100
  return (
    <div className="u-stack-20">
      <Section title={t('swr.plan')} subtitle={t('swr.plan_desc')}
        actions={<Button size="sm" variant="secondary" icon={<ListOrdered size={14} />} onClick={() => setVerEventos(true)}>{t('swr.ver_eventos')}</Button>}>
        <div className="u-stack-12">
          <form className="sdm-form" onSubmit={ev => { ev.preventDefault(); if (valido) setAplicado(Number(objetivo)) }}>
            <Input label={t('swr.objetivo')} type="number" min={0} max={100} value={objetivo} placeholder={p ? String(Math.round(p.target)) : ''}
              hint={t('swr.objetivo_ayuda')} onChange={ev => setObjetivo(ev.target.value)} />
            <div><Button type="submit" icon={<Target size={14} />} disabled={!valido} loading={plan.isFetching}>{t('swr.calcular_plan')}</Button></div>
          </form>
          {plan.isLoading ? <Spinner /> : p && <>
            <div className="sw-aviso">
              {t('swr.plan_de_a', { de: Math.round(p.current), a: Math.round(p.target) })}{' '}
              {p.reached ? t('swr.plan_alcanzado', { n: p.steps.length, final: Math.round(p.final_score) }) : t('swr.plan_no_alcanzado', { n: p.steps.length, final: Math.round(p.final_score) })}
            </div>
            {p.steps.length === 0 ? <EmptyState icon={<CheckCircle2 size={28} />} title={t('swr.plan_vacio')} /> : (
              <ol className="swr-pasos">
                {p.steps.map((s, i) => <PasoDePlan key={s.finding.id} n={i + 1} paso={s} onAbrir={setAbierto} />)}
              </ol>
            )}
          </>}
        </div>
      </Section>
      {abierto && <DetalleDeHallazgo id={abierto} onClose={() => setAbierto(null)} />}
      {verEventos && <EventosModal ambito={ambito} onClose={() => setVerEventos(false)} onAbrir={setAbierto} />}
    </div>
  )
}

function PasoDePlan({ n, paso, onAbrir }: { n: number; paso: PasoDelPlan; onAbrir: (id: string) => void }) {
  const t = useAppT()
  const e = useEtiquetaSw()
  const toast = useToast()
  const qc = useQueryClient()
  const err = useErr()
  const { puede } = useAuth()
  const h = paso.finding
  const r = paso.remediation
  const remediar = useMutation({
    mutationFn: (type: 'ticket' | 'change') => cmdbSoftwareApi.remediar(h.id, { type }),
    onSuccess: x => { toast.success(t('sw.remediacion_creada', { tipo: e('remedio', x.type) })); qc.invalidateQueries({ queryKey: ['swr', 'plan'] }); qc.invalidateQueries({ queryKey: ['sw'] }) },
    onError: err,
  })
  const accion = (a: PasoDelPlan['actions'][number]) => {
    const params = Object.fromEntries(Object.entries(a.params ?? {}).map(([k, v]) => [k, Array.isArray(v) ? (v as unknown[]).join(', ') : v]))
    return t(`swr.accion_${a.code}`, params as Record<string, string | number>)
  }
  return (
    <li className="swr-paso">
      <span className="swr-paso__n" aria-hidden="true">{n}</span>
      <div className="u-flex1-min0 u-stack-6">
        <div className="u-wrap-8">
          <Button variant="link" className="sw-enlace u-mono" onClick={() => onAbrir(h.id)}>{h.vuln_id ?? '—'}</Button>
          <SeveridadBadge s={h.severity} />
          {h.kev && <StatusBadge kind="danger" caps={false} title={t('sw.kev_ayuda')}>KEV</StatusBadge>}
          <span className="u-text3-xs">{h.product_name ?? '—'} <VersionTexto v={h.affected_version} />{h.ci_name ? ` · ${h.ci_name}` : ''}</span>
        </div>
        {paso.actions.length > 0 && <ul className="swr-paso__acciones">{paso.actions.map((a, k) => <li key={k}>{accion(a)}</li>)}</ul>}
        <div className="u-wrap-8">
          {r.ticket_id && <Link to={`/service-desk?ticket=${r.ticket_id}`} className="sw-enlace">{t('swr.ver_ticket')}</Link>}
          {r.change_id && <Link to="/changes" className="sw-enlace">{t('swr.ver_cambio')}</Link>}
          {r.problem_id && <StatusBadge kind="success" caps={false}>{t('sw.ya_tiene', { tipo: e('remedio', 'problem') })}</StatusBadge>}
          {r.task_id && <Link to="/tasks" className="sw-enlace">{t('swr.ver_tarea')}</Link>}
          {puede('software.gestionar') && !r.ticket_id && <Button size="xs" variant="secondary" loading={remediar.isPending && remediar.variables === 'ticket'} disabled={remediar.isPending} onClick={() => remediar.mutate('ticket')}>{t('sw.crear_remedio', { tipo: e('remedio', 'ticket') })}</Button>}
          {puede('software.gestionar') && !r.change_id && <Button size="xs" variant="ghost" loading={remediar.isPending && remediar.variables === 'change'} disabled={remediar.isPending} onClick={() => remediar.mutate('change')}>{t('sw.crear_remedio', { tipo: e('remedio', 'change') })}</Button>}
        </div>
      </div>
      <div className="u-stack-6 u-text3-xs">
        <span className="swr-impacto u-text1-sm-600">{t('swr.impacto_puntos', { n: redondeo(paso.impact, 1) })}</span>
        <span className="swr-impacto">{t('swr.indice_tras', { n: redondeo(paso.score_after, 1) })}</span>
      </div>
    </li>
  )
}

function EventosModal({ ambito, onClose, onAbrir }: { ambito: Ambito; onClose: () => void; onAbrir: (id: string) => void }) {
  const t = useAppT()
  const e = useEtiquetaSwr()
  const [tipo, setTipo] = useState('')
  const [pagina, setPagina] = useState(1)
  const { data, isLoading } = useQuery({
    queryKey: ['swr', 'eventos', ambito.scope_type, ambito.scope_id ?? '', tipo, pagina],
    queryFn: () => cmdbRiesgoApi.eventos(ambito, { kind: tipo || undefined, page: pagina, page_size: TAMANO }),
  })
  const items = data?.items ?? []
  const total = data?.total ?? 0
  return (
    <Modal open size="xl" onClose={onClose} title={t('swr.eventos')} subtitle={t('swr.eventos_desc')}>
      <div className="u-stack-12">
        <label className="sdm-field sw-campo-estrecho"><span>{t('swr.tipo_evento')}</span>
          <Select suelto placeholder={false} value={tipo} onChange={ev => { setTipo(ev.target.value); setPagina(1) }}>
            <option value="">{t('swr.todos')}</option>
            {TIPOS_DE_EVENTO.map(k => <option key={k} value={k}>{e('evento', k)}</option>)}
          </Select></label>
        {isLoading ? <Spinner /> : items.length === 0 ? <EmptyState title={t('swr.sin_eventos')} /> : (
          <TablaSimple etiqueta={t('swr.eventos')} densidad="compacta">
            <thead><tr>
              <th className="sw-num">{t('swr.col_puntos')}</th><th>{t('swr.tipo_evento')}</th><th>{t('swr.col_titulo')}</th>
              <th>{t('sw.severidad')}</th><th>{t('sw.software')}</th><th>{t('sw.maquina')}</th><th>{t('swr.col_fecha')}</th>
            </tr></thead>
            <tbody>{items.map(x => (
              <tr key={`${x.kind}-${x.id}`}>
                <td className="sw-num u-600">{redondeo(x.points, 2)}</td>
                <td>{e('evento', x.kind)}</td>
                <td>
                  {x.finding_id ? <Button variant="link" className="sw-enlace" onClick={() => onAbrir(x.finding_id as string)}>{x.title ?? '—'}</Button> : (x.title ?? '—')}
                  {x.detail && <div className="u-text3-xs sw-recorte" title={x.detail}>{x.detail}</div>}
                </td>
                <td>{x.severity ? <SeveridadBadge s={x.severity} /> : '—'}</td>
                <td>{x.product_name ?? '—'}</td>
                <td>{x.ci_name ?? '—'}</td>
                <td className="u-text3-xs">{x.occurred_at ? fmtDateTime(x.occurred_at) : '—'}</td>
              </tr>
            ))}</tbody>
          </TablaSimple>
        )}
        <Pagination page={pagina} totalPages={Math.max(1, Math.ceil(total / TAMANO))} onChange={setPagina} total={total} pageSize={TAMANO} />
      </div>
    </Modal>
  )
}

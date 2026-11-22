/**
 * Detalle de un hallazgo de vulnerabilidad (19-11-2026): el aviso (CVE, CVSS,
 * EPSS, KEV), su impacto (software, máquinas, servicios, clientes y
 * responsables), el triaje (cambiar de estado según las transiciones del
 * servidor), la remediación (ticket, problema, cambio o tarea) y la excepción
 * (motivo, controles compensatorios y caducidad; la decide quien tiene
 * `software.aprobar` o la bandeja de aprobaciones).
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ExternalLink, ShieldAlert } from 'lucide-react'
import { useAppT } from '../../../i18n/AppLangContext'
import { useToast } from '../../../context/ToastContext'
import { useAuth } from '../../../context/AuthContext'
import { confirmar } from '../../../context/ConfirmContext'
import { fmtDate, fmtDateTime } from '../../../utils/helpers'
import { projectsApi } from '../../../services/api'
import { cmdbSoftwareApi } from '../../../services/api/cmdbSoftware'
import type { EstadoHallazgo } from '../../../services/api/cmdbSoftware'
import { Button, DateInput, EmptyState, Modal, Section, Select, Spinner, StatusBadge, Tabs, Textarea } from '../../ui'
import { ESTADO_KIND, EXCEPCION_KIND, ListaKv, PosibleBadge, Semaforo, SeveridadBadge, TRANSICIONES, VersionTexto, useErr, useEtiquetaSw } from './comun'

type Remedio = 'ticket' | 'problem' | 'change' | 'task'
const REMEDIOS: Remedio[] = ['ticket', 'problem', 'change', 'task']

const enDias = (n: number) => { const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10) }

export default function DetalleDeHallazgo({ id, onClose }: { id: string; onClose: () => void }) {
  const t = useAppT()
  const e = useEtiquetaSw()
  const toast = useToast()
  const qc = useQueryClient()
  const err = useErr()
  const { puede } = useAuth()
  const gestiona = puede('software.gestionar')
  const [pestana, setPestana] = useState('resumen')
  const [notas, setNotas] = useState<string | null>(null)
  const [remedio, setRemedio] = useState<Remedio>('ticket')
  const [proyecto, setProyecto] = useState('')
  const [plan, setPlan] = useState('')
  const [vuelta, setVuelta] = useState('')
  const [motivo, setMotivo] = useState('')
  const [controles, setControles] = useState('')
  const [caduca, setCaduca] = useState(enDias(30))
  const { data: h, isLoading } = useQuery({ queryKey: ['sw', 'hallazgo', id], queryFn: () => cmdbSoftwareApi.hallazgo(id) })
  const proyectos = useQuery({
    queryKey: ['projects', 'selector-sw'],
    queryFn: () => projectsApi.list({ status: 'active' }).then(r => r.data),
    enabled: remedio === 'task' && pestana === 'remediar',
  })
  const refrescar = () => qc.invalidateQueries({ queryKey: ['sw'] })
  const cambiar = useMutation({
    mutationFn: (d: { status?: EstadoHallazgo; notes?: string | null }) => cmdbSoftwareApi.cambiarHallazgo(id, d),
    onSuccess: () => { toast.success(t('sw.guardado')); setNotas(null); refrescar() },
    onError: err,
  })
  const remediar = useMutation({
    mutationFn: () => cmdbSoftwareApi.remediar(id, {
      type: remedio, project_id: remedio === 'task' && proyecto ? proyecto : undefined,
      implementation_plan: remedio === 'change' && plan.trim() ? plan.trim() : undefined,
      rollback_plan: remedio === 'change' && vuelta.trim() ? vuelta.trim() : undefined,
    }),
    onSuccess: r => { toast.success(t('sw.remediacion_creada', { tipo: e('remedio', r.type) })); refrescar() },
    onError: err,
  })
  const excepcion = useMutation({
    mutationFn: () => cmdbSoftwareApi.pedirExcepcion(id, { reason: motivo.trim(), compensating_controls: controles.trim() || undefined, expires_at: caduca }),
    onSuccess: () => { toast.success(t('sw.excepcion_pedida')); setMotivo(''); setControles(''); refrescar() },
    onError: err,
  })

  const cerrado = h ? !TRANSICIONES[h.status] : false
  const vinculos: [Remedio, string | null][] = h ? [['ticket', h.ticket_id], ['problem', h.problem_id], ['change', h.change_id], ['task', h.task_id]] : []
  const imp = h?.impact

  return (
    <Modal open size="xl" onClose={onClose} title={h ? <span className="u-mono">{h.vuln_id}</span> : t('sw.hallazgo')}
      subtitle={h ? `${h.product_name ?? ''} ${h.affected_version ?? t('sw.version_desconocida')}${h.ci_name ? ` · ${h.ci_name}` : ''}` : undefined}>
      {isLoading || !h ? <Spinner /> : (
        <div className="u-stack-14">
          <div className="u-wrap-8">
            <SeveridadBadge s={h.severity} />
            <PosibleBadge posible={h.possible} />
            <StatusBadge kind={ESTADO_KIND[h.status] ?? 'neutral'} caps={false}>{e('estado', h.status)}</StatusBadge>
            {h.kev && <StatusBadge kind="danger" caps={false} title={t('sw.kev_ayuda')}>KEV</StatusBadge>}
            <Semaforo h={h} />
            {h.priority_score != null && <StatusBadge kind="accent" caps={false}>{t('sw.prioridad')}: {Math.round(h.priority_score)}</StatusBadge>}
          </div>
          <Tabs ariaLabel={t('sw.hallazgo')} active={pestana} onChange={setPestana} items={[
            { id: 'resumen', label: t('sw.aviso') },
            { id: 'impacto', label: t('sw.impacto'), count: imp?.summary.machines },
            ...(gestiona ? [{ id: 'triaje', label: t('sw.triaje') }, { id: 'remediar', label: t('sw.remediar') }, { id: 'excepcion', label: t('sw.excepcion') }] : []),
          ]} />

          {pestana === 'resumen' && (
            <div className="u-stack-12">
              {h.possible && <div className="sw-aviso">{t('sw.posible_ayuda')}</div>}
              {h.title && <div className="u-text1-sm-600">{h.title}</div>}
              {h.vulnerability.description && <div className="u-text2-sm sdm-pre">{h.vulnerability.description}</div>}
              <ListaKv filas={[
                ['CVSS', h.cvss_score != null ? `${h.cvss_score.toFixed(1)}${h.vulnerability.cvss_version ? ` (v${h.vulnerability.cvss_version})` : ''}` : '—'],
                [t('sw.vector'), h.vulnerability.cvss_vector ? <span className="u-mono">{h.vulnerability.cvss_vector}</span> : '—'],
                ['EPSS', h.epss_score != null ? `${(h.epss_score * 100).toFixed(2)} %${h.vulnerability.epss_percentile != null ? ` · ${t('sw.percentil', { n: Math.round(h.vulnerability.epss_percentile * 100) })}` : ''}` : '—'],
                ['KEV', h.kev ? t('sw.kev_desde', { fecha: fmtDate(h.vulnerability.kev_added) }) : t('sw.no')],
                [t('sw.alias'), h.aliases.length ? <span className="u-mono">{h.aliases.join(', ')}</span> : '—'],
                ['CWE', h.vulnerability.cwe.length ? <span className="u-mono">{h.vulnerability.cwe.join(', ')}</span> : '—'],
                [t('sw.publicado'), fmtDate(h.vulnerability.published_at)],
                [t('sw.fuente'), e('fuente', h.vulnerability.source)],
                [t('sw.version_afectada'), <VersionTexto key="v" v={h.affected_version} />],
                [t('sw.corregido_en'), <span key="f" className="u-mono">{h.fixed_version ?? '—'}</span>],
                [t('sw.dentro_de_col'), h.parent_product_name ? `${h.parent_product_name} ${h.parent_version ?? ''}` : '—'],
                [t('sw.entorno'), h.environment ? `${e('entorno', h.environment)}${h.exposure ? ` · ${e('expo', h.exposure)}` : ''}` : '—'],
                [t('sw.detectado'), fmtDateTime(h.first_seen_at)],
                [t('sw.plazo'), fmtDate(h.sla_due_at)],
              ]} />
              {h.vulnerability.references.length > 0 && (
                <div className="u-stack-6">
                  <div className="ds-eyebrow">{t('sw.referencias')}</div>
                  <ul className="sw-referencias">{h.vulnerability.references.slice(0, 15).map(r => (
                    <li key={r}><a href={r} target="_blank" rel="noopener noreferrer" className="sdm-wrap">{r} <ExternalLink size={12} /></a></li>
                  ))}</ul>
                </div>
              )}
              {h.exceptions.length > 0 && (
                <div className="u-stack-6">
                  <div className="ds-eyebrow">{t('sw.excepciones')}</div>
                  {h.exceptions.map(x => (
                    <div key={x.id} className="u-text3-xs"><StatusBadge kind={EXCEPCION_KIND[x.status] ?? 'neutral'} caps={false}>{e('exc', x.status)}</StatusBadge> {x.reason} · {t('sw.caduca')}: {fmtDate(x.expires_at)}</div>
                  ))}
                </div>
              )}
            </div>
          )}

          {pestana === 'impacto' && imp && (
            <div className="u-stack-12">
              <div className="ds-grid-stats">
                {(['software', 'instances', 'machines', 'services', 'clients', 'findings'] as const).map(k => (
                  <div key={k} className="ds-card sdm-card"><div className="u-text3-xs">{t(`sw.imp_${k}`)}</div><div className="u-text1-sm-600">{imp.summary[k]}</div></div>
                ))}
              </div>
              <div className="sdm-grid">
                <BloqueLista titulo={t('sw.imp_software')} filas={imp.software.map(s => `${s.product_name} ${s.version}`)} />
                <BloqueLista titulo={t('sw.imp_machines')} filas={imp.machines.map(m => `${m.name}${m.ip_address ? ` (${m.ip_address})` : ''}${m.environment ? ` · ${e('entorno', m.environment)}` : ''}`)} />
                <BloqueLista titulo={t('sw.imp_services')} filas={imp.services.map(s => s.name)} />
                <BloqueLista titulo={t('sw.imp_clients')} filas={imp.clients.map(c => c.name)} />
                <BloqueLista titulo={t('sw.imp_owners')} filas={imp.owners.map(o => o.name)} />
              </div>
            </div>
          )}

          {pestana === 'triaje' && (
            <div className="u-stack-12">
              {cerrado ? <div className="u-text3-xs">{t('sw.hallazgo_cerrado')}</div> : (
                <div className="u-stack-6">
                  <div className="ds-eyebrow">{t('sw.pasar_a')}</div>
                  <div className="u-wrap-8">
                    {(TRANSICIONES[h.status] ?? []).map(s => (
                      <Button key={s} size="sm" variant={s === 'false_positive' ? 'ghost' : 'secondary'} disabled={cambiar.isPending}
                        onClick={async () => { if (s !== 'false_positive' || await confirmar({ message: t('sw.falso_positivo_confirmar') })) cambiar.mutate({ status: s as EstadoHallazgo }) }}>
                        {e('estado', s)}
                      </Button>
                    ))}
                  </div>
                </div>
              )}
              <Textarea label={t('sw.notas')} rows={4} value={notas ?? h.notes ?? ''} onChange={ev => setNotas(ev.target.value)} />
              <div className="u-actions-10">
                <Button disabled={notas === null} loading={cambiar.isPending} onClick={() => cambiar.mutate({ notes: notas?.trim() || null })}>{t('sw.guardar_notas')}</Button>
              </div>
            </div>
          )}

          {pestana === 'remediar' && (
            <div className="u-stack-12">
              <div className="u-wrap-8">
                {vinculos.filter(([, v]) => v).map(([k]) => <StatusBadge key={k} kind="success" caps={false}>{t('sw.ya_tiene', { tipo: e('remedio', k) })}</StatusBadge>)}
              </div>
              {cerrado ? <div className="u-text3-xs">{t('sw.hallazgo_cerrado')}</div> : <>
                <div className="sdm-form">
                  <label className="sdm-field"><span>{t('sw.remediar_con')}</span>
                    <Select suelto placeholder={false} value={remedio} onChange={ev => setRemedio(ev.target.value as Remedio)}>
                      {REMEDIOS.map(r => <option key={r} value={r}>{e('remedio', r)}</option>)}
                    </Select></label>
                  {remedio === 'task' && (
                    <label className="sdm-field"><span>{t('sw.proyecto')}</span>
                      <Select suelto placeholder={false} value={proyecto} onChange={ev => setProyecto(ev.target.value)}>
                        <option value="">{t('sw.proyecto_del_software')}</option>
                        {(proyectos.data ?? []).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                      </Select></label>
                  )}
                </div>
                {remedio === 'change' && (
                  <div className="sdm-form">
                    <Textarea label={t('sw.plan_implantacion')} rows={3} value={plan} onChange={ev => setPlan(ev.target.value)} />
                    <Textarea label={t('sw.plan_vuelta_atras')} rows={3} value={vuelta} onChange={ev => setVuelta(ev.target.value)} />
                  </div>
                )}
                <div className="u-text3-xs">{t(`sw.remedio_ayuda_${remedio}`)}</div>
                <div className="u-actions-10">
                  <Button loading={remediar.isPending} onClick={() => remediar.mutate()}>{t('sw.crear_remedio', { tipo: e('remedio', remedio) })}</Button>
                </div>
              </>}
            </div>
          )}

          {pestana === 'excepcion' && (
            <div className="u-stack-12">
              {cerrado ? <div className="u-text3-xs">{t('sw.hallazgo_cerrado')}</div> : <>
                <div className="u-text3-xs">{t('sw.excepcion_ayuda')}</div>
                <Textarea label={t('sw.motivo')} rows={3} value={motivo} onChange={ev => setMotivo(ev.target.value)} />
                <Textarea label={t('sw.controles')} rows={3} value={controles} onChange={ev => setControles(ev.target.value)} />
                <label className="sdm-field"><span>{t('sw.caduca')}</span>
                  <DateInput className="ds-input" value={caduca} min={enDias(1)} onChange={ev => setCaduca(ev.target.value)} /></label>
                <div className="u-actions-10">
                  <Button icon={<ShieldAlert size={14} />} disabled={motivo.trim().length < 10 || !caduca} loading={excepcion.isPending} onClick={() => excepcion.mutate()}>{t('sw.pedir_excepcion')}</Button>
                </div>
              </>}
            </div>
          )}
        </div>
      )}
    </Modal>
  )
}

function BloqueLista({ titulo, filas }: { titulo: string; filas: string[] }) {
  const t = useAppT()
  return (
    <Section title={titulo} eyebrow>
      {filas.length === 0 ? <EmptyState title={t('sw.nada')} /> : (
        <ul className="sw-lista-simple">{filas.slice(0, 50).map((f, i) => <li key={i}>{f}</li>)}</ul>
      )}
    </Section>
  )
}

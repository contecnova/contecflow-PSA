/**
 * PlanificacionDeRecursosPage — /resources/planning (rev. 173).
 *
 * Las rutas de /resources que no tenían pantalla, más la carga real:
 *   · Disponibilidad: carga por persona y semana desde las tareas, con el
 *     calendario de cada persona (GET /planning/workload).
 *   · Skills: el equipo de un proyecto con sus skills y, por skill, quién está
 *     más libre (/resources/{id}/skill-gaps y /resources/available-by-skill).
 *   · Alertas: sobrecarga, infrautilización… con «visto» (/resources/alerts).
 *   · Histórico: utilización y facturable por semana (/resources/utilization-history).
 *   · Nivelación: la del proyecto elegido (GET/POST /planning/projects/{id}/leveling).
 *
 * 16-11-2026: pasada de diseño. Vacíos con EmptyState, icono lucide y
 * descripción (antes solo título); selectores y campo de semanas con
 * .ds-input (antes 12 px con fondo propio); "skills" en castellano.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BellRing, CalendarRange, FolderOpen, History, Scale, Sparkles } from 'lucide-react'
import Page from '../components/ui/Page'
import { Button, EmptyState, Spinner, StatusBadge, Tabs } from '../components/ui'
import { projectsApi, recursosApi, skillsApi, usersApi } from '../services/api'
import VistasDeTrabajo from '../components/planificador/VistasDeTrabajo'
import PanelDeNivelacion from '../components/planificador/PanelDeNivelacion'
import { useAppT } from '../i18n/AppLangContext'
import { useToast } from '../context/ToastContext'
import { extractErr, fmtDateTime } from '../utils/helpers'
import '../components/planificador/planificador.css'
import './PlanificacionDeRecursosPage.css'

const SEVERIDAD: Record<string, 'danger' | 'warning' | 'info'> = { critical: 'danger', warning: 'warning', info: 'info' }

export default function PlanificacionDeRecursosPage() {
  const t = useAppT()
  const [tab, setTab] = useState('availability')
  const [proyecto, setProyecto] = useState('')
  const { data: proyectos = [] } = useQuery({ queryKey: ['projects'], queryFn: () => projectsApi.list({}).then(r => r.data) })

  const selector = (
    <select className="ds-input plr-campo" aria-label={t('planificador.elige_proyecto')} value={proyecto} onChange={e => setProyecto(e.target.value)}>
      <option value="">{t('planificador.elige_proyecto')}</option>
      {proyectos.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
    </select>
  )

  return (
    <Page icon={<CalendarRange size={18} />} title={t('planificador.recursos_titulo')} subtitle={t('planificador.recursos_subtitulo')}>
      <Tabs
        items={[
          { id: 'availability', label: t('planificador.recursos_disponibilidad'), icon: <CalendarRange size={13} /> },
          { id: 'skills', label: t('planificador.recursos_skills'), icon: <Sparkles size={13} /> },
          { id: 'alerts', label: t('planificador.recursos_alertas'), icon: <BellRing size={13} /> },
          { id: 'history', label: t('planificador.recursos_historico'), icon: <History size={13} /> },
          { id: 'leveling', label: t('planificador.pestana_nivelacion'), icon: <Scale size={13} /> },
        ]}
        active={tab} onChange={setTab} ariaLabel={t('planificador.recursos_titulo')}
      />
      {tab === 'availability' && <VistasDeTrabajo vista="workload" projectId={proyecto || undefined} onVista={() => undefined} />}
      {tab === 'skills' && <PanelDeSkills selector={selector} proyecto={proyecto} />}
      {tab === 'alerts' && <PanelDeAlertas />}
      {tab === 'history' && <PanelHistorico />}
      {tab === 'leveling' && (
        <div className="plan-stack">
          <div className="plan-row">{selector}</div>
          {proyecto ? <PanelDeNivelacion projectId={proyecto} /> : (
            <EmptyState icon={<FolderOpen size={28} />} title={t('planificador.elige_proyecto')}
              description={t('planificador.elige_proyecto_nivelacion')} />
          )}
        </div>
      )}
    </Page>
  )
}

function PanelDeSkills({ selector, proyecto }: { selector: JSX.Element; proyecto: string }) {
  const t = useAppT()
  const [skill, setSkill] = useState('')
  const { data: catalogo = [] } = useQuery({ queryKey: ['skills-catalog'], queryFn: () => skillsApi.catalog().then(r => r.data) })
  const { data: personas = [] } = useQuery({ queryKey: ['users', 'directory'], queryFn: () => usersApi.directory().then(r => r.data) })
  const nombre = Object.fromEntries(personas.map(p => [p.id, p.full_name]))
  const { data: equipo = [], isLoading } = useQuery({
    queryKey: ['skills-proyecto', proyecto], queryFn: () => recursosApi.skillsDelProyecto(proyecto), enabled: !!proyecto,
  })
  const { data: libres = [], isFetching } = useQuery({
    queryKey: ['skills-libres', skill], queryFn: () => recursosApi.personasPorSkill(skill), enabled: !!skill,
  })
  const enEquipo = new Set(equipo.flatMap(e => e.skills.map(s => s.skill_id)))
  const faltan = catalogo.filter(c => !enEquipo.has(c.id))
  return (
    <div className="plan-stack">
      <div className="plan-row">{selector}</div>
      {proyecto && (isLoading ? <Spinner /> : (
        <div className="plan-card">
          <h3 className="plan-card__titulo">{t('planificador.skills_del_equipo')}</h3>
          {equipo.length === 0 ? <p className="plan-muted">{t('planificador.sin_skills_equipo')}</p> : (
            <ul className="plan-lista">
              {equipo.map(e => (
                <li key={e.user_id}>
                  <span>{nombre[e.user_id] ?? e.user_id}</span>
                  <span className="plan-row">{e.skills.map(s => <span key={s.skill_id} className="plan-chip">{s.skill_name} · {t(`planificador.nivel_${s.level}`)}</span>)}</span>
                </li>
              ))}
            </ul>
          )}
          {faltan.length > 0 && (
            <>
              <h3 className="plan-card__titulo">{t('planificador.skills_que_faltan')}</h3>
              <div className="plan-row">{faltan.map(c => <button key={c.id} type="button" className="plan-chip" onClick={() => setSkill(c.id)}>{c.name}</button>)}</div>
            </>
          )}
        </div>
      ))}
      <div className="plan-card plan-stack">
        <label className="plan-row plan-muted">
          {t('planificador.buscar_por_skill')}
          <select className="ds-input plr-campo" value={skill} onChange={e => setSkill(e.target.value)}>
            <option value="">{t('planificador.elige_skill')}</option>
            {catalogo.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
        {skill && (isFetching ? <Spinner /> : libres.length === 0 ? <p className="plan-muted">{t('planificador.nadie_con_skill')}</p> : (
          <table className="plan-tabla">
            <thead><tr><th>{t('planificador.col_persona')}</th><th>{t('planificador.col_nivel')}</th><th className="plan-num">{t('planificador.col_libres')}</th><th className="plan-num">{t('planificador.col_carga')}</th></tr></thead>
            <tbody>
              {libres.map(p => (
                <tr key={p.user_id}><td>{p.user_name}</td><td>{t(`planificador.nivel_${p.level}`)}</td>
                  <td className="plan-num">{Math.round(p.available_hours)} h</td><td className="plan-num">{Math.round(p.load_pct)} %</td></tr>
              ))}
            </tbody>
          </table>
        ))}
      </div>
    </div>
  )
}

function PanelDeAlertas() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [vistas, setVistas] = useState(false)
  const { data: alertas = [], isLoading } = useQuery({ queryKey: ['resource-alerts', vistas], queryFn: () => recursosApi.alertas(vistas) })
  const reconocer = useMutation({
    mutationFn: (id: string) => recursosApi.reconocerAlerta(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['resource-alerts'] }),
    onError: e => toast.error(extractErr(e, t('planificador.error_generico'))),
  })
  return (
    <div className="plan-stack">
      <label className="plan-row plan-muted"><input type="checkbox" checked={vistas} onChange={e => setVistas(e.target.checked)} />{t('planificador.ver_alertas_vistas')}</label>
      {isLoading ? <Spinner /> : alertas.length === 0 ? <EmptyState icon={<BellRing size={28} />} title={t('planificador.sin_alertas')} description={t('planificador.sin_alertas_desc')} /> : (
        <div className="plan-card plan-tabla-scroll">
          <table className="plan-tabla">
            <thead><tr><th>{t('planificador.col_persona')}</th><th>{t('planificador.col_alerta')}</th><th>{t('planificador.col_severidad')}</th><th>{t('planificador.col_fecha')}</th><th /></tr></thead>
            <tbody>
              {alertas.map(a => (
                <tr key={a.id}>
                  <td>{a.user_name}</td>
                  <td>{t(`planificador.alerta_${a.alert_type}`)}</td>
                  <td><StatusBadge kind={SEVERIDAD[a.severity] ?? 'neutral'}>{t(`planificador.severidad_${a.severity}`)}</StatusBadge></td>
                  <td>{fmtDateTime(a.triggered_at)}</td>
                  <td>{!a.acknowledged_at && <Button size="xs" variant="subtle" onClick={() => reconocer.mutate(a.id)}>{t('planificador.marcar_vista')}</Button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function PanelHistorico() {
  const t = useAppT()
  const [semanas, setSemanas] = useState(12)
  const { data = [], isLoading } = useQuery({ queryKey: ['utilizacion', semanas], queryFn: () => recursosApi.historico(semanas) })
  return (
    <div className="plan-stack">
      <label className="plan-row plan-muted">{t('planificador.semanas_atras')}
        <input type="number" min={1} max={52} className="ds-input plr-campo plr-campo--num" value={semanas} onChange={e => setSemanas(Math.min(52, Math.max(1, Number(e.target.value) || 1)))} />
      </label>
      {isLoading ? <Spinner /> : data.length === 0 ? <EmptyState icon={<History size={28} />} title={t('planificador.sin_historico')} description={t('planificador.sin_historico_desc')} /> : (
        <div className="plan-card plan-tabla-scroll">
          <table className="plan-tabla">
            <thead><tr><th>{t('planificador.col_persona')}</th><th>{t('planificador.col_semana')}</th><th className="plan-num">{t('planificador.col_planificadas')}</th><th className="plan-num">{t('planificador.col_reales')}</th><th className="plan-num">{t('planificador.col_utilizacion')}</th><th className="plan-num">{t('planificador.col_facturable')}</th></tr></thead>
            <tbody>
              {data.map(u => (
                <tr key={`${u.user_id}-${u.week_iso}`}>
                  <td>{u.user_name}</td><td>{u.week_iso}</td>
                  <td className="plan-num">{u.planned_hours}</td><td className="plan-num">{u.actual_hours}</td>
                  <td className="plan-num">{u.utilization_pct == null ? '—' : `${Math.round(u.utilization_pct)} %`}</td>
                  <td className="plan-num">{u.billable_pct == null ? '—' : `${Math.round(u.billable_pct)} %`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

import { useState, useId } from 'react'
import { useQuery } from '@tanstack/react-query'
import { integrationsApi, jiraApi, projectsApi, unwrapList } from '../services/api'
import { Button, Card, Page, Section } from '../components/ui'
import { Download, FileSpreadsheet, FolderKanban, Link2, RefreshCw } from 'lucide-react'
import { downloadBlob } from '../utils/helpers'
import { useAuth } from '../context/AuthContext'
import { useAppT } from '../i18n/AppLangContext'
import DateInput from '../components/ui/DateInput'
import { useToast } from '../context/ToastContext'
import './ExportsPage.css'

interface ProjectListItem {
  id: number | string
  name?: string
  code?: string
  status?: string
}

interface ImputExportForm {
  date_from: string
  date_to: string
  include_costs: boolean
  format: 'xlsx' | 'csv'
}

interface ProjectsExportForm {
  include_costs: boolean
  format: 'xlsx' | 'csv'
}

type LoadingState = Record<'imput' | 'proj', boolean>

function extractErrorMessage(error: unknown): string {
  if (typeof error !== 'object' || error == null) return ''
  const raw = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
  if (Array.isArray(raw)) {
    return raw
      .map((entry) => (typeof entry === 'object' && entry && 'msg' in entry ? String((entry as { msg: unknown }).msg) : String(entry)))
      .join(', ')
  }
  return raw ? String(raw) : ''
}

export default function ExportsPage(): JSX.Element {
  const idCampo = useId()
  const t = useAppT()
  const { hasRole } = useAuth()
  const today = new Date().toISOString().split('T')[0]
  const firstDay = new Date(new Date().getFullYear(), new Date().getMonth(), 1).toISOString().split('T')[0]

  const [imputForm, setImputForm] = useState<ImputExportForm>({ date_from: firstDay, date_to: today, include_costs: false, format: 'xlsx' })
  const [projForm,  setProjForm]  = useState<ProjectsExportForm>({ include_costs: false, format: 'xlsx' })
  const [jiraProject, setJiraProject] = useState('')
  const [loading, setLoading] = useState<LoadingState>({ imput: false, proj: false })
  const [jiraSyncing, setJiraSyncing] = useState(false)
  const toast = useToast()

  const { data: projects = [] } = useQuery<ProjectListItem[]>({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list({}).then((response) => unwrapList(response) as ProjectListItem[]),
  })

  const setLoad = (k: keyof LoadingState, v: boolean) => setLoading((l) => ({ ...l, [k]: v }))

  const exportImputations = async () => {
    setLoad('imput', true)
    try {
      // Auditoría 2026-08/09. Este selector llevaba desde siempre ofreciendo
      // XLSX y el servidor sólo servía CSV; ya coinciden: el formato va al
      // servidor y la extensión sale del botón.
      // Revisión 2026-11: admin y hr reciben las horas de todos; el resto, las suyas.
      const { data } = await integrationsApi.exportImputations({
        date_from: imputForm.date_from,
        date_to: imputForm.date_to,
        include_costs: imputForm.include_costs,
        formato: imputForm.format,
      })
      downloadBlob(data, t('pagina_exps.imputaciones', { date_from: imputForm.date_from, date_to: imputForm.date_to, format: imputForm.format }))
      toast.success(t('pagina_exps.archivo_descargado_correctamente'))
    } catch { toast.error(t('pagina_exps.error_al_exportar')) }
    finally { setLoad('imput', false) }
  }

  const exportProjects = async () => {
    setLoad('proj', true)
    try {
      const { data } = await integrationsApi.exportProjects({
        include_costs: projForm.include_costs,
        formato: projForm.format,
      })
      downloadBlob(data, t('pagina_exps.proyectos', { today, format: projForm.format }))
      toast.success(t('pagina_exps.archivo_descargado_correctamente'))
    } catch { toast.error(t('pagina_exps.error_al_exportar')) }
    finally { setLoad('proj', false) }
  }

  const syncJira = async () => {
    if (!jiraProject) return
    setJiraSyncing(true)
    try {
      await jiraApi.sync({ project_id: jiraProject })
      toast.success(t('pagina_exps.sincronizacion_con_jira_iniciada_en_segundo'))
    } catch (e) {
      toast.error(extractErrorMessage(e) || t('pagina_exps.error_al_sincronizar_con_jira'))
    } finally { setJiraSyncing(false) }
  }

  const selectorDeFormato = (actual: 'xlsx' | 'csv', cambiar: (f: 'xlsx' | 'csv') => void) => (
    <div className="exps-formatos" role="group" aria-label={t('exports.format')}>
      {(['xlsx', 'csv'] as const).map((fmt) => (
        <Button key={fmt} size="sm" variant={actual === fmt ? 'primary' : 'secondary'} onClick={() => cambiar(fmt)}>
          {fmt.toUpperCase()}
        </Button>
      ))}
    </div>
  )

  return (
    <Page icon={<Download size={18} />} title={t('nav.data_exports')} subtitle={t('exports.subtitle')}>
      <Card>
        <Section
          title={<span className="exps-titulo"><FileSpreadsheet size={16} aria-hidden />{t('pagina_exps.exportar_imputaciones')}</span>}
          subtitle={t('exports.descarga_el_registro_de_horas_en_excel')}
        >
          <div className="exps-grid">
            <div>
              <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="exps-label">{t('pagina_exps.desde')}</label>
              <DateInput id={`${idCampo}-1`} value={imputForm.date_from}
                onChange={e => setImputForm(f => ({ ...f, date_from: e.target.value }))}
                className="exps-card" />
            </div>
            <div>
              <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="exps-label">{t('pagina_exps.hasta')}</label>
              <DateInput id={`${idCampo}-2`} value={imputForm.date_to}
                onChange={e => setImputForm(f => ({ ...f, date_to: e.target.value }))}
                className="exps-card" />
            </div>
          </div>
          <div className="exps-row">
            {selectorDeFormato(imputForm.format, (fmt) => setImputForm(f => ({ ...f, format: fmt })))}
            {hasRole('admin', 'hr') && (
              <label className="u-row-center-8-pointer">
                <input type="checkbox" checked={imputForm.include_costs}
                  onChange={e => setImputForm(f => ({ ...f, include_costs: e.target.checked }))} />
                {t('pagina_exps.incluir_costes_confidencial')}
              </label>
            )}
          </div>
          <p className="exps-text">
            {hasRole('admin', 'hr') ? t('pagina_exps.incluye_las_horas_de_todas_las') : t('pagina_exps.incluye_tus_horas')}
          </p>
          <div>
            <Button onClick={exportImputations} loading={loading.imput} icon={<Download size={14} />}>
              {loading.imput ? t('pagina_exps.generando') : t('pagina_exps.descargar', { v1: imputForm.format.toUpperCase() })}
            </Button>
          </div>
        </Section>
      </Card>

      <Card>
        <Section
          title={<span className="exps-titulo"><FolderKanban size={16} aria-hidden />{t('pagina_exps.exportar_proyectos')}</span>}
          subtitle={t('exports.informe_completo_de_todos_los_proyectos_con')}
        >
          {/* Auditoría 2026-09: la etiqueta dice el formato que de verdad se descarga. */}
          <div className="exps-row">
            {selectorDeFormato(projForm.format, (fmt) => setProjForm(f => ({ ...f, format: fmt })))}
            {hasRole('admin') && (
              <label className="u-row-center-8-pointer">
                <input type="checkbox" checked={projForm.include_costs}
                  onChange={e => setProjForm(f => ({ ...f, include_costs: e.target.checked }))} />
                {t('exports.incluir_costes_y_margenes_confidencial')}
              </label>
            )}
          </div>
          <div>
            <Button onClick={exportProjects} loading={loading.proj} icon={<Download size={14} />}>
              {loading.proj ? t('pagina_exps.generando') : t('pagina_exps.descargar_de_proyectos', { v1: projForm.format.toUpperCase() })}
            </Button>
          </div>
        </Section>
      </Card>

      {hasRole('admin', 'pm') && (
        <Card>
          <Section
            title={<span className="exps-titulo"><Link2 size={16} aria-hidden />{t('exports.sincronizar_con_jira')}</span>}
            subtitle={t('exports.importa_issues_de_jira_como_tareas_en')}
          >
            <div className="exps-row-3">
              <select value={jiraProject} onChange={e => setJiraProject(e.target.value)}
                aria-label={t('pagina_exps.selecciona_proyecto')}
                className={`exps-input ${jiraProject ? 'exportsp-sx7' : 'exportsp-sx8'}`}>
                <option value="">{t('pagina_exps.selecciona_proyecto')}</option>
                {projects.filter(p => p.status === 'active').map(p => (
                  <option key={p.id} value={p.id}>{p.code} — {p.name}</option>
                ))}
              </select>
              <Button onClick={syncJira} disabled={!jiraProject} loading={jiraSyncing} icon={<RefreshCw size={14} />}>
                {jiraSyncing ? t('pagina_exps.sincronizando') : t('pagina_exps.sincronizar')}
              </Button>
            </div>
            <p className="exps-text-2">
              {t('pagina_exps.requiere_jira_enabled_true_y_credenciales')}
            </p>
          </Section>
        </Card>
      )}
    </Page>
  )
}

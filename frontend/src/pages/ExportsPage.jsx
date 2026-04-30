import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { integrationsApi, projectsApi } from '../services/api'
import { Button, Card } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Download } from 'lucide-react'
import { downloadBlob } from '../utils/helpers'
import { useAuth } from '../context/AuthContext'
import { useAppT } from '../i18n/AppLangContext'

export default function ExportsPage() {
  const t = useAppT()
  const { hasRole } = useAuth()
  const today = new Date().toISOString().split('T')[0]
  const firstDay = new Date(new Date().getFullYear(), new Date().getMonth(), 1).toISOString().split('T')[0]

  const [imputForm, setImputForm] = useState({ date_from: firstDay, date_to: today, include_costs: false, format: 'xlsx' })
  const [projForm,  setProjForm]  = useState({ include_costs: false })
  const [jiraProject, setJiraProject] = useState('')
  const [loading, setLoading] = useState({})
  const [jiraSyncing, setJiraSyncing] = useState(false)
  const [message, setMessage] = useState('')

  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list().then(r => r.data),
  })

  const setLoad = (k, v) => setLoading(l => ({ ...l, [k]: v }))
  const showMsg = (msg) => { setMessage(msg); setTimeout(() => setMessage(''), 3000) }

  const exportImputations = async () => {
    setLoad('imput', true)
    try {
      const { data } = await integrationsApi.exportImputations(imputForm)
      downloadBlob(data, `imputaciones_${imputForm.date_from}_${imputForm.date_to}.${imputForm.format}`)
      showMsg('✅ Archivo descargado correctamente')
    } catch { showMsg('❌ Error al exportar') }
    finally { setLoad('imput', false) }
  }

  const exportProjects = async () => {
    setLoad('proj', true)
    try {
      const { data } = await integrationsApi.exportProjects(projForm)
      downloadBlob(data, `proyectos_${today}.xlsx`)
      showMsg('✅ Archivo descargado correctamente')
    } catch { showMsg('❌ Error al exportar') }
    finally { setLoad('proj', false) }
  }

  const syncJira = async () => {
    if (!jiraProject) return
    setJiraSyncing(true)
    try {
      await integrationsApi.jiraSync(jiraProject)
      showMsg('✅ Sincronización con Jira iniciada en segundo plano')
    } catch (e) {
      const _raw = e.response?.data?.detail
      showMsg(`❌ ${Array.isArray(_raw) ? _raw.map(d => d.msg).join(', ') : (_raw || 'Error al sincronizar con Jira')}`)
    } finally { setJiraSyncing(false) }
  }

  return (
    <PageShell style={{ maxWidth: 760, margin: '0 auto' }}>
      <PageHeader icon={<Download size={18} />} title={t('exports.title')} subtitle={t('exports.subtitle')} />

      {message && (
        <div style={{
          background: message.startsWith('✅') ? 'var(--success-bg)' : 'var(--danger-bg)',
          border: `1px solid ${message.startsWith('✅') ? 'var(--success-border)' : 'var(--danger-border)'}`,
          borderRadius: 8, padding: '10px 16px', marginBottom: 20,
          fontSize: "var(--text-md)", color: message.startsWith('✅') ? 'var(--success)' : 'var(--danger)',
        }}>
          {message}
        </div>
      )}

      {/* Imputations export */}
      <Card style={{ marginBottom: 20 }}>
        <h3 style={{ fontSize: "var(--text-lg)", fontWeight: 700, marginBottom: 4 }}>📊 Exportar Imputaciones</h3>
        <p style={{ color: 'var(--text-2)', fontSize: "var(--text-base)", marginBottom: 20 }}>
          Descarga el registro de horas en Excel o CSV, listo para facturación o análisis.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 16 }}>
          <div>
            <label style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 6 }}>Desde</label>
            <input type="date" value={imputForm.date_from}
              onChange={e => setImputForm(f => ({ ...f, date_from: e.target.value }))}
              style={{ width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }} />
          </div>
          <div>
            <label style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 6 }}>Hasta</label>
            <input type="date" value={imputForm.date_to}
              onChange={e => setImputForm(f => ({ ...f, date_to: e.target.value }))}
              style={{ width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }} />
          </div>
        </div>
        <div style={{ display: 'flex', gap: 16, marginBottom: 16, alignItems: 'center' }}>
          <div style={{ display: 'flex', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, overflow: 'hidden' }}>
            {['xlsx', 'csv'].map(fmt => (
              <button key={fmt} onClick={() => setImputForm(f => ({ ...f, format: fmt }))}
                style={{ padding: '8px 16px', background: imputForm.format === fmt ? 'var(--accent-muted)' : 'transparent', border: 'none', color: imputForm.format === fmt ? 'var(--accent)' : 'var(--text-2)', fontSize: "var(--text-sm)", fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>
                {fmt.toUpperCase()}
              </button>
            ))}
          </div>
          {hasRole('admin') && (
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: "var(--text-base)", cursor: 'pointer' }}>
              <input type="checkbox" checked={imputForm.include_costs}
                onChange={e => setImputForm(f => ({ ...f, include_costs: e.target.checked }))} />
              Incluir costes € (confidencial)
            </label>
          )}
        </div>
        <Button onClick={exportImputations} disabled={loading.imput} icon="↓">
          {loading.imput ? 'Generando...' : `Descargar ${imputForm.format.toUpperCase()}`}
        </Button>
      </Card>

      {/* Projects export */}
      <Card style={{ marginBottom: 20 }}>
        <h3 style={{ fontSize: "var(--text-lg)", fontWeight: 700, marginBottom: 4 }}>📁 Exportar Proyectos</h3>
        <p style={{ color: 'var(--text-2)', fontSize: "var(--text-base)", marginBottom: 20 }}>
          Informe completo de todos los proyectos con métricas de avance y presupuesto.
        </p>
        {hasRole('admin') && (
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: "var(--text-base)", cursor: 'pointer', marginBottom: 16 }}>
            <input type="checkbox" checked={projForm.include_costs}
              onChange={e => setProjForm(f => ({ ...f, include_costs: e.target.checked }))} />
            Incluir costes y márgenes € (confidencial)
          </label>
        )}
        <Button onClick={exportProjects} disabled={loading.proj} icon="↓">
          {loading.proj ? 'Generando...' : 'Descargar Excel de proyectos'}
        </Button>
      </Card>

      {/* Jira sync */}
      {hasRole('admin', 'pm') && (
        <Card>
          <h3 style={{ fontSize: "var(--text-lg)", fontWeight: 700, marginBottom: 4 }}>🔗 Sincronizar con Jira</h3>
          <p style={{ color: 'var(--text-2)', fontSize: "var(--text-base)", marginBottom: 20 }}>
            Importa issues de Jira como tareas en Contecflow. Se sincroniza en segundo plano.
          </p>
          <div style={{ display: 'flex', gap: 12 }}>
            <select value={jiraProject} onChange={e => setJiraProject(e.target.value)}
              style={{ flex: 1, background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 14px', color: jiraProject ? 'var(--text-1)' : 'var(--text-2)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', cursor: 'pointer' }}>
              <option value="">Selecciona proyecto...</option>
              {projects.filter(p => p.status === 'active').map(p => (
                <option key={p.id} value={p.id}>{p.code} — {p.name}</option>
              ))}
            </select>
            <Button onClick={syncJira} disabled={!jiraProject || jiraSyncing} icon="↻">
              {jiraSyncing ? 'Sincronizando...' : 'Sincronizar'}
            </Button>
          </div>
          <p style={{ color: 'var(--text-3)', fontSize: "var(--text-xs)", marginTop: 10 }}>
            Requiere JIRA_ENABLED=true y credenciales configuradas en .env
          </p>
        </Card>
      )}
    </PageShell>
  )
}

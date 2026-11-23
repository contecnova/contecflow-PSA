// Pestaña de integraciones de Enterprise. 23-11-2026: troceado de EnterprisePage sin cambio de comportamiento.
import { useAppLang, useAppT } from '../i18n/AppLangContext'
import { useState, useId } from 'react'
import type { CSSProperties } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr, fmtDate } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { oauthIntegrationsApi, integrationsHubApi } from '../services/api'
import { Button, IconButton, CampoFecha, Pulsable, Input } from '../components/ui'
import { INTEGRATION_CATALOG } from '../constants/api'
import { CheckCircle2, RefreshCw, Trash2, X, XCircle } from 'lucide-react'
import { type IntegrationCatalogEntry, type IntegrationForm, JIRA_ID, type OAuthIntegration, iconoIntegracion } from './EnterpriseComun'

export function IntegrationsTab() {
  const { t } = useAppLang()
  const idCampo = useId()
  const traducir = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [configuring, setConfiguring] = useState<IntegrationCatalogEntry | null>(null)
  const [testing, setTesting]         = useState<string|null>(null)
  const [testResult, setTestResult]   = useState<{ok:boolean;message:string}|null>(null)
  const [form, setForm] = useState<IntegrationForm>({ name:'', access_token:'', config:{} })

  const { data: otras = [] } = useQuery({
    // 23-11-2026 (04 A8): clave propia; `['integrations']` la compartía con el chat.
    queryKey: ['oauth-integraciones'],
    queryFn: () => oauthIntegrationsApi.list().then(r => r.data),
  })

  // Segunda auditoría 2026-11 (#23): Jira es la conexión única de la organización
  // (`/integrations-hub/jira/config`), no una fila de `integration_configs`.
  const { data: jira } = useQuery({
    queryKey: ['jira-hub-config'],
    queryFn: () => integrationsHubApi.jiraConfig().then(r => r.data),
  })
  const integrations: OAuthIntegration[] = [
    ...otras.filter(i => i.integration_type !== 'jira'),
    ...(jira?.configured && jira.is_active ? [{
      id: JIRA_ID, name: jira.name, integration_type: 'jira', is_active: true,
      last_sync_at: jira.last_sync_at ?? null,
    }] : []),
  ]
  const invalidar = () => {
    qc.invalidateQueries({ queryKey: ['oauth-integraciones'] })
    qc.invalidateQueries({ queryKey: ['jira-hub-config'] })
  }

  const { mutate: create, isPending } = useMutation({
    mutationFn: (d: Omit<IntegrationForm, 'config'> & { config: string }): Promise<unknown> => {
      if (d.integration_type === 'jira') {
        const cfg = JSON.parse(d.config || '{}') as Record<string, string>
        return integrationsHubApi.saveJiraConfig({
          name: d.name, base_url: cfg.base_url || '', email: cfg.email || '',
          api_token: cfg.api_token || undefined, project_key: cfg.project_key ?? undefined,
        })
      }
      return oauthIntegrationsApi.create(d)
    },
    onSuccess: () => { invalidar(); setConfiguring(null); toast.success(t('pagina_ent.integracion_guardada')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const { mutate: del } = useMutation({
    mutationFn: (id: string) => id === JIRA_ID ? integrationsHubApi.deleteJiraConfig() : oauthIntegrationsApi.delete(id),
    onSuccess: () => { invalidar(); toast.success(t('pagina_ent.integracion_eliminada')) },

    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  })

  const { mutate: sync } = useMutation({
    mutationFn: (id: string) => id === JIRA_ID ? integrationsHubApi.syncJira() : oauthIntegrationsApi.sync(id, {}),
    onSuccess: (r) => { qc.invalidateQueries({ queryKey: ['oauth-integraciones'] }); toast.success(r?.data?.errors?.length
        ? t('pagina_ent.sincronizados_con_error', { synced: r?.data?.synced ?? 0, length: r.data.errors.length })
        : t('pagina_ent.sincronizados_elementos', { synced: r?.data?.synced ?? 0 })) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const testIntegration = async (integ: OAuthIntegration) => {
    setTesting(integ.id)
    setTestResult(null)
    try {
      const cfg = integ.config || {}
      if (integ.integration_type === 'slack') {
        const res = await integrationsHubApi.testSlack({ webhook_url: cfg.webhook_url || '' })
        setTestResult({ ok: true, message: res.data.message })
      } else if (integ.integration_type === 'teams') {
        const res = await integrationsHubApi.testTeams({ webhook_url: cfg.webhook_url || '' })
        setTestResult({ ok: true, message: res.data.message })
      } else if (integ.integration_type === 'jira') {
        // Sin datos: el servidor prueba la conexión guardada (el token no viaja al navegador).
        const res = await integrationsHubApi.testJira({})
        setTestResult({ ok: true, message: t('pagina_ent.conectado_proyectos_jira_disponibles', { total: res.data.total }) })
      } else {
        const res = await oauthIntegrationsApi.sync(integ.id, {})
        setTestResult({ ok: true, message: t('pagina_ent.sincronizados_elementos', { synced: res.data.synced }) })
      }
    } catch (e: unknown) {
      setTestResult({ ok: false, message: extractErr(e, t('pagina_ent.error_de_conexion')) })
    } finally {
      setTesting(null)
    }
  }

  // El catálogo viene de la configuración de negocio sin tipar (`unknown`).
  const CATALOG = INTEGRATION_CATALOG as IntegrationCatalogEntry[]

  return (
    <div>
      <div className="ent-box-6">{t('pagina_ent.integraciones_nativas')}</div>
      <div className="ent-box-7">{traducir('enterprise.conecta_contecflow_con_tus_herramientas_de_trabajo')}</div>

      {/* Integraciones activas */}
      {integrations.length > 0 && (
        <div className="u-mb-20">
          <div className="ent-box-8">{t('pagina_ent.configuradas')}</div>
          {integrations.map(integ => {
            const cat = CATALOG.find((c) => c.type === integ.integration_type) || { label: integ.integration_type }
            const Icono = iconoIntegracion(integ.integration_type)
            return (
              <div key={integ.id} className="ent-row-6">
                <div className="ent-row-7">
                  <span className="ent-label-6" aria-hidden><Icono size={20} /></span>
                  <div>
                    <div className="u-base-700">{integ.name || cat.label}</div>
                    <div className={`u-xs ${integ.is_active ? 'enterpri-sx3' : 'enterpri-sx4'}`}>
                      {integ.is_active ? t('pagina_ent.activa') : t('pagina_ent.inactiva')}
                      {integ.last_sync_at && t('pagina_ent.ultimo_sync', { v1: fmtDate(integ.last_sync_at) })}
                    </div>
                  </div>
                </div>
                <div className="u-row-6">
                  <Button size="sm" variant="secondary" onClick={() => testIntegration(integ)} loading={testing === integ.id}>
                    {t('pagina_ent.probar')}
                  </Button>
                  <Button size="sm" variant="secondary" icon={<RefreshCw size={14} />} onClick={() => sync(integ.id)}>
                    {t('pagina_ent.sync')}
                  </Button>
                  <IconButton className="ent-borrar" ariaLabel={t('pagina_ent.eliminar', { name: integ.name || cat.label })}
                    onClick={() => { openConfirmGlobal({ message: t('pagina_ent.eliminar', { name: integ.name }), onConfirm: () => del(integ.id), danger: true }) }}><Trash2 size={14} aria-hidden /></IconButton>
                </div>
              </div>
            )
          })}

          {/* Test result */}
          {testResult && (
            <div className={`ent-row-8 enterpri-sx5 ${testResult.ok ? 'enterpri-sx6' : 'enterpri-sx7'} enterprise-page-e7`} style={{ '--enterprise-page-border': `1px solid ${testResult.ok ? 'var(--success-border)' : 'var(--danger-border)'}` } as CSSProperties}>
              <span className="ent-resultado">{testResult.ok ? <CheckCircle2 size={14} aria-hidden /> : <XCircle size={14} aria-hidden />} {testResult.message}</span>
              <IconButton ariaLabel={t('pagina_ent.cerrar')} onClick={() => setTestResult(null)}><X size={14} aria-hidden /></IconButton>
            </div>
          )}
        </div>
      )}

      {/* Catálogo para añadir */}
      <div className="ent-box-8">
        {integrations.length === 0 ? t('pagina_ent.disponibles') : t('pagina_ent.anadir_otra')}
      </div>
      <div className="ent-grid-4">
        {CATALOG.map((cat) => { const Icono = iconoIntegracion(cat.type); return (
          <Pulsable key={cat.type} aria-pressed={configuring?.type === cat.type} onClick={() => {
            setConfiguring(cat)
            // Jira: se precarga la conexión guardada; el token vacío conserva el actual.
            const previa = cat.type === 'jira' && jira?.configured
              ? { base_url: jira.base_url || '', email: jira.email || '', project_key: jira.project_key || '' } : {}
            setForm({ name: (cat.type === 'jira' && jira?.configured && jira.name) || cat.label, integration_type: cat.type, config: previa })
          }}
            type="button"
            className="ent-btn-8 enterpri-sx8 ent-catalogo"
          >
            <div className="ent-box-9" aria-hidden><Icono size={22} /></div>
            <div className="ent-box-10">{cat.label}</div>
            <div className="u-text2-xs">{t(`pagina_ent.int_desc_${cat.type}`, cat.desc)}</div>
          </Pulsable>
        ) })}
      </div>

      {/* Formulario de configuración */}
      {configuring && (
        <div className="ent-card-7">
          <div className="ent-box-11">
            {t('pagina_ent.configurar')}{' '}{configuring.label}
          </div>
          <div className="ent-grid-5">
            <div>
              <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="enterprise-page-e18">{traducir('enterprise.nombre_de_la_integracion')}</label>
              <Input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.name} onChange={e => setForm(f=>({...f,name:e.target.value}))} inputClassName="enterprise-page-e19" />
            </div>
            {configuring.fields?.map(field => (
              <div key={field.key}>
                <label id={`${idCampo}-et-${field.key}`} htmlFor={`${idCampo}-${field.key}`} className="enterprise-page-e18">{t(`pagina_ent.int_campo_${configuring.type}_${field.key}`, field.label)}</label>
                {['date', 'datetime-local', 'time'].includes(field.type || '') ? (
                  // Fechas con el selector del kit (16-11-2026), nunca el input nativo.
                  <CampoFecha id={`${idCampo}-${field.key}`} aria-labelledby={`${idCampo}-et-${field.key}`}
                    modo={field.type === 'time' ? 'hora' : field.type === 'date' ? 'fecha' : 'fechaHora'}
                    value={String(form.config?.[field.key] || '')}
                    onChange={v => setForm(f => ({ ...f, config: { ...f.config, [field.key]: v } }))}
                    className="enterprise-page-e19"
                  />
                ) : (
                  <Input id={`${idCampo}-${field.key}`} aria-labelledby={`${idCampo}-et-${field.key}`}
                    type={field.type || 'text'}
                    value={form.config?.[field.key] || ''}
                    onChange={e => setForm(f => ({ ...f, config: { ...f.config, [field.key]: e.target.value } }))}
                    inputClassName="enterprise-page-e19"
                    placeholder={field.placeholder ? t(`pagina_ent.int_ph_${configuring.type}_${field.key}`, field.placeholder) : ''}
                  />
                )}
              </div>
            ))}
          </div>
          <div className="u-actions-8">
            <Button variant="secondary" onClick={() => setConfiguring(null)}>{t('pagina_ent.cancelar')}</Button>
            <Button onClick={() => create({ ...form, integration_type: configuring.type, config: JSON.stringify(form.config) })}
              loading={isPending}>
              {isPending ? t('pagina_ent.guardando') : t('pagina_ent.guardar_integracion')}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

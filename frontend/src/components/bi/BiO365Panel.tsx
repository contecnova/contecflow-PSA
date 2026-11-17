/**
 * BiO365Panel — Office 365 productivity analytics.
 * Conecta con /api/v1/bi/o365/*
 *
 * Revisión 2026-11: el secreto se guarda (cifrado) en vez de teclearlo en cada
 * sincronización; «Sincronizar» enseña lo que pasó con cada informe; la lista
 * de informes viene del servidor; y la adopción ya no pinta «[object Object]».
 */
import React, { useEffect, useState } from 'react'
import { tooltipDelTema } from '../../constants/estilosGrafico'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { biO365Api } from '../../services/api'
import { useAppT } from '../../i18n/AppLangContext'
import { useChartTheme } from '../../charts/useChartTheme'
import { BarChart3, Cloud, RefreshCw, Settings, Users } from 'lucide-react'
import { Button, EmptyState, Tabs, Checkbox } from '../ui'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { extractErr, fmtDateTime, localeActivo } from '../../utils/helpers'
import { useToast } from '../../context/ToastContext'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import './BiO365Panel.css'

interface O365ConfigForm {
  tenant_id: string
  client_id: string
  client_secret: string
  enabled: boolean
}


export default function BiO365Panel() {
  const idCampo = React.useId()
  const t             = useAppT()
  const toast         = useToast()
  const { tokens }    = useChartTheme()
  const qc            = useQueryClient()
  const [tab,          setTab]          = useState<string>('reports')
  const [selectedReport, setSelectedReport] = useState<string>('teams_activity')
  const [configForm,   setConfigForm]   = useState<O365ConfigForm>({ tenant_id: '', client_id: '', client_secret: '', enabled: true })
  const [configLoaded, setConfigLoaded] = useState<boolean>(false)

  const { data: config } = useQuery({
    queryKey: ['bi-o365-config'],
    queryFn:  () => biO365Api.getConfig().then(r => r.data),
  })

  useEffect(() => {
    if (config && !configLoaded) {
      setConfigForm({ tenant_id: config.tenant_id, client_id: config.client_id, client_secret: '', enabled: config.enabled })
      setConfigLoaded(true)
    }
  }, [config, configLoaded])

  const { data: reportData } = useQuery({
    queryKey: ['bi-o365-report', selectedReport],
    queryFn:  () => biO365Api.getReport(selectedReport, {}).then(r => r.data),
    enabled:  tab === 'reports',
  })

  const { data: adoptionData } = useQuery({
    queryKey: ['bi-o365-adoption'],
    queryFn:  () => biO365Api.getAdoption().then(r => r.data),
    enabled:  tab === 'adoption',
  })

  const saveConfigMutation = useMutation({
    mutationFn: (data: O365ConfigForm) => biO365Api.saveConfig(data).then(r => r.data),
    onSuccess:  () => {
      setConfigForm(f => ({ ...f, client_secret: '' }))
      toast.success(t('bio365.guardado'))
      qc.invalidateQueries({ queryKey: ['bi-o365-config'] })
    },
    onError: (e) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const syncMutation = useMutation({
    mutationFn: () => biO365Api.triggerSync({}).then(r => r.data),
    onSuccess:  (r) => {
      const filas = r.synced.reduce((n, x) => n + (x.records ?? 0), 0)
      if (r.ok) toast.success(t('bio365.sync_ok', { n: filas.toLocaleString(localeActivo()) }))
      else toast.error(t('bio365.sync_fallo', { error: r.error ?? '' }))
      qc.invalidateQueries({ queryKey: ['bi-o365-report'] })
      qc.invalidateQueries({ queryKey: ['bi-o365-adoption'] })
      qc.invalidateQueries({ queryKey: ['bi-o365-config'] })
    },
    onError: (e) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const puedeSincronizar = !!config?.enabled && !!config?.secret_puesto

  const rows = reportData?.rows ?? []

  const TAB_NAV = [
    { id: 'reports',  label: t('bio365.tab_informes'), icon: <BarChart3 size={14} /> },
    { id: 'adoption', label: t('bio365.tab_adopcion'), icon: <Users size={14} /> },
    { id: 'config',   label: t('bio365.tab_configuracion'), icon: <Settings size={14} /> },
  ]

  return (
    <div className="bi-o365-panel-e12">
      {/* Header */}
      <div className="bio3pa-row-1">
        <div className="u-row-center-10">
          <div className="bio3pa-row-2">
            <Cloud size={16} />
          </div>
          <div>
            <h3 className="bio3pa-box-1">
              {t('bio365.titulo')}
            </h3>
            <p className="bio3pa-box-2">{t('bio365.productividad_y_adopcion_de_microsoft_365')}</p>
          </div>
        </div>
        <Button size="sm" variant="secondary" icon={<RefreshCw size={14} />}
          onClick={() => syncMutation.mutate()}
          disabled={syncMutation.isPending || !puedeSincronizar}
          loading={syncMutation.isPending}
          title={puedeSincronizar ? undefined : t('bio365.falta_configurar')}
        >
          {t('bio365.sincronizar')}
        </Button>
      </div>

      {/* Tab navigation */}
      <Tabs items={TAB_NAV} active={tab} onChange={setTab} ariaLabel={t('bio365.titulo')} className="bio3pa-tabs" />

      {/* Reportes tab */}
      {tab === 'reports' && (
        <div className="u-stack-16">
          <div className="u-wrap-6">
            {(config?.reports ?? []).map(key => ({ key, label: t(`bio365.informe_${key}`) })).map(r => (
              <Button size="sm" variant={selectedReport === r.key ? 'primary' : 'secondary'} key={r.key} onClick={() => setSelectedReport(r.key)}>
                {r.label}
              </Button>
            ))}
          </div>

          {rows.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={rows.slice(0, 10)}>
                <XAxis dataKey={Object.keys(rows[0])[0]} tick={{ fontSize: "var(--text-3xs)", fill: tokens.textColor }} />
                <YAxis tick={{ fontSize: "var(--text-3xs)", fill: tokens.textColor }} />
                <Tooltip contentStyle={tooltipDelTema(tokens)} />
                <Bar dataKey={Object.keys(rows[0])[1] ?? 'value'} fill="var(--accent)" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <EmptyState icon={<BarChart3 size={28} />} title={t('bio365.sin_datos')} />
          )}
        </div>
      )}

      {/* Adopción tab */}
      {tab === 'adoption' && (
        adoptionData?.total_users ? (
          <div className="bio3pa-grid-1">
            <div className="bio3pa-grid-2">
              {([
                ['bio365.usuarios', adoptionData.total_users.toLocaleString(localeActivo())],
                ['bio365.activos', adoptionData.active_users.toLocaleString(localeActivo())],
                ['bio365.adopcion', `${(adoptionData.adoption_rate ?? 0).toLocaleString(localeActivo())} %`],
              ] as const).map(([k, v]) => (
                <div key={k} className="bio3pa-box-4">
                  <div className="bio3pa-box-5">{t(k)}</div>
                  <div className="bio3pa-txt-1">{v}</div>
                </div>
              ))}
            </div>
            {Object.keys(adoptionData.by_product ?? {}).length > 0 && (
              <div>
                <div className="bio3pa-label">{t('bio365.licencias_por_producto')}</div>
                {Object.entries(adoptionData.by_product ?? {}).sort((a, b) => b[1] - a[1]).map(([prod, n]) => (
                  <div key={prod} className="bio3pa-row-4">
                    <span className="u-text2">{prod}</span>
                    <span className="bio3pa-txt-2">{n.toLocaleString(localeActivo())}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : (
          <EmptyState icon={<Users size={28} />} title={t('bio365.sin_adopcion')} />
        )
      )}

      {/* Configuración tab */}
      {tab === 'config' && (
        <div className="u-stack-14">
          <div className="u-row-center-8">
            <Settings size={14} className="bio365pa-sx2" />
            <span className="u-text1-base-600">
              {t('bio365.config_graph')}
            </span>
          </div>
          <div className="bio3pa-grid-3">
            <div>
              <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="bi-o365-panel-e13">{t('bio365.tenant_id')}</label>
              <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} type="text" value={configForm.tenant_id} onChange={e => setConfigForm(f => ({ ...f, tenant_id: e.target.value }))} className="bi-o365-panel-e14" />
            </div>
            <div>
              <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="bi-o365-panel-e13">{t('bio365.client_id')}</label>
              <input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} type="text" value={configForm.client_id} onChange={e => setConfigForm(f => ({ ...f, client_id: e.target.value }))} className="bi-o365-panel-e14" />
            </div>
            <div className="u-col-full">
              <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="bi-o365-panel-e13">
                {t('bio365.client_secret')}{' '}
                <span className="bio3pa-txt-3">
                  {t('bio365.secreto_ayuda')}
                </span>
              </label>
              <input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} type="password" value={configForm.client_secret} onChange={e => setConfigForm(f => ({ ...f, client_secret: e.target.value }))} placeholder={config?.secret_puesto ? t('bio365.secreto_puesto') : ''} autoComplete="off" className="bi-o365-panel-e14" />
            </div>
          </div>
          <div className="bio3pa-row-5">
            <Checkbox className="bio3pa-row-6" label={t('bio365.sincronizacion_habilitada')} checked={configForm.enabled} onChange={m => setConfigForm(f => ({ ...f, enabled: m }))} />
            <Button
              onClick={() => saveConfigMutation.mutate(configForm)}
              disabled={saveConfigMutation.isPending}
              loading={saveConfigMutation.isPending}
            >
              {saveConfigMutation.isPending ? t('bio365.guardando') : t('common.save')}
            </Button>
          </div>
          {config?.last_sync_at && (
            <div className="u-text3-xs">
              {t('bio365.ultimo_sync')} {fmtDateTime(config.last_sync_at)}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

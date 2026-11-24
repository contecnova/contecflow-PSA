/**
 * Sección «Informes de Microsoft 365» de Configuración
 * (`/settings/m365-informes`, 19-11-2026).
 *
 * Antes era la pestaña «Configuración» del panel Office 365 de la Plataforma
 * de datos (BiO365Panel). Credenciales de Graph de la empresa para los
 * informes de uso y adopción: tenant, client id, client secret (se guarda
 * cifrado; vacío = no cambia) y si la sincronización está activa.
 *
 * No es lo mismo que la sección `m365` (Microsoft 365: calendario, hitos y
 * Teams), que se configura con variables de entorno de la instalación; esta
 * guarda credenciales por empresa en `app_settings` (bi_o365_service).
 *
 * Escritura: PUT /bi/o365/config, `require_admin`; la sección pide
 * `org.administrar`. Auditado desde el 19-11-2026 (`bi_o365_config`, sin el
 * secreto: solo si cambió).
 */
import React, { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Settings } from 'lucide-react'
import { biO365Api } from '../../services/api'
import { useAppT } from '../../i18n/AppLangContext'
import { Button, Checkbox, Spinner, Input } from '../ui'
import { extractErr, fmtDateTime } from '../../utils/helpers'
import { useToast } from '../../context/ToastContext'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import './BiO365Panel.css'

interface O365ConfigForm {
  tenant_id: string
  client_id: string
  client_secret: string
  enabled: boolean
}

export default function ConfigBiO365() {
  const idCampo = React.useId()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [configForm, setConfigForm] = useState<O365ConfigForm>({ tenant_id: '', client_id: '', client_secret: '', enabled: true })
  const [configLoaded, setConfigLoaded] = useState<boolean>(false)

  const { data: config, isLoading } = useQuery({
    queryKey: ['bi-o365-config'],
    queryFn: () => biO365Api.getConfig().then(r => r.data),
  })

  useEffect(() => {
    if (config && !configLoaded) {
      setConfigForm({ tenant_id: config.tenant_id, client_id: config.client_id, client_secret: '', enabled: config.enabled })
      setConfigLoaded(true)
    }
  }, [config, configLoaded])

  const saveConfigMutation = useMutation({
    mutationFn: (data: O365ConfigForm) => biO365Api.saveConfig(data).then(r => r.data),
    onSuccess: () => {
      setConfigForm(f => ({ ...f, client_secret: '' }))
      toast.success(t('bio365.guardado'))
      qc.invalidateQueries({ queryKey: ['bi-o365-config'] })
    },
    onError: (e) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  if (isLoading) return <Spinner />
  return (
    <div className="u-stack-14">
      <div className="u-row-center-8">
        <Settings size={14} className="bio365pa-sx2" />
        <span className="u-text1-base-600">
          {t('bio365.config_graph')}
        </span>
      </div>
      <div className="bio3pa-grid-3">
        <Input label={t('bio365.tenant_id')} id={`${idCampo}-1`} type="text" value={configForm.tenant_id} onChange={e => setConfigForm(f => ({ ...f, tenant_id: e.target.value }))} />
        <Input label={t('bio365.client_id')} id={`${idCampo}-2`} type="text" value={configForm.client_id} onChange={e => setConfigForm(f => ({ ...f, client_id: e.target.value }))} />
        <div className="u-col-full">
          <Input label={<>{t('bio365.client_secret')}{' '}<span className="bio3pa-txt-3">
              {t('bio365.secreto_ayuda')}
            </span></>} id={`${idCampo}-3`} type="password" value={configForm.client_secret} onChange={e => setConfigForm(f => ({ ...f, client_secret: e.target.value }))} placeholder={config?.secret_puesto ? t('bio365.secreto_puesto') : ''} autoComplete="off" />
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
  )
}

/**
 * Sección de proveedores de firma electrónica.
 * Troceado de SettingsPageSections.tsx sin cambio de comportamiento (23-11-2026).
 */
import React, { useState, type FormEvent } from 'react'
import { useToast } from '../../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { esignApi, apiUrl } from '../../services/api'
import type { ClaveDeFirma, ConfigDeFirma } from '../../services/api/tipos-finanzas'
import { Button, Input, Spinner } from '../../components/ui'
import { PenLine, FileSignature, CheckCircle2 } from 'lucide-react'
import { useAppLang } from '../../i18n/AppLangContext'
import { extractErr } from '../../utils/helpers'
import SeccionDeAjustes from './SeccionDeAjustes'

// ── E-firma (Electronic Signature) settings ───────────────────────────────────
type ESignFieldKey = ClaveDeFirma

/** GET /esign/config, o el formulario a medio rellenar. */
type ESignConfig = Partial<ConfigDeFirma>

type ESignProvider = {
  id: string
  label: string
  icon: React.ReactNode
  configKey: 'docusign_configured' | 'adobe_configured'
  fields: Array<{ key: ESignFieldKey; label: string; placeholder: string; secret: boolean }>
}

const ESIGN_PROVIDERS: ESignProvider[] = [
  {
    id: 'docusign',
    label: 'DocuSign',
    icon: <FileSignature size={18} />,
    configKey: 'docusign_configured',
    fields: [
      { key: 'docusign_integration_key', label: 'Integration Key (Client ID)', placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx', secret: false },
      { key: 'docusign_account_id',      label: 'Account ID',                  placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx', secret: false },
      { key: 'docusign_secret_key',      label: 'Secret Key',                  placeholder: '••••••••••••••••',                     secret: true  },
      { key: 'docusign_base_url',        label: 'Base URL',                    placeholder: 'https://demo.docusign.net/restapi',   secret: false },
    ],
  },
  {
    id: 'adobe',
    label: 'Adobe Sign',
    icon: <PenLine size={18} />,
    configKey: 'adobe_configured',
    fields: [
      { key: 'adobe_sign_client_id',     label: 'Client ID',     placeholder: 'CBJCH…',                                         secret: false },
      { key: 'adobe_sign_client_secret', label: 'Client Secret', placeholder: '••••••••••••••••',                               secret: true  },
      { key: 'adobe_sign_base_url',      label: 'Base URL',      placeholder: 'https://api.na1.adobesign.com/api/rest/v6',     secret: false },
    ],
  },
]

interface ProviderCardProps {
  provider: ESignProvider
  config: ESignConfig | undefined
  form: ESignConfig
  onChange: (key: ESignFieldKey, value: string) => void
  onSave: (provider: ESignProvider) => void
  isSaving: boolean
}

function ProviderCard({ provider, config, form, onChange, onSave, isSaving }: ProviderCardProps) {
  const idCampo = React.useId()
  const { t } = useAppLang()
  const isConfigured = config?.[provider.configKey]
  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    onSave(provider)
  }
  return (
    <div className={`set-provider${isConfigured ? ' set-provider--ok' : ''}`}>
      <div className="u-row-between u-mb-14">
        <div className="u-row-center-8">
          <span className="set-provider-icon" aria-hidden="true">{provider.icon}</span>
          <span className="u-md-700">{provider.label}</span>
        </div>
        <span className={`set-status${isConfigured ? ' set-status--ok' : ''}`}>
          {isConfigured ? <><CheckCircle2 size={13} aria-hidden /> {t('settings_sections.configurado')}</> : t('settings_sections.no_configurado')}
        </span>
      </div>

      <form onSubmit={handleSubmit}>
        <div className="set-grid2-mb14">
        {provider.fields.map(f => (
          <div key={f.key}>
            <Input label={f.label} id={`${idCampo}-${f.key}-c1934`}
              type={f.secret ? 'password' : 'text'}
              value={form[f.key] ?? ''}
              onChange={e => onChange(f.key, e.target.value)}
              placeholder={f.secret && form[f.key] === '***' ? t('settings_sections.guardado_cambiar') : f.placeholder}
              autoComplete="off"
            />
          </div>
        ))}
        </div>

        <div className="u-row-end">
          <Button size="sm" type="submit" loading={isSaving}>{t('settings_sections.guardar_x', { nombre: provider.label })}</Button>
        </div>
      </form>
    </div>
  )
}

export function ESignSettingsSection() {
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()

  const { data: config, isLoading } = useQuery<ESignConfig>({
    queryKey: ['esign-config'],
    queryFn: () => esignApi.getConfig().then(r => r.data),
  })

  const [form, setForm] = useState<ESignConfig>({})
  React.useEffect(() => {
    if (config) setForm({ ...config })
  }, [config])

  const { mutate: save, isPending: isSaving } = useMutation({
    mutationFn: (data: Partial<Record<ESignFieldKey, string>>) => esignApi.saveConfig(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['esign-config'] })
      qc.invalidateQueries({ queryKey: ['esign-stats'] })
      toast.success(t('settings.settings_saved'))
    },
    onError: e => toast.error(extractErr(e, t('settings_sections.err_guardar_config'))),
  })

  const handleChange = (key: ESignFieldKey, value: string) => setForm(f => ({ ...f, [key]: value }))

  const handleSave = (provider: ESignProvider) => {
    const payload: Partial<Record<ESignFieldKey, string>> = {}
    provider.fields.forEach(f => {
      const val = form[f.key]
      if (val !== undefined) payload[f.key] = val
    })
    save(payload)
  }

  return (
    <SeccionDeAjustes icon={<PenLine size={18} />} title={t('settings.firma_electronica')} description={t('settings_sections.firma_desc')}>
      {isLoading ? (
        <Spinner />
      ) : (
        <>
          <div className="set-note">
            <div className="set-note-title">{t('settings_sections.modo_manual')}</div>
            <div className="u-text2-sm">
              {t('settings.sin_credenciales_las_solicitudes_se_gestionan_en')}
            </div>
          </div>

          <div className="u-mb-20">
            <div className="set-eyebrow">{t('settings.webhooks_de_sincronizacion_de_estado')}</div>
            <div className="set-code-box">
              <div className="u-text2-xs-mb4">{t('settings.configura_en_el_panel_de_tu_proveedor')}</div>
              <div className="set-code-line">DocuSign Connect: <span className="ds-codigo u-text1">{apiUrl('/esign/webhooks/docusign')}</span></div>
              <div className="set-code-line">Adobe Sign: <span className="ds-codigo u-text1">{apiUrl('/esign/webhooks/adobe')}</span></div>
            </div>
          </div>

          {ESIGN_PROVIDERS.map(provider => (
            <ProviderCard
              key={provider.id}
              provider={provider}
              config={config}
              form={form}
              onChange={handleChange}
              onSave={handleSave}
              isSaving={isSaving}
            />
          ))}
        </>
      )}
    </SeccionDeAjustes>
  )
}

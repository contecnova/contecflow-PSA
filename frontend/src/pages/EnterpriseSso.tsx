// Pestaña de SSO de Enterprise. 23-11-2026: troceado de EnterprisePage sin cambio de comportamiento.
import { useAppLang, useAppT } from '../i18n/AppLangContext'
import { useState, useId } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { authApi, enterpriseApi } from '../services/api'
import type { ConfigSso } from '../services/api/tipos'
import { Button, EmptyState, IconButton, StatusBadge, Select, Checkbox, Input, Textarea } from '../components/ui'
import { CheckCircle2, KeyRound, Pencil, Plus, Trash2, XCircle } from 'lucide-react'
import useMediaQuery from '../hooks/useMediaQuery'
import { useRolesReales } from '../hooks/useRolesReales'
import { type AltaProps } from './EnterpriseComun'

export function SSOTab({ showCreate, setShowCreate }: AltaProps) {
  const { t } = useAppLang()
  // 19-11-2026: roles reales del backend (`GET /auth/roles`).
  const roles = useRolesReales()
  const idCampo = useId()
  const traducir = useAppT()
  const isNarrow = useMediaQuery('(max-width: 900px)')
  const toast = useToast()
  const qc = useQueryClient()
  const [testResult, setTestResult] = useState<{valid?:boolean; issues?:string[]}|null>(null)
  // Auditoría 2026-11: el formulario solo tenía cliente y discovery; no se
  // podía activar (el PATCH no existía en el cliente), ni elegir rol por
  // defecto, mapear grupos a roles o limitar dominios.
  const VACIO = {
    provider: 'azure_ad', name: '',
    oidc_client_id: '', oidc_client_secret: '',
    oidc_discovery_url: '', oidc_scopes: 'openid email profile', is_active: true,
    default_role: 'employee', auto_create_users: true, allowed_domains: '',
    groups_claim: 'groups', role_mapping_text: '',
    // SAML 2.0 (23-11-2026)
    saml_entity_id: '', saml_sso_url: '', saml_slo_url: '', saml_certificate: '',
    saml_attribute_email: 'email', saml_attribute_name: 'displayName', saml_attribute_role: '',
  }
  const [form, setForm] = useState(VACIO)
  const [editId, setEditId] = useState<string | null>(null)
  const [certGuardado, setCertGuardado] = useState(false)
  const esSaml = form.provider === 'saml'
  const { data: urlsSp } = useQuery({
    queryKey: ['saml-sp-urls'],
    queryFn: () => authApi.samlUrlsDelSp().then(r => r.data),
    enabled: esSaml && showCreate,
  })
  const aPayload = (f: typeof VACIO) => {
    const role_mapping: Record<string, string> = {}
    f.role_mapping_text.split('\n').map(l => l.trim()).filter(Boolean).forEach(l => {
      const i = l.lastIndexOf('=')
      if (i > 0) role_mapping[l.slice(0, i).trim()] = l.slice(i + 1).trim()
    })
    const { role_mapping_text: _omit, ...resto } = f
    const datos: Record<string, unknown> = { ...resto, role_mapping }
    const CAMPOS_OIDC = ['oidc_client_id', 'oidc_client_secret', 'oidc_discovery_url', 'oidc_scopes']
    const CAMPOS_SAML = ['saml_entity_id', 'saml_sso_url', 'saml_slo_url', 'saml_certificate',
      'saml_attribute_email', 'saml_attribute_name', 'saml_attribute_role']
    for (const k of (f.provider === 'saml' ? CAMPOS_OIDC : CAMPOS_SAML)) delete datos[k]
    if (f.provider === 'saml' && !f.saml_certificate) delete datos.saml_certificate
    if (editId) { delete datos.provider; if (!f.oidc_client_secret) delete datos.oidc_client_secret }
    return datos
  }

  const { data: configs = [] } = useQuery<ConfigSso[]>({
    queryKey: ['sso-cfg'],
    queryFn: () => enterpriseApi.ssoList().then(r => r.data), // 23-11-2026: sin .catch; el aviso lo da el onError global de consultas
  })

  const { mutate: create, isPending: creating } = useMutation({
    mutationFn: (d: Record<string, unknown>) => (editId ? enterpriseApi.ssoUpdate(editId, d) : enterpriseApi.ssoCreate(d)),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sso-cfg'] }); setShowCreate(false); setEditId(null); setForm(VACIO); toast.success(t('pagina_ent.sso_guardado')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const { mutate: toggle } = useMutation({
    mutationFn: (c: ConfigSso) => enterpriseApi.ssoUpdate(c.id, { is_active: !c.is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sso-cfg'] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const editar = (c: ConfigSso) => {
    setEditId(c.id)
    setForm({
      ...VACIO, provider: c.provider, name: c.name || '', oidc_client_id: c.oidc_client_id || '',
      oidc_discovery_url: c.oidc_discovery_url || '', oidc_scopes: c.oidc_scopes || VACIO.oidc_scopes,
      is_active: !!c.is_active, default_role: c.default_role || 'employee', auto_create_users: c.auto_create_users !== false,
      allowed_domains: c.allowed_domains || '', groups_claim: c.groups_claim || 'groups',
      role_mapping_text: Object.entries(c.role_mapping || {}).map(([g, r]) => `${g}=${r}`).join('\n'),
      saml_entity_id: c.saml_entity_id || '', saml_sso_url: c.saml_sso_url || '', saml_slo_url: c.saml_slo_url || '',
      saml_certificate: '', saml_attribute_email: c.saml_attribute_email || 'email',
      saml_attribute_name: c.saml_attribute_name || 'displayName', saml_attribute_role: c.saml_attribute_role || '',
    })
    setCertGuardado(!!c.has_certificate)
    setShowCreate(true)
  }

  const { mutate: del } = useMutation({
    mutationFn: (id: string) => enterpriseApi.ssoDelete(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sso-cfg'] }); toast.success(t('pagina_ent.sso_eliminado')) },

    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  })

  const testSSO = async (id: string) => {
    try {
      const res = await enterpriseApi.ssoTest(id)
      setTestResult(res.data)
    } catch (e: unknown) {
      setTestResult({ valid: false, issues: [extractErr(e, t('pagina_ent.error_de_conexion'))] })
    }
  }

  const PROVIDER_INFO: Record<string, { label:string; discovery:string }> = {
    azure_ad: { label: t('pagina_ent.azure_ad_entra_id'), discovery: 'https://login.microsoftonline.com/{tenant-id}/v2.0/.well-known/openid-configuration' },
    okta:     { label: 'Okta',                discovery: 'https://{your-domain}.okta.com/.well-known/openid-configuration' },
    google:   { label: 'Google Workspace',    discovery: 'https://accounts.google.com/.well-known/openid-configuration' },
    oidc:     { label: t('pagina_ent.oidc_generico'), discovery: 'https://your-idp.com/.well-known/openid-configuration' },
    saml:     { label: traducir('enterprise.saml_proveedor'), discovery: '' },
  }
  const cerrarFormulario = () => { setShowCreate(false); setEditId(null); setForm(VACIO); setCertGuardado(false) }
  const puedeGuardar = esSaml
    ? !!(form.saml_entity_id && form.saml_sso_url && (form.saml_certificate || certGuardado))
    : !!form.oidc_client_id


  return (
    <div>
      <div className="ent-row-10">
        <div className="u-min0">
          <div className="u-md-700">{t('pagina_ent.single_sign_on_sso')}</div>
          <div className="u-text2-sm">{t('pagina_ent.configura_azure_ad_entra_id_okta')}</div>
        </div>
      </div>

      {/* Información de integración */}
      <div className="enterprise-page-e10">
        <div className="ent-box-23">{traducir('enterprise.como_integrar_sso')}</div>
        <div className="ent-box-24">
          {traducir('enterprise.1_registra_contecflow_como_aplicacion_en_tu')}<br/>
          {traducir('enterprise.2_configura_el')} <strong className="u-text1">{t('pagina_ent.redirect_uri')}</strong>: <code className="ds-codigo ent-card-11">{window.location.origin}/login</code><br/>
          {traducir('enterprise.3_copia_el_client_id_y_client')}<br/>
          {traducir('enterprise.4_anade_el_boton_de_login_sso')} <strong className="u-text1">{t('pagina_ent.ajustes')}{' '}{'>'}{' '}{t('pagina_ent.seguridad')}</strong>.
        </div>
      </div>

      {/* Formulario de creación */}
      {showCreate && (
        <div className="enterprise-page-e11">
          <div className="ent-box-25">{editId ? traducir('enterprise.sso_editar') : traducir('enterprise.nuevo_proveedor_sso')}</div>
          <div className={`ent-grid-10 ${isNarrow ? 'enterpri-sx10' : 'enterpri-sx11'}`}>
            <div>
              <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="enterprise-page-e20">{t('pagina_ent.proveedor')}</label>
              <Select suelto placeholder={false} id={`${idCampo}-1`} value={form.provider} disabled={!!editId} onChange={e => {
                const info: { label?: string; discovery?: string } = PROVIDER_INFO[e.target.value] || {}
                setForm(f => ({ ...f, provider: e.target.value, oidc_discovery_url: info.discovery || '' }))
              }} className="enterprise-page-e19">
                {Object.entries(PROVIDER_INFO).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
              </Select>
            </div>
            <div>
              <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="enterprise-page-e20">{traducir('enterprise.nombre_para_mostrar_en_login')}</label>
              <Input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.name} onChange={e => setForm(f=>({...f,name:e.target.value}))} placeholder={PROVIDER_INFO[form.provider]?.label} inputClassName="enterprise-page-e19" />
            </div>
            {!esSaml && (<>
            <div>
              <label id={`${idCampo}-et10`} htmlFor={`${idCampo}-10`} className="enterprise-page-e20">{t('pagina_ent.client_id')}</label>
              <Input id={`${idCampo}-10`} aria-labelledby={`${idCampo}-et10`} value={form.oidc_client_id} onChange={e => setForm(f=>({...f,oidc_client_id:e.target.value}))} placeholder={traducir('enterprise.client_id_del_proveedor')} inputClassName="enterprise-page-e19" />
            </div>
            <div>
              <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="enterprise-page-e20">{t('pagina_ent.client_secret')}</label>
              <Input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} type="password" value={form.oidc_client_secret} onChange={e => setForm(f=>({...f,oidc_client_secret:e.target.value}))} inputClassName="enterprise-page-e19" />
            </div>
            <div className="u-col-full">
              <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="enterprise-page-e20">{t('pagina_ent.discovery_url_openid_connect')}</label>
              <Input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.oidc_discovery_url} onChange={e => setForm(f=>({...f,oidc_discovery_url:e.target.value}))} placeholder={PROVIDER_INFO[form.provider]?.discovery} inputClassName="enterprise-page-e19" />
            </div>
            <div>
              <label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="enterprise-page-e20">{traducir('enterprise.sso_scopes')}</label>
              <Input id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={form.oidc_scopes} onChange={e => setForm(f=>({...f,oidc_scopes:e.target.value}))} inputClassName="enterprise-page-e19" />
            </div>
            </>)}
            {esSaml && (<>
            <div className="u-col-full">
              <label id={`${idCampo}-et11`} htmlFor={`${idCampo}-11`} className="enterprise-page-e20">{traducir('enterprise.saml_entity_id')}</label>
              <Input id={`${idCampo}-11`} aria-labelledby={`${idCampo}-et11`} value={form.saml_entity_id} onChange={e => setForm(f=>({...f,saml_entity_id:e.target.value}))} placeholder="https://idp.example.com/metadata" inputClassName="enterprise-page-e19" />
            </div>
            <div>
              <label id={`${idCampo}-et12`} htmlFor={`${idCampo}-12`} className="enterprise-page-e20">{traducir('enterprise.saml_sso_url')}</label>
              <Input id={`${idCampo}-12`} aria-labelledby={`${idCampo}-et12`} value={form.saml_sso_url} onChange={e => setForm(f=>({...f,saml_sso_url:e.target.value}))} placeholder="https://idp.example.com/sso" inputClassName="enterprise-page-e19" />
            </div>
            <div>
              <label id={`${idCampo}-et13`} htmlFor={`${idCampo}-13`} className="enterprise-page-e20">{traducir('enterprise.saml_slo_url')}</label>
              <Input id={`${idCampo}-13`} aria-labelledby={`${idCampo}-et13`} value={form.saml_slo_url} onChange={e => setForm(f=>({...f,saml_slo_url:e.target.value}))} placeholder="https://idp.example.com/slo" inputClassName="enterprise-page-e19" />
            </div>
            <div className="u-col-full">
              <label id={`${idCampo}-et14`} htmlFor={`${idCampo}-14`} className="enterprise-page-e20">{traducir('enterprise.saml_certificado')}</label>
              <Textarea id={`${idCampo}-14`} aria-labelledby={`${idCampo}-et14`} rows={4} value={form.saml_certificate} onChange={e => setForm(f=>({...f,saml_certificate:e.target.value}))} placeholder={certGuardado ? traducir('enterprise.saml_certificado_guardado') : '-----BEGIN CERTIFICATE-----'} inputClassName="ds-codigo enterprise-page-e12" />
            </div>
            <div>
              <label id={`${idCampo}-et15`} htmlFor={`${idCampo}-15`} className="enterprise-page-e20">{traducir('enterprise.saml_attr_email')}</label>
              <Input id={`${idCampo}-15`} aria-labelledby={`${idCampo}-et15`} value={form.saml_attribute_email} onChange={e => setForm(f=>({...f,saml_attribute_email:e.target.value}))} inputClassName="enterprise-page-e19" />
            </div>
            <div>
              <label id={`${idCampo}-et16`} htmlFor={`${idCampo}-16`} className="enterprise-page-e20">{traducir('enterprise.saml_attr_nombre')}</label>
              <Input id={`${idCampo}-16`} aria-labelledby={`${idCampo}-et16`} value={form.saml_attribute_name} onChange={e => setForm(f=>({...f,saml_attribute_name:e.target.value}))} inputClassName="enterprise-page-e19" />
            </div>
            <div>
              <label id={`${idCampo}-et17`} htmlFor={`${idCampo}-17`} className="enterprise-page-e20">{traducir('enterprise.saml_attr_rol')}</label>
              <Input id={`${idCampo}-17`} aria-labelledby={`${idCampo}-et17`} value={form.saml_attribute_role} onChange={e => setForm(f=>({...f,saml_attribute_role:e.target.value}))} inputClassName="enterprise-page-e19" />
            </div>
            {urlsSp && (
              <div className="u-col-full u-text2-xs">
                <strong className="u-text1">{traducir('enterprise.saml_datos_sp')}</strong><br/>
                {traducir('enterprise.saml_metadata')}: <code className="ds-codigo">{urlsSp.metadata_url}</code><br/>
                {traducir('enterprise.saml_acs')}: <code className="ds-codigo">{urlsSp.acs_url}</code><br/>
                {traducir('enterprise.saml_slo_sp')}: <code className="ds-codigo">{urlsSp.slo_url}</code><br/>
                {traducir('enterprise.saml_firma_obligatoria')}
              </div>
            )}
            </>)}
            <div>
              <label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} className="enterprise-page-e20">{traducir('enterprise.sso_dominios')}</label>
              <Input id={`${idCampo}-6`} aria-labelledby={`${idCampo}-et6`} value={form.allowed_domains} onChange={e => setForm(f=>({...f,allowed_domains:e.target.value}))} placeholder={t('pagina_ent.empresa_com_filial_es')} inputClassName="enterprise-page-e19" />
            </div>
            <div>
              <label id={`${idCampo}-et7`} htmlFor={`${idCampo}-7`} className="enterprise-page-e20">{traducir('enterprise.sso_rol_defecto')}</label>
              <Select suelto placeholder={false} id={`${idCampo}-7`} value={form.default_role} onChange={e => setForm(f=>({...f,default_role:e.target.value}))} className="enterprise-page-e19">
                {roles.map(r => <option key={r.id} value={r.id}>{r.etiqueta}</option>)}
              </Select>
            </div>
            <div>
              <label id={`${idCampo}-et8`} htmlFor={`${idCampo}-8`} className="enterprise-page-e20">{traducir('enterprise.sso_claim_grupos')}</label>
              <Input id={`${idCampo}-8`} aria-labelledby={`${idCampo}-et8`} value={form.groups_claim} onChange={e => setForm(f=>({...f,groups_claim:e.target.value}))} inputClassName="enterprise-page-e19" />
            </div>
            <div className="u-col-full">
              <label id={`${idCampo}-et9`} htmlFor={`${idCampo}-9`} className="enterprise-page-e20">{traducir('enterprise.sso_mapeo')}</label>
              <Textarea id={`${idCampo}-9`} aria-labelledby={`${idCampo}-et9`} rows={3} value={form.role_mapping_text} onChange={e => setForm(f=>({...f,role_mapping_text:e.target.value}))} placeholder={'Contecflow-Admins=admin\nContecflow-PM=pm'} inputClassName="ds-codigo enterprise-page-e12" />
            </div>
            <label className="ent-label-9">
              <Checkbox aria-label={traducir('enterprise.sso_autocrear')} checked={form.auto_create_users} onChange={(_, e) => setForm(f=>({...f,auto_create_users:e.target.checked}))} />
              {traducir('enterprise.sso_autocrear')}
            </label>
            <label className="ent-label-9">
              <Checkbox aria-label={traducir('enterprise.sso_activo')} checked={form.is_active} onChange={(_, e) => setForm(f=>({...f,is_active:e.target.checked}))} />
              {traducir('enterprise.sso_activo')}
            </label>
          </div>
          <div className="u-actions-8">
            <Button variant="secondary" onClick={cerrarFormulario}>{t('pagina_ent.cancelar')}</Button>
            <Button onClick={() => create(aPayload(form))} disabled={!puedeGuardar} loading={creating}>
              {creating ? t('pagina_ent.guardando') : t('pagina_ent.guardar_sso')}
            </Button>
          </div>
        </div>
      )}

      {/* Lista de proveedores */}
      {configs.length === 0 && !showCreate ? (
        <EmptyState icon={<KeyRound size={28} />} title={traducir('enterprise.sin_sso_configurado')} description={traducir('enterprise.anade_azure_ad_okta_o_google_para')}
          action={<Button icon={<Plus size={14} />} onClick={() => { setEditId(null); setForm(VACIO); setShowCreate(true) }}>{t('pagina_ent.anadir_proveedor')}</Button>} />
      ) : (
        configs.map(c => {
          const info = PROVIDER_INFO[c.provider] || { label: c.provider }
          return (
            <div key={c.id} className="enterprise-page-e13">
              <div className="ent-row-11">
                <div className="ent-row-7">
                  <span className="ent-label-10" aria-hidden><KeyRound size={20} /></span>
                  <div className="ent-box-29">
                    <div className="u-md-700">{c.name || info.label}</div>
                    <div className="u-text2-xs">
                      {c.provider === 'saml'
                        ? (c.saml_entity_id || '').slice(0, 40)
                        : <>{t('pagina_ent.client_id_2')}{' '}{c.oidc_client_id?.slice(0,8)}...</>}
                      {' '}<StatusBadge kind={c.is_active ? 'success' : 'neutral'}>{c.is_active ? t('pagina_ent.activo') : t('pagina_ent.inactivo')}</StatusBadge>
                    </div>
                    {c.oidc_discovery_url && (
                      <div className="ent-box-30">{c.oidc_discovery_url.slice(0, 60)}...</div>
                    )}
                  </div>
                </div>
                <div className="u-wrap-6">
                  <Button size="sm" variant="secondary" onClick={() => toggle(c)}>
                    {c.is_active ? traducir('enterprise.sso_desactivar') : traducir('enterprise.sso_activar')}
                  </Button>
                  <Button size="sm" variant="secondary" onClick={() => testSSO(c.id)}>
                    {t('pagina_ent.verificar_config')}
                  </Button>
                  <IconButton variante="caja" onClick={() => editar(c)} ariaLabel={`${traducir('enterprise.sso_editar')} ${c.name || c.provider}`}><Pencil size={14} aria-hidden /></IconButton>
                  <IconButton variante="caja" tono="peligro" ariaLabel={t('pagina_ent.eliminar_2', { v1: c.name || c.provider })} onClick={() => { openConfirmGlobal({ message: t('pagina_ent.eliminar_2', { v1: c.name || c.provider }), onConfirm: () => del(c.id), danger: true }) }}><Trash2 size={14} aria-hidden /></IconButton>
                </div>
              </div>
            </div>
          )
        })
      )}

      {/* Resultado del test */}
      {testResult && (
        <div className={`enterprise-page-e13 ${testResult.valid ? 'enterprise-page-m14' : 'enterprise-page-m15'}`}>
          <div className={`ent-box-31 ent-resultado ${testResult.valid ? 'enterpri-sx3' : 'enterpri-sx4'}`}>
            {testResult.valid ? <CheckCircle2 size={14} aria-hidden /> : <XCircle size={14} aria-hidden />}
            {testResult.valid ? t('pagina_ent.configuracion_valida') : t('pagina_ent.configuracion_incompleta')}
          </div>
          {(testResult.issues?.length ?? 0) > 0 && (
            <ul className="ent-box-32">
              {testResult.issues!.map((i: string, idx: number) => <li key={idx} className="ent-box-33">{i}</li>)}
            </ul>
          )}
          <div className="ent-cerrar-clave"><Button size="sm" variant="secondary" onClick={() => setTestResult(null)}>{t('pagina_ent.cerrar')}</Button></div>
        </div>
      )}
    </div>
  )
}

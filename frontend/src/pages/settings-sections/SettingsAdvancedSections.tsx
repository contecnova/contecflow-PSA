/*
 * Secciones avanzadas de /settings (idiomas, registro, estado del sistema,
 * parámetros de funcionamiento y credenciales).
 *
 * 16-11-2026: pasada de diseño. Pestañas con Tabs (antes botones propios con
 * emojis); botones del kit con icono lucide; campos con .ds-input; textos que
 * estaban en castellano a fuego pasan por t() (es/en/zh); fuera la jerga
 * técnica visible (.env, override, knobs, FastAPI, localStorage, claves
 * internas de cada parámetro, rutas de API) en favor de lenguaje llano para
 * administradores; colores fijos (#c0392b, rgba) cambiados por tokens.
 */
import EstadoDeConectores from '../../components/conectores/EstadoDeConectores'
import type { CSSProperties } from 'react'
import { Fragment, useState, useEffect, useMemo } from 'react'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAppLang } from '../../i18n/AppLangContext'
import { extractErr } from '../../utils/helpers'
import { textoDeResultado } from '../../utils/resultadoConCodigo'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import SeccionDeAjustes from './SeccionDeAjustes'
import { settingsApi, type IntegrationProvider, type IntegrationTestResult, type RuntimeSetting } from '../../services/api'
import { Button, Select, Tabs, Input } from '../../components/ui'
import { CheckCircle2, Lock, Plug, Settings2, XCircle } from 'lucide-react'
import './SettingsAdvancedSections.css'

export { IdiomasSection } from './SettingsIdiomasSection'
export { LogLevelSection } from './SettingsEstadoSistemaSections'
export { SystemStateSection } from './SettingsEstadoSistemaSections'


// ── Runtime-flag groups (env → UI migration) ──────────────────────────────────
// Generic editor for groups declared in app/services/settings_service.py.
// Each row in the response is {key, type, label, value} — we render a typed
// input per row and PUT back to /settings/runtime/{group}/{key}.

// Los textos visibles salen de `settingsadvanced.rt_<id>` y `rt_<id>_desc`.
// 18-11-2026 (reorganización de Configuración): cada ajuste en un solo sitio.
// Los grupos `service_desk` (avisos del service desk) y `traduccion` tienen su
// propia sección (Service desk → Escalado y avisos; IA e idiomas → Traducción)
// y ya no salen aquí; las claves de `locale` que edita Empresa → General
// (CLAVES_EN_GENERAL) se ocultan en este editor.
export const CLAVES_EN_GENERAL = ['DEFAULT_CURRENCY', 'DEFAULT_TIMEZONE', 'DEFAULT_LANGUAGE', 'DEFAULT_WORKING_HOURS_PER_DAY']
// 19-11-2026: valores de negocio que se editan en su sección (Personas → Vacaciones; Seguridad → Chat).
export const CLAVE_MAXIMO_VACACIONES = 'VACATION_MAX_DAYS_ENTITLED'
export const CLAVE_RETENCION_PROPUESTA_CHAT = 'CHAT_RETENTION_PROPOSED_MONTHS'
const OCULTAS_POR_GRUPO: Record<string, string[]> = {
  locale: [...CLAVES_EN_GENERAL, CLAVE_MAXIMO_VACACIONES],
  audit: [CLAVE_RETENCION_PROPUESTA_CHAT],
}

const RUNTIME_GROUPS = [
  { id: 'sla',             label: 'SLA',                description: 'Tiempos por prioridad, jornada sin política y umbral de riesgo.' },
  { id: 'automations',     label: 'Automatizaciones',   description: 'Si las reglas saltan, cuánto puede encadenarse una con otra y los plazos del barrido.' },
  { id: 'tenants',         label: 'Empresas',           description: 'Cuarentena de la baja de una empresa y «entrar como» del soporte de plataforma.' },
  { id: 'risk',            label: 'Riesgo del proyecto', description: 'Pesos, umbrales de nivel y caché de la puntuación de riesgo por señales.' },
  { id: 'health',          label: 'Health scoring',     description: 'Pesos y umbrales del scoring de salud de cliente y proyecto.' },
  { id: 'proyectos',       label: 'Proyectos y planificador', description: 'Días laborables, umbrales del camino crítico, nivelación, alertas de recursos, curva S y cartera.' },
  { id: 'semantic',        label: 'Semantic',           description: 'Umbrales del clasificador semántico y motor de asignación.' },
  // 23-11-2026: `password_policy` se edita en Configuración › Seguridad de cuentas (el backend rechaza el grupo aquí).
  { id: 'locale',          label: 'Locale y jornada',   description: 'Moneda, zona horaria, idioma y defaults de jornada laboral.' },
  { id: 'tokens',          label: 'Tokens',             description: 'TTL de access y refresh tokens.' },
  { id: 'key_rotation',    label: 'Rotación de claves', description: 'Política de rotación automática de claves JWT e integraciones.' },
  { id: 'ai',              label: 'IA',                 description: 'Modelo por defecto, backend de embeddings, STT, alertas de coste.' },
  { id: 'feature_flags',   label: 'Feature flags',      description: 'Toggles operativos: M365, sincronización de tipos de cambio.' },
  { id: 'storage',         label: 'Almacenamiento',     description: 'TTL de URLs presigned S3 y tamaño máximo de subida.' },
  { id: 'security_network', label: 'Red / Proxy',       description: 'Trust de headers X-Forwarded y CIDRs autorizados.' },
  { id: 'ui_branding',     label: 'Branding / UI',      description: 'Nombre del producto, embed BI, etiqueta WebAuthn.' },
  { id: 'observability',   label: 'Observabilidad',     description: 'Token Bearer para el endpoint /metrics.' },
  { id: 'timeouts',        label: 'Timeouts',           description: 'Tiempos de espera por defecto para llamadas HTTP/AI a APIs externas.' },
  { id: 'audit',           label: 'Auditoría y cumplimiento', description: 'Exportación firmada del registro y umbrales del informe de cumplimiento.' },
  { id: 'presupuestos',    label: 'Presupuestos', description: 'Tipos de partida, qué categoría de gasto cuenta en cada una y quién crea y aprueba.' },
  { id: 'gastos',          label: 'Gastos', description: 'Tarifa por km, tamaño de los justificantes y qué roles gestionan los gastos de todos.' },
  { id: 'alm',             label: 'Licencias y hardware', description: 'Actas de entrega y su firma, préstamos, avisos de renovación, amortización, refacturación y tolerancia de la conciliación.' },
  { id: 'politicas',       label: 'Políticas y reglas', description: 'Cuántas entidades repasa el simulador y qué tipos de documento puede pedir una regla.' },
  { id: 'lecciones',       label: 'Lecciones aprendidas', description: 'Categorías, quién valida, borrador con IA y cómo se buscan los casos parecidos (pesos y mínimo).' },
  { id: 'licencias_uso', label: 'Licencias y equipos: uso real', description: 'Cuándo una licencia cuenta como sin uso o infrautilizada, cada cuánto se lee el uso, periodo de los informes, plazos de recuperación y qué se analiza como software sin gestionar.' },
  { id: 'licencias_integracion', label: 'Licencias y equipos: altas y bajas', description: 'Cuándo se liberan las licencias de quien se va, qué pasa con el equipo sin devolver, colas de devolución, compras y averías, y el kit de alta.' },
  { id: 'conectores',      label: 'Conectores contecmind / contecintelligence', description: 'Tiempos de espera, roles que escriben o analizan, tamaño de subida y registro de llamadas.' },
  { id: 'informes',        label: 'Informes', description: 'Periodo libre: rango máximo que se puede pedir, puntos máximos de una serie por granularidad y objetivo de la granularidad automática.' },
  { id: 'semaforos',       label: 'Semáforos', description: 'Cortes de aviso y crítico por métrica (presupuesto, carga, SLA, OKR, NPS, margen, sprint, aprobaciones, vencimientos, hitos del portal), los mismos en todas las pantallas e informes. Riesgo, salud y EVM siguen en sus grupos.' },
]


/** `solo` (19-11-2026): pinta sólo esas claves del grupo, para editar un ajuste en su sección. */
export function RuntimeGroupEditor({ groupId, description, ocultar = [], solo }: { groupId: string; description?: string; ocultar?: string[]; solo?: string[] }) {
  const { t } = useAppLang()
  // Los ajustes de plataforma sólo los cambia el superadmin (revisión 2026-11).
  const esSuperadmin = useAuth().puede('plataforma.empresas')
  const toast = useToast()
  const qc = useQueryClient()

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['runtime-flags', groupId],
    queryFn: () => settingsApi.runtimeGroup(groupId).then(r => r.data),
  })

  const { mutate: save, isPending } = useMutation({
    mutationFn: ({ key, value }: { key: string; value: string | boolean }) => settingsApi.setRuntime(groupId, key, value),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['runtime-flags', groupId] })
      // Los valores de formulario (`propuestas`) y los umbrales llegan por /settings/org-defaults.
      qc.invalidateQueries({ queryKey: ['org-defaults'] })
      toast.success(t('i18n.saved'))
    },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const [draft, setDraft] = useState<Record<string, string>>({})
  useEffect(() => {
    if (data?.items) {
      const next: Record<string, string> = {}
      for (const it of data.items) next[it.key] = it.value == null ? '' : String(it.value)
      setDraft(next)
    }
  }, [data])

  if (isLoading) return <div className="seadse-box-28">{t('chat.loading')}</div>
  if (isError) return <div className="seadse-box-29">{extractErr(error, GENERIC_ERROR_FALLBACK)}</div>

  const items = (data?.items || []).filter(it => !ocultar.includes(it.key) && (!solo || solo.includes(it.key)))

  return (
    <div className="u-stack-14">
      <div className="u-text2-sm">{description}</div>
      <div className="seadse-grid-5">
        {items.map(it => {
          const current = draft[it.key] ?? ''
          const isBool = it.type === 'bool'
          const dirty = String(it.value ?? '') !== String(current)
          return (
            <RuntimeFlagRow
              key={it.key}
              item={it}
              current={current}
              isBool={isBool}
              dirty={dirty}
              disabled={isPending || (it.plataforma && !esSuperadmin)}
              onChange={v => setDraft({ ...draft, [it.key]: v })}
              onSave={() => save({ key: it.key, value: isBool ? current === 'true' : current })}
            />
          )
        })}
      </div>
      <div className="u-text3-xs">
        {t('settingsadvanced.los_cambios_reemplazan_el_valor_por_defecto')}
      </div>
    </div>
  )
}


function RuntimeFlagRow({ item, current, isBool, dirty, disabled, onChange, onSave }: { item: RuntimeSetting; current: string; isBool: boolean; dirty: boolean; disabled: boolean; onChange: (v: string) => void; onSave: () => void }) {
  const { t } = useAppLang()
  // 19-11-2026: etiqueta traducida por clave (`ajuste_clave.<CLAVE>` en es/en/zh);
  // el texto del backend (inglés) queda de respaldo para claves nuevas.
  const etiqueta = t(`ajuste_clave.${item.key}`, item.label)
  return (
    <>
      <div className="seadse-stack-2">
        <span className="u-text1-sm-600">{etiqueta}</span>
        {item.plataforma && <span className="seadse-txt-2">{t('settingsadvanced.solo_superadmin')}</span>}
      </div>
      <div>
        {isBool ? (
          <Select suelto placeholder={false} value={String(current)} onChange={(e) => onChange(e.target.value)} aria-label={etiqueta} className="seadse-inputstyle" disabled={disabled && item.plataforma}>
            <option value="true">{t('settingsadvanced.activado')}</option>
            <option value="false">{t('settingsadvanced.desactivado')}</option>
          </Select>
        ) : (
          <Input aria-label={etiqueta} type={item.type === 'int' || item.type === 'float' ? 'number' : 'text'} step={item.type === 'float' ? 'any' : (item.type === 'int' ? '1' : undefined)} value={current} onChange={(e) => onChange(e.target.value)} disabled={disabled && item.plataforma} />
        )}
      </div>
      <Button size="sm" variant={dirty ? 'primary' : 'secondary'} onClick={onSave} disabled={!dirty || disabled}>
        {t('common.save')}
      </Button>
    </>
  )
}


// ── Integration credentials (Phase 2: encrypted per-org provider creds) ─────

export function IntegrationProviderEditor({ provider, label }: { provider: IntegrationProvider; label?: string }) {
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['integration', provider],
    queryFn: () => settingsApi.integrationProvider(provider).then(r => r.data),
  })
  const { mutate: save, isPending } = useMutation({
    mutationFn: ({ key, value }: { key: string; value: string }) => settingsApi.setIntegration(provider, key, value),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['integration', provider] })
      toast.success(t('i18n.saved'))
    },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const [testResult, setTestResult] = useState<IntegrationTestResult | null>(null)
  const { mutate: runTest, isPending: testing } = useMutation({
    mutationFn: () => settingsApi.testIntegration(provider).then(r => r.data),
    onSuccess: result => {
      setTestResult(result)
      // Incidencia 10 (23-11-2026): el resultado con código sale traducido.
      if (result?.ok) toast.success(textoDeResultado(t, result, t('settingsadvanced.conexion_ok')))
      else toast.error(textoDeResultado(t, result, t('settingsadvanced.conexion_fallo')))
    },
    onError: (e: unknown) => {
      setTestResult({ ok: false, detail: extractErr(e, GENERIC_ERROR_FALLBACK) })
      toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
    },
  })

  // Incidencia 10 (23-11-2026): nombre del campo traducido (`integraciones_prov.<proveedor>__<campo>`);
  // sin traducción, la etiqueta del registro del servidor.
  const etiquetaDeCampo = (campo: string, respaldo: string) => t(`integraciones_prov.${provider}__${campo}`, respaldo)

  // De dónde sale el valor, en palabras del administrador (antes "env", "org"...).
  const nombreDeOrigen = (origen?: string | null) =>
    origen && ['env', 'org', 'global', 'default'].includes(origen) ? t(`settingsadvanced.origen_${origen}`) : (origen ?? '—')

  const [draft, setDraft] = useState<Record<string, string>>({})
  useEffect(() => {
    if (data?.items) {
      const next: Record<string, string> = {}
      // Secrets never echo back — start as empty so admin types the new value.
      for (const it of data.items) next[it.key] = it.is_secret ? '' : (it.value == null ? '' : String(it.value))
      setDraft(next)
    }
  }, [data])

  if (isLoading) return <div className="seadse-box-28">{t('chat.loading')}</div>
  if (isError)   return <div className="seadse-box-29">{extractErr(error, GENERIC_ERROR_FALLBACK)}</div>

  const items = data?.items || []

  return (
    <form
      onSubmit={(e) => e.preventDefault()}
      autoComplete="off"
      className="u-stack-14"
    >
      <div className="seadse-row-6">
        <div className="u-text2-sm">
          {label}{t('settingsadvanced.valores_cifrados_en_reposo_resuelven_org_global')}
        </div>
        <Button variant="secondary" size="sm" icon={<Plug size={14} />} onClick={() => runTest()} loading={testing}>
          {testing ? t('settingsadvanced.probando') : t('settingsadvanced.probar_conexion')}
        </Button>
      </div>
      {testResult && (
        <div className={`seadse-box-37 settings-sx3 settings-advanced-sections-e1 seadse-con-icono ${testResult.ok ? 'settings-advanced-sections-m23' : 'settings-advanced-sections-m24'}`} role={testResult.ok ? 'status' : 'alert'} style={{ '--settings-advanced-sections-border': '1px solid ' + (testResult.ok ? 'var(--success-border)' : 'var(--danger-border)') } as CSSProperties}>
          {testResult.ok ? <CheckCircle2 size={15} aria-hidden /> : <XCircle size={15} aria-hidden />}
          <span><strong>{testResult.ok ? t('settingsadvanced.conexion_ok') : t('settingsadvanced.conexion_fallo')}</strong>{textoDeResultado(t, testResult) ? ` — ${textoDeResultado(t, testResult)}` : ''}</span>
        </div>
      )}
      <div className="seadse-grid-6">
        {items.map(it => {
          const current = draft[it.key] ?? ''
          const dirty = it.is_secret ? (current !== '') : (String(it.value ?? '') !== String(current))
          return (
            <Fragment key={it.key}>
              <div className="seadse-stack-2">
                <span className="u-text1-sm-600">{etiquetaDeCampo(it.key, it.label)}</span>
                <span className="seadse-txt-2">
                  {it.is_secret ? `${t('settingsadvanced.secreto')} ` : ''}{t('settingsadvanced.origen')} {nombreDeOrigen(it.source)}
                </span>
              </div>
              <div>
                {provider === 'sd_mailbox' && it.key === 'protocol' ? (
                  <Select suelto aria-label={etiquetaDeCampo(it.key, it.label)} value={current} onChange={(e) => setDraft({ ...draft, [it.key]: e.target.value })}>
                    <option value="">{t('integraciones_prov.elegir')}</option>
                    <option value="imap">{t('integraciones_prov.sd_mailbox_imap')}</option>
                    <option value="graph">{t('integraciones_prov.sd_mailbox_graph')}</option>
                  </Select>
                ) : (
                <Input aria-label={etiquetaDeCampo(it.key, it.label)} type={it.is_secret ? 'password' : (it.type === 'int' ? 'number' : 'text')} step={it.type === 'int' ? '1' : undefined} value={current} placeholder={it.is_secret && it.configured ? t('settingsadvanced.ya_configurado') : ''} onChange={(e) => setDraft({ ...draft, [it.key]: e.target.value })} />
                )}
              </div>
              <Button size="sm" variant={dirty ? 'primary' : 'secondary'} onClick={() => save({ key: it.key, value: current })} disabled={!dirty || isPending}>
                {t('common.save')}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => save({ key: it.key, value: '' })} disabled={isPending || (!it.configured)}
                title={it.configured ? t('settingsadvanced.borrar_valor_titulo') : t('settingsadvanced.no_configurado')}>
                {t('pol.borrar')}
              </Button>
            </Fragment>
          )
        })}
      </div>
    </form>
  )
}


export function IntegrationCredentialsSection({ subInicial }: { subInicial?: string } = {}) {
  const { t } = useAppLang()
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['integration-providers'],
    queryFn: () => settingsApi.integrations().then(r => r.data),
  })
  // useMemo (auditoría 2026-08, P1-6): con `?? []` / `|| []` esto creaba un
  // array nuevo en cada render, así que los useMemo/useEffect que lo tienen
  // como dependencia se reejecutaban SIEMPRE — no memoizaban nada.
  const providers = useMemo(() => data?.providers || [], [data?.providers])
  const [active, setActive] = useState<IntegrationProvider | null>(null)
  useEffect(() => {
    // Incidencia 8 (23-11-2026): `?sub=<proveedor>` abre ese proveedor (el botón
    // «Credenciales» del buzón del Service Desk llevaba siempre al primero, SMTP).
    if (!active && providers.length) {
      const pedido = providers.find(p => p.provider === subInicial)
      setActive((pedido ?? providers[0]).provider)
    }
  }, [providers, active, subInicial])

  if (isLoading) return <SeccionDeAjustes icon={<Lock size={18} />} title={t('settingsadvanced.credenciales_de_integracion')}><div className="seadse-box-28">{t('chat.loading')}</div></SeccionDeAjustes>
  if (isError)   return <SeccionDeAjustes icon={<Lock size={18} />} title={t('settingsadvanced.credenciales_de_integracion')}><div className="seadse-box-29">{extractErr(error, GENERIC_ERROR_FALLBACK)}</div></SeccionDeAjustes>

  const currentProvider = providers.find(p => p.provider === active)

  return (
    <SeccionDeAjustes
      icon={<Lock size={18} />}
      title={t('settingsadvanced.credenciales_de_integracion')}
      description={t('settingsadvanced.smtp_aws_s3_microsoft_graph_slack_stripe')}
    >
      <EstadoDeConectores />
      <Tabs
        className="seadse-pestanas"
        ariaLabel={t('settingsadvanced.credenciales_de_integracion')}
        items={providers.map(p => ({ id: p.provider, label: t(`integraciones_prov.${p.provider}`, p.label) }))}
        active={active ?? undefined}
        onChange={id => setActive(id as IntegrationProvider)}
      />
      {active && currentProvider && (
        <IntegrationProviderEditor key={active} provider={active} label={t(`integraciones_prov.${active}`, currentProvider.label)} />
      )}
    </SeccionDeAjustes>
  )
}


export function RuntimeFlagsSection() {
  const { t } = useAppLang()
  const [active, setActive] = useState(RUNTIME_GROUPS[0].id)
  const current = RUNTIME_GROUPS.find(g => g.id === active) || RUNTIME_GROUPS[0]
  return (
    <SeccionDeAjustes icon={<Settings2 size={18} />} title={t('settingsadvanced.configuracion_dinamica')} description={t('settingsadvanced.knobs_operativos_editables_sin_redeploy_resuelven_org')}>
      <Tabs
        className="seadse-pestanas"
        ariaLabel={t('settingsadvanced.configuracion_dinamica')}
        items={RUNTIME_GROUPS.map(g => ({ id: g.id, label: t(`settingsadvanced.rt_${g.id}`, g.label) }))}
        active={active}
        onChange={setActive}
      />
      <p className="u-text2-sm">{t('ajustes.runtime_en_otro_sitio')}</p>
      <RuntimeGroupEditor key={active} groupId={active} ocultar={OCULTAS_POR_GRUPO[active]} description={t(`settingsadvanced.rt_${current.id}_desc`, current.description)} />
    </SeccionDeAjustes>
  )
}

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
import type { CSSProperties, ChangeEvent } from 'react'
import { Fragment, useState, useEffect, useMemo } from 'react'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAppLang } from '../../i18n/AppLangContext'
import { APP_LANGUAGES, AVAILABLE_LANGUAGES, loadLanguage, getAllKeys, es } from '../../i18n/appTranslations.ts'
import { PORTAL_TRANSLATIONS, PORTAL_LANGUAGES, getPortalKeys } from '../../i18n/portalTranslations'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import SeccionDeAjustes from './SeccionDeAjustes'
import { portalClientsApi, settingsApi, type IntegrationProvider, type IntegrationTestResult, type LogLevel, type RuntimeSetting } from '../../services/api'
import { settingsApi as ajustesGeneralesApi, type SettingOut } from '../../services/settingsApi'
import type { PortalDictionary } from '../../i18n/portalTranslations'
import { alpha } from '../../constants/theme'
import { Button, Pulsable, Select, Tabs } from '../../components/ui'
import { AlertTriangle, BarChart3, Bot, Check, CheckCircle2, Download, FileText, Globe, Languages, Lock, MonitorSmartphone, Package, Phone, Plug, Save, Server, Settings2, ShieldAlert, Wrench, XCircle, Zap } from 'lucide-react'
import './SettingsAdvancedSections.css'

/** Textos por módulo y clave: `{módulo: {clave: texto}}`. */
// 16-11-2026: los diccionarios pueden anidar (`almint.criterio.todos`); la
// clave de una fila es la ruta dentro del módulo («criterio.todos»). Antes se
// suponían dos niveles y un texto anidado se pintaba como objeto: la pantalla
// entera caía («Objects are not valid as a React child»).
type TextosPorModulo = Record<string, Record<string, unknown>>

/** Texto en la ruta «a.b.c» dentro de un módulo, o `undefined` si no es texto. */
function leerRuta(obj: unknown, ruta: string): string | undefined {
  let v: unknown = obj
  for (const p of ruta.split('.')) {
    if (v && typeof v === 'object') v = (v as Record<string, unknown>)[p]
    else return undefined
  }
  return typeof v === 'string' ? v : undefined
}

/** Copia de `obj` con `val` en la ruta «a.b.c» (crea los niveles que falten). */
function ponerRuta(obj: Record<string, unknown> | undefined, ruta: string, val: string): Record<string, unknown> {
  const [cabeza, ...resto] = ruta.split('.')
  const copia: Record<string, unknown> = { ...(obj || {}) }
  copia[cabeza] = resto.length
    ? ponerRuta(copia[cabeza] && typeof copia[cabeza] === 'object' ? copia[cabeza] as Record<string, unknown> : undefined, resto.join('.'), val)
    : val
  return copia
}
/** Ediciones del portal por clave e idioma: `{clave: {idioma: texto}}`. */
type EdicionesPortal = Record<string, Record<string, string>>
type ClaveDeTraduccion = { module: string; key: string; full_key: string; base_es: string }
const TEXTOS_PORTAL = PORTAL_TRANSLATIONS as Record<string, PortalDictionary>

function descargarJSON(nombre: string, datos: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(datos, null, 2)], { type: 'application/json' }))
  const a = document.createElement('a'); a.href = url; a.download = nombre; a.click()
  URL.revokeObjectURL(url)
}

export function IdiomasSection() {
  const toast = useToast()
  const qc = useQueryClient()
  const { lang: operatorLang, setLang: setOperatorLang, t, setCustomTranslations, customTrans } = useAppLang()

  const { data: portalTrans = {} } = useQuery<Record<string, Record<string, string>>>({
    queryKey: ['portal-translations'],
    queryFn: () => portalClientsApi.translations().then(r => r.data).catch(() => ({})),
  })
  const { mutate: savePortalTrans, isPending: savingPortal } = useMutation({
    mutationFn: (d: Record<string, Record<string, string>>) => portalClientsApi.saveTranslations(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['portal-translations'] }); toast.success(t('i18n.saved_ok')) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const [activeTab, setActiveTab] = useState('operator')
  const [appLang, setAppLang] = useState('en')
  const [appTranslations, setAppTranslations] = useState<TextosPorModulo>({})
  const [loadingAppLang, setLoadingAppLang] = useState(true)
  const [portalLang, setPortalLang] = useState('en')
  const [searchKey, setSearchKey] = useState('')
  const [activeModule, setActiveModule] = useState('all')
  const [appEdits, setAppEdits] = useState<TextosPorModulo>({})
  const [portalEdits, setPortalEdits] = useState<EdicionesPortal>({})
  const [portalSearch, setPortalSearch] = useState('')
  const [hasUnsaved, setHasUnsaved] = useState(false)

  const allKeys: ClaveDeTraduccion[] = getAllKeys(es)
  const modules = ['all', ...new Set(allKeys.map(k => k.module))]

  useEffect(() => {
    let cancelled = false
    setLoadingAppLang(true)
    loadLanguage(appLang).then((tr) => {
      if (!cancelled) {
        // Los diccionarios son de texto; el tipo general admite anidamiento.
        setAppTranslations(tr as TextosPorModulo)
        setLoadingAppLang(false)
      }
    })
    return () => { cancelled = true }
  }, [appLang])

  const filteredKeys = allKeys.filter(k => {
    const matchMod = activeModule === 'all' || k.module === activeModule
    const matchSrc = !searchKey || k.key.includes(searchKey.toLowerCase()) ||
      k.base_es.toLowerCase().includes(searchKey.toLowerCase()) ||
      k.full_key.includes(searchKey.toLowerCase())
    return matchMod && matchSrc
  })

  const getAppVal = (lang: string, module: string, key: string) =>
    (lang === appLang ? (
      leerRuta(appEdits?.[module], key) ??
      leerRuta((customTrans as Record<string, TextosPorModulo>)?.[lang]?.[module], key) ??
      leerRuta(appTranslations?.[module], key)
    ) : '') ?? ''

  const setAppVal = (lang: string, module: string, key: string, val: string) => {
    if (lang !== appLang) return
    setAppEdits(prev => ({
      ...prev,
      [module]: ponerRuta(prev[module], key, val)
    }))
    setHasUnsaved(true)
  }

  const importJSON = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (ev) => {
      try {
        const data = JSON.parse(String(ev.target?.result ?? ''))
        if (typeof data !== 'object' || !data[appLang]) {
          toast.error(t('settingsadvanced.el_json_no_contiene_traducciones_para_el'))
          return
        }
        setAppEdits(data[appLang])
        setHasUnsaved(true)
        toast.success(t('settingsadvanced.traducciones_importadas_revisa_y_guarda_para_aplicar'))
      } catch {
        toast.error(t('settingsadvanced.error_al_leer_el_archivo_json'))
      }
    }
    reader.readAsText(file)
  }

  // Revisión 2026-11: se guardan en el servidor, para toda la empresa. Antes
  // solo en el localStorage de este navegador: nadie más las veía.
  const { mutate: saveAppTrans } = useMutation({
    mutationFn: () => settingsApi.saveAppTranslations({ [appLang]: appEdits }).then(r => r.data),
    onSuccess: todas => {
      setCustomTranslations(todas || {})
      qc.setQueryData(['app-translations'], todas || {})
      setAppEdits({})
      setHasUnsaved(false)
      toast.success(t('i18n.saved_ok'))
    },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  // Revisión 2026-11: exporta el MISMO formato que acepta «Importar JSON»
  // ({idioma: {módulo: {clave: texto}}}), con todas las claves y los textos
  // actuales; antes exportaba {módulo: …} y al reimportarlo daba error.
  const exportJSON = () => {
    const modelo: TextosPorModulo = {}
    for (const k of allKeys) {
      modelo[k.module] = ponerRuta(modelo[k.module], k.key, String(getAppVal(appLang, k.module, k.key) ?? ''))
    }
    descargarJSON(`contecflow_translations_${appLang}.json`, { [appLang]: modelo })
  }

  // Igual para el portal: {idioma: {clave: texto}}, con lo personalizado.
  const exportPortalJSON = () => {
    const modelo: Record<string, string> = {}
    for (const { key } of getPortalKeys()) {
      modelo[key] = String(portalEdits[key]?.[portalLang] ?? portalTrans[portalLang]?.[key]
        ?? TEXTOS_PORTAL[portalLang]?.[key] ?? '')
    }
    descargarJSON(`portal_translations_${portalLang}.json`, { [portalLang]: modelo })
  }


  if (loadingAppLang) return <div>{t('settingsadvanced.cargando_traducciones')}</div>

  return (
    <div className="u-stack-20">
      <Tabs
        ariaLabel={t('settingsadvanced.secciones_idiomas')}
        items={[
          { id: 'operator', label: t('settingsadvanced.tab_operador'), icon: <Languages size={14} /> },
          { id: 'app', label: t('settingsadvanced.tab_backoffice'), icon: <MonitorSmartphone size={14} /> },
          { id: 'portal', label: t('settingsadvanced.tab_portal'), icon: <Globe size={14} /> },
        ]}
        active={activeTab}
        onChange={setActiveTab}
      />

      {activeTab === 'operator' && (
        <div className="seadse-card">
          <div className="seadse-box-1">
            <div className="seadse-box-2">{t('settingsadvanced.idioma_del_operador_back_office')}</div>
            <div className="u-text2-sm">
              {t('settingsadvanced.idioma_de_la_interfaz_interna_cada_usuario')}
            </div>
          </div>
          <div className="seadse-sp-1">
            <div className="u-wrap-10">
              {/* Operator-facing picker: only well-covered locales (pl/zh hidden). */}
              {AVAILABLE_LANGUAGES.map(l => (
                <Pulsable className={`seadse-box-31 settings-sx2 settings-advanced-sections-e1 ${operatorLang === l.code ? 'settings-advanced-sections-m2' : 'settings-advanced-sections-m4'}`} key={l.code} onClick={() => setOperatorLang(l.code)} style={{ '--settings-advanced-sections-border': `2px solid ${operatorLang === l.code ? 'var(--accent)' : 'var(--surface-4)'}` } as CSSProperties}>
                  {l.label}
                  {operatorLang === l.code && <span className="seadse-box-3"><Check size={14} aria-hidden /></span>}
                </Pulsable>
              ))}
            </div>
            <div className="seadse-box-4">
              {t('settingsadvanced.al_cambiar_el_idioma_los_menus_titulos')}
            </div>
          </div>
        </div>
      )}

      {activeTab === 'app' && (
        <div>
          <div className="seadse-row-2">
            <div>
              <div className="u-text2-xs-mb4">{t('settingsadvanced.idioma_a_editar')}</div>
              <div className="u-row-6">
                {APP_LANGUAGES.filter(l => l.code !== 'es').map(l => (
                  <Pulsable className={`seadse-box-30 settings-sx1 settings-advanced-sections-e1 ${appLang === l.code ? 'settings-advanced-sections-m2' : 'settings-advanced-sections-m3'}`} key={l.code} onClick={() => setAppLang(l.code)} style={{ '--settings-advanced-sections-border': `1px solid ${appLang === l.code ? 'var(--accent)' : 'var(--surface-4)'}` } as CSSProperties}>
                    {l.label}
                  </Pulsable>
                ))}
              </div>
            </div>
            <div className="u-flex1">
              <div className="u-text2-xs-mb4">{t('settingsadvanced.buscar_clave')}</div>
              <input value={searchKey} onChange={e => setSearchKey(e.target.value)}
                placeholder={t('settingsadvanced.buscar_clave_de_traduccion')} aria-label={t('settingsadvanced.buscar_clave_de_traduccion')} className="ds-input seadse-fs" />
            </div>
            <div>
              <div className="u-text2-xs-mb4">{t('settingsadvanced.modulo')}</div>
              <Select suelto placeholder={false} value={activeModule} onChange={e => setActiveModule(e.target.value)} aria-label={t('settingsadvanced.modulo')} className="seadse-fs2">
                {modules.map(m => <option key={m} value={m}>{m === 'all' ? t('settingsadvanced.todos_los_modulos') : m}</option>)}
              </Select>
            </div>
            <div>
              <div className="u-text2-xs-mb4">{t('settingsadvanced.importar_json')}</div>
              <label className="seadse-box-5">
                {t('settingsadvanced.importar_json_2')}
                <input type="file" accept="application/json" aria-label={t('i18n.import_json')} className="seadse-box-6" onChange={importJSON} />
              </label>
            </div>
            <div>
              <div className="u-text2-xs-mb4">{t('settingsadvanced.exportar_json')}</div>
              <Button variant="secondary" icon={<Download size={14} />} onClick={exportJSON}>
                {t('settingsadvanced.exportar_json_2')}
              </Button>
            </div>
          </div>

          <div className="seadse-grid-1">
            <span>{t('settingsadvanced.col_modulo_clave')}</span>
            <span>{t('settingsadvanced.espanol_base')}</span>
            <span>{APP_LANGUAGES.find(l => l.code === appLang)?.label}</span>
          </div>
          <div className="seadse-box-8">
            {filteredKeys.slice(0, 200).map((item, idx) => {
              const currentVal = getAppVal(appLang, item.module, item.key)
              const isModified = leerRuta(appEdits[item.module], item.key) !== undefined
              return (
                <div className={`seadse-grid-7 ${idx % 2 === 0 ? 'settings-advanced-sections-m5' : 'settings-advanced-sections-m6'}`} key={item.full_key}>
                  <div>
                    <span className="seadse-box-9">{item.module}</span>
                    <span className={`ds-codigo seadse-txt-3 ${isModified ? 'settings-advanced-sections-m7' : 'settings-advanced-sections-m8'}`}>{item.key}</span>
                  </div>
                  <div className="seadse-box-10">
                    {item.base_es}
                  </div>
                  <input className={`seadse-fs3 ${isModified ? 'settings-advanced-sections-m9' : 'settings-advanced-sections-m10'}`}
                    aria-label={item.full_key}
                    value={currentVal}
                    onChange={e => setAppVal(appLang, item.module, item.key, e.target.value)}
                    placeholder={item.base_es}
                  />
                </div>
              )
            })}
            {filteredKeys.length > 200 && (
              <div className="seadse-box-11">
                {t('settingsadvanced.mostrando_200_de_n', { n: filteredKeys.length })}
              </div>
            )}
          </div>

          <div className="seadse-row-3">
            <div className="u-text2-sm">
              {t('settingsadvanced.claves_de_total', { n: filteredKeys.length, total: allKeys.length })}{hasUnsaved && <> · <span className="u-warning">{t('settingsadvanced.cambios_sin_guardar')}</span></>}
            </div>
            <div className="u-row-8">
              <Button icon={<Save size={14} />} onClick={() => saveAppTrans()} disabled={!hasUnsaved}>
                {t('settingsadvanced.guardar_traduccion')}
              </Button>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'portal' && (
        <div>
          <div className="seadse-row-2">
            <div>
              <div className="u-text2-xs-mb4">{t('settingsadvanced.idioma_a_editar')}</div>
              <div className="u-row-6">
                {PORTAL_LANGUAGES.filter(l => l.code !== 'es').map(l => (
                  <Pulsable className={`seadse-box-30 settings-sx1 settings-advanced-sections-e1 ${portalLang === l.code ? 'settings-advanced-sections-m2' : 'settings-advanced-sections-m3'}`} key={l.code} onClick={() => setPortalLang(l.code)} style={{ '--settings-advanced-sections-border': `1px solid ${portalLang === l.code ? 'var(--accent)' : 'var(--surface-4)'}` } as CSSProperties}>
                    <span className="u-text3-xs">{l.code.toUpperCase()}</span> {l.label}
                  </Pulsable>
                ))}
              </div>
            </div>
            <div>
              <div className="u-text2-xs-mb4">{t('settingsadvanced.buscar')}</div>
              <input value={portalSearch} onChange={e => setPortalSearch(e.target.value)}
                placeholder={t('settingsadvanced.buscar_texto_del_portal')} aria-label={t('settingsadvanced.buscar_texto_del_portal')} className="ds-input seadse-fs4" />
            </div>
            <div>
              <div className="u-text2-xs-mb4">{t('settingsadvanced.importar_json')}</div>
              <label className="seadse-box-5">
                {t('settingsadvanced.importar_json_2')}
                <input type="file" accept="application/json" aria-label={t('i18n.import_json')} className="seadse-box-6" onChange={e => {
                  const file = e.target.files?.[0]
                  if (!file) return
                  const reader = new FileReader()
                  reader.onload = evt => {
                    try {
                      const data = JSON.parse(String(evt.target?.result ?? ''))
                      setPortalEdits(prev => {
                        const merged: EdicionesPortal = { ...prev }
                        for (const [lang, keys] of Object.entries(data as Record<string, Record<string, string>>)) {
                          for (const [key, value] of Object.entries(keys)) {
                            if (!merged[key]) merged[key] = {}
                            merged[key][lang] = value
                          }
                        }
                        return merged
                      })
                      setHasUnsaved(true)
                      toast.success(t('settingsadvanced.traducciones_importadas_revisa_y_guarda_para_aplicar'))
                    } catch {
                      toast.error(t('settingsadvanced.error_al_leer_el_archivo_json'))
                    }
                  }
                  reader.readAsText(file)
                }} />
              </label>
            </div>
            <div>
              <div className="u-text2-xs-mb4">{t('settingsadvanced.exportar_json')}</div>
              <Button variant="secondary" icon={<Download size={14} />} onClick={exportPortalJSON}>
                {t('settingsadvanced.exportar_json_2')}
              </Button>
            </div>
          </div>

          <div className="seadse-grid-2">
            <span>{t('settingsadvanced.col_clave')}</span>
            <span>{t('settingsadvanced.espanol_base')}</span>
            <span>{portalLang.toUpperCase()} · {PORTAL_LANGUAGES.find(l => l.code === portalLang)?.label}</span>
          </div>
          <div className="seadse-box-8">
            {getPortalKeys()
              .filter(({ key, base_es }) => !portalSearch ||
                key.includes(portalSearch.toLowerCase()) ||
                base_es.toLowerCase().includes(portalSearch.toLowerCase()))
              .map(({ key, base_es }, idx) => {
                const currentVal = portalEdits[key]?.[portalLang]
                  ?? portalTrans[portalLang]?.[key]
                  ?? TEXTOS_PORTAL[portalLang]?.[key] ?? ''
                const isModified = portalEdits[key]?.[portalLang] !== undefined
                return (
                  <div className={`seadse-grid-8 ${idx % 2 === 0 ? 'settings-advanced-sections-m5' : 'settings-advanced-sections-m6'}`} key={key}>
                    <span className={`ds-codigo seadse-txt-3 ${isModified ? 'settings-advanced-sections-m7' : 'settings-advanced-sections-m8'}`}>{key}</span>
                    <span className="seadse-box-10">{base_es}</span>
                    <input className={`seadse-fs3 ${isModified ? 'settings-advanced-sections-m9' : 'settings-advanced-sections-m10'}`}
                      aria-label={key}
                      value={currentVal}
                      onChange={e => {
                        setPortalEdits(prev => ({ ...prev, [key]: { ...(prev[key] || {}), [portalLang]: e.target.value } }))
                        setHasUnsaved(true)
                      }}
                      placeholder={base_es}
                    />
                  </div>
                )
              })}
          </div>

          <div className="seadse-row-3">
            <div className="u-text2-sm">
              {getPortalKeys().length} {t('settingsadvanced.claves_8_idiomas')}
              {hasUnsaved && <span className="seadse-box-12">{t('settingsadvanced.cambios_sin_guardar')}</span>}
            </div>
            <div className="u-row-8">
              <Button icon={<Save size={14} />} loading={savingPortal} onClick={() => {
                // Solo lo editado: el servidor lo fusiona por clave (vacío = quitar).
                const cambios: Record<string, Record<string, string>> = {}
                for (const [key, langs] of Object.entries(portalEdits)) {
                  for (const [lang, val] of Object.entries(langs)) {
                    if (!cambios[lang]) cambios[lang] = {}
                    cambios[lang][key] = val
                  }
                }
                savePortalTrans(cambios)
                setPortalEdits({})
                setHasUnsaved(false)
              }} disabled={!hasUnsaved}>
                {savingPortal ? t('settingsadvanced.guardando') : t('settingsadvanced.guardar_traducciones')}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

type VentanaConLogger = Window & { __contecflowLogger?: { setLevel: (level: string) => void } }

export function LogLevelSection() {
  const { t } = useAppLang()
  const toast = useToast()
  const [backendLevel, setBackendLevel] = useState('')
  const [frontendLevel, setFrontendLevel] = useState(
    localStorage.getItem('contecflow_log_level') || (import.meta.env.DEV ? 'debug' : 'warn')
  )
  const qc = useQueryClient()

  const { data: serverLevel, isLoading } = useQuery({
    queryKey: ['log-level'],
    queryFn: () => settingsApi.logLevel().then(r => r.data),
  })

  useEffect(() => {
    if (serverLevel?.contecflow) {
      setBackendLevel(String(serverLevel.contecflow).toUpperCase())
    }
  }, [serverLevel])

  const handleSetBackend = async (level = backendLevel) => {
    if (!level) return
    try {
      const lvl = String(level).toUpperCase()
      setBackendLevel(lvl)
      await settingsApi.setLogLevel({ level: lvl as LogLevel })
      toast.success(t('settingsadvanced.nivel_backend_cambiado_a_lvl', { lvl }))
      qc.invalidateQueries({ queryKey: ['log-level'] })
    } catch {
      toast.error(t('settingsadvanced.error_al_cambiar_nivel_de_log'))
    }
  }

  const handleSetFrontend = (level: string) => {
    setFrontendLevel(level)
    localStorage.setItem('contecflow_log_level', level)
    const logger = (window as VentanaConLogger).__contecflowLogger
    if (logger) logger.setLevel(level)
    toast.success(t('settingsadvanced.nivel_frontend_cambiado_a_level_activo_hasta', { level: level.toUpperCase() }))
  }

  const LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
  const LEVEL_COLORS: Record<string, string> = { DEBUG: 'var(--text-2)', INFO: 'var(--accent)', WARNING: 'var(--warning)', ERROR: 'var(--danger)', CRITICAL: 'var(--danger)' }

  return (
    <SeccionDeAjustes icon={<FileText size={18} />} title={t('settingsadvanced.nivel_de_log')} description={t('settingsadvanced.controla_la_verbosidad_del_backend_y_frontend')}>
      <div className="seadse-grid-3">
        <div className="seadse-box-13">
          <div className="seadse-box-14 seadse-con-icono"><Server size={15} aria-hidden />{t('settingsadvanced.servidor_fastapi_uvicorn')}</div>
          <div className="seadse-box-15">
            {t('settingsadvanced.cambia_el_nivel_en_tiempo_real_sin')}
          </div>
          {!isLoading && serverLevel && (
            <div className="seadse-box-17">
              {t('settingsadvanced.nivel_actual')} <strong>{serverLevel.contecflow}</strong>
            </div>
          )}
          <div className="u-wrap-8">
            {LEVELS.map(l => (
              <Pulsable className="seadse-box-33 settings-sx3 settings-advanced-sections-e13" key={l} onClick={() => handleSetBackend(l)} style={{ '--settings-advanced-sections-border': `1px solid ${backendLevel === l ? LEVEL_COLORS[l] : 'var(--surface-4)'}`, '--settings-advanced-sections-background': backendLevel === l ? (alpha(LEVEL_COLORS[l], '22')) : 'var(--surface-3)', '--settings-advanced-sections-color': backendLevel === l ? LEVEL_COLORS[l] : 'var(--text-2)' } as CSSProperties}>
                {l}
              </Pulsable>
            ))}
          </div>
        </div>

        <div className="seadse-box-13">
          <div className="seadse-box-14 seadse-con-icono"><MonitorSmartphone size={15} aria-hidden />{t('settingsadvanced.navegador_react_vite')}</div>
          <div className="seadse-box-15">
            {t('settingsadvanced.controla_la_consola_del_navegador_se_guarda')}
          </div>
          <div className="seadse-box-17">
            {t('settingsadvanced.nivel_actual')} <strong>{frontendLevel.toUpperCase()}</strong>
          </div>
          <div className="u-wrap-8">
            {['DEBUG', 'INFO', 'WARN', 'ERROR', 'SILENT'].map(l => (
              <Pulsable className="seadse-box-33 settings-sx3 settings-advanced-sections-e13" key={l} onClick={() => handleSetFrontend(l.toLowerCase())} style={{ '--settings-advanced-sections-border': `1px solid ${frontendLevel.toUpperCase() === l ? (LEVEL_COLORS[l] || LEVEL_COLORS['ERROR']) : 'var(--surface-4)'}`, '--settings-advanced-sections-background': frontendLevel.toUpperCase() === l ? (alpha((LEVEL_COLORS[l] || LEVEL_COLORS['ERROR']), '22')) : 'var(--surface-3)', '--settings-advanced-sections-color': frontendLevel.toUpperCase() === l ? (LEVEL_COLORS[l] || LEVEL_COLORS['ERROR']) : 'var(--text-2)' } as CSSProperties}>
                {l}
              </Pulsable>
            ))}
          </div>
        </div>
      </div>
    </SeccionDeAjustes>
  )
}

// ── Estado del sistema (admin debug) ──────────────────────────────────────────

// `label` es el identificador del grupo; el texto visible sale de `settingsadvanced.<label>`.
const SYSTEM_KEY_GROUPS = [
  { label: 'sys_bi',   icon: <BarChart3 size={15} />, prefixes: ['bi.phase', 'bi.smart_alerts', 'bi.governance', 'bi.collaboration', 'bi.platform'] },
  { label: 'sys_etl',  icon: <Plug size={15} />,      prefixes: ['bi.etl', 'bi.o365', 'bi.intelligence'] },
  { label: 'sys_voz',  icon: <Phone size={15} />,     prefixes: ['sd.voice'] },
  { label: 'sys_ml',   icon: <Bot size={15} />,       prefixes: ['sd.ml_', 'sd.feedback', 'sd.auto_resolution', 'sd.assignment'] },
  { label: 'sys_sd',   icon: <Wrench size={15} />,    prefixes: ['sd.'] },
  { label: 'sys_olap', icon: <Zap size={15} />,       prefixes: ['olap.', 'cache_'] },
]

const isInternalKey = (key: string | null | undefined) => {
  if (!key) return false
  const k = String(key).toLowerCase()
  if (k.includes('.')) return true
  if (k.startsWith('bi_') || k.startsWith('sd_') || k.startsWith('ml_')) return true
  if (k.startsWith('_') || k.startsWith('cache_') || k.startsWith('feedback_')) return true
  return false
}

const groupForKey = (key: string) => {
  const k = String(key).toLowerCase()
  for (const g of SYSTEM_KEY_GROUPS) {
    if (g.prefixes.some(p => k.startsWith(p))) return g.label
  }
  return 'grupo_otros'
}

/** Fila de `/settings/general`; el ámbito y la fecha solo llegan si el backend los añade. */
type FilaAjuste = SettingOut & { organization_id?: string | null; organizationId?: string | null; updated_at?: string | null }

const dedupeSettingsByKey = (rows: FilaAjuste[]) => {
  const byKey = new Map<string, FilaAjuste>()
  for (const row of rows || []) {
    const key = String(row?.key || '')
    if (!key) continue
    const current = byKey.get(key)
    if (!current) {
      byKey.set(key, row)
      continue
    }

    const currentOrg = current.organization_id ?? current.organizationId ?? null
    const nextOrg = row.organization_id ?? row.organizationId ?? null
    if (!currentOrg && nextOrg) {
      byKey.set(key, row)
      continue
    }

    const currentUpdated = String(current.updated_at || '')
    const nextUpdated = String(row.updated_at || '')
    if (nextUpdated > currentUpdated) {
      byKey.set(key, row)
    }
  }
  return Array.from(byKey.values())
}

function tryFormatValue(raw: unknown): string | null {
  if (raw == null || raw === '') return null
  if (typeof raw === 'object') {
    try { return JSON.stringify(raw, null, 2) } catch { return String(raw) }
  }
  if (typeof raw !== 'string') return String(raw)
  const trimmed = raw.trim()
  if ((trimmed.startsWith('{') && trimmed.endsWith('}')) || (trimmed.startsWith('[') && trimmed.endsWith(']'))) {
    try {
      return JSON.stringify(JSON.parse(trimmed), null, 2)
    } catch {
      return raw
    }
  }
  return raw
}

function SystemSettingItem({ setting }: { setting: FilaAjuste }) {
  const { t } = useAppLang()
  const [expanded, setExpanded] = useState(false)
  const formatted = tryFormatValue(setting.value)
  const isJson = formatted && (formatted.startsWith('{') || formatted.startsWith('['))
  const lineCount = formatted ? formatted.split('\n').length : 0
  const preview = formatted
    ? formatted.split('\n').slice(0, 3).join('\n') + (lineCount > 3 ? '\n…' : '')
    : '—'

  return (
    <div className="seadse-box-19">
      <div className="seadse-row-4">
        <code className="ds-codigo seadse-box-20">{setting.key}</code>
        <Pulsable onClick={() => setExpanded(v => !v)} className="seadse-box-21">{expanded ? t('settingsadvanced.ocultar') : t('settingsadvanced.ver_completo')}</Pulsable>
      </div>
      {setting.description && (
        <div className="seadse-box-22">
          {setting.description}
        </div>
      )}
      <pre className={`ds-codigo ds-codigo--bloque settings-advanced-sections-e14 ${expanded ? 'settings-advanced-sections-m15' : 'settings-advanced-sections-m16'}`}>{expanded ? (formatted || '—') : preview}</pre>
      <div className="seadse-box-23">
        {isJson ? t('settingsadvanced.n_lineas_json', { n: lineCount }) : t('settingsadvanced.n_caracteres', { n: (setting.value || '').length })}
      </div>
    </div>
  )
}

// Revisión 2026-11: se mide el rol con el que conecta la aplicación, no solo
// que haya políticas: con un superusuario las políticas existen y no actúan.
function AislamientoEnLaBase() {
  const { t } = useAppLang()
  const { data } = useQuery<{ armed: boolean; role?: string; tables_with_rls?: number; tables_expected?: number; reason?: string | null }>({
    queryKey: ['db-isolation'],
    queryFn: () => settingsApi.dbIsolation().then(r => r.data),
  })
  if (!data) return null
  const color = data.armed ? 'var(--success)' : 'var(--warning)'
  return (
    <div className="seadse-box-34 settings-sx2 settings-advanced-sections-e17" role={data.armed ? undefined : 'alert'} style={{ '--settings-advanced-sections-background': `color-mix(in srgb, ${color} 8%, var(--surface-3))`, '--settings-advanced-sections-border': `1px solid color-mix(in srgb, ${color} 30%, var(--surface-4))` } as CSSProperties}>
      <strong className="settings-advanced-sections-e18" style={{ '--settings-advanced-sections-color': color } as CSSProperties}>{data.armed ? <Lock size={14} aria-hidden /> : <ShieldAlert size={14} aria-hidden />} {data.armed ? t('settingsadvanced.rls_armado') : t('settingsadvanced.rls_desarmado')}</strong>
      <div className="seadse-box-24">
        {t('settingsadvanced.rls_detalle', { rol: data.role ?? '—', n: data.tables_with_rls ?? 0, total: data.tables_expected ?? 0 })}
        {data.reason ? ` · ${data.reason}` : ''}
      </div>
    </div>
  )
}

export function SystemStateSection() {
  const { t } = useAppLang()
  const { data: settings = [], isLoading } = useQuery<FilaAjuste[]>({
    queryKey: ['settings-general'],
    queryFn: () => ajustesGeneralesApi.getGeneral().then(r => r.data),
  })

  const internal = dedupeSettingsByKey((settings || []).filter(s => isInternalKey(s.key)))
  // Agrupar por grupo lógico
  const grouped: Record<string, FilaAjuste[]> = {}
  for (const s of internal) {
    const label = groupForKey(s.key)
    if (!grouped[label]) grouped[label] = []
    grouped[label].push(s)
  }
  const orderedGroups = SYSTEM_KEY_GROUPS.map(g => g.label).filter(l => grouped[l]?.length)
  if (grouped['grupo_otros']?.length) orderedGroups.push('grupo_otros')
  const groupMeta = Object.fromEntries(SYSTEM_KEY_GROUPS.map(g => [g.label, g]))

  return (
    <SeccionDeAjustes icon={<Wrench size={18} />} title={t('settingsadvanced.estado_del_sistema')} description={t('settingsadvanced.lectura_del_estado_interno_persistido_por_servicios')}>
      <AislamientoEnLaBase />
      {isLoading ? (
        <div className="u-text3-sm">{t('chat.loading')}</div>
      ) : internal.length === 0 ? (
        <div className="seadse-box-25">
          {t('settingsadvanced.sin_estado_interno_registrado')}
        </div>
      ) : (
        <div className="seadse-stack-1">
          <div className="seadse-box-26">
            <strong className="u-warning seadse-con-icono"><AlertTriangle size={14} aria-hidden />{t('settingsadvanced.vista_de_solo_lectura')}</strong>{' '}
            {t('settingsadvanced.estos_blobs_son_estado_interno_de_servicios')}{' '}
            {t('settingsadvanced.editarlos_directamente_puede_romper_el_modulo_correspondiente')}
          </div>

          {orderedGroups.map(label => {
            const meta = groupMeta[label]
            const items = grouped[label]
            return (
              <div key={label}>
                <div className="seadse-row-5">
                  <div>
                    <div className="seadse-txt-1 seadse-con-icono">{meta?.icon || <Package size={15} />} {t(`settingsadvanced.${label}`)}</div>
                    {meta && (
                      <div className="u-text3-xs-mt2">
                        {t(`settingsadvanced.${label}_desc`)}
                      </div>
                    )}
                  </div>
                  <span className="seadse-box-27">{items.length}</span>
                </div>
                <div className="seadse-grid-4">
                  {items.map((s, idx) => {
                    const orgScope = s.organization_id ?? s.organizationId ?? 'global'
                    return <SystemSettingItem key={`${s.key}::${orgScope}::${idx}`} setting={s} />
                  })}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </SeccionDeAjustes>
  )
}


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
const OCULTAS_POR_GRUPO: Record<string, string[]> = { locale: CLAVES_EN_GENERAL }

const RUNTIME_GROUPS = [
  { id: 'sla',             label: 'SLA',                description: 'Tiempos por prioridad, jornada sin política y umbral de riesgo.' },
  { id: 'automations',     label: 'Automatizaciones',   description: 'Si las reglas saltan, cuánto puede encadenarse una con otra y los plazos del barrido.' },
  { id: 'tenants',         label: 'Empresas',           description: 'Cuarentena de la baja de una empresa y «entrar como» del soporte de plataforma.' },
  { id: 'risk',            label: 'Riesgo del proyecto', description: 'Pesos, umbrales de nivel y caché de la puntuación de riesgo por señales.' },
  { id: 'health',          label: 'Health scoring',     description: 'Pesos y umbrales del scoring de salud de cliente y proyecto.' },
  { id: 'proyectos',       label: 'Proyectos y planificador', description: 'Días laborables, umbrales del camino crítico, nivelación, alertas de recursos, curva S y cartera.' },
  { id: 'semantic',        label: 'Semantic',           description: 'Umbrales del clasificador semántico y motor de asignación.' },
  { id: 'password_policy', label: 'Política contraseñas', description: 'Reglas de validación y políticas de bloqueo.' },
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
]


export function RuntimeGroupEditor({ groupId, description, ocultar = [] }: { groupId: string; description?: string; ocultar?: string[] }) {
  const { t } = useAppLang()
  // Los ajustes de plataforma sólo los cambia el superadmin (revisión 2026-11).
  const esSuperadmin = !!useAuth().user?.is_superadmin
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

  const items = (data?.items || []).filter(it => !ocultar.includes(it.key))

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
  return (
    <>
      <div className="seadse-stack-2">
        <span className="u-text1-sm-600">{item.label}</span>
        {item.plataforma && <span className="seadse-txt-2">{t('settingsadvanced.solo_superadmin')}</span>}
      </div>
      <div>
        {isBool ? (
          <Select suelto placeholder={false} value={String(current)} onChange={(e) => onChange(e.target.value)} aria-label={item.label} className="seadse-inputstyle" disabled={disabled && item.plataforma}>
            <option value="true">{t('settingsadvanced.activado')}</option>
            <option value="false">{t('settingsadvanced.desactivado')}</option>
          </Select>
        ) : (
          <input
            aria-label={item.label}
            type={item.type === 'int' || item.type === 'float' ? 'number' : 'text'}
            step={item.type === 'float' ? 'any' : (item.type === 'int' ? '1' : undefined)}
            value={current}
            onChange={(e) => onChange(e.target.value)}
            className="ds-input seadse-inputstyle"
            disabled={disabled && item.plataforma}
          />
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
      if (result?.ok) toast.success(result.detail || t('settingsadvanced.conexion_ok'))
      else toast.error(result?.detail || t('settingsadvanced.conexion_fallo'))
    },
    onError: (e: unknown) => {
      setTestResult({ ok: false, detail: extractErr(e, GENERIC_ERROR_FALLBACK) })
      toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
    },
  })

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
          <span><strong>{testResult.ok ? t('settingsadvanced.conexion_ok') : t('settingsadvanced.conexion_fallo')}</strong>{testResult.detail ? ` — ${testResult.detail}` : ''}</span>
        </div>
      )}
      <div className="seadse-grid-6">
        {items.map(it => {
          const current = draft[it.key] ?? ''
          const dirty = it.is_secret ? (current !== '') : (String(it.value ?? '') !== String(current))
          return (
            <Fragment key={it.key}>
              <div className="seadse-stack-2">
                <span className="u-text1-sm-600">{it.label}</span>
                <span className="seadse-txt-2">
                  {it.is_secret ? `${t('settingsadvanced.secreto')} ` : ''}{t('settingsadvanced.origen')} {nombreDeOrigen(it.source)}
                </span>
              </div>
              <div>
                <input
                  aria-label={it.label}
                  type={it.is_secret ? 'password' : (it.type === 'int' ? 'number' : 'text')}
                  step={it.type === 'int' ? '1' : undefined}
                  value={current}
                  placeholder={it.is_secret && it.configured ? t('settingsadvanced.ya_configurado') : ''}
                  onChange={(e) => setDraft({ ...draft, [it.key]: e.target.value })}
                  className="ds-input seadse-inputstyle2"
                />
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


export function IntegrationCredentialsSection() {
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
    if (!active && providers.length) setActive(providers[0].provider)
  }, [providers, active])

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
        items={providers.map(p => ({ id: p.provider, label: p.label }))}
        active={active ?? undefined}
        onChange={id => setActive(id as IntegrationProvider)}
      />
      {active && currentProvider && (
        <IntegrationProviderEditor key={active} provider={active} label={currentProvider.label} />
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

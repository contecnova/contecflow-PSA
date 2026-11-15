import ConfigCorreoEntrante from '../service-desk/ConfigCorreoEntrante'
import EstadoDeConectores from '../../components/conectores/EstadoDeConectores'
import type { ChangeEvent } from 'react'
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
import './SettingsAdvancedSections.css'

/** Textos por módulo y clave: `{módulo: {clave: texto}}`. */
type TextosPorModulo = Record<string, Record<string, string>>
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
      appEdits?.[module]?.[key] ??
      (customTrans as Record<string, TextosPorModulo>)?.[lang]?.[module]?.[key] ??
      appTranslations?.[module]?.[key]
    ) : '') ?? ''

  const setAppVal = (lang: string, module: string, key: string, val: string) => {
    if (lang !== appLang) return
    setAppEdits(prev => ({
      ...prev,
      [module]: { ...(prev[module] || {}), [key]: val }
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
          toast.error('El JSON no contiene traducciones para el idioma seleccionado.')
          return
        }
        setAppEdits(data[appLang])
        setHasUnsaved(true)
        toast.success('Traducciones importadas. Revisa y guarda para aplicar.')
      } catch {
        toast.error('Error al leer el archivo JSON')
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
    const modelo: Record<string, Record<string, string>> = {}
    for (const k of allKeys) {
      (modelo[k.module] ??= {})[k.key] = String(getAppVal(appLang, k.module, k.key) ?? '')
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


  if (loadingAppLang) return <div>Cargando traducciones...</div>

  return (
    <div className="u-stack-20">
      <div className="seadse-row-1">
        {[['operator', '⚙️ Idioma del operador'], ['app', '🖥 Traducciones del back-office'], ['portal', '🌐 Portal cliente']].map(([id, label]) => (
          <button className="seadse-box-30" key={id} onClick={() => setActiveTab(id)}
            style={{ borderRadius: 'var(--radius-sm)', border: `1px solid ${activeTab === id ? 'var(--accent)' : 'var(--surface-4)'}`, background: activeTab === id ? 'var(--accent-muted)' : 'transparent', color: activeTab === id ? 'var(--accent)' : 'var(--text-2)' }}>
            {label}
          </button>
        ))}
      </div>

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
                <button className="seadse-box-31" key={l.code} onClick={() => setOperatorLang(l.code)}
                  style={{ borderRadius: 'var(--radius-md)', border: `2px solid ${operatorLang === l.code ? 'var(--accent)' : 'var(--surface-4)'}`, background: operatorLang === l.code ? 'var(--accent-muted)' : 'var(--surface-2)', color: operatorLang === l.code ? 'var(--accent)' : 'var(--text-2)' }}>
                  {l.flag} {l.label}
                  {operatorLang === l.code && <span className="seadse-box-3">✓</span>}
                </button>
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
              <div className="u-text2-xs-mb4">IDIOMA A EDITAR</div>
              <div className="u-row-6">
                {APP_LANGUAGES.filter(l => l.code !== 'es').map(l => (
                  <button className="seadse-box-30" key={l.code} onClick={() => setAppLang(l.code)}
                    style={{ borderRadius: 'var(--radius-sm)', border: `1px solid ${appLang === l.code ? 'var(--accent)' : 'var(--surface-4)'}`, background: appLang === l.code ? 'var(--accent-muted)' : 'transparent', color: appLang === l.code ? 'var(--accent)' : 'var(--text-2)' }}>
                    {l.flag} {l.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="u-flex1">
              <div className="u-text2-xs-mb4">BUSCAR CLAVE</div>
              <input value={searchKey} onChange={e => setSearchKey(e.target.value)}
                placeholder={t('settingsadvanced.buscar_clave_de_traduccion')} aria-label={t('settingsadvanced.buscar_clave_de_traduccion')} className="seadse-fs" />
            </div>
            <div>
              <div className="u-text2-xs-mb4">MODULO</div>
              <select value={activeModule} onChange={e => setActiveModule(e.target.value)} className="seadse-fs2">
                {modules.map(m => <option key={m} value={m}>{m === 'all' ? 'Todos los modulos' : m}</option>)}
              </select>
            </div>
            <div>
              <div className="u-text2-xs-mb4">IMPORTAR JSON</div>
              <label className="seadse-box-5">
                📥 Importar JSON
                <input type="file" accept="application/json" aria-label="Importar JSON" className="seadse-box-6" onChange={importJSON} />
              </label>
            </div>
            <div>
              <div className="u-text2-xs-mb4">EXPORTAR JSON</div>
              <button type="button" onClick={exportJSON}
                className="seadse-box-7">
                📤 Exportar JSON
              </button>
            </div>
          </div>

          <div className="seadse-grid-1">
            <span>Modulo.Clave</span>
            <span>🇪🇸 Espanol (base)</span>
            <span>{APP_LANGUAGES.find(l => l.code === appLang)?.flag} {APP_LANGUAGES.find(l => l.code === appLang)?.label}</span>
          </div>
          <div className="seadse-box-8">
            {filteredKeys.slice(0, 200).map((item, idx) => {
              const currentVal = getAppVal(appLang, item.module, item.key)
              const isModified = appEdits[item.module]?.[item.key] !== undefined
              return (
                <div className="seadse-grid-7" key={item.full_key}
                  style={{ background: idx % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.02)' }}>
                  <div>
                    <span className="seadse-box-9">{item.module}</span>
                    <span className="seadse-txt-3" style={{ color: isModified ? 'var(--warning)' : 'var(--text-2)' }}>{item.key}</span>
                  </div>
                  <div className="seadse-box-10">
                    {item.base_es}
                  </div>
                  <input className="seadse-fs3"
                    aria-label={item.full_key}
                    value={currentVal}
                    onChange={e => setAppVal(appLang, item.module, item.key, e.target.value)}
                    style={{ borderColor: isModified ? 'rgba(245,158,11,0.31)' : 'var(--surface-4)' }}
                    placeholder={item.base_es}
                  />
                </div>
              )
            })}
            {filteredKeys.length > 200 && (
              <div className="seadse-box-11">
                {t('settingsadvanced.mostrando_200_de')} {filteredKeys.length} {t('settingsadvanced.claves_usa_el_filtro_para_buscar_mas')}
              </div>
            )}
          </div>

          <div className="seadse-row-3">
            <div className="u-text2-sm">
              {filteredKeys.length} claves · {allKeys.length} total · {hasUnsaved && <span className="u-warning">{t('settingsadvanced.cambios_sin_guardar')}</span>}
            </div>
            <div className="u-row-8">
              <button className="seadse-box-32" onClick={() => saveAppTrans()} disabled={!hasUnsaved}
                style={{ background: hasUnsaved ? 'var(--accent)' : 'var(--surface-4)', color: hasUnsaved ? 'var(--surface-0)' : 'var(--text-2)', cursor: hasUnsaved ? 'pointer' : 'default' }}>
                💾 Guardar traduccion
              </button>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'portal' && (
        <div>
          <div className="seadse-row-2">
            <div>
              <div className="u-text2-xs-mb4">IDIOMA A EDITAR</div>
              <div className="u-row-6">
                {PORTAL_LANGUAGES.filter(l => l.code !== 'es').map(l => (
                  <button className="seadse-box-30" key={l.code} onClick={() => setPortalLang(l.code)}
                    style={{ borderRadius: 'var(--radius-sm)', border: `1px solid ${portalLang === l.code ? 'var(--accent)' : 'var(--surface-4)'}`, background: portalLang === l.code ? 'var(--accent-muted)' : 'transparent', color: portalLang === l.code ? 'var(--accent)' : 'var(--text-2)' }}>
                    {l.flag} {l.label}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <div className="u-text2-xs-mb4">BUSCAR</div>
              <input value={portalSearch} onChange={e => setPortalSearch(e.target.value)}
                placeholder={t('settingsadvanced.buscar_texto_del_portal')} aria-label={t('settingsadvanced.buscar_texto_del_portal')} className="seadse-fs4" />
            </div>
            <div>
              <div className="u-text2-xs-mb4">IMPORTAR JSON</div>
              <label className="seadse-box-5">
                📥 Importar JSON
                <input type="file" accept="application/json" aria-label="Importar JSON" className="seadse-box-6" onChange={e => {
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
                      toast.success('Traducciones importadas. Revisa y guarda para aplicar.')
                    } catch {
                      toast.error('Error al leer el archivo JSON')
                    }
                  }
                  reader.readAsText(file)
                }} />
              </label>
            </div>
            <div>
              <div className="u-text2-xs-mb4">EXPORTAR JSON</div>
              <button type="button" onClick={exportPortalJSON}
                className="seadse-box-7">
                📤 Exportar JSON
              </button>
            </div>
          </div>

          <div className="seadse-grid-2">
            <span>Clave</span>
            <span>🇪🇸 Espanol (base)</span>
            <span>{PORTAL_LANGUAGES.find(l => l.code === portalLang)?.flag} {PORTAL_LANGUAGES.find(l => l.code === portalLang)?.label}</span>
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
                  <div className="seadse-grid-8" key={key} style={{ background: idx % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.02)' }}>
                    <span className="seadse-txt-3" style={{ color: isModified ? 'var(--warning)' : 'var(--text-2)' }}>{key}</span>
                    <span className="seadse-box-10">{base_es}</span>
                    <input className="seadse-fs3"
                      aria-label={key}
                      value={currentVal}
                      onChange={e => {
                        setPortalEdits(prev => ({ ...prev, [key]: { ...(prev[key] || {}), [portalLang]: e.target.value } }))
                        setHasUnsaved(true)
                      }}
                      style={{ borderColor: isModified ? 'rgba(245,158,11,0.31)' : 'var(--surface-4)' }}
                      placeholder={base_es}
                    />
                  </div>
                )
              })}
          </div>

          <div className="seadse-row-3">
            <div className="u-text2-sm">
              {getPortalKeys().length} claves · 8 idiomas
              {hasUnsaved && <span className="seadse-box-12">{t('settingsadvanced.cambios_sin_guardar')}</span>}
            </div>
            <div className="u-row-8">
              <button className="seadse-box-32" onClick={() => {
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
              }} style={{ background: hasUnsaved ? 'var(--accent)' : 'var(--surface-4)', color: hasUnsaved ? 'var(--surface-0)' : 'var(--text-2)', cursor: hasUnsaved ? 'pointer' : 'default' }} disabled={!hasUnsaved}>
                {savingPortal ? 'Guardando...' : '💾 Guardar traducciones'}
              </button>
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
      toast.success(`Nivel backend cambiado a ${lvl}`)
      qc.invalidateQueries({ queryKey: ['log-level'] })
    } catch {
      toast.error('Error al cambiar nivel de log')
    }
  }

  const handleSetFrontend = (level: string) => {
    setFrontendLevel(level)
    localStorage.setItem('contecflow_log_level', level)
    const logger = (window as VentanaConLogger).__contecflowLogger
    if (logger) logger.setLevel(level)
    toast.success(`Nivel frontend cambiado a ${level.toUpperCase()} (activo hasta recarga)`)
  }

  const LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
  const LEVEL_COLORS: Record<string, string> = { DEBUG: 'var(--text-2)', INFO: 'var(--accent)', WARNING: 'var(--warning)', ERROR: 'var(--danger)', CRITICAL: '#c0392b' }

  return (
    <SeccionDeAjustes icon="📋" title={t('settingsadvanced.nivel_de_log')} description="Controla la verbosidad del backend y frontend">
      <div className="seadse-grid-3">
        <div className="seadse-box-13">
          <div className="seadse-box-14">🖥️ Servidor (FastAPI / Uvicorn)</div>
          <div className="seadse-box-15">
            {t('settingsadvanced.cambia_el_nivel_en_tiempo_real_sin')} <code className="seadse-box-16">LOG_LEVEL=INFO</code>
          </div>
          {!isLoading && serverLevel && (
            <div className="seadse-box-17">
              Nivel actual: <strong>{serverLevel.contecflow}</strong>
              <span className="seadse-box-18">
                (root: {serverLevel.root} · uvicorn: {serverLevel.uvicorn || serverLevel.root})
              </span>
            </div>
          )}
          <div className="u-wrap-8">
            {LEVELS.map(l => (
              <button className="seadse-box-33" key={l} onClick={() => handleSetBackend(l)}
                style={{ borderRadius: 8, border: `1px solid ${backendLevel === l ? LEVEL_COLORS[l] : 'var(--surface-4)'}`, background: backendLevel === l ? (alpha(LEVEL_COLORS[l], '22')) : 'var(--surface-3)', color: backendLevel === l ? LEVEL_COLORS[l] : 'var(--text-2)' }}>
                {l}
              </button>
            ))}
          </div>
        </div>

        <div className="seadse-box-13">
          <div className="seadse-box-14">🌐 Navegador (React / Vite)</div>
          <div className="seadse-box-15">
            {t('settingsadvanced.controla_la_consola_del_navegador_se_guarda')} <code className="seadse-box-16">{"__contecflowLogger.setLevel('debug')"}</code>
          </div>
          <div className="seadse-box-17">
            Nivel actual: <strong>{frontendLevel.toUpperCase()}</strong>
          </div>
          <div className="u-wrap-8">
            {['DEBUG', 'INFO', 'WARN', 'ERROR', 'SILENT'].map(l => (
              <button className="seadse-box-33" key={l} onClick={() => handleSetFrontend(l.toLowerCase())}
                style={{ borderRadius: 8, border: `1px solid ${frontendLevel.toUpperCase() === l ? (LEVEL_COLORS[l] || LEVEL_COLORS['ERROR']) : 'var(--surface-4)'}`, background: frontendLevel.toUpperCase() === l ? (alpha((LEVEL_COLORS[l] || LEVEL_COLORS['ERROR']), '22')) : 'var(--surface-3)', color: frontendLevel.toUpperCase() === l ? (LEVEL_COLORS[l] || LEVEL_COLORS['ERROR']) : 'var(--text-2)' }}>
                {l}
              </button>
            ))}
          </div>
        </div>
      </div>
    </SeccionDeAjustes>
  )
}

export function EmailInboundSection() {
  // La misma pantalla que Service Desk → Configuración → Correo entrante.
  return (
    <SeccionDeAjustes icon="📧" title="Email a ticket" description="Correo entrante al Service Desk: buzón, pasarela y últimos mensajes">
      <ConfigCorreoEntrante />
    </SeccionDeAjustes>
  )
}

// ── Estado del sistema (admin debug) ──────────────────────────────────────────

const SYSTEM_KEY_GROUPS = [
  {
    label: 'BI · Plataforma',
    icon: '📊',
    prefixes: ['bi.phase', 'bi.smart_alerts', 'bi.governance', 'bi.collaboration', 'bi.platform'],
    description: 'Estado interno de Smart Alerts, gobernanza, conectores BI, snapshots OLAP y plataforma.',
  },
  {
    label: 'BI · ETL & O365',
    icon: '🔌',
    prefixes: ['bi.etl', 'bi.o365', 'bi.intelligence'],
    description: 'Estado de conectores ETL, Microsoft 365 y configuración Intelligence.',
  },
  {
    label: 'Service Desk · Voz',
    icon: '📞',
    prefixes: ['sd.voice'],
    description: 'Configuración del agente IVR y sesiones de voz registradas.',
  },
  {
    label: 'Service Desk · ML',
    icon: '🤖',
    prefixes: ['sd.ml_', 'sd.feedback', 'sd.auto_resolution', 'sd.assignment'],
    description: 'Estado del motor de asignación ML y feedback de auto-resolución.',
  },
  {
    label: 'Service Desk · Otros',
    icon: '🛠',
    prefixes: ['sd.'],
    description: 'Cualquier otro estado interno de Service Desk.',
  },
  {
    label: 'OLAP & Cache',
    icon: '⚡',
    prefixes: ['olap.', 'cache_'],
    description: 'Estado de cubos OLAP, claves de cache y políticas TTL.',
  },
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
  return 'Otros'
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
        <code className="seadse-box-20">{setting.key}</code>
        <button
          type="button"
          onClick={() => setExpanded(v => !v)}
          className="seadse-box-21"
        >{expanded ? 'Ocultar' : 'Ver completo'}</button>
      </div>
      {setting.description && (
        <div className="seadse-box-22">
          {setting.description}
        </div>
      )}
      <pre style={{
        background: 'var(--surface-1)', border: '1px solid var(--surface-4)',
        borderRadius: 'var(--radius-sm)', padding: '8px 10px',
        fontSize: 'var(--text-2xs)', color: 'var(--text-2)',
        margin: 0, fontFamily: 'var(--font-mono)',
        maxHeight: expanded ? 'none' : 64,
        overflow: expanded ? 'auto' : 'hidden',
        whiteSpace: 'pre',
        ...(expanded ? { overflowX: 'auto' } : {}),
      }}>{expanded ? (formatted || '—') : preview}</pre>
      <div className="seadse-box-23">
        {isJson ? `JSON · ${lineCount} líneas` : `Texto · ${(setting.value || '').length} caracteres`}
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
    <div className="seadse-box-34" role={data.armed ? undefined : 'alert'} style={{ borderRadius: 'var(--radius-md)', background: `color-mix(in srgb, ${color} 8%, var(--surface-3))`, border: `1px solid color-mix(in srgb, ${color} 30%, var(--surface-4))` }}>
      <strong style={{ color }}>{data.armed ? '🔒 ' + t('settingsadvanced.rls_armado') : '⚠ ' + t('settingsadvanced.rls_desarmado')}</strong>
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
  if (grouped['Otros']?.length) orderedGroups.push('Otros')
  const groupMeta = Object.fromEntries(SYSTEM_KEY_GROUPS.map(g => [g.label, g]))

  return (
    <SeccionDeAjustes icon="🔧" title={t('settingsadvanced.estado_del_sistema')} description="Lectura del estado interno persistido por servicios BI / ITSM (admin · solo lectura)">
      <AislamientoEnLaBase />
      {isLoading ? (
        <div className="u-text3-sm">Cargando…</div>
      ) : internal.length === 0 ? (
        <div className="seadse-box-25">
          {t('settingsadvanced.sin_estado_interno_registrado')}
        </div>
      ) : (
        <div className="seadse-stack-1">
          <div className="seadse-box-26">
            <strong className="u-warning">{t('settingsadvanced.vista_de_solo_lectura')}</strong>{' '}
            {t('settingsadvanced.estos_blobs_son_estado_interno_de_servicios')}<code className="u-mono">/bi/govern</code>, <code className="u-mono">/bi/data</code>,
            <code className="u-mono">{t('settingsadvanced.service_desk_voz_ml_auto_resolucion')}</code>{t('settingsadvanced.editarlos_directamente_puede_romper_el_modulo_correspondiente')}
          </div>

          {orderedGroups.map(label => {
            const meta = groupMeta[label]
            const items = grouped[label]
            return (
              <div key={label}>
                <div className="seadse-row-5">
                  <div>
                    <div className="seadse-txt-1">{meta?.icon || '📦'} {label}</div>
                    {meta?.description && (
                      <div className="u-text3-xs-mt2">
                        {meta.description}
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

const RUNTIME_GROUPS = [
  { id: 'sla',             label: 'SLA',                description: 'Tiempos por prioridad, jornada sin política y umbral de riesgo.' },
  { id: 'service_desk',    label: 'Service Desk',       description: 'A quién se avisa de cada cambio de ticket y cómo se entrega.' },
  { id: 'automations',     label: 'Automatizaciones',   description: 'Si las reglas saltan, cuánto puede encadenarse una con otra y los plazos del barrido.' },
  { id: 'tenants',         label: 'Empresas',           description: 'Cuarentena de la baja de una empresa y «entrar como» del soporte de plataforma.' },
  { id: 'risk',            label: 'Riesgo del proyecto', description: 'Pesos, umbrales de nivel y caché de la puntuación de riesgo por señales.' },
  { id: 'health',          label: 'Health scoring',     description: 'Pesos y umbrales del scoring de salud de cliente y proyecto.' },
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
  { id: 'politicas',       label: 'Políticas y reglas', description: 'Cuántas entidades repasa el simulador y qué tipos de documento puede pedir una regla.' },
  { id: 'lecciones',       label: 'Lecciones aprendidas', description: 'Categorías, quién valida, borrador con IA y cómo se buscan los casos parecidos (pesos y mínimo).' },
  { id: 'conectores',      label: 'Conectores contecmind / contecintelligence', description: 'Tiempos de espera, roles que escriben o analizan, tamaño de subida y registro de llamadas.' },
]


export function RuntimeGroupEditor({ groupId, description }: { groupId: string; description?: string }) {
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
      toast.success('Guardado')
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

  if (isLoading) return <div className="seadse-box-28">Cargando…</div>
  if (isError) return <div className="seadse-box-29">{extractErr(error, GENERIC_ERROR_FALLBACK)}</div>

  const items = data?.items || []

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
  return (
    <>
      <div className="seadse-stack-2">
        <span className="u-text1-sm-600">{item.label}</span>
        <span className="seadse-txt-2">{item.key}{item.plataforma ? ' · plataforma (superadmin)' : ''}</span>
      </div>
      <div>
        {isBool ? (
          <select value={String(current)} onChange={(e) => onChange(e.target.value)} className="seadse-inputstyle" disabled={disabled && item.plataforma}>
            <option value="true">Activado</option>
            <option value="false">Desactivado</option>
          </select>
        ) : (
          <input
            aria-label={item.label}
            type={item.type === 'int' || item.type === 'float' ? 'number' : 'text'}
            step={item.type === 'float' ? 'any' : (item.type === 'int' ? '1' : undefined)}
            value={current}
            onChange={(e) => onChange(e.target.value)}
            className="seadse-inputstyle"
            disabled={disabled && item.plataforma}
          />
        )}
      </div>
      <button className="seadse-box-35"
        type="button"
        onClick={onSave}
        disabled={!dirty || disabled}
        style={{ background: dirty ? 'var(--accent)' : 'var(--surface-3)', color: dirty ? '#fff' : 'var(--text-3)', cursor: dirty && !disabled ? 'pointer' : 'not-allowed' }}
      >Guardar</button>
    </>
  )
}


// ── Integration credentials (Phase 2: encrypted per-org provider creds) ─────

function IntegrationProviderEditor({ provider, label }: { provider: IntegrationProvider; label?: string }) {
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
      toast.success('Guardado')
    },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const [testResult, setTestResult] = useState<IntegrationTestResult | null>(null)
  const { mutate: runTest, isPending: testing } = useMutation({
    mutationFn: () => settingsApi.testIntegration(provider).then(r => r.data),
    onSuccess: result => {
      setTestResult(result)
      if (result?.ok) toast.success(result.detail || 'Conexión OK')
      else toast.error(result?.detail || 'Test de conexión falló')
    },
    onError: (e: unknown) => {
      setTestResult({ ok: false, detail: extractErr(e, GENERIC_ERROR_FALLBACK) })
      toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
    },
  })

  const [draft, setDraft] = useState<Record<string, string>>({})
  useEffect(() => {
    if (data?.items) {
      const next: Record<string, string> = {}
      // Secrets never echo back — start as empty so admin types the new value.
      for (const it of data.items) next[it.key] = it.is_secret ? '' : (it.value == null ? '' : String(it.value))
      setDraft(next)
    }
  }, [data])

  if (isLoading) return <div className="seadse-box-28">Cargando…</div>
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
        <button className="seadse-box-36"
          type="button"
          onClick={() => runTest()}
          disabled={testing}
          style={{ cursor: testing ? 'not-allowed' : 'pointer' }}
        >{testing ? 'Probando…' : 'Probar conexión'}</button>
      </div>
      {testResult && (
        <div className="seadse-box-37" style={{ borderRadius: 8, background: testResult.ok ? 'rgba(34,197,94,.12)' : 'rgba(239,68,68,.12)', border: '1px solid ' + (testResult.ok ? 'rgba(34,197,94,.4)' : 'rgba(239,68,68,.4)'), color: testResult.ok ? 'var(--success, #22c55e)' : 'var(--danger, #ef4444)' }}>
          <strong>{testResult.ok ? '✓ OK' : '✗ Error'}</strong> — {testResult.detail}
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
                  {it.key}{it.is_secret ? ' • secreto' : ''} • origen: {it.source}
                </span>
              </div>
              <div>
                <input
                  aria-label={it.label}
                  type={it.is_secret ? 'password' : (it.type === 'int' ? 'number' : 'text')}
                  step={it.type === 'int' ? '1' : undefined}
                  value={current}
                  placeholder={it.is_secret && it.configured ? '•••• (configurado)' : ''}
                  onChange={(e) => setDraft({ ...draft, [it.key]: e.target.value })}
                  className="seadse-inputstyle2"
                />
              </div>
              <button className="seadse-box-35"
                type="button"
                onClick={() => save({ key: it.key, value: current })}
                disabled={!dirty || isPending}
                style={{ background: dirty ? 'var(--accent)' : 'var(--surface-3)', color: dirty ? '#fff' : 'var(--text-3)', cursor: dirty && !isPending ? 'pointer' : 'not-allowed' }}
              >Guardar</button>
              <button className="seadse-box-38"
                type="button"
                onClick={() => save({ key: it.key, value: '' })}
                disabled={isPending || (!it.configured)}
                title={it.configured ? 'Borrar override (vuelve al valor del .env)' : 'No configurado'}
                style={{ cursor: isPending || !it.configured ? 'not-allowed' : 'pointer' }}
              >Borrar</button>
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

  if (isLoading) return <SeccionDeAjustes icon="🔐" title={t('settingsadvanced.credenciales_de_integracion')}><div className="seadse-box-28">Cargando…</div></SeccionDeAjustes>
  if (isError)   return <SeccionDeAjustes icon="🔐" title={t('settingsadvanced.credenciales_de_integracion')}><div className="seadse-box-29">{extractErr(error, GENERIC_ERROR_FALLBACK)}</div></SeccionDeAjustes>

  const currentProvider = providers.find(p => p.provider === active)

  return (
    <SeccionDeAjustes
      icon="🔐"
      title={t('settingsadvanced.credenciales_de_integracion')}
      description="SMTP, AWS S3, Microsoft Graph, Slack, Stripe, etc. Los secretos se cifran en reposo (Fernet/HKDF + opcional AWS KMS) y nunca se devuelven en las respuestas."
    >
      <EstadoDeConectores />
      <div className="seadse-row-7">
        {providers.map(p => (
          <button className="seadse-box-39"
            key={p.provider}
            onClick={() => setActive(p.provider)}
            style={{ borderRadius: 'var(--radius-full)', border: '1px solid ' + (active === p.provider ? 'var(--accent)' : 'var(--surface-4)'), background: active === p.provider ? 'var(--accent-muted)' : 'transparent', color: active === p.provider ? 'var(--accent)' : 'var(--text-2)' }}
          >{p.label}</button>
        ))}
      </div>
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
    <SeccionDeAjustes icon="⚙️" title={t('settingsadvanced.configuracion_dinamica')} description="Knobs operativos editables sin redeploy. Resuelven org → global → valor del .env.">
      <div className="seadse-row-7">
        {RUNTIME_GROUPS.map(g => (
          <button className="seadse-box-39"
            key={g.id}
            onClick={() => setActive(g.id)}
            style={{ borderRadius: 'var(--radius-full)', border: '1px solid ' + (active === g.id ? 'var(--accent)' : 'var(--surface-4)'), background: active === g.id ? 'var(--accent-muted)' : 'transparent', color: active === g.id ? 'var(--accent)' : 'var(--text-2)' }}
          >{g.label}</button>
        ))}
      </div>
      <RuntimeGroupEditor key={active} groupId={active} description={current.description} />
    </SeccionDeAjustes>
  )
}

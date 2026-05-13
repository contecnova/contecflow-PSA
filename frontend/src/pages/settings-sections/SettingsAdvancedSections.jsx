import { useState, useEffect } from 'react'
import { useToast } from '../../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAppLang } from '../../i18n/AppLangContext'
import { APP_LANGUAGES, loadLanguage, getAllKeys, es } from '../../i18n/appTranslations.mjs'
import { PORTAL_TRANSLATIONS, PORTAL_LANGUAGES, getPortalKeys } from '../../i18n/portalTranslations'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { Card } from '../../components/ui'
import { portalClientsApi, settingsApi } from '../../services/api'

function Section({ icon, title, description, children }) {
  return (
    <Card style={{ marginBottom: 24 }}>
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontSize: "var(--text-lg)", fontWeight: 700 }}>{icon} {title}</div>
        {description && <div style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', marginTop: 4 }}>{description}</div>}
      </div>
      {children}
    </Card>
  )
}

export function IdiomasSection() {
  const toast = useToast()
  const qc = useQueryClient()
  const { lang: operatorLang, setLang: setOperatorLang, t, _translations, setCustomTranslations, customTrans } = useAppLang()

  const { data: _portalTrans = {} } = useQuery({
    queryKey: ['portal-translations'],
    queryFn: () => portalClientsApi.translations().then(r => r.data).catch(() => ({})),
  })
  const { mutate: savePortalTrans, isPending: savingPortal } = useMutation({
    mutationFn: d => portalClientsApi.saveTranslations(d),
    onSuccess: () => { qc.invalidateQueries(['portal-translations']); toast.success(t('i18n.saved_ok')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const [activeTab, setActiveTab] = useState('operator')
  const [appLang, setAppLang] = useState('en')
  const [appTranslations, setAppTranslations] = useState({})
  const [loadingAppLang, setLoadingAppLang] = useState(true)
  const [portalLang, setPortalLang] = useState('en')
  const [searchKey, setSearchKey] = useState('')
  const [activeModule, setActiveModule] = useState('all')
  const [appEdits, setAppEdits] = useState({})
  const [portalEdits, setPortalEdits] = useState({})
  const [portalSearch, setPortalSearch] = useState('')
  const [hasUnsaved, setHasUnsaved] = useState(false)

  const allKeys = getAllKeys(es)
  const modules = ['all', ...new Set(allKeys.map(k => k.module))]

  useEffect(() => {
    let cancelled = false
    setLoadingAppLang(true)
    loadLanguage(appLang).then(tr => {
      if (!cancelled) {
        setAppTranslations(tr)
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

  const getAppVal = (lang, module, key) =>
    (lang === appLang ? (
      appEdits?.[module]?.[key] ??
      customTrans?.[module]?.[key] ??
      appTranslations?.[module]?.[key]
    ) : '') ?? ''

  const setAppVal = (lang, module, key, val) => {
    if (lang !== appLang) return
    setAppEdits(prev => ({
      ...prev,
      [module]: { ...(prev[module] || {}), [key]: val }
    }))
    setHasUnsaved(true)
  }

  const importJSON = (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (ev) => {
      try {
        const data = JSON.parse(ev.target.result)
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

  const saveAppTrans = () => {
    const merged = { ...customTrans }
    merged[appLang] = { ...customTrans[appLang], ...appEdits }
    setCustomTranslations(merged)
    setAppEdits({})
    setHasUnsaved(false)
    toast.success(t('i18n.saved_ok'))
  }

  const exportJSON = () => {
    const data = JSON.stringify(appTranslations, null, 2)
    const blob = new Blob([data], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a'); a.href = url
    a.download = `contecflow_translations_${appLang}.json`; a.click()
    URL.revokeObjectURL(url)
  }

  const fs = { width: '100%', background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '6px 10px', color: 'var(--text-1)', fontSize: "var(--text-sm)", outline: 'none', fontFamily: 'inherit' }
  const card = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12 }

  if (loadingAppLang) return <div>Cargando traducciones...</div>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', gap: 6, borderBottom: '1px solid var(--surface-4)', paddingBottom: 10 }}>
        {[['operator', '⚙️ Idioma del operador'], ['app', '🖥 Traducciones del back-office'], ['portal', '🌐 Portal cliente']].map(([id, label]) => (
          <button key={id} onClick={() => setActiveTab(id)}
            style={{ padding: '5px 14px', borderRadius: 6, border: `1px solid ${activeTab === id ? 'var(--accent)' : 'var(--surface-4)'}`, background: activeTab === id ? 'var(--accent-muted)' : 'transparent', color: activeTab === id ? 'var(--accent)' : 'var(--text-2)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>
            {label}
          </button>
        ))}
      </div>

      {activeTab === 'operator' && (
        <div style={card}>
          <div style={{ padding: '20px 24px', borderBottom: '1px solid var(--surface-4)' }}>
            <div style={{ fontSize: "var(--text-md)", fontWeight: 700, marginBottom: 4 }}>Idioma del operador (back-office)</div>
            <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
              Idioma de la interfaz interna. Cada usuario puede configurar el suyo desde aquí. Se guarda en el navegador.
            </div>
          </div>
          <div style={{ padding: '20px 24px' }}>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              {APP_LANGUAGES.map(l => (
                <button key={l.code} onClick={() => setOperatorLang(l.code)}
                  style={{ padding: '12px 22px', borderRadius: 10, border: `2px solid ${operatorLang === l.code ? 'var(--accent)' : 'var(--surface-4)'}`, background: operatorLang === l.code ? 'var(--accent-muted)' : 'var(--surface-2)', color: operatorLang === l.code ? 'var(--accent)' : 'var(--text-2)', fontSize: "var(--text-md-em)", fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit', transition: 'all 0.15s' }}>
                  {l.flag} {l.label}
                  {operatorLang === l.code && <span style={{ marginLeft: 8, fontSize: "var(--text-sm)" }}>✓</span>}
                </button>
              ))}
            </div>
            <div style={{ marginTop: 16, padding: '10px 14px', background: 'var(--surface-1)', borderRadius: 8, fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
              💡 Al cambiar el idioma, los menús, títulos y textos de la interfaz se mostrarán en ese idioma.
              Las páginas que aún no estén totalmente traducidas mostrarán el texto en español.
            </div>
          </div>
        </div>
      )}

      {activeTab === 'app' && (
        <div>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 16, flexWrap: 'wrap' }}>
            <div>
              <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginBottom: 4 }}>IDIOMA A EDITAR</div>
              <div style={{ display: 'flex', gap: 6 }}>
                {APP_LANGUAGES.filter(l => l.code !== 'es').map(l => (
                  <button key={l.code} onClick={() => setAppLang(l.code)}
                    style={{ padding: '5px 14px', borderRadius: 6, border: `1px solid ${appLang === l.code ? 'var(--accent)' : 'var(--surface-4)'}`, background: appLang === l.code ? 'var(--accent-muted)' : 'transparent', color: appLang === l.code ? 'var(--accent)' : 'var(--text-2)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>
                    {l.flag} {l.label}
                  </button>
                ))}
              </div>
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginBottom: 4 }}>BUSCAR CLAVE</div>
              <input value={searchKey} onChange={e => setSearchKey(e.target.value)}
                placeholder="Buscar clave de traduccion" aria-label="Buscar clave de traduccion" style={{ ...fs, width: 280 }} />
            </div>
            <div>
              <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginBottom: 4 }}>MODULO</div>
              <select value={activeModule} onChange={e => setActiveModule(e.target.value)} style={{ ...fs, width: 160 }}>
                {modules.map(m => <option key={m} value={m}>{m === 'all' ? 'Todos los modulos' : m}</option>)}
              </select>
            </div>
            <div>
              <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginBottom: 4 }}>IMPORTAR JSON</div>
              <label style={{ display: 'inline-block', padding: '7px 14px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>
                📤 Importar JSON
                <input type="file" accept="application/json" style={{ display: 'none' }} onChange={importJSON} />
              </label>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '140px 1fr 1fr', gap: 8, padding: '8px 14px', background: 'var(--surface-1)', borderRadius: '8px 8px 0 0', fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase' }}>
            <span>Modulo.Clave</span>
            <span>🇪🇸 Espanol (base)</span>
            <span>{APP_LANGUAGES.find(l => l.code === appLang)?.flag} {APP_LANGUAGES.find(l => l.code === appLang)?.label}</span>
          </div>
          <div style={{ border: '1px solid var(--surface-4)', borderTop: 'none', borderRadius: '0 0 8px 8px', maxHeight: 500, overflowY: 'auto' }}>
            {filteredKeys.slice(0, 200).map((item, idx) => {
              const currentVal = getAppVal(appLang, item.module, item.key)
              const isModified = appEdits[appLang]?.[item.module]?.[item.key] !== undefined
              return (
                <div key={item.full_key}
                  style={{ display: 'grid', gridTemplateColumns: '140px 1fr 1fr', gap: 8, padding: '6px 14px', borderBottom: '1px solid var(--surface-4)20', background: idx % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.02)', alignItems: 'center' }}>
                  <div>
                    <span style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', display: 'block' }}>{item.module}</span>
                    <span style={{ fontSize: "var(--text-xs)", fontFamily: 'var(--font-mono)', color: isModified ? 'var(--warning)' : 'var(--text-2)' }}>{item.key}</span>
                  </div>
                  <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {item.base_es}
                  </div>
                  <input
                    value={currentVal}
                    onChange={e => setAppVal(appLang, item.module, item.key, e.target.value)}
                    style={{ ...fs, padding: '4px 8px', borderColor: isModified ? 'rgba(245,158,11,0.31)' : 'var(--surface-4)' }}
                    placeholder={item.base_es}
                  />
                </div>
              )
            })}
            {filteredKeys.length > 200 && (
              <div style={{ padding: '10px 14px', fontSize: "var(--text-sm)", color: 'var(--text-2)', textAlign: 'center' }}>
                Mostrando 200 de {filteredKeys.length} claves. Usa el filtro para buscar mas especifico.
              </div>
            )}
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 14 }}>
            <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
              {filteredKeys.length} claves · {allKeys.length} total · {hasUnsaved && <span style={{ color: 'var(--warning)' }}>⚠ Cambios sin guardar</span>}
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button onClick={exportJSON}
                style={{ padding: '7px 14px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>
                📥 Exportar JSON
              </button>
              <button onClick={saveAppTrans} disabled={!hasUnsaved}
                style={{ padding: '7px 14px', borderRadius: 8, border: 'none', background: hasUnsaved ? 'var(--accent)' : 'var(--surface-4)', color: hasUnsaved ? 'var(--surface-0)' : 'var(--text-2)', cursor: hasUnsaved ? 'pointer' : 'default', fontSize: "var(--text-sm)", fontWeight: 700, fontFamily: 'inherit' }}>
                💾 Guardar traduccion
              </button>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'portal' && (
        <div>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 16, flexWrap: 'wrap' }}>
            <div>
              <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginBottom: 4 }}>IDIOMA A EDITAR</div>
              <div style={{ display: 'flex', gap: 6 }}>
                {PORTAL_LANGUAGES.filter(l => l.code !== 'es').map(l => (
                  <button key={l.code} onClick={() => setPortalLang(l.code)}
                    style={{ padding: '5px 14px', borderRadius: 6, border: `1px solid ${portalLang === l.code ? 'var(--accent)' : 'var(--surface-4)'}`, background: portalLang === l.code ? 'var(--accent-muted)' : 'transparent', color: portalLang === l.code ? 'var(--accent)' : 'var(--text-2)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>
                    {l.flag} {l.label}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginBottom: 4 }}>BUSCAR</div>
              <input value={portalSearch} onChange={e => setPortalSearch(e.target.value)}
                placeholder="Buscar texto del portal" aria-label="Buscar texto del portal" style={{ ...fs, width: 260 }} />
            </div>
            <div>
              <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginBottom: 4 }}>IMPORTAR JSON</div>
              <label style={{ display: 'inline-block', padding: '7px 14px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>
                📤 Importar JSON
                <input type="file" accept="application/json" style={{ display: 'none' }} onChange={e => {
                  const file = e.target.files[0]
                  if (!file) return
                  const reader = new FileReader()
                  reader.onload = evt => {
                    try {
                      const data = JSON.parse(evt.target.result)
                      setPortalEdits(prev => {
                        const merged = { ...prev }
                        for (const [lang, keys] of Object.entries(data)) {
                          for (const [key, value] of Object.entries(keys)) {
                            if (!merged[key]) merged[key] = {}
                            merged[key][lang] = value
                          }
                        }
                        return merged
                      })
                      setHasUnsaved(true)
                      alert('Traducciones importadas. Revisa y guarda para aplicar.')
                    } catch {
                      alert('Error al leer el archivo JSON')
                    }
                  }
                  reader.readAsText(file)
                }} />
              </label>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '180px 1fr 1fr', gap: 8, padding: '8px 14px', background: 'var(--surface-1)', borderRadius: '8px 8px 0 0', fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase' }}>
            <span>Clave</span>
            <span>🇪🇸 Espanol (base)</span>
            <span>{PORTAL_LANGUAGES.find(l => l.code === portalLang)?.flag} {PORTAL_LANGUAGES.find(l => l.code === portalLang)?.label}</span>
          </div>
          <div style={{ border: '1px solid var(--surface-4)', borderTop: 'none', borderRadius: '0 0 8px 8px', maxHeight: 500, overflowY: 'auto' }}>
            {getPortalKeys()
              .filter(({ key, base_es }) => !portalSearch ||
                key.includes(portalSearch.toLowerCase()) ||
                base_es.toLowerCase().includes(portalSearch.toLowerCase()))
              .map(({ key, base_es }, idx) => {
                const currentVal = portalEdits[key]?.[portalLang]
                  ?? PORTAL_TRANSLATIONS[portalLang]?.[key] ?? ''
                const isModified = portalEdits[key]?.[portalLang] !== undefined
                return (
                  <div key={key} style={{ display: 'grid', gridTemplateColumns: '180px 1fr 1fr', gap: 8, padding: '6px 14px', borderBottom: '1px solid var(--surface-4)20', background: idx % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.02)', alignItems: 'center' }}>
                    <span style={{ fontSize: "var(--text-xs)", fontFamily: 'var(--font-mono)', color: isModified ? 'var(--warning)' : 'var(--text-2)' }}>{key}</span>
                    <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{base_es}</span>
                    <input
                      value={currentVal}
                      onChange={e => {
                        setPortalEdits(prev => ({ ...prev, [key]: { ...(prev[key] || {}), [portalLang]: e.target.value } }))
                        setHasUnsaved(true)
                      }}
                      style={{ ...fs, padding: '4px 8px', borderColor: isModified ? 'rgba(245,158,11,0.31)' : 'var(--surface-4)' }}
                      placeholder={base_es}
                    />
                  </div>
                )
              })}
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 14 }}>
            <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
              {getPortalKeys().length} claves · 8 idiomas
              {hasUnsaved && <span style={{ color: 'var(--warning)', marginLeft: 8 }}>⚠ Cambios sin guardar</span>}
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <label style={{ display: 'inline-block', padding: '7px 14px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>
                📤 Importar JSON
                <input type="file" accept="application/json" style={{ display: 'none' }} onChange={e => {
                  const file = e.target.files[0]
                  if (!file) return
                  const reader = new FileReader()
                  reader.onload = evt => {
                    try {
                      const data = JSON.parse(evt.target.result)
                      setPortalEdits(prev => {
                        const merged = { ...prev }
                        for (const [lang, keys] of Object.entries(data)) {
                          for (const [key, value] of Object.entries(keys)) {
                            if (!merged[key]) merged[key] = {}
                            merged[key][lang] = value
                          }
                        }
                        return merged
                      })
                      setHasUnsaved(true)
                      alert('Traducciones importadas. Revisa y guarda para aplicar.')
                    } catch {
                      alert('Error al leer el archivo JSON')
                    }
                  }
                  reader.readAsText(file)
                }} />
              </label>
              <button onClick={() => {
                const data = JSON.stringify(PORTAL_TRANSLATIONS, null, 2)
                const blob = new Blob([data], { type: 'application/json' })
                const url = URL.createObjectURL(blob); const a = document.createElement('a')
                a.href = url; a.download = 'portal_translations.json'; a.click()
                URL.revokeObjectURL(url)
              }} style={{ padding: '7px 14px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>
                📥 Exportar JSON
              </button>
              <button onClick={() => {
                const stored = JSON.parse(localStorage.getItem('contecflow_portal_custom') || '{}')
                for (const [key, langs] of Object.entries(portalEdits)) {
                  for (const [lang, val] of Object.entries(langs)) {
                    if (!stored[lang]) stored[lang] = {}
                    stored[lang][key] = val
                  }
                }
                localStorage.setItem('contecflow_portal_custom', JSON.stringify(stored))
                savePortalTrans(stored)
                setPortalEdits({})
                setHasUnsaved(false)
              }} style={{ padding: '7px 14px', borderRadius: 8, border: 'none', background: hasUnsaved ? 'var(--accent)' : 'var(--surface-4)', color: hasUnsaved ? 'var(--surface-0)' : 'var(--text-2)', cursor: hasUnsaved ? 'pointer' : 'default', fontSize: "var(--text-sm)", fontWeight: 700, fontFamily: 'inherit' }} disabled={!hasUnsaved}>
                {savingPortal ? 'Guardando...' : '💾 Guardar traducciones'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export function LogLevelSection() {
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
      await settingsApi.setLogLevel({ level: lvl })
      toast.success(`Nivel backend cambiado a ${lvl}`)
      qc.invalidateQueries(['log-level'])
    } catch {
      toast.error('Error al cambiar nivel de log')
    }
  }

  const handleSetFrontend = (level) => {
    setFrontendLevel(level)
    localStorage.setItem('contecflow_log_level', level)
    if (window.__contecflowLogger) window.__contecflowLogger.setLevel(level)
    toast.success(`Nivel frontend cambiado a ${level.toUpperCase()} (activo hasta recarga)`)
  }

  const LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
  const LEVEL_COLORS = { DEBUG: 'var(--text-2)', INFO: 'var(--accent)', WARNING: 'var(--warning)', ERROR: 'var(--danger)', CRITICAL: '#c0392b' }

  return (
    <Section icon="📋" title="Nivel de log" description="Controla la verbosidad del backend y frontend">
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16 }}>
        <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: '18px 20px' }}>
          <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 4 }}>🖥️ Servidor (FastAPI / Uvicorn)</div>
          <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 16 }}>
            Cambia el nivel en tiempo real sin reiniciar. Configurable tambien por variable de entorno <code style={{ background: 'var(--surface-3)', padding: '1px 6px', borderRadius: 4, fontSize: "var(--text-xs)" }}>LOG_LEVEL=INFO</code>
          </div>
          {!isLoading && serverLevel && (
            <div style={{ fontSize: "var(--text-sm)", color: 'var(--success)', marginBottom: 12 }}>
              Nivel actual: <strong>{serverLevel.contecflow}</strong>
              <span style={{ color: 'var(--text-2)', marginLeft: 8 }}>
                (root: {serverLevel.root} · uvicorn: {serverLevel.uvicorn || serverLevel.root})
              </span>
            </div>
          )}
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {LEVELS.map(l => (
              <button key={l} onClick={() => handleSetBackend(l)}
                style={{ padding: '6px 14px', borderRadius: 8, border: `1px solid ${backendLevel === l ? LEVEL_COLORS[l] : 'var(--surface-4)'}`,
                  background: backendLevel === l ? (LEVEL_COLORS[l] + '22') : 'var(--surface-3)',
                  color: backendLevel === l ? LEVEL_COLORS[l] : 'var(--text-2)',
                  cursor: 'pointer', fontSize: "var(--text-xs)", fontFamily: 'inherit' }}>
                {l}
              </button>
            ))}
          </div>
        </div>

        <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: '18px 20px' }}>
          <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 4 }}>🌐 Navegador (React / Vite)</div>
          <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 16 }}>
            Controla la consola del navegador. Se guarda en localStorage. Tambien puedes escribir en la consola: <code style={{ background: 'var(--surface-3)', padding: '1px 6px', borderRadius: 4, fontSize: "var(--text-xs)" }}>{"__contecflowLogger.setLevel('debug')"}</code>
          </div>
          <div style={{ fontSize: "var(--text-sm)", color: 'var(--success)', marginBottom: 12 }}>
            Nivel actual: <strong>{frontendLevel.toUpperCase()}</strong>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {['DEBUG', 'INFO', 'WARN', 'ERROR', 'SILENT'].map(l => (
              <button key={l} onClick={() => handleSetFrontend(l.toLowerCase())}
                style={{ padding: '6px 14px', borderRadius: 8,
                  border: `1px solid ${frontendLevel.toUpperCase() === l ? (LEVEL_COLORS[l] || LEVEL_COLORS['ERROR']) : 'var(--surface-4)'}`,
                  background: frontendLevel.toUpperCase() === l ? ((LEVEL_COLORS[l] || LEVEL_COLORS['ERROR']) + '22') : 'var(--surface-3)',
                  color: frontendLevel.toUpperCase() === l ? (LEVEL_COLORS[l] || LEVEL_COLORS['ERROR']) : 'var(--text-2)',
                  cursor: 'pointer', fontSize: "var(--text-xs)", fontFamily: 'inherit' }}>
                {l}
              </button>
            ))}
          </div>
        </div>
      </div>
    </Section>
  )
}

export function EmailInboundSection() {
  const webhookUrl = `${window.location.origin}/api/v1/service-desk/inbound-email`

  return (
    <Section icon="📧" title="Email a ticket" description="Configura la entrada de correos al Service Desk">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* Pasos + URL/Header en grid 2 columnas para aprovechar el ancho */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 14 }}>
          <div style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: '14px 18px', fontSize: "var(--text-sm)" }}>
            <div style={{ fontWeight: 700, marginBottom: 10, color: 'var(--text-1)' }}>¿Cómo funciona?</div>
            <ol style={{ margin: 0, paddingLeft: 20, lineHeight: 1.7, color: 'var(--text-2)' }}>
              <li>Configura tu proveedor de email (Mailgun, SendGrid, Postmark o similar) para reenviar los emails entrantes a la URL de webhook.</li>
              <li>El proveedor envía el email parseado como JSON a Contecflow.</li>
              <li>Contecflow crea el ticket automáticamente con asunto → título y cuerpo → descripción.</li>
              <li>El ticket se asigna al primer agente disponible con política SLA activa.</li>
            </ol>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div>
              <label style={{ display: 'block', fontSize: "var(--text-2xs)", color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700, marginBottom: 6 }}>
                URL del Webhook
              </label>
              <div style={{ display: 'flex', gap: 8 }}>
                <input readOnly value={webhookUrl}
                  style={{ flex: 1, minWidth: 0, padding: '9px 13px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'var(--surface-3)', color: 'var(--text-1)', fontSize: "var(--text-sm)", fontFamily: 'var(--font-mono)', textOverflow: 'ellipsis' }} />
                <button onClick={() => { navigator.clipboard.writeText(webhookUrl) }}
                  style={{ padding: '9px 16px', borderRadius: 8, background: 'var(--accent)', border: 'none', color: '#fff', cursor: 'pointer', fontSize: "var(--text-xs)", fontWeight: 700, flexShrink: 0 }}>
                  Copiar
                </button>
              </div>
              <div style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-3)', marginTop: 4 }}>
                Configura esta URL en tu proveedor de email.
              </div>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: "var(--text-2xs)", color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700, marginBottom: 6 }}>
                Autenticación (X-Contecflow-Email-Secret)
              </label>
              <div style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '10px 14px', fontSize: "var(--text-xs)", color: 'var(--text-2)', lineHeight: 1.6 }}>
                Configura la variable de entorno <code style={{ background: 'var(--surface-4)', padding: '1px 6px', borderRadius: 4, color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}>INBOUND_EMAIL_SECRET</code> en el servidor con un valor secreto aleatorio.
                El relay debe enviar ese mismo valor en la cabecera HTTP <code style={{ background: 'var(--surface-4)', padding: '1px 6px', borderRadius: 4, color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}>X-Contecflow-Email-Secret</code> con cada petición.
              </div>
            </div>
          </div>
        </div>

        {/* Guías por proveedor */}
        <div>
          <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700, marginBottom: 8 }}>
            Guías de configuración por proveedor
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 10 }}>
            {[
              { name: 'Mailgun',  url: 'https://documentation.mailgun.com/docs/mailgun/user-manual/receive-forward-store/', note: 'Routes → Forward → URL' },
              { name: 'SendGrid', url: 'https://docs.sendgrid.com/for-developers/parsing-email/setting-up-the-inbound-parse-webhook', note: 'Inbound Parse Webhook' },
              { name: 'Postmark', url: 'https://postmarkapp.com/developer/user-guide/inbound/how-it-works', note: 'Inbound Message Webhook' },
            ].map(p => (
              <a key={p.name} href={p.url} target="_blank" rel="noopener noreferrer"
                style={{ display: 'block', padding: '12px 16px', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 10, textDecoration: 'none', color: 'var(--text-1)', transition: 'border-color .15s' }}
                onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--accent)' }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--surface-4)' }}
              >
                <div style={{ fontWeight: 700, marginBottom: 4 }}>{p.name} ↗</div>
                <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>{p.note}</div>
              </a>
            ))}
          </div>
        </div>

        {/* Formato JSON esperado */}
        <div>
          <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700, marginBottom: 6 }}>
            Formato JSON esperado <span style={{ fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>(superset compatible con todos los proveedores)</span>
          </div>
          <pre style={{
            background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
            borderRadius: 8, padding: '12px 16px',
            fontSize: "var(--text-xs)", color: 'var(--text-2)',
            margin: 0, overflowX: 'auto', whiteSpace: 'pre',
            fontFamily: 'var(--font-mono)',
          }}>{`{
  "from": "Cliente <cliente@empresa.com>",
  "subject": "Mi impresora no funciona",
  "body-plain": "Texto del email...",
  "text": "Texto del email...",
  "stripped-text": "..."
}`}</pre>
        </div>
      </div>
    </Section>
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

const isInternalKey = (key) => {
  if (!key) return false
  const k = String(key).toLowerCase()
  if (k.includes('.')) return true
  if (k.startsWith('bi_') || k.startsWith('sd_') || k.startsWith('ml_')) return true
  if (k.startsWith('_') || k.startsWith('cache_') || k.startsWith('feedback_')) return true
  return false
}

const groupForKey = (key) => {
  const k = String(key).toLowerCase()
  for (const g of SYSTEM_KEY_GROUPS) {
    if (g.prefixes.some(p => k.startsWith(p))) return g.label
  }
  return 'Otros'
}

const dedupeSettingsByKey = (rows) => {
  const byKey = new Map()
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

function tryFormatValue(raw) {
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

function SystemSettingItem({ setting }) {
  const [expanded, setExpanded] = useState(false)
  const formatted = tryFormatValue(setting.value)
  const isJson = formatted && (formatted.startsWith('{') || formatted.startsWith('['))
  const lineCount = formatted ? formatted.split('\n').length : 0
  const preview = formatted
    ? formatted.split('\n').slice(0, 3).join('\n') + (lineCount > 3 ? '\n…' : '')
    : '—'

  return (
    <div style={{
      background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
      borderRadius: 10, padding: '12px 14px',
      minWidth: 0, overflow: 'hidden',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 6 }}>
        <code style={{
          fontSize: 'var(--text-xs)', color: 'var(--accent)',
          fontFamily: 'var(--font-mono)', wordBreak: 'break-all',
          flex: 1, minWidth: 0,
        }}>{setting.key}</code>
        <button
          type="button"
          onClick={() => setExpanded(v => !v)}
          style={{
            background: 'transparent', border: '1px solid var(--surface-4)',
            borderRadius: 6, padding: '3px 9px',
            color: 'var(--text-2)', fontFamily: 'inherit',
            fontSize: 'var(--text-2xs)', cursor: 'pointer', flexShrink: 0,
          }}
        >{expanded ? 'Ocultar' : 'Ver completo'}</button>
      </div>
      {setting.description && (
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginBottom: 6 }}>
          {setting.description}
        </div>
      )}
      <pre style={{
        background: 'var(--surface-1)', border: '1px solid var(--surface-4)',
        borderRadius: 6, padding: '8px 10px',
        fontSize: 'var(--text-2xs)', color: 'var(--text-2)',
        margin: 0, fontFamily: 'var(--font-mono)',
        maxHeight: expanded ? 'none' : 64,
        overflow: expanded ? 'auto' : 'hidden',
        whiteSpace: 'pre',
        ...(expanded ? { overflowX: 'auto' } : {}),
      }}>{expanded ? (formatted || '—') : preview}</pre>
      <div style={{ marginTop: 4, fontSize: 'var(--text-2xs)', color: 'var(--text-3)' }}>
        {isJson ? `JSON · ${lineCount} líneas` : `Texto · ${(setting.value || '').length} caracteres`}
      </div>
    </div>
  )
}

export function SystemStateSection() {
  const { data: settings = [], isLoading } = useQuery({
    queryKey: ['settings-general'],
    queryFn: () => settingsApi.general().then(r => r.data),
  })

  const internal = dedupeSettingsByKey((settings || []).filter(s => isInternalKey(s.key)))
  // Agrupar por grupo lógico
  const grouped = {}
  for (const s of internal) {
    const label = groupForKey(s.key)
    if (!grouped[label]) grouped[label] = []
    grouped[label].push(s)
  }
  const orderedGroups = SYSTEM_KEY_GROUPS.map(g => g.label).filter(l => grouped[l]?.length)
  if (grouped['Otros']?.length) orderedGroups.push('Otros')
  const groupMeta = Object.fromEntries(SYSTEM_KEY_GROUPS.map(g => [g.label, g]))

  return (
    <Section icon="🔧" title="Estado del sistema" description="Lectura del estado interno persistido por servicios BI / ITSM (admin · solo lectura)">
      {isLoading ? (
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)' }}>Cargando…</div>
      ) : internal.length === 0 ? (
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)', textAlign: 'center', padding: 16 }}>
          Sin estado interno registrado.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
          <div style={{
            background: 'color-mix(in srgb, var(--warning) 8%, var(--surface-3))',
            border: '1px solid color-mix(in srgb, var(--warning) 30%, var(--surface-4))',
            borderRadius: 10, padding: '10px 14px',
            fontSize: 'var(--text-xs)', color: 'var(--text-2)', lineHeight: 1.5,
          }}>
            <strong style={{ color: 'var(--warning)' }}>⚠ Vista de solo lectura.</strong>{' '}
            Estos blobs son estado interno de servicios y se gestionan desde sus paneles dedicados
            (<code style={{ fontFamily: 'var(--font-mono)' }}>/bi/govern</code>, <code style={{ fontFamily: 'var(--font-mono)' }}>/bi/data</code>,
            <code style={{ fontFamily: 'var(--font-mono)' }}>/service-desk → Voz/ML/Auto-Resolución</code>).
            Editarlos directamente puede romper el módulo correspondiente.
          </div>

          {orderedGroups.map(label => {
            const meta = groupMeta[label]
            const items = grouped[label]
            return (
              <div key={label}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8, gap: 8 }}>
                  <div>
                    <div style={{
                      fontSize: 'var(--text-2xs)', color: 'var(--text-3)',
                      textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700,
                    }}>{meta?.icon || '📦'} {label}</div>
                    {meta?.description && (
                      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginTop: 2 }}>
                        {meta.description}
                      </div>
                    )}
                  </div>
                  <span style={{
                    fontSize: 'var(--text-2xs)', fontWeight: 700,
                    color: 'var(--text-2)', background: 'var(--surface-4)',
                    borderRadius: 999, padding: '2px 9px',
                  }}>{items.length}</span>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: 10 }}>
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
    </Section>
  )
}

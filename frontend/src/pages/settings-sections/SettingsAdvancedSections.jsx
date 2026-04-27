import React, { useEffect, useState } from 'react'
import { useToast } from '../../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAppLang } from '../../i18n/AppLangContext'
import { APP_LANGUAGES, loadLanguage, getAllKeys, es } from '../../i18n/appTranslations.mjs'
import { PORTAL_TRANSLATIONS, PORTAL_LANGUAGES, getPortalKeys } from '../../i18n/portalTranslations'
import { extractErr } from '../../utils/helpers'
import { Card } from '../../components/ui'
import api from '../../services/api'

function Section({ icon, title, description, children }) {
  return (
    <Card style={{ marginBottom: 24 }}>
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontSize: 16, fontWeight: 700 }}>{icon} {title}</div>
        {description && <div style={{ fontSize: 13, color: 'var(--text-2)', marginTop: 4 }}>{description}</div>}
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
    queryFn: () => api.get('/portal/translations').then(r => r.data).catch(() => ({})),
  })
  const { mutate: savePortalTrans, isPending: savingPortal } = useMutation({
    mutationFn: d => api.post('/portal/translations', d),
    onSuccess: () => { qc.invalidateQueries(['portal-translations']); toast.success(t('i18n.saved_ok')) },
    onError: e => toast.error(extractErr(e, 'Error')),
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

  const fs = { width: '100%', background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '6px 10px', color: 'var(--text-1)', fontSize: 12, outline: 'none', fontFamily: 'inherit' }
  const card = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12 }

  if (loadingAppLang) return <div>Cargando traducciones...</div>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', gap: 6, borderBottom: '1px solid var(--surface-4)', paddingBottom: 10 }}>
        {[['operator', '⚙️ Idioma del operador'], ['app', '🖥 Traducciones del back-office'], ['portal', '🌐 Portal cliente']].map(([id, label]) => (
          <button key={id} onClick={() => setActiveTab(id)}
            style={{ padding: '7px 16px', borderRadius: 8, border: `1px solid ${activeTab === id ? 'var(--accent-glow)' : 'var(--surface-4)'}`, background: activeTab === id ? 'var(--accent-muted)' : 'transparent', color: activeTab === id ? 'var(--accent)' : 'var(--text-2)', fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>
            {label}
          </button>
        ))}
      </div>

      {activeTab === 'operator' && (
        <div style={card}>
          <div style={{ padding: '20px 24px', borderBottom: '1px solid var(--surface-4)' }}>
            <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 4 }}>Idioma del operador (back-office)</div>
            <div style={{ fontSize: 12, color: 'var(--text-2)' }}>
              Idioma de la interfaz interna. Cada usuario puede configurar el suyo desde aquí. Se guarda en el navegador.
            </div>
          </div>
          <div style={{ padding: '20px 24px' }}>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              {APP_LANGUAGES.map(l => (
                <button key={l.code} onClick={() => setOperatorLang(l.code)}
                  style={{ padding: '12px 22px', borderRadius: 10, border: `2px solid ${operatorLang === l.code ? 'var(--accent)' : 'var(--surface-4)'}`, background: operatorLang === l.code ? 'var(--accent-muted)' : 'var(--surface-2)', color: operatorLang === l.code ? 'var(--accent)' : 'var(--text-2)', fontSize: 15, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit', transition: 'all 0.15s' }}>
                  {l.flag} {l.label}
                  {operatorLang === l.code && <span style={{ marginLeft: 8, fontSize: 12 }}>✓</span>}
                </button>
              ))}
            </div>
            <div style={{ marginTop: 16, padding: '10px 14px', background: 'var(--surface-1)', borderRadius: 8, fontSize: 12, color: 'var(--text-2)' }}>
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
              <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 4 }}>IDIOMA A EDITAR</div>
              <div style={{ display: 'flex', gap: 6 }}>
                {APP_LANGUAGES.filter(l => l.code !== 'es').map(l => (
                  <button key={l.code} onClick={() => setAppLang(l.code)}
                    style={{ padding: '7px 16px', borderRadius: 8, border: `1px solid ${appLang === l.code ? 'var(--accent-glow)' : 'var(--surface-4)'}`, background: appLang === l.code ? 'var(--accent-muted)' : 'transparent', color: appLang === l.code ? 'var(--accent)' : 'var(--text-2)', fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>
                    {l.flag} {l.label}
                  </button>
                ))}
              </div>
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 4 }}>BUSCAR CLAVE</div>
              <input value={searchKey} onChange={e => setSearchKey(e.target.value)}
                placeholder="Buscar clave de traduccion" aria-label="Buscar clave de traduccion" style={{ ...fs, width: 280 }} />
            </div>
            <div>
              <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 4 }}>MODULO</div>
              <select value={activeModule} onChange={e => setActiveModule(e.target.value)} style={{ ...fs, width: 160 }}>
                {modules.map(m => <option key={m} value={m}>{m === 'all' ? 'Todos los modulos' : m}</option>)}
              </select>
            </div>
            <div>
              <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 4 }}>IMPORTAR JSON</div>
              <label style={{ display: 'inline-block', padding: '7px 14px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>
                📤 Importar JSON
                <input type="file" accept="application/json" style={{ display: 'none' }} onChange={importJSON} />
              </label>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '140px 1fr 1fr', gap: 8, padding: '8px 14px', background: 'var(--surface-1)', borderRadius: '8px 8px 0 0', fontSize: 10, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase' }}>
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
                    <span style={{ fontSize: 10, color: 'var(--text-3)', display: 'block' }}>{item.module}</span>
                    <span style={{ fontSize: 11, fontFamily: 'monospace', color: isModified ? 'var(--warning)' : 'var(--text-2)' }}>{item.key}</span>
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
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
              <div style={{ padding: '10px 14px', fontSize: 12, color: 'var(--text-2)', textAlign: 'center' }}>
                Mostrando 200 de {filteredKeys.length} claves. Usa el filtro para buscar mas especifico.
              </div>
            )}
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 14 }}>
            <div style={{ fontSize: 12, color: 'var(--text-2)' }}>
              {filteredKeys.length} claves · {allKeys.length} total · {hasUnsaved && <span style={{ color: 'var(--warning)' }}>⚠ Cambios sin guardar</span>}
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button onClick={exportJSON}
                style={{ padding: '7px 14px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>
                📥 Exportar JSON
              </button>
              <button onClick={saveAppTrans} disabled={!hasUnsaved}
                style={{ padding: '7px 14px', borderRadius: 8, border: 'none', background: hasUnsaved ? 'var(--accent)' : 'var(--surface-4)', color: hasUnsaved ? 'var(--surface-0)' : 'var(--text-2)', cursor: hasUnsaved ? 'pointer' : 'default', fontSize: 12, fontWeight: 700, fontFamily: 'inherit' }}>
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
              <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 4 }}>IDIOMA A EDITAR</div>
              <div style={{ display: 'flex', gap: 6 }}>
                {PORTAL_LANGUAGES.filter(l => l.code !== 'es').map(l => (
                  <button key={l.code} onClick={() => setPortalLang(l.code)}
                    style={{ padding: '7px 16px', borderRadius: 8, border: `1px solid ${portalLang === l.code ? 'var(--accent-glow)' : 'var(--surface-4)'}`, background: portalLang === l.code ? 'var(--accent-muted)' : 'transparent', color: portalLang === l.code ? 'var(--accent)' : 'var(--text-2)', fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>
                    {l.flag} {l.label}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 4 }}>BUSCAR</div>
              <input value={portalSearch} onChange={e => setPortalSearch(e.target.value)}
                placeholder="Buscar texto del portal" aria-label="Buscar texto del portal" style={{ ...fs, width: 260 }} />
            </div>
            <div>
              <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 4 }}>IMPORTAR JSON</div>
              <label style={{ display: 'inline-block', padding: '7px 14px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>
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

          <div style={{ display: 'grid', gridTemplateColumns: '180px 1fr 1fr', gap: 8, padding: '8px 14px', background: 'var(--surface-1)', borderRadius: '8px 8px 0 0', fontSize: 10, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase' }}>
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
                    <span style={{ fontSize: 11, fontFamily: 'monospace', color: isModified ? 'var(--warning)' : 'var(--text-2)' }}>{key}</span>
                    <span style={{ fontSize: 12, color: 'var(--text-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{base_es}</span>
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
            <div style={{ fontSize: 12, color: 'var(--text-2)' }}>
              {getPortalKeys().length} claves · 8 idiomas
              {hasUnsaved && <span style={{ color: 'var(--warning)', marginLeft: 8 }}>⚠ Cambios sin guardar</span>}
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <label style={{ display: 'inline-block', padding: '7px 14px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>
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
              }} style={{ padding: '7px 14px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>
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
              }} style={{ padding: '7px 14px', borderRadius: 8, border: 'none', background: hasUnsaved ? 'var(--accent)' : 'var(--surface-4)', color: hasUnsaved ? 'var(--surface-0)' : 'var(--text-2)', cursor: hasUnsaved ? 'pointer' : 'default', fontSize: 12, fontWeight: 700, fontFamily: 'inherit' }} disabled={!hasUnsaved}>
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
    queryFn: () => api.get('/settings/log-level').then(r => r.data),
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
      await api.post('/settings/log-level', { level: lvl })
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
      <div style={{ display: 'flex', flexDirection: 'column', gap: 24, maxWidth: 640 }}>
        <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: '18px 20px' }}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 4 }}>🖥️ Servidor (FastAPI / Uvicorn)</div>
          <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 16 }}>
            Cambia el nivel en tiempo real sin reiniciar. Configurable tambien por variable de entorno <code style={{ background: 'var(--surface-3)', padding: '1px 6px', borderRadius: 4, fontSize: 11 }}>LOG_LEVEL=INFO</code>
          </div>
          {!isLoading && serverLevel && (
            <div style={{ fontSize: 12, color: 'var(--success)', marginBottom: 12 }}>
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
                  cursor: 'pointer', fontSize: 12, fontWeight: 600, fontFamily: 'inherit' }}>
                {l}
              </button>
            ))}
          </div>
        </div>

        <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: '18px 20px' }}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 4 }}>🌐 Navegador (React / Vite)</div>
          <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 16 }}>
            Controla la consola del navegador. Se guarda en localStorage. Tambien puedes escribir en la consola: <code style={{ background: 'var(--surface-3)', padding: '1px 6px', borderRadius: 4, fontSize: 11 }}>{"__contecflowLogger.setLevel('debug')"}</code>
          </div>
          <div style={{ fontSize: 12, color: 'var(--success)', marginBottom: 12 }}>
            Nivel actual: <strong>{frontendLevel.toUpperCase()}</strong>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {['DEBUG', 'INFO', 'WARN', 'ERROR', 'SILENT'].map(l => (
              <button key={l} onClick={() => handleSetFrontend(l.toLowerCase())}
                style={{ padding: '6px 14px', borderRadius: 8,
                  border: `1px solid ${frontendLevel.toUpperCase() === l ? (LEVEL_COLORS[l] || LEVEL_COLORS['ERROR']) : 'var(--surface-4)'}`,
                  background: frontendLevel.toUpperCase() === l ? ((LEVEL_COLORS[l] || LEVEL_COLORS['ERROR']) + '22') : 'var(--surface-3)',
                  color: frontendLevel.toUpperCase() === l ? (LEVEL_COLORS[l] || LEVEL_COLORS['ERROR']) : 'var(--text-2)',
                  cursor: 'pointer', fontSize: 12, fontWeight: 600, fontFamily: 'inherit' }}>
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
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20, maxWidth: 720 }}>
        <div style={{ background: 'var(--surface-3)', borderRadius: 10, padding: '16px 20px', fontSize: 13 }}>
          <div style={{ fontWeight: 600, marginBottom: 10 }}>¿Como funciona?</div>
          <ol style={{ margin: 0, paddingLeft: 20, lineHeight: 2, color: 'var(--text-2)' }}>
            <li>Configura tu proveedor de email (Mailgun, SendGrid, Postmark o similar) para reenviar los emails entrantes a la URL de webhook.</li>
            <li>El proveedor envia el email parseado como JSON a Contecflow.</li>
            <li>Contecflow crea el ticket automaticamente con asunto→titulo y cuerpo→descripcion.</li>
            <li>El ticket se asigna al primer agente disponible con politica SLA activa.</li>
          </ol>
        </div>

        <div>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-3)', marginBottom: 6 }}>
            URL del Webhook (configura en tu proveedor de email)
          </label>
          <div style={{ display: 'flex', gap: 8 }}>
            <input readOnly value={webhookUrl}
              style={{ flex: 1, padding: '9px 12px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'var(--surface-2)', color: 'var(--text-1)', fontSize: 13, fontFamily: 'monospace' }} />
            <button onClick={() => { navigator.clipboard.writeText(webhookUrl) }}
              style={{ padding: '9px 16px', borderRadius: 8, background: 'var(--accent)', border: 'none', color: '#fff', cursor: 'pointer', fontSize: 12, fontWeight: 600 }}>
              Copiar
            </button>
          </div>
        </div>

        <div>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-3)', marginBottom: 6 }}>
            Header de autenticacion (X-Contecflow-Email-Secret)
          </label>
          <div style={{ background: 'var(--surface-3)', borderRadius: 8, padding: '10px 14px', fontSize: 12, color: 'var(--text-2)', fontFamily: 'monospace' }}>
            Configura la variable de entorno <strong style={{ color: 'var(--accent)' }}>INBOUND_EMAIL_SECRET</strong> en el servidor con un valor secreto aleatorio.
            El relay de email debe enviar ese mismo valor en la cabecera HTTP <strong>X-Contecflow-Email-Secret</strong> con cada peticion.
          </div>
        </div>

        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-3)', marginBottom: 10 }}>Guias de configuracion por proveedor</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
            {[
              { name: 'Mailgun', url: 'https://documentation.mailgun.com/docs/mailgun/user-manual/receive-forward-store/', note: 'Routes -> Forward -> URL' },
              { name: 'SendGrid', url: 'https://docs.sendgrid.com/for-developers/parsing-email/setting-up-the-inbound-parse-webhook', note: 'Inbound Parse Webhook' },
              { name: 'Postmark', url: 'https://postmarkapp.com/developer/user-guide/inbound/how-it-works', note: 'Inbound Message Webhook' },
            ].map(p => (
              <a key={p.name} href={p.url} target="_blank" rel="noopener noreferrer"
                style={{ display: 'block', padding: '12px 16px', background: 'var(--surface-3)', borderRadius: 10, textDecoration: 'none', color: 'var(--text-1)' }}>
                <div style={{ fontWeight: 600, marginBottom: 4 }}>{p.name}</div>
                <div style={{ fontSize: 11, color: 'var(--text-3)' }}>{p.note}</div>
              </a>
            ))}
          </div>
        </div>

        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-3)', marginBottom: 6 }}>Formato JSON esperado (superset compatible con todos los proveedores)</div>
          <pre style={{ background: 'var(--surface-3)', borderRadius: 8, padding: '12px 16px', fontSize: 11, color: 'var(--text-2)', overflow: 'auto', margin: 0 }}>{`{
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

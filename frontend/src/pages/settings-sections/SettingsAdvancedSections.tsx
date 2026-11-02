import type { CSSProperties, ReactNode } from 'react'
import { Fragment, useState, useEffect, useMemo } from 'react'
import { useToast } from '../../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAppLang } from '../../i18n/AppLangContext'
import { APP_LANGUAGES, AVAILABLE_LANGUAGES, loadLanguage, getAllKeys, es } from '../../i18n/appTranslations.mjs'
import { PORTAL_TRANSLATIONS, PORTAL_LANGUAGES, getPortalKeys } from '../../i18n/portalTranslations'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { Card } from '../../components/ui'
import { portalClientsApi, settingsApi } from '../../services/api'

function Section({ icon, title, description, children }: { icon?: ReactNode; title?: ReactNode; description?: ReactNode; children?: ReactNode }) {
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
  const { lang: operatorLang, setLang: setOperatorLang, t, setCustomTranslations, customTrans } = useAppLang()

  const { data: _portalTrans = {} } = useQuery({
    queryKey: ['portal-translations'],
    queryFn: () => portalClientsApi.translations().then(r => r.data).catch(() => ({})),
  })
  const { mutate: savePortalTrans, isPending: savingPortal } = useMutation({
    mutationFn: (d: any) => portalClientsApi.saveTranslations(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['portal-translations'] }); toast.success(t('i18n.saved_ok')) },
    onError: (e: any) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const [activeTab, setActiveTab] = useState('operator')
  const [appLang, setAppLang] = useState('en')
  const [appTranslations, setAppTranslations] = useState<Record<string, any>>({})
  const [loadingAppLang, setLoadingAppLang] = useState(true)
  const [portalLang, setPortalLang] = useState('en')
  const [searchKey, setSearchKey] = useState('')
  const [activeModule, setActiveModule] = useState('all')
  const [appEdits, setAppEdits] = useState<Record<string, any>>({})
  const [portalEdits, setPortalEdits] = useState<Record<string, any>>({})
  const [portalSearch, setPortalSearch] = useState('')
  const [hasUnsaved, setHasUnsaved] = useState(false)

  const allKeys: any[] = getAllKeys(es)
  const modules = ['all', ...new Set(allKeys.map((k: any) => k.module))]

  useEffect(() => {
    let cancelled = false
    setLoadingAppLang(true)
    loadLanguage(appLang).then((tr: any) => {
      if (!cancelled) {
        setAppTranslations(tr)
        setLoadingAppLang(false)
      }
    })
    return () => { cancelled = true }
  }, [appLang])

  const filteredKeys = allKeys.filter((k: any) => {
    const matchMod = activeModule === 'all' || k.module === activeModule
    const matchSrc = !searchKey || k.key.includes(searchKey.toLowerCase()) ||
      k.base_es.toLowerCase().includes(searchKey.toLowerCase()) ||
      k.full_key.includes(searchKey.toLowerCase())
    return matchMod && matchSrc
  })

  const getAppVal = (lang: string, module: string, key: string) =>
    (lang === appLang ? (
      appEdits?.[module]?.[key] ??
      (customTrans as any)?.[module]?.[key] ??
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

  const importJSON = (e: any) => {
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

  const saveAppTrans = () => {
    const merged: Record<string, any> = { ...customTrans }
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

  const fs: CSSProperties = { width: '100%', background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '6px 10px', color: 'var(--text-1)', fontSize: "var(--text-sm)", outline: 'none', fontFamily: 'inherit' }
  const card: CSSProperties = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12 }

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
            <div style={{ fontSize: "var(--text-md)", fontWeight: 700, marginBottom: 4 }}>{t('settingsadvanced.idioma_del_operador_back_office')}</div>
            <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
              {t('settingsadvanced.idioma_de_la_interfaz_interna_cada_usuario')}
            </div>
          </div>
          <div style={{ padding: '20px 24px' }}>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              {/* Operator-facing picker: only well-covered locales (pl/zh hidden). */}
              {AVAILABLE_LANGUAGES.map(l => (
                <button key={l.code} onClick={() => setOperatorLang(l.code)}
                  style={{ padding: '12px 22px', borderRadius: 10, border: `2px solid ${operatorLang === l.code ? 'var(--accent)' : 'var(--surface-4)'}`, background: operatorLang === l.code ? 'var(--accent-muted)' : 'var(--surface-2)', color: operatorLang === l.code ? 'var(--accent)' : 'var(--text-2)', fontSize: "var(--text-md-em)", fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit', transition: 'all 0.15s' }}>
                  {l.flag} {l.label}
                  {operatorLang === l.code && <span style={{ marginLeft: 8, fontSize: "var(--text-sm)" }}>✓</span>}
                </button>
              ))}
            </div>
            <div style={{ marginTop: 16, padding: '10px 14px', background: 'var(--surface-1)', borderRadius: 8, fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
              {t('settingsadvanced.al_cambiar_el_idioma_los_menus_titulos')}
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
                placeholder={t('settingsadvanced.buscar_clave_de_traduccion')} aria-label={t('settingsadvanced.buscar_clave_de_traduccion')} style={{ ...fs, width: 280 }} />
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
                {t('settingsadvanced.mostrando_200_de')} {filteredKeys.length} {t('settingsadvanced.claves_usa_el_filtro_para_buscar_mas')}
              </div>
            )}
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 14 }}>
            <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
              {filteredKeys.length} claves · {allKeys.length} total · {hasUnsaved && <span style={{ color: 'var(--warning)' }}>{t('settingsadvanced.cambios_sin_guardar')}</span>}
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
                placeholder={t('settingsadvanced.buscar_texto_del_portal')} aria-label={t('settingsadvanced.buscar_texto_del_portal')} style={{ ...fs, width: 260 }} />
            </div>
            <div>
              <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginBottom: 4 }}>IMPORTAR JSON</div>
              <label style={{ display: 'inline-block', padding: '7px 14px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>
                📤 Importar JSON
                <input type="file" accept="application/json" style={{ display: 'none' }} onChange={e => {
                  const file = e.target.files?.[0]
                  if (!file) return
                  const reader = new FileReader()
                  reader.onload = evt => {
                    try {
                      const data = JSON.parse(String(evt.target?.result ?? ''))
                      setPortalEdits((prev: Record<string, any>) => {
                        const merged: Record<string, any> = { ...prev }
                        for (const [lang, keys] of Object.entries(data as Record<string, any>)) {
                          for (const [key, value] of Object.entries(keys as Record<string, any>)) {
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
                  ?? (PORTAL_TRANSLATIONS as any)[portalLang]?.[key] ?? ''
                const isModified = portalEdits[key]?.[portalLang] !== undefined
                return (
                  <div key={key} style={{ display: 'grid', gridTemplateColumns: '180px 1fr 1fr', gap: 8, padding: '6px 14px', borderBottom: '1px solid var(--surface-4)20', background: idx % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.02)', alignItems: 'center' }}>
                    <span style={{ fontSize: "var(--text-xs)", fontFamily: 'var(--font-mono)', color: isModified ? 'var(--warning)' : 'var(--text-2)' }}>{key}</span>
                    <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{base_es}</span>
                    <input
                      value={currentVal}
                      onChange={e => {
                        setPortalEdits((prev: Record<string, any>) => ({ ...prev, [key]: { ...(prev[key] || {}), [portalLang]: e.target.value } }))
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
              {hasUnsaved && <span style={{ color: 'var(--warning)', marginLeft: 8 }}>{t('settingsadvanced.cambios_sin_guardar')}</span>}
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <label style={{ display: 'inline-block', padding: '7px 14px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>
                📤 Importar JSON
                <input type="file" accept="application/json" style={{ display: 'none' }} onChange={e => {
                  const file = e.target.files?.[0]
                  if (!file) return
                  const reader = new FileReader()
                  reader.onload = evt => {
                    try {
                      const data = JSON.parse(String(evt.target?.result ?? ''))
                      setPortalEdits((prev: Record<string, any>) => {
                        const merged: Record<string, any> = { ...prev }
                        for (const [lang, keys] of Object.entries(data as Record<string, any>)) {
                          for (const [key, value] of Object.entries(keys as Record<string, any>)) {
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
                const stored: Record<string, any> = JSON.parse(localStorage.getItem('contecflow_portal_custom') || '{}')
                for (const [key, langs] of Object.entries(portalEdits)) {
                  for (const [lang, val] of Object.entries(langs as Record<string, any>)) {
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
  const { t } = useAppLang()
  const toast = useToast()
  const [backendLevel, setBackendLevel] = useState('')
  const [frontendLevel, setFrontendLevel] = useState(
    localStorage.getItem('contecflow_log_level') || (import.meta.env.DEV ? 'debug' : 'warn')
  )
  const qc = useQueryClient()

  const { data: serverLevel, isLoading } = useQuery<any>({
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
      await settingsApi.setLogLevel({ level: lvl as any })
      toast.success(`Nivel backend cambiado a ${lvl}`)
      qc.invalidateQueries({ queryKey: ['log-level'] })
    } catch {
      toast.error('Error al cambiar nivel de log')
    }
  }

  const handleSetFrontend = (level: string) => {
    setFrontendLevel(level)
    localStorage.setItem('contecflow_log_level', level)
    if ((window as any).__contecflowLogger) (window as any).__contecflowLogger.setLevel(level)
    toast.success(`Nivel frontend cambiado a ${level.toUpperCase()} (activo hasta recarga)`)
  }

  const LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
  const LEVEL_COLORS: Record<string, string> = { DEBUG: 'var(--text-2)', INFO: 'var(--accent)', WARNING: 'var(--warning)', ERROR: 'var(--danger)', CRITICAL: '#c0392b' }

  return (
    <Section icon="📋" title={t('settingsadvanced.nivel_de_log')} description="Controla la verbosidad del backend y frontend">
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16 }}>
        <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: '18px 20px' }}>
          <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 4 }}>🖥️ Servidor (FastAPI / Uvicorn)</div>
          <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 16 }}>
            {t('settingsadvanced.cambia_el_nivel_en_tiempo_real_sin')} <code style={{ background: 'var(--surface-3)', padding: '1px 6px', borderRadius: 4, fontSize: "var(--text-xs)" }}>LOG_LEVEL=INFO</code>
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
            {t('settingsadvanced.controla_la_consola_del_navegador_se_guarda')} <code style={{ background: 'var(--surface-3)', padding: '1px 6px', borderRadius: 4, fontSize: "var(--text-xs)" }}>{"__contecflowLogger.setLevel('debug')"}</code>
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
  const { t } = useAppLang()
  const webhookUrl = `${window.location.origin}/api/v1/service-desk/inbound-email`

  return (
    <Section icon="📧" title="Email a ticket" description="Configura la entrada de correos al Service Desk">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* Pasos + URL/Header en grid 2 columnas para aprovechar el ancho */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 14 }}>
          <div style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: '14px 18px', fontSize: "var(--text-sm)" }}>
            <div style={{ fontWeight: 700, marginBottom: 10, color: 'var(--text-1)' }}>{t('settingsadvanced.como_funciona')}</div>
            <ol style={{ margin: 0, paddingLeft: 20, lineHeight: 1.7, color: 'var(--text-2)' }}>
              <li>{t('settingsadvanced.configura_tu_proveedor_de_email_mailgun_sendgrid')}</li>
              <li>{t('settingsadvanced.el_proveedor_envia_el_email_parseado_como')}</li>
              <li>{t('settingsadvanced.contecflow_crea_el_ticket_automaticamente_con_asunto')}</li>
              <li>{t('settingsadvanced.el_ticket_se_asigna_al_primer_agente')}</li>
            </ol>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div>
              <label style={{ display: 'block', fontSize: "var(--text-2xs)", color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700, marginBottom: 6 }}>
                {t('settingsadvanced.url_del_webhook')}
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
                {t('settingsadvanced.configura_esta_url_en_tu_proveedor_de')}
              </div>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: "var(--text-2xs)", color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700, marginBottom: 6 }}>
                {t('settingsadvanced.autenticacion_x_contecflow_email_secret')}
              </label>
              <div style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '10px 14px', fontSize: "var(--text-xs)", color: 'var(--text-2)', lineHeight: 1.6 }}>
                {t('settingsadvanced.configura_la_variable_de_entorno')} <code style={{ background: 'var(--surface-4)', padding: '1px 6px', borderRadius: 4, color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}>INBOUND_EMAIL_SECRET</code> {t('settingsadvanced.en_el_servidor_con_un_valor_secreto')} <code style={{ background: 'var(--surface-4)', padding: '1px 6px', borderRadius: 4, color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}>X-Contecflow-Email-Secret</code> {t('settingsadvanced.con_cada_peticion')}
              </div>
            </div>
          </div>
        </div>

        {/* Guías por proveedor */}
        <div>
          <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700, marginBottom: 8 }}>
            {t('settingsadvanced.guias_de_configuracion_por_proveedor')}
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
            Formato JSON esperado <span style={{ fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>{t('settingsadvanced.superset_compatible_con_todos_los_proveedores')}</span>
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

const isInternalKey = (key: any) => {
  if (!key) return false
  const k = String(key).toLowerCase()
  if (k.includes('.')) return true
  if (k.startsWith('bi_') || k.startsWith('sd_') || k.startsWith('ml_')) return true
  if (k.startsWith('_') || k.startsWith('cache_') || k.startsWith('feedback_')) return true
  return false
}

const groupForKey = (key: any) => {
  const k = String(key).toLowerCase()
  for (const g of SYSTEM_KEY_GROUPS) {
    if (g.prefixes.some(p => k.startsWith(p))) return g.label
  }
  return 'Otros'
}

const dedupeSettingsByKey = (rows: any[]) => {
  const byKey = new Map<string, any>()
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

function tryFormatValue(raw: any) {
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

function SystemSettingItem({ setting }: { setting: any }) {
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
  const { t } = useAppLang()
  const { data: settings = [], isLoading } = useQuery<any[]>({
    queryKey: ['settings-general'],
    queryFn: () => settingsApi.general().then(r => r.data as any),
  })

  const internal = dedupeSettingsByKey((settings || []).filter((s: any) => isInternalKey(s.key)))
  // Agrupar por grupo lógico
  const grouped: Record<string, any[]> = {}
  for (const s of internal) {
    const label = groupForKey(s.key)
    if (!grouped[label]) grouped[label] = []
    grouped[label].push(s)
  }
  const orderedGroups = SYSTEM_KEY_GROUPS.map(g => g.label).filter(l => grouped[l]?.length)
  if (grouped['Otros']?.length) orderedGroups.push('Otros')
  const groupMeta = Object.fromEntries(SYSTEM_KEY_GROUPS.map(g => [g.label, g]))

  return (
    <Section icon="🔧" title={t('settingsadvanced.estado_del_sistema')} description="Lectura del estado interno persistido por servicios BI / ITSM (admin · solo lectura)">
      {isLoading ? (
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)' }}>Cargando…</div>
      ) : internal.length === 0 ? (
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)', textAlign: 'center', padding: 16 }}>
          {t('settingsadvanced.sin_estado_interno_registrado')}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
          <div style={{
            background: 'color-mix(in srgb, var(--warning) 8%, var(--surface-3))',
            border: '1px solid color-mix(in srgb, var(--warning) 30%, var(--surface-4))',
            borderRadius: 10, padding: '10px 14px',
            fontSize: 'var(--text-xs)', color: 'var(--text-2)', lineHeight: 1.5,
          }}>
            <strong style={{ color: 'var(--warning)' }}>{t('settingsadvanced.vista_de_solo_lectura')}</strong>{' '}
            {t('settingsadvanced.estos_blobs_son_estado_interno_de_servicios')}<code style={{ fontFamily: 'var(--font-mono)' }}>/bi/govern</code>, <code style={{ fontFamily: 'var(--font-mono)' }}>/bi/data</code>,
            <code style={{ fontFamily: 'var(--font-mono)' }}>{t('settingsadvanced.service_desk_voz_ml_auto_resolucion')}</code>{t('settingsadvanced.editarlos_directamente_puede_romper_el_modulo_correspondiente')}
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
                  {items.map((s: any, idx: number) => {
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


// ── Runtime-flag groups (env → UI migration) ──────────────────────────────────
// Generic editor for groups declared in app/services/settings_service.py.
// Each row in the response is {key, type, label, value} — we render a typed
// input per row and PUT back to /settings/runtime/{group}/{key}.

const RUNTIME_GROUPS = [
  { id: 'sla',             label: 'SLA',                description: 'Tiempos por prioridad, jornada sin política y umbral de riesgo.' },
  { id: 'service_desk',    label: 'Service Desk',       description: 'A quién se avisa de cada cambio de ticket y cómo se entrega.' },
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
]


export function RuntimeGroupEditor({ groupId, description }: { groupId: string; description?: string }) {
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()

  const { data, isLoading, isError, error } = useQuery<any>({
    queryKey: ['runtime-flags', groupId],
    queryFn: () => settingsApi.runtimeGroup(groupId).then(r => r.data),
  })

  const { mutate: save, isPending } = useMutation({
    mutationFn: ({ key, value }: { key: string; value: any }) => settingsApi.setRuntime(groupId, key, value),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['runtime-flags', groupId] })
      toast.success('Guardado')
    },
    onError: (e: any) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const [draft, setDraft] = useState<Record<string, any>>({})
  useEffect(() => {
    if (data?.items) {
      const next: Record<string, any> = {}
      for (const it of data.items) next[it.key] = it.value == null ? '' : String(it.value)
      setDraft(next)
    }
  }, [data])

  if (isLoading) return <div style={{ padding: 12, color: 'var(--text-2)' }}>Cargando…</div>
  if (isError) return <div style={{ padding: 12, color: 'var(--danger)' }}>{extractErr(error, GENERIC_ERROR_FALLBACK)}</div>

  const items = data?.items || []

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)' }}>{description}</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 200px auto', gap: 10, alignItems: 'center' }}>
        {items.map((it: any) => {
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
              disabled={isPending}
              onChange={(v: any) => setDraft({ ...draft, [it.key]: v })}
              onSave={() => save({ key: it.key, value: isBool ? (current === 'true' || current === true) : current })}
            />
          )
        })}
      </div>
      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>
        {t('settingsadvanced.los_cambios_reemplazan_el_valor_por_defecto')}
      </div>
    </div>
  )
}


function RuntimeFlagRow({ item, current, isBool, dirty, disabled, onChange, onSave }: { item: any; current: any; isBool: boolean; dirty: boolean; disabled: boolean; onChange: (v: any) => void; onSave: () => void }) {
  const inputStyle: CSSProperties = {
    width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
    borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 'var(--text-base)',
    outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box',
  }
  return (
    <>
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        <span style={{ fontWeight: 600, color: 'var(--text-1)', fontSize: 'var(--text-sm)' }}>{item.label}</span>
        <span style={{ color: 'var(--text-3)', fontSize: 'var(--text-2xs)', fontFamily: 'ui-monospace, monospace' }}>{item.key}</span>
      </div>
      <div>
        {isBool ? (
          <select value={String(current)} onChange={(e) => onChange(e.target.value)} style={inputStyle}>
            <option value="true">Activado</option>
            <option value="false">Desactivado</option>
          </select>
        ) : (
          <input
            type={item.type === 'int' || item.type === 'float' ? 'number' : 'text'}
            step={item.type === 'float' ? 'any' : (item.type === 'int' ? '1' : undefined)}
            value={current}
            onChange={(e) => onChange(e.target.value)}
            style={inputStyle}
          />
        )}
      </div>
      <button
        type="button"
        onClick={onSave}
        disabled={!dirty || disabled}
        style={{
          background: dirty ? 'var(--accent)' : 'var(--surface-3)',
          border: 'none', borderRadius: 8, padding: '8px 16px',
          color: dirty ? '#fff' : 'var(--text-3)',
          cursor: dirty && !disabled ? 'pointer' : 'not-allowed',
          fontSize: 'var(--text-sm)', fontFamily: 'inherit',
        }}
      >Guardar</button>
    </>
  )
}


// ── Integration credentials (Phase 2: encrypted per-org provider creds) ─────

function IntegrationProviderEditor({ provider, label }: { provider: any; label?: string }) {
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const { data, isLoading, isError, error } = useQuery<any>({
    queryKey: ['integration', provider],
    queryFn: () => settingsApi.integrationProvider(provider).then(r => r.data),
  })
  const { mutate: save, isPending } = useMutation({
    mutationFn: ({ key, value }: { key: string; value: any }) => settingsApi.setIntegration(provider, key, value),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['integration', provider] })
      toast.success('Guardado')
    },
    onError: (e: any) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const [testResult, setTestResult] = useState<any>(null)
  const { mutate: runTest, isPending: testing } = useMutation({
    mutationFn: () => settingsApi.testIntegration(provider).then(r => r.data),
    onSuccess: (result: any) => {
      setTestResult(result)
      if (result?.ok) toast.success(result.detail || 'Conexión OK')
      else toast.error(result?.detail || 'Test de conexión falló')
    },
    onError: (e: any) => {
      setTestResult({ ok: false, detail: extractErr(e, GENERIC_ERROR_FALLBACK) })
      toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
    },
  })

  const [draft, setDraft] = useState<Record<string, any>>({})
  useEffect(() => {
    if (data?.items) {
      const next: Record<string, any> = {}
      // Secrets never echo back — start as empty so admin types the new value.
      for (const it of data.items) next[it.key] = it.is_secret ? '' : (it.value == null ? '' : String(it.value))
      setDraft(next)
    }
  }, [data])

  if (isLoading) return <div style={{ padding: 12, color: 'var(--text-2)' }}>Cargando…</div>
  if (isError)   return <div style={{ padding: 12, color: 'var(--danger)' }}>{extractErr(error, GENERIC_ERROR_FALLBACK)}</div>

  const items = data?.items || []

  return (
    <form
      onSubmit={(e) => e.preventDefault()}
      autoComplete="off"
      style={{ display: 'flex', flexDirection: 'column', gap: 14 }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 14 }}>
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)' }}>
          {label}{t('settingsadvanced.valores_cifrados_en_reposo_resuelven_org_global')}
        </div>
        <button
          type="button"
          onClick={() => runTest()}
          disabled={testing}
          style={{
            background: 'transparent',
            border: '1px solid var(--accent-border)',
            color: 'var(--accent)',
            borderRadius: 8, padding: '8px 14px',
            cursor: testing ? 'not-allowed' : 'pointer',
            fontSize: 'var(--text-sm)', fontFamily: 'inherit', whiteSpace: 'nowrap',
          }}
        >{testing ? 'Probando…' : 'Probar conexión'}</button>
      </div>
      {testResult && (
        <div style={{
          padding: '10px 14px', borderRadius: 8, fontSize: 'var(--text-sm)',
          background: testResult.ok ? 'rgba(34,197,94,.12)' : 'rgba(239,68,68,.12)',
          border: '1px solid ' + (testResult.ok ? 'rgba(34,197,94,.4)' : 'rgba(239,68,68,.4)'),
          color: testResult.ok ? 'var(--success, #22c55e)' : 'var(--danger, #ef4444)',
        }}>
          <strong>{testResult.ok ? '✓ OK' : '✗ Error'}</strong> — {testResult.detail}
        </div>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 260px auto auto', gap: 10, alignItems: 'center' }}>
        {items.map((it: any) => {
          const inputStyle: CSSProperties = {
            width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
            borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 'var(--text-base)',
            outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box',
          }
          const current = draft[it.key] ?? ''
          const dirty = it.is_secret ? (current !== '') : (String(it.value ?? '') !== String(current))
          return (
            <Fragment key={it.key}>
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                <span style={{ fontWeight: 600, color: 'var(--text-1)', fontSize: 'var(--text-sm)' }}>{it.label}</span>
                <span style={{ color: 'var(--text-3)', fontSize: 'var(--text-2xs)', fontFamily: 'ui-monospace, monospace' }}>
                  {it.key}{it.is_secret ? ' • secreto' : ''} • origen: {it.source}
                </span>
              </div>
              <div>
                <input
                  type={it.is_secret ? 'password' : (it.type === 'int' ? 'number' : 'text')}
                  step={it.type === 'int' ? '1' : undefined}
                  value={current}
                  placeholder={it.is_secret && it.configured ? '•••• (configurado)' : ''}
                  onChange={(e) => setDraft({ ...draft, [it.key]: e.target.value })}
                  style={inputStyle}
                />
              </div>
              <button
                type="button"
                onClick={() => save({ key: it.key, value: current })}
                disabled={!dirty || isPending}
                style={{
                  background: dirty ? 'var(--accent)' : 'var(--surface-3)',
                  border: 'none', borderRadius: 8, padding: '8px 16px',
                  color: dirty ? '#fff' : 'var(--text-3)',
                  cursor: dirty && !isPending ? 'pointer' : 'not-allowed',
                  fontSize: 'var(--text-sm)', fontFamily: 'inherit',
                }}
              >Guardar</button>
              <button
                type="button"
                onClick={() => save({ key: it.key, value: '' })}
                disabled={isPending || (!it.configured)}
                title={it.configured ? 'Borrar override (vuelve al valor del .env)' : 'No configurado'}
                style={{
                  background: 'transparent',
                  border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px',
                  color: 'var(--text-2)',
                  cursor: isPending || !it.configured ? 'not-allowed' : 'pointer',
                  fontSize: 'var(--text-sm)', fontFamily: 'inherit',
                }}
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
  const { data, isLoading, isError, error } = useQuery<any>({
    queryKey: ['integration-providers'],
    queryFn: () => settingsApi.integrations().then(r => r.data),
  })
  // useMemo (auditoría 2026-08, P1-6): con `?? []` / `|| []` esto creaba un
  // array nuevo en cada render, así que los useMemo/useEffect que lo tienen
  // como dependencia se reejecutaban SIEMPRE — no memoizaban nada.
  const providers = useMemo(() => data?.providers || [], [data?.providers])
  const [active, setActive] = useState<any>(null)
  useEffect(() => {
    if (!active && providers.length) setActive(providers[0].provider)
  }, [providers, active])

  if (isLoading) return <Section icon="🔐" title={t('settingsadvanced.credenciales_de_integracion')}><div style={{ padding: 12, color: 'var(--text-2)' }}>Cargando…</div></Section>
  if (isError)   return <Section icon="🔐" title={t('settingsadvanced.credenciales_de_integracion')}><div style={{ padding: 12, color: 'var(--danger)' }}>{extractErr(error, GENERIC_ERROR_FALLBACK)}</div></Section>

  const currentProvider = providers.find((p: any) => p.provider === active)

  return (
    <Section
      icon="🔐"
      title={t('settingsadvanced.credenciales_de_integracion')}
      description="SMTP, AWS S3, Microsoft Graph, Slack, Stripe, etc. Los secretos se cifran en reposo (Fernet/HKDF + opcional AWS KMS) y nunca se devuelven en las respuestas."
    >
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 16 }}>
        {providers.map((p: any) => (
          <button
            key={p.provider}
            onClick={() => setActive(p.provider)}
            style={{
              padding: '6px 14px',
              borderRadius: 999,
              border: '1px solid ' + (active === p.provider ? 'var(--accent)' : 'var(--surface-4)'),
              background: active === p.provider ? 'var(--accent-muted)' : 'transparent',
              color: active === p.provider ? 'var(--accent)' : 'var(--text-2)',
              fontSize: 'var(--text-sm)', fontWeight: 600, cursor: 'pointer',
              fontFamily: 'inherit',
            }}
          >{p.label}</button>
        ))}
      </div>
      {active && currentProvider && (
        <IntegrationProviderEditor key={active} provider={active} label={currentProvider.label} />
      )}
    </Section>
  )
}


export function RuntimeFlagsSection() {
  const { t } = useAppLang()
  const [active, setActive] = useState(RUNTIME_GROUPS[0].id)
  const current = RUNTIME_GROUPS.find(g => g.id === active) || RUNTIME_GROUPS[0]
  return (
    <Section icon="⚙️" title={t('settingsadvanced.configuracion_dinamica')} description="Knobs operativos editables sin redeploy. Resuelven org → global → valor del .env.">
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 16 }}>
        {RUNTIME_GROUPS.map(g => (
          <button
            key={g.id}
            onClick={() => setActive(g.id)}
            style={{
              padding: '6px 14px',
              borderRadius: 999,
              border: '1px solid ' + (active === g.id ? 'var(--accent)' : 'var(--surface-4)'),
              background: active === g.id ? 'var(--accent-muted)' : 'transparent',
              color: active === g.id ? 'var(--accent)' : 'var(--text-2)',
              fontSize: 'var(--text-sm)', fontWeight: 600, cursor: 'pointer',
              fontFamily: 'inherit',
            }}
          >{g.label}</button>
        ))}
      </div>
      <RuntimeGroupEditor key={active} groupId={active} description={current.description} />
    </Section>
  )
}

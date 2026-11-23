// Seccion de idiomas y textos del portal en Ajustes. 23-11-2026: troceado de SettingsAdvancedSections sin cambio de comportamiento.
import type { CSSProperties, ChangeEvent } from 'react'
import { useState, useEffect } from 'react'
import { useToast } from '../../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAppLang } from '../../i18n/AppLangContext'
import { APP_LANGUAGES, AVAILABLE_LANGUAGES, loadLanguage, getAllKeys, es } from '../../i18n/appTranslations.ts'
import { PORTAL_TRANSLATIONS, PORTAL_LANGUAGES, getPortalKeys } from '../../i18n/portalTranslations'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { portalClientsApi, settingsApi } from '../../services/api'
import type { PortalDictionary } from '../../i18n/portalTranslations'
import { Buscador, Button, Pulsable, Select, Tabs, Input } from '../../components/ui'
import { Check, Download, Globe, Languages, MonitorSmartphone, Save } from 'lucide-react'

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
    queryFn: () => portalClientsApi.translations().then(r => r.data),
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
              <Buscador value={searchKey} onChange={setSearchKey} placeholder={t('settingsadvanced.buscar_clave_de_traduccion')} aria-label={t('settingsadvanced.buscar_clave_de_traduccion')} inputClassName="seadse-fs" />
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
                  <Input aria-label={item.full_key} value={currentVal} onChange={e => setAppVal(appLang, item.module, item.key, e.target.value)} placeholder={item.base_es} inputClassName={isModified ? 'settings-advanced-sections-m9' : 'settings-advanced-sections-m10'} />
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
              <Buscador value={portalSearch} onChange={setPortalSearch} placeholder={t('settingsadvanced.buscar_texto_del_portal')} aria-label={t('settingsadvanced.buscar_texto_del_portal')} inputClassName="seadse-fs4" />
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
                    <Input aria-label={key} value={currentVal} onChange={e => {
                        setPortalEdits(prev => ({ ...prev, [key]: { ...(prev[key] || {}), [portalLang]: e.target.value } }))
                        setHasUnsaved(true)
                      }} placeholder={base_es} inputClassName={isModified ? 'settings-advanced-sections-m9' : 'settings-advanced-sections-m10'} />
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

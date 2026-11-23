// Secciones de nivel de log y estado del sistema en Ajustes. 23-11-2026: troceado de SettingsAdvancedSections sin cambio de comportamiento.
import type { CSSProperties } from 'react'
import { useState, useEffect } from 'react'
import { useToast } from '../../context/ToastContext'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useAppLang } from '../../i18n/AppLangContext'
import { extractErr } from '../../utils/helpers'
import SeccionDeAjustes from './SeccionDeAjustes'
import { settingsApi, type LogLevel } from '../../services/api'
import { settingsApi as ajustesGeneralesApi, type SettingOut } from '../../services/settingsApi'
import { alpha } from '../../constants/theme'
import { Pulsable } from '../../components/ui'
import { AlertTriangle, BarChart3, Bot, FileText, Lock, MonitorSmartphone, Package, Phone, Plug, Server, ShieldAlert, Wrench, Zap } from 'lucide-react'

type VentanaConLogger = Window & { __contecflowLogger?: { setLevel: (level: string) => void } }

export function LogLevelSection() {
  const { t } = useAppLang()
  const toast = useToast()
  const [backendLevel, setBackendLevel] = useState('')
  const [frontendLevel, setFrontendLevel] = useState(() => {
    // 23-11-2026: localStorage puede estar bloqueado (modo privado): se usa el nivel por defecto.
    let guardado: string | null = null
    try { guardado = localStorage.getItem('contecflow_log_level') } catch { /* accesorio: sin almacenamiento */ }
    return guardado || (import.meta.env.DEV ? 'debug' : 'warn')
  })
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
    } catch (e) {
      toast.error(extractErr(e, t('settingsadvanced.error_al_cambiar_nivel_de_log')))
    }
  }

  const handleSetFrontend = (level: string) => {
    setFrontendLevel(level)
    try { localStorage.setItem('contecflow_log_level', level) } catch { /* accesorio: sin almacenamiento, el nivel solo dura esta sesión */ }
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
    try { return JSON.stringify(raw, null, 2) } catch { /* accesorio: solo es el formato de lectura */ return String(raw) }
  }
  if (typeof raw !== 'string') return String(raw)
  const trimmed = raw.trim()
  if ((trimmed.startsWith('{') && trimmed.endsWith('}')) || (trimmed.startsWith('[') && trimmed.endsWith(']'))) {
    try {
      return JSON.stringify(JSON.parse(trimmed), null, 2)
    } catch {
      /* accesorio: no era JSON válido; se enseña el texto tal cual */
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

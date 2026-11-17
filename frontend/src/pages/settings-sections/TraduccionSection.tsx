/**
 * TraduccionSection — administración de la traducción en tiempo real operador ↔ cliente
 * (16-11-2026). Ajustes → Sistema → Traducción (`/settings?tab=traduccion`), solo admin.
 *
 * - Uso: KPIs de `GET /translation/usage`.
 * - Ajustes: grupo en vivo `traduccion` (`/settings/runtime/traduccion`), con controles
 *   propios (interruptores, proveedor, canales e idiomas de la KB como casillas).
 * - Credenciales: DeepL y Azure Translator con el editor de integraciones de siempre
 *   (los secretos nunca vuelven del servidor: solo «configurado»).
 * - Probar proveedor: `POST /translation/test`.
 * - Glosario: `/translation/glossary` (alta, edición y borrado con confirmación).
 *
 * 16-11-2026 (pasada de diseño): todas las KPI con icono lucide; si el servidor
 * manda un ajuste sin traducción, se enseña su nombre legible (`label`) y no la
 * clave técnica (TRANSLATION_*) ni una ayuda vacía.
 */
import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, BookA, CheckCircle2, Coins, FileClock, KeyRound, Languages, Lock, Pencil, Plus, Save, Sparkles, Trash2, Trash, XCircle, FlaskConical, Gauge } from 'lucide-react'
import { Button, Checkbox, Confirm, DataTable, IconButton, KpiCard, Modal, Section, Select, StatusBadge, Switch, Tabs, Spinner, EmptyState, type ColumnaDeTabla, useErroresDeCampo } from '../../components/ui'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { useAppLang } from '../../i18n/AppLangContext'
import { aiProvidersApi, settingsApi, type RuntimeSetting } from '../../services/api'
import { traduccionApi, type PruebaDeTraduccion, type TerminoDeGlosario } from '../../services/api/traduccion'
import { errorDeTraduccion, motivoDeTraduccion, nombreDeIdioma, useConfigDeTraduccion } from '../../hooks/useTraduccion'
import { extractErr } from '../../utils/helpers'
import { IntegrationProviderEditor } from './SettingsAdvancedSections'
import './TraduccionSection.css'

/** Canales del servidor (`TRANSLATION_CHANNELS`), en el orden en que se enseñan. */
export const CANALES_DE_TRADUCCION = ['ticket', 'email', 'livechat', 'whatsapp', 'slack', 'teams', 'portal_assistant', 'internal_chat', 'kb', 'editor', 'portal'] as const
const PROVEEDORES = ['ai', 'deepl', 'azure'] as const
type Proveedor = typeof PROVEEDORES[number]

const GRUPO = 'traduccion'
const BOOLEANOS = ['TRANSLATION_ENABLED', 'TRANSLATION_OUTBOUND_AUTO', 'TRANSLATION_INCLUDE_ORIGINAL']
const LISTAS = ['TRANSLATION_CHANNELS', 'TRANSLATION_KB_LANGUAGES']

const csv = (v: string) => v.split(',').map(s => s.trim()).filter(Boolean)

function useErrorDeTraduccion() {
  const { t } = useAppLang()
  return (e: unknown) => errorDeTraduccion(t, extractErr(e, ''))
}

export default function TraduccionSection() {
  const { t } = useAppLang()
  const esAdmin = useAuth().user?.role === 'admin'
  if (!esAdmin) return <EmptyState icon={<Lock size={28} strokeWidth={1.5} aria-hidden="true" />} title={t('traduccion_admin.solo_admin')} />
  return (
    <div className="trad-admin">
      <UsoDeTraduccion />
      <AjustesDeTraduccion />
      <IaQueTraduce />
      <CredencialesDeTraduccion />
      <ProbarProveedor />
      <Glosario />
    </div>
  )
}

// ── IA que traduce ──────────────────────────────────────────────────────────
// 16-11-2026: con el proveedor «IA», la traducción usa cualquier IA generalista
// configurada en la app (Gemini, Claude, GPT, Mistral…), no solo traductores
// especializados. Aquí se elige cuál y con qué modelo, sin ir al Hub de IA: se
// guarda en la MISMA ruta por función del Hub (módulo `translation`), así que
// no hay dos configuraciones que puedan contradecirse.
const MODULO_TRADUCCION = 'translation'

function IaQueTraduce() {
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: proveedores = [] } = useQuery({
    queryKey: ['ai-providers'],
    queryFn: () => aiProvidersApi.list().then(r => r.data ?? []),
  })
  const { data: enrutado } = useQuery({
    queryKey: ['ai-routing'],
    queryFn: () => aiProvidersApi.getRouting().then(r => r.data),
  })
  // Solo filas de la empresa: el proveedor del servidor ya es «la IA principal».
  const elegibles = proveedores.filter(p => p.source !== 'env' && p.status !== 'inactive')
  const principal = proveedores.find(p => p.is_default) || proveedores[0]
  const ruta = enrutado?.routes?.[MODULO_TRADUCCION]
  const [proveedorId, setProveedorId] = useState<string>('')
  const [modelo, setModelo] = useState<string>('')
  useEffect(() => {
    setProveedorId(ruta?.provider_id ?? '')
    setModelo(ruta?.model ?? '')
  }, [ruta?.provider_id, ruta?.model])

  const elegido = elegibles.find(p => p.id === proveedorId)
  const modelos = elegido ? Array.from(new Set([elegido.default_model, ...(elegido.available_models || [])].filter(Boolean))) as string[] : []

  const guardar = useMutation({
    mutationFn: () => {
      const rutas = { ...(enrutado?.routes || {}) }
      if (proveedorId || modelo) rutas[MODULO_TRADUCCION] = { provider_id: proveedorId || null, model: modelo || null }
      else delete rutas[MODULO_TRADUCCION]
      return aiProvidersApi.saveRouting(rutas)
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['ai-routing'] }); toast.success(t('traduccion_admin.ia_guardada')) },
    onError: (e: unknown) => toast.error(extractErr(e, t('traduccion_admin.ia_error'))),
  })

  const cambiado = (proveedorId || '') !== (ruta?.provider_id ?? '') || (modelo || '') !== (ruta?.model ?? '')
  return (
    <Section title={t('traduccion_admin.ia_titulo')} subtitle={t('traduccion_admin.ia_desc')}>
      <div className="trad-admin__fila">
        <div className="ds-field">
          <label className="ds-field__label" htmlFor="trad-admin-ia">{t('traduccion_admin.ia_proveedor')}</label>
          <Select suelto id="trad-admin-ia" value={proveedorId}
            onChange={e => { setProveedorId(e.target.value); setModelo('') }}
            placeholder={principal ? t('traduccion_admin.ia_principal_de', { nombre: principal.name }) : t('traduccion_admin.ia_principal')}>
            {elegibles.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </Select>
          <span className="ds-field__hint">{t('traduccion_admin.ia_proveedor_ayuda')}</span>
        </div>
        <div className="ds-field">
          <label className="ds-field__label" htmlFor="trad-admin-ia-modelo">{t('traduccion_admin.ia_modelo')}</label>
          <Select suelto id="trad-admin-ia-modelo" value={modelo} disabled={!elegido}
            onChange={e => setModelo(e.target.value)} placeholder={t('traduccion_admin.ia_modelo_por_defecto')}>
            {modelos.map(m => <option key={m} value={m}>{m}</option>)}
          </Select>
        </div>
      </div>
      {elegibles.length === 0 && <p className="ds-field__hint">{t('traduccion_admin.ia_sin_proveedores')}</p>}
      <div>
        <Button icon={<Save size={14} />} onClick={() => guardar.mutate()} disabled={!cambiado} loading={guardar.isPending}>
          {t('traduccion_admin.guardar')}
        </Button>
      </div>
    </Section>
  )
}

// ── Uso ─────────────────────────────────────────────────────────────────────

function UsoDeTraduccion() {
  const { t, lang } = useAppLang()
  const { data, isLoading, isError, error } = useQuery({ queryKey: ['traduccion-uso'], queryFn: traduccionApi.uso })
  const mensajeDeError = useErrorDeTraduccion()
  const num = (n: number) => new Intl.NumberFormat(lang).format(n)
  const usd = (n: number) => new Intl.NumberFormat(lang, { style: 'currency', currency: 'USD', maximumFractionDigits: 4 }).format(n)
  return (
    <Section title={t('traduccion_admin.uso_titulo')} subtitle={t('traduccion_admin.uso_desc')}>
      {isLoading ? <Spinner /> : isError || !data ? <p className="trad-admin__error" role="alert">{mensajeDeError(error)}</p> : (
        <div className="ds-grid-stats">
          <KpiCard icon={<Languages size={14} />} label={t('traduccion_admin.kpi_mensajes')} value={num(data.messages_translated)} />
          <KpiCard icon={<Gauge size={14} />} label={t('traduccion_admin.kpi_cache')} value={num(data.cache.entries)}
            sub={t('traduccion_admin.kpi_cache_sub', { aciertos: num(data.cache.hits), caracteres: num(data.cache.characters) })} />
          <KpiCard icon={<Coins size={14} />} label={t('traduccion_admin.kpi_coste_hoy')} value={usd(data.today_cost_usd)}
            sub={t('traduccion_admin.kpi_llamadas_sub', { n: num(data.today_calls) })} />
          <KpiCard icon={<AlertTriangle size={14} />} label={t('traduccion_admin.kpi_fallos_hoy')} value={num(data.today_failures)} danger={data.today_failures > 0} />
          <KpiCard icon={<Sparkles size={14} />} label={t('traduccion_admin.kpi_ia_hoy')} value={usd(data.ai_spend_today_usd)}
            sub={t('traduccion_admin.kpi_ia_sub', { tope: usd(data.ai_daily_budget_usd) })}
            warning={data.ai_daily_budget_usd > 0 && data.ai_spend_today_usd >= data.ai_daily_budget_usd * 0.8} />
          <KpiCard icon={<BookA size={14} />} label={t('traduccion_admin.kpi_glosario')} value={num(data.glossary_terms)} />
          <KpiCard icon={<FileClock size={14} />} label={t('traduccion_admin.kpi_kb_revision')} value={num(data.kb_versions_in_review)} accent={data.kb_versions_in_review > 0} />
        </div>
      )}
    </Section>
  )
}

// ── Ajustes en vivo ─────────────────────────────────────────────────────────

function AjustesDeTraduccion() {
  const { t, lang } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: config } = useConfigDeTraduccion()
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['runtime-flags', GRUPO],
    queryFn: () => settingsApi.runtimeGroup(GRUPO).then(r => r.data),
  })
  const items = useMemo(() => data?.items ?? [], [data])
  const [borrador, setBorrador] = useState<Record<string, string>>({})
  useEffect(() => {
    const next: Record<string, string> = {}
    for (const it of items) next[it.key] = it.value == null ? '' : String(it.value)
    setBorrador(next)
  }, [items])

  const cambiados = items.filter(it => String(it.value ?? '') !== (borrador[it.key] ?? ''))
  const guardar = useMutation({
    mutationFn: async () => {
      for (const it of cambiados) {
        const v = borrador[it.key] ?? ''
        await settingsApi.setRuntime(GRUPO, it.key, it.type === 'bool' ? v === 'true' : v)
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['runtime-flags', GRUPO] })
      qc.invalidateQueries({ queryKey: ['traduccion-config'] })
      toast.success(t('traduccion_admin.ajustes_guardados'))
    },
    onError: (e: unknown) => {
      qc.invalidateQueries({ queryKey: ['runtime-flags', GRUPO] })
      toast.error(extractErr(e, t('traduccion.err.generico')))
    },
  })

  const poner = (k: string, v: string) => setBorrador(b => ({ ...b, [k]: v }))
  const alternarEnLista = (k: string, valor: string) => {
    const actual = csv(borrador[k] ?? '')
    poner(k, (actual.includes(valor) ? actual.filter(x => x !== valor) : [...actual, valor]).join(','))
  }
  // Sin traducción para un ajuste nuevo del servidor: su nombre legible, nunca la clave.
  const etiqueta = (it: RuntimeSetting) => t(`traduccion_admin.ajuste.${it.key}`, it.label || it.key)
  const ayuda = (k: string) => t(`traduccion_admin.ayuda.${k}`, ' ').trim()

  if (isLoading) return <Section title={t('traduccion_admin.ajustes_titulo')}><Spinner /></Section>
  if (isError) return <Section title={t('traduccion_admin.ajustes_titulo')}><p className="trad-admin__error" role="alert">{extractErr(error, t('traduccion.err.generico'))}</p></Section>

  const porClave = new Map(items.map(it => [it.key, it]))
  const otros = items.filter(it => !BOOLEANOS.includes(it.key) && !LISTAS.includes(it.key) && it.key !== 'TRANSLATION_PROVIDER')
  const idiomasKb = config?.languages ?? []

  return (
    <Section
      title={t('traduccion_admin.ajustes_titulo')}
      subtitle={t('traduccion_admin.ajustes_desc')}
      actions={
        <Button icon={<Save size={14} />} onClick={() => guardar.mutate()} disabled={cambiados.length === 0} loading={guardar.isPending}>
          {cambiados.length ? t('traduccion_admin.guardar_n', { n: cambiados.length }) : t('traduccion_admin.guardar')}
        </Button>
      }
    >
      <div className="ds-card trad-admin__tarjeta">
        <div className="trad-admin__interruptores">
          {BOOLEANOS.filter(k => porClave.has(k)).map(k => {
            const it = porClave.get(k) as RuntimeSetting
            return (
              <Switch key={k} className="trad-admin__check" checked={borrador[k] === 'true'}
                onChange={m => poner(k, m ? 'true' : 'false')}
                label={etiqueta(it)} ayuda={ayuda(k) || undefined} />
            )
          })}
        </div>

        {porClave.has('TRANSLATION_PROVIDER') && (
          <div className="ds-field trad-admin__campo-corto">
            <label className="ds-field__label" htmlFor="trad-admin-proveedor">{t('traduccion_admin.ajuste.TRANSLATION_PROVIDER')}</label>
            <Select suelto placeholder={false} id="trad-admin-proveedor" value={borrador.TRANSLATION_PROVIDER ?? 'ai'}
              onChange={e => poner('TRANSLATION_PROVIDER', e.target.value)}>
              {PROVEEDORES.map(p => <option key={p} value={p}>{t(`traduccion_admin.proveedor.${p}`)}</option>)}
            </Select>
            <span className="ds-field__hint">{t('traduccion_admin.ayuda.TRANSLATION_PROVIDER')}</span>
          </div>
        )}

        {porClave.has('TRANSLATION_CHANNELS') && (
          <fieldset className="ds-grupo-opciones trad-admin__grupo">
            <legend className="ds-field__label">{t('traduccion_admin.ajuste.TRANSLATION_CHANNELS')}</legend>
            <div className="trad-admin__casillas">
              {CANALES_DE_TRADUCCION.map(c => (
                <Checkbox key={c} className="trad-admin__casilla" checked={csv(borrador.TRANSLATION_CHANNELS ?? '').includes(c)}
                  onChange={() => alternarEnLista('TRANSLATION_CHANNELS', c)}
                  label={t(`traduccion_admin.canal.${c}`)} />
              ))}
            </div>
          </fieldset>
        )}

        {porClave.has('TRANSLATION_KB_LANGUAGES') && (
          <fieldset className="ds-grupo-opciones trad-admin__grupo">
            <legend className="ds-field__label">{t('traduccion_admin.ajuste.TRANSLATION_KB_LANGUAGES')}</legend>
            <span className="ds-field__hint">{t('traduccion_admin.ayuda.TRANSLATION_KB_LANGUAGES')}</span>
            <div className="trad-admin__casillas">
              {Array.from(new Set([...idiomasKb, ...csv(borrador.TRANSLATION_KB_LANGUAGES ?? '')])).map(c => (
                <Checkbox key={c} className="trad-admin__casilla" checked={csv(borrador.TRANSLATION_KB_LANGUAGES ?? '').includes(c)}
                  onChange={() => alternarEnLista('TRANSLATION_KB_LANGUAGES', c)}
                  label={nombreDeIdioma(c, lang)} />
              ))}
            </div>
          </fieldset>
        )}

        {otros.length > 0 && (
          <div className="trad-admin__numeros">
            {otros.map(it => (
              <div key={it.key} className="ds-field">
                <label className="ds-field__label" htmlFor={`trad-admin-${it.key}`}>{etiqueta(it)}</label>
                <input id={`trad-admin-${it.key}`} className="ds-input"
                  type={it.type === 'int' || it.type === 'float' ? 'number' : 'text'}
                  step={it.type === 'float' ? 'any' : it.type === 'int' ? '1' : undefined}
                  min={it.type === 'int' || it.type === 'float' ? 0 : undefined}
                  value={borrador[it.key] ?? ''} onChange={e => poner(it.key, e.target.value)} />
                {ayuda(it.key) && <span className="ds-field__hint">{ayuda(it.key)}</span>}
              </div>
            ))}
          </div>
        )}
      </div>
    </Section>
  )
}

// ── Credenciales ────────────────────────────────────────────────────────────

function CredencialesDeTraduccion() {
  const { t } = useAppLang()
  const [activo, setActivo] = useState<'deepl' | 'azure_translator'>('deepl')
  return (
    <Section title={t('traduccion_admin.credenciales_titulo')} subtitle={t('traduccion_admin.credenciales_desc')}>
      <div className="ds-card trad-admin__tarjeta">
        <Tabs
          items={[
            { id: 'deepl', label: 'DeepL', icon: <KeyRound size={14} /> },
            { id: 'azure_translator', label: 'Azure Translator', icon: <KeyRound size={14} /> },
          ]}
          active={activo}
          onChange={id => setActivo(id as 'deepl' | 'azure_translator')}
          ariaLabel={t('traduccion_admin.credenciales_titulo')}
        />
        <IntegrationProviderEditor key={activo} provider={activo} label={activo === 'deepl' ? 'DeepL' : 'Azure Translator'} />
      </div>
    </Section>
  )
}

// ── Probar proveedor ────────────────────────────────────────────────────────

function ProbarProveedor() {
  const { t, lang } = useAppLang()
  const { data: config } = useConfigDeTraduccion()
  const mensajeDeError = useErrorDeTraduccion()
  const [proveedor, setProveedor] = useState<Proveedor | ''>('')
  const [destino, setDestino] = useState('')
  const [texto, setTexto] = useState('')
  const [resultado, setResultado] = useState<PruebaDeTraduccion | null>(null)
  const idiomas = useMemo(() => config?.languages ?? [], [config?.languages])
  useEffect(() => { if (!destino && idiomas.length) setDestino(idiomas.find(i => i !== lang) ?? idiomas[0]) }, [idiomas, destino, lang])

  const probar = useMutation({
    mutationFn: () => traduccionApi.probar({ provider: proveedor || undefined, target_language: destino, text: texto.trim() }),
    onSuccess: r => setResultado(r),
    onError: (e: unknown) => setResultado({ ok: false, reason: undefined, text: mensajeDeError(e) }),
  })

  return (
    <Section title={t('traduccion_admin.probar_titulo')} subtitle={t('traduccion_admin.probar_desc')}>
      <div className="ds-card trad-admin__tarjeta">
        <div className="trad-admin__numeros">
          <div className="ds-field">
            <label className="ds-field__label" htmlFor="trad-admin-probar-proveedor">{t('traduccion_admin.ajuste.TRANSLATION_PROVIDER')}</label>
            <Select suelto id="trad-admin-probar-proveedor" value={proveedor} onChange={e => setProveedor(e.target.value as Proveedor | '')}
              placeholder={t('traduccion_admin.proveedor_actual')}>
              {PROVEEDORES.map(p => <option key={p} value={p}>{t(`traduccion_admin.proveedor.${p}`)}</option>)}
            </Select>
          </div>
          <div className="ds-field">
            <label className="ds-field__label" htmlFor="trad-admin-probar-idioma">{t('traduccion_admin.idioma_destino')}</label>
            <Select suelto placeholder={false} id="trad-admin-probar-idioma" value={destino} onChange={e => setDestino(e.target.value)}>
              {idiomas.map(i => <option key={i} value={i}>{nombreDeIdioma(i, lang)}</option>)}
            </Select>
          </div>
        </div>
        <div className="ds-field">
          <label className="ds-field__label" htmlFor="trad-admin-probar-texto">{t('traduccion_admin.texto_de_prueba')}</label>
          <textarea id="trad-admin-probar-texto" className="ds-input" rows={3} value={texto} onChange={e => setTexto(e.target.value)} />
        </div>
        <div className="u-row-end">
          <Button icon={<FlaskConical size={14} />} onClick={() => probar.mutate()} disabled={!texto.trim() || !destino} loading={probar.isPending}>
            {t('traduccion_admin.probar')}
          </Button>
        </div>
        {resultado && (
          <div className={`trad-admin__resultado ${resultado.ok ? 'trad-admin__resultado--ok' : 'trad-admin__resultado--error'}`} role="status">
            {resultado.ok ? <CheckCircle2 size={16} aria-hidden="true" /> : <XCircle size={16} aria-hidden="true" />}
            <div className="u-min0">
              <div className="u-text1-sm-600">
                {resultado.ok
                  ? (resultado.provider
                    ? t('traduccion_admin.prueba_ok_de', { proveedor: t(`traduccion_admin.proveedor.${resultado.provider}`) })
                    : t('traduccion_admin.prueba_ok'))
                  : t('traduccion_admin.prueba_error')}
              </div>
              <div className="trad-admin__resultado-texto">
                {resultado.ok ? resultado.text : (resultado.reason ? motivoDeTraduccion(t, resultado.reason) : resultado.text)}
              </div>
            </div>
          </div>
        )}
      </div>
    </Section>
  )
}

// ── Glosario ────────────────────────────────────────────────────────────────

type FilaTraduccion = { idioma: string; texto: string }
interface FormTermino { term: string; filas: FilaTraduccion[]; case_sensitive: boolean; notes: string; is_active: boolean }

const FORM_VACIO: FormTermino = { term: '', filas: [], case_sensitive: false, notes: '', is_active: true }

function Glosario() {
  const { t, lang } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const mensajeDeError = useErrorDeTraduccion()
  const { data, isLoading } = useQuery({ queryKey: ['traduccion-glosario'], queryFn: traduccionApi.glosario })
  const [editando, setEditando] = useState<TerminoDeGlosario | 'nuevo' | null>(null)
  const [borrando, setBorrando] = useState<TerminoDeGlosario | null>(null)

  const refrescar = () => {
    qc.invalidateQueries({ queryKey: ['traduccion-glosario'] })
    qc.invalidateQueries({ queryKey: ['traduccion-uso'] })
  }
  const borrar = useMutation({
    mutationFn: (id: string) => traduccionApi.borrarTermino(id),
    onSuccess: () => { refrescar(); setBorrando(null); toast.success(t('traduccion_admin.termino_borrado')) },
    onError: (e: unknown) => toast.error(mensajeDeError(e)),
  })

  const columnas: ColumnaDeTabla<TerminoDeGlosario>[] = [
    { key: 'term', label: t('traduccion_admin.col_termino'), render: (_v, f) => <span className="u-text1-sm-600">{f.term}</span> },
    {
      key: 'translations', label: t('traduccion_admin.col_traducciones'), sortable: false,
      render: (_v, f) => {
        const pares = Object.entries(f.translations ?? {})
        if (pares.length === 0) return <span className="ds-muted">{t('traduccion_admin.no_se_traduce')}</span>
        return (
          <ul className="trad-admin__pares">
            {pares.map(([idioma, texto]) => <li key={idioma}><span className="ds-muted">{nombreDeIdioma(idioma, lang)}:</span> {texto}</li>)}
          </ul>
        )
      },
    },
    { key: 'case_sensitive', label: t('traduccion_admin.col_mayusculas'), render: (_v, f) => f.case_sensitive ? t('traduccion_admin.si') : t('traduccion_admin.no') },
    {
      key: 'is_active', label: t('traduccion_admin.col_estado'),
      render: (_v, f) => <StatusBadge kind={f.is_active ? 'success' : 'neutral'}>{f.is_active ? t('traduccion_admin.activo') : t('traduccion_admin.inactivo')}</StatusBadge>,
    },
    { key: 'notes', label: t('traduccion_admin.col_notas'), sortable: false, render: (_v, f) => f.notes || '—' },
    {
      key: 'acciones', label: <span className="u-sr-only">{t('traduccion_admin.acciones')}</span>, sortable: false,
      render: (_v, f) => (
        <div className="u-row-6">
          <IconButton ariaLabel={t('traduccion_admin.editar_x', { termino: f.term })} title={t('traduccion_admin.editar')} onClick={() => setEditando(f)}><Pencil size={14} aria-hidden="true" /></IconButton>
          <IconButton ariaLabel={t('traduccion_admin.borrar_x', { termino: f.term })} title={t('traduccion_admin.borrar')} onClick={() => setBorrando(f)}><Trash2 size={14} aria-hidden="true" /></IconButton>
        </div>
      ),
    },
  ]

  return (
    <Section
      title={t('traduccion_admin.glosario_titulo')}
      subtitle={t('traduccion_admin.glosario_desc')}
      actions={<Button icon={<Plus size={14} />} onClick={() => setEditando('nuevo')}>{t('traduccion_admin.nuevo_termino')}</Button>}
    >
      <div className="ds-card trad-admin__tarjeta">
        <DataTable columns={columnas} data={data?.items ?? []} loading={isLoading} emptyIcon={<BookA size={28} />} emptyTitle={t('traduccion_admin.glosario_vacio')} />
      </div>
      {editando && (
        <ModalDeTermino
          termino={editando === 'nuevo' ? null : editando}
          onClose={() => setEditando(null)}
          onGuardado={() => { refrescar(); setEditando(null) }}
        />
      )}
      <Confirm
        open={!!borrando}
        title={t('traduccion_admin.borrar_termino_titulo')}
        description={t('traduccion_admin.borrar_termino_desc', { termino: borrando?.term ?? '' })}
        onCancel={() => setBorrando(null)}
        onConfirm={() => borrando && borrar.mutate(borrando.id)}
        loading={borrar.isPending}
      />
    </Section>
  )
}

export function ModalDeTermino({ termino, onClose, onGuardado }: { termino: TerminoDeGlosario | null; onClose: () => void; onGuardado: () => void }) {
  const { t, lang } = useAppLang()
  const toast = useToast()
  const mensajeDeError = useErrorDeTraduccion()
  const { data: config } = useConfigDeTraduccion()
  const idiomas = config?.languages ?? []
  const [form, setForm] = useState<FormTermino>(() => termino ? {
    term: termino.term,
    filas: Object.entries(termino.translations ?? {}).map(([idioma, texto]) => ({ idioma, texto })),
    case_sensitive: termino.case_sensitive,
    notes: termino.notes ?? '',
    is_active: termino.is_active,
  } : FORM_VACIO)
  const usados = new Set(form.filas.map(f => f.idioma))
  const libres = idiomas.filter(i => !usados.has(i))

  const campos = useErroresDeCampo()
  const msg = (k: string) => campos.de(k) ? <div className="u-field-error">{campos.de(k)}</div> : null
  const guardar = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: () => {
      const translations: Record<string, string> = {}
      for (const f of form.filas) if (f.idioma && f.texto.trim()) translations[f.idioma] = f.texto.trim()
      const cuerpo = { term: form.term.trim(), translations, case_sensitive: form.case_sensitive, notes: form.notes.trim() || null, is_active: form.is_active }
      return termino ? traduccionApi.cambiarTermino(termino.id, cuerpo) : traduccionApi.crearTermino(cuerpo)
    },
    onSuccess: () => { toast.success(termino ? t('traduccion_admin.termino_guardado') : t('traduccion_admin.termino_creado')); onGuardado() },
    onError: (e: unknown) => { campos.recoger(e); toast.error(mensajeDeError(e)) },
  })

  const cambiarFila = (i: number, cambio: Partial<FilaTraduccion>) =>
    setForm(f => ({ ...f, filas: f.filas.map((x, j) => j === i ? { ...x, ...cambio } : x) }))
  const quitarFila = (i: number) => setForm(f => ({ ...f, filas: f.filas.filter((_, j) => j !== i) }))
  const anadirFila = () => libres.length && setForm(f => ({ ...f, filas: [...f.filas, { idioma: libres[0], texto: '' }] }))

  return (
    <Modal open onClose={onClose} size="lg" title={termino ? t('traduccion_admin.editar_termino') : t('traduccion_admin.nuevo_termino')}>
      <div className="u-stack-14">
        <div className="ds-field">
          <label className="ds-field__label" htmlFor="trad-termino">{t('traduccion_admin.col_termino')}</label>
          <input id="trad-termino" className="ds-input" value={form.term} maxLength={200} onChange={e => { campos.limpiar('term'); setForm(f => ({ ...f, term: e.target.value })) }} />{msg('term')}
        </div>

        <fieldset className="ds-grupo-opciones trad-admin__grupo">
          <legend className="ds-field__label">{t('traduccion_admin.col_traducciones')}</legend>
          <span className="ds-field__hint">{t('traduccion_admin.traducciones_ayuda')}</span>
          {form.filas.map((fila, i) => (
            <div key={i} className="trad-admin__fila-idioma">
              <Select suelto placeholder={false} aria-label={t('traduccion_admin.idioma_n', { n: i + 1 })} value={fila.idioma}
                onChange={e => cambiarFila(i, { idioma: e.target.value })}>
                {[fila.idioma, ...libres].filter(Boolean).map(c => <option key={c} value={c}>{nombreDeIdioma(c, lang)}</option>)}
              </Select>
              <input aria-label={t('traduccion_admin.texto_en', { idioma: nombreDeIdioma(fila.idioma, lang) })} className="ds-input"
                value={fila.texto} onChange={e => cambiarFila(i, { texto: e.target.value })} />
              <IconButton ariaLabel={t('traduccion_admin.quitar_idioma', { idioma: nombreDeIdioma(fila.idioma, lang) })} onClick={() => quitarFila(i)}>
                <Trash size={14} aria-hidden="true" />
              </IconButton>
            </div>
          ))}
          <div>
            <Button variant="secondary" size="sm" icon={<Plus size={14} />} onClick={anadirFila} disabled={libres.length === 0}>
              {t('traduccion_admin.anadir_idioma')}
            </Button>
          </div>
        </fieldset>

        <Checkbox className="trad-admin__casilla" checked={form.case_sensitive} onChange={m => { campos.limpiar('case_sensitive'); setForm(f => ({ ...f, case_sensitive: m })) }}
          label={t('traduccion_admin.distingue_mayusculas')} />
        <Checkbox className="trad-admin__casilla" checked={form.is_active} onChange={m => { campos.limpiar('is_active'); setForm(f => ({ ...f, is_active: m })) }}
          label={t('traduccion_admin.activo')} />
        <div className="ds-field">
          <label className="ds-field__label" htmlFor="trad-notas">{t('traduccion_admin.col_notas')}</label>
          <textarea id="trad-notas" className="ds-input" rows={2} value={form.notes} onChange={e => { campos.limpiar('notes'); setForm(f => ({ ...f, notes: e.target.value })) }} />{msg('notes')}
        </div>
        <div className="u-actions-8">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button icon={<Save size={14} />} onClick={() => guardar.mutate()} disabled={!form.term.trim()} loading={guardar.isPending}>
            {t('traduccion_admin.guardar')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

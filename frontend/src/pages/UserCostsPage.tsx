/**
 * UserCostsPage — admin/HR view to manage employer cost calculations.
 *
 * Sections:
 *   1. Summary KPIs (avg cost/h, users with/without cost data, total annual cost)
 *   2. Country presets (% SS empresa, productive hours/year per country)
 *   3. Users table — each row links to its versioned cost profile history
 *   4. Profile editor with live preview (gross salary → SS% → extras → cost/hour)
 *
 * 16-11-2026: KPIs con KpiCard (antes borde izquierdo de color y emojis); secciones con Card + Section; "+ Override país" pasa a "Personalizar
 * país" con icono (y fuera los "overrides" en castellano); botones de fila en
 * una línea (antes se apilaban); vacíos con EmptyState e icono lucide; select
 * de país con ds-input; título del menú (nav.user_costs).
 */
import type { ReactNode } from 'react'
import { useId, useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { userCostsApi, usersApi, apiErrorMsg } from '../services/api'
import type { PerfilDeCoste, PresetDePais, ResumenDeCostes } from '../services/api/tipos-finanzas'
import { Button, Card, KpiCard, Modal, Spinner, EmptyState, Input, Section, Select, TablaSimple } from '../components/ui'
import PageShell from '../components/layout/PageShell'
import PageHeader from '../components/layout/PageHeader'
import { useToast } from '../context/ToastContext'
import { confirmar } from '../context/ConfirmContext'
import { Wallet, Globe, History, Plus, Calculator, BarChart3, AlertTriangle, Download, Users, SearchX } from 'lucide-react'
import { useAppLang } from '../i18n/AppLangContext'
import StatusBadge from '../components/ui/StatusBadge'

import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
import { fmtDate, localeActivo } from '../utils/helpers'
import './UserCostsPage.css'

/** Un preset (serialize_country) o uno nuevo a medio rellenar. */
type CountryRow = Partial<PresetDePais>
type SummaryRow = ResumenDeCostes['users'][number]
/** Lo que la pantalla usa de una persona: su id y su nombre. */
type UserRow = { id: string; full_name?: string | null }
type ProfileRow = PerfilDeCoste



export default function UserCostsPage() {
  const fmtMoneda = useFormatoMoneda()
  const { t } = useAppLang()
  const qc = useQueryClient()
  const toast = useToast()
  const [editProfile, setEditProfile] = useState<{ user: UserRow; profile?: ProfileRow } | null>(null) // { user, profile? }
  const [editCountry, setEditCountry] = useState<CountryRow | null>(null) // preset
  const [historyUser, setHistoryUser] = useState<UserRow | null>(null) // user
  const [search, setSearch] = useState('')

  const { data: summary, isLoading: loadingSummary } = useQuery<ResumenDeCostes>({
    queryKey: ['user-costs-summary'],
    queryFn: () => userCostsApi.summary().then(r => r.data),
  })

  const { data: countries = [], isLoading: loadingCountries } = useQuery<CountryRow[]>({
    queryKey: ['user-costs-countries'],
    queryFn: () => userCostsApi.listCountries().then(r => r.data),
  })

  // Pantalla de administración: la ficha completa de toda la plantilla. Sin `page`,
  // `usersApi.list` recorre todas las páginas (antes se cortaba en SELECTOR_LIST_SIZE).
  const { data: users = [] } = useQuery<UserRow[]>({
    queryKey: ['users-list-for-costs'],
    queryFn: () => usersApi.list().then(r => r.data.map(u => ({ id: u.id, full_name: u.full_name }))),
  })

  const seedCountriesMut = useMutation({
    mutationFn: (force: boolean) => userCostsApi.seedCountries(force),
    onSuccess: (r) => {
      toast.success(t('usercosts.paises_cargados', { creados: r.data.created, actualizados: r.data.updated }))
      qc.invalidateQueries({ queryKey: ['user-costs-countries'] })
    },
    onError: (e) => toast.error(apiErrorMsg(e, t('usercosts.error_cargar_paises'))),
  })

  const userById = useMemo(
    () => Object.fromEntries(users.map((u) => [u.id, u])),
    [users],
  )

  // useMemo (auditoría 2026-08, P1-6): con `?? []` / `|| []` esto creaba un
  // array nuevo en cada render, así que los useMemo/useEffect que lo tienen
  // como dependencia se reejecutaban SIEMPRE — no memoizaban nada.
  const summaryRows: SummaryRow[] = useMemo(() => summary?.users || [], [summary?.users])
  const filteredUsers = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return summaryRows
    return summaryRows.filter((u) =>
      (u.full_name || '').toLowerCase().includes(q) ||
      (u.department || '').toLowerCase().includes(q),
    )
  }, [summaryRows, search])

  const totalAnnualCost = useMemo(() => {
    // Approximate: cost/h × productive_hours_year (we don't have ph_year here, use 1700)
    return summaryRows.reduce((s: number, u) => s + (u.cost_per_hour ? u.cost_per_hour * 1700 : 0), 0)
  }, [summaryRows])

  return (
    <PageShell>
      <PageHeader
        icon={<Wallet size={18} />}
        title={t('nav.user_costs')}
        subtitle={t('usercosts.subtitulo')}
      />

      <div className="ds-page">
      <div className="ds-grid-stats">
        <KpiCard icon={<Calculator size={16} />} label={t('usercosts.kpi_coste_hora_medio')}
                value={fmtMoneda(summary?.avg_cost_per_hour, { decimales: 0 })}
                sub={t('usercosts.n_personas', { n: summary?.users_with_cost ?? 0 })} />
        <KpiCard icon={<BarChart3 size={16} />} label={t('usercosts.kpi_coste_anual_total')}
                value={fmtMoneda(totalAnnualCost, { decimales: 0 })}
                sub={t('usercosts.estimacion_horas_ano', { horas: (1700).toLocaleString(localeActivo()) })} />
        <KpiCard icon={<AlertTriangle size={16} />} label={t('usercosts.sin_datos_de_coste')}
                value={summary?.users_missing_cost ?? 0}
                sub={t('usercosts.completar_para_margen')}
                warning={(summary?.users_missing_cost ?? 0) > 0} />
        <KpiCard icon={<Globe size={16} />} label={t('usercosts.paises_configurados')}
                value={countries.length}
                sub={t('usercosts.n_overrides_org', { n: countries.filter((c) => !c.is_default).length })} />
      </div>

      <Card>
      <Section
        title={<span className="uc-section-title"><Globe size={16} aria-hidden="true" />{t('usercosts.paises_y_de_coste_empresa')}</span>}
        actions={<>
          <Button size="sm" variant="secondary" icon={<Download size={13} />} onClick={() => seedCountriesMut.mutate(false)}
                  loading={seedCountriesMut.isPending}>
            {t('usercosts.cargar_predefinidos')}
          </Button>
          <Button size="sm" icon={<Plus size={13} />} onClick={() => setEditCountry({ country_code: '', country_name: '', currency: fmtMoneda.moneda, employer_cost_pct: 0.30, productive_hours_year: 1700 })}>
            {t('usercosts.override_pais')}
          </Button>
        </>}
      >
        {loadingCountries ? <Spinner /> : countries.length === 0 ? (
          <EmptyState icon={<Globe size={28} />} title={t('usercosts.sin_paises_configurados')}
                      description={t('usercosts.vacio_paises_desc')}
                      action={<Button icon={<Download size={14} />} onClick={() => seedCountriesMut.mutate(false)} loading={seedCountriesMut.isPending}>{t('usercosts.cargar_predefinidos')}</Button>} />
        ) : (
          <div className="uc-countries">
            {countries.map(c => (
              <CountryCard key={c.id} c={c} onEdit={() => setEditCountry(c)} />
            ))}
          </div>
        )}
      </Section>
      </Card>

      <Card>
      <Section
        title={<span className="uc-section-title"><Users size={16} aria-hidden="true" />{t('usercosts.personas_y_coste_hora')}</span>}
        actions={
          <div className="uc-search">
            <Input placeholder={t('usercosts.buscar_placeholder')} aria-label={t('usercosts.buscar_placeholder')} value={search}
                   onChange={(e: { target: { value: string } }) => setSearch(e.target.value)} />
          </div>
        }
      >
        {loadingSummary ? <Spinner /> : filteredUsers.length === 0 ? (
          search.trim()
            ? <EmptyState icon={<SearchX size={28} />} title={t('usercosts.sin_resultados')} description={t('usercosts.sin_resultados_desc')} />
            : <EmptyState icon={<Users size={28} />} title={t('usercosts.sin_personas')} description={t('usercosts.sin_personas_desc')} />
        ) : (
          <div className="uc-table-wrap">
            <TablaSimple claseTabla="u-table">
              <thead>
                <tr className="uc-thead-row">
                  <th scope="col" className="uc-th">{t('usercosts.col_persona')}</th>
                  <th scope="col" className="uc-th">{t('usercosts.col_departamento')}</th>
                  <th scope="col" className="uc-th uc-th--right">{t('usercosts.col_coste_hora')}</th>
                  <th scope="col" className="uc-th">{t('usercosts.col_origen')}</th>
                  <th scope="col" className="uc-th uc-th--actions">{t('usercosts.col_acciones')}</th>
                </tr>
              </thead>
              <tbody>
                {filteredUsers.map(u => {
                  const user = userById[u.user_id]
                  return (
                    <tr key={u.user_id} className="uc-row">
                      <td className="uc-td">{u.full_name}</td>
                      <td className="uc-td uc-td--muted">{u.department || '—'}</td>
                      <td className="uc-td uc-td--money">
                        {u.cost_per_hour ? fmtMoneda(u.cost_per_hour, { decimales: 0 }) : <span className="u-warning">{t('usercosts.falta')}</span>}
                      </td>
                      <td className="uc-td">
                        <SourceBadge source={u.source} />
                      </td>
                      <td className="uc-td uc-td--right">
                        <div className="uc-row-actions">
                          <Button size="sm" variant="ghost" icon={<History size={13} />} onClick={() => setHistoryUser(user || { id: u.user_id, full_name: u.full_name })}>
                            {t('usercosts.historico')}
                          </Button>
                          <Button size="sm" variant="secondary" icon={<Plus size={13} />} onClick={() => setEditProfile({ user: user || { id: u.user_id, full_name: u.full_name } })}>
                            {t('usercosts.nueva_version')}
                          </Button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </TablaSimple>
          </div>
        )}
      </Section>
      </Card>
      </div>

      {/* Profile editor (wizard) */}
      {editProfile && (
        <ProfileWizard
          user={editProfile.user}
          countries={countries}
          existing={editProfile.profile}
          onClose={() => setEditProfile(null)}
          onSaved={() => {
            setEditProfile(null)
            qc.invalidateQueries({ queryKey: ['user-costs-summary'] })
            if (historyUser) qc.invalidateQueries({ queryKey: ['user-costs-history', historyUser.id] })
          }}
        />
      )}

      {/* Country override editor */}
      {editCountry && (
        <CountryEditor
          preset={editCountry}
          onClose={() => setEditCountry(null)}
          onSaved={() => {
            setEditCountry(null)
            qc.invalidateQueries({ queryKey: ['user-costs-countries'] })
          }}
        />
      )}

      {/* History modal */}
      {historyUser && (
        <HistoryModal
          user={historyUser}
          onClose={() => setHistoryUser(null)}
          onAddNew={() => { setEditProfile({ user: historyUser }); setHistoryUser(null) }}
        />
      )}
    </PageShell>
  )
}


// ── Sub-components ──────────────────────────────────────────────────────────
function CountryCard({ c, onEdit }: { c: CountryRow; onEdit: () => void }) {
  const { t } = useAppLang()
  return (
    <Card onClick={onEdit} className="uc-country">
      <div className="u-row-between">
        <span className="u-600">{c.country_code} · {c.country_name}</span>
        <StatusBadge kind={c.is_default ? 'neutral' : 'accent'} caps={false}>
          {c.is_default ? t('usercosts.predefinido') : t('usercosts.personalizado')}
        </StatusBadge>
      </div>
      <div className="uc-country-meta">
        <span><strong>{((c.employer_cost_pct ?? 0) * 100).toFixed(1)}%</strong> {t('usercosts.coste_empresa_lower')}</span>
        <span className="u-text3">{c.productive_hours_year} {t('usercosts.h_ano')}</span>
        <span className="u-text3">{c.currency}</span>
      </div>
      {c.notes && <div className="uc-country-notes">{c.notes}</div>}
    </Card>
  )
}

function SourceBadge({ source }: { source?: string }) {
  const { t } = useAppLang()
  const cfgMap: Record<string, { label: string; color: string }> = {
    profile:            { label: t('usercosts.origen_perfil'), color: 'var(--success)' },
    legacy_hourly_rate: { label: t('usercosts.origen_tarifa_interna'),  color: 'var(--warning)' },
    none:               { label: t('usercosts.origen_sin_datos'),       color: 'var(--danger)' },
  }
  const cfg = cfgMap[source || ''] || { label: source, color: 'var(--text-3)' }
  return (
    <StatusBadge color={cfg.color} caps={false}>{cfg.label}</StatusBadge>
  )
}


// ── Profile wizard ───────────────────────────────────────────────────────────
type ProfileForm = {
  valid_from: string
  country_code: string
  currency: string
  gross_annual_salary: number | string
  employer_cost_pct: number | string
  extra_annual_costs: number | string
  productive_hours_year: number | string
  notes: string
}

function ProfileWizard({ user, countries, existing, onClose, onSaved }: { user: UserRow; countries: CountryRow[]; existing?: ProfileRow; onClose: () => void; onSaved: () => void }) {
  const fmtMoneda = useFormatoMoneda()
  const { t } = useAppLang()
  const toast = useToast()
  const idPais = useId()
  // Los campos numéricos guardan el texto del input al editarlos.
  const [form, setForm] = useState<ProfileForm>({
    valid_from: existing?.valid_from || new Date().toISOString().slice(0, 10),
    country_code: existing?.country_code || '',
    currency: existing?.currency || fmtMoneda.moneda,
    gross_annual_salary: existing?.gross_annual_salary || '',
    employer_cost_pct: existing?.employer_cost_pct ?? 0.32,
    extra_annual_costs: existing?.extra_annual_costs ?? 0,
    productive_hours_year: existing?.productive_hours_year ?? 1700,
    notes: existing?.notes || '',
  })

  // Live preview of derived values
  const total = useMemo(() => {
    const g = Number(form.gross_annual_salary) || 0
    const e = Number(form.employer_cost_pct) || 0
    const x = Number(form.extra_annual_costs) || 0
    return Math.round(g * (1 + e) + x)
  }, [form])
  const hours = Number(form.productive_hours_year) || 1700
  const costPerHour = total > 0 ? Math.round((total / hours) * 100) / 100 : 0

  const onPickCountry = (code: string) => {
    const c = countries.find((x) => x.country_code === code)
    if (!c) { setForm(f => ({ ...f, country_code: code })); return }
    setForm(f => ({
      ...f,
      country_code: code,
      currency: c.currency,
      employer_cost_pct: c.employer_cost_pct,
      productive_hours_year: c.productive_hours_year,
    }))
  }

  const save = async () => {
    if (!form.gross_annual_salary || Number(form.gross_annual_salary) <= 0) {
      toast.error(t('usercosts.error_salario')); return
    }
    try {
      await userCostsApi.createProfile(user.id, {
        ...form,
        gross_annual_salary: Number(form.gross_annual_salary),
        employer_cost_pct: Number(form.employer_cost_pct),
        extra_annual_costs: Number(form.extra_annual_costs),
        productive_hours_year: Number(form.productive_hours_year),
      })
      toast.success(t('usercosts.perfil_guardado'))
      onSaved()
    } catch (e) {
      toast.error(apiErrorMsg(e, t('usercosts.error_guardar')))
    }
  }

  return (
    <Modal open onClose={onClose} title={t('usercosts.modal_coste_hora', { persona: user.full_name ?? '' })} width={620}>
      <div className="u-stack-14">
        <p className="uc-intro">
          {t('usercosts.selecciona_el_pais_rellena_ss_empresa_y')}
        </p>

        {/* Step 1 — Country */}
        <div>
          <Label htmlFor={idPais}>{t('usercosts.pais_region')}</Label>
          <Select suelto placeholder={false} id={idPais} value={form.country_code} onChange={(e) => onPickCountry(e.target.value)}
                  className="uc-select">
            <option value="">{t('usercosts.selecciona_pais')}</option>
            {countries.map(c => (
              <option key={c.id} value={c.country_code}>
                {c.country_code} · {c.country_name} ({((c.employer_cost_pct ?? 0) * 100).toFixed(1)}% — {c.productive_hours_year}h)
              </option>
            ))}
          </Select>
        </div>

        <div className="uc-grid-2">
          <Input label={t('usercosts.vigencia_desde')} type="date" value={form.valid_from}
                 onChange={(e: { target: { value: string } }) => setForm({ ...form, valid_from: e.target.value })} />
          <Input label={t('usercosts.moneda')} value={form.currency}
                 onChange={(e: { target: { value: string } }) => setForm({ ...form, currency: e.target.value.toUpperCase() })} />

          <Input label={t('usercosts.salario_bruto_anual')} type="number" value={form.gross_annual_salary}
                 onChange={(e: { target: { value: string } }) => setForm({ ...form, gross_annual_salary: e.target.value })}
                 placeholder={t('usercosts.salario_placeholder')} />
          <Input label={t('usercosts.pct_coste_empresa')} type="number" value={form.employer_cost_pct}
                 onChange={(e: { target: { value: string } }) => setForm({ ...form, employer_cost_pct: e.target.value })}
                 hint={t('usercosts.pct_hint_largo')} />

          <Input label={t('usercosts.costes_extra_anuales')} type="number" value={form.extra_annual_costs}
                 onChange={(e: { target: { value: string } }) => setForm({ ...form, extra_annual_costs: e.target.value })}
                 hint={t('usercosts.costes_extra_hint')} />
          <Input label={t('usercosts.horas_productivas_ano')} type="number" value={form.productive_hours_year}
                 onChange={(e: { target: { value: string } }) => setForm({ ...form, productive_hours_year: e.target.value })}
                 hint={t('usercosts.horas_productivas_hint')} />
        </div>

        {/* Live preview */}
        <div className="uc-preview">
          <div className="uc-preview-title">
            {t('usercosts.calculo_derivado')}
          </div>
          <div className="uc-preview-stats" aria-live="polite">
            <Stat label={t('usercosts.coste_anual_total')} value={fmtMoneda(total, { moneda: form.currency, decimales: 0 })} />
            <Stat label={t('usercosts.coste_por_hora')} value={fmtMoneda(costPerHour, { moneda: form.currency, decimales: 0 })}
                  emphasised />
          </div>
        </div>

        <Input label={t('usercosts.notas_opcional')} value={form.notes}
               onChange={(e: { target: { value: string } }) => setForm({ ...form, notes: e.target.value })}
               placeholder={t('usercosts.notas_placeholder')} />

        <div className="u-actions-8">
          <Button variant="secondary" onClick={onClose}>{t('usercosts.cancelar')}</Button>
          <Button onClick={save}>{t('usercosts.guardar_version')}</Button>
        </div>
      </div>
    </Modal>
  )
}


// ── Country override editor ─────────────────────────────────────────────────
function CountryEditor({ preset, onClose, onSaved }: { preset: CountryRow; onClose: () => void; onSaved: () => void }) {
  const fmtMoneda = useFormatoMoneda()
  const { t } = useAppLang()
  const toast = useToast()
  const [form, setForm] = useState<{ country_code: string; country_name: string; currency: string; employer_cost_pct: number | string; productive_hours_year: number | string; notes: string }>({
    country_code: preset.country_code || '',
    country_name: preset.country_name || '',
    currency: preset.currency || fmtMoneda.moneda,
    employer_cost_pct: preset.employer_cost_pct ?? 0.30,
    productive_hours_year: preset.productive_hours_year ?? 1700,
    notes: preset.notes || '',
  })

  const save = async () => {
    if (!form.country_code || form.country_code.length !== 2) {
      toast.error(t('usercosts.error_iso')); return
    }
    try {
      if (preset.id && !preset.is_default) {
        await userCostsApi.updateCountry(preset.id, {
          country_name: form.country_name,
          currency: form.currency,
          employer_cost_pct: Number(form.employer_cost_pct),
          productive_hours_year: Number(form.productive_hours_year),
          notes: form.notes,
        })
      } else {
        await userCostsApi.upsertCountry({
          ...form,
          country_code: form.country_code.toUpperCase(),
          employer_cost_pct: Number(form.employer_cost_pct),
          productive_hours_year: Number(form.productive_hours_year),
        })
      }
      toast.success(t('usercosts.pais_guardado'))
      onSaved()
    } catch (e) {
      toast.error(apiErrorMsg(e, t('usercosts.error_guardar_pais')))
    }
  }

  const remove = async () => {
    if (preset.is_default) return
    // `openConfirmGlobal` no devuelve nada: con él `ok` era siempre undefined y el override no se borraba nunca.
    const ok = await confirmar({
      title: t('usercosts.eliminar_override'),
      message: t('usercosts.confirmar_eliminar_override', { pais: preset.country_name ?? '' }),
      danger: true, confirmLabel: t('usercosts.eliminar'),
    })
    if (!ok) return
    try {
      await userCostsApi.deleteCountry(preset.id)
      onSaved()
    } catch (e) {
      toast.error(apiErrorMsg(e, t('usercosts.error_eliminar')))
    }
  }

  return (
    <Modal open onClose={onClose}
           title={preset.id ? t('usercosts.editar_pais', { pais: preset.country_name ?? '' }) : t('usercosts.nuevo_pais')} width={520}>
      <div className="u-stack-12">
        <div className="uc-grid-1-2">
          <Input label={t('usercosts.codigo_iso')} value={form.country_code}
                 onChange={(e: { target: { value: string } }) => setForm({ ...form, country_code: e.target.value.toUpperCase() })}
                 placeholder="ES" />
          <Input label={t('usercosts.nombre')} value={form.country_name}
                 onChange={(e: { target: { value: string } }) => setForm({ ...form, country_name: e.target.value })}
                 placeholder={t('usercosts.espana')} />
        </div>
        <div className="uc-grid-3">
          <Input label={t('usercosts.moneda')} value={form.currency}
                 onChange={(e: { target: { value: string } }) => setForm({ ...form, currency: e.target.value.toUpperCase() })} />
          <Input label={t('usercosts.pct_coste_empresa')} type="number" value={form.employer_cost_pct}
                 onChange={(e: { target: { value: string } }) => setForm({ ...form, employer_cost_pct: e.target.value })}
                 hint={t('usercosts.pct_hint_corto')} />
          <Input label={t('usercosts.horas_ano_productivas')} type="number" value={form.productive_hours_year}
                 onChange={(e: { target: { value: string } }) => setForm({ ...form, productive_hours_year: e.target.value })} />
        </div>
        <Input label={t('usercosts.notas')} value={form.notes}
               onChange={(e: { target: { value: string } }) => setForm({ ...form, notes: e.target.value })} />
        <div className="u-row-between">
          <div>
            {preset.id && !preset.is_default && (
              <Button variant="danger" onClick={remove}>{t('usercosts.eliminar_override')}</Button>
            )}
          </div>
          <div className="u-row-8">
            <Button variant="secondary" onClick={onClose}>{t('usercosts.cancelar')}</Button>
            <Button onClick={save}>{t('usercosts.guardar')}</Button>
          </div>
        </div>
      </div>
    </Modal>
  )
}


// ── History of versions per user ────────────────────────────────────────────
function HistoryModal({ user, onClose, onAddNew }: { user: UserRow; onClose: () => void; onAddNew: () => void }) {
  const fmtMoneda = useFormatoMoneda()
  const { t } = useAppLang()
  const { data: profiles = [], isLoading } = useQuery<ProfileRow[]>({
    queryKey: ['user-costs-history', user.id],
    queryFn: () => userCostsApi.listProfiles(user.id).then(r => r.data),
  })
  return (
    <Modal open onClose={onClose} title={t('usercosts.modal_historico', { persona: user.full_name ?? '' })} width={620}>
      {isLoading ? <Spinner /> : profiles.length === 0 ? (
        <EmptyState icon={<History size={28} />} title={t('usercosts.sin_versiones_aun')}
                    description={t('usercosts.sin_versiones_desc')}
                    action={<Button icon={<Plus size={14} />} onClick={onAddNew}>{t('usercosts.crear_primera_version')}</Button>} />
      ) : (
        <>
          <div className="u-row-end u-mb-10">
            <Button size="sm" icon={<Plus size={13} />} onClick={onAddNew}>{t('usercosts.nueva_version')}</Button>
          </div>
          {profiles.map(p => (
            <div key={p.id} className="uc-history-row">
              <div>
                <div className="u-600">
                  {fmtDate(p.valid_from)} → {p.valid_to ? fmtDate(p.valid_to) : t('usercosts.actual')}
                  {p.is_active && <StatusBadge kind="success" caps={false} className="uc-current">{t('usercosts.vigente')}</StatusBadge>}
                </div>
                <div className="u-text3-xs">
                  {t('usercosts.historico_linea', { bruto: fmtMoneda(p.gross_annual_salary, { moneda: p.currency, decimales: 0 }), pct: ((p.employer_cost_pct ?? 0) * 100).toFixed(1) })} · {t('usercosts.n_horas_ano', { n: p.productive_hours_year })}
                  {p.notes && <> · {p.notes}</>}
                </div>
              </div>
              <div className="uc-right">
                <div className="uc-mono-strong">
                  {fmtMoneda(p.cost_per_hour, { moneda: p.currency, decimales: 0 })} / h
                </div>
                <div className="u-text3-xs">
                  {fmtMoneda(p.total_annual_cost, { moneda: p.currency, decimales: 0 })} {t('usercosts.ano')}
                </div>
              </div>
            </div>
          ))}
        </>
      )}
    </Modal>
  )
}


// ── Reusable bits ───────────────────────────────────────────────────────────
function Label({ children, htmlFor }: { children: ReactNode; htmlFor?: string }) {
  return (
    <label htmlFor={htmlFor} className="uc-label">
      {children}
    </label>
  )
}
function Stat({ label, value, emphasised }: { label: ReactNode; value: ReactNode; emphasised?: boolean }) {
  return (
    <div>
      <div className="uc-stat-label">{label}</div>
      <div className={`uc-stat-value${emphasised ? ' uc-stat-value--strong' : ''}`}>
        {value}
      </div>
    </div>
  )
}

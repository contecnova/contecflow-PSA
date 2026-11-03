/**
 * UserCostsPage — admin/HR view to manage employer cost calculations.
 *
 * Sections:
 *   1. Summary KPIs (avg cost/h, users with/without cost data, total annual cost)
 *   2. Country presets (% SS empresa, productive hours/year per country)
 *   3. Users table — each row links to its versioned cost profile history
 *   4. Profile editor with live preview (gross salary → SS% → extras → cost/hour)
 */
import type { ReactNode, KeyboardEvent as ReactKeyboardEvent } from 'react'
import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api, { userCostsApi, apiErrorMsg, unwrapList } from '../services/api'
import { Button, Modal, Spinner, EmptyState, Input as InputRaw} from '../components/ui'
import PageShell from '../components/layout/PageShell'
import PageHeader from '../components/layout/PageHeader'
import { useToast } from '../context/ToastContext'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { Wallet, Globe, History, Plus } from 'lucide-react'
import { useAppLang } from '../i18n/AppLangContext'
import { alpha } from '../constants/theme'

// Loosely-typed alias: Input infers its props as required.
const Input = InputRaw as unknown as (props: Record<string, unknown>) => JSX.Element

type CountryRow = { [k: string]: unknown; id?: string; country_code?: string; country_name?: string; currency?: string; employer_cost_pct?: number; productive_hours_year?: number; is_default?: boolean; notes?: string }
type SummaryRow = { [k: string]: unknown; user_id: string; full_name?: string; department?: string; cost_per_hour?: number; source?: string }
type UserRow = { [k: string]: unknown; id: string; full_name?: string }
type ProfileRow = { [k: string]: unknown; id: string; valid_from?: string; valid_to?: string; is_active?: boolean; notes?: string; gross_annual_salary?: number; currency?: string; employer_cost_pct?: number; productive_hours_year?: number; cost_per_hour?: number; total_annual_cost?: number }

const fmtCur = (v: number | null | undefined, currency = 'EUR', lang = 'es') =>
  v == null ? '—' : new Intl.NumberFormat(lang, { style: 'currency', currency, maximumFractionDigits: 0 }).format(v)


export default function UserCostsPage() {
  const { t } = useAppLang()
  const { lang } = useAppLang()
  const qc = useQueryClient()
  const toast = useToast()
  const [editProfile, setEditProfile] = useState<{ user: UserRow; profile?: Record<string, unknown> } | null>(null) // { user, profile? }
  const [editCountry, setEditCountry] = useState<CountryRow | null>(null) // preset
  const [historyUser, setHistoryUser] = useState<UserRow | null>(null) // user
  const [search, setSearch] = useState('')

  const { data: summary, isLoading: loadingSummary } = useQuery<{ users?: SummaryRow[]; users_with_cost?: number; users_missing_cost?: number; avg_cost_per_hour?: number }>({
    queryKey: ['user-costs-summary'],
    queryFn: () => userCostsApi.summary(undefined).then((r: { data: { users?: SummaryRow[] } }) => r.data),
  })

  const { data: countries = [], isLoading: loadingCountries } = useQuery<CountryRow[]>({
    queryKey: ['user-costs-countries'],
    queryFn: () => userCostsApi.listCountries().then((r: { data: CountryRow[] }) => r.data),
  })

  const { data: users = [] } = useQuery<UserRow[]>({
    queryKey: ['users-list-for-costs'],
    queryFn: () => api.get('/users', { params: { page_size: 200 } }).then(unwrapList).catch(() => []) as Promise<UserRow[]>,
  })

  const seedCountriesMut = useMutation({
    mutationFn: (force: boolean) => userCostsApi.seedCountries(force),
    onSuccess: (r: { data: { created: number; updated: number } }) => {
      toast.success(`Países cargados: +${r.data.created}, actualizados ${r.data.updated}`)
      qc.invalidateQueries({ queryKey: ['user-costs-countries'] })
    },
    onError: (e) => toast.error(apiErrorMsg(e, 'Error al cargar países')),
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
        icon={<Wallet size={22} />}
        title={t('usercosts.estructura_de_coste')}
        subtitle="Salario bruto, coste empresa y coste/hora real por persona — base para el cálculo de margen real."
        meta={
          (summary && (
            <span>
              {summary.users_with_cost} {t('usercosts.con_coste')} {summary.users_missing_cost} {t('usercosts.sin_coste_media')} {fmtCur(summary.avg_cost_per_hour, 'EUR', lang)}/h
            </span>
          )) as never
        }
      />

      {/* KPIs */}
      <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', marginBottom: 24 }}>
        <KpiBox icon="🧮" label="Coste/hora medio"
                value={fmtCur(summary?.avg_cost_per_hour, 'EUR', lang)}
                sub={`${summary?.users_with_cost ?? 0} personas`} />
        <KpiBox icon="📊" label="Coste anual total (aprox.)"
                value={fmtCur(totalAnnualCost, 'EUR', lang)}
                sub="Estimación 1.700 h/año" />
        <KpiBox icon="⚠️" label={t('usercosts.sin_datos_de_coste')}
                value={summary?.users_missing_cost ?? 0}
                sub="Hay que completarlos para que el margen sea real"
                accent={(summary?.users_missing_cost ?? 0) > 0 ? 'var(--warning)' : 'var(--success)'} />
        <KpiBox icon="🌍" label={t('usercosts.paises_configurados')}
                value={countries.length}
                sub={`${countries.filter((c) => !c.is_default).length} overrides org`} />
      </div>

      {/* Country presets */}
      <Section
        title={t('usercosts.paises_y_de_coste_empresa')}
        icon={<Globe size={16} />}
        actions={
          <div style={{ display: 'flex', gap: 6 }}>
            <Button size="sm" variant="ghost" onClick={() => seedCountriesMut.mutate(false)}
                    disabled={seedCountriesMut.isPending}>
              Cargar predefinidos
            </Button>
            <Button size="sm" onClick={() => setEditCountry({ country_code: '', country_name: '', currency: 'EUR', employer_cost_pct: 0.30, productive_hours_year: 1700 })}>
              {t('usercosts.override_pais')}
            </Button>
          </div>
        }
      >
        {loadingCountries ? <Spinner /> : countries.length === 0 ? (
          <EmptyState icon="🌍" title={t('usercosts.sin_paises_configurados')}
                      description="Carga los predefinidos para empezar (España, Francia, US, Brasil, etc.)"
                      ctaLabel="Cargar países" onCta={() => seedCountriesMut.mutate(false)} />
        ) : (
          <div style={{ display: 'grid', gap: 8, gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))' }}>
            {countries.map(c => (
              <CountryCard key={c.id} c={c} onEdit={() => setEditCountry(c)} />
            ))}
          </div>
        )}
      </Section>

      {/* Users with their cost-per-hour */}
      <Section
        title="Personas y coste/hora"
        icon={<Wallet size={16} />}
        actions={
          <Input placeholder="Buscar persona o departamento…" value={search}
                 onChange={(e: { target: { value: string } }) => setSearch(e.target.value)} style={{ width: 280 }} />
        }
      >
        {loadingSummary ? <Spinner /> : (
          <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8, overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: 'var(--surface-1)', textAlign: 'left' }}>
                  <th style={th}>Persona</th>
                  <th style={th}>Departamento</th>
                  <th style={{ ...th, textAlign: 'right' }}>Coste/hora</th>
                  <th style={th}>Origen</th>
                  <th style={{ ...th, width: 200, textAlign: 'right' }}>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {filteredUsers.map(u => {
                  const user = userById[u.user_id]
                  return (
                    <tr key={u.user_id} style={{ borderTop: '1px solid var(--surface-4)' }}>
                      <td style={td}>{u.full_name}</td>
                      <td style={{ ...td, color: 'var(--text-3)' }}>{u.department || '—'}</td>
                      <td style={{ ...td, textAlign: 'right', fontFamily: 'var(--font-mono)' }}>
                        {u.cost_per_hour ? fmtCur(u.cost_per_hour, 'EUR', lang) : <span style={{ color: 'var(--warning)' }}>Falta</span>}
                      </td>
                      <td style={td}>
                        <SourceBadge source={u.source} />
                      </td>
                      <td style={{ ...td, textAlign: 'right' }}>
                        <Button size="xs" variant="ghost" onClick={() => setHistoryUser(user || { id: u.user_id, full_name: u.full_name })}>
                          <History size={11} /> {t('usercosts.historico')}
                        </Button>
                        <Button size="xs" onClick={() => setEditProfile({ user: user || { id: u.user_id, full_name: u.full_name } })}>
                          <Plus size={11} /> {t('usercosts.nueva_version')}
                        </Button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </Section>

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
function Section({ title, icon, actions, children }: { title: ReactNode; icon: ReactNode; actions?: ReactNode; children: ReactNode }) {
  return (
    <div style={{ marginBottom: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <h3 style={{ fontSize: 'var(--text-md)', display: 'flex', alignItems: 'center', gap: 8, margin: 0 }}>
          {icon}{title}
        </h3>
        <div>{actions}</div>
      </div>
      {children}
    </div>
  )
}

function KpiBox({ icon, label, value, sub, accent = 'var(--accent)' }: { icon: ReactNode; label: ReactNode; value: ReactNode; sub?: ReactNode; accent?: string }) {
  return (
    <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
                  borderRadius: 8, padding: 14, borderLeft: `3px solid ${accent}` }}>
      <div style={{ fontSize: 'var(--text-xs)', textTransform: 'uppercase', color: 'var(--text-3)',
                    letterSpacing: '0.06em', marginBottom: 6 }}>
        {icon} {label}
      </div>
      <div style={{ fontSize: 'var(--text-2xl)', fontWeight: 700, color: 'var(--text-1)', marginBottom: 4 }}>
        {value}
      </div>
      {sub && <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{sub}</div>}
    </div>
  )
}

function CountryCard({ c, onEdit }: { c: CountryRow; onEdit: () => void }) {
  const { t } = useAppLang()
  return (
    <div onClick={onEdit}
      role="button"
      tabIndex={0}
      onKeyDown={(e: ReactKeyboardEvent) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onEdit() } }}
      style={{
      background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8,
      padding: 12, cursor: 'pointer', display: 'flex', flexDirection: 'column', gap: 6,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontWeight: 600 }}>{c.country_code} · {c.country_name}</span>
        {c.is_default && <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>predefinido</span>}
      </div>
      <div style={{ display: 'flex', gap: 14, fontSize: 'var(--text-sm)' }}>
        <span><strong>{((c.employer_cost_pct ?? 0) * 100).toFixed(1)}%</strong> coste empresa</span>
        <span style={{ color: 'var(--text-3)' }}>{c.productive_hours_year} {t('usercosts.h_ano')}</span>
        <span style={{ color: 'var(--text-3)' }}>{c.currency}</span>
      </div>
      {c.notes && <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-4)' }}>{c.notes}</div>}
    </div>
  )
}

function SourceBadge({ source }: { source?: string }) {
  const cfgMap: Record<string, { label: string; color: string }> = {
    profile:            { label: 'Perfil de coste', color: 'var(--success)' },
    legacy_hourly_rate: { label: 'Tarifa interna',  color: 'var(--warning)' },
    none:               { label: 'Sin datos',       color: 'var(--danger)' },
  }
  const cfg = cfgMap[source || ''] || { label: source, color: 'var(--text-3)' }
  return (
    <span style={{ fontSize: 'var(--text-xs)', padding: '2px 8px', borderRadius: 10,
                   border: `1px solid ${alpha(cfg.color, '55')}`, color: cfg.color, background: alpha(cfg.color, '11') }}>
      {cfg.label}
    </span>
  )
}


// ── Profile wizard ───────────────────────────────────────────────────────────
function ProfileWizard({ user, countries, existing, onClose, onSaved }: { user: UserRow; countries: CountryRow[]; existing?: any; onClose: () => void; onSaved: () => void }) {
  const { t } = useAppLang()
  const { lang } = useAppLang()
  const toast = useToast()
  const [form, setForm] = useState({
    valid_from: existing?.valid_from || new Date().toISOString().slice(0, 10),
    country_code: existing?.country_code || '',
    currency: existing?.currency || 'EUR',
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
      toast.error('Introduce el salario bruto anual'); return
    }
    try {
      await userCostsApi.createProfile(user.id, {
        ...form,
        gross_annual_salary: Number(form.gross_annual_salary),
        employer_cost_pct: Number(form.employer_cost_pct),
        extra_annual_costs: Number(form.extra_annual_costs),
        productive_hours_year: Number(form.productive_hours_year),
      })
      toast.success('Perfil de coste guardado')
      onSaved()
    } catch (e) {
      toast.error(apiErrorMsg(e, 'Error al guardar'))
    }
  }

  return (
    <Modal open onClose={onClose} title={`Coste/hora — ${user.full_name}`} width={620}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)', margin: 0 }}>
          {t('usercosts.selecciona_el_pais_rellena_ss_empresa_y')}
        </p>

        {/* Step 1 — Country */}
        <div>
          <Label>{t('usercosts.pais_region')}</Label>
          <select value={form.country_code} onChange={(e) => onPickCountry(e.target.value)}
                  style={selectStyle}>
            <option value="">{t('usercosts.selecciona_pais')}</option>
            {countries.map(c => (
              <option key={c.id} value={c.country_code}>
                {c.country_code} · {c.country_name} ({((c.employer_cost_pct ?? 0) * 100).toFixed(1)}% — {c.productive_hours_year}h)
              </option>
            ))}
          </select>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10 }}>
          <Input label="Vigencia desde" type="date" value={form.valid_from}
                 onChange={(e: { target: { value: string } }) => setForm({ ...form, valid_from: e.target.value })} />
          <Input label="Moneda" value={form.currency}
                 onChange={(e: { target: { value: string } }) => setForm({ ...form, currency: e.target.value.toUpperCase() })} />

          <Input label="Salario bruto anual" type="number" value={form.gross_annual_salary}
                 onChange={(e: { target: { value: string } }) => setForm({ ...form, gross_annual_salary: e.target.value })}
                 placeholder="Ej: 45000" />
          <Input label="% Coste empresa" type="number" value={form.employer_cost_pct}
                 onChange={(e: { target: { value: string } }) => setForm({ ...form, employer_cost_pct: e.target.value })}
                 hint="0.32 = 32% (SS empresa + extras)" />

          <Input label="Costes extra anuales" type="number" value={form.extra_annual_costs}
                 onChange={(e: { target: { value: string } }) => setForm({ ...form, extra_annual_costs: e.target.value })}
                 hint="Bonus, equipo, formación, beneficios" />
          <Input label={t('usercosts.horas_productivas_ano')} type="number" value={form.productive_hours_year}
                 onChange={(e: { target: { value: string } }) => setForm({ ...form, productive_hours_year: e.target.value })}
                 hint="Anuales − vacaciones − festivos − formación" />
        </div>

        {/* Live preview */}
        <div style={{ background: 'var(--accent-muted)', border: '1px solid var(--accent-glow)',
                      borderRadius: 8, padding: 14 }}>
          <div style={{ fontSize: 'var(--text-xs)', textTransform: 'uppercase', color: 'var(--accent)',
                        letterSpacing: '0.07em', marginBottom: 8 }}>
            {t('usercosts.calculo_derivado')}
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-around', textAlign: 'center' }}>
            <Stat label="Coste anual total" value={fmtCur(total, form.currency, lang)} />
            <Stat label={t('usercosts.coste_por_hora')} value={fmtCur(costPerHour, form.currency, lang)}
                  emphasised />
          </div>
        </div>

        <Input label="Notas (opcional)" value={form.notes}
               onChange={(e: { target: { value: string } }) => setForm({ ...form, notes: e.target.value })}
               placeholder="Ej: ascenso a senior 2026" />

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={save}>{t('usercosts.guardar_version')}</Button>
        </div>
      </div>
    </Modal>
  )
}


// ── Country override editor ─────────────────────────────────────────────────
function CountryEditor({ preset, onClose, onSaved }: { preset: CountryRow; onClose: () => void; onSaved: () => void }) {
  const { t } = useAppLang()
  const toast = useToast()
  const [form, setForm] = useState<{ country_code: string; country_name: string; currency: string; employer_cost_pct: number | string; productive_hours_year: number | string; notes: string }>({
    country_code: preset.country_code || '',
    country_name: preset.country_name || '',
    currency: preset.currency || 'EUR',
    employer_cost_pct: preset.employer_cost_pct ?? 0.30,
    productive_hours_year: preset.productive_hours_year ?? 1700,
    notes: preset.notes || '',
  })

  const save = async () => {
    if (!form.country_code || form.country_code.length !== 2) {
      toast.error('Código ISO de 2 letras (ej: ES, FR, US)'); return
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
      toast.success('País guardado')
      onSaved()
    } catch (e) {
      toast.error(apiErrorMsg(e, 'Error al guardar país'))
    }
  }

  const remove = async () => {
    if (preset.is_default) return
    const ok = await (openConfirmGlobal as unknown as (opts: Record<string, unknown>) => unknown)({
      title: 'Eliminar override',
      message: `¿Eliminar el override de ${preset.country_name}? Volverá a usarse el predefinido.`,
      variant: 'danger', confirmLabel: 'Eliminar',
    })
    if (!ok) return
    try {
      await userCostsApi.deleteCountry(preset.id)
      onSaved()
    } catch (e) {
      toast.error(apiErrorMsg(e, 'Error al eliminar'))
    }
  }

  return (
    <Modal open onClose={onClose}
           title={preset.id ? `Editar ${preset.country_name}` : 'Nuevo país'} width={520}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 10 }}>
          <Input label={t('usercosts.codigo_iso')} value={form.country_code}
                 onChange={(e: { target: { value: string } }) => setForm({ ...form, country_code: e.target.value.toUpperCase() })}
                 placeholder="ES" />
          <Input label="Nombre" value={form.country_name}
                 onChange={(e: { target: { value: string } }) => setForm({ ...form, country_name: e.target.value })}
                 placeholder={t('usercosts.espana')} />
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
          <Input label="Moneda" value={form.currency}
                 onChange={(e: { target: { value: string } }) => setForm({ ...form, currency: e.target.value.toUpperCase() })} />
          <Input label="% Coste empresa" type="number" value={form.employer_cost_pct}
                 onChange={(e: { target: { value: string } }) => setForm({ ...form, employer_cost_pct: e.target.value })}
                 hint="0.32 = 32%" />
          <Input label={t('usercosts.horas_ano_productivas')} type="number" value={form.productive_hours_year}
                 onChange={(e: { target: { value: string } }) => setForm({ ...form, productive_hours_year: e.target.value })} />
        </div>
        <Input label="Notas" value={form.notes}
               onChange={(e: { target: { value: string } }) => setForm({ ...form, notes: e.target.value })} />
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <div>
            {preset.id && !preset.is_default && (
              <Button variant="danger" onClick={remove}>Eliminar override</Button>
            )}
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <Button variant="secondary" onClick={onClose}>Cancelar</Button>
            <Button onClick={save}>Guardar</Button>
          </div>
        </div>
      </div>
    </Modal>
  )
}


// ── History of versions per user ────────────────────────────────────────────
function HistoryModal({ user, onClose, onAddNew }: { user: UserRow; onClose: () => void; onAddNew: () => void }) {
  const { t } = useAppLang()
  const { lang } = useAppLang()
  const { data: profiles = [], isLoading } = useQuery<ProfileRow[]>({
    queryKey: ['user-costs-history', user.id],
    queryFn: () => userCostsApi.listProfiles(user.id).then((r: { data: ProfileRow[] }) => r.data),
  })
  return (
    <Modal open onClose={onClose} title={`Histórico — ${user.full_name}`} width={620}>
      {isLoading ? <Spinner /> : profiles.length === 0 ? (
        <EmptyState icon="○" title={t('usercosts.sin_versiones_aun')}
                    ctaLabel="+ Crear primera versión" onCta={onAddNew} />
      ) : (
        <>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 10 }}>
            <Button size="sm" onClick={onAddNew}>{t('usercosts.nueva_version_2')}</Button>
          </div>
          {profiles.map(p => (
            <div key={p.id} style={{
              padding: '10px 12px', borderBottom: '1px solid var(--surface-4)',
              display: 'flex', justifyContent: 'space-between',
            }}>
              <div>
                <div style={{ fontWeight: 600 }}>
                  {p.valid_from} → {p.valid_to || 'actual'}
                  {p.is_active && <span style={{
                    marginLeft: 8, fontSize: 'var(--text-xs)', padding: '2px 8px', borderRadius: 10,
                    background: 'var(--success-bg)', color: 'var(--success)',
                  }}>vigente</span>}
                </div>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>
                  {fmtCur(p.gross_annual_salary, p.currency, lang)} bruto · {((p.employer_cost_pct ?? 0) * 100).toFixed(1)}% empresa · {p.productive_hours_year}{t('usercosts.h_ano')}
                  {p.notes && <> · {p.notes}</>}
                </div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 700 }}>
                  {fmtCur(p.cost_per_hour, p.currency, lang)} / h
                </div>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>
                  {fmtCur(p.total_annual_cost, p.currency, lang)} {t('usercosts.ano')}
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
function Label({ children }: { children: ReactNode }) {
  return (
    <label style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)', marginBottom: 6, display: 'block' }}>
      {children}
    </label>
  )
}
function Stat({ label, value, emphasised }: { label: ReactNode; value: ReactNode; emphasised?: boolean }) {
  return (
    <div>
      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginBottom: 4 }}>{label}</div>
      <div style={{
        fontSize: emphasised ? 'var(--text-2xl)' : 'var(--text-lg)',
        fontWeight: 700,
        color: emphasised ? 'var(--accent)' : 'var(--text-1)',
        fontFamily: 'var(--font-mono)',
      }}>
        {value}
      </div>
    </div>
  )
}

const th = { padding: '10px 14px', fontSize: 'var(--text-xs)', textTransform: 'uppercase',
             color: 'var(--text-3)', fontWeight: 600, letterSpacing: '0.06em' }
const td = { padding: '10px 14px', fontSize: 'var(--text-sm)', color: 'var(--text-1)' }
const selectStyle = {
  width: '100%', padding: '8px 12px', fontSize: 'var(--text-sm)',
  background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
  borderRadius: 6, color: 'var(--text-1)', fontFamily: 'inherit',
}

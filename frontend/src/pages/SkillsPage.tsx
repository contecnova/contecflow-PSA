/**
 * SkillsPage — habilidades del equipo: matriz, perfiles, búsqueda de personas
 * por habilidad y catálogo.
 *
 * 16-11-2026: título igual que el menú ("Habilidades"); KPIs con KpiCard en
 * .ds-grid-stats (antes cifra monoespaciada en cajas propias); pestañas del
 * modal con <Tabs> (antes botones a mano); iconos lucide en lugar de emojis
 * (categorías, historial, consejos, botones); vacíos con EmptyState; la matriz
 * sin habilidades ya no pinta una tabla de 150px dentro de una tarjeta ancha.
 */
import type { CSSProperties, ReactNode } from 'react'
import { useState, useId } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr, fmtDate } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { skillsApi, usersApi } from '../services/api'
import type { SkillDelCatalogo } from '../services/api/tipos-alm'
import type { CambioDeNivelDeSkill, MatrizDeSkills, PersonaPorSkills, SkillDePersona } from '../services/api/tipos-personas'
import { Button, Card, KpiCard, Modal, Section, Spinner, EmptyState, Tabs, IconButton, Select, Pulsable, TablaSimple, Checkbox, useErroresDeCampo } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Award, BookOpen, Code2, Grid3x3, HeartHandshake, History, Languages, Layers, Lightbulb, Pencil, Plus, Ruler, Search, Sparkles, Tags, UserRound, Users, Wrench, X } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useAppT } from '../i18n/AppLangContext'
import './SkillsPage.css'
import StatusBadge from '../components/ui/StatusBadge'

// ── Estilos compartidos (SkillsPage.css) ─────────────────────────────────────
const fs = 'ds-input skl-input'
const ls = 'skl-label'

// ── Tipos de dominio ──────────────────────────────────────────────────────────
type CatalogSkill = SkillDelCatalogo
type UserSkill = SkillDePersona
type MatrixUser = MatrizDeSkills['users'][number]
type SkillsMatrixData = MatrizDeSkills
type SkillHistoryEntry = CambioDeNivelDeSkill
type StaffMatch = PersonaPorSkills
interface DomainUser {
  id: string; full_name?: string; job_title?: string; role?: string
  department?: string; is_active?: boolean
}

// `label` y las categorías son claves de i18n (bloque `skills`).
const LEVEL_CFG: Record<string, { label: string; color: string; score: number }> = {
  basic:        { label: 'skills.nivel_basic',        color: 'var(--text-2)', score: 1 },
  intermediate: { label: 'skills.level_intermediate', color: 'var(--accent)', score: 2 },
  advanced:     { label: 'skills.level_advanced',     color: 'var(--warning)', score: 3 },
  expert:       { label: 'skills.level_expert',       color: 'var(--success)', score: 4 },
}
const CAT_ICONS: Record<string, ReactNode> = {
  technical: <Code2 size={13} aria-hidden />, language: <Languages size={13} aria-hidden />,
  methodology: <Ruler size={13} aria-hidden />, tool: <Wrench size={13} aria-hidden />,
  soft: <HeartHandshake size={13} aria-hidden />, certification: <Award size={13} aria-hidden />,
}
const CATEGORIES = Object.keys(CAT_ICONS)
const LEVELS = Object.keys(LEVEL_CFG)

/** Nombre traducido de la categoría, o la categoría tal cual si no es de las conocidas. */
function useCatLabel() {
  const t = useAppT()
  return (cat: string) => CAT_ICONS[cat] ? t('skills.cat_' + cat) : cat
}

/** Título de grupo por categoría: icono lucide + nombre. */
function CatTitle({ cat, label }: { cat: string; label: string }) {
  return <div className="skl-eyebrow">{CAT_ICONS[cat]}<span>{label}</span></div>
}

const colorVar = (color: string) => ({ '--skl-c': color } as CSSProperties)

function LevelBadge({ level }: { level?: string }) {
  const t = useAppT()
  const cfg = LEVEL_CFG[level || ''] || LEVEL_CFG.basic
  return (
    <StatusBadge color={cfg.color} caps={false}>
      {t(cfg.label)}
    </StatusBadge>
  )
}

function SkillsMatrix({ users, skills }: { users: MatrixUser[]; skills: SkillsMatrixData['skills'] }) {
  const t = useAppT()
  const levelColor = (level?: string) => LEVEL_CFG[level || '']?.color || 'transparent'

  const cats = [...new Set(skills.map(s => s.category))]

  return (
    <div className="u-scroll-x">
      <TablaSimple claseTabla="skl-matrix">
        <thead>
          <tr>
            <th scope="col" className="skl-matrix__corner">{t('skills.persona')}</th>
            {cats.map(cat => (
              skills.filter(s => s.category === cat).map(s => (
                <th key={s.id} scope="col" className="skl-matrix__skill" title={s.name}>
                  <div className="skl-matrix__rot">
                    {s.name}
                  </div>
                </th>
              ))
            ))}
          </tr>
          <tr>
            <th aria-hidden="true" className="skl-matrix__corner skl-matrix__corner--blank"></th>
            {cats.map(cat => (
              skills.filter(s => s.category === cat).map(s => (
                <th key={s.id + '-cat'} className="skl-matrix__catcell">
                  <div className="skl-matrix__cat" title={t('skills.cat_' + s.category, s.category)} aria-label={t('skills.cat_' + s.category, s.category)}>{CAT_ICONS[s.category]}</div>
                </th>
              ))
            ))}
          </tr>
        </thead>
        <tbody>
          {users.map(u => (
            <tr key={u.user_id}>
              <th scope="row" className="skl-matrix__user">
                <div className="skl-matrix__name">{u.user_name}</div>
                {u.department && <div className="u-text2-2xs">{u.department}</div>}
              </th>
              {cats.map(cat => (
                skills.filter(s => s.category === cat).map(s => {
                  const us = u.skills[s.id]
                  const nivel = us?.level ? LEVEL_CFG[us.level] : undefined
                  const titulo = us?.level ? `${nivel ? t(nivel.label) : us.level}${us.certified ? ` · ${t('skills.certificado')}` : ''}` : ''
                  return (
                    <td key={s.id} className="skl-matrix__cell">
                      {us?.level ? (
                        <div title={titulo} aria-label={`${s.name}: ${titulo}`} className="skl-level" style={colorVar(levelColor(us.level))}>
                          {nivel?.score}
                          {us.certified && <Award size={9} aria-hidden className="skl-level__cert" />}
                        </div>
                      ) : (
                        <div className="skl-level skl-level--empty" />
                      )}
                    </td>
                  )
                })
              ))}
            </tr>
          ))}
        </tbody>
      </TablaSimple>
    </div>
  )
}

function UserSkillModal({ user, onClose }: { user: DomainUser; onClose: () => void }) {
  const idCampo = useId()
  const t = useAppT()
  const catLabel = useCatLabel()
  const qc = useQueryClient()
  const toast = useToast()
  const [modalTab, setModalTab] = useState('skills')
  const [form, setForm] = useState({ skill_id: '', level: 'basic', years_experience: '', certified: false, cert_name: '', notes: '' })

  const { data: catalog = [] } = useQuery<CatalogSkill[]>({ queryKey: ['skills-catalog'], queryFn: () => skillsApi.catalog().then(r => r.data) })
  const { data: userSkills = [] } = useQuery<UserSkill[]>({ queryKey: ['user-skills', user.id], queryFn: () => skillsApi.userSkills(user.id).then(r => r.data) })
  const { data: skillHistory = [] } = useQuery<SkillHistoryEntry[]>({
    queryKey: ['skill-history', user.id],
    queryFn: () => skillsApi.userHistory(user.id).then(r => r.data).catch((): SkillHistoryEntry[] => []),
    enabled: modalTab === 'history',
  })

  const campos = useErroresDeCampo()
  const msg = (k: string) => campos.de(k) ? <div className="u-field-error">{campos.de(k)}</div> : null
  const { mutate: addSkill } = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: (data: Record<string, unknown>) => skillsApi.addUserSkill(user.id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['user-skills', user.id] }); qc.invalidateQueries({ queryKey: ['skills-matrix'] }); setForm({ skill_id: '', level: 'basic', years_experience: '', certified: false, cert_name: '', notes: '' }) },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) },
  })
  const { mutate: removeSkill } = useMutation({
    mutationFn: (skillId: string) => skillsApi.removeUserSkill(user.id, skillId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['user-skills', user.id] }); qc.invalidateQueries({ queryKey: ['skills-matrix'] }) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const byCategory = userSkills.reduce<Record<string, UserSkill[]>>((a, s) => { const c = s.category || ''; if (!a[c]) a[c] = []; a[c]!.push(s); return a }, {})
  const nivelDe = (l?: string) => (l && LEVEL_CFG[l] ? t(LEVEL_CFG[l].label) : l)

  return (
    <Modal open title={t('skills.modal_titulo', { name: user.full_name || '' })} onClose={onClose} width={620}>
      <div className="skl-modal-tabs">
        <Tabs
          ariaLabel={t('skills.title')}
          active={modalTab}
          onChange={setModalTab}
          items={[
            { id: 'skills', label: t('skills.tab_skills'), icon: <Sparkles size={14} /> },
            { id: 'history', label: t('skills.tab_historial'), icon: <History size={14} /> },
          ]}
        />
      </div>

      {modalTab === 'history' && (
        <div>
          {skillHistory.length === 0 ? (
            <EmptyState icon={<History size={28} />} title={t('skills.sin_historial_de_evaluaciones_registrado')} />
          ) : skillHistory.map(e => {
            return (
              <div key={e.id} className="skl-history">
                <div className="u-flex1-min0">
                  <div className="skl-history__name">{e.skill_name}</div>
                  <div className="skl-history__levels">
                    {e.old_level && <span className="u-text2">{nivelDe(e.old_level)}</span>}
                    {e.old_level && <span className="u-text2" aria-hidden="true">→</span>}
                    <span className="skl-history__new">{nivelDe(e.new_level)}</span>
                  </div>
                  {e.notes && <div className="skl-history__notes">{e.notes}</div>}
                </div>
                <div className="skl-history__when">
                  <div className="u-text3-xs">{fmtDate(e.recorded_at)}</div>
                  <div className="u-text2-xs">{t('skills.por')} {e.recorded_by}</div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {modalTab === 'skills' && (
      <div>
      {/* Existing skills */}
      <div className="u-mb-20">
        {Object.keys(byCategory).length === 0 ? (
          <EmptyState icon={<Sparkles size={28} />} title={t('skills.sin_skills_registrados')} description={t('skills.sin_skills_registrados_desc')} />
        ) : Object.entries(byCategory).map(([cat, skills]) => (
          <div key={cat} className="u-mb-14">
            <CatTitle cat={cat} label={catLabel(cat)} />
            <div className="u-wrap-8">
              {skills.map(s => (
                <div key={s.id} className="skl-chip">
                  <span className="u-base-600">{s.skill_name}</span>
                  <LevelBadge level={s.level} />
                  {s.years_experience && <span className="u-text2-xs">{t('skills.anos_abrev', { n: s.years_experience })}</span>}
                  {s.certified && <StatusBadge kind="success" caps={false}>{t('skills.cert_abrev')}</StatusBadge>}
                  <IconButton type="button" onClick={() => { openConfirmGlobal({ message: t('skills.confirm_quitar_usuario'), onConfirm: () => removeSkill(s.id), danger: true }) }} className="skl-x"
                    ariaLabel={t('skills.quitar_skill', { name: s.skill_name || '' })} title={t('skills.quitar_skill', { name: s.skill_name || '' })}><X size={14} aria-hidden /></IconButton>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Add skill */}
      <div className="skl-add">
        <div className="skl-add__title">{t('skills.anadir_nuevo_skill')}</div>
        <div className="skl-add__grid">
          <div>
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className={ls}>{t('skills.skill_req')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-1`} value={form.skill_id} onChange={e => { campos.limpiar('skill_id'); setForm(f => ({ ...f, skill_id: e.target.value })) }} className={`${fs}${form.skill_id ? ' skl-input--picked' : ''}`}>
              <option value="">{t('skills.selecciona_un_skill')}</option>
              {CATEGORIES.map(cat => (
                <optgroup key={cat} label={catLabel(cat)}>
                  {catalog.filter(s => s.category === cat).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                </optgroup>
              ))}
            </Select>{msg('skill_id')}
          </div>
          <div>
            <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className={ls}>{t('skills.nivel_req')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-2`} value={form.level} onChange={e => { campos.limpiar('level'); setForm(f => ({ ...f, level: e.target.value })) }} className={fs}>
              {LEVELS.map(l => <option key={l} value={l}>{t(LEVEL_CFG[l].label)}</option>)}
            </Select>{msg('level')}
          </div>
          <div>
            <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className={ls}>{t('skills.anos_exp')}</label>
            <input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} type="number" min="0" max="30" step="0.5" value={form.years_experience} onChange={e => { campos.limpiar('years_experience'); setForm(f => ({ ...f, years_experience: e.target.value })) }} className={fs} placeholder={t('skills.anos_placeholder')} />{msg('years_experience')}
          </div>
        </div>
        <div className="skl-add__row">
          <Checkbox className="skl-check" checked={!!form.certified} onChange={v => { campos.limpiar('certified'); setForm(f => ({ ...f, certified: v })) }}
            label={t('skills.tiene_certificacion')} />
          {form.certified && (
            <input aria-label={t('skills.nombre_de_la_certificacion')} value={form.cert_name} onChange={e => { campos.limpiar('cert_name'); setForm(f => ({ ...f, cert_name: e.target.value })) }} className={`${fs} skl-input--grow`} placeholder={t('skills.nombre_de_la_certificacion')} />
          )}
          {msg('cert_name')}
        </div>
        <Button
          icon={<Plus size={14} />}
          onClick={() => form.skill_id && addSkill(form)}
          disabled={!form.skill_id}>
          {form.skill_id ? t('skills.anadir_al_perfil', { name: catalog.find(s => s.id === form.skill_id)?.name || '' }) : t('skills.selecciona_para_anadir')}
        </Button>
      </div>
      </div>
      )}
    </Modal>
  )
}

function StaffingSearch() {
  const t = useAppT()
  const [selectedSkills, setSelectedSkills] = useState<string[]>([])
  const [minLevel, setMinLevel] = useState('basic')
  const [results, setResults] = useState<StaffMatch[] | null>(null)
  const [searching, setSearching] = useState(false)
  const idNivel = useId()

  const { data: catalog = [] } = useQuery<CatalogSkill[]>({ queryKey: ['skills-catalog'], queryFn: () => skillsApi.catalog().then(r => r.data) })

  const search = async () => {
    if (selectedSkills.length === 0) return
    setSearching(true)
    try {
      const r = await skillsApi.search({ skill_ids: selectedSkills.join(','), min_level: minLevel })
      setResults(r.data)
    } finally { setSearching(false) }
  }

  const toggleSkill = (id: string) => setSelectedSkills(s => s.includes(id) ? s.filter(x => x !== id) : [...s, id])

  return (
    <Card>
      <Section title={<span className="skl-titulo"><Search size={16} aria-hidden />{t('skills.buscar_recursos_por_skills')}</span>}>
      <div className="skl-staff__filters">
        <div className="skl-flex2" role="group" aria-label={t('skills.skills_requeridos')}>
          <div className="skl-eyebrow">{t('skills.skills_requeridos')}</div>
          <div className="u-wrap-6">
            {catalog.map(s => (
              <Pulsable key={s.id} type="button" onClick={() => toggleSkill(s.id)} aria-pressed={selectedSkills.includes(s.id)} className="skl-toggle">
                {s.name}
              </Pulsable>
            ))}
          </div>
        </div>
        <div className="u-flex1">
          <label htmlFor={idNivel} className="skl-eyebrow skl-eyebrow--block">{t('skills.nivel_minimo')}</label>
          <Select suelto placeholder={false} id={idNivel} value={minLevel} onChange={e => setMinLevel(e.target.value)} className={fs}>
            {LEVELS.map(l => <option key={l} value={l}>{t(LEVEL_CFG[l].label)}</option>)}
          </Select>
        </div>
      </div>
      <Button icon={<Search size={14} />} onClick={search} disabled={selectedSkills.length === 0 || searching}>
        {searching ? t('skills.buscando') : t('skills.buscar_n', { n: selectedSkills.length })}
      </Button>

      {results !== null && (
        <div className="skl-results">
          <div className="skl-results__count" role="status">{t('skills.n_recursos', { n: results.length })}</div>
          {results.length === 0 ? (
            <EmptyState icon={<Search size={28} />} title={t('skills.sin_recursos_para_estos_criterios')} description={t('skills.sin_recursos_desc')} />
          ) : (
            <div className="u-stack-10">
              {results.map(u => (
                <div key={u.user_id} className="skl-match">
                  <div className="skl-match__head">
                    <div>
                      <div className="u-base-700">{u.user_name}</div>
                      <div className="u-text2-xs">{u.department} · {u.role}</div>
                    </div>
                    <span className="skl-match__count">{t('skills.n_skills', { n: u.skill_count })}</span>
                  </div>
                  <div className="u-wrap-6">
                    {u.matching_skills.map(s => (
                      <div key={s.skill_id} className="u-row-center-6">
                        <span className="skl-match__skill">{s.skill_name}</span>
                        <LevelBadge level={s.level} />
                        {s.years_experience && <span className="u-text2-2xs">{t('skills.anos_abrev', { n: s.years_experience })}</span>}
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      </Section>
    </Card>
  )
}

function UserSkillPreview({ userId }: { userId: string }) {
  const t = useAppT()
  const { data: skills = [] } = useQuery<UserSkill[]>({
    queryKey: ['user-skills-preview', userId],
    queryFn: () => skillsApi.userSkills(userId).then(r => r.data),
  })
  if (skills.length === 0) return <div className="u-text3-sm">{t('skills.sin_skills_registrados_haz_clic_para_anadir')}</div>
  return (
    <div className="skl-preview">
      {skills.slice(0, 6).map(s => {
        const cfg = LEVEL_CFG[s.level || ''] || LEVEL_CFG.basic
        return (
          <span key={s.id} className="skl-preview__pill" style={colorVar(cfg.color)}>
            {s.skill_name}
          </span>
        )
      })}
      {skills.length > 6 && <span className="u-text2-xs">+{skills.length - 6} {t('skills.mas')}</span>}
    </div>
  )
}

export default function SkillsPage() {
  const t = useAppT()
  const catLabel = useCatLabel()
  const { puede } = useAuth()
  const toast = useToast()
  const qc = useQueryClient()
  // Matriz, Staffing y Catálogo leen endpoints de admin y hr; el resto entra
  // por Perfiles (revisión 2026-11: antes la pestaña inicial les daba 403).
  const esGestor = puede('competencias.gestionar')
  const [tab, setTab] = useState(esGestor ? 'matrix' : 'profiles')
  const [editingUser, setEditingUser] = useState<DomainUser | null>(null)

  const { data: matrix, isLoading: loadingMatrix } = useQuery<SkillsMatrixData>({
    queryKey: ['skills-matrix'],
    queryFn: () => skillsApi.matrix().then(r => r.data),
    enabled: tab === 'matrix',
  })

  const { data: catalog = [], isLoading: loadingCatalog } = useQuery<CatalogSkill[]>({
    queryKey: ['skills-catalog'],
    queryFn: () => skillsApi.catalog().then(r => r.data),
    enabled: tab === 'catalog',
  })

  const { data: users = [] } = useQuery<DomainUser[]>({
    queryKey: ['users'],
    queryFn: () => usersApi.list().then(r => r.data),
    enabled: tab === 'profiles',
  })

  const { mutate: createSkill } = useMutation({
    mutationFn: (data: Record<string, unknown>) => skillsApi.createCatalog(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['skills-catalog'] }),
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: deleteSkill } = useMutation({
    mutationFn: (id: string) => skillsApi.deleteCatalog(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['skills-catalog'] }),
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const [newSkill, setNewSkill] = useState({ name: '', category: 'technical', description: '' })

  const tabs = [
    ...(esGestor ? [{ id: 'matrix', label: t('skills.tab_matriz'), icon: <Grid3x3 size={14} /> }] : []),
    { id: 'profiles', label: t('skills.tab_perfiles'), icon: <UserRound size={14} /> },
    ...(esGestor ? [
      { id: 'search', label: t('skills.tab_staffing'), icon: <Search size={14} /> },
      { id: 'catalog', label: t('skills.tab_catalogo'), icon: <BookOpen size={14} /> },
    ] : []),
  ]
  const activos = users.filter(u => u.is_active !== false)

  // KPI stats
  const totalSkillsInCatalog = catalog.length
  const activeUsers = users.filter(u => u.is_active !== false).length
  const matrixSkillCount = matrix?.skills?.length ?? 0

  return (
    <PageShell>
      <PageHeader icon={<Award size={18} />} title={t('skills.title')} subtitle={t('skills.subtitle')} />

      <div className="u-stack-16">
      <div className="ds-grid-stats">
        <KpiCard icon={<BookOpen size={16} />} label={t('skills.kpi_catalogo')} value={totalSkillsInCatalog || matrixSkillCount} />
        <KpiCard icon={<Users size={16} />} label={t('skills.kpi_personas')} value={matrix?.users?.length ?? activeUsers} />
        <KpiCard icon={<Tags size={16} />} label={t('skills.kpi_categorias')} value={CATEGORIES.length} />
      </div>

      {tabs.length > 1 && <Tabs items={tabs} active={tab} onChange={setTab} ariaLabel={t('skills.title')} />}

      {tab === 'matrix' && (
        loadingMatrix ? <Spinner /> : !matrix ? null : (matrix.users.length === 0 || matrix.skills.length === 0) ? (
          <EmptyState icon={<Grid3x3 size={28} />} title={t('skills.sin_datos_de_skills')} description={t('skills.sin_datos_desc')} />
        ) : (
          <Card>
            <div className="skl-legend">
              {Object.entries(LEVEL_CFG).map(([l, cfg]) => (
                <div key={l} className="u-row-center-6">
                  <div className="skl-level skl-level--legend" style={colorVar(cfg.color)} aria-hidden="true">{cfg.score}</div>
                  <span className="u-text2-xs">{t(cfg.label)}</span>
                </div>
              ))}
            </div>
            <SkillsMatrix users={matrix.users} skills={matrix.skills} />
          </Card>
        )
      )}

      {tab === 'profiles' && (
        activos.length === 0 ? (
          <EmptyState icon={<Users size={28} />} title={t('skills.sin_personas')} description={t('skills.sin_personas_desc')} />
        ) : (
        <div className="u-stack-16">
          <div className="skl-tip">
            <Lightbulb size={16} aria-hidden className="skl-tip__icon" />
            <span>{t('skills.haz_clic_en_cualquier_persona_para_ver')}</span>
          </div>
          <div className="skl-people">
            {activos.map(u => (
              <Pulsable key={u.id} type="button"
                onClick={() => setEditingUser(u)}
                className="skl-person">
                <div className="skl-person__head">
                  <div className="u-min0">
                    <div className="skl-person__name">{u.full_name}</div>
                    <div className="u-text2-sm-mt2">{u.job_title || u.role} · {u.department || '—'}</div>
                  </div>
                  <span className="skl-person__cta">
                    <Pencil size={13} aria-hidden />{t('skills.gestionar_skills')}
                  </span>
                </div>
                <UserSkillPreview userId={u.id} />
              </Pulsable>
            ))}
          </div>
        </div>
        )
      )}

      {tab === 'search' && <StaffingSearch />}

      {tab === 'catalog' && (
        <div className="u-stack-16">
          <Card>
            <Section title={t('skills.anadir_nuevo_skill_al_catalogo')}>
            <div className="skl-catalog__form">
              <input aria-label={t('skills.nombre_del_skill')} value={newSkill.name} onChange={e => setNewSkill(f => ({ ...f, name: e.target.value }))} className={`${fs} skl-input--grow2`} placeholder={t('skills.nombre_del_skill')} />
              <Select suelto placeholder={false} aria-label={t('skills.category')} value={newSkill.category} onChange={e => setNewSkill(f => ({ ...f, category: e.target.value }))} className={`${fs} skl-input--grow1`}>
                {CATEGORIES.map(c => <option key={c} value={c}>{catLabel(c)}</option>)}
              </Select>
              <Button icon={<Plus size={14} />} onClick={() => { createSkill(newSkill); setNewSkill({ name: '', category: 'technical', description: '' }) }} disabled={!newSkill.name}>{t('skills.anadir')}</Button>
            </div>
            </Section>
          </Card>
          {loadingCatalog ? <Spinner /> : catalog.length === 0 ? (
            <EmptyState icon={<Layers size={28} />} title={t('skills.no_skills')} description={t('skills.catalogo_vacio_desc')} />
          ) : (
            <div className="u-stack-8">
              {CATEGORIES.filter(cat => catalog.some(s => s.category === cat)).map(cat => (
                <div key={cat}>
                  <CatTitle cat={cat} label={catLabel(cat)} />
                  <div className="skl-catalog__list">
                    {catalog.filter(s => s.category === cat).map(s => (
                      <div key={s.id} className="skl-chip skl-chip--catalog">
                        <span className="skl-base">{s.name}</span>
                        <span className="u-text2-xs">{t('skills.n_usuarios', { n: s.user_count ?? 0 })}</span>
                        <IconButton type="button" onClick={() => { openConfirmGlobal({ message: t('skills.confirm_quitar_catalogo'), onConfirm: () => deleteSkill(s.id), danger: true }) }} className="skl-x"
                          ariaLabel={t('skills.quitar_skill', { name: s.name })} title={t('skills.quitar_skill', { name: s.name })}><X size={14} aria-hidden /></IconButton>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      </div>

      {editingUser && <UserSkillModal user={editingUser} onClose={() => setEditingUser(null)} />}
    </PageShell>
  )
}

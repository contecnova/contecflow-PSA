import { useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'
import { Card, Button, Modal, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { Zap } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useAppT } from '../i18n/AppLangContext'

// ── Estilos compartidos ───────────────────────────────────────────────────────
const _fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const _ls = { fontSize: 11, fontWeight: 600, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }


const LEVEL_CFG = {
  basic:        { label: 'Básico',       color: 'var(--text-2)', score: 1 },
  intermediate: { label: 'Intermedio',   color: 'var(--accent)', score: 2 },
  advanced:     { label: 'Avanzado',     color: 'var(--warning)', score: 3 },
  expert:       { label: 'Experto',      color: 'var(--success)', score: 4 },
}
const CAT_LABELS = {
  technical: '💻 Técnico', language: '🌍 Idioma', methodology: '📐 Metodología',
  tool: '🔧 Herramienta', soft: '🤝 Habilidad blanda', certification: '🏆 Certificación'
}
const CATEGORIES = Object.keys(CAT_LABELS)
const LEVELS = Object.keys(LEVEL_CFG)

function LevelBadge({ level }) {
  const cfg = LEVEL_CFG[level] || LEVEL_CFG.basic
  return (
    <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 20, background: cfg.color + '20', color: cfg.color, border: `1px solid ${cfg.color}40`, whiteSpace: 'nowrap' }}>
      {'★'.repeat(cfg.score)}{'☆'.repeat(4 - cfg.score)} {cfg.label}
    </span>
  )
}

function SkillsMatrix({ users, skills }) {
  const _levelScore = { basic: 1, intermediate: 2, advanced: 3, expert: 4 }
  const levelColor = (level) => LEVEL_CFG[level]?.color || 'transparent'

  const cats = [...new Set(skills.map(s => s.category))]

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ borderCollapse: 'separate', borderSpacing: 2, fontSize: 11 }}>
        <thead>
          <tr>
            <th style={{ padding: '8px 12px', textAlign: 'left', color: 'var(--text-2)', minWidth: 150, position: 'sticky', left: 0, background: 'var(--surface-0)', zIndex: 2 }}>Persona</th>
            {cats.map(cat => (
              skills.filter(s => s.category === cat).map(s => (
                <th key={s.id} style={{ padding: '4px 6px', color: 'var(--text-2)', textAlign: 'center', minWidth: 70, maxWidth: 80, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  <div style={{ transform: 'rotate(-35deg)', transformOrigin: 'bottom left', height: 60, display: 'flex', alignItems: 'flex-end' }}>
                    {s.name}
                  </div>
                </th>
              ))
            ))}
          </tr>
          <tr>
            <th style={{ position: 'sticky', left: 0, background: 'var(--surface-0)', zIndex: 2 }}></th>
            {cats.map(cat => (
              skills.filter(s => s.category === cat).map(s => (
                <th key={s.id + '-cat'} style={{ padding: '2px 4px', textAlign: 'center' }}>
                  <div style={{ fontSize: 9, color: 'var(--text-3)' }}>{CAT_LABELS[s.category]?.split(' ')[0]}</div>
                </th>
              ))
            ))}
          </tr>
        </thead>
        <tbody>
          {users.map(u => (
            <tr key={u.user_id}>
              <td style={{ padding: '4px 12px', position: 'sticky', left: 0, background: 'var(--surface-2)', zIndex: 1, borderBottom: '1px solid var(--surface-4)' }}>
                <div style={{ fontSize: 12, fontWeight: 600 }}>{u.user_name}</div>
                {u.department && <div style={{ fontSize: 10, color: 'var(--text-2)' }}>{u.department}</div>}
              </td>
              {cats.map(cat => (
                skills.filter(s => s.category === cat).map(s => {
                  const us = u.skills[s.id]
                  return (
                    <td key={s.id} style={{ padding: 2, textAlign: 'center', borderBottom: '1px solid var(--surface-4)20' }}>
                      {us?.level ? (
                        <div title={`${LEVEL_CFG[us.level]?.label}${us.certified ? ' · Certificado' : ''}`}
                          style={{ width: 28, height: 28, borderRadius: 6, background: levelColor(us.level) + '30', border: `1px solid ${levelColor(us.level)}60`, display: 'flex', alignItems: 'center', justifyContent: 'center', margin: 'auto', fontSize: 10, color: levelColor(us.level), fontWeight: 700 }}>
                          {LEVEL_CFG[us.level]?.score}
                          {us.certified && <span style={{ fontSize: 8 }}>✓</span>}
                        </div>
                      ) : (
                        <div style={{ width: 28, height: 28, borderRadius: 6, background: 'var(--surface-4)', margin: 'auto' }} />
                      )}
                    </td>
                  )
                })
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function UserSkillModal({ user, onClose }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [modalTab, setModalTab] = useState('skills')
  const [form, setForm] = useState({ skill_id: '', level: 'basic', years_experience: '', certified: false, cert_name: '', notes: '' })
  const fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const ls = { fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

  const { data: catalog = [] } = useQuery({ queryKey: ['skills-catalog'], queryFn: () => api.get('/skills/catalog').then(r => r.data) })
  const { data: userSkills = [] } = useQuery({ queryKey: ['user-skills', user.id], queryFn: () => api.get(`/skills/users/${user.id}`).then(r => r.data) })
  const { data: skillHistory = [] } = useQuery({
    queryKey: ['skill-history', user.id],
    queryFn: () => api.get(`/skills/users/${user.id}/history`).then(r => r.data).catch(() => []),
    enabled: modalTab === 'history',
  })

  const { mutate: addSkill } = useMutation({
    mutationFn: (data) => api.post(`/skills/users/${user.id}`, data),
    onSuccess: () => { qc.invalidateQueries(['user-skills', user.id]); qc.invalidateQueries(['skills-matrix']); setForm({ skill_id: '', level: 'basic', years_experience: '', certified: false, cert_name: '', notes: '' }) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: removeSkill } = useMutation({
    mutationFn: (skillId) => api.delete(`/skills/users/${user.id}/${skillId}`),
    onSuccess: () => { qc.invalidateQueries(['user-skills', user.id]); qc.invalidateQueries(['skills-matrix']) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const byCategory = userSkills.reduce((a, s) => { const c = s.category; if (!a[c]) a[c] = []; a[c].push(s); return a }, {})

  return (
    <Modal open title={`Skills — ${user.full_name}`} onClose={onClose} width={620}>
      {/* Tabs */}
      <div style={{ display:'flex', gap:6, marginBottom: 20 , borderBottom: '1px solid var(--surface-4)', paddingBottom: 12 }}>
        {[['skills','🧠 Skills'],['history','📈 Historial']].map(([id,label]) => (
          <button key={id} onClick={() => setModalTab(id)}
            style={{ padding:'6px 14px', borderRadius:7, fontSize:12, fontWeight:600,
              border: `1px solid ${modalTab===id ? 'var(--accent-glow)' : 'var(--surface-4)'}`,
              background: modalTab===id ? 'var(--accent-muted)' : 'transparent',
              color: modalTab===id ? 'var(--accent)' : 'var(--text-2)',
              cursor:'pointer', fontFamily:'inherit' }}>
            {label}
          </button>
        ))}
      </div>

      {modalTab === 'history' && (
        <div>
          {skillHistory.length === 0 ? (
            <div style={{ textAlign:'center', padding:'32px 0', color:'var(--text-3)', fontSize:13 }}>
              Sin historial de evaluaciones registrado
            </div>
          ) : skillHistory.map(e => {
            const LEVEL_ICONS = { basic:'⬜', intermediate:'🔵', advanced:'🟣', expert:'⭐' }
            return (
              <div key={e.id} style={{ display:'flex', gap:12, padding:'10px 14px',
                background:'var(--surface-2)', border:'1px solid var(--surface-4)',
                borderRadius:10, marginBottom:6 }}>
                <div style={{ flex:1, minWidth:0 }}>
                  <div style={{ fontSize:13, fontWeight:600, marginBottom:2 }}>{e.skill_name}</div>
                  <div style={{ display:'flex', alignItems:'center', gap:8, fontSize:12 }}>
                    {e.old_level && <span style={{ color:'var(--text-3)' }}>{LEVEL_ICONS[e.old_level]} {e.old_level}</span>}
                    {e.old_level && <span style={{ color:'var(--text-3)' }}>→</span>}
                    <span style={{ color:'var(--accent)', fontWeight:600 }}>{LEVEL_ICONS[e.new_level]} {e.new_level}</span>
                  </div>
                  {e.notes && <div style={{ fontSize:11, color:'var(--text-2)', marginTop:3 }}>{e.notes}</div>}
                </div>
                <div style={{ textAlign:'right', flexShrink:0 }}>
                  <div style={{ fontSize:11, color:'var(--text-3)' }}>{e.recorded_at?.slice(0,10)}</div>
                  <div style={{ fontSize:11, color:'var(--text-2)' }}>por {e.recorded_by}</div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {modalTab === 'skills' && (
      <div>
      {/* Existing skills */}
      <div style={{ marginBottom: 20 }}>
        {Object.keys(byCategory).length === 0 ? (
          <div style={{ fontSize: 13, color: 'var(--text-2)', textAlign: 'center', padding: '16px 0' }}>Sin skills registrados</div>
        ) : Object.entries(byCategory).map(([cat, skills]) => (
          <div key={cat} style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>{CAT_LABELS[cat] || cat}</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {skills.map(s => (
                <div key={s.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px', background: 'var(--surface-3)', borderRadius: 8, border: '1px solid var(--surface-4)' }}>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>{s.skill_name}</span>
                  <LevelBadge level={s.level} />
                  {s.years_experience && <span style={{ fontSize: 11, color: 'var(--text-2)' }}>{s.years_experience}a</span>}
                  {s.certified && <span style={{ fontSize: 10, color: 'var(--success)' }}>✓ Cert.</span>}
                  <button onClick={() => { openConfirmGlobal({ message: '¿Eliminar esta habilidad del usuario?', onConfirm: () => removeSkill(s.id), danger: true }) }} style={{ background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer', fontSize: 14, padding: 0 }}>×</button>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Add skill */}
      <div style={{ padding: 16, background: 'var(--accent-muted)', border: '2px dashed var(--accent-muted)', borderRadius: 10 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--accent)', marginBottom: 14 }}>➕ Añadir nuevo skill</div>
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr', gap: 10, marginBottom: 12 }}>
          <div>
            <label style={ls}>Skill *</label>
            <select value={form.skill_id} onChange={e => setForm(f => ({ ...f, skill_id: e.target.value }))} style={{ ...fs, borderColor: form.skill_id ? 'var(--accent-glow)' : 'var(--surface-4)' }}>
              <option value="">— Selecciona un skill —</option>
              {CATEGORIES.map(cat => (
                <optgroup key={cat} label={CAT_LABELS[cat] || cat}>
                  {catalog.filter(s => s.category === cat).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                </optgroup>
              ))}
            </select>
          </div>
          <div>
            <label style={ls}>Nivel *</label>
            <select value={form.level} onChange={e => setForm(f => ({ ...f, level: e.target.value }))} style={fs}>
              {LEVELS.map(l => <option key={l} value={l}>{LEVEL_CFG[l].label} {'★'.repeat(LEVEL_CFG[l].score)}</option>)}
            </select>
          </div>
          <div>
            <label style={ls}>Años exp.</label>
            <input type="number" min="0" max="30" step="0.5" value={form.years_experience} onChange={e => setForm(f => ({ ...f, years_experience: e.target.value }))} style={fs} placeholder="Ej: 3.5" />
          </div>
        </div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 14 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13, color: 'var(--text-1)' }}>
            <input type="checkbox" checked={form.certified} onChange={e => setForm(f => ({ ...f, certified: e.target.checked }))} />
            Tiene certificación
          </label>
          {form.certified && (
            <input value={form.cert_name} onChange={e => setForm(f => ({ ...f, cert_name: e.target.value }))} style={{ ...fs, flex: 1 }} placeholder="Nombre de la certificacion" />
          )}
        </div>
        <button
          onClick={() => form.skill_id && addSkill(form)}
          disabled={!form.skill_id}
          style={{
            width: '100%', padding: '11px', borderRadius: 8, border: 'none', cursor: form.skill_id ? 'pointer' : 'not-allowed',
            background: form.skill_id ? 'linear-gradient(135deg, #00d4ff, #7c3aed)' : 'var(--surface-4)',
            color: form.skill_id ? '#fff' : 'var(--text-3)', fontSize: 14, fontWeight: 700, fontFamily: 'inherit',
            transition: 'all 0.15s',
          }}>
          {form.skill_id ? `✓ Añadir "${catalog.find(s => s.id === form.skill_id)?.name || ''}" al perfil` : 'Selecciona un skill para añadir'}
        </button>
      </div>
      </div>
      )}
    </Modal>
  )
}

function StaffingSearch() {
  const [selectedSkills, setSelectedSkills] = useState([])
  const [minLevel, setMinLevel] = useState('basic')
  const [results, setResults] = useState(null)
  const [searching, setSearching] = useState(false)

  const { data: catalog = [] } = useQuery({ queryKey: ['skills-catalog'], queryFn: () => api.get('/skills/catalog').then(r => r.data) })

  const search = async () => {
    if (selectedSkills.length === 0) return
    setSearching(true)
    try {
      const r = await api.get(`/skills/search?skill_ids=${selectedSkills.join(',')}&min_level=${minLevel}`)
      setResults(r.data)
    } finally { setSearching(false) }
  }

  const toggleSkill = (id) => setSelectedSkills(s => s.includes(id) ? s.filter(x => x !== id) : [...s, id])

  return (
    <Card style={{ padding: 20 }}>
      <h3 style={{ fontSize: 14, fontWeight: 700, marginBottom: 16 }}>🔍 Buscar recursos por skills</h3>
      <div style={{ display: 'flex', gap: 16, marginBottom: 16, flexWrap: 'wrap' }}>
        <div style={{ flex: 2 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>Skills requeridos</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {catalog.map(s => (
              <button key={s.id} onClick={() => toggleSkill(s.id)}
                style={{ padding: '4px 10px', borderRadius: 20, border: `1px solid ${selectedSkills.includes(s.id) ? 'var(--accent-glow)' : 'var(--surface-4)'}`, background: selectedSkills.includes(s.id) ? 'var(--accent-glow)' : 'var(--surface-3)', color: selectedSkills.includes(s.id) ? 'var(--accent)' : 'var(--text-2)', fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }}>
                {s.name}
              </button>
            ))}
          </div>
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>Nivel mínimo</div>
          <select value={minLevel} onChange={e => setMinLevel(e.target.value)}
            style={{ width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit' }}>
            {LEVELS.map(l => <option key={l} value={l}>{LEVEL_CFG[l].label}</option>)}
          </select>
        </div>
      </div>
      <Button onClick={search} disabled={selectedSkills.length === 0 || searching}>
        {searching ? 'Buscando...' : `Buscar (${selectedSkills.length} skills)`}
      </Button>

      {results !== null && (
        <div style={{ marginTop: 16 }}>
          <div style={{ fontSize: 13, color: 'var(--text-2)', marginBottom: 10 }}>{results.length} recursos encontrados</div>
          {results.length === 0 ? (
            <EmptyState icon="🔍" title="Sin recursos para estos criterios" description="Ajusta los skills o el nivel minimo requerido" />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {results.map(u => (
                <div key={u.user_id} style={{ padding: '12px 16px', background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 700 }}>{u.user_name}</div>
                      <div style={{ fontSize: 11, color: 'var(--text-2)' }}>{u.department} · {u.role}</div>
                    </div>
                    <span style={{ fontSize: 11, background: 'var(--success-bg)', color: 'var(--success)', border: '1px solid #00e5a030', borderRadius: 20, padding: '3px 10px' }}>{u.skill_count} skills</span>
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {u.matching_skills.map(s => (
                      <div key={s.skill_id} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span style={{ fontSize: 12, color: 'var(--text-1)' }}>{s.skill_name}</span>
                        <LevelBadge level={s.level} />
                        {s.years_experience && <span style={{ fontSize: 10, color: 'var(--text-2)' }}>{s.years_experience}a</span>}
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </Card>
  )
}

function UserSkillPreview({ userId }) {
  const { data: skills = [] } = useQuery({
    queryKey: ['user-skills-preview', userId],
    queryFn: () => api.get(`/skills/users/${userId}`).then(r => r.data),
  })
  if (skills.length === 0) return <div style={{ fontSize: 12, color: 'var(--text-3)' }}>Sin skills registrados · haz clic para añadir</div>
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
      {skills.slice(0, 6).map(s => {
        const cfg = LEVEL_CFG[s.level] || LEVEL_CFG.basic
        return (
          <span key={s.id} style={{ fontSize: 11, padding: '2px 7px', borderRadius: 20, background: cfg.color + '15', color: cfg.color, border: `1px solid ${cfg.color}30` }}>
            {s.skill_name}
          </span>
        )
      })}
      {skills.length > 6 && <span style={{ fontSize: 11, color: 'var(--text-2)' }}>+{skills.length - 6} más</span>}
    </div>
  )
}

export default function SkillsPage() {
  const t = useAppT()
  const { _user, hasRole } = useAuth()
  const toast = useToast()
  const qc = useQueryClient()
  const [tab, setTab] = useState('matrix')
  const [editingUser, setEditingUser] = useState(null)

  const { data: matrix, isLoading: loadingMatrix } = useQuery({
    queryKey: ['skills-matrix'],
    queryFn: () => api.get('/skills/matrix').then(r => r.data),
    enabled: tab === 'matrix',
  })

  const { data: catalog = [], isLoading: loadingCatalog } = useQuery({
    queryKey: ['skills-catalog'],
    queryFn: () => api.get('/skills/catalog').then(r => r.data),
    enabled: tab === 'catalog',
  })

  const { data: users = [] } = useQuery({
    queryKey: ['users'],
    queryFn: () => api.get('/users').then(r => r.data),
    enabled: tab === 'profiles',
  })

  const { mutate: createSkill } = useMutation({
    mutationFn: (data) => api.post('/skills/catalog', data),
    onSuccess: () => qc.invalidateQueries(['skills-catalog']),
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: deleteSkill } = useMutation({
    mutationFn: (id) => api.delete(`/skills/catalog/${id}`),
    onSuccess: () => qc.invalidateQueries(['skills-catalog']),
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const [newSkill, setNewSkill] = useState({ name: '', category: 'technical', description: '' })
  const inputStyle = { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit' }

  const tabs = [
    { id: 'matrix',   label: 'Matriz' },
    { id: 'profiles', label: 'Perfiles' },
    { id: 'search',   label: 'Staffing' },
    ...(hasRole('admin', 'hr') ? [{ id: 'catalog', label: 'Catálogo' }] : []),
  ]

  // KPI stats
  const totalSkillsInCatalog = catalog.length
  const activeUsers = users.filter(u => u.is_active !== false).length
  const matrixSkillCount = matrix?.skills?.length ?? 0

  return (
    <div style={{ padding: 32 }}>
      <PageHeader icon={<Zap size={18} />} title={t('skills.title')} subtitle={t('skills.subtitle')} />

      {/* KPI bar */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 24 }}>
        {[
          { label: 'Skills en catálogo',  value: totalSkillsInCatalog || matrixSkillCount, color: 'var(--accent)' },
          { label: 'Personas evaluadas',  value: matrix?.users?.length ?? activeUsers,     color: 'var(--success)' },
          { label: 'Categorías',          value: Object.keys(CAT_LABELS).length,           color: 'var(--purple)' },
        ].map(k => (
          <div key={k.label} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: '14px 18px' }}>
            <div style={{ fontSize: 24, fontWeight: 800, fontFamily: "'Space Mono', monospace", color: k.color, lineHeight: 1.1 }}>{k.value}</div>
            <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 4 }}>{k.label}</div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 24, background: 'var(--surface-1)', borderRadius: 10, padding: 4, width: 'fit-content' }}>
        {tabs.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            style={{ padding: '7px 18px', borderRadius: 7, border: 'none',
              background: tab === t.id ? 'var(--accent-muted)' : 'transparent',
              color: tab === t.id ? 'var(--accent)' : 'var(--text-2)',
              fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
              outline: tab === t.id ? '1px solid rgba(79,142,247,0.3)' : 'none',
              transition: 'all .15s' }}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'matrix' && (
        loadingMatrix ? <Spinner /> : !matrix ? null : matrix.users.length === 0 ? (
          <EmptyState icon="🗂" title="Sin datos de skills" description="Anade skills al perfil de los usuarios para ver la matriz" />
        ) : (
          <Card style={{ padding: 16 }}>
            <div style={{ marginBottom: 12, display: 'flex', gap: 16, flexWrap: 'wrap' }}>
              {Object.entries(LEVEL_CFG).map(([l, cfg]) => (
                <div key={l} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <div style={{ width: 16, height: 16, borderRadius: 4, background: cfg.color + '30', border: `1px solid ${cfg.color}60`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 9, color: cfg.color, fontWeight: 700 }}>{cfg.score}</div>
                  <span style={{ fontSize: 11, color: 'var(--text-2)' }}>{cfg.label}</span>
                </div>
              ))}
            </div>
            <SkillsMatrix users={matrix.users} skills={matrix.skills} />
          </Card>
        )
      )}

      {tab === 'profiles' && (
        <div>
          <div style={{ background: 'var(--accent-muted)', border: '1px solid var(--accent-muted)', borderRadius: 10, padding: '10px 16px', marginBottom: 20, fontSize: 13, color: 'var(--accent)', display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 18 }}>💡</span>
            Haz clic en cualquier persona para ver y editar sus skills
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 14 }}>
            {users.filter(u => u.is_active !== false).map(u => (
              <button key={u.id} type="button"
                onClick={() => setEditingUser(u)}
                style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: 20, cursor: 'pointer', transition: 'all 0.15s', width:'100%', textAlign:'left', fontFamily:'inherit' }}
                onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--accent)'; e.currentTarget.style.background = 'var(--surface-2)' }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--surface-4)'; e.currentTarget.style.background = 'var(--surface-2)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                  <div>
                    <div style={{ fontSize: 15, fontWeight: 700 }}>{u.full_name}</div>
                    <div style={{ fontSize: 12, color: 'var(--text-2)', marginTop: 2 }}>{u.job_title || u.role} · {u.department || '—'}</div>
                  </div>
                  <div style={{ background: 'var(--accent-glow)', border: '1px solid rgba(79,142,247,0.3)', borderRadius: 8, padding: '5px 12px', color: 'var(--accent)', fontSize: 12, fontWeight: 700, flexShrink: 0 }}>
                    ✏️ Gestionar skills
                  </div>
                </div>
                <UserSkillPreview userId={u.id} />
              </button>
            ))}
          </div>
        </div>
      )}

      {tab === 'search' && <StaffingSearch />}

      {tab === 'catalog' && (
        <div>
          <Card style={{ padding: 16, marginBottom: 20 }}>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 14 }}>Añadir nuevo skill al catálogo</div>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-end' }}>
              <input value={newSkill.name} onChange={e => setNewSkill(f => ({ ...f, name: e.target.value }))} style={{ ...inputStyle, flex: 2 }} placeholder="Nombre del skill" />
              <select value={newSkill.category} onChange={e => setNewSkill(f => ({ ...f, category: e.target.value }))} style={{ ...inputStyle, flex: 1 }}>
                {CATEGORIES.map(c => <option key={c} value={c}>{CAT_LABELS[c]}</option>)}
              </select>
              <Button onClick={() => { createSkill(newSkill); setNewSkill({ name: '', category: 'technical', description: '' }) }} disabled={!newSkill.name}>Añadir</Button>
            </div>
          </Card>
          {loadingCatalog ? <Spinner /> : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {CATEGORIES.filter(cat => catalog.some(s => s.category === cat)).map(cat => (
                <div key={cat}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>{CAT_LABELS[cat]}</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
                    {catalog.filter(s => s.category === cat).map(s => (
                      <div key={s.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 12px', background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8 }}>
                        <span style={{ fontSize: 13 }}>{s.name}</span>
                        <span style={{ fontSize: 11, color: 'var(--text-2)' }}>{s.user_count} usuarios</span>
                        <button onClick={() => { openConfirmGlobal({ message: '¿Eliminar esta habilidad del catálogo?', onConfirm: () => deleteSkill(s.id), danger: true }) }} style={{ background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer', fontSize: 14, padding: 0 }}>×</button>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {editingUser && <UserSkillModal user={editingUser} onClose={() => setEditingUser(null)} />}
    </div>
  )
}
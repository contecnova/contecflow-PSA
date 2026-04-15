/**
 * GlobalSearchModal — Cmd+K search across all modules
 * Busca en: proyectos, tareas, clientes, tickets, contratos, wiki
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import api from '../../services/api'
import { useAppT } from '../../i18n/AppLangContext'

const ENTITY_CFG = {
  project:  { icon: '⬡', color: 'var(--accent)', label: 'Proyecto',  path: _p => `/projects` },
  task:     { icon: '▦', color: 'var(--success)', label: 'Tarea',     path: _p => `/tasks` },
  client:   { icon: '🏢', color: 'var(--warning)', label: 'Cliente',   path: _p => `/clients` },
  ticket:   { icon: '🎫', color: 'var(--purple)', label: 'Ticket',    path: _p => `/service-desk` },
  contract: { icon: '📄', color: 'var(--warning)', label: 'Contrato',  path: _p => `/contracts` },
  wiki:     { icon: '📚', color: 'var(--accent)', label: 'Wiki',      path: _p => `/wiki` },
}

export default function GlobalSearchModal({ open, onClose }) {
  const t = useAppT()
  const [q, setQ] = useState('')
  const [selected, setSelected] = useState(0)
  const inputRef = useRef(null)
  const navigate = useNavigate()

  useEffect(() => {
    if (open) { setQ(''); setSelected(0); setTimeout(() => inputRef.current?.focus(), 50) }
  }, [open])

  useEffect(() => {
    const handler = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') { e.preventDefault(); open ? onClose() : null }
      if (!open) return
      if (e.key === 'Escape') onClose()
      if (e.key === 'ArrowDown') setSelected(s => s + 1)
      if (e.key === 'ArrowUp')   setSelected(s => Math.max(0, s - 1))
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onClose])

  const { data: results = [], isFetching } = useQuery({
    queryKey: ['global-search', q],
    queryFn: async () => {
      if (q.trim().length < 2) return []
      const [projects, tasks, clients, tickets] = await Promise.allSettled([
        api.get('/projects', { params: { search: q, limit: 5 } }).then(r =>
          (r.data?.items || r.data || []).slice(0,4).map(p => ({
            id: p.id, type: 'project', title: p.name, subtitle: p.code, status: p.status
          }))),
        api.get('/tasks', { params: { search: q, limit: 5 } }).then(r =>
          (r.data?.items || r.data || []).slice(0,4).map(t => ({
            id: t.id, type: 'task', title: t.title, subtitle: t.project_name, status: t.status
          }))),
        api.get('/clients', { params: { q, limit: 5 } }).then(r =>
          (r.data || []).slice(0,4).map(c => ({
            id: c.id, type: 'client', title: c.name, subtitle: c.industry, status: c.status
          }))),
        api.get('/sd/tickets', { params: { search: q, limit: 5 } }).then(r =>
          (r.data?.items || r.data || []).slice(0,4).map(t => ({
            id: t.id, type: 'ticket', title: t.title, subtitle: t.ticket_type, status: t.status
          }))),
      ])
      return [
        ...(projects.status === 'fulfilled' ? projects.value : []),
        ...(tasks.status    === 'fulfilled' ? tasks.value    : []),
        ...(clients.status  === 'fulfilled' ? clients.value  : []),
        ...(tickets.status  === 'fulfilled' ? tickets.value  : []),
      ]
    },
    enabled: q.trim().length >= 2,
    staleTime: 10000,
  })

  const clampedSelected = Math.min(selected, Math.max(0, results.length - 1))

  const go = useCallback((item) => {
    if (!item) return
    const cfg = ENTITY_CFG[item.type]
    navigate(cfg?.path(item) || '/')
    onClose()
  }, [navigate, onClose])

  useEffect(() => {
    const handler = (e) => {
      if (e.key === 'Enter' && open && results[clampedSelected]) {
        go(results[clampedSelected])
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, results, clampedSelected, go])

  if (!open) return null

  const QUICK_ACTIONS = [
    { icon: '⬡', label: t('global_search.quick_projects'), path: '/projects' },
    { icon: '▦', label: t('global_search.quick_my_tasks'), path: '/tasks' },
    { icon: '🏢', label: t('global_search.quick_clients'), path: '/clients' },
    { icon: '🎫', label: t('global_search.quick_service_desk'), path: '/service-desk' },
    { icon: '📊', label: t('global_search.quick_reports'), path: '/reports' },
    { icon: '📚', label: t('global_search.quick_wiki'), path: '/wiki' },
  ]

  return (
    <div onClick={onClose} style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)',
      display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
      paddingTop: '12vh', zIndex: 99998, backdropFilter: 'blur(4px)',
    }}>
      <div onClick={e => e.stopPropagation()} style={{
        background: 'var(--surface-1)', border: '1px solid #1e2d45',
        borderRadius: 16, width: '100%', maxWidth: 600,
        boxShadow: '0 24px 64px rgba(0,0,0,0.8)',
        overflow: 'hidden',
      }}>
        {/* Input */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '16px 20px', borderBottom: '1px solid #1e2d45' }}>
          <span style={{ fontSize: 18, color: 'var(--text-2)' }}>{isFetching ? '⟳' : '🔍'}</span>
          <input
            ref={inputRef}
            value={q}
            onChange={e => { setQ(e.target.value); setSelected(0) }}
            placeholder={t('global_search.placeholder_modal')}
            style={{
              flex: 1, background: 'none', border: 'none', outline: 'none',
              fontSize: 16, color: 'var(--text-1)', fontFamily: 'inherit',
            }}
          />
          <kbd style={{ fontSize: 11, color: 'var(--text-2)', background: 'var(--surface-4)', borderRadius: 4, padding: '2px 6px' }}>ESC</kbd>
        </div>

        {/* Results */}
        <div style={{ maxHeight: 400, overflowY: 'auto' }}>
          {q.trim().length < 2 ? (
            <div style={{ padding: '12px 8px' }}>
              <div style={{ fontSize: 11, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.08em', padding: '4px 12px', marginBottom: 6 }}>
                {t('global_search.quick_access')}
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4, padding: '0 8px' }}>
                {QUICK_ACTIONS.map(a => (
                  <button key={a.path} onClick={() => { navigate(a.path); onClose() }}
                    style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '10px 12px', borderRadius: 8,
                      border: 'none', background: 'transparent', color: 'var(--text-1)', cursor: 'pointer',
                      fontSize: 13, fontFamily: 'inherit', textAlign: 'left',
                      transition: 'background 0.1s',
                    }}
                    onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-4)'}
                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                  >
                    <span style={{ fontSize: 16 }}>{a.icon}</span>
                    {a.label}
                  </button>
                ))}
              </div>
            </div>
          ) : results.length === 0 && !isFetching ? (
            <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-2)', fontSize: 13 }}>
              {t('global_search.no_results_for')} &quot;{q}&quot;
            </div>
          ) : (
            <div style={{ padding: '8px 8px' }}>
              {results.map((r, i) => {
                const cfg = ENTITY_CFG[r.type] || {}
                const isSelected = i === clampedSelected
                return (
                  <div key={r.id} onClick={() => go(r)}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 12, padding: '10px 12px',
                      borderRadius: 8, cursor: 'pointer', marginBottom: 2,
                      background: isSelected ? 'var(--surface-4)' : 'transparent',
                      transition: 'background 0.1s',
                    }}
                    onMouseEnter={() => setSelected(i)}
                  >
                    <div style={{
                      width: 34, height: 34, borderRadius: 8, flexShrink: 0,
                      background: (cfg.color || 'var(--text-2)') + '15',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: 16,
                    }}>{cfg.icon}</div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-1)',
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {r.title}
                      </div>
                      <div style={{ fontSize: 11, color: 'var(--text-2)' }}>
                        {cfg.label}{r.subtitle ? ` · ${r.subtitle}` : ''}
                      </div>
                    </div>
                    {r.status && (
                      <span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 20,
                        background: 'var(--surface-4)', color: 'var(--text-2)', whiteSpace: 'nowrap' }}>
                        {r.status}
                      </span>
                    )}
                    <kbd style={{ fontSize: 10, color: 'var(--text-3)', background: 'var(--surface-4)',
                      borderRadius: 4, padding: '2px 6px', opacity: isSelected ? 1 : 0 }}>↵</kbd>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{ padding: '10px 20px', borderTop: '1px solid #1e2d45', display: 'flex', gap: 16, alignItems: 'center' }}>
          {[['↑↓', 'navegar'], ['↵', 'abrir'], ['esc', 'cerrar']].map(([key]) => (
            <span key={key} style={{ fontSize: 11, color: 'var(--text-2)', display: 'flex', gap: 4, alignItems: 'center' }}>
              <kbd style={{ background: 'var(--surface-4)', borderRadius: 4, padding: '1px 5px', fontSize: 10 }}>{key}</kbd>
              {key === '↑↓' ? t('common.navigate') : key === '↵' ? t('common.open') : t('common.close').toLowerCase()}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}

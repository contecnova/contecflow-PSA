/**
 * Aprobar o rechazar desde el enlace del correo, sin entrar (revisión 2026-11).
 *
 * Abrir el enlace solo enseña el resumen: decidir es pulsar un botón (POST),
 * porque los gestores de correo abren los enlaces solos para analizarlos.
 */
import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { useSearchParams } from 'react-router-dom'
import api from '../services/api'

interface Resumen { request_id: string; entity_type: string; summary?: string | null; step: number; approver: string }

const caja: CSSProperties = { maxWidth: 460, margin: '10vh auto', padding: 28, borderRadius: 14,
  background: 'var(--surface-1)', border: '1px solid var(--surface-4)', color: 'var(--text-1)', fontFamily: 'inherit' }
const boton = (fondo: string): CSSProperties => ({ flex: 1, padding: '10px 14px', borderRadius: 10, border: 'none',
  background: fondo, color: 'var(--on-accent-light)', fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit' })

function mensajeDe(e: unknown): string {
  const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof d === 'string' ? d : 'No se pudo completar'
}

export default function AprobacionPorCorreoPage() {
  const [params] = useSearchParams()
  const token = params.get('token') || ''
  const [resumen, setResumen] = useState<Resumen | null>(null)
  const [error, setError] = useState('')
  const [nota, setNota] = useState('')
  const [hecho, setHecho] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)

  useEffect(() => {
    if (!token) { setError('El enlace no es válido: le falta el token'); return }
    api.get('/approvals/email-decision', { params: { token } })
      .then(r => setResumen(r.data as Resumen))
      .catch(e => setError(mensajeDe(e)))
  }, [token])

  async function decidir(decision: 'approved' | 'rejected') {
    if (decision === 'rejected' && !nota.trim()) { setError('Para rechazar indica el motivo'); return }
    setEnviando(true); setError('')
    try {
      await api.post('/approvals/email-decision', { token, decision, note: nota.trim() || null })
      setHecho(decision === 'approved' ? 'Aprobada. Gracias.' : 'Rechazada. Se ha avisado a quien la pidió.')
    } catch (e) { setError(mensajeDe(e)) } finally { setEnviando(false) }
  }

  return (
    <main style={caja}>
      <h1 style={{ fontSize: 'var(--text-lg)', margin: '0 0 12px' }}>Aprobación</h1>
      {hecho ? <p role="status">{hecho}</p> : resumen ? (
        <>
          <p style={{ margin: '0 0 6px' }}><strong>{resumen.summary || resumen.entity_type}</strong></p>
          <p style={{ margin: '0 0 16px', color: 'var(--text-2)', fontSize: 'var(--text-sm)' }}>
            Paso {resumen.step} · decides como {resumen.approver}
          </p>
          <label htmlFor="nota" className="u-text2-sm">Nota (obligatoria para rechazar)</label>
          <textarea id="nota" rows={3} value={nota} onChange={e => setNota(e.target.value)}
            style={{ width: '100%', boxSizing: 'border-box', margin: '6px 0 16px', padding: 10, borderRadius: 8,
              background: 'var(--surface-2)', color: 'var(--text-1)', border: '1px solid var(--surface-4)', fontFamily: 'inherit' }} />
          <div style={{ display: 'flex', gap: 10 }}>
            <button type="button" disabled={enviando} onClick={() => { void decidir('approved') }} style={boton('var(--success)')}>Aprobar</button>
            <button type="button" disabled={enviando} onClick={() => { void decidir('rejected') }} style={boton('var(--danger)')}>Rechazar</button>
          </div>
        </>
      ) : !error && <p>Cargando…</p>}
      {error && <p role="alert" style={{ color: 'var(--danger)', marginTop: 12 }}>{error}</p>}
    </main>
  )
}

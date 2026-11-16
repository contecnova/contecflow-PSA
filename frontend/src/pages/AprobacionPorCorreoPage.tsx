/**
 * Aprobar o rechazar desde el enlace del correo, sin entrar (revisión 2026-11).
 *
 * Abrir el enlace solo enseña el resumen: decidir es pulsar un botón (POST),
 * porque los gestores de correo abren los enlaces solos para analizarlos.
 */
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import api from '../services/api'
import { useAppT } from '../i18n/AppLangContext'
import { Button } from '../components/ui'
import { Check, X } from 'lucide-react'
import './AprobacionPorCorreoPage.css'

interface Resumen { request_id: string; entity_type: string; summary?: string | null; step: number; approver: string }

function mensajeDe(e: unknown, porDefecto: string): string {
  const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof d === 'string' ? d : porDefecto
}

export default function AprobacionPorCorreoPage() {
  const t = useAppT()
  const [params] = useSearchParams()
  const token = params.get('token') || ''
  const [resumen, setResumen] = useState<Resumen | null>(null)
  const [error, setError] = useState('')
  const [nota, setNota] = useState('')
  const [hecho, setHecho] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)

  useEffect(() => {
    if (!token) { setError(t('aprob_correo.sin_token')); return }
    api.get('/approvals/email-decision', { params: { token } })
      .then(r => setResumen(r.data as Resumen))
      .catch(e => setError(mensajeDe(e, t('aprob_correo.error'))))
  }, [token, t])

  async function decidir(decision: 'approved' | 'rejected') {
    if (decision === 'rejected' && !nota.trim()) { setError(t('aprob_correo.falta_motivo')); return }
    setEnviando(true); setError('')
    try {
      await api.post('/approvals/email-decision', { token, decision, note: nota.trim() || null })
      setHecho(decision === 'approved' ? t('aprob_correo.aprobada') : t('aprob_correo.rechazada'))
    } catch (e) { setError(mensajeDe(e, t('aprob_correo.error'))) } finally { setEnviando(false) }
  }

  return (
    <main className="apc-box">
      <h1 className="apc-title">{t('aprob_correo.titulo')}</h1>
      {hecho ? <p role="status">{hecho}</p> : resumen ? (
        <>
          <p className="apc-summary"><strong>{resumen.summary || t(`approvals.entity_${resumen.entity_type}`, resumen.entity_type)}</strong></p>
          <p className="apc-step">
            {t('aprob_correo.paso', { step: resumen.step, approver: resumen.approver })}
          </p>
          <label htmlFor="nota" id="nota-etiqueta" className="u-text2-sm">{t('aprob_correo.nota')}</label>
          <textarea id="nota" aria-labelledby="nota-etiqueta" rows={3} value={nota} onChange={e => setNota(e.target.value)}
            className="apc-note" />
          <div className="u-row-10">
            <Button icon={<Check size={14} />} disabled={enviando} onClick={() => { void decidir('approved') }}>{t('aprob_correo.aprobar')}</Button>
            <Button variant="secondary" icon={<X size={14} />} disabled={enviando} onClick={() => { void decidir('rejected') }}>{t('aprob_correo.rechazar')}</Button>
          </div>
        </>
      ) : !error && <p role="status">{t('aprob_correo.cargando')}</p>}
      {error && <p role="alert" className="apc-error">{error}</p>}
    </main>
  )
}

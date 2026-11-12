/**
 * Detalle de un gasto (revisión 2026-11): justificantes y documentos (varios),
 * reparto entre proyectos y lo que dicen las políticas de gasto antes de
 * enviarlo. El dueño lo cambia mientras está en borrador; quien gestiona
 * gastos (`EXPENSE_MANAGER_ROLES`), siempre.
 */
import { useEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { FileText, Plus, ShieldAlert, ShieldCheck, Trash2, Upload } from 'lucide-react'
import { gastosApi, projectsApi } from '../../services/api'
import { Button, Modal, Spinner } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr, localeActivo } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'

type GastoMin = { id: string; code?: string; description?: string; amount?: number | string; currency?: string; status?: string; km?: number | null
  policy_flags?: { mensaje: string }[] }

const titulo: CSSProperties = { fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.04em', color: 'var(--text-2)', margin: '0 0 8px', display: 'flex', alignItems: 'center', gap: 6 }
const campo: CSSProperties = { background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 10px', color: 'var(--text-1)', fontSize: 'var(--text-sm)', fontFamily: 'inherit' }

export default function DetalleDeGasto({ gasto, editable, onClose }: { gasto: GastoMin; editable: boolean; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const fichero = useRef<HTMLInputElement>(null)
  const [subiendo, setSubiendo] = useState(false)
  const [partes, setPartes] = useState<{ project_id: string; percentage: string }[]>([])
  const [guardando, setGuardando] = useState(false)
  const adj = useQuery({ queryKey: ['gasto', gasto.id, 'justificantes'], queryFn: () => gastosApi.justificantes(gasto.id) })
  const rep = useQuery({ queryKey: ['gasto', gasto.id, 'reparto'], queryFn: () => gastosApi.reparto(gasto.id) })
  const pol = useQuery({ queryKey: ['gasto', gasto.id, 'politicas'], queryFn: () => gastosApi.comprobar(gasto.id) })
  const proyectos = useQuery({ queryKey: ['projects'], queryFn: () => projectsApi.list().then(r => r.data as unknown as { id: string; code?: string; name?: string }[]) })
  useEffect(() => {
    if (rep.data) setPartes(rep.data.items.map(p => ({ project_id: p.project_id, percentage: String(p.percentage) })))
  }, [rep.data])
  const refrescar = () => {
    qc.invalidateQueries({ queryKey: ['gasto', gasto.id] })
    qc.invalidateQueries({ queryKey: ['expenses-my'] })
  }
  const fallo = (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))

  const subir = async (f: File) => {
    setSubiendo(true)
    try { await gastosApi.subir(gasto.id, f); refrescar() } catch (e) { fallo(e) } finally { setSubiendo(false) }
  }
  const abrir = async (aid: string) => {
    try { const { url } = await gastosApi.urlJustificante(aid); window.open(url, '_blank', 'noopener') } catch (e) { fallo(e) }
  }
  const quitar = async (aid: string) => { try { await gastosApi.quitarJustificante(aid); refrescar() } catch (e) { fallo(e) } }
  const suma = partes.reduce((s, p) => s + (Number(p.percentage) || 0), 0)
  const guardarReparto = async () => {
    setGuardando(true)
    try {
      await gastosApi.repartir(gasto.id, partes.filter(p => p.project_id).map(p => ({ project_id: p.project_id, percentage: Number(p.percentage) })))
      toast.success(t('gas.reparto_guardado')); refrescar()
    } catch (e) { fallo(e) } finally { setGuardando(false) }
  }
  const importe = Number(gasto.amount) || 0
  const dinero = (n: number) => n.toLocaleString(localeActivo(), { style: 'currency', currency: gasto.currency || 'EUR' })

  return (
    <Modal open onClose={onClose} size="lg" title={`${gasto.code ?? ''} — ${gasto.description ?? ''}`} subtitle={`${dinero(importe)}${gasto.km ? ` · ${gasto.km} km` : ''}`}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        <section aria-label={t('gas.politicas')}>
          <h4 style={titulo}>{pol.data?.incumplimientos.length ? <ShieldAlert size={14} color="var(--warning)" /> : <ShieldCheck size={14} color="var(--success)" />}{t('gas.politicas')}</h4>
          {pol.isLoading ? <Spinner size={16} /> : (pol.data?.incumplimientos ?? []).length === 0
            ? <div style={{ fontSize: 'var(--text-sm)', color: 'var(--success)' }}>{t('gas.cumple')}</div>
            : pol.data!.incumplimientos.map((i, k) => (
              <div key={k} role="alert" style={{ fontSize: 'var(--text-sm)', color: i.accion === 'bloquear' ? 'var(--danger)' : 'var(--warning)', marginBottom: 4 }}>
                <strong>{t(`gas.accion_${i.accion}`)}:</strong> {i.mensaje}
              </div>
            ))}
          {gasto.status !== 'draft' && (gasto.policy_flags ?? []).length > 0 && (
            <div className="u-hint">{t('gas.enviado_con_avisos', { n: gasto.policy_flags!.length })}</div>
          )}
        </section>

        <section aria-label={t('gas.justificantes')}>
          <h4 style={titulo}><FileText size={14} />{t('gas.justificantes')}
            {editable && (
              <>
                <input ref={fichero} type="file" hidden aria-label={t('gas.adjuntar')} accept="image/*,application/pdf"
                  onChange={e => { const f = e.target.files?.[0]; if (f) subir(f); e.target.value = '' }} />
                <Button size="xs" variant="secondary" icon={<Upload size={12} />} loading={subiendo} style={{ marginLeft: 'auto' }} onClick={() => fichero.current?.click()}>{t('gas.adjuntar')}</Button>
              </>
            )}
          </h4>
          {adj.isLoading ? <Spinner size={16} /> : (adj.data?.items ?? []).length === 0
            ? <div className="u-text3-sm">{t('gas.sin_justificantes')}</div>
            : adj.data!.items.map(a => (
              <div key={a.id} style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '6px 0', borderTop: '1px solid var(--surface-3)' }}>
                <button type="button" onClick={() => abrir(a.id)} style={{ flex: 1, textAlign: 'left', background: 'none', border: 'none', padding: 0, cursor: 'pointer', color: 'var(--accent)', fontSize: 'var(--text-sm)' }}>{a.filename}</button>
                <span className="u-text3-xs">{a.size_bytes ? `${Math.max(1, Math.round(a.size_bytes / 1024))} KB` : ''}</span>
                {editable && <Button size="xs" variant="ghost" title={t('gas.quitar')} icon={<Trash2 size={12} />} onClick={() => quitar(a.id)}>{''}</Button>}
              </div>
            ))}
        </section>

        <section aria-label={t('gas.reparto')}>
          <h4 style={titulo}>{t('gas.reparto')}</h4>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginBottom: 8 }}>{t('gas.reparto_ayuda')}</div>
          {partes.map((p, i) => (
            <div key={i} style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 90px 110px 32px', gap: 6, alignItems: 'center', marginBottom: 6 }}>
              <select aria-label={t('gas.proyecto')} disabled={!editable} value={p.project_id} onChange={e => setPartes(v => v.map((x, j) => j === i ? { ...x, project_id: e.target.value } : x))} style={campo}>
                <option value="">{t('gas.elige_proyecto')}</option>
                {(proyectos.data ?? []).map(pr => <option key={pr.id} value={pr.id}>{pr.code ? `${pr.code} — ` : ''}{pr.name}</option>)}
              </select>
              <input aria-label={t('gas.porcentaje')} type="number" min={0} max={100} step="0.01" disabled={!editable} value={p.percentage}
                onChange={e => setPartes(v => v.map((x, j) => j === i ? { ...x, percentage: e.target.value } : x))} style={campo} />
              <span style={{ fontSize: 'var(--text-sm)', fontFamily: 'var(--font-mono)', textAlign: 'right' }}>{dinero(importe * (Number(p.percentage) || 0) / 100)}</span>
              {editable && <Button size="xs" variant="ghost" title={t('gas.quitar')} icon={<Trash2 size={12} />} onClick={() => setPartes(v => v.filter((_, j) => j !== i))}>{''}</Button>}
            </div>
          ))}
          {editable && (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 6 }}>
              <Button size="xs" variant="secondary" icon={<Plus size={12} />} onClick={() => setPartes(v => [...v, { project_id: '', percentage: String(Math.max(0, 100 - suma)) }])}>{t('gas.anadir_proyecto')}</Button>
              <span style={{ fontSize: 'var(--text-xs)', color: partes.length && Math.abs(suma - 100) > 0.01 ? 'var(--danger)' : 'var(--text-3)' }}>
                {partes.length ? t('gas.suma', { n: suma.toLocaleString(localeActivo(), { maximumFractionDigits: 2 }) }) : t('gas.sin_reparto')}
              </span>
              <Button size="xs" style={{ marginLeft: 'auto' }} loading={guardando} disabled={partes.length > 0 && Math.abs(suma - 100) > 0.01} onClick={guardarReparto}>{t('gas.guardar_reparto')}</Button>
            </div>
          )}
        </section>
      </div>
    </Modal>
  )
}

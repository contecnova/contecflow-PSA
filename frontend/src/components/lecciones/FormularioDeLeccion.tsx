/**
 * Alta o edición de una lección aprendida (revisión 2026-11).
 *
 * Con origen (proyecto, ticket, problema…) se piden al servidor los HECHOS
 * medidos y una propuesta (de la IA si está activada); aquí se enseñan los
 * hechos al lado y la persona corrige la propuesta antes de guardarla.
 */
import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Sparkles } from 'lucide-react'
import { leccionesApi } from '../../services/api'
import type { Hecho, Leccion } from '../../services/api'
import { Button, Modal, Spinner } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'

type Form = { titulo: string; tipo: string; categoria: string; severidad: string; que_paso: string; causa: string
  impacto: string; recomendacion: string; etiquetas: string }
const VACIO: Form = { titulo: '', tipo: 'evitar', categoria: '', severidad: 'media', que_paso: '', causa: '', impacto: '', recomendacion: '', etiquetas: '' }

const campo: CSSProperties = { width: '100%', boxSizing: 'border-box', background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 10px', color: 'var(--text-1)', fontSize: 'var(--text-sm)', fontFamily: 'inherit' }
const etiqueta: CSSProperties = { fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginBottom: 4, display: 'block' }

export function valorDeHecho(v: Hecho['valor']): string {
  if (Array.isArray(v)) return v.join(' · ')
  if (typeof v === 'boolean') return v ? '✓' : '—'
  return String(v)
}

export function TablaDeHechos({ hechos }: { hechos: Hecho[] }) {
  const t = useAppT()
  if (!hechos.length) return <div className="u-text3-sm">{t('lec.sin_hechos')}</div>
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-sm)' }}>
      <tbody>{hechos.map(h => (
        <tr key={h.etiqueta} style={{ borderTop: '1px solid var(--surface-3)' }}>
          <td style={{ padding: '5px 8px 5px 0', color: 'var(--text-3)', verticalAlign: 'top', whiteSpace: 'nowrap' }}>{h.etiqueta}</td>
          <td style={{ padding: '5px 0', color: 'var(--text-1)' }}>{valorDeHecho(h.valor)}</td>
        </tr>))}
      </tbody>
    </table>
  )
}

export default function FormularioDeLeccion({ origen, leccion, onClose, onGuardada }: {
  origen?: { tipo: string; id: string } | null; leccion?: Leccion | null; onClose: () => void; onGuardada: (l: Leccion) => void
}) {
  const t = useAppT()
  const toast = useToast()
  const [form, setForm] = useState<Form>(VACIO)
  const [guardando, setGuardando] = useState(false)
  const cfg = useQuery({ queryKey: ['lecciones', 'config'], queryFn: leccionesApi.config, staleTime: 300_000 })
  const borrador = useQuery({
    queryKey: ['lecciones', 'borrador', origen?.tipo, origen?.id], queryFn: () => leccionesApi.borrador(origen!.tipo, origen!.id),
    enabled: !!origen && !leccion, retry: false, staleTime: Infinity,
  })

  useEffect(() => {
    const p = leccion ?? borrador.data?.propuesta
    if (!p) return
    setForm({ titulo: p.titulo ?? '', tipo: p.tipo ?? 'evitar', categoria: p.categoria ?? '', severidad: p.severidad ?? 'media',
      que_paso: p.que_paso ?? '', causa: p.causa ?? '', impacto: p.impacto ?? '', recomendacion: p.recomendacion ?? '', etiquetas: p.etiquetas ?? '' })
  }, [leccion, borrador.data])
  useEffect(() => {
    if (!form.categoria && cfg.data?.categorias?.length) setForm(f => ({ ...f, categoria: cfg.data!.categorias[0] }))
  }, [cfg.data, form.categoria])

  const guardar = async (enviar: boolean) => {
    setGuardando(true)
    try {
      const cuerpo = { ...form, enviar_a_revision: enviar }
      const l = leccion
        ? await leccionesApi.editar(leccion.id, cuerpo)
        : await leccionesApi.crear({ ...cuerpo, origen_tipo: origen?.tipo ?? 'manual', origen_id: origen?.id })
      toast.success(t(leccion ? 'lec.guardada' : 'lec.creada', { codigo: l.codigo }))
      onGuardada(l)
    } catch (e) {
      toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
    } finally {
      setGuardando(false)
    }
  }
  const set = (k: keyof Form) => (e: { target: { value: string } }) => setForm(f => ({ ...f, [k]: e.target.value }))
  const hechos = leccion?.hechos ?? borrador.data?.hechos ?? []
  const listo = form.titulo.trim() && form.que_paso.trim() && form.recomendacion.trim() && form.categoria

  return (
    <Modal open onClose={onClose} size="xl" title={leccion ? `${leccion.codigo} — ${t('lec.editar')}` : t('lec.nueva')}
      subtitle={origen ? (borrador.data?.origen_ref ?? '…') : leccion?.origen_ref ?? undefined}>
      {origen && borrador.isLoading ? <Spinner /> : borrador.isError ? (
        <div role="alert" style={{ color: 'var(--danger)', fontSize: 'var(--text-sm)' }}>{extractErr(borrador.error, GENERIC_ERROR_FALLBACK)}</div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: hechos.length ? 'minmax(0, 1fr) 320px' : '1fr', gap: 20 }}>
          <div className="u-stack-12">
            {borrador.data && (
              <div style={{ fontSize: 'var(--text-xs)', color: borrador.data.ia ? 'var(--accent)' : 'var(--text-3)', display: 'flex', gap: 6, alignItems: 'center' }}>
                <Sparkles size={13} />{borrador.data.ia ? t('lec.propuesta_ia') : (borrador.data.aviso || t('lec.propuesta_hechos'))}
              </div>
            )}
            <label><span style={etiqueta}>{t('lec.titulo')}</span><input aria-label={t('lec.titulo')} value={form.titulo} onChange={set('titulo')} style={campo} maxLength={300} /></label>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
              <label><span style={etiqueta}>{t('lec.tipo')}</span>
                <select aria-label={t('lec.tipo')} value={form.tipo} onChange={set('tipo')} style={campo}>
                  <option value="evitar">{t('lec.tipo_evitar')}</option><option value="repetir">{t('lec.tipo_repetir')}</option>
                </select></label>
              <label><span style={etiqueta}>{t('lec.categoria')}</span>
                <select aria-label={t('lec.categoria')} value={form.categoria} onChange={set('categoria')} style={campo}>
                  {(cfg.data?.categorias ?? []).map(c => <option key={c} value={c}>{t(`lec.cat_${c}`, c)}</option>)}
                </select></label>
              <label><span style={etiqueta}>{t('lec.severidad')}</span>
                <select aria-label={t('lec.severidad')} value={form.severidad} onChange={set('severidad')} style={campo}>
                  {['baja', 'media', 'alta'].map(s => <option key={s} value={s}>{t(`lec.sev_${s}`)}</option>)}
                </select></label>
            </div>
            <label><span style={etiqueta}>{t('lec.que_paso')}</span><textarea rows={4} aria-label={t('lec.que_paso')} value={form.que_paso} onChange={set('que_paso')} style={campo} /></label>
            <label><span style={etiqueta}>{t('lec.causa')}</span><textarea rows={2} aria-label={t('lec.causa')} value={form.causa} onChange={set('causa')} style={campo} /></label>
            <label><span style={etiqueta}>{t('lec.impacto')}</span><textarea rows={2} aria-label={t('lec.impacto')} value={form.impacto} onChange={set('impacto')} style={campo} /></label>
            <label><span style={etiqueta}>{t('lec.recomendacion')}</span><textarea rows={3} aria-label={t('lec.recomendacion')} value={form.recomendacion} onChange={set('recomendacion')} style={campo} placeholder={t('lec.recomendacion_ayuda')} /></label>
            <label><span style={etiqueta}>{t('lec.etiquetas')}</span><input aria-label={t('lec.etiquetas')} value={form.etiquetas} onChange={set('etiquetas')} style={campo} placeholder="erp, migracion" /></label>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', borderTop: '1px solid var(--surface-3)', paddingTop: 12 }}>
              <Button variant="secondary" onClick={onClose}>{t('lec.cancelar')}</Button>
              <Button variant="secondary" disabled={!listo} loading={guardando} onClick={() => guardar(false)}>{t('lec.guardar_borrador')}</Button>
              {(!leccion || leccion.estado === 'borrador') && <Button disabled={!listo} loading={guardando} onClick={() => guardar(true)}>{t('lec.enviar_revision')}</Button>}
            </div>
          </div>
          {hechos.length > 0 && (
            <aside aria-label={t('lec.hechos')} style={{ borderLeft: '1px solid var(--surface-3)', paddingLeft: 16 }}>
              <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.04em', color: 'var(--text-2)', marginBottom: 8 }}>{t('lec.hechos')}</div>
              <TablaDeHechos hechos={hechos} />
            </aside>
          )}
        </div>
      )}
    </Modal>
  )
}

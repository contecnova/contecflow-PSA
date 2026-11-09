/**
 * Campañas y plantillas de presupuestos (revisión 2026-11).
 *
 * Campaña: el ejercicio que se presupuesta, con su fecha límite de envío; la
 * lista enseña cuántos presupuestos hay en cada estado y los días que quedan.
 * A los responsables de los que siguen sin enviar se les avisa cuando falta
 * `BUDGET_CAMPAIGN_REMINDER_DAYS` o menos.
 *
 * Plantilla: partidas para empezar un presupuesto. Se crea desde un presupuesto
 * («guardar como plantilla») y se usa al dar de alta otro.
 */
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { presupuestosApi } from '../../services/api'
import { Button, EmptyState, Spinner } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { campo } from './FormularioDePartida'

const caja: CSSProperties = { border: '1px solid var(--surface-4)', borderRadius: 10, padding: 12 }
const rejilla: CSSProperties = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(170px, 100%), 1fr))', gap: 10, alignItems: 'end' }
const lbl: CSSProperties = { fontSize: 'var(--text-xs)', color: 'var(--text-3)', display: 'block', marginBottom: 3 }

export function CampanasDePresupuesto() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['presupuestos', 'campanas'], queryFn: () => presupuestosApi.campanas() })
  const anio = new Date().getFullYear() + 1
  const [f, setF] = useState({ nombre: '', year: String(anio), fecha_limite: '', instrucciones: '' })
  const [ocupado, setOcupado] = useState(false)
  const guardar = async (cuerpo: Record<string, unknown>, id?: string) => {
    setOcupado(true)
    try {
      await presupuestosApi.guardarCampana(cuerpo, id)
      qc.invalidateQueries({ queryKey: ['presupuestos', 'campanas'] })
      if (!id) setF({ nombre: '', year: String(anio), fecha_limite: '', instrucciones: '' })
    } catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) } finally { setOcupado(false) }
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginTop: 14 }}>
      <div style={{ ...caja, ...rejilla }}>
        <label><span style={lbl}>{t('pres.campana_nombre')}</span><input aria-label={t('pres.campana_nombre')} value={f.nombre} onChange={e => setF(v => ({ ...v, nombre: e.target.value }))} style={campo} /></label>
        <label><span style={lbl}>{t('pres.ejercicio')}</span><input aria-label={t('pres.ejercicio')} type="number" value={f.year} onChange={e => setF(v => ({ ...v, year: e.target.value }))} style={campo} /></label>
        <label><span style={lbl}>{t('pres.fecha_limite')}</span><input aria-label={t('pres.fecha_limite')} type="date" value={f.fecha_limite} onChange={e => setF(v => ({ ...v, fecha_limite: e.target.value }))} style={campo} /></label>
        <label style={{ gridColumn: '1 / -1' }}><span style={lbl}>{t('pres.instrucciones')}</span>
          <textarea aria-label={t('pres.instrucciones')} rows={2} value={f.instrucciones} onChange={e => setF(v => ({ ...v, instrucciones: e.target.value }))} style={{ ...campo, resize: 'vertical' }} /></label>
        <div><Button loading={ocupado} disabled={!f.nombre.trim() || !f.fecha_limite || !f.year}
          onClick={() => guardar({ nombre: f.nombre, year: Number(f.year), fecha_limite: f.fecha_limite, instrucciones: f.instrucciones || null })}>{t('pres.abrir_campana')}</Button></div>
      </div>
      {q.isLoading ? <Spinner /> : q.isError ? <div role="alert" style={{ color: 'var(--danger)' }}>{extractErr(q.error, GENERIC_ERROR_FALLBACK)}</div>
        : (q.data ?? []).length === 0 ? <EmptyState title={t('pres.sin_campanas')} description={t('pres.campanas_ayuda')} />
        : (q.data ?? []).map(c => (
          <div key={c.id} style={{ ...caja, display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
            <div style={{ flex: '1 1 220px', minWidth: 0 }}>
              <strong>{c.nombre}</strong> · {c.year}
              <div style={{ fontSize: 'var(--text-xs)', color: c.abierta && c.dias_restantes < 0 ? 'var(--danger)' : 'var(--text-3)' }}>
                {t('pres.fecha_limite')}: {c.fecha_limite}{c.abierta ? ` · ${c.dias_restantes >= 0 ? t('pres.quedan_dias', { n: c.dias_restantes }) : t('pres.vencida')}` : ` · ${t('pres.cerrada')}`}
              </div>
              {c.instrucciones && <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-2)', marginTop: 4 }}>{c.instrucciones}</div>}
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', fontSize: 'var(--text-xs)' }}>
              <span>{t('pres.presupuestos')}: <strong>{c.presupuestos}</strong></span>
              {Object.entries(c.por_estado).map(([e, n]) => <span key={e}>{t(`pres.estado_${e}`)}: <strong>{n}</strong></span>)}
            </div>
            <Button size="sm" variant="secondary" loading={ocupado} onClick={() => guardar({ abierta: !c.abierta }, c.id)}>{c.abierta ? t('pres.cerrar_campana') : t('pres.reabrir_campana')}</Button>
          </div>
        ))}
    </div>
  )
}

export function PlantillasDePresupuesto() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['presupuestos', 'plantillas'], queryFn: () => presupuestosApi.plantillas() })
  const lista = useQuery({ queryKey: ['presupuestos', 'años'], queryFn: () => presupuestosApi.listar({}) })
  const [nombre, setNombre] = useState('')
  const [desde, setDesde] = useState('')
  const [ocupado, setOcupado] = useState(false)
  const crear = async () => {
    setOcupado(true)
    try {
      await presupuestosApi.guardarPlantilla({ nombre, desde_presupuesto: desde })
      qc.invalidateQueries({ queryKey: ['presupuestos', 'plantillas'] }); setNombre(''); setDesde('')
    } catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) } finally { setOcupado(false) }
  }
  const borrar = async (id: string) => {
    try { await presupuestosApi.borrarPlantilla(id); qc.invalidateQueries({ queryKey: ['presupuestos', 'plantillas'] }) }
    catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) }
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginTop: 14 }}>
      <div style={{ ...caja, ...rejilla }}>
        <label><span style={lbl}>{t('pres.plantilla_nombre')}</span><input aria-label={t('pres.plantilla_nombre')} value={nombre} onChange={e => setNombre(e.target.value)} style={campo} /></label>
        <label><span style={lbl}>{t('pres.desde_presupuesto')}</span>
          <select aria-label={t('pres.desde_presupuesto')} value={desde} onChange={e => setDesde(e.target.value)} style={campo}>
            <option value="">{t('pres.elige_presupuesto')}</option>
            {(lista.data ?? []).map(b => <option key={b.id} value={b.id}>{b.name} · {b.year} · v{b.version}</option>)}
          </select></label>
        <div><Button loading={ocupado} disabled={!nombre.trim() || !desde} onClick={crear}>{t('pres.guardar_como_plantilla')}</Button></div>
      </div>
      {q.isLoading ? <Spinner /> : (q.data ?? []).length === 0 ? <EmptyState title={t('pres.sin_plantillas')} description={t('pres.plantillas_ayuda')} />
        : (q.data ?? []).map(pl => (
          <div key={pl.id} style={{ ...caja, display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
            <div style={{ flex: '1 1 220px', minWidth: 0 }}>
              <strong>{pl.nombre}</strong>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {pl.partidas.map(x => x.descripcion).filter(Boolean).slice(0, 6).join(' · ')}
              </div>
            </div>
            <span style={{ fontSize: 'var(--text-xs)' }}>{pl.partidas.length} {t('pres.partidas')}</span>
            <Button size="sm" variant="ghost" onClick={() => borrar(pl.id)}>{t('pres.quitar')}</Button>
          </div>
        ))}
    </div>
  )
}

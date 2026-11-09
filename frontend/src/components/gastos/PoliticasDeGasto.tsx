/**
 * Políticas de gasto (revisión 2026-11), para el administrador.
 *
 * Cada política aplica a una categoría o a todas, con una o varias reglas: tope
 * por gasto, tope diario por persona, justificante obligatorio desde un importe
 * y explicación obligatoria desde un importe. «Bloquear» impide enviar el
 * gasto; «Avisar» lo deja enviar marcado, y un flujo de aprobación con la
 * condición «excede una política» puede pedir un paso más.
 */
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2 } from 'lucide-react'
import { gastosApi } from '../../services/api'
import type { PoliticaDeGasto } from '../../services/api'
import { Button, EmptyState, Spinner } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'

const campo: CSSProperties = { width: '100%', boxSizing: 'border-box', background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 10px', color: 'var(--text-1)', fontSize: 'var(--text-sm)', fontFamily: 'inherit' }
const REGLAS = ['limite_por_gasto', 'limite_diario', 'justificante_desde', 'justificacion_desde'] as const
type Borrador = { nombre: string; categoria: string; accion: 'bloquear' | 'avisar' } & Record<(typeof REGLAS)[number], string>
const VACIA: Borrador = { nombre: '', categoria: '', accion: 'bloquear', limite_por_gasto: '', limite_diario: '', justificante_desde: '', justificacion_desde: '' }

export default function PoliticasDeGasto({ categorias }: { categorias: { id: string; label: string }[] }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [nueva, setNueva] = useState<Borrador>(VACIA)
  const q = useQuery({ queryKey: ['gastos', 'politicas'], queryFn: gastosApi.politicas })
  const refrescar = () => qc.invalidateQueries({ queryKey: ['gastos', 'politicas'] })
  const fallo = (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  const num = (v: string) => (v === '' ? null : Number(v))
  const crear = async () => {
    try {
      await gastosApi.crearPolitica({ nombre: nueva.nombre, categoria: nueva.categoria || null, accion: nueva.accion,
        ...Object.fromEntries(REGLAS.map(r => [r, num(nueva[r])])) })
      setNueva(VACIA); refrescar(); toast.success(t('gas.politica_creada'))
    } catch (e) { fallo(e) }
  }
  const cambiar = async (p: PoliticaDeGasto, body: Partial<PoliticaDeGasto>) => { try { await gastosApi.editarPolitica(p.id, body); refrescar() } catch (e) { fallo(e) } }
  const etiquetaCat = (c?: string | null) => (c ? categorias.find(x => x.id === c)?.label ?? c : t('gas.todas_las_categorias'))
  const set = (k: keyof Borrador) => (e: { target: { value: string } }) => setNueva(v => ({ ...v, [k]: e.target.value }))
  const listo = nueva.nombre.trim().length >= 2 && REGLAS.some(r => nueva[r] !== '')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <p style={{ margin: 0, fontSize: 'var(--text-sm)', color: 'var(--text-2)' }}>{t('gas.politicas_ayuda')}</p>
      {q.isLoading ? <Spinner /> : (q.data?.items ?? []).length === 0
        ? <EmptyState icon="🛡️" title={t('gas.sin_politicas')} description="" />
        : (
          <div style={{ border: '1px solid var(--surface-4)', borderRadius: 10, overflow: 'hidden' }}>
            {q.data!.items.map(p => (
              <div key={p.id} style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.2fr) 140px minmax(0, 2fr) 120px 90px 36px', gap: 10, alignItems: 'center', padding: '10px 12px', borderTop: '1px solid var(--surface-3)', fontSize: 'var(--text-sm)', opacity: p.activa ? 1 : 0.55 }}>
                <strong>{p.nombre}</strong>
                <span style={{ color: 'var(--text-2)' }}>{etiquetaCat(p.categoria)}</span>
                <span style={{ color: 'var(--text-2)', fontSize: 'var(--text-xs)' }}>
                  {REGLAS.filter(r => p[r] != null).map(r => t(`gas.regla_${r}`, { n: p[r] as number })).join(' · ')}
                </span>
                <select aria-label={t('gas.accion')} value={p.accion} onChange={e => cambiar(p, { accion: e.target.value as 'bloquear' | 'avisar' })} style={campo}>
                  <option value="bloquear">{t('gas.accion_bloquear')}</option><option value="avisar">{t('gas.accion_avisar')}</option>
                </select>
                <label style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 'var(--text-xs)' }}>
                  <input type="checkbox" aria-label={t('gas.activa')} checked={p.activa} onChange={e => cambiar(p, { activa: e.target.checked })} />{t('gas.activa')}
                </label>
                <Button size="xs" variant="ghost" title={t('gas.quitar')} icon={<Trash2 size={12} />}
                  onClick={() => openConfirmGlobal({ message: t('gas.borrar_politica', { nombre: p.nombre }), danger: true, onConfirm: async () => { try { await gastosApi.borrarPolitica(p.id); refrescar() } catch (e) { fallo(e) } } })}>{''}</Button>
              </div>
            ))}
          </div>
        )}
      <section aria-label={t('gas.nueva_politica')} style={{ border: '1px solid var(--surface-4)', borderRadius: 10, padding: 14, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 10, alignItems: 'end' }}>
        <label><span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{t('gas.nombre')}</span><input aria-label={t('gas.nombre')} value={nueva.nombre} onChange={set('nombre')} style={campo} /></label>
        <label><span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{t('gas.categoria')}</span>
          <select aria-label={t('gas.categoria')} value={nueva.categoria} onChange={set('categoria')} style={campo}>
            <option value="">{t('gas.todas_las_categorias')}</option>
            {categorias.map(c => <option key={c.id} value={c.id}>{c.label}</option>)}
          </select></label>
        {REGLAS.map(r => (
          <label key={r}><span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{t(`gas.campo_${r}`)}</span>
            <input aria-label={t(`gas.campo_${r}`)} type="number" min={0} step="0.01" value={nueva[r]} onChange={set(r)} style={campo} /></label>
        ))}
        <label><span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{t('gas.accion')}</span>
          <select aria-label={t('gas.accion')} value={nueva.accion} onChange={set('accion')} style={campo}>
            <option value="bloquear">{t('gas.accion_bloquear')}</option><option value="avisar">{t('gas.accion_avisar')}</option>
          </select></label>
        <Button icon={<Plus size={13} />} disabled={!listo} onClick={crear}>{t('gas.crear_politica')}</Button>
      </section>
    </div>
  )
}

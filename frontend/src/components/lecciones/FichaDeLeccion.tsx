/**
 * Ficha de una lección aprendida (revisión 2026-11): qué pasó, por qué, qué
 * hacer, los hechos medidos del origen, su estado (revisión y validación), sus
 * acciones de mejora y lo que ha dicho quien la recibió como recomendación.
 */
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { leccionesApi } from '../../services/api'
import type { Leccion } from '../../services/api'
import { Button, Modal, Spinner, UserSelect } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr, fmtDate } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import FormularioDeLeccion, { TablaDeHechos } from './FormularioDeLeccion'

const titulo: CSSProperties = { fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.04em', color: 'var(--text-2)', margin: '0 0 6px' }
const texto: CSSProperties = { fontSize: 'var(--text-sm)', color: 'var(--text-1)', whiteSpace: 'pre-wrap', lineHeight: 1.55, margin: 0 }
const campo: CSSProperties = { background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 10px', color: 'var(--text-1)', fontSize: 'var(--text-sm)', fontFamily: 'inherit' }

export function ColorDeEstado(estado: string): string {
  return estado === 'validada' ? 'var(--success)' : estado === 'en_revision' ? 'var(--warning)' : estado === 'archivada' ? 'var(--text-3)' : 'var(--info)'
}

export default function FichaDeLeccion({ id, onClose }: { id: string; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [editando, setEditando] = useState(false)
  const [accion, setAccion] = useState({ descripcion: '', responsable_id: '', fecha_limite: '' })
  const { data: l, isLoading, isError, error } = useQuery({ queryKey: ['lecciones', 'ficha', id], queryFn: () => leccionesApi.detalle(id) })
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['lecciones'] }) }
  const fallo = (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  const estado = useMutation({ mutationFn: (e: string) => leccionesApi.estado(id, e), onSuccess: refrescar, onError: fallo })
  const girando = (e: string) => estado.isPending && estado.variables === e
  const nuevaAccion = useMutation({
    mutationFn: () => leccionesApi.crearAccion(id, { descripcion: accion.descripcion, responsable_id: accion.responsable_id || null, fecha_limite: accion.fecha_limite || null }),
    onSuccess: () => { setAccion({ descripcion: '', responsable_id: '', fecha_limite: '' }); refrescar() }, onError: fallo,
  })
  const avanzar = useMutation({ mutationFn: ({ aid, e }: { aid: string; e: string }) => leccionesApi.editarAccion(aid, { estado: e }), onSuccess: refrescar, onError: fallo })

  if (editando && l) return <FormularioDeLeccion leccion={l} onClose={() => setEditando(false)} onGuardada={() => { setEditando(false); refrescar() }} />
  return (
    <Modal open onClose={onClose} size="xl" title={l ? `${l.codigo} — ${l.titulo}` : '…'} subtitle={l?.origen_ref ?? undefined}>
      {isLoading ? <Spinner /> : isError ? <div role="alert" style={{ color: 'var(--danger)' }}>{extractErr(error, GENERIC_ERROR_FALLBACK)}</div> : l && (
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 300px', gap: 22 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <span style={{ color: ColorDeEstado(l.estado), border: '1px solid currentColor', borderRadius: 99, padding: '1px 10px', fontSize: 'var(--text-xs)', fontWeight: 600 }}>{t(`lec.estado_${l.estado}`)}</span>
              <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-2)' }}>{t(`lec.tipo_${l.tipo}`)} · {t(`lec.cat_${l.categoria}`, l.categoria)} · {t(`lec.sev_${l.severidad}`)}</span>
              {l.etiquetas && <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>#{l.etiquetas.split(',').map(e => e.trim()).join(' #')}</span>}
            </div>
            <section><h4 style={titulo}>{t('lec.recomendacion')}</h4><p style={{ ...texto, fontWeight: 600 }}>{l.recomendacion}</p></section>
            <section><h4 style={titulo}>{t('lec.que_paso')}</h4><p style={texto}>{l.que_paso}</p></section>
            {l.causa && <section><h4 style={titulo}>{t('lec.causa')}</h4><p style={texto}>{l.causa}</p></section>}
            {l.impacto && <section><h4 style={titulo}>{t('lec.impacto')}</h4><p style={texto}>{l.impacto}</p></section>}

            <section>
              <h4 style={titulo}>{t('lec.acciones')}</h4>
              {(l.acciones ?? []).length === 0 && <p style={{ ...texto, color: 'var(--text-3)' }}>{t('lec.sin_acciones')}</p>}
              {(l.acciones ?? []).map(a => (
                <div key={a.id} style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '6px 0', borderTop: '1px solid var(--surface-3)', fontSize: 'var(--text-sm)' }}>
                  <span style={{ flex: 1, color: a.estado === 'hecha' ? 'var(--text-3)' : 'var(--text-1)', textDecoration: a.estado === 'hecha' ? 'line-through' : undefined }}>{a.descripcion}</span>
                  {a.fecha_limite && <span style={{ fontSize: 'var(--text-xs)', color: a.vencida ? 'var(--danger)' : 'var(--text-3)' }}>{fmtDate(a.fecha_limite)}</span>}
                  <select aria-label={t('lec.estado_accion')} value={a.estado} onChange={e => avanzar.mutate({ aid: a.id, e: e.target.value })} style={campo}>
                    {['abierta', 'en_curso', 'hecha', 'descartada'].map(s => <option key={s} value={s}>{t(`lec.accion_${s}`)}</option>)}
                  </select>
                </div>
              ))}
              {l.puedo_editar && (
                <form onSubmit={e => { e.preventDefault(); if (accion.descripcion.trim().length >= 3) nuevaAccion.mutate() }}
                  style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 200px 150px auto', gap: 6, marginTop: 8 }}>
                  <input aria-label={t('lec.nueva_accion')} placeholder={t('lec.nueva_accion')} value={accion.descripcion} onChange={e => setAccion(v => ({ ...v, descripcion: e.target.value }))} style={campo} />
                  <UserSelect value={accion.responsable_id} onChange={(uid: string) => setAccion(v => ({ ...v, responsable_id: uid }))} placeholder={t('lec.responsable')} />
                  <input type="date" aria-label={t('lec.fecha_limite')} value={accion.fecha_limite} onChange={e => setAccion(v => ({ ...v, fecha_limite: e.target.value }))} style={campo} />
                  <Button size="sm" type="submit" loading={nuevaAccion.isPending}>{t('lec.anadir')}</Button>
                </form>
              )}
            </section>

            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', borderTop: '1px solid var(--surface-3)', paddingTop: 12 }}>
              {l.puedo_editar && <Button variant="secondary" onClick={() => setEditando(true)}>{t('lec.editar')}</Button>}
              {l.estado === 'borrador' && l.puedo_editar && <Button variant="secondary" loading={girando('en_revision')} onClick={() => estado.mutate('en_revision')}>{t('lec.enviar_revision')}</Button>}
              {l.puedo_validar && l.estado !== 'validada' && l.estado !== 'archivada' && <Button loading={girando('validada')} onClick={() => estado.mutate('validada')}>{t('lec.validar')}</Button>}
              {l.puedo_validar && l.estado !== 'archivada' && <Button variant="ghost" loading={girando('archivada')} onClick={() => estado.mutate('archivada')}>{t('lec.archivar')}</Button>}
              {l.puedo_validar && l.estado === 'archivada' && <Button variant="secondary" loading={girando('validada')} onClick={() => estado.mutate('validada')}>{t('lec.reactivar')}</Button>}
            </div>
          </div>

          <aside style={{ borderLeft: '1px solid var(--surface-3)', paddingLeft: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
            <section>
              <h4 style={titulo}>{t('lec.le_sirvio')}</h4>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6, textAlign: 'center' }}>
                {(['util', 'aplicada', 'no_aplica'] as const).map(v => (
                  <div key={v}><div style={{ fontSize: 'var(--text-lg)', fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{l.usos[v]}</div><div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{t(`lec.uso_${v}`)}</div></div>
                ))}
              </div>
            </section>
            <section><h4 style={titulo}>{t('lec.hechos')}</h4><TablaDeHechos hechos={l.hechos ?? []} /></section>
            {l.validada_en && <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{t('lec.validada_el', { fecha: fmtDate(l.validada_en) })}</div>}
          </aside>
        </div>
      )}
    </Modal>
  )
}

export type { Leccion }

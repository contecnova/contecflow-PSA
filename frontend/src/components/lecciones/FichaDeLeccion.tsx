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
import DateInput from '../ui/DateInput'
import './FichaDeLeccion.css'

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
      {isLoading ? <Spinner /> : isError ? <div role="alert" className="u-danger">{extractErr(error, GENERIC_ERROR_FALLBACK)}</div> : l && (
        <div className="fidele-grid-1">
          <div className="u-stack-16">
            <div className="u-wrap-center-8">
              <span className="fidele-box-1 ficha-de-leccion-e1" style={{ '--ficha-de-leccion-color': ColorDeEstado(l.estado) } as CSSProperties}>{t(`lec.estado_${l.estado}`)}</span>
              <span className="u-text2-xs">{t(`lec.tipo_${l.tipo}`)} · {t(`lec.cat_${l.categoria}`, l.categoria)} · {t(`lec.sev_${l.severidad}`)}</span>
              {l.etiquetas && <span className="u-text3-xs">#{l.etiquetas.split(',').map(e => e.trim()).join(' #')}</span>}
            </div>
            <section><h4 className="fidele-titulo">{t('lec.recomendacion')}</h4><p className="fidele-texto2">{l.recomendacion}</p></section>
            <section><h4 className="fidele-titulo">{t('lec.que_paso')}</h4><p className="fidele-texto">{l.que_paso}</p></section>
            {l.causa && <section><h4 className="fidele-titulo">{t('lec.causa')}</h4><p className="fidele-texto">{l.causa}</p></section>}
            {l.impacto && <section><h4 className="fidele-titulo">{t('lec.impacto')}</h4><p className="fidele-texto">{l.impacto}</p></section>}

            <section>
              <h4 className="fidele-titulo">{t('lec.acciones')}</h4>
              {(l.acciones ?? []).length === 0 && <p className="fidele-texto3">{t('lec.sin_acciones')}</p>}
              {(l.acciones ?? []).map(a => (
                <div key={a.id} className="fidele-row-1">
                  <span className={`fidele-box-2 ${a.estado === 'hecha' ? 'ficha-de-leccion-m2' : 'ficha-de-leccion-m3'}`}>{a.descripcion}</span>
                  {a.fecha_limite && <span className={`fidele-txt-2 ${a.vencida ? 'ficha-de-leccion-m4' : 'ficha-de-leccion-m5'}`}>{fmtDate(a.fecha_limite)}</span>}
                  <select aria-label={t('lec.estado_accion')} value={a.estado} onChange={e => avanzar.mutate({ aid: a.id, e: e.target.value })} className="fidele-campo">
                    {['abierta', 'en_curso', 'hecha', 'descartada'].map(s => <option key={s} value={s}>{t(`lec.accion_${s}`)}</option>)}
                  </select>
                </div>
              ))}
              {l.puedo_editar && (
                <form onSubmit={e => { e.preventDefault(); if (accion.descripcion.trim().length >= 3) nuevaAccion.mutate() }}
                  className="fidele-grid-2">
                  <input aria-label={t('lec.nueva_accion')} placeholder={t('lec.nueva_accion')} value={accion.descripcion} onChange={e => setAccion(v => ({ ...v, descripcion: e.target.value }))} className="fidele-campo" />
                  <UserSelect value={accion.responsable_id} onChange={(uid: string) => setAccion(v => ({ ...v, responsable_id: uid }))} placeholder={t('lec.responsable')} />
                  <DateInput aria-label={t('lec.fecha_limite')} value={accion.fecha_limite} onChange={e => setAccion(v => ({ ...v, fecha_limite: e.target.value }))} style={campo} />
                  <Button size="sm" type="submit" loading={nuevaAccion.isPending}>{t('lec.anadir')}</Button>
                </form>
              )}
            </section>

            <div className="fidele-row-2">
              {l.puedo_editar && <Button variant="secondary" onClick={() => setEditando(true)}>{t('lec.editar')}</Button>}
              {l.estado === 'borrador' && l.puedo_editar && <Button variant="secondary" loading={girando('en_revision')} onClick={() => estado.mutate('en_revision')}>{t('lec.enviar_revision')}</Button>}
              {l.puedo_validar && l.estado !== 'validada' && l.estado !== 'archivada' && <Button loading={girando('validada')} onClick={() => estado.mutate('validada')}>{t('lec.validar')}</Button>}
              {l.puedo_validar && l.estado !== 'archivada' && <Button variant="ghost" loading={girando('archivada')} onClick={() => estado.mutate('archivada')}>{t('lec.archivar')}</Button>}
              {l.puedo_validar && l.estado === 'archivada' && <Button variant="secondary" loading={girando('validada')} onClick={() => estado.mutate('validada')}>{t('lec.reactivar')}</Button>}
            </div>
          </div>

          <aside className="fidele-stack-1">
            <section>
              <h4 className="fidele-titulo">{t('lec.le_sirvio')}</h4>
              <div className="fidele-grid-3">
                {(['util', 'aplicada', 'no_aplica'] as const).map(v => (
                  <div key={v}><div className="fidele-txt-1">{l.usos[v]}</div><div className="u-text3-xs">{t(`lec.uso_${v}`)}</div></div>
                ))}
              </div>
            </section>
            <section><h4 className="fidele-titulo">{t('lec.hechos')}</h4><TablaDeHechos hechos={l.hechos ?? []} /></section>
            {l.validada_en && <div className="u-text3-xs">{t('lec.validada_el', { fecha: fmtDate(l.validada_en) })}</div>}
          </aside>
        </div>
      )}
    </Modal>
  )
}

export type { Leccion }

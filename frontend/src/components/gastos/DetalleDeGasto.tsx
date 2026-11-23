/**
 * Detalle de un gasto (revisión 2026-11): justificantes y documentos (varios),
 * reparto entre proyectos y lo que dicen las políticas de gasto. Rev. 166
 * (#27): cada justificante lleva su tipo de documento (`POLICY_DOCUMENT_TYPES`);
 * en borrador se ve qué pasará al enviarlo y, enviado, el «por qué» del motor
 * de políticas (`/policies/explanations/gastos/{id}`). El dueño lo cambia
 * mientras está en borrador; quien gestiona gastos (`EXPENSE_MANAGER_ROLES`), siempre.
 */
import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { FileText, Plus, ShieldAlert, ShieldCheck, Trash2, Upload } from 'lucide-react'
import { gastosApi, politicasApi } from '../../services/api'
import type { Gasto } from '../../services/api/tipos-finanzas'
import ExplicacionDeEntidad from '../politicas/ExplicacionDeEntidad'
import './gastos-politicas.css'
import { Button, Modal, Spinner, Pulsable, Select, Input } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr, localeActivo } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'

import { useFormatoMoneda } from '../../hooks/useFormatoMoneda'
import { useListaDeProyectos } from '../../hooks/useListas'
import { confirmar } from '../../context/ConfirmContext'
/** Lo que la ficha lee del gasto (serialize_expense). */
type GastoMin = Pick<Gasto, 'id' | 'code' | 'description' | 'amount' | 'currency' | 'status' | 'km'>


export default function DetalleDeGasto({ gasto, editable, onClose }: { gasto: GastoMin; editable: boolean; onClose: () => void }) {
  const fmtMoneda = useFormatoMoneda()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const fichero = useRef<HTMLInputElement>(null)
  const [subiendo, setSubiendo] = useState(false)
  const [partes, setPartes] = useState<{ project_id: string; percentage: string }[]>([])
  const [guardando, setGuardando] = useState(false)
  const adj = useQuery({ queryKey: ['gasto', gasto.id, 'justificantes'], queryFn: () => gastosApi.justificantes(gasto.id) })
  const rep = useQuery({ queryKey: ['gasto', gasto.id, 'reparto'], queryFn: () => gastosApi.reparto(gasto.id) })
  const borrador = gasto.status === 'draft'
  const pol = useQuery({ queryKey: ['gasto', gasto.id, 'vista-previa'], queryFn: () => gastosApi.vistaPrevia(gasto.id), enabled: borrador, retry: false })
  const tipos = useQuery({ queryKey: ['politicas', 'tipos-de-documento'], queryFn: politicasApi.tiposDeDocumento })
  const [tipoNuevo, setTipoNuevo] = useState('')
  const doc = (d: string) => t(`pol.doc_${d}`, d)
  const proyectos = useListaDeProyectos()
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
    try { await gastosApi.subir(gasto.id, f, tipoNuevo || null); refrescar() } catch (e) { fallo(e) } finally { setSubiendo(false) }
  }
  const abrir = async (aid: string) => {
    try { const { url } = await gastosApi.urlJustificante(aid); window.open(url, '_blank', 'noopener') } catch (e) { fallo(e) }
  }
  const tipar = async (aid: string, tipo: string) => { try { await gastosApi.tipar(aid, tipo || null); refrescar() } catch (e) { fallo(e) } }
  // 23-11-2026: quitar un justificante pide confirmación.
  const quitar = async (aid: string) => { if (!(await confirmar({ message: t('gas.confirmar_quitar_justificante'), danger: true, confirmLabel: t('gas.quitar') }))) return; try { await gastosApi.quitarJustificante(aid); refrescar() } catch (e) { fallo(e) } }
  const suma = partes.reduce((s, p) => s + (Number(p.percentage) || 0), 0)
  const guardarReparto = async () => {
    setGuardando(true)
    try {
      await gastosApi.repartir(gasto.id, partes.filter(p => p.project_id).map(p => ({ project_id: p.project_id, percentage: Number(p.percentage) })))
      toast.success(t('gas.reparto_guardado')); refrescar()
    } catch (e) { fallo(e) } finally { setGuardando(false) }
  }
  const importe = Number(gasto.amount) || 0
  const dinero = (n: number) => fmtMoneda(n, { moneda: gasto.currency })

  return (
    <Modal open onClose={onClose} size="lg" title={`${gasto.code ?? ''} — ${gasto.description ?? ''}`} subtitle={`${dinero(importe)}${gasto.km ? ` · ${gasto.km} km` : ''}`}>
      <div className="u-stack-20">
        <section className="gp-seccion" aria-label={t('gas.politicas')}>
          <h4 className="gp-titulo">{borrador && pol.data && !pol.data.puede_enviar
            ? <ShieldAlert size={14} aria-hidden /> : <ShieldCheck size={14} aria-hidden />}{t('gas.politicas')}</h4>
          {!borrador ? <ExplicacionDeEntidad dominio="gastos" entidadId={gasto.id} />
            : pol.isLoading ? <Spinner size={16} label={t('gas.comprobando_politicas')} />
            : pol.isError ? <div role="alert" className="gp-error">{extractErr(pol.error, t('gas.error_vista_previa'))}</div>
            : pol.data && (pol.data.bloqueos.length + pol.data.avisos.length + pol.data.requisitos.length + pol.data.niveles + pol.data.aprobacion.pasos_anadidos.length) === 0
              ? <p className="gp-ok">{t('gas.cumple')}</p>
              : (
                <ul className="gp-lista">
                  {pol.data?.bloqueos.map((b, k) => <li key={`b${k}`} data-estado="pendiente">{b.mensaje}</li>)}
                  {pol.data?.requisitos.map((r, k) => (
                    <li key={`r${k}`} data-estado={r.cumplido ? 'cumplido' : 'pendiente'}>
                      {r.mensaje || t(`pol.res_${r.tipo}`)}{r.tipos_de_documento.length > 0 && <span className="gp-ayuda"> · {r.tipos_de_documento.map(doc).join(' / ')}</span>}
                    </li>
                  ))}
                  {(pol.data?.niveles ?? 0) + (pol.data?.aprobacion.pasos_anadidos.length ?? 0) > 0 && (
                    <li data-tono="aviso">{t('gas.mas_aprobacion', { n: (pol.data?.niveles ?? 0) + (pol.data?.aprobacion.pasos_anadidos.length ?? 0) })}</li>
                  )}
                  {pol.data?.avisos.map((a, k) => <li key={`a${k}`} data-tono="aviso">{a.mensaje}</li>)}
                </ul>
              )}
        </section>

        <section aria-label={t('gas.justificantes')}>
          <h4 className="gp-titulo"><FileText size={14} aria-hidden />{t('gas.justificantes')}
            {editable && (
              <>
                <Select suelto placeholder={false} className="gp-campo gp-campo--auto" aria-label={t('gas.tipo_de_documento_nuevo')} value={tipoNuevo}
                  onChange={e => setTipoNuevo(e.target.value)} disabled={tipos.isLoading}>
                  <option value="">{t('gas.sin_tipo')}</option>
                  {(tipos.data?.tipos ?? []).map(d => <option key={d} value={d}>{doc(d)}</option>)}
                </Select>
                <input ref={fichero} type="file" hidden aria-label={t('gas.adjuntar')} accept="image/*,application/pdf"
                  onChange={e => { const f = e.target.files?.[0]; if (f) subir(f); e.target.value = '' }} />
                <span className="gp-empuja"><Button size="xs" variant="secondary" icon={<Upload size={12} />} loading={subiendo} onClick={() => fichero.current?.click()}>{t('gas.adjuntar')}</Button></span>
              </>
            )}
          </h4>
          {adj.isLoading ? <Spinner size={16} /> : (adj.data?.items ?? []).length === 0
            ? <div className="u-text3-sm">{t('gas.sin_justificantes')}</div>
            : adj.data!.items.map(a => (
              <div key={a.id} className="gp-adjunto">
                <Pulsable type="button" className="gp-enlace" onClick={() => abrir(a.id)}>{a.filename}</Pulsable>
                {editable ? (
                  <Select suelto placeholder={false} className="gp-campo" aria-label={t('gas.tipo_de_documento_de', { fichero: a.filename })} value={a.document_type ?? ''}
                    onChange={e => tipar(a.id, e.target.value)}>
                    <option value="">{t('gas.sin_tipo')}</option>
                    {(tipos.data?.tipos ?? []).map(d => <option key={d} value={d}>{doc(d)}</option>)}
                  </Select>
                ) : <span className="gp-ayuda">{a.document_type ? doc(a.document_type) : t('gas.sin_tipo')}</span>}
                <span className="u-text3-xs">{a.size_bytes ? `${Math.max(1, Math.round(a.size_bytes / 1024))} KB` : ''}</span>
                {editable && <Button size="xs" variant="ghost" title={t('gas.quitar')} icon={<Trash2 size={12} />} onClick={() => quitar(a.id)}>{''}</Button>}
              </div>
            ))}
        </section>

        <section aria-label={t('gas.reparto')}>
          <h4 className="gp-titulo">{t('gas.reparto')}</h4>
          <p className="gp-ayuda gp-mb">{t('gas.reparto_ayuda')}</p>
          {partes.map((p, i) => (
            <div key={i} className="gp-parte">
              <Select suelto placeholder={false} aria-label={t('gas.proyecto')} disabled={!editable} value={p.project_id} onChange={e => setPartes(v => v.map((x, j) => j === i ? { ...x, project_id: e.target.value } : x))} className="gp-campo">
                <option value="">{t('gas.elige_proyecto')}</option>
                {(proyectos.data ?? []).map(pr => <option key={pr.id} value={pr.id}>{pr.code ? `${pr.code} — ` : ''}{pr.name}</option>)}
              </Select>
              <Input aria-label={t('gas.porcentaje')} type="number" min={0} max={100} step="0.01" disabled={!editable} value={p.percentage} onChange={e => setPartes(v => v.map((x, j) => j === i ? { ...x, percentage: e.target.value } : x))} inputClassName="gp-campo" />
              <span className="gp-cifra">{dinero(importe * (Number(p.percentage) || 0) / 100)}</span>
              {editable && <Button size="xs" variant="ghost" title={t('gas.quitar')} icon={<Trash2 size={12} />} onClick={() => setPartes(v => v.filter((_, j) => j !== i))}>{''}</Button>}
            </div>
          ))}
          {editable && (
            <div className="gp-fila gp-mt">
              <Button size="xs" variant="secondary" icon={<Plus size={12} />} onClick={() => setPartes(v => [...v, { project_id: '', percentage: String(Math.max(0, 100 - suma)) }])}>{t('gas.anadir_proyecto')}</Button>
              <span className={partes.length && Math.abs(suma - 100) > 0.01 ? 'gp-error gp-xs' : 'gp-ayuda'} aria-live="polite">
                {partes.length ? t('gas.suma', { n: suma.toLocaleString(localeActivo(), { maximumFractionDigits: 2 }) }) : t('gas.sin_reparto')}
              </span>
              <span className="gp-empuja"><Button size="xs" loading={guardando} disabled={partes.length > 0 && Math.abs(suma - 100) > 0.01} onClick={guardarReparto}>{t('gas.guardar_reparto')}</Button></span>
            </div>
          )}
        </section>
      </div>
    </Modal>
  )
}

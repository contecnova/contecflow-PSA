/**
 * Confirmación del envío de un gasto (rev. 166, tarea #27): antes de enviar, qué
 * políticas aplican y qué pasará —quién aprueba (y los niveles que añade cada
 * exceso), avisos, documentos que faltan y a quién se informa—. Sin efectos:
 * `GET /expenses/{id}/policy-preview`. Si algo lo bloquea o falta un requisito,
 * no se puede confirmar y se dice qué hacer.
 */
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, FileText, Info, Send, ShieldAlert, XCircle } from 'lucide-react'
import { gastosApi } from '../../services/api'
import type { VistaPreviaDeEnvio as Vista } from '../../services/api/gastos'
import { Button, Modal, Spinner } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { extractErr } from '../../utils/helpers'
import './gastos-politicas.css'

export default function VistaPreviaDeEnvio({ gastoId, titulo, enviando, onConfirmar, onCerrar, onAbrirDetalle }: {
  gastoId: string; titulo: string; enviando: boolean
  onConfirmar: () => void; onCerrar: () => void; onAbrirDetalle: () => void
}) {
  const t = useAppT()
  const q = useQuery({ queryKey: ['gasto', gastoId, 'vista-previa'], queryFn: () => gastosApi.vistaPrevia(gastoId), retry: false })
  const v = q.data
  return (
    <Modal open onClose={onCerrar} size="md" title={t('gas.confirmar_envio')} subtitle={titulo}>
      <div className="u-stack-16" aria-live="polite">
        {q.isLoading && <Spinner label={t('gas.comprobando_politicas')} />}
        {q.isError && <div role="alert" className="gp-error">{extractErr(q.error, t('gas.error_vista_previa'))}</div>}
        {v && <Contenido v={v} onAbrirDetalle={onAbrirDetalle} />}
        <div className="gp-acciones">
          <Button variant="secondary" onClick={onCerrar}>{t('gas.cancelar')}</Button>
          <Button icon={<Send size={14} />} loading={enviando} disabled={!v || !v.puede_enviar || enviando} onClick={onConfirmar}>
            {t('gas.enviar_ahora')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function Contenido({ v, onAbrirDetalle }: { v: Vista; onAbrirDetalle: () => void }) {
  const t = useAppT()
  const doc = (d: string) => t(`pol.doc_${d}`, d)
  const pendientes = v.requisitos.filter(r => !r.cumplido)
  const a = v.aprobacion
  const cadena = [
    ...a.pasos_del_flujo.map(p => ({ nombre: p.nombre, politica: false, informar: p.informar })),
    ...a.niveles_anadidos.map(n => ({ nombre: t('gas.responsable_nivel', { n }), politica: true, informar: false })),
    ...a.pasos_anadidos.map(p => ({ nombre: p.nombre || t('gas.paso_de_politica'), politica: true, informar: p.informar })),
  ]
  const veredicto = !v.puede_enviar ? (v.decision === 'block' ? 'gas.veredicto_bloqueo' : 'gas.veredicto_faltan')
    : v.decision === 'auto_approve' ? 'gas.veredicto_auto'
    : cadena.length ? 'gas.veredicto_aprobacion' : 'gas.veredicto_revision'
  const tono = !v.puede_enviar ? 'block' : v.decision
  return (
    <>
      <div className={`gp-veredicto gp-veredicto--${tono}`} role={v.puede_enviar ? 'status' : 'alert'}>
        {!v.puede_enviar ? <XCircle size={18} aria-hidden /> : v.decision === 'review' ? <ShieldAlert size={18} aria-hidden /> : <CheckCircle2 size={18} aria-hidden />}
        <div>
          <p className="gp-texto"><strong>{t(veredicto)}</strong></p>
          <p className="gp-ayuda">{v.politicas_que_aplican.length
            ? t('gas.politicas_que_aplican', { lista: v.politicas_que_aplican.join(', ') }) : t('gas.ninguna_politica_aplica')}</p>
        </div>
      </div>

      {v.bloqueos.length > 0 && (
        <section className="gp-seccion" aria-label={t('gas.bloqueos')}>
          <h4 className="gp-titulo"><XCircle size={14} aria-hidden />{t('gas.bloqueos')}</h4>
          <ul className="gp-lista">{v.bloqueos.map((b, i) => <li key={i} data-estado="pendiente">{b.mensaje}<span className="gp-ayuda">{b.politica}</span></li>)}</ul>
        </section>
      )}

      {v.puede_enviar && v.decision !== 'auto_approve' && (
        <section className="gp-seccion" aria-label={t('gas.quien_aprueba')}>
          <h4 className="gp-titulo"><ShieldAlert size={14} aria-hidden />{t('gas.quien_aprueba')}</h4>
          {cadena.length ? (
            <ol className="gp-cadena">
              {cadena.map((p, i) => (
                <li key={i}><span className={`gp-paso${p.politica ? ' gp-paso--politica' : ''}${p.informar ? ' gp-paso--informar' : ''}`}>
                  {p.nombre}{p.politica && <span className="gp-ayuda">· {t('gas.por_politica')}</span>}{p.informar && <span className="gp-ayuda">· {t('gas.solo_informa')}</span>}
                </span></li>
              ))}
            </ol>
          ) : <p className="gp-ayuda">{t('gas.sin_flujo')}</p>}
          {v.excesos.map((x, i) => (
            <p key={i} className="gp-ayuda">{t('gas.exceso_detalle', {
              politica: x.politica, pct: x.exceso_pct.toLocaleString(undefined, { maximumFractionDigits: 1 }),
              valor: x.valor ?? '', referencia: x.referencia ?? '', moneda: x.moneda ?? '' })}</p>
          ))}
        </section>
      )}

      {v.requisitos.length > 0 && (
        <section className="gp-seccion" aria-label={t('gas.documentos_requeridos')}>
          <h4 className="gp-titulo"><FileText size={14} aria-hidden />{t('gas.documentos_requeridos')}</h4>
          <ul className="gp-lista">
            {v.requisitos.map((r, i) => (
              <li key={i} data-estado={r.cumplido ? 'cumplido' : 'pendiente'}>
                {r.cumplido ? <CheckCircle2 size={14} aria-label={t('gas.cumplido')} /> : <XCircle size={14} aria-label={t('gas.pendiente')} />}
                <span>{r.mensaje || t(`pol.res_${r.tipo}`)}
                  {r.tipos_de_documento.length > 0 && <span className="gp-ayuda"> · {r.tipos_de_documento.map(doc).join(' / ')}</span>}
                </span>
              </li>
            ))}
          </ul>
          {pendientes.length > 0 && (
            <div className="gp-fila"><span className="gp-ayuda">{t('gas.completa_en_el_detalle')}</span>
              <Button size="xs" variant="secondary" onClick={onAbrirDetalle}>{t('gas.abrir_detalle')}</Button></div>
          )}
        </section>
      )}

      {v.avisos.length > 0 && (
        <section className="gp-seccion" aria-label={t('gas.avisos')}>
          <h4 className="gp-titulo"><AlertTriangle size={14} aria-hidden />{t('gas.avisos')}</h4>
          <ul className="gp-lista">{v.avisos.map((x, i) => <li key={i} data-tono="aviso">{x.mensaje}</li>)}</ul>
        </section>
      )}

      {v.avisar.length > 0 && (
        <section className="gp-seccion" aria-label={t('gas.se_informara')}>
          <h4 className="gp-titulo"><Info size={14} aria-hidden />{t('gas.se_informara')}</h4>
          <ul className="gp-lista">
            {v.avisar.map((x, i) => (
              <li key={i}>{x.destinatarios.map(d => `${t(`pol.dest_${d.tipo}`)}${d.valor ? ` (${d.valor})` : ''}`).join(', ')}
                <span className="gp-ayuda"> · {x.canales.map(c => t(`pol.canal_${c}`)).join(', ')}{x.mensaje ? ` · ${x.mensaje}` : ''}</span></li>
            ))}
          </ul>
        </section>
      )}
    </>
  )
}

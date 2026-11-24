/**
 * Ficha de un activo (fase 1): titular vigente, ciclo de vida (compra →
 * almacén → asignado o prestado → reparación → baja → reciclaje), actas de
 * entrega y devolución con su firma y fotos del estado, documentos, software
 * instalado e historial inmutable.
 */
import { useId, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArchiveX, Check, CheckCircle2, Minus, FileSignature, FileText, HandCoins, MapPinOff, PackageCheck, PackageOpen, Plus, Recycle,
  RotateCcw, ShieldAlert, Trash2, Undo2, Upload, UserPlus, Wrench, X,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { Button, Drawer, Modal, Spinner, Tabs, Select, useErroresDeCampo, Input, Textarea, IconButton } from '../ui'
import { LicenseSelect } from '../ui/EntitySelect'
import DateInput from '../ui/DateInput'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { assetsApi } from '../../services/api'
import { almApi } from '../../services/api/alm'
import type { Acta, Adjunto, Asignacion } from '../../services/api/alm'
import { sanitizeUrl } from '../../utils/security'
import { fmtCurrency, fmtDate, fmtDateTime } from '../../utils/helpers'
import AsignarModal from './AsignarModal'
import CerrarAsignacionModal from './CerrarAsignacionModal'
import HistorialAlm from './HistorialAlm'
import { TicketsDelRecurso } from './EnlaceTicketRecurso'
import { Dato, EstadoAlm, ICONO_ACTIVO, ICONO_TITULAR, errorAlm, textoDeChecklist, textoDeTitular } from './almFases'

/** Acciones del ciclo de vida (`alm_ciclo_de_vida.TRANSICIONES`) con su icono. */
const ICONO_ACCION: Record<string, ReactNode> = {
  assign: <UserPlus size={14} />, lend: <HandCoins size={14} />, return: <Undo2 size={14} />,
  receive: <PackageCheck size={14} />, repair_sent: <Wrench size={14} />, repair_done: <CheckCircle2 size={14} />,
  retired: <ArchiveX size={14} />, disposed: <Recycle size={14} />, lost: <MapPinOff size={14} />,
  stolen: <ShieldAlert size={14} />, found: <PackageOpen size={14} />,
}
const MOTIVOS_DE_BAJA = ['obsolete', 'broken', 'lost', 'stolen', 'sold', 'other']
const METODOS = ['recycle', 'donate', 'sell', 'destroy']
const CLAVES = ['alm-assets', 'alm-asset', 'alm-assignments', 'alm-history', 'alm-dashboard', 'alm-acts', 'alm-expiring']

function AccionModal({ assetId, accion, onClose }: { assetId: string; accion: string; onClose: () => void }) {
  const t = useAppT()
  const id = useId()
  const toast = useToast()
  const qc = useQueryClient()
  const [motivo, setMotivo] = useState('')
  const [datos, setDatos] = useState<Record<string, string>>(accion === 'retired' ? { reason: 'obsolete' } : accion === 'disposed' ? { method: 'recycle' } : {})
  const [error, setError] = useState('')
  const campo = (k: string) => (e: { target: { value: string } }) => setDatos(d => ({ ...d, [k]: e.target.value }))
  const campos = useErroresDeCampo()
  const msg = (k: string) => campos.de(k) ? <div className="u-field-error">{campos.de(k)}</div> : null
  const { mutate, isPending } = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: () => almApi.ciclo(assetId, accion, motivo || undefined, datos),
    onSuccess: () => { toast.success(t('alm.lifecycle_done')); CLAVES.forEach(k => qc.invalidateQueries({ queryKey: [k] })); onClose() },
    onError: (e: unknown) => { if (!campos.recoger(e)) setError(errorAlm(t, e)) },
  })
  return (
    <Modal open onClose={onClose} width={560} title={t(`alm.action_${accion}`)}>
      <div className="u-stack-14">
        <p className="alm-hint">{t(`alm.action_${accion}_hint`)}</p>
        {accion === 'repair_sent' && (
          <div className="almf-rejilla-2">
            <div>
              <Input label={t('alm.repair_vendor')} id={`${id}-v`} value={datos.vendor ?? ''} onChange={campo('vendor')} />{msg('vendor')}</div>
            <div>
              <Input label={t('alm.repair_ticket')} id={`${id}-tk`} value={datos.ticket ?? ''} onChange={campo('ticket')} />{msg('ticket')}</div>
            <div>
              <DateInput label={t('alm.repair_expected_back')} id={`${id}-b`} value={datos.expected_back ?? ''} onChange={campo('expected_back')} />{msg('expected_back')}</div>
            <div>
              <Input label={t('alm.repair_cost')} id={`${id}-c`} type="number" min={0} value={datos.cost ?? ''} onChange={campo('cost')} />{msg('cost')}</div>
          </div>
        )}
        {accion === 'retired' && (
          <div>
            <Select label={t('alm.disposal_reason')} placeholder={false} id={`${id}-r`} value={datos.reason} onChange={campo('reason')}>
              {MOTIVOS_DE_BAJA.map(m => <option key={m} value={m}>{t(`alm.disposal_reason_${m}`)}</option>)}
            </Select>{msg('reason')}</div>
        )}
        {accion === 'disposed' && (
          <div className="almf-rejilla-2">
            <div>
              <Select label={t('alm.disposal_method')} placeholder={false} id={`${id}-m`} value={datos.method} onChange={campo('method')}>
                {METODOS.map(m => <option key={m} value={m}>{t(`alm.disposal_method_${m}`)}</option>)}
              </Select>{msg('method')}</div>
            <div>
              <Input label={t('alm.disposal_value')} id={`${id}-val`} type="number" min={0} value={datos.value ?? ''} onChange={campo('value')} />{msg('value')}</div>
          </div>
        )}
        <Textarea label={t('alm.reason')} id={`${id}-mot`} rows={2} value={motivo} onChange={e => setMotivo(e.target.value)} />
        {error && <p className="u-field-error" role="alert">{error}</p>}
      </div>
      <div className="almf-acciones-modal">
        <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant={['retired', 'lost', 'stolen', 'disposed'].includes(accion) ? 'danger' : 'primary'}
          onClick={() => mutate()} loading={isPending} disabled={isPending}>{t(`alm.action_${accion}`)}</Button>
      </div>
    </Modal>
  )
}

function Galeria({ adjuntos }: { adjuntos: Adjunto[] }) {
  const t = useAppT()
  if (!adjuntos.length) return <p className="almf-vacio">{t('alm.attachments_empty')}</p>
  return (
    <div className="almf-galeria">
      {adjuntos.map(a => (
        <a key={a.id} href={sanitizeUrl(a.url ?? '#')} target="_blank" rel="noopener noreferrer" title={a.file_name ?? ''}>
          {a.mime?.startsWith('image/') && a.url
            ? <img src={sanitizeUrl(a.url)} alt={a.file_name ?? t(`alm.attachment_${a.kind}`, a.kind)} loading="lazy" />
            : <span className="almf-galeria__doc"><FileText size={18} aria-hidden="true" />{a.file_name}</span>}
        </a>
      ))}
    </div>
  )
}

function Subir({ etiqueta, onFichero, ocupado }: { etiqueta: string; onFichero: (f: File) => void; ocupado?: boolean }) {
  return (
    <label className="almf-subir" aria-busy={ocupado || undefined}>
      <Upload size={14} aria-hidden="true" />{etiqueta}
      <input type="file" accept="image/*,application/pdf" disabled={ocupado}
        onChange={e => { const f = e.target.files?.[0]; if (f) onFichero(f); e.target.value = '' }} />
    </label>
  )
}

export function TarjetaDeActa({ acta, gestor = true }: { acta: Acta; gestor?: boolean }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const refrescar = () => ['alm-acts', 'alm-asset', 'alm-dashboard'].forEach(k => qc.invalidateQueries({ queryKey: [k] }))
  const regenerar = useMutation({ mutationFn: () => almApi.regenerarActa(acta.id), onSuccess: refrescar, onError: e => toast.error(errorAlm(t, e)) })
  const anular = useMutation({ mutationFn: () => almApi.anularActa(acta.id), onSuccess: refrescar, onError: e => toast.error(errorAlm(t, e)) })
  const foto = useMutation({
    mutationFn: (f: File) => almApi.subirFotoDeActa(acta.id, f),
    onSuccess: () => { toast.success(t('alm.attachment_uploaded')); refrescar() },
    onError: e => toast.error(errorAlm(t, e)),
  })
  return (
    <li className="almf-fila">
      <div className="almf-fila__principal">
        <span className="almf-fila__nombre">
          <FileSignature size={14} aria-hidden="true" />
          {t(`alm.act_${acta.kind}`)} · {acta.asset_name}
          <EstadoAlm t={t} codigo={acta.status} />
        </span>
        <span className="almf-fila__meta">
          {acta.holder_name && <span>{acta.holder_name}</span>}
          {acta.created_at && <span>{fmtDateTime(acta.created_at)}</span>}
          {acta.condition && <span>{t(`alm.assets_condition_${acta.condition}`)}</span>}
          {acta.signed_at && <span>{t('alm.signed_on', { date: fmtDateTime(acta.signed_at) })}</span>}
          {acta.esign_provider && <span>{t(`alm.esign_${acta.esign_provider}`, acta.esign_provider)}</span>}
        </span>
        {acta.checklist.length > 0 && (
          <span className="almf-fila__meta">
            {acta.checklist.map(c => (
              <span key={c.item} className="almf-pills">
                {c.ok ? <Check size={12} aria-label={t('common.yes')} /> : <Minus size={12} aria-label={t('common.no')} />}
                {textoDeChecklist(t, c.item)}{c.note ? ` (${c.note})` : ''}
              </span>
            ))}
          </span>
        )}
        {acta.observations && <span className="almf-evento__motivo">{acta.observations}</span>}
        {acta.attachments.length > 0 && <Galeria adjuntos={acta.attachments} />}
      </div>
      <div className="almf-fila__acciones">
        {acta.pdf_url && <a className="ui-btn ui-btn--secondary ui-btn--sm" href={sanitizeUrl(acta.pdf_url)} target="_blank" rel="noopener noreferrer">{t('alm.act_pdf')}</a>}
        {gestor && acta.status !== 'signed' && acta.status !== 'void' && (
          <>
            {!acta.pdf_url && <Button size="sm" variant="secondary" icon={<RotateCcw size={14} />} loading={regenerar.isPending}
              onClick={() => regenerar.mutate()}>{t('alm.act_regenerate')}</Button>}
            <Subir etiqueta={t('alm.photo_add')} onFichero={f => foto.mutate(f)} ocupado={foto.isPending} />
            <Button size="sm" variant="ghost" icon={<Trash2 size={14} />}
              onClick={() => openConfirmGlobal({ message: t('alm.act_void_confirm'), onConfirm: () => anular.mutate(), danger: true })}>
              {t('alm.act_void')}
            </Button>
          </>
        )}
      </div>
    </li>
  )
}

/** Los cambios de cada campo del activo (`alm_asset_history`): estado, ubicación, fechas... */
function CambiosDeCampos({ assetId }: { assetId: string }) {
  const t = useAppT()
  const { data = [] } = useQuery({ queryKey: ['alm-asset', assetId, 'campos'], queryFn: () => assetsApi.history(assetId).then(r => r.data) })
  if (!data.length) return null
  return (
    <details className="almf-bloque">
      <summary className="almf-bloque__titulo">{t('alm.field_changes', { n: data.length })}</summary>
      <ul className="almf-lista">
        {data.map(h => (
          <li key={h.id} className="almf-fila">
            <div className="almf-fila__principal">
              <span className="almf-fila__nombre">{t(`alm.field_${h.field}`, h.field)}</span>
              <span className="almf-fila__meta">
                <span>{h.old_value ?? '—'} · {h.new_value ?? '—'}</span>
                {h.changed_at && <span>{fmtDateTime(h.changed_at)}</span>}
                {h.user_name && <span>{h.user_name}</span>}
              </span>
            </div>
          </li>
        ))}
      </ul>
    </details>
  )
}

export default function FichaActivo({ assetId, onClose }: { assetId: string; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [tab, setTab] = useState('data')
  const [asignar, setAsignar] = useState<'assignment' | 'loan' | null>(null)
  const [cerrar, setCerrar] = useState<Asignacion | null>(null)
  const [accion, setAccion] = useState<string | null>(null)
  const [licencia, setLicencia] = useState('')
  const { data: a, isLoading } = useQuery({ queryKey: ['alm-asset', assetId], queryFn: () => assetsApi.get(assetId).then(r => r.data) })
  const vigente = useQuery({
    queryKey: ['alm-assignments', 'asset', assetId],
    queryFn: () => almApi.asignaciones({ asset_id: assetId, status: 'active,pending', page_size: 1 }),
    enabled: !!a?.current_assignment_id,
  })
  const actas = useQuery({ queryKey: ['alm-acts', assetId], queryFn: () => almApi.actas({ asset_id: assetId }), enabled: tab === 'acts' })
  const adjuntos = useQuery({ queryKey: ['alm-asset', assetId, 'adjuntos'], queryFn: () => almApi.adjuntosDeActivo(assetId), enabled: tab === 'docs' })
  const subir = useMutation({
    mutationFn: (f: File) => almApi.subirAdjuntoDeActivo(assetId, f, f.type.startsWith('image/') ? 'photo' : 'other'),
    onSuccess: () => { toast.success(t('alm.attachment_uploaded')); qc.invalidateQueries({ queryKey: ['alm-asset', assetId, 'adjuntos'] }) },
    onError: e => toast.error(errorAlm(t, e)),
  })
  const instalar = useMutation({
    mutationFn: () => almApi.instalar(assetId, { license_id: licencia }),
    onSuccess: () => { setLicencia(''); qc.invalidateQueries({ queryKey: ['alm-asset', assetId] }); qc.invalidateQueries({ queryKey: ['alm-licenses'] }) },
    onError: e => toast.error(errorAlm(t, e)),
  })
  const desinstalar = useMutation({
    mutationFn: (installId: string) => almApi.desinstalar(assetId, installId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alm-asset', assetId] }),
    onError: e => toast.error(errorAlm(t, e)),
  })
  const asignacion = vigente.data?.items?.[0] ?? null

  const pulsar = (k: string) => {
    if (k === 'assign') return setAsignar('assignment')
    if (k === 'lend') return setAsignar('loan')
    if (k === 'return') return asignacion && setCerrar(asignacion)
    setAccion(k)
  }

  return (
    <Drawer onClose={onClose} ariaLabel={a?.name ?? t('alm.asset')} width={660} variant="borde">
      <div className="almf-ficha">
        <div className="almf-ficha__cabecera">
          <div className="almf-ficha__titulo">
            <span className="almf-ficha__icono" aria-hidden="true">{(a && ICONO_ACTIVO[a.type]) ?? ICONO_ACTIVO.other}</span>
            <div>
              <h2>{a?.name ?? '…'}</h2>
              <div className="almf-ficha__sub">{[a?.brand, a?.model, a?.asset_tag].filter(Boolean).join(' · ')}</div>
            </div>
          </div>
          <IconButton variante="caja" ariaLabel={t('common.close')} onClick={onClose} data-cierra-dialogo=""><X size={16} aria-hidden="true" /></IconButton>
        </div>
        {isLoading || !a ? <Spinner /> : (
          <div className="almf-ficha__cuerpo">
            <div className="almf-bloque">
              <div className="almf-bloque__titulo">
                <span>{t(`alm.asset_status_${a.status}`, a.status)}</span>
                {a.loan_overdue && <EstadoAlm t={t} codigo="active" vencido />}
              </div>
              {a.holder_type ? (
                <div className="almf-fila">
                  <div className="almf-fila__principal">
                    <span className="almf-fila__nombre">{ICONO_TITULAR[a.holder_type]}{a.holder_name ?? '—'}
                      {a.assignment_status === 'pending' && <EstadoAlm t={t} codigo="pending" />}</span>
                    <span className="almf-fila__meta">
                      <span>{textoDeTitular(t, a.holder_type)}</span>
                      <span>{t(`alm.mode_${a.assignment_mode ?? 'assignment'}`)}</span>
                      {a.loan_due && <span>{t('alm.loan_due_on', { date: fmtDate(a.loan_due) })}</span>}
                    </span>
                  </div>
                </div>
              ) : <p className="almf-vacio">{t('alm.no_holder')}</p>}
              <div className="almf-ficha__acciones">
                {a.actions.map(k => (
                  <Button key={k} size="sm" variant={k === 'assign' || k === 'lend' ? 'primary' : 'secondary'} icon={ICONO_ACCION[k]}
                    onClick={() => pulsar(k)} disabled={k === 'return' && !asignacion}>
                    {t(`alm.action_${k}`)}
                  </Button>
                ))}
                {a.assignment_status === 'pending' && asignacion && (
                  <Button size="sm" variant="ghost" onClick={() => setCerrar(asignacion)}>{t('alm.cancel_request')}</Button>
                )}
              </div>
            </div>

            <Tabs active={tab} onChange={setTab} ariaLabel={a.name} items={[
              { id: 'data', label: t('alm.data') },
              { id: 'acts', label: t('alm.acts') },
              { id: 'docs', label: t('alm.attachments') },
              { id: 'software', label: t('alm.installs'), count: a.licenses.length },
              { id: 'tickets', label: t('alm.tickets') },
              { id: 'history', label: t('alm.history') },
            ]} />

            {tab === 'data' && (
              <dl className="almf-datos">
                <Dato etiqueta={t('alm.assets_label_serial')}>{a.serial_number}</Dato>
                <Dato etiqueta={t('alm.assets_label_location')}>{a.location}</Dato>
                <Dato etiqueta={t('alm.assets_label_condition')}>{t(`alm.assets_condition_${a.condition}`, a.condition)}</Dato>
                <Dato etiqueta={t('alm.assets_label_purchase_date')}>{fmtDate(a.purchase_date)}</Dato>
                <Dato etiqueta={t('alm.assets_label_purchase_price')}>{a.purchase_price != null ? fmtCurrency(a.purchase_price, a.currency) : '—'}</Dato>
                <Dato etiqueta={t('alm.assets_book_value')}>{a.book_value != null ? fmtCurrency(a.book_value, a.currency) : '—'}</Dato>
                {a.residual_value != null && <Dato etiqueta={t('alm.residual_value')}>{fmtCurrency(a.residual_value, a.currency)}</Dato>}
                {a.lease_monthly_cost != null && <Dato etiqueta={t('alm.lease_monthly_cost')}>{fmtCurrency(a.lease_monthly_cost, a.currency)}</Dato>}
                <Dato etiqueta={t('alm.assets_label_warranty_end')}>{fmtDate(a.warranty_expiry)}</Dato>
                <Dato etiqueta={t('alm.rebillable')}>{a.rebillable ? t('common.yes') : t('common.no')}</Dato>
                {a.disposal_date && <Dato etiqueta={t('alm.disposal_reason')}>{`${fmtDate(a.disposal_date)} · ${t(`alm.disposal_reason_${a.disposal_reason}`, a.disposal_reason ?? '')}`}</Dato>}
                {a.disposal_method && <Dato etiqueta={t('alm.disposal_method')}>{t(`alm.disposal_method_${a.disposal_method}`)}{a.disposal_value != null ? ` · ${fmtCurrency(a.disposal_value, a.currency)}` : ''}</Dato>}
              </dl>
            )}

            {tab === 'acts' && (actas.isLoading ? <Spinner /> : (actas.data ?? []).length === 0
              ? <p className="almf-vacio">{t('alm.acts_empty')}</p>
              : <ul className="almf-lista">{(actas.data ?? []).map(ac => <TarjetaDeActa key={ac.id} acta={ac} />)}</ul>)}

            {tab === 'docs' && (
              <div className="almf-bloque">
                <Subir etiqueta={t('alm.attachment_add')} onFichero={f => subir.mutate(f)} ocupado={subir.isPending} />
                {adjuntos.isLoading ? <Spinner /> : <Galeria adjuntos={adjuntos.data ?? []} />}
              </div>
            )}

            {tab === 'software' && (
              <div className="almf-bloque">
                <div className="almf-filtros">
                  <div className="almf-filtro">
                    <span className="uiinde-estiloetiqueta">{t('alm.install_license')}</span>
                    <LicenseSelect value={licencia} onChange={v => setLicencia(v)} />
                  </div>
                  <Button icon={<Plus size={14} />} disabled={!licencia || instalar.isPending} loading={instalar.isPending}
                    onClick={() => instalar.mutate()}>{t('alm.install_add')}</Button>
                </div>
                {a.licenses.length === 0 ? <p className="almf-vacio">{t('alm.installs_empty')}</p> : (
                  <ul className="almf-lista">
                    {a.licenses.map(l => (
                      <li key={l.install_id} className="almf-fila">
                        <span className="almf-fila__nombre">{l.name ?? '—'}{l.version ? ` · ${l.version}` : ''}</span>
                        <Button size="sm" variant="ghost" icon={<Trash2 size={14} />}
                          onClick={() => openConfirmGlobal({ message: t('alm.install_remove_confirm', { name: l.name ?? '' }), onConfirm: () => desinstalar.mutate(l.install_id), danger: true })}>
                          {t('alm.install_remove')}
                        </Button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            {tab === 'tickets' && <TicketsDelRecurso tipo="asset" id={assetId} />}

            {tab === 'history' && (
              <>
                <HistorialAlm filtro={{ asset_id: assetId }} />
                <CambiosDeCampos assetId={assetId} />
              </>
            )}
          </div>
        )}
      </div>
      {asignar && a && <AsignarModal recurso={{ tipo: 'asset', id: a.id, nombre: a.name }} modoInicial={asignar} onClose={() => setAsignar(null)} />}
      {cerrar && <CerrarAsignacionModal asignacion={cerrar} onClose={() => setCerrar(null)} />}
      {accion && <AccionModal assetId={assetId} accion={accion} onClose={() => setAccion(null)} />}
    </Drawer>
  )
}

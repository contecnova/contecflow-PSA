/**
 * Ficha de una licencia (fase 1): asientos según su métrica, titulares (bolsas
 * con su reparto), uso, pico concurrente, instalaciones, clave cifrada (se ve
 * a petición y queda en el historial) e historial inmutable.
 */
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Eye, Plus, Split, X, UserMinus, Activity } from 'lucide-react'
import { Button, Drawer, Spinner, Tabs } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { licensesApi } from '../../services/api'
import { almApi } from '../../services/api/alm'
import type { Asignacion } from '../../services/api/alm'
import { fmtCurrency, fmtDate, fmtDateTime } from '../../utils/helpers'
import AsignarModal from './AsignarModal'
import CerrarAsignacionModal from './CerrarAsignacionModal'
import HistorialAlm from './HistorialAlm'
import { TicketsDelRecurso } from './EnlaceTicketRecurso'
import { Dato, EstadoAlm, ICONO_LICENCIA, ICONO_LICENCIA_DEFECTO, ICONO_TITULAR, errorAlm, textoDeTitular } from './almFases'

function FilaDeAsignacion({ a, hija, onRepartir, onCerrar }: {
  a: Asignacion; hija?: boolean; onRepartir?: () => void; onCerrar: () => void
}) {
  const t = useAppT()
  return (
    <li className={`almf-fila${hija ? ' almf-fila--hija' : ''}`}>
      <div className="almf-fila__principal">
        <span className="almf-fila__nombre">
          {ICONO_TITULAR[a.holder_type]}
          {a.holder_name ?? textoDeTitular(t, a.holder_type)}
          <EstadoAlm t={t} codigo={a.status} />
          {a.mode === 'pool' && <span className="alm-compliance-tag">{t('alm.pool_badge', { used: a.used_in_pool ?? 0, total: a.quantity })}</span>}
          {a.mode !== 'pool' && a.quantity > 1 && <span className="alm-compliance-tag">{t('alm.quantity_n', { n: a.quantity })}</span>}
        </span>
        <span className="almf-fila__meta">
          <span>{textoDeTitular(t, a.holder_type)}</span>
          <span>{t('alm.since_date', { date: fmtDate(a.valid_from) })}</span>
          {a.valid_to && <span>{t('alm.until_date', { date: fmtDate(a.valid_to) })}</span>}
          {a.assigned_by_name && <span>{t('alm.assigned_by', { name: a.assigned_by_name })}</span>}
          {a.rebillable && <span>{t('alm.rebillable')}</span>}
        </span>
        {a.reason && <span className="almf-evento__motivo">{a.reason}</span>}
      </div>
      <div className="almf-fila__acciones">
        {onRepartir && a.status === 'active' && (
          <Button size="sm" variant="secondary" icon={<Split size={14} />} onClick={onRepartir}>{t('alm.pool_split')}</Button>
        )}
        <Button size="sm" variant="ghost" icon={<UserMinus size={14} />} onClick={onCerrar}>
          {a.status === 'pending' ? t('alm.cancel_request') : t('alm.end_action')}
        </Button>
      </div>
    </li>
  )
}

export default function FichaLicencia({ licenseId, onClose }: { licenseId: string; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [tab, setTab] = useState('holders')
  const [asignar, setAsignar] = useState<{ bolsa: Asignacion | null } | null>(null)
  const [cerrar, setCerrar] = useState<Asignacion | null>(null)
  const [clave, setClave] = useState<string | null>(null)
  const [pico, setPico] = useState('')
  const { data: lic, isLoading } = useQuery({
    queryKey: ['alm-license', licenseId],
    queryFn: () => licensesApi.get(licenseId).then(r => r.data),
  })
  const uso = useQuery({ queryKey: ['alm-license', licenseId, 'uso'], queryFn: () => almApi.uso(licenseId), enabled: tab === 'usage' })
  const picos = useQuery({
    queryKey: ['alm-license', licenseId, 'picos'], queryFn: () => almApi.picos(licenseId),
    enabled: tab === 'usage' && lic?.metric === 'concurrent',
  })
  const verClave = useMutation({
    mutationFn: () => almApi.clave(licenseId),
    onSuccess: r => setClave(r.license_key ?? ''),
    onError: e => toast.error(errorAlm(t, e)),
  })
  const anotarPico = useMutation({
    mutationFn: () => almApi.anotarPico(licenseId, Number(pico)),
    onSuccess: () => { setPico(''); qc.invalidateQueries({ queryKey: ['alm-license', licenseId] }); qc.invalidateQueries({ queryKey: ['alm-licenses'] }) },
    onError: e => toast.error(errorAlm(t, e)),
  })

  const asignaciones = lic?.assignments ?? []
  const primeras = asignaciones.filter(a => !a.parent_id)
  const hijas = (id: string) => asignaciones.filter(a => a.parent_id === id)
  const concurrente = lic?.metric === 'concurrent'
  const ocupados = concurrente ? (lic?.concurrent_peak ?? 0) : (lic?.used_seats ?? 0)
  const pct = lic?.total_seats ? Math.min(100, (ocupados / lic.total_seats) * 100) : 0
  const tono = pct > 100 || (lic?.total_seats && ocupados > lic.total_seats) ? ' almf-barra__relleno--peligro' : pct > 85 ? ' almf-barra__relleno--aviso' : ''

  return (
    <Drawer onClose={onClose} ariaLabel={lic?.name ?? t('alm.license')} width={640} variant="borde">
      <div className="almf-ficha">
        <div className="almf-ficha__cabecera">
          <div className="almf-ficha__titulo">
            <span className="almf-ficha__icono" aria-hidden="true">{(lic && ICONO_LICENCIA[lic.type]) ?? ICONO_LICENCIA_DEFECTO}</span>
            <div>
              <h2>{lic?.name ?? '…'}</h2>
              <div className="almf-ficha__sub">
                {[lic?.vendor_name, lic?.tier, lic && t(`alm.metric_${lic.metric}`)].filter(Boolean).join(' · ')}
              </div>
            </div>
          </div>
          <button type="button" className="alm-icon-btn" aria-label={t('common.close')} onClick={onClose}><X size={16} aria-hidden="true" /></button>
        </div>
        {isLoading || !lic ? <Spinner /> : (
          <div className="almf-ficha__cuerpo">
            <div className="almf-ficha__acciones">
              <Button icon={<Plus size={14} />} onClick={() => setAsignar({ bolsa: null })}>{t('alm.assign_action')}</Button>
              {lic.has_key && (
                <Button variant="secondary" icon={<Eye size={14} />} onClick={() => verClave.mutate()} loading={verClave.isPending}>
                  {t('alm.key_show')}
                </Button>
              )}
            </div>
            {clave !== null && (
              <div className="almf-aviso almf-aviso--info" role="status">
                <span className="almf-mono">{clave || '—'}</span>
              </div>
            )}

            <div className="almf-bloque">
              <div className="almf-bloque__titulo">
                <span>{concurrente ? t('alm.seats_peak') : t('alm.licenses_seats_used')}</span>
                <span>{lic.total_seats ? `${ocupados}/${lic.total_seats}` : t('alm.seats_unlimited', { n: lic.used_seats })}</span>
              </div>
              {lic.total_seats ? (
                <div className="almf-barra" role="progressbar" aria-valuemin={0} aria-valuemax={lic.total_seats} aria-valuenow={ocupados}
                  aria-label={t('alm.licenses_seats_used')}>
                  <div className={`almf-barra__relleno${tono}`} style={{ '--almf-pct': `${pct}%` } as CSSProperties} />
                </div>
              ) : null}
              {concurrente && <p className="alm-hint">{t('alm.concurrent_hint', { n: lic.used_seats })}</p>}
            </div>

            <dl className="almf-datos">
              <Dato etiqueta={t('alm.metric')}>{t(`alm.metric_${lic.metric}`)}</Dato>
              <Dato etiqueta={t('alm.licenses_label_type')}>{t(`alm.license_type_${lic.type}`, lic.type)}</Dato>
              {(lic.sku || lic.tier) && <Dato etiqueta={t('alm.tier_sku')}>{[lic.tier, lic.sku].filter(Boolean).join(' · ')}</Dato>}
              <Dato etiqueta={t('alm.contracts_label_annual_cost')}>{lic.annual_cost != null ? fmtCurrency(lic.annual_cost) : '—'}</Dato>
              <Dato etiqueta={t('alm.licenses_label_expiry_date')}>{fmtDate(lic.expiry_date)}</Dato>
              <Dato etiqueta={t('alm.licenses_label_contract')}>{lic.contract_title ?? '—'}</Dato>
              {lic.has_key && <Dato etiqueta={t('alm.licenses_label_key')}><span className="almf-mono">•••• {lic.license_key_hint}</span></Dato>}
              <Dato etiqueta={t('alm.rebillable')}>{lic.rebillable ? t('common.yes') : t('common.no')}</Dato>
            </dl>

            <Tabs active={tab} onChange={setTab} ariaLabel={lic.name} items={[
              { id: 'holders', label: t('alm.holders'), count: primeras.length },
              { id: 'usage', label: t('alm.usage'), icon: <Activity size={14} /> },
              { id: 'installs', label: t('alm.installs'), count: lic.installs.length },
              { id: 'tickets', label: t('alm.tickets') },
              { id: 'history', label: t('alm.history') },
            ]} />

            {tab === 'holders' && (primeras.length === 0 ? <p className="almf-vacio">{t('alm.holders_empty')}</p> : (
              <ul className="almf-lista">
                {primeras.map(a => (
                  <FilaDeAsignacionConHijas key={a.id} a={a} hijas={hijas(a.id)}
                    onRepartir={() => setAsignar({ bolsa: a })} onCerrar={setCerrar} />
                ))}
              </ul>
            ))}

            {tab === 'usage' && (
              <div className="almf-bloque">
                {uso.isLoading ? <Spinner /> : uso.data && (
                  <dl className="almf-datos">
                    <Dato etiqueta={t('alm.usage_assigned')}>{uso.data.assigned}</Dato>
                    <Dato etiqueta={t('alm.usage_in_use')}>{uso.data.in_use ?? t('alm.usage_no_data_yet')}</Dato>
                    <Dato etiqueta={t('alm.usage_underused')}>{uso.data.underused ?? '—'}</Dato>
                    <Dato etiqueta={t('alm.usage_unused')}>{uso.data.unused ?? '—'}</Dato>
                    <Dato etiqueta={t('alm.usage_source')}>{t(`alm.usage_source_${uso.data.source}`, uso.data.source)}</Dato>
                  </dl>
                )}
                {concurrente && (
                  <>
                    <h4 className="almf-bloque__titulo">{t('alm.peaks')}</h4>
                    <div className="almf-filtros">
                      <div className="almf-filtro">
                        <label className="alm-label" htmlFor="almf-pico">{t('alm.peak_record')}</label>
                        <input id="almf-pico" type="number" min={0} className="alm-input" value={pico} onChange={e => setPico(e.target.value)} />
                      </div>
                      <Button variant="secondary" disabled={pico === '' || anotarPico.isPending} loading={anotarPico.isPending}
                        onClick={() => anotarPico.mutate()}>{t('common.save')}</Button>
                    </div>
                    {(picos.data ?? []).length === 0 ? <p className="almf-vacio">{t('alm.peaks_empty')}</p> : (
                      <ul className="almf-lista">
                        {(picos.data ?? []).slice(0, 20).map(p => (
                          <li key={p.id} className="almf-fila">
                            <span>{t('alm.peak_n', { n: p.peak })}</span>
                            <span className="almf-fila__meta">{fmtDateTime(p.measured_at)} · {t(`alm.usage_source_${p.source}`, p.source)}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </>
                )}
              </div>
            )}

            {tab === 'installs' && (lic.installs.length === 0 ? <p className="almf-vacio">{t('alm.installs_empty')}</p> : (
              <ul className="almf-lista">
                {lic.installs.map(i => (
                  <li key={i.id} className="almf-fila">
                    <span className="almf-fila__nombre">{i.asset_name ?? '—'}</span>
                    <span className="almf-fila__meta">{i.version ?? ''} {i.installed_at ? fmtDate(i.installed_at) : ''}</span>
                  </li>
                ))}
              </ul>
            ))}

            {tab === 'tickets' && <TicketsDelRecurso tipo="license" id={licenseId} />}

            {tab === 'history' && <HistorialAlm filtro={{ license_id: licenseId }} />}
          </div>
        )}
      </div>
      {asignar && lic && (
        <AsignarModal onClose={() => setAsignar(null)} bolsa={asignar.bolsa}
          recurso={{ tipo: 'license', id: lic.id, nombre: lic.name, metric: lic.metric, totalSeats: lic.total_seats, usedSeats: lic.used_seats }} />
      )}
      {cerrar && <CerrarAsignacionModal asignacion={cerrar} onClose={() => setCerrar(null)} />}
    </Drawer>
  )
}

function FilaDeAsignacionConHijas({ a, hijas, onRepartir, onCerrar }: {
  a: Asignacion; hijas: Asignacion[]; onRepartir: () => void; onCerrar: (a: Asignacion) => void
}) {
  return (
    <>
      <FilaDeAsignacion a={a} onRepartir={a.mode === 'pool' ? onRepartir : undefined} onCerrar={() => onCerrar(a)} />
      {hijas.map(h => <FilaDeAsignacion key={h.id} a={h} hija onCerrar={() => onCerrar(h)} />)}
    </>
  )
}

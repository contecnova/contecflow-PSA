/**
 * Pestaña Riesgo → Informes (22-11-2026): informes programados de riesgo
 * (`cyber_risk`: índice, tendencia, factores y plan; `vuln_management`:
 * métricas y principales hallazgos) por correo con PDF, con su ámbito,
 * frecuencia, hora, día y destinatarios; «Enviar ahora».
 *
 * Diseño: docs/CMDB_SOFTWARE_Y_VULNERABILIDADES.md §11.10.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FileText, Plus, Send, Trash2 } from 'lucide-react'
import { useAppT } from '../../../../i18n/AppLangContext'
import { useToast } from '../../../../context/ToastContext'
import { useAuth } from '../../../../context/AuthContext'
import { confirmar } from '../../../../context/ConfirmContext'
import { fmtDateTime } from '../../../../utils/helpers'
import { cmdbRiesgoApi } from '../../../../services/api/cmdbRiesgo'
import type { Ambito, Frecuencia, InformeDeRiesgo, InformeDeRiesgoIn, TipoDeInforme } from '../../../../services/api/cmdbRiesgo'
import { Button, Checkbox, EmptyState, IconButton, Input, Modal, Section, Select, Spinner, StatusBadge } from '../../../ui'
import { useErr } from '../comun'
import SelectorDeAmbito from './SelectorDeAmbito'
import { useEtiquetaSwr, useMetaRiesgo } from './comunRiesgo'

const TIPOS: TipoDeInforme[] = ['cyber_risk', 'vuln_management']
const FRECUENCIAS: Frecuencia[] = ['daily', 'weekly', 'monthly']
const DIAS_SEMANA = [0, 1, 2, 3, 4, 5, 6]
const RE_CORREO = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export default function Informes() {
  const t = useAppT()
  const e = useEtiquetaSwr()
  const toast = useToast()
  const qc = useQueryClient()
  const err = useErr()
  const { puede } = useAuth()
  const gestiona = puede('software.gestionar')
  const [editando, setEditando] = useState<InformeDeRiesgo | 'nuevo' | null>(null)
  const { data, isLoading } = useQuery({ queryKey: ['swr', 'informes'], queryFn: cmdbRiesgoApi.informes })
  const refrescar = () => qc.invalidateQueries({ queryKey: ['swr', 'informes'] })
  const enviar = useMutation({
    mutationFn: cmdbRiesgoApi.enviarInforme,
    onSuccess: r => {
      const n = Array.isArray(r.recipients) ? r.recipients.length : Number(r.recipients ?? 0)
      if (r.ok) toast.success(t('swr.informe_enviado', { n }))
      else toast.error(t('swr.informe_fallo', { detalle: r.error ?? '' }))
      refrescar()
    },
    onError: err,
  })
  const borrar = useMutation({ mutationFn: cmdbRiesgoApi.borrarInforme, onSuccess: refrescar, onError: err })
  const activar = useMutation({ mutationFn: ({ id, si }: { id: string; si: boolean }) => cmdbRiesgoApi.editarInforme(id, { is_active: si }), onSuccess: refrescar, onError: err })
  const lista = data ?? []
  const cuando = (x: InformeDeRiesgo) => {
    const hora = `${String(x.send_hour).padStart(2, '0')}:00`
    if (x.frequency === 'weekly') return t('swr.cuando_semanal', { dia: t(`swr.dia_semana_${x.day_of_week ?? 0}`), hora })
    if (x.frequency === 'monthly') return t('swr.cuando_mensual', { dia: x.day_of_month ?? 1, hora })
    return t('swr.cuando_diario', { hora })
  }
  return (
    <Section title={t('swr.informes')} subtitle={t('swr.informes_desc')}
      actions={gestiona && <Button size="sm" icon={<Plus size={14} />} onClick={() => setEditando('nuevo')}>{t('swr.nuevo_informe')}</Button>}>
      {isLoading ? <Spinner /> : lista.length === 0 ? <EmptyState icon={<FileText size={28} />} title={t('swr.sin_informes')} /> : (
        <ul className="sdm-list">
          {lista.map(x => (
            <li key={x.id} className="sdm-list__item">
              <div className="u-flex1-min0 u-stack-6">
                <div className="u-wrap-8">
                  <span className="u-text1-sm-600">{x.name}</span>
                  <StatusBadge caps={false}>{e('informe', x.report_type)}</StatusBadge>
                  <StatusBadge caps={false} kind="accent">{e('ambito', x.scope_type)}</StatusBadge>
                  <StatusBadge kind={x.is_active ? 'success' : 'neutral'} caps={false}>{t(x.is_active ? 'swr.activo' : 'swr.inactivo')}</StatusBadge>
                  {x.last_status && <StatusBadge kind={x.last_status === 'ok' ? 'success' : x.last_status === 'error' ? 'danger' : 'info'} caps={false}>{e('estado_envio', x.last_status)}</StatusBadge>}
                </div>
                <div className="u-text3-xs">{cuando(x)} · {t('swr.destinatarios_n', { n: x.recipients.length })}: {x.recipients.join(', ')}</div>
                <div className="u-text3-xs">{t('swr.ultimo_envio')}: {x.last_run_at ? fmtDateTime(x.last_run_at) : t('swr.nunca')} · {t('swr.proximo_envio')}: {x.is_active && x.next_run_at ? fmtDateTime(x.next_run_at) : '—'}</div>
                {x.last_error && <div className="u-text3-xs u-danger sdm-wrap">{x.last_error}</div>}
              </div>
              {gestiona && (
                <div className="u-actions-8">
                  <Button size="xs" variant="secondary" icon={<Send size={12} />} loading={enviar.isPending && enviar.variables === x.id} disabled={enviar.isPending} onClick={() => enviar.mutate(x.id)}>{t('swr.enviar_ahora')}</Button>
                  <Button size="xs" variant="ghost" onClick={() => activar.mutate({ id: x.id, si: !x.is_active })}>{t(x.is_active ? 'swr.desactivar' : 'swr.activar')}</Button>
                  <Button size="xs" variant="ghost" onClick={() => setEditando(x)}>{t('swr.editar')}</Button>
                  <IconButton variante="caja" tono="peligro" ariaLabel={t('swr.borrar')} onClick={async () => { if (await confirmar({ message: t('swr.borrar_informe_confirmar', { nombre: x.name }), danger: true })) borrar.mutate(x.id) }}><Trash2 size={14} /></IconButton>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      {editando && <InformeModal inicial={editando === 'nuevo' ? null : editando} onClose={() => setEditando(null)} onSaved={() => { setEditando(null); refrescar() }} />}
    </Section>
  )
}

function InformeModal({ inicial, onClose, onSaved }: { inicial: InformeDeRiesgo | null; onClose: () => void; onSaved: () => void }) {
  const t = useAppT()
  const e = useEtiquetaSwr()
  const toast = useToast()
  const err = useErr()
  const meta = useMetaRiesgo()
  const [nombre, setNombre] = useState(inicial?.name ?? '')
  const [tipo, setTipo] = useState<TipoDeInforme>(inicial?.report_type ?? 'cyber_risk')
  const [ambito, setAmbito] = useState<Ambito>({ scope_type: inicial?.scope_type ?? 'org', scope_id: inicial?.scope_id ?? null })
  const [frecuencia, setFrecuencia] = useState<Frecuencia>(inicial?.frequency ?? 'weekly')
  const [hora, setHora] = useState(String(inicial?.send_hour ?? 8))
  const [diaSemana, setDiaSemana] = useState(String(inicial?.day_of_week ?? 0))
  const [diaMes, setDiaMes] = useState(String(inicial?.day_of_month ?? 1))
  const [destinatarios, setDestinatarios] = useState((inicial?.recipients ?? []).join(', '))
  const [activo, setActivo] = useState(inicial?.is_active ?? true)
  const correos = destinatarios.split(/[,;\s]+/).map(s => s.trim()).filter(Boolean)
  const malos = correos.filter(c => !RE_CORREO.test(c))
  const horaN = Number(hora)
  const diaMesN = Number(diaMes)
  const datos = (): InformeDeRiesgoIn => ({
    name: nombre.trim(), report_type: tipo, scope_type: ambito.scope_type, scope_id: ambito.scope_type === 'org' ? null : ambito.scope_id ?? null,
    frequency: frecuencia, send_hour: horaN, day_of_week: frecuencia === 'weekly' ? Number(diaSemana) : null,
    day_of_month: frecuencia === 'monthly' ? diaMesN : null, recipients: correos, is_active: activo,
  })
  const guardar = useMutation({
    mutationFn: () => (inicial ? cmdbRiesgoApi.editarInforme(inicial.id, datos()) : cmdbRiesgoApi.crearInforme(datos())),
    onSuccess: () => { toast.success(t('swr.guardado')); onSaved() },
    onError: err,
  })
  const listo = nombre.trim().length >= 2 && correos.length > 0 && malos.length === 0 && horaN >= 0 && horaN <= 23
    && (ambito.scope_type === 'org' || !!ambito.scope_id) && (frecuencia !== 'monthly' || (diaMesN >= 1 && diaMesN <= 28))
  return (
    <Modal open size="lg" onClose={onClose} title={inicial ? t('swr.editar_informe') : t('swr.nuevo_informe')}>
      <div className="u-stack-12">
        <div className="sdm-form">
          <Input label={t('swr.col_nombre')} value={nombre} onChange={ev => setNombre(ev.target.value)} />
          <Select label={t('swr.tipo_informe')} placeholder={false} value={tipo} onChange={ev => setTipo(ev.target.value as TipoDeInforme)}
            hint={t(`swr.informe_ayuda_${tipo}`)}>
            {(meta.data?.report_types ?? TIPOS).map(x => <option key={x} value={x}>{e('informe', x)}</option>)}
          </Select>
        </div>
        <SelectorDeAmbito className="sdm-form" valor={ambito} onChange={setAmbito} />
        <div className="sdm-form">
          <Select label={t('swr.frecuencia')} placeholder={false} value={frecuencia} onChange={ev => setFrecuencia(ev.target.value as Frecuencia)}>
            {(meta.data?.frequencies ?? FRECUENCIAS).map(x => <option key={x} value={x}>{e('frecuencia', x)}</option>)}
          </Select>
          <Input label={t('swr.hora')} type="number" min={0} max={23} value={hora} onChange={ev => setHora(ev.target.value)} hint={t('swr.hora_ayuda')} />
          {frecuencia === 'weekly' && (
            <Select label={t('swr.dia_semana')} placeholder={false} value={diaSemana} onChange={ev => setDiaSemana(ev.target.value)}>
              {DIAS_SEMANA.map(d => <option key={d} value={d}>{t(`swr.dia_semana_${d}`)}</option>)}
            </Select>
          )}
          {frecuencia === 'monthly' && <Input label={t('swr.dia_mes')} type="number" min={1} max={28} value={diaMes} onChange={ev => setDiaMes(ev.target.value)} hint={t('swr.dia_mes_ayuda')} />}
        </div>
        <Input label={t('swr.destinatarios')} value={destinatarios} placeholder={t('swr.destinatarios_ph')} onChange={ev => setDestinatarios(ev.target.value)}
          error={malos.length ? t('swr.correos_malos', { lista: malos.join(', ') }) : undefined} hint={t('swr.destinatarios_ayuda')} />
        <Checkbox checked={activo} onChange={setActivo} label={t('swr.activo')} />
        <div className="u-actions-10">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button disabled={!listo} loading={guardar.isPending} onClick={() => guardar.mutate()}>{t('common.save')}</Button>
        </div>
      </div>
    </Modal>
  )
}

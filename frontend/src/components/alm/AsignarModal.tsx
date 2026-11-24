/**
 * Asignar una licencia o un activo (licencias y hardware, fase 1).
 *
 * Titular universal (persona, proyecto, departamento, cliente o equipo), desde/
 * hasta, motivo, cantidad (bolsas y volumen), préstamo con devolución, imputación
 * del coste y, para un equipo que pasa a una persona, el checklist del acta de
 * entrega. Si la empresa tiene flujo de aprobación para `alm_assignment`, la
 * asignación queda pendiente y se avisa.
 */
import { useEffect, useId, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Modal, Button, GrupoDeOpciones, Select, Input, Textarea } from '../ui'
import { ProjectSelect, ClientSelect } from '../ui/EntitySelect'
import DateInput from '../ui/DateInput'
import { useToast } from '../../context/ToastContext'
import { useAppT } from '../../i18n/AppLangContext'
import { almApi } from '../../services/api/alm'
import type { Asignacion, Condicion, FilaDeChecklist, ModoDeAsignacion, NuevaAsignacion, TipoDeTitular } from '../../services/api/alm'
import { almExtApi } from '../../services/api'
import { EditorDeChecklist, SelectorDeTitular, errorAlm, hoyIso } from './almFases'

export interface RecursoAAsignar {
  tipo: 'license' | 'asset'
  id: string
  nombre: string
  metric?: string
  totalSeats?: number | null
  usedSeats?: number
}

function tiposPermitidos(r: RecursoAAsignar, bolsa?: Asignacion | null): TipoDeTitular[] {
  if (r.tipo === 'asset') return ['user', 'project', 'department', 'client', 'asset']
  if (bolsa) return r.metric === 'device' ? ['asset'] : ['user']
  if (r.metric === 'device') return ['asset', 'project', 'department', 'client']
  if (r.metric === 'named_user') return ['user', 'project', 'department', 'client']
  return ['user', 'asset', 'project', 'department', 'client']
}

export default function AsignarModal({ recurso, bolsa = null, modoInicial = 'assignment', onClose }: {
  recurso: RecursoAAsignar
  bolsa?: Asignacion | null
  modoInicial?: 'assignment' | 'loan'
  onClose: () => void
}) {
  const t = useAppT()
  const idBase = useId()
  const toast = useToast()
  const qc = useQueryClient()
  const tipos = tiposPermitidos(recurso, bolsa)
  const cfg = useQuery({ queryKey: ['alm-config'], queryFn: almApi.config, staleTime: 5 * 60_000 })
  const { data: centros = [] } = useQuery({ queryKey: ['alm-cost-centers'], queryFn: () => almExtApi.costCenters().then(r => r.data) })

  const [tipo, setTipo] = useState<TipoDeTitular>(tipos[0])
  const [titular, setTitular] = useState('')
  const [modo, setModo] = useState<ModoDeAsignacion>(modoInicial)
  const [cantidad, setCantidad] = useState('1')
  const [desde, setDesde] = useState(hoyIso())
  const [hasta, setHasta] = useState('')
  const [motivo, setMotivo] = useState('')
  const [cargoProyecto, setCargoProyecto] = useState('')
  const [cargoCentro, setCargoCentro] = useState('')
  const [cargoCliente, setCargoCliente] = useState('')
  const [refacturar, setRefacturar] = useState<'' | 'yes' | 'no'>('')
  const [checklist, setChecklist] = useState<FilaDeChecklist[]>([])
  const [condicion, setCondicion] = useState<Condicion | ''>('')
  const [observaciones, setObservaciones] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    if (cfg.data) setChecklist(cfg.data.checklist.map(item => ({ item, ok: false, note: '' })))
  }, [cfg.data])
  useEffect(() => {
    if (modo === 'loan' && !hasta && cfg.data) setHasta(hoyIso(cfg.data.loan_default_days || 14))
  }, [modo, hasta, cfg.data])

  const esBolsa = recurso.tipo === 'license' && !bolsa && ['project', 'department', 'client'].includes(tipo)
  const pideCantidad = recurso.tipo === 'license' && (esBolsa || recurso.metric === 'volume')
  const conActa = recurso.tipo === 'asset' && tipo === 'user' && !!cfg.data?.acts_enabled
  const libres = useMemo(() => {
    if (bolsa) return Math.max(0, bolsa.quantity - (bolsa.used_in_pool ?? 0))
    if (recurso.tipo !== 'license' || recurso.totalSeats == null || ['concurrent', 'site'].includes(recurso.metric ?? '')) return null
    return Math.max(0, recurso.totalSeats - (recurso.usedSeats ?? 0))
  }, [bolsa, recurso])

  const { mutate, isPending } = useMutation({
    mutationFn: () => {
      const cuerpo: NuevaAsignacion = {
        holder_type: tipo, holder_id: titular, valid_from: desde || undefined, valid_to: hasta || undefined,
        reason: motivo.trim() || undefined,
        quantity: pideCantidad ? Number(cantidad) || 1 : 1,
        mode: recurso.tipo === 'asset' ? modo : (esBolsa ? 'pool' : undefined),
        parent_id: bolsa?.id,
        charge_project_id: cargoProyecto || undefined, charge_cost_center_id: cargoCentro || undefined,
        charge_client_id: cargoCliente || undefined,
        rebillable: refacturar === '' ? undefined : refacturar === 'yes',
      }
      if (conActa) Object.assign(cuerpo, { checklist, condition: condicion || undefined, observations: observaciones.trim() || undefined })
      return recurso.tipo === 'license' ? almApi.asignarLicencia(recurso.id, cuerpo) : almApi.asignarActivo(recurso.id, cuerpo)
    },
    onSuccess: (r) => {
      const pendiente = (r as Asignacion | undefined)?.status === 'pending'
      toast.success(pendiente ? t('alm.assign_pending_approval') : t('alm.assign_done'))
      for (const k of ['alm-licenses', 'alm-license', 'alm-assets', 'alm-asset', 'alm-assignments', 'alm-history', 'alm-dashboard', 'alm-acts'])
        qc.invalidateQueries({ queryKey: [k] })
      onClose()
    },
    onError: e => setError(errorAlm(t, e)),
  })

  const enviar = () => {
    setError('')
    if (!titular) return setError(t('alm.err_titular_obligatorio'))
    if (modo === 'loan' && !hasta) return setError(t('alm.err_prestamo_sin_devolucion'))
    if (hasta && desde && hasta < desde) return setError(t('alm.err_fin_antes_de_inicio'))
    mutate()
  }

  const titulo = bolsa ? t('alm.assign_from_pool', { name: recurso.nombre })
    : recurso.tipo === 'asset' && modo === 'loan' ? t('alm.lend_title', { name: recurso.nombre })
      : t('alm.assign_title', { name: recurso.nombre })

  return (
    <Modal open onClose={onClose} title={titulo} width={680}>
      <div className="u-stack-14">
        {libres !== null && (
          <div className={`almf-aviso${libres > 0 ? ' almf-aviso--info' : ' almf-aviso--peligro'}`} role="status">
            {libres > 0 ? t('alm.seats_free', { n: libres }) : t('alm.err_sin_asientos')}
          </div>
        )}
        {recurso.tipo === 'asset' && (
          <GrupoDeOpciones forma="fila" className="almf-titular__tipos" aria-label={t('alm.assign_mode')}
            valor={modo} onChange={v => setModo(v as typeof modo)}
            opciones={(['assignment', 'loan'] as const).map(m => ({ valor: m, titulo: t(`alm.mode_${m}`) }))} />
        )}
        <SelectorDeTitular t={t} tipo={tipo} id={titular} tipos={tipos} idBase={idBase}
          onChange={(k, v) => { setTipo(k); setTitular(v) }} />
        {esBolsa && <p className="alm-hint">{t('alm.pool_hint')}</p>}
        <div className="almf-rejilla-2">
          {pideCantidad && (
            <Input label={esBolsa ? t('alm.pool_seats') : t('alm.quantity')} id={`${idBase}-q`} type="number" min={1} value={cantidad} onChange={e => setCantidad(e.target.value)} />
          )}
          <DateInput label={t('alm.valid_from')} id={`${idBase}-desde`} value={desde} onChange={e => setDesde(e.target.value)} />
          <DateInput label={<>{modo === 'loan' ? t('alm.loan_due') : t('alm.valid_to')}{modo === 'loan' ? ' *' : ''}</>} id={`${idBase}-hasta`} value={hasta} onChange={e => setHasta(e.target.value)} />
          <div className="almf-col-completa">
            <Textarea label={t('alm.reason')} id={`${idBase}-motivo`} rows={2} value={motivo} onChange={e => setMotivo(e.target.value)} placeholder={t('alm.reason_placeholder')} />
          </div>
        </div>

        {conActa && (
          <details className="almf-bloque" open>
            <summary className="almf-bloque__titulo">{t('alm.delivery_act')}</summary>
            <EditorDeChecklist t={t} filas={checklist} onChange={setChecklist} />
            <div className="almf-rejilla-2">
              <Select label={t('alm.assets_label_condition')} placeholder={false} id={`${idBase}-cond`} value={condicion} onChange={e => setCondicion(e.target.value as Condicion | '')}>
                  <option value="">{t('alm.condition_keep')}</option>
                  {(['new', 'good', 'fair', 'poor'] as const).map(c => <option key={c} value={c}>{t(`alm.assets_condition_${c}`)}</option>)}
                </Select>
              <Input label={t('alm.observations')} id={`${idBase}-obs`} value={observaciones} onChange={e => setObservaciones(e.target.value)} />
            </div>
            <p className="alm-hint">{t('alm.delivery_act_hint')}</p>
          </details>
        )}

        <details className="almf-bloque">
          <summary className="almf-bloque__titulo">{t('alm.charge_title')}</summary>
          <p className="alm-hint">{t('alm.charge_hint')}</p>
          <div className="almf-rejilla-2">
            <ProjectSelect label={t('alm.charge_project')} value={cargoProyecto} onChange={v => setCargoProyecto(v)} placeholder={t('alm.charge_auto')} />
            <Select label={t('alm.charge_cost_center')} placeholder={false} id={`${idBase}-cc`} value={cargoCentro} onChange={e => setCargoCentro(e.target.value)}>
                <option value="">{t('alm.charge_auto')}</option>
                {centros.map(c => <option key={c.id} value={c.id}>{c.code} · {c.name}</option>)}
              </Select>
            <ClientSelect label={t('alm.charge_client')} id={`${idBase}-cli`} value={cargoCliente} onChange={v => setCargoCliente(v)} placeholder={t('alm.charge_auto')} />
            <Select label={t('alm.rebillable')} placeholder={false} id={`${idBase}-refa`} value={refacturar} onChange={e => setRefacturar(e.target.value as '' | 'yes' | 'no')}>
                <option value="">{t('alm.rebillable_inherit')}</option>
                <option value="yes">{t('common.yes')}</option>
                <option value="no">{t('common.no')}</option>
              </Select>
          </div>
        </details>

        {error && <p className="u-field-error" role="alert">{error}</p>}
      </div>
      <div className="almf-acciones-modal">
        <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
        <Button onClick={enviar} loading={isPending} disabled={isPending}>
          {modo === 'loan' ? t('alm.lend_confirm') : t('alm.assign_confirm')}
        </Button>
      </div>
    </Modal>
  )
}

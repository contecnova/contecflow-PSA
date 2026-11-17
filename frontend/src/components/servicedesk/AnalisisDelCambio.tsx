/**
 * AnalisisDelCambio — lo que el CAB necesita de un cambio, en su panel
 * (mejoras de mercado 16-11-2026): análisis de impacto con el radio de impacto
 * de la CMDB de cada CI afectado, matriz de riesgo, planes de vuelta atrás, de
 * pruebas y de comunicaciones, simulación «¿y si…?», reunión del CAB y las dos
 * vías directas (aprobación de un administrador y vía rápida de emergencia).
 *
 * Los planes se guardan en el servidor: se lee el último y «Generar» lo rehace.
 * Los permisos los decide el servidor (vía rápida: responsables; aprobación
 * directa: administrador; nunca quien pidió el cambio); aquí solo se ocultan
 * los botones a quien no puede.
 *
 * 16-11-2026 (pasada de diseño): vacíos con icono lucide; fecha de la reunión
 * con DateInput (antes `datetime-local` nativo); «Rechazar» y «vía rápida» ya
 * no usan la variante `danger`, que queda para borrar; textos de ayuda legibles.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarClock, FileText, FlaskConical, Gauge, Megaphone, Radar, RotateCcw, ShieldCheck, Zap } from 'lucide-react'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { useAuth } from '../../context/AuthContext'
import { confirmar } from '../../context/ConfirmContext'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { Button, EmptyState, GrupoDeOpciones, Select, Spinner, StatusBadge, Tabs } from '../ui'
import { usersApi } from '../../services/api'
import { cambiosApi } from '../../services/api/serviceDeskMercado'
import type { WhatIf } from '../../services/api/serviceDeskMercado'
import VistaDeDatos from './VistaDeDatos'
import { etiquetaSd } from '../../pages/service-desk/sdUtils'
import DateInput from '../ui/DateInput'
import './sdMercado.css'

interface CambioMin { id: string; number?: string; status?: string | null; change_type?: string | null; affected_cis?: string[]; requester_id?: string | null }

const ROLES_RESPONSABLES = ['admin', 'pm', 'team_lead', 'hr']

export default function AnalisisDelCambio({ cambio }: { cambio: CambioMin }) {
  const t = useAppT()
  const [vista, setVista] = useState('impacto')
  return (
    <div className="ds-card sdm-card u-mb-16">
      <Tabs active={vista} onChange={setVista} ariaLabel={t('sd_mercado.analisis_cambio')} items={[
        { id: 'impacto', label: t('sd_mercado.chg_impacto'), icon: <Radar size={14} /> },
        { id: 'riesgo', label: t('sd_mercado.chg_riesgo'), icon: <Gauge size={14} /> },
        { id: 'vuelta', label: t('sd_mercado.chg_vuelta'), icon: <RotateCcw size={14} /> },
        { id: 'pruebas', label: t('sd_mercado.chg_pruebas'), icon: <FlaskConical size={14} /> },
        { id: 'comunicaciones', label: t('sd_mercado.chg_comunicaciones'), icon: <Megaphone size={14} /> },
        { id: 'simulacion', label: t('sd_mercado.chg_simulacion'), icon: <Zap size={14} /> },
        { id: 'aprobacion', label: t('sd_mercado.chg_aprobacion'), icon: <ShieldCheck size={14} /> },
      ]} />
      <div className="u-mb-10" />
      {vista === 'impacto' && <Impacto cambio={cambio} />}
      {vista === 'riesgo' && <Matriz cambio={cambio} />}
      {vista === 'vuelta' && <Plan cambio={cambio} clave="vuelta" leer={cambiosApi.vueltaAtras} generar={cambiosApi.generarVueltaAtras} />}
      {vista === 'pruebas' && <Plan cambio={cambio} clave="pruebas" leer={cambiosApi.pruebas} generar={cambiosApi.generarPruebas} />}
      {vista === 'comunicaciones' && <Plan cambio={cambio} clave="comunicaciones" leer={cambiosApi.comunicaciones} generar={cambiosApi.generarComunicaciones} />}
      {vista === 'simulacion' && <Simulacion cambio={cambio} />}
      {vista === 'aprobacion' && <Aprobacion cambio={cambio} />}
    </div>
  )
}

const err404 = (e: unknown) => (e as { response?: { status?: number } })?.response?.status === 404

function Plan({ cambio, clave, leer, generar }: {
  cambio: CambioMin; clave: string
  leer: (id: string) => Promise<Record<string, unknown>>; generar: (id: string) => Promise<Record<string, unknown>>
}) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['sdm-chg', clave, cambio.id], queryFn: () => leer(cambio.id), retry: false })
  const gen = useMutation({
    mutationFn: () => generar(cambio.id),
    onSuccess: d => { qc.setQueryData(['sdm-chg', clave, cambio.id], d); toast.success(t('sd_mercado.plan_generado')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  return (
    <div className="u-stack-10">
      <div className="u-row-end"><Button size="sm" variant="secondary" onClick={() => gen.mutate()} loading={gen.isPending}>{t(q.data ? 'sd_mercado.regenerar' : 'sd_mercado.generar')}</Button></div>
      {q.isLoading ? <Spinner /> : q.data ? <VistaDeDatos datos={q.data} />
        : <EmptyState icon={<FileText size={28} />} title={t(err404(q.error) ? 'sd_mercado.plan_sin_generar' : 'sd_mercado.error_carga')} />}
    </div>
  )
}

function Impacto({ cambio }: { cambio: CambioMin }) {
  const t = useAppT()
  const cis = cambio.affected_cis ?? []
  const [ci, setCi] = useState(cis[0] ?? '')
  const radio = useQuery({ queryKey: ['sdm-blast', ci], queryFn: () => cambiosApi.radioDeImpacto(ci), enabled: !!ci, retry: false })
  return (
    <div className="u-stack-12">
      <Plan cambio={cambio} clave="impacto" leer={cambiosApi.impacto} generar={cambiosApi.analizarImpacto} />
      <div className="ds-eyebrow">{t('sd_mercado.radio_impacto')}</div>
      {cis.length === 0 ? <EmptyState icon={<Radar size={28} />} title={t('sd_mercado.sin_cis')} /> : (
        <>
          <label className="sdm-field"><span>{t('sd_mercado.ci_afectado')}</span>
            <Select suelto placeholder={false} value={ci} onChange={e => setCi(e.target.value)}>
              {cis.map(c => <option key={c} value={c}>{c}</option>)}
            </Select></label>
          {radio.isLoading ? <Spinner size={16} /> : radio.data ? <VistaDeDatos datos={radio.data} /> : <div className="u-text2-xs">{t('sd_mercado.error_carga')}</div>}
        </>
      )}
    </div>
  )
}

function Matriz({ cambio }: { cambio: CambioMin }) {
  const t = useAppT()
  const q = useQuery({ queryKey: ['sdm-chg', 'matriz', cambio.id], queryFn: () => cambiosApi.matrizDeRiesgo(cambio.id), retry: false })
  if (q.isLoading) return <Spinner />
  if (!q.data || q.data.risk_matrix.length === 0) return <EmptyState icon={<Gauge size={28} />} title={t('sd_mercado.matriz_vacia')} />
  return <VistaDeDatos datos={q.data.risk_matrix} />
}

function Simulacion({ cambio }: { cambio: CambioMin }) {
  const t = useAppT()
  const toast = useToast()
  const [f, setF] = useState<{ downtime: string; tipo: string; hora: string; dia: string; quitar: string[] }>({ downtime: '', tipo: '', hora: '', dia: '', quitar: [] })
  const sim = useMutation({
    mutationFn: () => {
      const datos: WhatIf = {}
      if (f.downtime !== '') datos.downtime_minutes = Number(f.downtime)
      if (f.tipo) datos.change_type = f.tipo
      if (f.hora !== '') datos.scheduled_hour_utc = Number(f.hora)
      if (f.dia !== '') datos.scheduled_dow = Number(f.dia)
      if (f.quitar.length) datos.remove_ci_ids = f.quitar
      return cambiosApi.simular(cambio.id, datos)
    },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  return (
    <div className="u-stack-12">
      <div className="u-text2-xs">{t('sd_mercado.simulacion_desc')}</div>
      <div className="sdm-form">
        <label className="sdm-field"><span>{t('sd_mercado.parada_min')}</span><input className="ds-input" type="number" min={0} value={f.downtime} onChange={e => setF({ ...f, downtime: e.target.value })} /></label>
        <label className="sdm-field"><span>{t('sd_mercado.tipo_cambio')}</span>
          <Select suelto placeholder={false} value={f.tipo} onChange={e => setF({ ...f, tipo: e.target.value })}>
            <option value="">{t('sd_mercado.sin_cambiar')}</option>
            {['standard', 'normal', 'emergency'].map(x => <option key={x} value={x}>{etiquetaSd('chg_type', x)}</option>)}
          </Select></label>
        <label className="sdm-field"><span>{t('sd_mercado.hora_utc')}</span><input className="ds-input" type="number" min={0} max={23} value={f.hora} onChange={e => setF({ ...f, hora: e.target.value })} /></label>
        <label className="sdm-field"><span>{t('sd_mercado.dia_semana')}</span>
          <Select suelto placeholder={false} value={f.dia} onChange={e => setF({ ...f, dia: e.target.value })}>
            <option value="">{t('sd_mercado.sin_cambiar')}</option>
            {[0, 1, 2, 3, 4, 5, 6].map(d => <option key={d} value={d}>{t(`sd_mercado.dia_${d}`)}</option>)}
          </Select></label>
      </div>
      {(cambio.affected_cis ?? []).length > 0 && (
        <GrupoDeOpciones tipo="checkbox" forma="lista" className="u-stack-6" leyenda={t('sd_mercado.quitar_cis')} valor={f.quitar}
          onChange={quitar => setF({ ...f, quitar })}
          opciones={(cambio.affected_cis ?? []).map(c => ({ valor: c, titulo: c }))} />
      )}
      <div className="u-row-end"><Button size="sm" onClick={() => sim.mutate()} loading={sim.isPending}>{t('sd_mercado.simular')}</Button></div>
      {sim.data && <VistaDeDatos datos={sim.data} />}
    </div>
  )
}

function Aprobacion({ cambio }: { cambio: CambioMin }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { user } = useAuth()
  const esAdmin = user?.role === 'admin'
  const esResponsable = ROLES_RESPONSABLES.includes(String(user?.role))
  const esSolicitante = !!user?.id && user.id === cambio.requester_id
  const [motivo, setMotivo] = useState('')
  const [justificacion, setJustificacion] = useState('')
  const [aprobadores, setAprobadores] = useState<string[]>([])
  const [reunion, setReunion] = useState({ cuando: '', agenda: '' })
  const usuarios = useQuery({ queryKey: ['users'], queryFn: () => usersApi.list().then(r => r.data), enabled: esResponsable })
  const flujo = useQuery({ queryKey: ['sdm-cab-flujo', cambio.id], queryFn: () => cambiosApi.flujoCab(cambio.id), retry: false })
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['sd-changes'] }); qc.invalidateQueries({ queryKey: ['sd-change-detail', cambio.id] }); qc.invalidateQueries({ queryKey: ['sdm-cab-flujo', cambio.id] }) }
  const err = (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  const directo = useMutation({
    mutationFn: (ok: boolean) => cambiosApi.aprobarDirecto(cambio.id, ok, motivo.trim() || undefined),
    onSuccess: () => { setMotivo(''); refrescar(); toast.success(t('sd_mercado.decision_guardada')) },
    onError: err,
  })
  const rapida = useMutation({
    mutationFn: () => cambiosApi.viaRapida(cambio.id, { approver_ids: aprobadores, justification: justificacion.trim() }),
    onSuccess: () => { setJustificacion(''); setAprobadores([]); refrescar(); toast.success(t('sd_mercado.via_rapida_hecha')) },
    onError: err,
  })
  const programar = useMutation({
    mutationFn: () => cambiosApi.reunionCab(cambio.id, { scheduled_at: new Date(reunion.cuando).toISOString(), agenda: reunion.agenda.trim() }),
    onSuccess: () => { setReunion({ cuando: '', agenda: '' }); refrescar(); toast.success(t('sd_mercado.reunion_programada')) },
    onError: err,
  })
  return (
    <div className="u-stack-12">
      {flujo.data && (
        <div className="ds-card sdm-card"><div className="sdm-card__head">{t('sd_mercado.flujo_cab')}</div><VistaDeDatos datos={flujo.data} /></div>
      )}
      {esResponsable && (
        <div className="ds-card sdm-card">
          <div className="sdm-card__head"><CalendarClock size={14} aria-hidden="true" />{t('sd_mercado.reunion_cab')}</div>
          <div className="sdm-form">
            <label className="sdm-field"><span>{t('sd_mercado.cuando')}</span><DateInput className="ds-input" withTime value={reunion.cuando} onChange={e => setReunion({ ...reunion, cuando: e.target.value })} /></label>
          </div>
          <label className="sdm-field"><span>{t('sd_mercado.agenda')}</span><textarea className="ds-input" rows={2} value={reunion.agenda} onChange={e => setReunion({ ...reunion, agenda: e.target.value })} /></label>
          <div className="u-row-end"><Button size="sm" onClick={() => programar.mutate()} loading={programar.isPending} disabled={!reunion.cuando || reunion.agenda.trim().length < 5}>{t('sd_mercado.programar')}</Button></div>
        </div>
      )}
      {esSolicitante && <div className="u-text2-xs">{t('sd_mercado.no_aprueba_solicitante')}</div>}
      {esAdmin && !esSolicitante && (
        <div className="ds-card sdm-card">
          <div className="sdm-card__head">{t('sd_mercado.aprobacion_directa')}</div>
          <div className="u-text2-xs">{t('sd_mercado.aprobacion_directa_desc')}</div>
          <label className="sdm-field"><span>{t('sd_mercado.motivo')}</span><textarea className="ds-input" rows={2} value={motivo} onChange={e => setMotivo(e.target.value)} /></label>
          <div className="u-actions-8">
            <Button size="sm" variant="secondary" onClick={() => directo.mutate(false)} disabled={directo.isPending || !motivo.trim()}>{t('sd_mercado.rechazar')}</Button>
            <Button size="sm" onClick={async () => { if (await confirmar({ message: t('sd_mercado.aprobar_directo_confirmar', { n: cambio.number || '' }) })) directo.mutate(true) }} disabled={directo.isPending}>{t('sd_mercado.aprobar')}</Button>
          </div>
        </div>
      )}
      {esResponsable && !esSolicitante && (
        <div className="ds-card sdm-card">
          <div className="sdm-card__head"><Zap size={14} aria-hidden="true" />{t('sd_mercado.via_rapida')}</div>
          <div className="u-text2-xs">{t('sd_mercado.via_rapida_desc')}</div>
          <GrupoDeOpciones tipo="checkbox" forma="lista" leyenda={t('sd_mercado.aprobadores')} valor={aprobadores}
            onChange={setAprobadores}
            opciones={(usuarios.data ?? []).filter(u => u.id !== cambio.requester_id).map(u => ({ valor: u.id, titulo: u.full_name }))} />
          <label className="sdm-field"><span>{t('sd_mercado.justificacion')}</span><textarea className="ds-input" rows={2} value={justificacion} onChange={e => setJustificacion(e.target.value)} /></label>
          <div className="u-row-end"><Button size="sm" icon={<Zap size={13} />} onClick={async () => {
            if (await confirmar({ message: t('sd_mercado.via_rapida_confirmar'), danger: true })) rapida.mutate()
          }} loading={rapida.isPending} disabled={aprobadores.length === 0 || justificacion.trim().length < 10}>{t('sd_mercado.via_rapida_btn')}</Button></div>
        </div>
      )}
      {cambio.status && <div className="u-text2-xs">{t('sd_mercado.estado_actual')}: <StatusBadge caps={false}>{etiquetaSd('chg_st', cambio.status)}</StatusBadge></div>}
    </div>
  )
}

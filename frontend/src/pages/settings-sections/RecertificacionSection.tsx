/**
 * Recertificación de accesos (23-11-2026, docs/seguridad/politicas_de_cuenta.md §9).
 *
 * - `Campanas` (pestaña de Seguridad de cuentas, `seguridad.administrar`):
 *   abrir, ver, cerrar (aplicando revocaciones) y exportar con sus evidencias.
 * - Por defecto (sección «Recertificación de accesos», `seguridad.recertificar`):
 *   lo que me toca revisar; cada decisión lleva un comentario obligatorio.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, ShieldCheck } from 'lucide-react'
import { Button, Input, Section, Spinner, StatusBadge, Tabla, type ColumnaTabla } from '../../components/ui'
import { confirmar, pedirTexto } from '../../context/ConfirmContext'
import { useToast } from '../../context/ToastContext'
import { useAppLang } from '../../i18n/AppLangContext'
import { extractErr, fmtDate, fmtDateTime } from '../../utils/helpers'
import {
  seguridadApi, type Campana, type DecisionDeAcceso, type ElementoDeRevision,
} from '../../services/api/seguridadDeCuentas'
import SeccionDeAjustes from './SeccionDeAjustes'
import './SeguridadDeCuentasSection.css'

const TONO: Record<DecisionDeAcceso, 'neutral' | 'success' | 'danger' | 'warning'> = {
  pending: 'neutral', keep: 'success', revoke: 'danger', modify: 'warning',
}

function useDecidir(campana: string, alTerminar: () => void) {
  const { t } = useAppLang()
  const toast = useToast()
  return async (e: ElementoDeRevision, decision: DecisionDeAcceso) => {
    const comentario = await pedirTexto({
      title: t(`seguridad_cuentas.decision_${decision}`), message: t('seguridad_cuentas.evidencia_d', { nombre: e.user ?? '' }),
      label: t('seguridad_cuentas.evidencia'), required: true, multiline: true,
    })
    if (comentario === null) return
    try {
      await seguridadApi.decidir(campana, e.id, decision, comentario)
      toast.success(t('seguridad_cuentas.hecho'))
      alTerminar()
    } catch (err) { toast.error(extractErr(err, t('seguridad_cuentas.err_accion'))) }
  }
}

function TablaDeElementos({ campana, filas, cargando, abierta, alTerminar }: {
  campana: string; filas: ElementoDeRevision[]; cargando?: boolean; abierta: boolean; alTerminar: () => void
}) {
  const { t } = useAppLang()
  const decidir = useDecidir(campana, alTerminar)
  const columnas: ColumnaTabla<ElementoDeRevision>[] = [
    { key: 'user', label: t('seguridad_cuentas.col_usuario'), sortable: true,
      render: (_: never, e) => <span>{e.user}<br /><span className="segc-tenue">{e.email}</span></span> },
    { key: 'rol', label: t('seguridad_cuentas.col_rol'), render: (_: never, e) => e.snapshot.role ?? '—' },
    { key: 'privilegios', label: t('seguridad_cuentas.col_privilegios'),
      render: (_: never, e) => (e.snapshot.sensitive_capabilities ?? []).join(', ') || '—' },
    { key: 'mfa', label: 'MFA', render: (_: never, e) => e.snapshot.mfa ? t('seguridad_cuentas.si') : t('seguridad_cuentas.no') },
    { key: 'last', label: t('seguridad_cuentas.col_ultimo_acceso'), render: (_: never, e) => fmtDate(e.snapshot.last_login ?? null) },
    { key: 'reviewer', label: t('seguridad_cuentas.col_responsable') },
    { key: 'decision', label: t('seguridad_cuentas.col_decision'),
      render: (_: never, e) => <span><StatusBadge kind={TONO[e.decision]}>{t(`seguridad_cuentas.decision_${e.decision}`)}</StatusBadge>
        {e.comment && <><br /><span className="segc-tenue">{e.comment}</span></>}</span> },
    { key: 'acciones', label: t('seguridad_cuentas.col_acciones'),
      render: (_: never, e) => !abierta ? fmtDateTime(e.decided_at) : (
        <div className="segc-acciones">
          {(['keep', 'modify', 'revoke'] as DecisionDeAcceso[]).map(d => (
            <Button key={d} size="sm" variant={d === 'revoke' ? 'danger' : 'secondary'} onClick={() => decidir(e, d)}>
              {t(`seguridad_cuentas.decision_${d}`)}
            </Button>
          ))}
        </div>
      ) },
  ]
  return <Tabla etiqueta={t('seguridad_cuentas.p_recertificacion')} columnas={columnas} filas={filas} cargando={cargando} ordenable />
}

function descargar(nombre: string, datos: Blob) {
  const url = URL.createObjectURL(datos)
  const a = document.createElement('a')
  a.href = url
  a.download = nombre
  a.click()
  URL.revokeObjectURL(url)
}

/** Campañas (administración). */
export function Campanas() {
  const { t } = useAppLang()
  const qc = useQueryClient()
  const toast = useToast()
  const [nombre, setNombre] = useState('')
  const [vence, setVence] = useState('')
  const [abierta, setAbierta] = useState<Campana | null>(null)
  const q = useQuery({ queryKey: ['seguridad-campanas'], queryFn: seguridadApi.campanas })
  const elementos = useQuery({
    queryKey: ['seguridad-campana', abierta?.id], queryFn: () => seguridadApi.elementos(abierta!.id), enabled: !!abierta,
  })
  const refrescar = () => {
    qc.invalidateQueries({ queryKey: ['seguridad-campanas'] })
    qc.invalidateQueries({ queryKey: ['seguridad-campana'] })
  }
  const abrir = useMutation({
    mutationFn: () => seguridadApi.abrirCampana(nombre, vence || undefined),
    onSuccess: () => { setNombre(''); setVence(''); toast.success(t('seguridad_cuentas.hecho')); refrescar() },
    onError: e => toast.error(extractErr(e, t('seguridad_cuentas.err_accion'))),
  })
  const cerrar = async (c: Campana) => {
    const aplicar = await confirmar({ title: t('seguridad_cuentas.a_cerrar_campana'), message: t('seguridad_cuentas.confirmar_cerrar', { n: c.pending }),
      confirmLabel: t('seguridad_cuentas.cerrar_y_revocar'), danger: true })
    try {
      const r = await seguridadApi.cerrarCampana(c.id, aplicar)
      toast.success(t('seguridad_cuentas.campana_cerrada', { n: r.deactivated.length }))
      setAbierta(null)
      refrescar()
    } catch (e) { toast.error(extractErr(e, t('seguridad_cuentas.err_accion'))) }
  }
  const exportar = async (c: Campana, formato: 'csv' | 'json') => {
    try { descargar(`access-review-${c.id.slice(0, 8)}.${formato}`, await seguridadApi.exportarCampana(c.id, formato)) }
    catch (e) { toast.error(extractErr(e, t('seguridad_cuentas.err_accion'))) }
  }
  const columnas: ColumnaTabla<Campana>[] = [
    { key: 'name', label: t('seguridad_cuentas.col_campana'), sortable: true },
    { key: 'status', label: t('seguridad_cuentas.col_estado'),
      render: (_: never, c) => <StatusBadge kind={c.status === 'open' ? 'warning' : 'success'}>{t(`seguridad_cuentas.campana_${c.status}`)}</StatusBadge> },
    { key: 'pending', label: t('seguridad_cuentas.col_pendientes'), render: (_: never, c) => `${c.pending} / ${c.items}` },
    { key: 'due_at', label: t('seguridad_cuentas.col_vence'), render: (_: never, c) => fmtDate(c.due_at) },
    { key: 'closed_at', label: t('seguridad_cuentas.col_cierre'), render: (_: never, c) => fmtDate(c.closed_at) },
    { key: 'acciones', label: t('seguridad_cuentas.col_acciones'),
      render: (_: never, c) => (
        <div className="segc-acciones">
          <Button size="sm" variant="secondary" onClick={() => setAbierta(c)}>{t('seguridad_cuentas.a_ver')}</Button>
          {c.status === 'open' && <Button size="sm" variant="secondary" onClick={() => cerrar(c)}>{t('seguridad_cuentas.a_cerrar_campana')}</Button>}
          <Button size="sm" variant="ghost" icon={<Download size={14} />} onClick={() => exportar(c, 'csv')}>CSV</Button>
          <Button size="sm" variant="ghost" icon={<Download size={14} />} onClick={() => exportar(c, 'json')}>JSON</Button>
        </div>
      ) },
  ]
  return (
    <div>
      <Section title={t('seguridad_cuentas.nueva_campana')} subtitle={t('seguridad_cuentas.nueva_campana_d')}>
        <div className="segc-campos">
          <Input label={t('seguridad_cuentas.col_campana')} value={nombre} maxLength={200} onChange={e => setNombre(e.target.value)} />
          <Input label={t('seguridad_cuentas.col_vence')} type="date" value={vence} onChange={e => setVence(e.target.value)} />
        </div>
        <Button disabled={!nombre.trim()} loading={abrir.isPending} onClick={() => abrir.mutate()}>{t('seguridad_cuentas.a_abrir_campana')}</Button>
      </Section>
      <Tabla etiqueta={t('seguridad_cuentas.p_recertificacion')} columnas={columnas} filas={q.data ?? []} cargando={q.isLoading} />
      {abierta && (
        <Section title={abierta.name}>
          <TablaDeElementos campana={abierta.id} filas={elementos.data ?? []} cargando={elementos.isLoading}
            abierta={abierta.status === 'open'} alTerminar={refrescar} />
        </Section>
      )}
    </div>
  )
}

/** Lo que me toca revisar (responsables). */
export default function RecertificacionSection() {
  const { t } = useAppLang()
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['seguridad-mis-revisiones'], queryFn: seguridadApi.misRevisiones })
  const refrescar = () => qc.invalidateQueries({ queryKey: ['seguridad-mis-revisiones'] })
  return (
    <SeccionDeAjustes icon={<ShieldCheck size={18} />} title={t('seguridad_cuentas.mis_revisiones')}
      description={t('seguridad_cuentas.mis_revisiones_d')}>
      {q.isLoading && <Spinner label={t('seguridad_cuentas.cargando')} />}
      {!q.isLoading && (q.data ?? []).length === 0 && <p className="segc-tenue">{t('seguridad_cuentas.sin_revisiones')}</p>}
      {(q.data ?? []).map(g => (
        <Section key={g.campaign.id} title={g.campaign.name}
          subtitle={g.campaign.due_at ? t('seguridad_cuentas.vence_el', { fecha: fmtDate(g.campaign.due_at) }) : undefined}>
          <TablaDeElementos campana={g.campaign.id} filas={g.items} abierta alTerminar={refrescar} />
        </Section>
      ))}
    </SeccionDeAjustes>
  )
}

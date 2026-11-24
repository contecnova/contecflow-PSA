/**
 * Mis equipos y licencias — autoservicio de cada persona (licencias y hardware, fase 4).
 *
 * Lo que tengo (con fechas de préstamo y devolución), pedir una licencia o un
 * equipo (va al catálogo del service desk, con su aprobación), devolver,
 * comunicar una avería (ticket enlazado al equipo) y ver y firmar mis actas.
 * Todo viene acotado a quien pregunta: un subcontratado solo ve lo suyo.
 *
 * 16-11-2026: título = el del menú; KPIs en .ds-grid-stats como el resto;
 * fecha del préstamo con DateInput; vacíos del historial con icono lucide.
 */
import { useState } from 'react'
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query'
import { AlertTriangle, FileSignature, History, KeyRound, Laptop, PackagePlus, Send, Undo2, Wrench } from 'lucide-react'
import { almIntegracionApi } from '../services/api/almIntegracion'
import type { MiEquipo, MiLicencia, Peticion, Devolucion, HistorialPropio, ActaResumen } from '../services/api/almIntegracion'
import { Button, DataTable, EmptyState, KpiCard, Modal, Page, Select, Spinner, Tabs, useErroresDeCampo, Textarea } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'
import { useToast } from '../context/ToastContext'
import { fmtDate } from '../utils/helpers'
import { sanitizeUrl } from '../utils/security'
import DateInput from '../components/ui/DateInput'
import { Estado, etiqueta, mensajeDeError } from '../components/alm/almComun'
import '../components/alm/almIntegracion.css'

type Accion = { tipo: 'pedir'; que: 'licencia' | 'equipo' } | { tipo: 'averia'; equipo: MiEquipo }
  | { tipo: 'devolver'; equipo: MiEquipo } | { tipo: 'dejar'; licencia: MiLicencia } | { tipo: 'acta'; id: string }

export default function MisEquiposPage() {
  const t = useAppT()
  const [tab, setTab] = useState('equipos')
  const [accion, setAccion] = useState<Accion | null>(null)
  const q = useQuery({ queryKey: ['alm-mio'], queryFn: almIntegracionApi.mio })
  const opciones = useQuery({ queryKey: ['alm-mio', 'opciones'], queryFn: almIntegracionApi.opciones })
  const d = q.data
  const abiertas = (d?.peticiones ?? []).filter(p => ['pendiente', 'en_compra'].includes(p.estado)).length
  return (
    <Page icon={<Laptop size={18} />} title={t('nav.my_equipment')} subtitle={t('almint.mio_sub')}
      actions={<div className="almint-acciones">
        {opciones.data?.puede_pedir_licencia && <Button variant="secondary" icon={<KeyRound size={14} />}
          onClick={() => setAccion({ tipo: 'pedir', que: 'licencia' })}>{t('almint.pedir_licencia')}</Button>}
        {opciones.data?.puede_pedir_equipo && <Button icon={<PackagePlus size={14} />}
          onClick={() => setAccion({ tipo: 'pedir', que: 'equipo' })}>{t('almint.pedir_equipo')}</Button>}
      </div>}>
      {q.isLoading ? <Spinner /> : q.isError ? <EmptyState icon={<AlertTriangle size={28} />} title={mensajeDeError(t, q.error)} /> : d && <>
        <div className="ds-grid-stats">
          <KpiCard icon={<Laptop size={16} />} label={t('almint.kpi_equipos')} value={d.equipos.length}
            sub={d.equipos.some(e => e.overdue) ? t('almint.kpi_prestamo_vencido') : undefined} danger={d.equipos.some(e => e.overdue)} />
          <KpiCard icon={<KeyRound size={16} />} label={t('almint.kpi_licencias')} value={d.licencias.length} />
          <KpiCard icon={<FileSignature size={16} />} label={t('almint.kpi_actas')} value={d.actas_pendientes.length} warning={d.actas_pendientes.length > 0} />
          <KpiCard icon={<Send size={16} />} label={t('almint.kpi_peticiones')} value={abiertas} />
        </div>
        <Tabs active={tab} onChange={setTab} ariaLabel={t('almint.mio_titulo')} items={[
          { id: 'equipos', label: t('almint.tab_equipos'), count: d.equipos.length, icon: <Laptop size={14} /> },
          { id: 'licencias', label: t('almint.tab_licencias'), count: d.licencias.length, icon: <KeyRound size={14} /> },
          { id: 'actas', label: t('almint.tab_actas'), count: d.actas_pendientes.length, icon: <FileSignature size={14} /> },
          { id: 'peticiones', label: t('almint.tab_peticiones'), count: d.peticiones.length, icon: <Send size={14} /> },
          { id: 'historial', label: t('almint.tab_historial'), icon: <History size={14} /> },
        ]} />
        <div className="almint-panel">
          {tab === 'equipos' && <Equipos filas={d.equipos} onAccion={setAccion} />}
          {tab === 'licencias' && <Licencias filas={d.licencias} onAccion={setAccion} />}
          {tab === 'actas' && <Actas filas={d.actas_pendientes} onAccion={setAccion} />}
          {tab === 'peticiones' && <Peticiones filas={d.peticiones} onAccion={setAccion}
            licencia={Boolean(opciones.data?.puede_pedir_licencia)} equipo={Boolean(opciones.data?.puede_pedir_equipo)} />}
          {tab === 'historial' && <Historial filas={d.historial} devoluciones={d.devoluciones} />}
        </div>
      </>}
      {accion?.tipo === 'pedir' && <PedirModal que={accion.que} onClose={() => setAccion(null)} />}
      {accion?.tipo === 'averia' && <AveriaModal equipo={accion.equipo} onClose={() => setAccion(null)} />}
      {(accion?.tipo === 'devolver' || accion?.tipo === 'dejar') && <MotivoModal accion={accion} onClose={() => setAccion(null)} />}
      {accion?.tipo === 'acta' && <ActaModal id={accion.id} onClose={() => setAccion(null)} />}
    </Page>
  )
}

function Equipos({ filas, onAccion }: { filas: MiEquipo[]; onAccion: (a: Accion) => void }) {
  const t = useAppT()
  if (!filas.length) return <EmptyState icon={<Laptop size={28} />} title={t('almint.sin_equipos')} description={t('almint.sin_equipos_desc')} />
  return (
    <div className="almint-lista">
      {filas.map(e => (
        <div key={e.assignment_id} className="ds-card almint-ficha">
          <div className="almint-ficha-cab">
            <div className="almint-ficha-titulo">
              <strong>{e.name}</strong>
              <span className="almint-tenue">{[etiqueta(t, 'tipo_equipo', e.type), e.brand, e.model].filter(Boolean).join(' · ')}</span>
              <span className="almint-tenue">{[e.asset_tag, e.serial_number].filter(Boolean).join(' · ')}</span>
            </div>
            <div className="almint-pastillas">
              <Estado t={t} codigo={e.mode === 'loan' ? 'prestamo' : 'asignado'} />
              {e.overdue && <Estado t={t} codigo="vencido" />}
              {e.devolucion && <Estado t={t} codigo={`devolucion_${e.devolucion.estado}`} />}
            </div>
          </div>
          <dl className="almint-datos">
            <div><dt>{t('almint.desde')}</dt><dd>{fmtDate(e.valid_from)}</dd></div>
            <div><dt>{e.mode === 'loan' ? t('almint.devolver_antes_de') : t('almint.hasta')}</dt><dd>{fmtDate(e.valid_to)}</dd></div>
            {e.devolucion?.fecha_limite && <div><dt>{t('almint.fecha_limite_devolucion')}</dt><dd>{fmtDate(e.devolucion.fecha_limite)}</dd></div>}
            {e.devolucion?.ticket && <div><dt>{t('almint.ticket')}</dt><dd>{e.devolucion.ticket.number}</dd></div>}
          </dl>
          {e.averias_abiertas.length > 0 && <p className="almint-aviso">{t('almint.averias_abiertas', { n: e.averias_abiertas.length, tickets: e.averias_abiertas.map(a => a.number).join(', ') })}</p>}
          <div className="almint-acciones">
            {e.acta_entrega?.status === 'pending_signature' && <Button size="sm" icon={<FileSignature size={14} />} onClick={() => onAccion({ tipo: 'acta', id: e.acta_entrega!.id })}>{t('almint.firmar_entrega')}</Button>}
            <Button size="sm" variant="secondary" icon={<Wrench size={14} />} onClick={() => onAccion({ tipo: 'averia', equipo: e })}>{t('almint.comunicar_averia')}</Button>
            {!e.devolucion && <Button size="sm" variant="ghost" icon={<Undo2 size={14} />} onClick={() => onAccion({ tipo: 'devolver', equipo: e })}>{t('almint.devolver')}</Button>}
          </div>
        </div>
      ))}
    </div>
  )
}

function Licencias({ filas, onAccion }: { filas: MiLicencia[]; onAccion: (a: Accion) => void }) {
  const t = useAppT()
  return <DataTable<MiLicencia> data={filas} emptyIcon={<KeyRound size={28} />} emptyTitle={t('almint.sin_licencias')} columns={[
    { key: 'name', label: t('almint.col_licencia'), render: (_v, f) => <span><strong>{f.name}</strong>{f.product_name && f.product_name !== f.name ? <span className="almint-tenue"> · {f.product_name}</span> : null}</span> },
    { key: 'status', label: t('almint.col_estado'), render: (_v, f) => <Estado t={t} codigo={f.status} /> },
    { key: 'from_pool', label: t('almint.col_origen'), render: (_v, f) => f.from_pool ? t('almint.de_la_bolsa') : etiqueta(t, 'fuente', f.source) },
    { key: 'valid_from', label: t('almint.desde'), render: (_v, f) => fmtDate(f.valid_from) },
    { key: 'valid_to', label: t('almint.hasta'), render: (_v, f) => fmtDate(f.valid_to) },
    { key: 'acciones', label: '', sortable: false, render: (_v, f) => f.status === 'active'
      ? <Button size="xs" variant="ghost" onClick={() => onAccion({ tipo: 'dejar', licencia: f })}>{t('almint.ya_no_la_necesito')}</Button> : null },
  ]} />
}

function Actas({ filas, onAccion }: { filas: ActaResumen[]; onAccion: (a: Accion) => void }) {
  const t = useAppT()
  return <DataTable<ActaResumen> data={filas} emptyIcon={<FileSignature size={28} />} emptyTitle={t('almint.sin_actas')} columns={[
    { key: 'kind', label: t('almint.col_acta'), render: (_v, f) => etiqueta(t, 'tipo_acta', f.kind) },
    { key: 'asset_name', label: t('almint.col_equipo') },
    { key: 'created_at', label: t('almint.col_fecha'), render: (_v, f) => fmtDate(f.created_at) },
    { key: 'acciones', label: '', sortable: false, render: (_v, f) => <Button size="xs" icon={<FileSignature size={12} />} onClick={() => onAccion({ tipo: 'acta', id: f.id })}>{t('almint.ver_y_firmar')}</Button> },
  ]} />
}

/** 19-11-2026: sin peticiones, el estado vacío explica y ofrece pedir (antes era una pantalla sin salida). */
function Peticiones({ filas, onAccion, licencia, equipo }: { filas: Peticion[]; onAccion: (a: Accion) => void; licencia: boolean; equipo: boolean }) {
  const t = useAppT()
  if (filas.length === 0) {
    return <EmptyState icon={<Send size={28} />} title={t('almint.sin_peticiones')} description={t('almint.sin_peticiones_ayuda')}
      action={<div className="almint-acciones">
        {licencia && <Button variant="secondary" icon={<KeyRound size={14} />} onClick={() => onAccion({ tipo: 'pedir', que: 'licencia' })}>{t('almint.pedir_licencia')}</Button>}
        {equipo && <Button icon={<PackagePlus size={14} />} onClick={() => onAccion({ tipo: 'pedir', que: 'equipo' })}>{t('almint.pedir_equipo')}</Button>}
      </div>} />
  }
  return <DataTable<Peticion> data={filas} emptyIcon={<Send size={28} />} emptyTitle={t('almint.sin_peticiones')} columns={[
    { key: 'tipo', label: t('almint.col_que'), render: (_v, f) => f.tipo === 'licencia' ? f.license_name : etiqueta(t, 'tipo_equipo', f.asset_type) },
    { key: 'estado', label: t('almint.col_estado'), render: (_v, f) => <span className="almint-pastillas"><Estado t={t} codigo={f.estado} />{f.aprobacion === 'pending' && <Estado t={t} codigo="en_aprobacion" />}</span> },
    { key: 'ticket', label: t('almint.ticket'), render: (_v, f) => f.ticket ? `${f.ticket.number}` : '—' },
    { key: 'compra', label: t('almint.col_compra'), render: (_v, f) => f.compra ? f.compra.number : '—' },
    { key: 'created_at', label: t('almint.col_fecha'), render: (_v, f) => fmtDate(f.created_at) },
  ]} />
}

function Historial({ filas, devoluciones }: { filas: HistorialPropio[]; devoluciones: Devolucion[] }) {
  const t = useAppT()
  return <div className="almint-lista">
    <h3 className="almint-subtitulo">{t('almint.devoluciones')}</h3>
    <DataTable<Devolucion> data={devoluciones} emptyIcon={<Undo2 size={28} />} emptyTitle={t('almint.sin_devoluciones')} columns={[
      { key: 'asset_name', label: t('almint.col_equipo') },
      { key: 'estado', label: t('almint.col_estado'), render: (_v, f) => <Estado t={t} codigo={f.estado} /> },
      { key: 'ticket', label: t('almint.ticket'), render: (_v, f) => f.ticket?.number ?? '—' },
      { key: 'created_at', label: t('almint.col_fecha'), render: (_v, f) => fmtDate(f.created_at) },
    ]} />
    <h3 className="almint-subtitulo">{t('almint.lo_que_tuve')}</h3>
    <DataTable<HistorialPropio> data={filas} emptyIcon={<History size={28} />} emptyTitle={t('almint.sin_historial')} columns={[
      { key: 'name', label: t('almint.col_recurso') },
      { key: 'status', label: t('almint.col_estado'), render: (_v, f) => <Estado t={t} codigo={f.end_kind || f.status} /> },
      { key: 'valid_from', label: t('almint.desde'), render: (_v, f) => fmtDate(f.valid_from) },
      { key: 'ended_on', label: t('almint.hasta'), render: (_v, f) => fmtDate(f.ended_on) },
    ]} />
  </div>
}

function useRefrescar() {
  const qc = useQueryClient()
  return () => qc.invalidateQueries({ queryKey: ['alm-mio'] })
}

function PedirModal({ que, onClose }: { que: 'licencia' | 'equipo'; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const refrescar = useRefrescar()
  const opciones = useQuery({ queryKey: ['alm-mio', 'opciones'], queryFn: almIntegracionApi.opciones })
  const [f, setF] = useState({ license_id: '', asset_type: '', motivo: '', hasta: '' })
  const camposB = useErroresDeCampo()
  const msgB = (k: string) => camposB.de(k) ? <div className="u-field-error">{camposB.de(k)}</div> : null
  const m = useMutation({
    onMutate: () => camposB.limpiar(),
    mutationFn: () => almIntegracionApi.pedir({ tipo: que, license_id: f.license_id || undefined, asset_type: f.asset_type || undefined,
      motivo: f.motivo || undefined, hasta: f.hasta || undefined }),
    onSuccess: () => { toast.success(t('almint.peticion_enviada')); refrescar(); onClose() },
    onError: (e: unknown) => { if (!camposB.recoger(e)) toast.error(mensajeDeError(t, e)) },
  })
  const listo = que === 'licencia' ? !!f.license_id : !!f.asset_type
  return (
    <Modal open onClose={onClose} title={que === 'licencia' ? t('almint.pedir_licencia') : t('almint.pedir_equipo')} subtitle={t('almint.pedir_sub')}>
      <div className="almint-form">
        {que === 'licencia'
          ? <Select error={camposB.de('license_id')} label={t('almint.col_licencia')} value={f.license_id} onChange={e => setF({ ...f, license_id: e.target.value })}
              options={(opciones.data?.licencias ?? []).map(l => ({ value: l.id, label: l.product_name && l.product_name !== l.name ? `${l.name} · ${l.product_name}` : l.name }))} />
          : <Select error={camposB.de('asset_type')} label={t('almint.tipo_de_equipo')} value={f.asset_type} onChange={e => setF({ ...f, asset_type: e.target.value })}
              options={(opciones.data?.tipos_de_equipo ?? []).map(v => ({ value: v, label: etiqueta(t, 'tipo_equipo', v) }))} />}
        {que === 'equipo' && <div className="almint-campo">
          <DateInput label={t('almint.prestamo_hasta')} value={f.hasta} onChange={e => setF({ ...f, hasta: e.target.value })} />{msgB('hasta')}
          <span className="almint-tenue">{t('almint.prestamo_hasta_ayuda')}</span></div>}
        <div className="almint-campo"><Textarea label={t('almint.motivo')} rows={3} value={f.motivo} onChange={e => setF({ ...f, motivo: e.target.value })} />{msgB('motivo')}</div>
        <div className="almint-acciones almint-acciones--fin">
          <Button variant="ghost" onClick={onClose}>{t('common.cancel')}</Button>
          <Button icon={<Send size={14} />} disabled={!listo} loading={m.isPending} onClick={() => m.mutate()}>{t('almint.enviar_peticion')}</Button>
        </div>
      </div>
    </Modal>
  )
}

const URGENCIAS = ['low', 'medium', 'high', 'critical']

function AveriaModal({ equipo, onClose }: { equipo: MiEquipo; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const refrescar = useRefrescar()
  const [descripcion, setDescripcion] = useState('')
  const [urgencia, setUrgencia] = useState('medium')
  const m = useMutation({
    mutationFn: () => almIntegracionApi.averia(equipo.assignment_id, descripcion, urgencia),
    onSuccess: r => { toast.success(t('almint.averia_enviada', { ticket: r.number })); refrescar(); onClose() },
    onError: e => toast.error(mensajeDeError(t, e)),
  })
  return (
    <Modal open onClose={onClose} title={t('almint.comunicar_averia')} subtitle={equipo.name ?? undefined}>
      <div className="almint-form">
        <Textarea label={t('almint.que_le_pasa')} rows={4} value={descripcion} onChange={e => setDescripcion(e.target.value)} />
        <Select label={t('almint.urgencia_label')} value={urgencia} onChange={e => setUrgencia(e.target.value)}
          options={URGENCIAS.map(u => ({ value: u, label: etiqueta(t, 'urgencia', u) }))} />
        <div className="almint-acciones almint-acciones--fin">
          <Button variant="ghost" onClick={onClose}>{t('common.cancel')}</Button>
          <Button icon={<Wrench size={14} />} disabled={!descripcion.trim() || !urgencia} loading={m.isPending} onClick={() => m.mutate()}>{t('almint.abrir_ticket')}</Button>
        </div>
      </div>
    </Modal>
  )
}

function MotivoModal({ accion, onClose }: { accion: Extract<Accion, { tipo: 'devolver' | 'dejar' }>; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const refrescar = useRefrescar()
  const [motivo, setMotivo] = useState('')
  const devolver = accion.tipo === 'devolver'
  const m = useMutation({
    // Devolver abre una `Devolucion`; dejar la licencia solo responde `{ ok }`: el resultado no se usa.
    mutationFn: async (): Promise<void> => {
      if (devolver) await almIntegracionApi.devolver(accion.equipo.assignment_id, motivo || undefined)
      else await almIntegracionApi.dejar(accion.licencia.assignment_id, motivo || undefined)
    },
    onSuccess: () => { toast.success(devolver ? t('almint.devolucion_abierta') : t('almint.licencia_liberada')); refrescar(); onClose() },
    onError: e => toast.error(mensajeDeError(t, e)),
  })
  return (
    <Modal open onClose={onClose} title={devolver ? t('almint.devolver') : t('almint.ya_no_la_necesito')}
      subtitle={devolver ? accion.equipo.name ?? undefined : accion.licencia.name ?? undefined}>
      <div className="almint-form">
        <p className="almint-tenue">{devolver ? t('almint.devolver_explicacion') : t('almint.dejar_explicacion')}</p>
        <Textarea label={t('almint.motivo')} rows={3} value={motivo} onChange={e => setMotivo(e.target.value)} />
        <div className="almint-acciones almint-acciones--fin">
          <Button variant="ghost" onClick={onClose}>{t('common.cancel')}</Button>
          <Button variant={devolver ? 'primary' : 'danger'} loading={m.isPending} onClick={() => m.mutate()}>{devolver ? t('almint.devolver') : t('almint.liberar')}</Button>
        </div>
      </div>
    </Modal>
  )
}

function ActaModal({ id, onClose }: { id: string; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const refrescar = useRefrescar()
  const q = useQuery({ queryKey: ['alm-mio', 'acta', id], queryFn: () => almIntegracionApi.verActa(id) })
  const m = useMutation({
    mutationFn: () => almIntegracionApi.firmarActa(id),
    onSuccess: () => { toast.success(t('almint.acta_firmada')); refrescar(); onClose() },
    onError: e => toast.error(mensajeDeError(t, e)),
  })
  const a = q.data
  return (
    <Modal open onClose={onClose} size="lg" title={a ? etiqueta(t, 'tipo_acta', a.kind) : t('almint.tab_actas')} subtitle={a?.asset_name ?? undefined}>
      {q.isLoading ? <Spinner /> : q.isError ? <p className="almint-aviso">{mensajeDeError(t, q.error)}</p> : a && (
        <div className="almint-form">
          <div className="almint-pastillas"><Estado t={t} codigo={a.status} />{a.condition && <span className="almint-tenue">{etiqueta(t, 'condicion', a.condition)}</span>}</div>
          {(a.checklist ?? []).length > 0 && <ul className="almint-checklist">
            {(a.checklist ?? []).map((c, i) => <li key={i} className={c.ok ? 'almint-ok' : 'almint-ko'}>{c.item}{c.note ? ` · ${c.note}` : ''}</li>)}
          </ul>}
          {a.observations && <p>{a.observations}</p>}
          {a.pdf_url && <a className="almint-enlace" href={sanitizeUrl(a.pdf_url)} target="_blank" rel="noreferrer">{t('almint.ver_pdf')}</a>}
          {a.esign_provider && a.esign_provider !== 'manual' && a.status === 'pending_signature' && <p className="almint-tenue">{t('almint.firma_externa')}</p>}
          <div className="almint-acciones almint-acciones--fin">
            <Button variant="ghost" onClick={onClose}>{t('common.close')}</Button>
            {a.status === 'pending_signature' && (!a.esign_provider || a.esign_provider === 'manual') &&
              <Button icon={<FileSignature size={14} />} loading={m.isPending} onClick={() => m.mutate()}>{t('almint.firmar')}</Button>}
          </div>
        </div>
      )}
    </Modal>
  )
}

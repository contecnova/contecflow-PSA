/**
 * Altas y bajas de licencias y equipos (licencias y hardware, fase 4).
 *
 * - Bajas: el expediente de cada baja (manual, SCIM, fin de contrato o
 *   programada) con sus licencias y sus devoluciones hasta el acta firmada.
 * - Devoluciones: registrar que el equipo ha vuelto (acta de devolución) o
 *   darlo por perdido.
 * - Kits propuestos: confirmar con un clic el kit de alta de cada persona.
 * - Kits: qué licencias y equipos tocan por rol, puesto, departamento o equipo.
 * - Catálogo y peticiones: los ítems «Pedir licencia» y «Pedir equipo» y lo
 *   que se ha pedido (con su aprobación y su compra si no había).
 */
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Boxes, CalendarClock, ClipboardCheck, KeyRound, Laptop, ListChecks, PackageCheck, Plus, Send, Trash2, UserMinus } from 'lucide-react'
import { almIntegracionApi } from '../services/api/almIntegracion'
import type { Baja, Devolucion, ElementoDeKit, ItemDeCatalogoAlm, Kit, Peticion, PropuestaDeKit } from '../services/api/almIntegracion'
import { licensesApi, sdCatalogApi, usersApi } from '../services/api'
import { Button, DataTable, EmptyState, KpiCard, Modal, Page, Select, Spinner, Tabs, Pulsable, Checkbox, useErroresDeCampo, Textarea, Input } from '../components/ui'
import DateInput from '../components/ui/DateInput'
import { useAppT } from '../i18n/AppLangContext'
import { useToast } from '../context/ToastContext'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useAuth } from '../context/AuthContext'
import { fmtDate } from '../utils/helpers'
import { Estado, etiqueta, mensajeDeError } from '../components/alm/almComun'
import '../components/alm/almIntegracion.css'

const TIPOS_DE_EQUIPO = ['laptop', 'desktop', 'server', 'mobile', 'tablet', 'network', 'printer', 'monitor', 'peripheral', 'vm', 'other']
const CRITERIOS = ['todos', 'rol', 'puesto', 'departamento', 'equipo']
const CONDICIONES = ['new', 'good', 'fair', 'poor']

export default function ALMAltasBajasPage() {
  const t = useAppT()
  const { puede } = useAuth()
  const gestionaPersonas = puede('alm.personas')
  const configura = puede('alm.configurar')
  const esAdmin = puede('org.administrar')
  const [params, setParams] = useSearchParams()
  const pestanas = [
    gestionaPersonas && { id: 'bajas', label: t('almint.tab_bajas'), icon: <UserMinus size={14} /> },
    { id: 'devoluciones', label: t('almint.tab_devoluciones'), icon: <PackageCheck size={14} /> },
    { id: 'kits_propuestos', label: t('almint.tab_propuestas'), icon: <ClipboardCheck size={14} /> },
    gestionaPersonas && { id: 'kits', label: t('almint.tab_kits'), icon: <Boxes size={14} /> },
    { id: 'peticiones', label: t('almint.tab_peticiones_gestion'), icon: <Send size={14} /> },
    { id: 'catalogo', label: t('almint.tab_catalogo'), icon: <ListChecks size={14} /> },
  ].filter(Boolean) as { id: string; label: string; icon: JSX.Element }[]
  const tab = pestanas.some(p => p.id === params.get('tab')) ? String(params.get('tab')) : pestanas[0].id
  return (
    <Page icon={<UserMinus size={18} />} title={t('almint.gestion_titulo')} subtitle={t('almint.gestion_sub')}>
      <Tabs active={tab} onChange={id => setParams({ tab: id })} ariaLabel={t('almint.gestion_titulo')} items={pestanas} />
      <div className="almint-panel">
        {tab === 'bajas' && <Bajas />}
        {tab === 'devoluciones' && <Devoluciones />}
        {tab === 'kits_propuestos' && <Propuestas destacada={params.get('propuesta')} />}
        {tab === 'kits' && <Kits puedeEditar={configura} />}
        {tab === 'peticiones' && <Peticiones />}
        {tab === 'catalogo' && <Catalogo puedeEditar={esAdmin} />}
      </div>
    </Page>
  )
}

// ── Bajas ─────────────────────────────────────────────────────────────────────

function Bajas() {
  const t = useAppT()
  const [estado, setEstado] = useState('')
  const [abierta, setAbierta] = useState<string | null>(null)
  const [programar, setProgramar] = useState(false)
  const q = useQuery({ queryKey: ['alm-bajas', estado], queryFn: () => almIntegracionApi.bajas(estado || undefined) })
  const filas = q.data ?? []
  return <div className="almint-lista">
    <div className="ds-grid-stats almint-kpis">
      <KpiCard icon={<UserMinus size={16} />} label={t('almint.kpi_bajas_abiertas')} value={filas.filter(b => b.estado === 'pendiente_devolucion').length} warning />
      <KpiCard icon={<CalendarClock size={16} />} label={t('almint.kpi_bajas_programadas')} value={filas.filter(b => b.estado === 'programada').length} />
      <KpiCard icon={<Laptop size={16} />} label={t('almint.kpi_equipos_por_volver')} value={filas.reduce((n, b) => n + b.devoluciones_pendientes, 0)} />
    </div>
    <div className="almint-filtros">
      <Select label={t('almint.col_estado')} value={estado} onChange={e => setEstado(e.target.value)}
        options={['programada', 'pendiente_devolucion', 'cerrada', 'anulada'].map(v => ({ value: v, label: etiqueta(t, 'estado', v) }))} />
      <Button icon={<CalendarClock size={14} />} onClick={() => setProgramar(true)}>{t('almint.programar_baja')}</Button>
    </div>
    {q.isLoading ? <Spinner /> : <DataTable<Baja> data={filas} emptyIcon={<UserMinus size={28} />} emptyTitle={t('almint.sin_bajas')} columns={[
      { key: 'user_name', label: t('almint.persona'), render: (_v, f) => <Pulsable type="button" className="almint-boton-enlace" onClick={() => setAbierta(f.id)}>{f.user_name}</Pulsable> },
      { key: 'motivo', label: t('almint.col_motivo'), render: (_v, f) => etiqueta(t, 'motivo_baja', f.motivo) },
      { key: 'estado', label: t('almint.col_estado'), render: (_v, f) => <Estado t={t} codigo={f.estado} /> },
      { key: 'fecha_efectiva', label: t('almint.col_fecha_baja'), render: (_v, f) => fmtDate(f.fecha_efectiva) },
      { key: 'licencias_liberar_en', label: t('almint.col_licencias'), render: (_v, f) => f.licencias_liberadas_en
        ? t('almint.licencias_liberadas_n', { n: f.licencias_liberadas }) : t('almint.se_liberan_el', { fecha: fmtDate(f.licencias_liberar_en) }) },
      { key: 'devoluciones_pendientes', label: t('almint.col_devoluciones'), render: (_v, f) => `${f.devoluciones_total - f.devoluciones_pendientes}/${f.devoluciones_total}` },
    ]} />}
    {abierta && <DetalleDeBaja id={abierta} onClose={() => setAbierta(null)} />}
    {programar && <ProgramarBaja onClose={() => setProgramar(false)} />}
  </div>
}

function DetalleDeBaja({ id, onClose }: { id: string; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['alm-baja', id], queryFn: () => almIntegracionApi.baja(id) })
  const anular = useMutation({
    mutationFn: () => almIntegracionApi.anularBaja(id),
    onSuccess: () => { toast.success(t('almint.baja_anulada')); qc.invalidateQueries({ queryKey: ['alm-bajas'] }); onClose() },
    onError: e => toast.error(mensajeDeError(t, e)),
  })
  const b = q.data
  return <Modal open onClose={onClose} size="lg" title={b?.user_name ?? t('almint.tab_bajas')} subtitle={b ? etiqueta(t, 'motivo_baja', b.motivo) : undefined}>
    {q.isLoading ? <Spinner /> : b && <div className="almint-form">
      <dl className="almint-datos">
        <div><dt>{t('almint.col_estado')}</dt><dd><Estado t={t} codigo={b.estado} /></dd></div>
        <div><dt>{t('almint.col_fecha_baja')}</dt><dd>{fmtDate(b.fecha_efectiva)}</dd></div>
        <div><dt>{t('almint.col_licencias')}</dt><dd>{b.licencias_liberadas_en ? t('almint.licencias_liberadas_n', { n: b.licencias_liberadas }) : t('almint.se_liberan_el', { fecha: fmtDate(b.licencias_liberar_en) })}</dd></div>
        {b.confirmada_con_pendientes && <div><dt>{t('almint.confirmada_con_pendientes')}</dt><dd>{t('common.yes')}</dd></div>}
      </dl>
      {(b.licencias_vigentes ?? []).length > 0 && <><h3 className="almint-subtitulo">{t('almint.licencias_por_liberar')}</h3>
        <ul className="almint-checklist">{(b.licencias_vigentes ?? []).map(l => <li key={l.assignment_id}>{l.name}</li>)}</ul></>}
      <h3 className="almint-subtitulo">{t('almint.devoluciones')}</h3>
      <TablaDeDevoluciones filas={b.devoluciones ?? []} />
      <div className="almint-acciones almint-acciones--fin">
        {b.estado === 'programada' && <Button variant="danger" loading={anular.isPending} onClick={() => openConfirmGlobal({ message: t('almint.confirmar_anular_baja'), confirmLabel: t('almint.anular_baja'), danger: true, onConfirm: () => anular.mutate() })}>{t('almint.anular_baja')}</Button>}
        <Button variant="ghost" onClick={onClose}>{t('common.close')}</Button>
      </div>
    </div>}
  </Modal>
}

function ProgramarBaja({ onClose }: { onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [f, setF] = useState({ user_id: '', fecha: '', notas: '' })
  const personas = useQuery({ queryKey: ['alm-personas-activas'], queryFn: () => usersApi.list().then(r => (r.data ?? []).filter(u => u.is_active !== false)) })
  const camposB = useErroresDeCampo()
  const msgB = (k: string) => camposB.de(k) ? <div className="u-field-error">{camposB.de(k)}</div> : null
  const m = useMutation({
    onMutate: () => camposB.limpiar(),
    mutationFn: () => almIntegracionApi.programarBaja({ user_id: f.user_id, fecha: f.fecha, notas: f.notas || undefined }),
    onSuccess: () => { toast.success(t('almint.baja_programada')); qc.invalidateQueries({ queryKey: ['alm-bajas'] }); onClose() },
    onError: (e: unknown) => { if (!camposB.recoger(e)) toast.error(mensajeDeError(t, e)) },
  })
  return <Modal open onClose={onClose} title={t('almint.programar_baja')} subtitle={t('almint.programar_baja_sub')}>
    <div className="almint-form">
      <Select error={camposB.de('user_id')} label={t('almint.persona')} value={f.user_id} onChange={e => setF({ ...f, user_id: e.target.value })}
        options={(personas.data ?? []).map(u => ({ value: u.id, label: u.full_name }))} />
      <div className="almint-campo"><DateInput label={t('almint.col_fecha_baja')} value={f.fecha} onChange={e => setF({ ...f, fecha: e.target.value })} />{msgB('fecha')}</div>
      <div className="almint-campo"><Textarea label={t('almint.notas')} rows={2} value={f.notas} onChange={e => setF({ ...f, notas: e.target.value })} />{msgB('notas')}</div>
      <div className="almint-acciones almint-acciones--fin">
        <Button variant="ghost" onClick={onClose}>{t('common.cancel')}</Button>
        <Button disabled={!f.user_id || !f.fecha} loading={m.isPending} onClick={() => m.mutate()}>{t('almint.programar_baja')}</Button>
      </div>
    </div>
  </Modal>
}

// ── Devoluciones ──────────────────────────────────────────────────────────────

function Devoluciones() {
  const t = useAppT()
  const [estado, setEstado] = useState('pendiente')
  const q = useQuery({ queryKey: ['alm-devoluciones', estado], queryFn: () => almIntegracionApi.devoluciones(estado || undefined) })
  return <div className="almint-lista">
    <div className="almint-filtros">
      <Select label={t('almint.col_estado')} value={estado} onChange={e => setEstado(e.target.value)}
        options={['pendiente', 'recibida', 'cerrada', 'perdida'].map(v => ({ value: v, label: etiqueta(t, 'estado', v) }))} />
    </div>
    {q.isLoading ? <Spinner /> : <TablaDeDevoluciones filas={q.data ?? []} />}
  </div>
}

function TablaDeDevoluciones({ filas }: { filas: Devolucion[] }) {
  const t = useAppT()
  const [accion, setAccion] = useState<{ tipo: 'recibir' | 'perdida'; d: Devolucion } | null>(null)
  return <>
    <DataTable<Devolucion> data={filas} emptyIcon={<PackageCheck size={28} />} emptyTitle={t('almint.sin_devoluciones')} columns={[
      { key: 'asset_name', label: t('almint.col_equipo'), render: (_v, f) => [f.asset_name, f.asset_tag].filter(Boolean).join(' · ') },
      { key: 'user_name', label: t('almint.persona') },
      { key: 'origen', label: t('almint.col_origen'), render: (_v, f) => etiqueta(t, 'origen_devolucion', f.origen) },
      { key: 'estado', label: t('almint.col_estado'), render: (_v, f) => <span className="almint-pastillas"><Estado t={t} codigo={f.estado} />{f.vencida && <Estado t={t} codigo="vencido" />}{f.acta && <Estado t={t} codigo={f.acta.status} />}</span> },
      { key: 'fecha_limite', label: t('almint.fecha_limite_devolucion'), render: (_v, f) => fmtDate(f.fecha_limite) },
      { key: 'ticket', label: t('almint.ticket'), render: (_v, f) => f.ticket?.number ?? '—' },
      { key: 'acciones', label: '', sortable: false, render: (_v, f) => f.estado === 'pendiente' ? <span className="almint-acciones">
        <Button size="xs" onClick={() => setAccion({ tipo: 'recibir', d: f })}>{t('almint.registrar_recepcion')}</Button>
        <Button size="xs" variant="ghost" onClick={() => setAccion({ tipo: 'perdida', d: f })}>{t('almint.dar_por_perdido')}</Button>
      </span> : null },
    ]} />
    {accion && <AccionDeDevolucion {...accion} onClose={() => setAccion(null)} />}
  </>
}

function AccionDeDevolucion({ tipo, d, onClose }: { tipo: 'recibir' | 'perdida'; d: Devolucion; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [f, setF] = useState({ condition: 'good', observations: '', a_reparar: false, motivo: '' })
  const m = useMutation({
    mutationFn: () => tipo === 'recibir'
      ? almIntegracionApi.recibir(d.id, { condition: f.condition, observations: f.observations || undefined, a_reparar: f.a_reparar })
      : almIntegracionApi.perdida(d.id, f.motivo),
    onSuccess: () => {
      toast.success(tipo === 'recibir' ? t('almint.recepcion_registrada') : t('almint.equipo_perdido'))
      qc.invalidateQueries({ queryKey: ['alm-devoluciones'] }); qc.invalidateQueries({ queryKey: ['alm-baja'] }); qc.invalidateQueries({ queryKey: ['alm-bajas'] })
      onClose()
    },
    onError: e => toast.error(mensajeDeError(t, e)),
  })
  return <Modal open onClose={onClose} title={tipo === 'recibir' ? t('almint.registrar_recepcion') : t('almint.dar_por_perdido')} subtitle={d.asset_name ?? undefined}>
    <div className="almint-form">
      {tipo === 'recibir' ? <>
        <Select label={t('almint.estado_fisico')} value={f.condition} onChange={e => setF({ ...f, condition: e.target.value })}
          options={CONDICIONES.map(c => ({ value: c, label: etiqueta(t, 'condicion', c) }))} />
        <Textarea label={t('almint.observaciones')} rows={3} value={f.observations} onChange={e => setF({ ...f, observations: e.target.value })} />
        <label className="almint-elemento"><span><Checkbox checked={f.a_reparar} onChange={(_, e) => setF({ ...f, a_reparar: e.target.checked })} /> {t('almint.enviar_a_reparar')}</span></label>
        <p className="almint-tenue">{t('almint.recepcion_explicacion')}</p>
      </> : <Textarea label={t('almint.motivo')} rows={3} value={f.motivo} onChange={e => setF({ ...f, motivo: e.target.value })} />}
      <div className="almint-acciones almint-acciones--fin">
        <Button variant="ghost" onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant={tipo === 'recibir' ? 'primary' : 'danger'} disabled={tipo === 'perdida' && !f.motivo.trim()} loading={m.isPending} onClick={() => m.mutate()}>{t('common.confirm')}</Button>
      </div>
    </div>
  </Modal>
}

// ── Propuestas de kit ─────────────────────────────────────────────────────────

function Propuestas({ destacada }: { destacada: string | null }) {
  const t = useAppT()
  const [estado, setEstado] = useState('pendiente')
  const q = useQuery({ queryKey: ['alm-propuestas', estado], queryFn: () => almIntegracionApi.propuestas(estado || undefined) })
  const filas = [...(q.data ?? [])].sort((a, b) => (a.id === destacada ? -1 : b.id === destacada ? 1 : 0))
  return <div className="almint-lista">
    <div className="almint-filtros">
      <Select label={t('almint.col_estado')} value={estado} onChange={e => setEstado(e.target.value)}
        options={['pendiente', 'confirmada', 'descartada'].map(v => ({ value: v, label: etiqueta(t, 'estado', v) }))} />
    </div>
    {q.isLoading ? <Spinner /> : filas.length === 0
      ? <EmptyState icon={<ClipboardCheck size={28} />} title={t('almint.sin_propuestas')} description={t('almint.sin_propuestas_desc')} />
      : filas.map(p => <TarjetaDePropuesta key={p.id} p={p} />)}
  </div>
}

function TarjetaDePropuesta({ p }: { p: PropuestaDeKit }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [elegidas, setElegidas] = useState<string[]>(p.elementos.map(e => e.clave ?? ''))
  const refrescar = () => qc.invalidateQueries({ queryKey: ['alm-propuestas'] })
  const confirmar = useMutation({
    mutationFn: () => almIntegracionApi.confirmarPropuesta(p.id, elegidas),
    onSuccess: () => { toast.success(t('almint.kit_confirmado')); refrescar() },
    onError: e => toast.error(mensajeDeError(t, e)),
  })
  const descartar = useMutation({
    mutationFn: () => almIntegracionApi.descartarPropuesta(p.id),
    onSuccess: () => { toast.success(t('almint.kit_descartado')); refrescar() },
    onError: e => toast.error(mensajeDeError(t, e)),
  })
  const resultado = Array.isArray(p.resultado) ? p.resultado as ElementoDeKit[] : []
  return <div className="ds-card almint-ficha">
    <div className="almint-ficha-cab">
      <div className="almint-ficha-titulo">
        <strong>{p.user_name}</strong>
        <span className="almint-tenue">{[p.user_job_title, p.user_department].filter(Boolean).join(' · ')}</span>
        <span className="almint-tenue">{t('almint.kits_aplicados', { kits: p.kits.map(k => k.nombre).join(', ') })}</span>
      </div>
      <Estado t={t} codigo={p.estado} />
    </div>
    <div>
      {(p.estado === 'pendiente' ? p.elementos : resultado).map((e, i) => <div key={`${e.clave}-${i}`} className="almint-elemento">
        <label>
          {p.estado === 'pendiente' && <Checkbox checked={elegidas.includes(e.clave ?? '')}
            onChange={(_, ev) => setElegidas(ev.target.checked ? [...elegidas, e.clave ?? ''] : elegidas.filter(c => c !== e.clave))} />}
          {e.tipo === 'licencia' ? <KeyRound size={14} aria-hidden /> : <Laptop size={14} aria-hidden />}
          <span>{e.tipo === 'licencia' ? e.license_name : `${etiqueta(t, 'tipo_equipo', e.asset_type)} × ${e.cantidad}`}</span>
        </label>
        {p.estado === 'pendiente'
          ? <Estado t={t} codigo={e.disponible ? 'disponible' : 'sin_existencias'} />
          : <span className="almint-pastillas"><Estado t={t} codigo={e.resultado} />{e.ticket_number && <span className="almint-tenue">{e.ticket_number}</span>}{e.codigo && <span className="almint-tenue">{mensajeDeError(t, { response: { data: { detail: e.codigo } } })}</span>}</span>}
      </div>)}
    </div>
    {p.estado === 'pendiente' && p.puedo_decidir && <div className="almint-acciones almint-acciones--fin">
      <Button variant="ghost" loading={descartar.isPending} onClick={() => descartar.mutate()}>{t('almint.descartar')}</Button>
      <Button icon={<ClipboardCheck size={14} />} disabled={!elegidas.length} loading={confirmar.isPending} onClick={() => confirmar.mutate()}>{t('almint.confirmar_kit')}</Button>
    </div>}
  </div>
}

// ── Kits ──────────────────────────────────────────────────────────────────────

function Kits({ puedeEditar }: { puedeEditar: boolean }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [editando, setEditando] = useState<Kit | 'nuevo' | null>(null)
  const q = useQuery({ queryKey: ['alm-kits'], queryFn: almIntegracionApi.kits })
  const borrar = useMutation({
    mutationFn: (id: string) => almIntegracionApi.borrarKit(id),
    onSuccess: () => { toast.success(t('almint.kit_retirado')); qc.invalidateQueries({ queryKey: ['alm-kits'] }) },
    onError: e => toast.error(mensajeDeError(t, e)),
  })
  return <div className="almint-lista">
    {puedeEditar && <div className="almint-filtros"><Button icon={<Plus size={14} />} onClick={() => setEditando('nuevo')}>{t('almint.nuevo_kit')}</Button></div>}
    {q.isLoading ? <Spinner /> : <DataTable<Kit> data={q.data ?? []} emptyIcon={<Boxes size={28} />} emptyTitle={t('almint.sin_kits')} columns={[
      { key: 'nombre', label: t('almint.col_nombre') },
      { key: 'criterio', label: t('almint.col_aplica_a'), render: (_v, f) => f.criterio === 'todos' ? etiqueta(t, 'criterio', 'todos') : `${etiqueta(t, 'criterio', f.criterio)}: ${f.valor}` },
      { key: 'elementos', label: t('almint.col_contenido'), sortable: false, render: (_v, f) => f.elementos.map(e => e.tipo === 'licencia' ? e.license_name : `${etiqueta(t, 'tipo_equipo', e.asset_type)} × ${e.cantidad}`).join(', ') },
      ...(puedeEditar ? [{ key: 'acciones', label: '', sortable: false, render: (_v: never, f: Kit) => <span className="almint-acciones">
        <Button size="xs" variant="ghost" onClick={() => setEditando(f)}>{t('common.edit')}</Button>
        <Button size="xs" variant="ghost" icon={<Trash2 size={12} />} onClick={() => openConfirmGlobal({ message: t('almint.confirmar_retirar_kit', { nombre: f.nombre }), confirmLabel: t('almint.retirar'), danger: true, onConfirm: () => borrar.mutate(f.id) })}>{t('almint.retirar')}</Button>
      </span> }] : []),
    ]} />}
    {editando && <EditorDeKit kit={editando === 'nuevo' ? null : editando} onClose={() => setEditando(null)} />}
  </div>
}

function EditorDeKit({ kit, onClose }: { kit: Kit | null; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [f, setF] = useState({ nombre: kit?.nombre ?? '', descripcion: kit?.descripcion ?? '', criterio: kit?.criterio ?? 'todos', valor: kit?.valor ?? '' })
  const [elementos, setElementos] = useState<ElementoDeKit[]>(kit?.elementos ?? [])
  const licencias = useQuery({ queryKey: ['alm-licencias-para-asignar'], queryFn: () => licensesApi.list({ page_size: 200 }).then(r => r.data) })
  const campos = useErroresDeCampo()
  const msg = (k: string) => campos.de(k) ? <div className="u-field-error">{campos.de(k)}</div> : null
  const m = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: () => {
      const datos = { ...f, valor: f.criterio === 'todos' ? null : f.valor, elementos }
      return kit ? almIntegracionApi.cambiarKit(kit.id, datos) : almIntegracionApi.crearKit(datos)
    },
    onSuccess: () => { toast.success(t('almint.kit_guardado')); qc.invalidateQueries({ queryKey: ['alm-kits'] }); onClose() },
    onError: (e: unknown) => { campos.recoger(e); toast.error(mensajeDeError(t, e)) },
  })
  const cambiar = (i: number, cambio: Partial<ElementoDeKit>) => setElementos(elementos.map((e, j) => j === i ? { ...e, ...cambio } : e))
  return <Modal open onClose={onClose} size="lg" title={kit ? kit.nombre : t('almint.nuevo_kit')} subtitle={t('almint.kit_sub')}>
    <div className="almint-form">
      <div className="almint-campo"><Input label={t('almint.col_nombre')} value={f.nombre} onChange={e => setF({ ...f, nombre: e.target.value })} />{msg('nombre')}</div>
      <div className="almint-fila">
        <Select error={campos.de('criterio')} label={t('almint.col_aplica_a')} value={f.criterio} onChange={e => setF({ ...f, criterio: e.target.value })}
          options={CRITERIOS.map(c => ({ value: c, label: etiqueta(t, 'criterio', c) }))} />
        {f.criterio !== 'todos' && <div className="almint-campo"><Input label={t('almint.valor_del_criterio')} value={f.valor} onChange={e => setF({ ...f, valor: e.target.value })} />{msg('valor')}</div>}
      </div>
      <div className="almint-campo"><Textarea label={t('common.description')} rows={2} value={f.descripcion} onChange={e => setF({ ...f, descripcion: e.target.value })} />{msg('descripcion')}</div>
      <h3 className="almint-subtitulo">{t('almint.col_contenido')}</h3>
      {elementos.map((e, i) => <div key={i} className="almint-fila">
        <Select label={t('almint.tipo')} value={e.tipo} onChange={ev => cambiar(i, { tipo: ev.target.value as 'licencia' | 'equipo', license_id: null, asset_type: null })}
          options={[{ value: 'licencia', label: t('almint.una_licencia') }, { value: 'equipo', label: t('almint.un_equipo') }]} />
        {e.tipo === 'licencia'
          ? <Select label={t('almint.col_licencia')} value={e.license_id ?? ''} onChange={ev => cambiar(i, { license_id: ev.target.value })}
              options={(licencias.data ?? []).map(l => ({ value: String(l.id), label: String(l.name) }))} />
          : <Select label={t('almint.tipo_de_equipo')} value={e.asset_type ?? ''} onChange={ev => cambiar(i, { asset_type: ev.target.value })}
              options={TIPOS_DE_EQUIPO.map(v => ({ value: v, label: etiqueta(t, 'tipo_equipo', v) }))} />}
        {e.tipo === 'equipo' && <Input label={t('almint.col_cantidad')} type="number" min={1} value={e.cantidad} onChange={ev => cambiar(i, { cantidad: Number(ev.target.value) || 1 })} />}
        <div className="almint-acciones"><Button size="xs" variant="ghost" icon={<Trash2 size={12} />} onClick={() => setElementos(elementos.filter((_x, j) => j !== i))}>{t('almint.quitar')}</Button></div>
      </div>)}
      <div className="almint-acciones">
        <Button size="sm" variant="secondary" icon={<KeyRound size={14} />} onClick={() => setElementos([...elementos, { tipo: 'licencia', cantidad: 1 }])}>{t('almint.anadir_licencia')}</Button>
        <Button size="sm" variant="secondary" icon={<Laptop size={14} />} onClick={() => setElementos([...elementos, { tipo: 'equipo', cantidad: 1 }])}>{t('almint.anadir_equipo')}</Button>
      </div>
      <div className="almint-acciones almint-acciones--fin">
        <Button variant="ghost" onClick={onClose}>{t('common.cancel')}</Button>
        <Button disabled={!f.nombre.trim() || !elementos.length} loading={m.isPending} onClick={() => m.mutate()}>{t('common.save')}</Button>
      </div>
    </div>
  </Modal>
}

// ── Peticiones ────────────────────────────────────────────────────────────────

function Peticiones() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [estado, setEstado] = useState('')
  const q = useQuery({ queryKey: ['alm-peticiones', estado], queryFn: () => almIntegracionApi.peticiones(estado || undefined) })
  const reintentar = useMutation({
    mutationFn: (id: string) => almIntegracionApi.reintentar(id),
    onSuccess: r => { toast.success(etiqueta(t, 'estado', r.estado)); qc.invalidateQueries({ queryKey: ['alm-peticiones'] }) },
    onError: e => toast.error(mensajeDeError(t, e)),
  })
  return <div className="almint-lista">
    <div className="almint-filtros">
      <Select label={t('almint.col_estado')} value={estado} onChange={e => setEstado(e.target.value)}
        options={['pendiente', 'cumplida', 'en_compra', 'rechazada', 'error'].map(v => ({ value: v, label: etiqueta(t, 'estado', v) }))} />
    </div>
    {q.isLoading ? <Spinner /> : <DataTable<Peticion> data={q.data ?? []} emptyIcon={<Send size={28} />} emptyTitle={t('almint.sin_peticiones')} columns={[
      { key: 'beneficiario_name', label: t('almint.persona') },
      { key: 'tipo', label: t('almint.col_que'), render: (_v, f) => f.tipo === 'licencia' ? f.license_name : etiqueta(t, 'tipo_equipo', f.asset_type) },
      { key: 'estado', label: t('almint.col_estado'), render: (_v, f) => <span className="almint-pastillas"><Estado t={t} codigo={f.estado} />{f.aprobacion === 'pending' && <Estado t={t} codigo="en_aprobacion" />}</span> },
      { key: 'ticket', label: t('almint.ticket'), render: (_v, f) => f.ticket?.number ?? '—' },
      { key: 'compra', label: t('almint.col_compra'), render: (_v, f) => f.compra?.number ?? '—' },
      { key: 'created_at', label: t('almint.col_fecha'), render: (_v, f) => fmtDate(f.created_at) },
      { key: 'acciones', label: '', sortable: false, render: (_v, f) => ['en_compra', 'error'].includes(f.estado)
        ? <Button size="xs" variant="secondary" loading={reintentar.isPending} onClick={() => reintentar.mutate(f.id)}>{t('almint.reintentar_alta')}</Button> : null },
    ]} />}
  </div>
}

// ── Catálogo ──────────────────────────────────────────────────────────────────

function Catalogo({ puedeEditar }: { puedeEditar: boolean }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['alm-items-catalogo'], queryFn: almIntegracionApi.itemsDeCatalogo })
  const catalogo = useQuery({ queryKey: ['sd-catalog'], queryFn: () => sdCatalogApi.list().then(r => r.data), enabled: puedeEditar })
  const licencias = useQuery({ queryKey: ['alm-licencias-para-asignar'], queryFn: () => licensesApi.list({ page_size: 200 }).then(r => r.data), enabled: puedeEditar })
  const [nuevo, setNuevo] = useState({ service_item_id: '', tipo: 'licencia', license_id: '', asset_type: '' })
  const [categoria, setCategoria] = useState('')
  const refrescar = () => qc.invalidateQueries({ queryKey: ['alm-items-catalogo'] })
  const guardar = useMutation({
    mutationFn: () => almIntegracionApi.guardarItem({ service_item_id: nuevo.service_item_id, tipo: nuevo.tipo,
      license_id: nuevo.license_id || null, asset_type: nuevo.asset_type || null }),
    onSuccess: () => { toast.success(t('almint.item_guardado')); refrescar(); setNuevo({ service_item_id: '', tipo: 'licencia', license_id: '', asset_type: '' }) },
    onError: e => toast.error(mensajeDeError(t, e)),
  })
  const crear = useMutation({
    mutationFn: () => almIntegracionApi.crearItems(categoria, { licencia: t('almint.pedir_licencia'), equipo: t('almint.pedir_equipo') }),
    onSuccess: () => { toast.success(t('almint.items_creados')); refrescar(); qc.invalidateQueries({ queryKey: ['sd-catalog'] }) },
    onError: e => toast.error(mensajeDeError(t, e)),
  })
  const borrar = useMutation({
    mutationFn: (id: string) => almIntegracionApi.borrarItem(id),
    onSuccess: () => refrescar(),
    onError: e => toast.error(mensajeDeError(t, e)),
  })
  const servicios = (catalogo.data ?? []).flatMap(c => (c.services ?? []).map(s => ({ value: String(s.id), label: `${c.name} · ${s.name}` })))
  return <div className="almint-lista">
    <p className="almint-tenue">{t('almint.catalogo_explicacion')}</p>
    {q.isLoading ? <Spinner /> : <DataTable<ItemDeCatalogoAlm> data={q.data ?? []} emptyIcon={<ListChecks size={28} />} emptyTitle={t('almint.sin_items')} columns={[
      { key: 'service_item_name', label: t('almint.col_item') },
      { key: 'tipo', label: t('almint.tipo'), render: (_v, f) => f.tipo === 'licencia' ? t('almint.una_licencia') : t('almint.un_equipo') },
      { key: 'license_name', label: t('almint.col_concreto'), render: (_v, f) => f.license_name ?? (f.asset_type ? etiqueta(t, 'tipo_equipo', f.asset_type) : t('almint.a_elegir')) },
      { key: 'requires_catalog_approval', label: t('almint.col_aprobacion'), render: (_v, f) => etiqueta(t, 'aprobacion', f.approval) },
      ...(puedeEditar ? [{ key: 'acciones', label: '', sortable: false, render: (_v: never, f: ItemDeCatalogoAlm) =>
        <Button size="xs" variant="ghost" icon={<Trash2 size={12} />} onClick={() => openConfirmGlobal({ message: t('almint.confirmar_quitar_item', { nombre: f.service_item_name }), confirmLabel: t('almint.quitar'), danger: true, onConfirm: () => borrar.mutate(f.id) })}>{t('almint.quitar')}</Button> }] : []),
    ]} />}
    {puedeEditar && <>
      <h3 className="almint-subtitulo">{t('almint.marcar_item')}</h3>
      <div className="almint-fila">
        <Select label={t('almint.col_item')} value={nuevo.service_item_id} onChange={e => setNuevo({ ...nuevo, service_item_id: e.target.value })} options={servicios} />
        <Select label={t('almint.tipo')} value={nuevo.tipo} onChange={e => setNuevo({ ...nuevo, tipo: e.target.value, license_id: '', asset_type: '' })}
          options={[{ value: 'licencia', label: t('almint.una_licencia') }, { value: 'equipo', label: t('almint.un_equipo') }]} />
        {nuevo.tipo === 'licencia'
          ? <Select label={t('almint.col_concreto')} value={nuevo.license_id} onChange={e => setNuevo({ ...nuevo, license_id: e.target.value })}
              options={(licencias.data ?? []).map(l => ({ value: String(l.id), label: String(l.name) }))} />
          : <Select label={t('almint.col_concreto')} value={nuevo.asset_type} onChange={e => setNuevo({ ...nuevo, asset_type: e.target.value })}
              options={TIPOS_DE_EQUIPO.map(v => ({ value: v, label: etiqueta(t, 'tipo_equipo', v) }))} />}
      </div>
      <div className="almint-acciones"><Button disabled={!nuevo.service_item_id} loading={guardar.isPending} onClick={() => guardar.mutate()}>{t('common.save')}</Button></div>
      <h3 className="almint-subtitulo">{t('almint.crear_items')}</h3>
      <div className="almint-filtros">
        <Select label={t('almint.categoria')} value={categoria} onChange={e => setCategoria(e.target.value)}
          options={(catalogo.data ?? []).map(c => ({ value: String(c.id), label: c.name }))} />
        <Button variant="secondary" disabled={!categoria} loading={crear.isPending} onClick={() => crear.mutate()}>{t('almint.crear_items_boton')}</Button>
      </div>
    </>}
  </div>
}

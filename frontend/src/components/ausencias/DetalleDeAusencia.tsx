/**
 * Detalle de una ausencia (tarea #25): línea de tiempo (pedida, en espera,
 * plaza, aprobación paso a paso, documentos, recordatorios, escalados),
 * documentos con sus versiones (ver, descargar, sustituir, añadir), lo que se
 * pide con su vencimiento, la aprobación y las plazas. Quien gestiona (RRHH,
 * admin o responsable) además pide otro documento, dispensa, amplía o da plaza.
 */
import { fmtDateTime } from '../../utils/helpers'
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, Eye, FilePlus2, Lock, RefreshCw } from 'lucide-react'
import { ausenciasApi } from '../../services/api/ausencias'
import type { DetalleDeAusencia as Detalle, DocumentoDeAusencia } from '../../services/api/tipos-ausencias'
import { Button, Drawer, Spinner } from '../ui'
import DateInput from '../ui/DateInput'
import { AvisoDeError } from './admin/comun'
import { EstadoDeAusenciaChip, TipoChip, cantidad, fecha, useTa, useTiposDeDocumento } from './comun'

export default function DetalleDeAusencia({ id, onCerrar }: { id: string | null; onCerrar: () => void }) {
  const { ta } = useTa()
  const q = useQuery({ queryKey: ['ausencias', 'detalle', id], queryFn: () => ausenciasApi.detalle(id as string), enabled: Boolean(id) })
  return (
    <Drawer open={Boolean(id)} onClose={onCerrar} ariaLabel={ta('detalle')}>
      <div className="aus-drawer">
      <header className="aus-fila aus-drawer-cabecera">
        <h2 className="aus-titulo">{ta('detalle')}</h2>
        <Button size="xs" variant="ghost" onClick={onCerrar}>{ta('cerrar')}</Button>
      </header>
      {q.isLoading && <Spinner label={ta('cargando')} />}
      {q.isError && <AvisoDeError error={q.error} defecto={ta('error_cargar')} />}
      {q.data && <Contenido d={q.data} />}
      </div>
    </Drawer>
  )
}

function Contenido({ d }: { d: Detalle }) {
  const { ta, lang } = useTa()
  const a = d.ausencia
  return (
    <div className="aus-detalle">
      <header className="aus-fila">
        <TipoChip a={a} /><EstadoDeAusenciaChip estado={a.status} />
        <span>{fecha(a.start_date, lang)} → {fecha(a.end_date, lang)} · {cantidad(a, ta)}</span>
      </header>
      {a.user_name && <p className="aus-ayuda">{a.user_name}{a.substitute_name ? ` · ${ta('sustituto')}: ${a.substitute_name}` : ''}</p>}
      {a.rejection_reason && <p className="aus-bloqueo">{a.rejection_reason}</p>}
      {d.posicion_en_espera && <p className="aus-aviso">{ta('posicion_en_espera', { n: d.posicion_en_espera })}</p>}
      <Gestion d={d} />
      <Documentos d={d} />
      {d.aprobacion && (
        <section aria-labelledby="aus-aprob">
          <h3 id="aus-aprob" className="aus-subtitulo">{ta('aprobacion')} · {ta(`solicitud_${d.aprobacion.estado}`)}</h3>
          <ol className="aus-pasos">
            {d.aprobacion.pasos.map((p, i) => {
              const decs = d.aprobacion?.decisiones.filter(x => x.orden === p.orden) ?? []
              const actual = d.aprobacion?.estado === 'pending' && p.orden === d.aprobacion.paso_actual
              return (
                <li key={`${p.orden}-${i}`} className={`aus-paso aus-paso--${p.tipo}${actual ? ' aus-paso--actual' : ''}`}
                  aria-current={actual ? 'step' : undefined}>
                  {p.nombre}{p.tipo === 'inform' ? ` · ${ta('informa')}` : ''}
                  {decs.map((x, j) => <span key={j} className="aus-chip">{ta(`voto_${x.decision}`)} · {x.quien}</span>)}
                </li>
              )
            })}
          </ol>
        </section>
      )}
      {d.plazas.length > 0 && (
        <section aria-labelledby="aus-plazas">
          <h3 id="aus-plazas" className="aus-subtitulo">{ta('plazas')}</h3>
          <ul className="aus-lista-simple">
            {d.plazas.map(p => <li key={`${p.clave}-${p.fecha}-${p.turno}`}>{fecha(p.fecha, lang)} · {ta(`plaza_${p.estado}`)}
              {p.por_encima ? ` · ${ta('por_encima')}` : ''}</li>)}
          </ul>
        </section>
      )}
      <section aria-labelledby="aus-linea">
        <h3 id="aus-linea" className="aus-subtitulo">{ta('linea_de_tiempo')}</h3>
        <ol className="aus-linea">
          {d.linea_de_tiempo.map((e, i) => (
            <li key={i} className={`aus-evento aus-evento--${e.tipo}`}>
              <strong>{ta(`evento_${e.tipo}`)}</strong>
              {typeof e.datos.documento === 'string' && <> · {e.datos.documento}</>}
              {typeof e.datos.version === 'number' && <> · v{e.datos.version}</>}
              {typeof e.datos.posicion === 'number' && <> · {ta('posicion_en_espera', { n: e.datos.posicion })}</>}
              {typeof e.datos.motivo === 'string' && <> · {e.datos.motivo}</>}
              <span className="aus-ayuda"> {e.quien ?? ta('sistema')} · {e.cuando ? fmtDateTime(e.cuando) : ''}</span>
            </li>
          ))}
        </ol>
      </section>
    </div>
  )
}

function Documentos({ d }: { d: Detalle }) {
  const { ta, lang } = useTa()
  const qc = useQueryClient()
  const tipos = useTiposDeDocumento().data ?? []
  const [tipoId, setTipoId] = useState('')
  const [sustituye, setSustituye] = useState<DocumentoDeAusencia | null>(null)
  const subir = useMutation({
    mutationFn: (f: File) => ausenciasApi.subirDocumento(d.ausencia.id, sustituye?.tipo_id ?? tipoId, f, sustituye?.id),
    onSuccess: () => { setSustituye(null); qc.invalidateQueries({ queryKey: ['ausencias'] }) },
  })
  const abrir = useMutation({
    mutationFn: ({ doc, accion }: { doc: DocumentoDeAusencia; accion: 'view' | 'download' }) => ausenciasApi.abrirDocumento(d.ausencia.id, doc.id, accion),
    onSuccess: r => { window.open(r.url, '_blank', 'noopener') },
  })
  return (
    <section aria-labelledby="aus-docs">
      <h3 id="aus-docs" className="aus-subtitulo">{ta('documentos')}</h3>
      {d.requisitos.length > 0 && (
        <ul className="aus-lista-simple">
          {d.requisitos.map(r => (
            <li key={r.id} className={`aus-requisito aus-requisito--${r.estado}`}>
              {r.tipo}{r.secuencia > 1 ? ` #${r.secuencia}` : ''} · {ta(`requisito_${r.estado}`)} · {ta('vence_el', { fecha: fecha(r.vence, lang) })}
              {r.estado === 'pendiente' || r.estado === 'vencido' ? <Dispensar d={d} requisitoId={r.id} /> : null}
            </li>
          ))}
        </ul>
      )}
      {d.documentos.length === 0 ? <p className="aus-ayuda">{ta('sin_documentos')}</p> : (
        <ul className="aus-lista-simple">
          {d.documentos.map(doc => (
            <li key={doc.id} className={`aus-documento${doc.estado === 'sustituido' ? ' aus-documento--viejo' : ''}`}>
              {doc.especial && <Lock size={12} aria-label={ta('categoria_especial')} />} {doc.tipo} · v{doc.version}
              {doc.estado === 'sustituido' ? ` · ${ta('sustituido')}` : ''} · {fecha(doc.subido_en, lang)}
              {doc.puede_ver ? (
                <>
                  <Button size="xs" variant="ghost" icon={<Eye size={12} />} onClick={() => abrir.mutate({ doc, accion: 'view' })}>{ta('ver')}</Button>
                  <Button size="xs" variant="ghost" icon={<Download size={12} />} onClick={() => abrir.mutate({ doc, accion: 'download' })}>{ta('descargar')}</Button>
                  {d.puede_subir && doc.estado === 'vigente' && (
                    <Button size="xs" variant="ghost" icon={<RefreshCw size={12} />} onClick={() => setSustituye(doc)}>{ta('sustituir')}</Button>
                  )}
                </>
              ) : <span className="aus-ayuda"> · {ta('acceso_restringido')}</span>}
            </li>
          ))}
        </ul>
      )}
      {abrir.isError && <AvisoDeError error={abrir.error} defecto={ta('error_documento')} />}
      {d.puede_subir && (
        <div className="aus-fila">
          {sustituye ? <span className="aus-chip">{ta('sustituyendo', { tipo: sustituye.tipo ?? '', v: sustituye.version })}</span> : (
            <select className="aus-campo" aria-label={ta('tipo_de_documento')} value={tipoId} onChange={e => setTipoId(e.target.value)}>
              <option value="">{ta('elige_tipo_de_documento')}</option>
              {tipos.map(t => <option key={t.id} value={t.id}>{t.nombres?.[lang as 'es'] || t.nombre}</option>)}
            </select>
          )}
          <label className="aus-boton-fichero">
            <FilePlus2 size={13} aria-hidden /> {ta('adjuntar')}
            <input type="file" className="u-sr-only" aria-label={ta('adjuntar')} disabled={!sustituye && !tipoId}
              onChange={e => { const f = e.target.files?.[0]; if (f) subir.mutate(f); e.target.value = '' }} />
          </label>
          {sustituye && <Button size="xs" variant="ghost" onClick={() => setSustituye(null)}>{ta('cancelar')}</Button>}
          {subir.isPending && <Spinner size={14} label={ta('subiendo')} />}
        </div>
      )}
      {subir.isError && <AvisoDeError error={subir.error} defecto={ta('error_subir')} />}
    </section>
  )
}

function Dispensar({ d, requisitoId }: { d: Detalle; requisitoId: string }) {
  const { ta } = useTa()
  const qc = useQueryClient()
  const m = useMutation({ mutationFn: () => ausenciasApi.dispensar(d.ausencia.id, requisitoId), onSuccess: () => qc.invalidateQueries({ queryKey: ['ausencias'] }) })
  if (!d.puede_gestionar) return null
  return <Button size="xs" variant="ghost" loading={m.isPending} onClick={() => m.mutate()}>{ta('dispensar')}</Button>
}

function Gestion({ d }: { d: Detalle }) {
  const { ta, lang } = useTa()
  const qc = useQueryClient()
  const tipos = useTiposDeDocumento().data ?? []
  const [tipoId, setTipoId] = useState('')
  const [vence, setVence] = useState('')
  const [fin, setFin] = useState('')
  const listo = () => qc.invalidateQueries({ queryKey: ['ausencias'] })
  const pedir = useMutation({ mutationFn: () => ausenciasApi.pedirDocumento(d.ausencia.id, tipoId, vence), onSuccess: () => { setTipoId(''); setVence(''); listo() } })
  const ampliar = useMutation({ mutationFn: () => ausenciasApi.ampliar(d.ausencia.id, fin), onSuccess: () => { setFin(''); listo() } })
  const plaza = useMutation({ mutationFn: () => ausenciasApi.darPlaza(d.ausencia.id), onSuccess: listo })
  if (!d.puede_gestionar) return null
  return (
    <section className="aus-gestion" aria-labelledby="aus-gestion">
      <h3 id="aus-gestion" className="aus-subtitulo">{ta('gestionar')}</h3>
      <div className="aus-fila">
        <select className="aus-campo" aria-label={ta('pedir_documento')} value={tipoId} onChange={e => setTipoId(e.target.value)}>
          <option value="">{ta('pedir_documento')}</option>
          {tipos.map(t => <option key={t.id} value={t.id}>{t.nombres?.[lang as 'es'] || t.nombre}</option>)}
        </select>
        <DateInput className="aus-campo" aria-label={ta('fecha_limite')} value={vence} onChange={e => setVence(e.target.value)} />
        <Button size="sm" variant="secondary" disabled={!tipoId || !vence} loading={pedir.isPending} onClick={() => pedir.mutate()}>{ta('pedir')}</Button>
      </div>
      {d.ausencia.status === 'approved' && (
        <div className="aus-fila">
          <DateInput className="aus-campo" aria-label={ta('nuevo_fin')} value={fin} min={d.ausencia.end_date} onChange={e => setFin(e.target.value)} />
          <Button size="sm" variant="secondary" disabled={!fin} loading={ampliar.isPending} onClick={() => ampliar.mutate()}>{ta('ampliar')}</Button>
        </div>
      )}
      {d.ausencia.status === 'waitlisted' && (
        <Button size="sm" variant="secondary" loading={plaza.isPending} onClick={() => plaza.mutate()}>{ta('dar_plaza')}</Button>
      )}
      {[pedir, ampliar, plaza].map((m, i) => m.isError ? <AvisoDeError key={i} error={m.error} defecto={ta('error_guardar')} /> : null)}
    </section>
  )
}

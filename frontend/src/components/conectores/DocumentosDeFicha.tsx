/**
 * Documentos de contecmind en una ficha de contecflow (revisión 2026-11).
 *
 * Un solo panel para tickets, contratos, proyectos y artículos:
 *  - los documentos enlazados (abrir, descargar, quitar el enlace);
 *  - subir un fichero a la carpeta de la ficha en contecmind (si el rol puede);
 *  - buscar en contecmind y enlazar lo que ya existe;
 *  - en un ticket, «documentos que pueden resolverlo», buscados por su asunto;
 *  - preguntar a los documentos de la carpeta, con citas.
 * Todo con los permisos que contecmind da a quien está mirando.
 */
import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, ExternalLink, FileText, Link2, MessageSquareText, Search, Sparkles, Trash2, Upload } from 'lucide-react'
import { conectoresApi, mensajeDeConector } from '../../services/api'
import type { DocHit, Enlace, FichaDocumental } from '../../services/api'
import { Button, Spinner } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { localeActivo } from '../../utils/helpers'
import DocumentoContecmind, { descargarOriginal } from './DocumentoContecmind'
import { STALE_DEFAULT_MS } from '../../constants/timings'
import './DocumentosDeFicha.css'


export function tamano(n?: number | null): string {
  if (!n && n !== 0) return ''
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toLocaleString(localeActivo(), { maximumFractionDigits: 0 })} KB`
  return `${(n / 1024 / 1024).toLocaleString(localeActivo(), { maximumFractionDigits: 1 })} MB`
}

export default function DocumentosDeFicha({ ficha, id, sugerir = false, preguntar = false }: {
  ficha: FichaDocumental; id: string; sugerir?: boolean; preguntar?: boolean
}) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const fichero = useRef<HTMLInputElement>(null)
  const [abierto, setAbierto] = useState<string | null>(null)
  const [busqueda, setBusqueda] = useState('')
  const [buscado, setBuscado] = useState('')
  const [pregunta, setPregunta] = useState('')
  const clave = ['conectores', 'enlaces', ficha, id]

  const disp = useQuery({ queryKey: ['conectores', 'cm-disponible'], queryFn: conectoresApi.cmDisponible, staleTime: STALE_DEFAULT_MS })
  const configurado = !!disp.data?.configurado
  const enlaces = useQuery({ queryKey: clave, queryFn: () => conectoresApi.enlaces(ficha, id), enabled: configurado })
  const sugeridos = useQuery({
    queryKey: ['conectores', 'sugerencias', ficha, id], queryFn: () => conectoresApi.sugerencias(ficha, id),
    enabled: configurado && sugerir, retry: false,
  })
  const resultados = useQuery({
    queryKey: ['conectores', 'buscar', buscado], queryFn: () => conectoresApi.buscar(buscado, 10),
    enabled: configurado && buscado.length >= 2, retry: false,
  })
  const refrescar = () => {
    qc.invalidateQueries({ queryKey: clave })
    qc.invalidateQueries({ queryKey: ['conectores', 'sugerencias', ficha, id] })
  }
  const error = (e: unknown) => toast.error(mensajeDeConector(e, t('docs.error_generico')))

  const enlazar = useMutation({
    mutationFn: (h: DocHit) => conectoresApi.enlazar(ficha, id, h.document_id),
    onSuccess: () => { toast.success(t('docs.enlazado')); refrescar() }, onError: error,
  })
  const subir = useMutation({
    mutationFn: (f: File) => conectoresApi.subir(ficha, id, f),
    onSuccess: () => { toast.success(t('docs.subido')); refrescar() }, onError: error,
  })
  const quitar = useMutation({
    mutationFn: (e: Enlace) => conectoresApi.desenlazar(ficha, id, e.id),
    onSuccess: () => { toast.success(t('docs.quitado')); refrescar() }, onError: error,
  })
  const preguntarCarpeta = useMutation({
    mutationFn: () => conectoresApi.preguntarCarpeta(ficha, id, pregunta.trim()), onError: error,
  })

  if (disp.isLoading) return <div className="dodefi-caja"><Spinner size={18} /></div>
  if (!configurado) {
    return (
      <section aria-label={t('docs.titulo')} className="dodefi-caja">
        <div className="dodefi-titulo"><FileText size={15} />{t('docs.titulo')}</div>
        <div className="dodefi-sub2">{t('docs.no_configurado')}</div>
      </section>
    )
  }
  const lista = enlaces.data?.items ?? []
  const yaEnlazados = new Set(lista.map(e => e.document_id))

  return (
    <section aria-label={t('docs.titulo')} className="dodefi-caja2">
      <header className="u-wrap-center-8">
        <div className="dodefi-titulo"><FileText size={15} />{t('docs.titulo')}<span className="dodefi-sub3">· contecmind</span></div>
        <div className="dodefi-row-1">
          {disp.data?.puede_escribir && (
            <>
              <input ref={fichero} type="file" hidden aria-label={t('docs.subir')}
                onChange={e => { const f = e.target.files?.[0]; if (f) subir.mutate(f); e.target.value = '' }} />
              <Button size="sm" variant="secondary" icon={<Upload size={13} />} loading={subir.isPending}
                onClick={() => fichero.current?.click()}>{t('docs.subir')}</Button>
            </>
          )}
        </div>
      </header>

      {/* Enlazados */}
      <div className="u-stack-6">
        {enlaces.isLoading ? <Spinner size={18} />
          : enlaces.isError ? <div role="alert" className="dodefi-sub4">{mensajeDeConector(enlaces.error, t('docs.error_generico'))}</div>
          : lista.length === 0 ? <div className="dodefi-sub">{t('docs.vacio')}</div>
          : lista.map(e => (
            <div key={e.id} className="dodefi-fila">
              <FileText size={15} color="var(--accent)" aria-hidden />
              <button type="button" onClick={() => setAbierto(e.document_id)}
                className="dodefi-box-1">
                {e.title}
              </button>
              <span className="dodefi-sub">{tamano(e.size_bytes)}</span>
              <span className="dodefi-sub5">{t(`docs.origen_${e.origen}`)}</span>
              <Button size="xs" variant="ghost" title={t('docs.descargar')} icon={<Download size={13} />}
                onClick={() => descargarOriginal(e.document_id, e.title).catch(error)}>{''}</Button>
              <Button size="xs" variant="ghost" title={t('docs.quitar')} icon={<Trash2 size={13} />}
                onClick={() => openConfirmGlobal({ title: t('docs.quitar_titulo'), message: t('docs.quitar_texto'), danger: true, onConfirm: () => quitar.mutate(e) })}>{''}</Button>
            </div>
          ))}
      </div>

      {/* Sugeridos (ticket) */}
      {sugerir && (
        <div>
          <div className="dodefi-titulo2">
            <Sparkles size={13} />{t('docs.sugeridos')}
          </div>
          <div className="dodefi-stack-1">
            {sugeridos.isLoading ? <Spinner size={16} />
              : sugeridos.isError ? <div className="dodefi-sub">{mensajeDeConector(sugeridos.error, t('docs.error_generico'))}</div>
              : (sugeridos.data?.items ?? []).length === 0 ? <div className="dodefi-sub">{t('docs.sin_sugeridos')}</div>
              : sugeridos.data!.items.map(h => <Resultado key={h.document_id} h={h} onAbrir={() => setAbierto(h.document_id)} onEnlazar={() => enlazar.mutate(h)} ya={yaEnlazados.has(h.document_id)} />)}
          </div>
        </div>
      )}

      {/* Buscar y enlazar */}
      <form onSubmit={e => { e.preventDefault(); setBuscado(busqueda.trim()) }} className="u-row-6">
        <input aria-label={t('docs.buscar')} placeholder={t('docs.buscar_placeholder')} value={busqueda} onChange={e => setBusqueda(e.target.value)} className="dodefi-campo" />
        <Button size="sm" variant="secondary" type="submit" icon={<Search size={13} />}>{t('docs.buscar')}</Button>
      </form>
      {buscado.length >= 2 && (
        <div className="u-stack-6">
          {resultados.isLoading ? <Spinner size={16} />
            : resultados.isError ? <div role="alert" className="dodefi-sub4">{mensajeDeConector(resultados.error, t('docs.error_generico'))}</div>
            : (resultados.data?.items ?? []).length === 0 ? <div className="dodefi-sub">{t('docs.sin_resultados')}</div>
            : resultados.data!.items.map(h => <Resultado key={h.document_id} h={h} onAbrir={() => setAbierto(h.document_id)} onEnlazar={() => enlazar.mutate(h)} ya={yaEnlazados.has(h.document_id)} />)}
        </div>
      )}

      {/* Preguntar a la carpeta */}
      {preguntar && lista.length > 0 && (
        <div className="dodefi-box-2">
          <form onSubmit={e => { e.preventDefault(); if (pregunta.trim().length >= 2) preguntarCarpeta.mutate() }} className="u-row-6">
            <input aria-label={t('docs.preguntar')} placeholder={t('docs.preguntar_placeholder')} value={pregunta} onChange={e => setPregunta(e.target.value)} className="dodefi-campo" />
            <Button size="sm" type="submit" icon={<MessageSquareText size={13} />} loading={preguntarCarpeta.isPending}>{t('docs.preguntar')}</Button>
          </form>
          {preguntarCarpeta.data && (
            <div className="dodefi-stack-2">
              <div className="dodefi-txt-1">{preguntarCarpeta.data.answer || t('docs.sin_respuesta')}</div>
              {preguntarCarpeta.data.citations.map((c, i) => (
                <button key={i} type="button" onClick={() => setAbierto(c.document_id)}
                  className="dodefi-box-3">
                  <strong className="u-text1">[{i + 1}] {c.title || c.document_id}{c.page ? ` · ${t('docs.pagina')} ${c.page}` : ''}</strong>
                  <div className="dodefi-sp-1">{c.text}</div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {abierto && <DocumentoContecmind id={abierto} puedeEscribir={!!disp.data?.puede_escribir} onClose={() => setAbierto(null)} />}
    </section>
  )
}

function Resultado({ h, onAbrir, onEnlazar, ya }: { h: DocHit; onAbrir: () => void; onEnlazar: () => void; ya: boolean }) {
  const t = useAppT()
  return (
    <div className="dodefi-fila2">
      <ExternalLink size={14} color="var(--text-3)" style={{ marginTop: 3 }} aria-hidden />
      <div className="u-flex1-min0">
        <button type="button" onClick={onAbrir} className="dodefi-box-4">{h.title}</button>
        {h.snippet && <div className="dodefi-sub6">{h.snippet}</div>}
      </div>
      <Button size="xs" variant={ya ? 'ghost' : 'secondary'} disabled={ya} icon={<Link2 size={12} />} onClick={onEnlazar}>
        {ya ? t('docs.ya_enlazado') : t('docs.enlazar')}
      </Button>
    </div>
  )
}

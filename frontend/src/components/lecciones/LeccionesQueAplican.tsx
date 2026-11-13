/**
 * «Lecciones que aplican» (revisión 2026-11): en un proyecto, un ticket o un
 * proyecto que se está creando, las lecciones parecidas con el porqué
 * («Evita: … — porque en PRJ-0007 pasó: …»), los motivos del parecido y la
 * pregunta de si sirvió, que es lo que mide la utilidad de la base.
 */
import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Lightbulb, ThumbsUp, Check, X } from 'lucide-react'
import { leccionesApi } from '../../services/api'
import type { Recomendacion } from '../../services/api'
import { Spinner } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import FichaDeLeccion from './FichaDeLeccion'
import { LIVE_VALIDATION_DEBOUNCE_MS, STALE_SHORT_MS } from '../../constants/timings'

const caja: CSSProperties = { border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)', padding: 14, background: 'var(--surface-1)', display: 'flex', flexDirection: 'column', gap: 10 }
const chip: CSSProperties = { fontSize: 'var(--text-xs)', color: 'var(--text-2)', border: '1px solid var(--surface-4)', borderRadius: 99, padding: '1px 8px' }

export default function LeccionesQueAplican({ contexto, id, campos }: {
  contexto: 'project' | 'ticket' | 'nuevo_proyecto'; id?: string; campos?: Record<string, unknown>
}) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [abierta, setAbierta] = useState<string | null>(null)
  // Al crear un proyecto los campos cambian con cada tecla: se consulta cuando se paran.
  const [camposQuietos, setCamposQuietos] = useState(campos)
  const firma = JSON.stringify(campos ?? {})
  useEffect(() => {
    const h = setTimeout(() => setCamposQuietos(JSON.parse(firma)), LIVE_VALIDATION_DEBOUNCE_MS)
    return () => clearTimeout(h)
  }, [firma])
  const clave = ['lecciones', 'recomendaciones', contexto, id ?? JSON.stringify(camposQuietos ?? {})]
  const q = useQuery({
    queryKey: clave, retry: false, staleTime: STALE_SHORT_MS,
    queryFn: () => contexto === 'nuevo_proyecto' ? leccionesApi.recomendacionesNuevo(camposQuietos ?? {}) : leccionesApi.recomendaciones(contexto, id!),
    enabled: contexto === 'nuevo_proyecto' ? Object.values(camposQuietos ?? {}).some(Boolean) : !!id,
  })
  const valorar = async (r: Recomendacion, valor: string) => {
    try {
      await leccionesApi.valorar(r.id, { contexto_tipo: contexto, contexto_id: id ?? null, valor })
      qc.invalidateQueries({ queryKey: clave })
      toast.success(t('lec.gracias'))
    } catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) }
  }
  const items = q.data?.items ?? []
  return (
    <section aria-label={t('lec.que_aplican')} style={caja}>
      <div className="u-row-center-8">
        <Lightbulb size={15} color="var(--warning)" aria-hidden />
        <strong style={{ fontSize: 'var(--text-sm)', color: 'var(--text-1)' }}>{t('lec.que_aplican')}</strong>
        {q.data && <span className="u-text3-xs">{t('lec.de_evaluadas', { n: items.length, total: q.data.evaluadas })}</span>}
      </div>
      {q.isLoading ? <Spinner size={16} />
        : q.isError ? <div role="alert" style={{ fontSize: 'var(--text-sm)', color: 'var(--danger)' }}>{extractErr(q.error, GENERIC_ERROR_FALLBACK)}</div>
        : items.length === 0 ? <div className="u-text3-sm">{t('lec.ninguna_aplica')}</div>
        : items.map(r => (
          <article key={r.id} style={{ borderLeft: `3px solid ${r.tipo === 'evitar' ? 'var(--danger)' : 'var(--success)'}`, padding: '4px 0 4px 10px' }}>
            <button type="button" onClick={() => setAbierta(r.id)} style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', textAlign: 'left', color: 'var(--text-1)', fontSize: 'var(--text-sm)', lineHeight: 1.5 }}>
              {r.frase}
            </button>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center', marginTop: 6 }}>
              <span style={{ ...chip, fontFamily: 'var(--font-mono)' }}>{r.codigo}</span>
              {r.motivos.map(m => <span key={m.clave} style={chip}>{t(`lec.motivo_${m.clave}`)}{m.detalle?.length ? `: ${m.detalle.join(', ')}` : ''}</span>)}
              <span style={{ marginLeft: 'auto', display: 'flex', gap: 4 }}>
                {([['util', ThumbsUp], ['aplicada', Check], ['no_aplica', X]] as const).map(([v, Icono]) => (
                  <button key={v} type="button" title={t(`lec.uso_${v}`)} aria-label={t(`lec.uso_${v}`)} aria-pressed={r.mi_valoracion === v} onClick={() => valorar(r, v)}
                    style={{ display: 'inline-flex', alignItems: 'center', gap: 4, background: r.mi_valoracion === v ? 'var(--accent-muted)' : 'transparent', color: r.mi_valoracion === v ? 'var(--accent)' : 'var(--text-3)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)', padding: '2px 8px', cursor: 'pointer', fontSize: 'var(--text-xs)' }}>
                    <Icono size={12} />{t(`lec.uso_${v}`)}
                  </button>
                ))}
              </span>
            </div>
          </article>
        ))}
      {abierta && <FichaDeLeccion id={abierta} onClose={() => setAbierta(null)} />}
    </section>
  )
}

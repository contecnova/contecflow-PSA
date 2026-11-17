/**
 * «Lecciones que aplican» (revisión 2026-11): en un proyecto, un ticket o un
 * proyecto que se está creando, las lecciones parecidas con el porqué
 * («Evita: … — porque en PRJ-0007 pasó: …»), los motivos del parecido y la
 * pregunta de si sirvió, que es lo que mide la utilidad de la base.
 */
import { type CSSProperties, useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Lightbulb, ThumbsUp, Check, X } from 'lucide-react'
import { leccionesApi } from '../../services/api'
import type { Recomendacion } from '../../services/api'
import { Button, Spinner, Pulsable } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import FichaDeLeccion from './FichaDeLeccion'
import { LIVE_VALIDATION_DEBOUNCE_MS, STALE_SHORT_MS } from '../../constants/timings'
import './LeccionesQueAplican.css'


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
    <section aria-label={t('lec.que_aplican')} className="lequap-caja">
      <div className="u-row-center-8">
        <Lightbulb size={15} color="var(--warning)" aria-hidden />
        <strong className="lequap-txt-1">{t('lec.que_aplican')}</strong>
        {q.data && <span className="u-text3-xs">{t('lec.de_evaluadas', { n: items.length, total: q.data.evaluadas })}</span>}
      </div>
      {q.isLoading ? <Spinner size={16} />
        : q.isError ? <div role="alert" className="lequap-txt-2">{extractErr(q.error, GENERIC_ERROR_FALLBACK)}</div>
        : items.length === 0 ? <div className="u-text3-sm">{t('lec.ninguna_aplica')}</div>
        : items.map(r => (
          <article className="lequap-sp-1 lecciones-que-aplican-e1" key={r.id} style={{ '--lecciones-que-aplican-border-left': `3px solid ${r.tipo === 'evitar' ? 'var(--danger)' : 'var(--success)'}` } as CSSProperties}>
            <Pulsable onClick={() => setAbierta(r.id)} className="lequap-box-1">
              {r.frase}
            </Pulsable>
            <div className="lequap-row-1">
              <span className="lequap-chip2">{r.codigo}</span>
              {r.motivos.map(m => <span key={m.clave} className="lequap-chip">{t(`lec.motivo_${m.clave}`)}{m.detalle?.length ? `: ${m.detalle.join(', ')}` : ''}</span>)}
              <span className="lequap-row-2">
                {([['util', ThumbsUp], ['aplicada', Check], ['no_aplica', X]] as const).map(([v, Icono]) => (
                  <Button key={v} size="xs" variant={r.mi_valoracion === v ? 'primary' : 'secondary'} icon={<Icono size={12} />}
                    title={t(`lec.uso_${v}`)} onClick={() => valorar(r, v)}>
                    {t(`lec.uso_${v}`)}
                  </Button>
                ))}
              </span>
            </div>
          </article>
        ))}
      {abierta && <FichaDeLeccion id={abierta} onClose={() => setAbierta(null)} />}
    </section>
  )
}

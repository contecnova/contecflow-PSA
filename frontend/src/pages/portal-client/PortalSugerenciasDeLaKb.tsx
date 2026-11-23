// Sugerencias de la base de conocimiento al redactar un ticket en el portal de cliente. 23-11-2026: troceado de PortalSupportDesk sin cambio de comportamiento.
import { useEffect, useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useToast } from '../../context/ToastContext'
import { CLIENT_API, useErrorDelPortal, useLang, useIdiomaDelPortal } from './portalClientContext'
import { PortalButton } from './PortalUI'
import { SLOW_INPUT_DEBOUNCE_MS } from '../../constants/timings'
import { Pulsable } from '../../components/ui'

/**
 * Mientras el cliente escribe el título, los artículos públicos que podrían
 * resolverle el problema. Si uno se lo resuelve, no abre la petición y queda
 * contado como desvío en el artículo.
 */
export function SugerenciasDeLaKb({ texto, onResuelto }: { texto: string; onResuelto: () => void }) {
  const traducir = useLang()
  const errorDe = useErrorDelPortal()
  const toast = useToast()
  const [consulta, setConsulta] = useState('')
  const [abierto, setAbierto] = useState<string | null>(null)
  const idioma = useIdiomaDelPortal()
  useEffect(() => {
    const h = setTimeout(() => setConsulta(texto.trim()), SLOW_INPUT_DEBOUNCE_MS)
    return () => clearTimeout(h)
  }, [texto])
  const { data: sugerencias = [] } = useQuery<{ id: string; title: string; summary?: string | null }[]>({
    queryKey: ['portal-kb-suggest', consulta, idioma],
    queryFn: () => CLIENT_API.get('/sd/kb/suggest', { params: { q: consulta, lang: idioma } }).then(r => r.data as { id: string; title: string; summary?: string | null }[]),
    enabled: consulta.length >= 4,
  })
  const { data: detalle } = useQuery<{ body?: string }>({
    queryKey: ['portal-kb-article', abierto, idioma],
    queryFn: () => CLIENT_API.get(`/sd/kb/${abierto}`, { params: { lang: idioma } }).then(r => r.data as { body?: string }),
    enabled: !!abierto,
  })
  const resuelto = useMutation({
    mutationFn: (id: string) => CLIENT_API.post(`/sd/kb/${id}/deflected`),
    onSuccess: () => { toast.success(traducir('sd_cfg.kb_solved_thanks')); onResuelto() },
    onError: (e: unknown) => toast.error(errorDe(e, traducir('error_inesperado'))),
  })
  if (consulta.length < 4 || sugerencias.length === 0) return null
  return (
    <div role="region" aria-label={traducir('sd_cfg.kb_suggest_title')}
      className="posude-stack-2">
      <strong className="u-sm">{traducir('sd_cfg.kb_suggest_title')}</strong>
      {sugerencias.slice(0, 3).map(a => (
        <div key={a.id} className="posude-box-16">
          <Pulsable onClick={() => setAbierto(abierto === a.id ? null : a.id)} aria-expanded={abierto === a.id}
            className="posude-box-17">
            {a.title}
          </Pulsable>
          {abierto === a.id && (
            <div className="posude-stack-3">
              <div className="posude-txt-3">{detalle?.body ?? a.summary ?? ''}</div>
              <div><PortalButton onClick={() => resuelto.mutate(a.id)} loading={resuelto.isPending}>{traducir('sd_cfg.kb_solved')}</PortalButton></div>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

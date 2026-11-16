/**
 * CatalogoInteligente — el catálogo inteligente en el formulario de un ticket
 * (mejoras de mercado 16-11-2026): servicios recomendados para quien pide, los
 * más pedidos, «Sugerir servicio» a partir de lo escrito y «Rellenar» el
 * formulario. Usa `/sd/catalog/smart/*`, que ya existía sin pantalla.
 */
import { useMutation, useQuery } from '@tanstack/react-query'
import { Sparkles, TrendingUp, Wand2 } from 'lucide-react'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { Button, StatusBadge } from '../ui'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { catalogoInteligenteApi } from '../../services/api/serviceDeskMercado'
import type { RellenoSugerido } from '../../services/api/serviceDeskMercado'
import './sdMercado.css'

export default function CatalogoInteligente({ texto, servicioId, onElegir, onRellenar }: {
  texto: string; servicioId?: string
  onElegir: (serviceId: string) => void; onRellenar: (r: RellenoSugerido) => void
}) {
  const t = useAppT()
  const toast = useToast()
  const err = (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  const recomendados = useQuery({ queryKey: ['sdm-smart-recs'], queryFn: () => catalogoInteligenteApi.recomendados() })
  const populares = useQuery({ queryKey: ['sdm-smart-popular'], queryFn: () => catalogoInteligenteApi.populares() })
  const sugerir = useMutation({
    mutationFn: () => catalogoInteligenteApi.sugerir(texto),
    onSuccess: r => { if (r.service_id) onElegir(r.service_id); else toast.info(t('sd_mercado.smart_sin_sugerencia')) },
    onError: err,
  })
  const rellenar = useMutation({
    mutationFn: () => catalogoInteligenteApi.rellenar(texto, servicioId),
    onSuccess: onRellenar,
    onError: err,
  })
  const chips = [...(recomendados.data ?? []), ...(populares.data ?? [])]
    .filter((s, i, a) => s.service_id && a.findIndex(x => x.service_id === s.service_id) === i).slice(0, 8)
  return (
    <div className="ds-card sdm-card">
      <div className="sdm-card__head"><Sparkles size={14} aria-hidden="true" />{t('sd_mercado.smart_titulo')}
        <span className="ds-toolbar__spacer" />
        <Button size="xs" variant="secondary" icon={<Wand2 size={12} />} onClick={() => sugerir.mutate()} loading={sugerir.isPending} disabled={texto.trim().length < 3}>{t('sd_mercado.smart_sugerir')}</Button>
        <Button size="xs" variant="ghost" onClick={() => rellenar.mutate()} loading={rellenar.isPending} disabled={texto.trim().length < 3}>{t('sd_mercado.smart_rellenar')}</Button>
      </div>
      {sugerir.data?.service_id && (
        <div className="u-text2-xs">{t('sd_mercado.smart_sugerido', { n: sugerir.data.service_name || '' })} · {etiquetaCodigo(t, 'sd_mercado.confianza_nivel', sugerir.data.confidence)}</div>
      )}
      {chips.length > 0 && (
        <div className="u-wrap-6">
          <TrendingUp size={12} aria-hidden="true" />
          {chips.map(s => (
            <button key={s.service_id} type="button" className="u-btn-outline-sm" aria-pressed={servicioId === s.service_id} onClick={() => onElegir(s.service_id)}>
              {s.service_name}{s.ticket_count ? <StatusBadge caps={false}>{s.ticket_count}</StatusBadge> : null}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

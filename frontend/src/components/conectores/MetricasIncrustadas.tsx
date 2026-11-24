/**
 * Métricas certificadas de contecintelligence incrustadas en el panel BI (23-11-2026).
 *
 * Es el `<ci-metric>` de contecintelligence hecho componente de la pantalla:
 *  - pide a contecflow un token ACOTADO (`POST /conectores/contecintelligence/token`,
 *    alcances de lectura, unos minutos); la credencial de la aplicación no sale
 *    del servidor;
 *  - con ese token llama DIRECTAMENTE a `<base_url>/metrics/query` (sin pasar
 *    por contecflow), con los permisos y el filtro de filas de quien mira;
 *  - solo si el origen de contecintelligence está en `CONTECINTELLIGENCE_EMBED_ORIGINS`
 *    (y por tanto en el `connect-src` de la CSP). Si no, no se muestra nada.
 *
 * Qué métricas se ven lo elige cada persona (se recuerda en este navegador).
 */
import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Sigma, X } from 'lucide-react'
import { conectoresApi } from '../../services/api'
import type { Metrica, TokenCI } from '../../services/api'
import { IconButton, Select, Spinner } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { localeActivo } from '../../utils/helpers'
import { STALE_DEFAULT_MS } from '../../constants/timings'

const CLAVE = 'contecflow.bi.metricas_ci'
const leer = (): string[] => { try { return JSON.parse(localStorage.getItem(CLAVE) || '[]') as string[] } catch { return [] } }
const guardar = (v: string[]) => { try { localStorage.setItem(CLAVE, JSON.stringify(v)) } catch { /* sin almacenamiento: solo esta sesión */ } }

type Salida = { label?: string; columns: string[]; rows: unknown[][]; governed?: boolean }

async function consultarDirecto(tok: TokenCI, m: Metrica): Promise<Salida> {
  const r = await fetch(`${tok.base_url}/metrics/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${tok.access_token}` },
    body: JSON.stringify({ source_id: m.source_id, query: { metric: m.name, dimensions: [], limit: 20 } }),
    credentials: 'omit',
  })
  if (!r.ok) throw new Error(String(r.status))
  return await r.json() as Salida
}

function Tarjeta({ m, tok, onQuitar }: { m: Metrica; tok: TokenCI; onQuitar: () => void }) {
  const t = useAppT()
  const q = useQuery({ queryKey: ['ci-incrustada', m.source_id, m.name, tok.access_token], queryFn: () => consultarDirecto(tok, m), retry: false })
  const unico = q.data && q.data.rows.length === 1 && q.data.rows[0].length === 1 ? q.data.rows[0][0] : undefined
  return (
    <div className="ds-card u-stack-8">
      <div className="u-row-between">
        <span className="u-text2-xs">{m.label}{q.data?.governed ? ` · ${t('ci.es_certificada')}` : ''}</span>
        <IconButton onClick={onQuitar} ariaLabel={t('ci_extra.quitar_metrica')}><X size={12} aria-hidden /></IconButton>
      </div>
      {q.isLoading ? <Spinner /> : q.isError ? <div className="u-text3-xs" role="alert">{t('ci_extra.incrustada_error')}</div>
        : unico !== undefined ? <div className="u-600">{typeof unico === 'number' ? unico.toLocaleString(localeActivo()) : String(unico ?? '—')}</div>
        : <div className="u-text2-xs">{t('ci_extra.n_filas', { n: q.data?.rows.length ?? 0 })}</div>}
    </div>
  )
}

export default function MetricasIncrustadas() {
  const t = useAppT()
  const disp = useQuery({ queryKey: ['conectores', 'ci-disponible'], queryFn: conectoresApi.ciDisponible, staleTime: STALE_DEFAULT_MS, retry: false })
  const analista = !!disp.data?.configurado && !!disp.data?.analista
  const tok = useQuery({
    queryKey: ['conectores', 'ci-token'], queryFn: () => conectoresApi.token(), enabled: analista, retry: false,
    // Se renueva antes de que caduque (el servidor dice cuánto dura).
    refetchInterval: d => { const s = d.state.data?.expires_in ?? 0; return s > 60 ? (s - 30) * 1000 : false },
  })
  const metricas = useQuery({ queryKey: ['conectores', 'ci-metricas'], queryFn: () => conectoresApi.metricas(), enabled: !!tok.data?.incrustable, retry: false })
  const [elegidas, setElegidas] = useState<string[]>(leer)
  useEffect(() => guardar(elegidas), [elegidas])
  if (!analista || !tok.data?.incrustable || !tok.data.access_token) return null
  const lista = metricas.data?.items ?? []
  const clave = (m: Metrica) => `${m.source_id}:${m.name}`
  const visibles = lista.filter(m => elegidas.includes(clave(m)))
  return (
    <section className="bi-panel" aria-labelledby="bi-metricas-ci">
      <h2 id="bi-metricas-ci" className="bi-panel__title"><Sigma size={14} aria-hidden="true" /> {t('ci_extra.incrustadas_titulo')}</h2>
      <p className="u-text3-xs">{t('ci_extra.incrustadas_ayuda')}</p>
      <div className="u-wrap-center-8">
        <Select suelto placeholder={false} aria-label={t('ci_extra.anadir_metrica')} value="" onChange={e => e.target.value && setElegidas(v => [...new Set([...v, e.target.value])])}>
          <option value="">{t('ci_extra.anadir_metrica')}</option>
          {lista.filter(m => !elegidas.includes(clave(m))).map(m => <option key={clave(m)} value={clave(m)}>{m.label}</option>)}
        </Select>
      </div>
      <div className="ds-grid-stats">
        {visibles.map(m => <Tarjeta key={clave(m)} m={m} tok={tok.data as TokenCI} onQuitar={() => setElegidas(v => v.filter(x => x !== clave(m)))} />)}
      </div>
    </section>
  )
}

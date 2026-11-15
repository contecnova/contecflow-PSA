/**
 * «Por qué» de una entidad (rev. 166, tarea #27): la última evaluación guardada
 * de `GET /policies/explanations/{dominio}/{id}` —decisión, niveles añadidos,
 * avisos, requisitos y a quién se informó— y la traza de cada política. La ven
 * el dueño, quien la aprueba y un administrador (el servidor lo comprueba).
 */
import { useQuery } from '@tanstack/react-query'
import { politicasApi } from '../../services/api'
import { Spinner } from '../ui'
import { extractErr } from '../../utils/helpers'
import { useTextos } from './comun'
import { Explicacion } from './Simulador'

export default function ExplicacionDeEntidad({ dominio, entidadId }: { dominio: string; entidadId: string }) {
  const { t } = useTextos()
  const q = useQuery({
    queryKey: ['politicas', 'explicacion', dominio, entidadId],
    queryFn: () => politicasApi.explicaciones(dominio, entidadId),
    retry: false,
  })
  if (q.isLoading) return <Spinner size={16} label={t('pol.cargando')} />
  if (q.isError) return <div role="alert" className="pol-error">{extractErr(q.error, t('pol.error_cargar'))}</div>
  const ev = q.data?.evaluaciones?.[0]
  if (!ev) return <p className="pol-ayuda">{t('pol.sin_evaluaciones')}</p>
  const r = ev.resultado ?? {}
  const niveles = (r.niveles ?? 0) + (r.pasos ?? []).length
  return (
    <div className="pol-explicacion">
      <div className="pol-fila">
        <span className={`pol-chip pol-chip--${ev.decision}`}>{t(`pol.decision_${ev.decision}`)}</span>
        {niveles > 0 && <span className="pol-chip pol-chip--review">{t('pol.n_niveles', { n: niveles })}</span>}
        {ev.created_at && <span className="pol-ayuda">{t('pol.evaluado_el', { fecha: ev.created_at.slice(0, 16).replace('T', ' ') })}</span>}
      </div>
      {(r.avisos ?? []).length > 0 && (
        <ul aria-label={t('pol.avisos')}>
          {(r.avisos ?? []).map((a, i) => <li key={i}>{a.mensaje}{a.politica ? <span className="pol-ayuda"> · {a.politica}</span> : null}</li>)}
        </ul>
      )}
      {(r.requisitos ?? []).length > 0 && (
        <ul aria-label={t('pol.requisitos')}>
          {(r.requisitos ?? []).map((q2, i) => (
            <li key={i}>{q2.mensaje || t(`pol.res_${q2.tipo}`)}
              {(q2.tipos_de_documento ?? []).length > 0 && <span className="pol-ayuda"> · {(q2.tipos_de_documento ?? []).map(d => t(`pol.doc_${d}`, d)).join(', ')}</span>}
            </li>
          ))}
        </ul>
      )}
      {(r.avisar ?? []).length > 0 && (
        <ul aria-label={t('pol.informados')}>
          {(r.avisar ?? []).map((a, i) => <li key={i}>{t('pol.se_informo', { politica: a.politica ?? '' })}{a.mensaje ? `: ${a.mensaje}` : ''}</li>)}
        </ul>
      )}
      <Explicacion politicas={ev.explicacion?.politicas ?? []} />
    </div>
  )
}

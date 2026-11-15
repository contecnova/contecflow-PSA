/**
 * Lecciones en la ficha de un proyecto o un ticket (revisión 2026-11):
 * las que aplican (aprendidas en otros casos) y las que salieron de éste, con
 * el botón para registrar una desde sus hechos. Cerrado y sin lección, lo pide.
 */
import { type CSSProperties, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { leccionesApi } from '../../services/api'
import { Button } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import FormularioDeLeccion from './FormularioDeLeccion'
import FichaDeLeccion, { ColorDeEstado } from './FichaDeLeccion'
import LeccionesQueAplican from './LeccionesQueAplican'
import './LeccionesDeOrigen.css'

export default function LeccionesDeOrigen({ id, origen = 'project', cerrado = false }: {
  id: string; origen?: 'project' | 'ticket'; cerrado?: boolean
}) {
  const t = useAppT()
  const qc = useQueryClient()
  const [nueva, setNueva] = useState(false)
  const [abierta, setAbierta] = useState<string | null>(null)
  const propias = useQuery({ queryKey: ['lecciones', 'de', origen, id], queryFn: () => leccionesApi.deOrigen(origen, id), retry: false })
  const lista = propias.data?.items ?? []
  return (
    <div className="u-stack-12">
      <LeccionesQueAplican contexto={origen} id={id} />
      <section aria-label={t(`lec.de_este_${origen}`)} className="ledeor-box-1">
        <div className="ledeor-row-1">
          <strong className="u-sm">{t(`lec.de_este_${origen}`)}</strong>
          <Button size="sm" variant={cerrado && !lista.length ? 'primary' : 'secondary'} icon={<Plus size={13} />} className="leccione-sx1" onClick={() => setNueva(true)}>
            {t('lec.registrar')}
          </Button>
        </div>
        {cerrado && !lista.length && !propias.isLoading && (
          <div role="status" className="ledeor-box-2">{t(`lec.cerrado_sin_leccion_${origen}`)}</div>
        )}
        {lista.length === 0 ? <div className="u-text3-sm">{t('lec.ninguna_registrada')}</div>
          : lista.map(l => (
            <button key={l.id} type="button" onClick={() => setAbierta(l.id)} className="ledeor-row-2">
              <span className="ledeor-txt-1">{l.codigo}</span>
              <span className="u-flex1">{l.titulo}</span>
              <span className="ledeor-txt-2 lecciones-de-origen-e1" style={{ '--lecciones-de-origen-color': ColorDeEstado(l.estado) } as CSSProperties}>{t(`lec.estado_${l.estado}`)}</span>
            </button>
          ))}
      </section>
      {nueva && <FormularioDeLeccion origen={{ tipo: origen, id }} onClose={() => setNueva(false)}
        onGuardada={l => { setNueva(false); qc.invalidateQueries({ queryKey: ['lecciones'] }); setAbierta(l.id) }} />}
      {abierta && <FichaDeLeccion id={abierta} onClose={() => setAbierta(null)} />}
    </div>
  )
}

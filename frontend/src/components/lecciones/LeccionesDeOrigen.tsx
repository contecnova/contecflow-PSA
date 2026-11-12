/**
 * Lecciones en la ficha de un proyecto o un ticket (revisión 2026-11):
 * las que aplican (aprendidas en otros casos) y las que salieron de éste, con
 * el botón para registrar una desde sus hechos. Cerrado y sin lección, lo pide.
 */
import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { leccionesApi } from '../../services/api'
import { Button } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import FormularioDeLeccion from './FormularioDeLeccion'
import FichaDeLeccion, { ColorDeEstado } from './FichaDeLeccion'
import LeccionesQueAplican from './LeccionesQueAplican'

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
      <section aria-label={t(`lec.de_este_${origen}`)} style={{ border: '1px solid var(--surface-4)', borderRadius: 10, padding: 14, background: 'var(--surface-1)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <strong className="u-sm">{t(`lec.de_este_${origen}`)}</strong>
          <Button size="sm" variant={cerrado && !lista.length ? 'primary' : 'secondary'} icon={<Plus size={13} />} style={{ marginLeft: 'auto' }} onClick={() => setNueva(true)}>
            {t('lec.registrar')}
          </Button>
        </div>
        {cerrado && !lista.length && !propias.isLoading && (
          <div role="status" style={{ fontSize: 'var(--text-sm)', color: 'var(--warning)', marginBottom: 6 }}>{t(`lec.cerrado_sin_leccion_${origen}`)}</div>
        )}
        {lista.length === 0 ? <div className="u-text3-sm">{t('lec.ninguna_registrada')}</div>
          : lista.map(l => (
            <button key={l.id} type="button" onClick={() => setAbierta(l.id)} style={{ display: 'flex', gap: 10, width: '100%', alignItems: 'center', background: 'none', border: 'none', borderTop: '1px solid var(--surface-3)', padding: '7px 0', cursor: 'pointer', textAlign: 'left', color: 'var(--text-1)', fontSize: 'var(--text-sm)' }}>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>{l.codigo}</span>
              <span className="u-flex1">{l.titulo}</span>
              <span style={{ fontSize: 'var(--text-xs)', color: ColorDeEstado(l.estado) }}>{t(`lec.estado_${l.estado}`)}</span>
            </button>
          ))}
      </section>
      {nueva && <FormularioDeLeccion origen={{ tipo: origen, id }} onClose={() => setNueva(false)}
        onGuardada={l => { setNueva(false); qc.invalidateQueries({ queryKey: ['lecciones'] }); setAbierta(l.id) }} />}
      {abierta && <FichaDeLeccion id={abierta} onClose={() => setAbierta(null)} />}
    </div>
  )
}

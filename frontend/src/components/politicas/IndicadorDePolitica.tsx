/**
 * Indicador compacto del resultado de las políticas (rev. 166, tarea #27): en
 * la lista de gastos y en la bandeja de quien aprueba. Dice si se excedió una
 * política, en qué porcentaje y cuántos niveles de aprobación añadió.
 */
import { ShieldAlert } from 'lucide-react'
import type { ResumenDePolitica } from '../../services/api/tipos-politicas'
import { useTextos } from './comun'

export default function IndicadorDePolitica({ resumen }: { resumen: ResumenDePolitica | null | undefined }) {
  const { t } = useTextos()
  if (!resumen) return null
  const niveles = (resumen.niveles ?? 0) + (resumen.pasos ?? 0)
  const avisos = (resumen.avisos ?? []).length
  const exceso = resumen.exceso_pct
  if (!niveles && !avisos && (exceso === null || exceso === undefined)) return null
  const titulo = [
    exceso !== null && exceso !== undefined ? t('pol.ind_exceso', { pct: exceso.toLocaleString(undefined, { maximumFractionDigits: 1 }) }) : '',
    niveles ? t('pol.n_niveles', { n: niveles }) : '',
    avisos ? t('pol.n_avisos', { n: avisos }) : '',
    (resumen.politicas ?? []).join(', '),
  ].filter(Boolean).join(' · ')
  return (
    <span className="pol-indicador" title={titulo} aria-label={t('pol.ind_aria', { detalle: titulo })} role="note">
      <ShieldAlert size={12} aria-hidden />
      {exceso !== null && exceso !== undefined && exceso > 0 && (
        <span className="pol-chip pol-chip--review">+{exceso.toLocaleString(undefined, { maximumFractionDigits: 1 })} %</span>
      )}
      {niveles > 0 && <span className="pol-chip pol-chip--review">{t('pol.n_niveles', { n: niveles })}</span>}
      {avisos > 0 && !niveles && <span className="pol-chip">{t('pol.n_avisos', { n: avisos })}</span>}
    </span>
  )
}

/**
 * Plantilla del Executive Summary (22-11-2026): título en tres idiomas, campos
 * que se incluyen, fases cuyo dictamen se cita e historial. Sirve para la fase
 * de comité y para la acción de cierre `executive_summary`.
 */
import { Checkbox, GrupoDeOpciones } from '../ui'
import type { DefinicionDeFlujo, PlantillaDeResumen } from '../../services/api/demanda'
import { useAppT } from '../../i18n/AppLangContext'
import { CamposI18n } from './comunes'
import './demanda.css'

export default function EditorDePlantillaResumen({ valor, onChange, def }: { valor: PlantillaDeResumen; onChange: (v: PlantillaDeResumen) => void; def: DefinicionDeFlujo }) {
  const t = useAppT()
  return (
    <div className="u-stack-12">
      <CamposI18n etiqueta={t('demanda.cfg_titulo_resumen')} valor={valor.title} onChange={v => onChange({ ...valor, title: v })} />
      {def.fields.length > 0 && (
        <GrupoDeOpciones tipo="checkbox" forma="fila" leyenda={t('demanda.cfg_resumen_campos')} valor={valor.fields || []} onChange={v => onChange({ ...valor, fields: v })}
          opciones={def.fields.map(c => ({ valor: c.key, titulo: c.label.es || c.key }))} />
      )}
      {def.phases.length > 0 && (
        <GrupoDeOpciones tipo="checkbox" forma="fila" leyenda={t('demanda.cfg_resumen_dictamenes')} valor={valor.opinion_phases || []} onChange={v => onChange({ ...valor, opinion_phases: v })}
          opciones={def.phases.map(f => ({ valor: f.key, titulo: f.name.es || f.key }))} />
      )}
      <Checkbox label={t('demanda.cfg_resumen_historial')} checked={!!valor.include_history} onChange={ok => onChange({ ...valor, include_history: ok })} />
    </div>
  )
}

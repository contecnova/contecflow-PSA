/**
 * Pestaña «Riesgo» de la CMDB (22-11-2026): índice de riesgo 0-100 por ámbito
 * (empresa, cliente/unidad, servicio, máquina, aplicación) y gestión de
 * vulnerabilidades: plan de reducción, métricas, superficies y vistas,
 * controles compensatorios e intentos de explotación, importación de terceros
 * e informes programados. La pinta CMDBPage a quien tiene `software.ver`;
 * escribir pide `software.gestionar` (el servidor lo vuelve a mirar).
 *
 * Diseño: docs/CMDB_SOFTWARE_Y_VULNERABILIDADES.md §11. Datos:
 * services/api/cmdbRiesgo.ts. Textos: espacio `swr` de es/en/zh.
 */
import { useState } from 'react'
import { useAppT } from '../../../../i18n/AppLangContext'
import type { Ambito } from '../../../../services/api/cmdbRiesgo'
import { Tabs } from '../../../ui'
import SelectorDeAmbito from './SelectorDeAmbito'
import Indice from './Indice'
import Plan from './Plan'
import Metricas from './Metricas'
import Superficies from './Superficies'
import Controles from './Controles'
import Importar from './Importar'
import Informes from './Informes'
import '../../../servicedesk/sdMercado.css'
import '../software.css'
import './riesgo.css'

type Sub = 'indice' | 'plan' | 'metricas' | 'superficies' | 'controles' | 'importar' | 'informes'
const SUBS: Sub[] = ['indice', 'plan', 'metricas', 'superficies', 'controles', 'importar', 'informes']
/** Las que dependen del ámbito elegido (el resto es de toda la empresa). */
const CON_AMBITO: Sub[] = ['indice', 'plan', 'metricas']

export function RiesgoTab() {
  const t = useAppT()
  const [sub, setSub] = useState<Sub>('indice')
  const [ambito, setAmbito] = useState<Ambito>({ scope_type: 'org', scope_id: null })
  // Sin entidad elegida en un ámbito que la pide, se enseña el de la empresa.
  const efectivo: Ambito = ambito.scope_type !== 'org' && !ambito.scope_id ? { scope_type: 'org', scope_id: null } : ambito
  return (
    <div className="u-stack-20">
      <Tabs ariaLabel={t('swr.tab_riesgo')} active={sub} onChange={id => setSub(id as Sub)}
        items={SUBS.map(s => ({ id: s, label: t(`swr.sub_${s}`) }))} />
      {CON_AMBITO.includes(sub) && (
        <div className="u-stack-6">
          <SelectorDeAmbito valor={ambito} onChange={setAmbito} />
          {ambito.scope_type !== 'org' && !ambito.scope_id && <div className="u-text3-xs">{t('swr.ambito_sin_entidad')}</div>}
        </div>
      )}
      {sub === 'indice' && <Indice ambito={efectivo} onElegirAmbito={setAmbito} />}
      {sub === 'plan' && <Plan ambito={efectivo} />}
      {sub === 'metricas' && <Metricas ambito={efectivo} />}
      {sub === 'superficies' && <Superficies />}
      {sub === 'controles' && <Controles />}
      {sub === 'importar' && <Importar />}
      {sub === 'informes' && <Informes />}
    </div>
  )
}

export default RiesgoTab

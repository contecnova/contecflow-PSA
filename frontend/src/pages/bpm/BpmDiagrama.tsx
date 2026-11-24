/**
 * Diagrama BPMN de solo lectura con marcas: dónde está una instancia (pasos
 * pendientes, hechos, incidentes) o el recorrido de una simulación.
 *
 * Revisión BPM 23-11-2026 (docs/BPM.md, «Seguir una instancia»): el detalle de
 * una instancia solo tenía la tabla de pasos; ahora se ve sobre el diagrama de
 * SU versión. bpmn-js se carga bajo demanda, como en el editor.
 */
import { useEffect, useRef, useState } from 'react'
import type BaseViewer from 'bpmn-js/lib/BaseViewer'
import type Canvas from 'diagram-js/lib/core/Canvas'
import { useAppLang } from '../../i18n/AppLangContext'
import './BpmRunPanel.css'

type Props = {
  xml: string | null | undefined
  activos?: string[]
  hechos?: string[]
  incidentes?: string[]
  alto?: 'normal' | 'bajo'
}

export default function BpmDiagrama({ xml, activos = [], hechos = [], incidentes = [], alto = 'normal' }: Props): JSX.Element {
  const { t } = useAppLang()
  const ref = useRef<HTMLDivElement>(null)
  const [fallo, setFallo] = useState(false)
  const marcas = JSON.stringify([activos, hechos, incidentes])

  useEffect(() => {
    let visor: BaseViewer | null = null
    let vigente = true
    setFallo(false)
    if (!ref.current || !xml) return
    const [act, hec, inc] = JSON.parse(marcas) as [string[], string[], string[]]
    ;(async () => {
      await Promise.all([
        import('bpmn-js/dist/assets/diagram-js.css'),
        import('bpmn-js/dist/assets/bpmn-font/css/bpmn.css'),
      ])
      const { default: Visor } = await import('bpmn-js/lib/NavigatedViewer')
      if (!vigente || !ref.current) return
      visor = new Visor({ container: ref.current })
      await visor.importXML(xml)
      const canvas = visor.get<Canvas>('canvas')
      canvas.zoom('fit-viewport', { x: 0, y: 0 })
      const poner = (ids: string[], clase: string) => ids.forEach(id => {
        try { canvas.addMarker(id, clase) } catch { /* elemento sin forma en el diagrama (p. ej. de otra versión): sin marca */ }
      })
      poner(hec, 'bpm-marca-hecho')
      poner(act, 'bpm-marca-activo')
      poner(inc, 'bpm-marca-incidente')
    })().catch(() => { if (vigente) setFallo(true) })
    return () => {
      vigente = false
      try { visor?.destroy() } catch { /* accesorio: liberar un visor ya roto */ }
    }
  }, [xml, marcas])

  if (!xml) return <></>
  return (
    <div className="bpm-diagrama">
      {fallo && <div role="alert" className="bprupa-box-2">{t('bpm.error_diagrama')}</div>}
      <div ref={ref} className={`bpm-diagrama__lienzo${alto === 'bajo' ? ' bpm-diagrama__lienzo--bajo' : ''}`}
        role="img" aria-label={t('bpm.diagrama_de_la_instancia')} />
      <div className="bpm-diagrama__leyenda" aria-hidden="true">
        <span className="bpm-leyenda bpm-leyenda--activo">{t('bpm.leyenda_pendiente')}</span>
        <span className="bpm-leyenda bpm-leyenda--hecho">{t('bpm.leyenda_hecho')}</span>
        <span className="bpm-leyenda bpm-leyenda--incidente">{t('bpm.leyenda_incidente')}</span>
      </div>
    </div>
  )
}

// Las condiciones de las alertas del BI (`trend_down`...) llegan como código
// del backend: se traducen por `condicion_alerta.<codigo>` en es/en/zh y un
// código desconocido se ve tal cual, nunca una clave interna.
import { describe, expect, it } from 'vitest'
import { etiquetaCodigo } from '../etiquetaCodigo'
import en from '../langs/en.mjs'
import es from '../langs/es.mjs'
import zh from '../langs/zh.mjs'

const CODIGOS = ['threshold_above', 'threshold_below', 'trend_up', 'trend_down', 'anomaly']
const idiomas = { es, en, zh } as unknown as Record<string, { condicion_alerta: Record<string, string> }>

describe('condicion_alerta', () => {
  it.each(Object.keys(idiomas))('%s define todas las condiciones sin dejar el código', (l) => {
    for (const c of CODIGOS) {
      const texto = idiomas[l].condicion_alerta[c]
      expect(texto, `${l}.${c}`).toBeTruthy()
      expect(texto).not.toBe(c)
    }
  })

  it('etiquetaCodigo usa el diccionario y cae al código si no existe', () => {
    const t = ((clave: string, resp?: string) => {
      const [m, k] = clave.split('.')
      return (es as unknown as Record<string, Record<string, string>>)[m]?.[k] ?? resp ?? clave
    }) as never
    expect(etiquetaCodigo(t, 'condicion_alerta', 'trend_down')).toBe('Tendencia a la baja')
    expect(etiquetaCodigo(t, 'condicion_alerta', 'nueva_condicion')).toBe('nueva_condicion')
  })
})

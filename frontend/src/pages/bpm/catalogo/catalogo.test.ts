import { describe, it, expect } from 'vitest'
import { ESTRUCTURA_CATALOGO } from './estructura'
import es from './textos/es'
import en from './textos/en'
import zh from './textos/zh'
import { es as dic } from '../../../i18n/appTranslations.mjs'
import { construirCatalogo } from './index'
describe('catalogo', () => {
  it('claves', () => {
    const t = (k: string) => k
    let total = 0
    for (const [n, d] of [['es', es], ['en', en], ['zh', zh]] as const) {
      expect(Object.keys(d).sort()).toEqual(ESTRUCTURA_CATALOGO.map(e => e.id).sort())
      let c = 0
      for (const e of ESTRUCTURA_CATALOGO) {
        const x = d[e.id]
        expect(x.steps.length, `${n} ${e.id} steps`).toBe(e.pasos)
        expect(Object.keys(x.nodes).sort(), `${n} ${e.id} nodes`).toEqual(e.nodos.filter(o => !o.sinNombre).map(o => o.id).sort())
        expect(x.flows.length, `${n} ${e.id} flows`).toBe(e.flujos.filter(f => f[2]).length)
        expect(!!x.sla, `${n} ${e.id} sla`).toBe(e.slaDiasHabiles === undefined)
        expect(!!x.diagrama, `${n} ${e.id} diag`).toBe(!!es[e.id].diagrama)
        for (const v of [x.name, x.description, x.owner, ...x.steps, ...x.flows, ...Object.values(x.nodes)]) expect(v.trim().length).toBeGreaterThan(0)
        c += 3 + x.steps.length + Object.keys(x.nodes).length + x.flows.length + (x.sla ? 1 : 0)
      }
      total = c
      construirCatalogo(d, t)
    }
    for (const k of ['sla_dia_habil','sla_dias_habiles','blank_proceso','blank_inicio','blank_actividad','blank_fin']) expect((dic as unknown as Record<string, Record<string, string>>).bpm[k]).toBeTruthy()
    expect(total).toBeGreaterThan(600)
  })
})

import { describe, expect, it } from 'vitest'
import { ESTRUCTURA_CATALOGO } from './estructura'
import { ESTRUCTURA_LINEAL } from './estructuraLineal'
import { cargarTextosCatalogo, construirCatalogo, construirLineales } from './index'
import zhPropio from './textos/zh'
import en from './textosLineales/en'
import es from './textosLineales/es'
import zh from './textosLineales/zh'

const CATEGORIAS_DE_LA_PAGINA = ['proyectos', 'finanzas', 'rrhh', 'servicedesk', 'crm', 'admin']
const t = (k: string) => k

describe('procesos lineales del catálogo (los 40 sembrados por el backend; 24-11-2026: + portal_conversation)', () => {
  it('son 40, sin colisión con los procesos de diagrama propio', () => {
    expect(ESTRUCTURA_LINEAL).toHaveLength(40)
    const propios = new Set(ESTRUCTURA_CATALOGO.map((e) => e.id))
    const ids = ESTRUCTURA_LINEAL.map((e) => e.id)
    expect(new Set(ids).size).toBe(ids.length)
    for (const id of ids) expect(propios.has(id), id).toBe(false)
  })

  it('cada idioma tiene exactamente los mismos procesos y el mismo número de pasos', () => {
    const ids = ESTRUCTURA_LINEAL.map((e) => e.id).sort()
    for (const [idioma, d] of [['es', es], ['en', en], ['zh', zh]] as const) {
      expect(Object.keys(d).sort(), idioma).toEqual(ids)
      for (const e of ESTRUCTURA_LINEAL) {
        const x = d[e.id]
        expect(x.steps.length, `${idioma} ${e.id}`).toBe(e.pasos)
        for (const v of [x.name, x.description, ...x.steps]) expect(v.trim().length, `${idioma} ${e.id}`).toBeGreaterThan(0)
      }
    }
  })

  it('la categoría de cada uno es una de las que filtra la página', () => {
    for (const e of ESTRUCTURA_LINEAL) expect(CATEGORIAS_DE_LA_PAGINA, e.id).toContain(e.category)
  })

  it('el inglés y el chino no son copia del castellano', () => {
    for (const e of ESTRUCTURA_LINEAL) {
      expect(en[e.id].name === es[e.id].name && en[e.id].description === es[e.id].description, `en ${e.id}`).toBe(false)
      expect(zh[e.id].name, `zh ${e.id}`).not.toBe(es[e.id].name)
    }
  })

  it('el diagrama lleva los pasos del idioma: inicio, tareas y fin', () => {
    const xmlEn = construirLineales(en).find((p) => p.id === 'invoice_workflow')!.bpmn
    const xmlZh = construirLineales(zh).find((p) => p.id === 'invoice_workflow')!.bpmn
    expect(xmlEn).toContain('<bpmn:startEvent id="StartEvent_1" name="Draft">')
    expect(xmlEn).toContain('<bpmn:endEvent id="EndEvent_5" name="Closed">')
    expect(xmlEn).toContain('name="Issued"')
    expect(xmlZh).toContain('name="已开具"')
    expect(xmlZh).not.toContain('Emitida')
  })

  it('construirCatalogo los añade a los de diagrama propio y sin ellos sigue igual que antes', () => {
    const sin = construirCatalogo(zhPropio, t)
    expect(sin.some((p) => p.id === 'invoice_workflow')).toBe(false)
    const con = construirCatalogo(zhPropio, t, zh)
    expect(con.length).toBe(sin.length + 40)  // 24-11-2026: + portal_conversation
  })

  it('no inventa responsable ni SLA que el origen no tiene', () => {
    for (const p of construirLineales(en)) {
      expect(p.owner).toBe('')
      expect(p.sla).toBe('')
    }
  })

  it('carga los textos lineales por idioma y cae al castellano con uno desconocido', async () => {
    expect((await cargarTextosCatalogo('zh')).lineales.invoice_workflow.name).toBe(zh.invoice_workflow.name)
    expect((await cargarTextosCatalogo('xx')).lineales.invoice_workflow.name).toBe(es.invoice_workflow.name)
  })
})

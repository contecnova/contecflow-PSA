import { describe, it, expect } from 'vitest'
import en from './textos/en'
import zh from './textos/zh'
import { construirCatalogo, cargarTextosCatalogo } from './index'

const t = (k: string, p?: Record<string, unknown>) => `${k}:${p?.n ?? ''}`

describe('construirCatalogo', () => {
  it('formatea el SLA numérico con la clave del idioma y deja el textual tal cual', () => {
    const lista = construirCatalogo(en, t)
    expect(lista.find(p => p.id === 'proj_creation')?.sla).toBe('bpm.sla_dias_habiles:3')
    expect(lista.find(p => p.id === 'sprint_planning')?.sla).toBe('bpm.sla_dia_habil:1')
    expect(lista.find(p => p.id === 'task_lifecycle')?.sla).toBe('Per estimate')
  })

  it('pone el texto de cada idioma en el XML del diagrama, etiquetas de flujo incluidas', () => {
    const xmlEn = construirCatalogo(en, t).find(p => p.id === 'proj_creation')!.bpmn
    const xmlZh = construirCatalogo(zh, t).find(p => p.id === 'proj_creation')!.bpmn
    expect(xmlEn).toContain('name="Approved?"')
    expect(xmlEn).toContain('name="Yes"')
    expect(xmlZh).toContain('name="是否批准？"')
    expect(xmlZh).toContain('name="是"')
    expect(xmlZh).not.toContain('Aprobado')
  })

  it('carga los textos por idioma y cae al castellano con un idioma desconocido', async () => {
    expect((await cargarTextosCatalogo('zh')).lang).toBe('zh')
    expect((await cargarTextosCatalogo('xx')).lang).toBe('es')
  })
})

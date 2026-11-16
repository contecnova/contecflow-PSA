// Externos como internos: la marca «Externo · proveedor» y el formulario del externo.
import { vi, describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('../i18n/AppLangContext', () => ({
  useAppLang: () => ({ t: traducir, lang: 'es' }),
  useAppT: () => traducir,
}))

function traducir(clave: string, params?: string | Record<string, unknown>): string {
  const p = typeof params === 'object' && params ? params : {}
  if (clave === 'uikit.externo') return 'Externo'
  if (clave === 'uikit.externo_de') return `Externo · ${String(p.empresa)}`
  return clave
}

import MarcaExterno, { esExterno, etiquetaDePersona, textoMarcaExterno } from '../components/ui/MarcaExterno'
import { cargaDeExterno, estadoDeAcceso, externoCompleto, finDeAccesoEfectivo, formularioDeExternoInicial } from '../components/externos/FormularioDeExterno'

describe('marca de externo', () => {
  it('reconoce al externo por rol o por proveedor', () => {
    expect(esExterno({ role: 'subcontractor' })).toBe(true)
    expect(esExterno({ role: 'developer', external_company: 'Acme' })).toBe(true)
    expect(esExterno({ role: 'employee', external_company: null })).toBe(false)
    expect(esExterno({ role: 'employee', external_company: '  ' })).toBe(false)
    expect(esExterno(null)).toBe(false)
  })

  it('compone el texto con y sin proveedor', () => {
    expect(textoMarcaExterno(traducir, { role: 'subcontractor', external_company: 'Acme' })).toBe('Externo · Acme')
    expect(textoMarcaExterno(traducir, { role: 'subcontractor', external_company: null })).toBe('Externo')
    expect(textoMarcaExterno(traducir, { role: 'pm' })).toBeNull()
  })

  it('etiqueta de persona: nombre y marca solo si es externo', () => {
    expect(etiquetaDePersona(traducir, { full_name: 'Ana Ruiz', role: 'subcontractor', external_company: 'Acme' })).toBe('Ana Ruiz · Externo · Acme')
    expect(etiquetaDePersona(traducir, { full_name: 'Luis Gil', role: 'employee' })).toBe('Luis Gil')
  })

  it('la pastilla no pinta nada para un interno', () => {
    const { container } = render(<MarcaExterno persona={{ role: 'employee' }} />)
    expect(container.textContent).toBe('')
    render(<MarcaExterno persona={{ role: 'subcontractor', external_company: 'Acme' }} />)
    expect(screen.getByText('Externo · Acme')).toBeTruthy()
  })
})

describe('formulario del externo', () => {
  it('estado de acceso según login y fecha de fin', () => {
    expect(estadoDeAcceso({ has_access: false, access_until: '2026-12-31' }, '2026-11-16')).toBe('sin_acceso')
    expect(estadoDeAcceso({ has_access: true, access_until: null }, '2026-11-16')).toBe('con_acceso')
    expect(estadoDeAcceso({ has_access: true, access_until: '2026-12-31' }, '2026-11-16')).toBe('caduca')
    expect(estadoDeAcceso({ has_access: true, access_until: '2026-11-01' }, '2026-11-16')).toBe('caducado')
  })

  it('fin de acceso por defecto = disponible hasta; sin acceso, null', () => {
    const base = formularioDeExternoInicial(null, 'EUR')
    expect(finDeAccesoEfectivo({ ...base, available_until: '2027-03-31' })).toBe('2027-03-31')
    expect(finDeAccesoEfectivo({ ...base, available_until: '2027-03-31', access_until: '2027-01-15', access_until_manual: true })).toBe('2027-01-15')
    expect(finDeAccesoEfectivo({ ...base, has_access: false, available_until: '2027-03-31' })).toBeNull()
  })

  it('exige nombre y responsable interno; la carga normaliza números y vacíos', () => {
    const f = { ...formularioDeExternoInicial(null, 'EUR'), name: ' Ana ', cost_rate: '45.5', sell_rate: '', internal_owner_id: 'u1' }
    expect(externoCompleto({ ...f, internal_owner_id: '' })).toBe(false)
    expect(externoCompleto(f)).toBe(true)
    const carga = cargaDeExterno(f)
    expect(carga).toMatchObject({ name: 'Ana', cost_rate: 45.5, sell_rate: null, currency: 'EUR', has_access: true, internal_owner_id: 'u1', weekly_capacity_hours: 40, email: null })
  })
})

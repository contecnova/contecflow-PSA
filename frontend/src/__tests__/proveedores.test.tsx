// Proveedores y externalización (19-11-2026, migración 189): alta con elección de
// tipo, exclusión asignado/proveedor en tareas, pestañas de la ficha por tipo,
// rutas de `/suppliers` y la sección de Configuración. Ver
// docs/PROVEEDORES_Y_EXTERNALIZACION.md.
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

const { http, barril } = vi.hoisted(() => ({
  http: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  barril: {
    usersApi: { directory: vi.fn() },
    subcontractorsApi: { create: vi.fn() },
    vendorsApi: { list: vi.fn() },
  },
}))

function traducir(clave: string, params?: string | Record<string, unknown>): string {
  const p = typeof params === 'object' && params ? params : {}
  return Object.keys(p).length ? `${clave}:${Object.values(p).join(',')}` : clave
}

vi.mock('../services/api/_core', () => ({ default: http }))
vi.mock('../services/api', () => barril)
vi.mock('../i18n/AppLangContext', () => ({
  useAppT: () => traducir,
  useAppLang: () => ({ t: traducir, lang: 'es' }),
}))
vi.mock('../context/ToastContext', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }))
vi.mock('../context/AuthContext', () => ({ useAuth: () => ({ puede: () => true }) }))
vi.mock('../hooks/useOrgSettings', () => ({
  useOrgSettings: () => ({ currency: 'EUR', currencies: ['EUR', 'USD'], weekly_capacity_hours: 40, tax_rate: 21 }),
}))

import AltaDeProveedor, { cargaDeFreelance } from '../pages/proveedores/AltaDeProveedor'
import ConfigProveedores, { CLAVES_EN_CALIENTE } from '../pages/proveedores/ConfigProveedores'
import ExternalizarTarea from '../components/proveedores/ExternalizarTarea'
import { aQuienSeAsigna, asignacionExclusiva, pasosDePaquete, pestanasDeLaFicha } from '../pages/proveedores/logica'
import { tramosDeFormulario } from '../pages/proveedores/FormulariosDeContrato'
import { proveedoresApi } from '../services/api/proveedores'
import { formularioDeExternoInicial } from '../components/externos/FormularioDeExterno'
import { SECCIONES_DE_AJUSTES } from '../pages/settings/catalogoDeAjustes'
import { CLAVE_I18N_DE_CATALOGO } from '../hooks/useCatalogo'
import { CAPACIDADES } from '../permisos/capacidades'

function envolver(nodo: ReactNode) {
  return render(
    <MemoryRouter>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{nodo}</QueryClientProvider>
    </MemoryRouter>,
  )
}

/** Respuestas de GET por ruta (el interceptor real ya desenvuelve `{data, meta}`). */
function responder(rutas: Record<string, unknown>) {
  http.get.mockImplementation((url: string) => Promise.resolve({ data: rutas[url] ?? [] }))
}

beforeEach(() => {
  Object.values(http).forEach(f => f.mockReset().mockResolvedValue({ data: {} }))
  barril.usersApi.directory.mockReset().mockResolvedValue({ data: [{ id: 'u1', full_name: 'Ana Ruiz', role: 'pm' }] })
  barril.subcontractorsApi.create.mockReset()
  barril.vendorsApi.list.mockReset().mockResolvedValue({ data: [] })
})

describe('alta de proveedor con elección de tipo', () => {
  it('pide el tipo y, según la elección, pinta el formulario de persona o el de empresa con modos', async () => {
    responder({})
    envolver(<AltaDeProveedor onClose={() => {}} />)
    expect(screen.getByText('proveedores.alta_freelance')).toBeTruthy()
    expect(screen.getByText('proveedores.alta_empresa')).toBeTruthy()
    // Persona: los campos del externo (responsable interno obligatorio) y el botón de alta en un paso.
    fireEvent.click(screen.getByText('proveedores.alta_freelance'))
    expect(screen.getByText('externos.nombre')).toBeTruthy()
    expect(screen.getByText(/externos\.responsable_interno/)).toBeTruthy()
    expect(screen.getByText('proveedores.crear_freelance')).toBeTruthy()
    expect(screen.queryByText('managed_services')).toBeNull()
    // Empresa: modos de relación como casillas. (El traductor de prueba devuelve la clave, así que
    // `etiquetaDe` cae al valor de la enumeración, como en la app con una clave sin traducir.)
    fireEvent.click(screen.getByText('proveedores.cambiar_tipo'))
    fireEvent.click(screen.getByText('proveedores.alta_empresa'))
    for (const m of ['staff_augmentation', 'outsourcing', 'managed_services']) {
      expect(screen.getByText(m)).toBeTruthy()
      expect(screen.getByText(`proveedores.modo_${m}_d`)).toBeTruthy()
    }
  })

  it('la carga del freelance lleva responsable, formación y modos', () => {
    const form = { ...formularioDeExternoInicial(null, 'EUR'), name: ' Eva Gil ', internal_owner_id: 'u1', cost_rate: '50' }
    const carga = cargaDeFreelance(form, { vat_number: ' 12345678Z ', country: '', training_enabled: true, outsourcing: true })
    expect(carga).toMatchObject({
      name: 'Eva Gil', internal_owner_id: 'u1', cost_rate: 50, vat_number: '12345678Z', country: null,
      training_enabled: true, engagement_modes: ['staff_augmentation', 'outsourcing'], has_access: true,
    })
    expect(cargaDeFreelance(form, { vat_number: '', country: '', training_enabled: false, outsourcing: false }).engagement_modes).toEqual(['staff_augmentation'])
  })
})

describe('tarea: asignado y proveedor son excluyentes', () => {
  const vacio = { assignee_id: '', supplier_id: '', supplier_work_package_id: '' }
  it('elegir persona vacía proveedor y paquete; elegir proveedor vacía la persona', () => {
    const conProveedor = asignacionExclusiva({ ...vacio, assignee_id: 'u1' }, 'supplier_id', 's1')
    expect(conProveedor).toEqual({ assignee_id: '', supplier_id: 's1', supplier_work_package_id: '' })
    const conPaquete = asignacionExclusiva(conProveedor, 'supplier_work_package_id', 'w1')
    expect(conPaquete.supplier_work_package_id).toBe('w1')
    expect(asignacionExclusiva(conPaquete, 'assignee_id', 'u2')).toEqual({ assignee_id: 'u2', supplier_id: '', supplier_work_package_id: '' })
    // Cambiar de proveedor vacía el paquete (es de otro proveedor); repetir el mismo lo conserva.
    expect(asignacionExclusiva(conPaquete, 'supplier_id', 's2').supplier_work_package_id).toBe('')
    expect(asignacionExclusiva(conPaquete, 'supplier_id', 's1').supplier_work_package_id).toBe('w1')
    // Vaciar la persona no toca nada más.
    expect(asignacionExclusiva(conPaquete, 'assignee_id', '')).toEqual({ ...conPaquete, assignee_id: '' })
  })

  it('«Externalizar a» lista los proveedores de outsourcing del proyecto y avisa del cambio', async () => {
    responder({ '/suppliers/assignable': [{ id: 's1', code: 'SUB-1', name: 'Acme Outsourcing', kind: 'company', work_packages: [{ id: 'w1', title: 'Migración', project_id: 'p1', status: 'planned' }] }] })
    const onChange = vi.fn()
    envolver(<ExternalizarTarea projectId="p1" supplierId="" paqueteId="" onChange={onChange} idBase="t" />)
    expect(await screen.findByText('SUB-1 — Acme Outsourcing')).toBeTruthy()
    expect(http.get).toHaveBeenCalledWith('/suppliers/assignable', { params: { project_id: 'p1' } })
    fireEvent.change(screen.getByLabelText('proveedores.externalizar_a'), { target: { value: 's1' } })
    expect(onChange).toHaveBeenCalledWith('supplier_id', 's1')
  })

  it('sin proveedores asignables no pinta nada', async () => {
    responder({ '/suppliers/assignable': [] })
    const { container } = envolver(<ExternalizarTarea projectId="p1" supplierId="" paqueteId="" onChange={vi.fn()} idBase="t" />)
    await waitFor(() => expect(http.get).toHaveBeenCalled())
    expect(container.textContent).toBe('')
  })
})

describe('ficha según el tipo', () => {
  it('pestañas: sin personas en outsourcing puro; servicios y paquetes según modos', () => {
    expect(pestanasDeLaFicha({ kind: 'company', engagement_modes: ['outsourcing'] })).not.toContain('workers')
    expect(pestanasDeLaFicha({ kind: 'company', engagement_modes: ['outsourcing'] })).toContain('packages')
    expect(pestanasDeLaFicha({ kind: 'company', engagement_modes: ['managed_services'] })).toEqual(
      ['summary', 'contracts', 'services', 'billing', 'performance', 'compliance'])
    expect(pestanasDeLaFicha({ kind: 'freelance', engagement_modes: ['staff_augmentation'] })).toContain('workers')
    expect(pestanasDeLaFicha({ kind: 'freelance', engagement_modes: ['staff_augmentation'] })).not.toContain('packages')
  })

  it('a quién se asigna y ciclo del paquete', () => {
    expect(aQuienSeAsigna({ kind: 'freelance', engagement_modes: ['outsourcing'] })).toBe('person')
    expect(aQuienSeAsigna({ kind: 'company', engagement_modes: ['staff_augmentation', 'outsourcing'] })).toBe('person_and_supplier')
    expect(aQuienSeAsigna({ kind: 'company', engagement_modes: ['managed_services'] })).toBe('none')
    expect(aQuienSeAsigna({ kind: 'company', engagement_modes: ['outsourcing'], lifecycle_status: 'suspended' })).toBe('none')
    expect(pasosDePaquete('delivered')).toEqual(['accept', 'reject'])
    expect(pasosDePaquete('accepted')).toEqual([])
  })

  it('tramos de precio: sin filas vacías y «hasta» vacío sin límite', () => {
    expect(tramosDeFormulario([{ from: '0', to: '100', price: '10' }, { from: '100', to: '', price: '8' }, { from: '', to: '', price: '' }]))
      .toEqual([{ from: 0, to: 100, price: 10 }, { from: 100, to: null, price: 8 }])
  })
})

describe('cliente de /suppliers', () => {
  it('rutas de ciclo de vida, paquetes, previsión y GRC', async () => {
    await proveedoresApi.suspender('s1', 'Impago')
    await proveedoresApi.pasoDePaquete('w1', 'accept')
    await proveedoresApi.rechazarPaquete('w1', 'Faltan pruebas')
    await proveedoresApi.prevision('c1', { desde: '2026-11-01', hasta: '2026-11-30' })
    await proveedoresApi.cerrarPeriodo('c1', '2026-11-01', '2026-11-30')
    await proveedoresApi.revocarAcceso('g1', null)
    await proveedoresApi.contratoDesdePlantilla('s1', 't1')
    expect(http.post).toHaveBeenCalledWith('/suppliers/s1/suspend', { reason: 'Impago' })
    expect(http.post).toHaveBeenCalledWith('/suppliers/work-packages/w1/accept')
    expect(http.post).toHaveBeenCalledWith('/suppliers/work-packages/w1/reject', { reason: 'Faltan pruebas' })
    expect(http.get).toHaveBeenCalledWith('/suppliers/contracts/c1/forecast', { params: { desde: '2026-11-01', hasta: '2026-11-30' } })
    expect(http.post).toHaveBeenCalledWith('/suppliers/contracts/c1/statements', { period_start: '2026-11-01', period_end: '2026-11-30' })
    expect(http.post).toHaveBeenCalledWith('/suppliers/access-grants/g1/revoke', { reason: null })
    expect(http.post).toHaveBeenCalledWith('/suppliers/s1/contracts/from-template/t1')
  })
})

describe('Configuración → Proveedores', () => {
  it('sección en Finanzas con su capacidad; capacidades y catálogos nuevos registrados', () => {
    const s = SECCIONES_DE_AJUSTES.find(x => x.id === 'proveedores')
    expect(s).toMatchObject({ grupo: 'finanzas', capacidad: 'proveedores.config' })
    expect(CAPACIDADES).toEqual(expect.arrayContaining(['proveedores.ver', 'proveedores.gestionar', 'proveedores.config']))
    expect(CLAVE_I18N_DE_CATALOGO['supplier-service-types']).toBe('proveedores.tipo_servicio_')
    expect(CLAVE_I18N_DE_CATALOGO['supplier-billing-units']).toBe('proveedores.unidad_')
  })

  it('pinta plantillas con sus líneas, los dos catálogos y los umbrales en caliente', async () => {
    responder({
      '/suppliers/contract-templates': [{
        id: 't1', subcontractor_id: null, is_template: true, code: null, title: 'SOC mensual', contract_type: 'service', modes: ['managed_services'],
        status: 'draft', currency: 'EUR', lines: [{ id: 'l1', contract_id: 't1', model: 'subscription', unit: 'device_month', description: null, rate_id: null,
          rate_description: null, service_id: null, work_package_id: null, unit_price: 900, period: 'monthly', included_units: 50, overage_price: 12,
          tiers: [], min_amount: null, max_amount: null, valid_from: null, valid_until: null, is_active: true }],
      }],
      '/settings/supplier-service-types': [],
      '/settings/supplier-billing-units': [],
      '/settings/runtime/proyectos': { group: 'proyectos', items: CLAVES_EN_CALIENTE.map(k => ({ key: k, type: 'int', label: k, value: 1, plataforma: false })) },
    })
    envolver(<ConfigProveedores />)
    expect(await screen.findByText('SOC mensual')).toBeTruthy()
    expect(screen.getByText('subscription')).toBeTruthy()
    expect(screen.getByText('catalogos_ajustes.supplier_service_types')).toBeTruthy()
    expect(screen.getByText('catalogos_ajustes.supplier_billing_units')).toBeTruthy()
    // Etiqueta: `ajuste_clave.<CLAVE>` si está traducida; si no, la del backend (aquí, la clave).
    expect(await screen.findByLabelText('PROVEEDORES_TOLERANCIA_CONCILIACION_PCT')).toBeTruthy()
    expect(http.get).toHaveBeenCalledWith('/settings/runtime/proyectos')
  })
})

// Proveedores, migración 191: rutas y capacidades (la ficha con `proveedores.ver`,
// el portal con `proveedores.portal`), acciones de un estado de cuenta con la
// bandeja de aprobaciones, fuente de medición y recuentos pegados, destinos de
// un informe del portal y quién puede ser contacto del portal.
// Ver docs/PROVEEDORES_Y_EXTERNALIZACION.md §13-§16.
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { rutaDeclarada, puedeAbrir } from '../permisos/navegacion'
import { CAPACIDADES } from '../permisos/capacidades'
import type { Capacidad } from '../permisos/capacidades'
import {
  TONO_CUENTA, accionesDeEstado, admiteMedicion, enBandeja, filasDeRecuento, TIPOS_DE_INFORME, FUENTES_DE_MEDICION,
} from '../pages/proveedores/logica'

const src = (ruta: string) => readFileSync(resolve(__dirname, '..', ruta), 'utf8')

describe('rutas y menú de proveedores', () => {
  it('/subcontractors se abre con proveedores.ver (no con finanzas.ver)', () => {
    expect(rutaDeclarada('/subcontractors')?.capacidad).toBe('proveedores.ver')
    const soloVer = (c: Capacidad) => c === 'proveedores.ver'
    expect(puedeAbrir('/subcontractors', soloVer)).toBe(true)
    expect(puedeAbrir('/subcontractors', c => c === 'finanzas.ver')).toBe(false)
  })

  it('/supplier-portal se abre solo con proveedores.portal y está en el menú y en App', () => {
    expect(rutaDeclarada('/supplier-portal')?.capacidad).toBe('proveedores.portal')
    expect(puedeAbrir('/supplier-portal', c => c === 'proveedores.ver')).toBe(false)
    expect(CAPACIDADES).toContain('proveedores.portal')
    expect(src('components/layout/Layout.tsx')).toMatch(/to: '\/supplier-portal'/)
    expect(src('App.tsx')).toMatch(/path="\/supplier-portal"/)
  })

  it('la pantalla de proveedores no lleva botón «Configurar»', () => {
    expect(src('pages/SubcontractorsPage.tsx')).not.toMatch(/ajustes\.configurar/)
  })

  it('la bandeja de aprobaciones conoce el tipo supplier_statement', () => {
    expect(src('pages/ApprovalsPage.tsx')).toMatch(/supplier_statement:/)
  })
})

describe('estado de cuenta y bandeja de aprobaciones', () => {
  it('pending_approval tiene tono y solo admite disputar', () => {
    expect(TONO_CUENTA.pending_approval).toBe('warning')
    expect(enBandeja('pending_approval')).toBe(true)
    expect(accionesDeEstado('pending_approval', true)).toEqual(['dispute'])
  })

  it('aprobar solo conciliado y con factura; aprobado sin acciones', () => {
    expect(accionesDeEstado('reconciled', true)).toEqual(['reconcile', 'approve', 'dispute'])
    expect(accionesDeEstado('reconciled', false)).toEqual(['reconcile', 'dispute'])
    expect(accionesDeEstado('closed', false)).toEqual(['reconcile', 'dispute'])
    expect(accionesDeEstado('disputed', true)).toEqual(['reconcile'])
    expect(accionesDeEstado('approved', true)).toEqual([])
  })
})

describe('fuentes de medición', () => {
  it('solo por dispositivo o usuario al mes', () => {
    expect(FUENTES_DE_MEDICION).toEqual(['manual', 'cmdb', 'external'])
    expect(admiteMedicion('device_month')).toBe(true)
    expect(admiteMedicion('user_month')).toBe(true)
    expect(admiteMedicion('ticket')).toBe(false)
    expect(admiteMedicion(null)).toBe(false)
  })

  it('recuentos pegados: id o nombre, separadores, cabecera y líneas malas', () => {
    const servicios = [{ id: 's-1', name: 'EDR gestionado' }, { id: 's-2', name: 'MDM' }]
    const texto = 'servicio;fecha;cantidad;sistema\nEDR gestionado;2026-11-30;250;SIEM\ns-2\t2026-11-30\t12,5\nnadie;2026-11-30;3\nMDM;30/11/2026;3\nMDM;;-1'
    const { filas, malas } = filasDeRecuento(texto, servicios)
    expect(filas).toEqual([
      { service_id: 's-1', as_of: '2026-11-30', quantity: 250, system: 'SIEM' },
      { service_id: 's-2', as_of: '2026-11-30', quantity: 12.5, system: null },
    ])
    expect(malas).toEqual([4, 5, 6])
  })
})

describe('portal del proveedor', () => {
  it('tipos de informe del portal', () => {
    expect(TIPOS_DE_INFORME).toEqual(['progress', 'periodic', 'service_log', 'sla_evidence'])
  })

  it('las llamadas del portal nunca llevan el id del proveedor', () => {
    const api = src('services/api/proveedores.ts')
    const bloque = api.slice(api.indexOf('export const portalProveedorApi'))
    expect(bloque).not.toMatch(/sub_?[iI]d|subcontractor/)
  })
})

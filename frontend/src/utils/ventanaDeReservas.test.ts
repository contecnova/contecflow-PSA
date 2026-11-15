import { describe, expect, it } from 'vitest'
import { ventanaVisible } from './ventanaDeReservas'

describe('ventanaVisible', () => {
  it('va del lunes inicial al domingo de la última semana', () => {
    const v = ventanaVisible(new Date(2031, 2, 3), 12)  // lunes 3 mar 2031
    expect(v).toEqual({ date_from: '2031-03-03', date_to: '2031-05-25' })
  })
  it('una semana: lunes a domingo', () => {
    expect(ventanaVisible(new Date(2031, 2, 3), 1)).toEqual({ date_from: '2031-03-03', date_to: '2031-03-09' })
  })
  it('cambia al mover el número de semanas (la clave de la consulta cambia y se vuelve a pedir)', () => {
    const lunes = new Date(2031, 2, 3)
    expect(ventanaVisible(lunes, 8).date_to).not.toBe(ventanaVisible(lunes, 12).date_to)
  })
  it('no desplaza el día aunque cruce el cambio de hora', () => {
    expect(ventanaVisible(new Date(2031, 2, 24), 2).date_to).toBe('2031-04-06')
  })
  it('semanas inválidas se tratan como una', () => {
    expect(ventanaVisible(new Date(2031, 2, 3), 0).date_to).toBe('2031-03-09')
  })
  it('no modifica la fecha recibida', () => {
    const lunes = new Date(2031, 2, 3)
    ventanaVisible(lunes, 4)
    expect(lunes.getDate()).toBe(3)
  })
})

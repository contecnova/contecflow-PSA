import { describe, it, expect } from 'vitest'
import { extractErr, loadColor, statusColor } from './helpers'

describe('helpers', () => {
  it('extractErr normalizes pydantic array errors', () => {
    const err = {
      response: {
        data: {
          detail: [
            { loc: ['body', 'email'], msg: 'field required' },
            { loc: ['body', 'password'], msg: 'too short' },
          ],
        },
      },
    }
    expect(extractErr(err)).toContain('email: field required')
    expect(extractErr(err)).toContain('password: too short')
  })

  it('loadColor marks overload above 100%', () => {
    expect(loadColor(110)).toBe('#ff4757')
    expect(loadColor(90)).toBe('#ffb800')
    expect(loadColor(70)).toBe('#00e5a0')
  })

  it('statusColor falls back safely for unknown status', () => {
    expect(statusColor('in_progress')).toBe('#4f8ef7')
    expect(statusColor('unknown_status')).toBe('#7a8aaa')
  })
})

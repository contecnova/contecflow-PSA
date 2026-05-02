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
    expect(loadColor(110)).toBe('var(--danger)')
    expect(loadColor(90)).toBe('var(--warning)')
    expect(loadColor(70)).toBe('var(--success)')
  })

  it('statusColor falls back safely for unknown status', () => {
    expect(statusColor('in_progress')).toBe('var(--accent)')
    expect(statusColor('unknown_status')).toBe('var(--text-3)')
  })
})

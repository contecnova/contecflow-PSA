import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import MarkdownText from '../components/ui/MarkdownText'

describe('MarkdownText', () => {
  it('pinta negrita y viñetas sin dejar asteriscos', () => {
    const { container } = render(<MarkdownText text={'**Riesgos:**\n*   **ERP Acme**: alto\n- otro'} />)
    expect(container.querySelectorAll('strong')).toHaveLength(2)
    expect(container.textContent).not.toContain('*')
    expect(container.textContent).toContain('•  ERP Acme: alto')
    expect(container.textContent).toContain('•  otro')
  })
  it('un asterisco suelto no abre cursiva', () => {
    const { container } = render(<MarkdownText text={'2 * 3 = 6 y *esto* sí'} />)
    expect(container.querySelectorAll('em')).toHaveLength(1)
    expect(container.textContent).toContain('2 * 3 = 6')
  })
})

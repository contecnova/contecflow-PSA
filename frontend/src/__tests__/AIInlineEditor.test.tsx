import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import AIInlineEditor from '../components/AIInlineEditor';

// El editor lee `t` y `lang` con useAppLang (el useAppT retirado devolvía un
// respaldo sin proveedor; useAppLang exige AppLangProvider, como en la app).
// Aquí solo se prueba el campo: se simula el contexto de idioma.
vi.mock('../i18n/AppLangContext', () => ({
  useAppLang: () => ({ t: (k: string) => k, lang: 'es' }),
}));

describe('AIInlineEditor', () => {
  it('renderiza el textarea y placeholder', () => {
    render(<AIInlineEditor value="" onChange={() => {}} placeholder="Escribe aquí..." />);
    const textarea = screen.getByPlaceholderText('Escribe aquí...');
    expect(textarea).toBeInTheDocument();
  });

  it('llama a onChange al escribir', () => {
    const onChange = vi.fn();
    render(<AIInlineEditor value="" onChange={onChange} placeholder="Test" />);
    const textarea = screen.getByPlaceholderText('Test');
    fireEvent.change(textarea, { target: { value: 'nuevo texto' } });
    expect(onChange).toHaveBeenCalled();
  });
});

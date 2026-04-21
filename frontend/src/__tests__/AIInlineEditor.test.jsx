import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import AIInlineEditor from '../components/AIInlineEditor';

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

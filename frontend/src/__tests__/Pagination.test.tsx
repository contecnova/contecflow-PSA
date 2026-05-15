import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import Pagination from '../components/ui/Pagination';

describe('Pagination', () => {
  it('no muestra nada si solo hay una página', () => {
    const { container } = render(<Pagination page={1} totalPages={1} onChange={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('muestra los botones de navegación y llama a onChange', () => {
    const onChange = vi.fn();
    render(<Pagination page={2} totalPages={3} onChange={onChange} />);
    expect(screen.getByText('2')).toBeInTheDocument();
    fireEvent.click(screen.getByText('3'));
    expect(onChange).toHaveBeenCalledWith(3);
  });

  it('deshabilita el botón anterior en la primera página', () => {
    render(<Pagination page={1} totalPages={3} onChange={() => {}} />);
    // Pagination button uses title="Anterior" (not aria-label); query by title
    const prevBtn = screen.getByTitle('Anterior');
    expect(prevBtn).toBeDisabled();
  });
});

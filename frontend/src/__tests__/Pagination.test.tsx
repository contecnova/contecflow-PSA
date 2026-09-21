import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import Pagination from '../components/ui/Pagination';
import { AppLangProvider } from '../i18n/AppLangContext';
// `Pagination` y `TimerWidget` pasan ahora sus textos por `t()`, y `useAppLang`
// lanza a proposito si no encuentra el proveedor: es la guarda que impide que
// alguien use la traduccion fuera del arbol donde existe. Lo correcto es que el
// test monte el contexto, no debilitar la guarda para que el test pase.
//
// El proveedor ya contempla el entorno de pruebas —`loading` arranca en `false`
// cuando detecta Vitest—, asi que pinta a los hijos de inmediato.

describe('Pagination', () => {
  it('no muestra nada si solo hay una página', () => {
    const { container } = render(<AppLangProvider><Pagination page={1} totalPages={1} onChange={() => {}} /></AppLangProvider>);
    expect(container).toBeEmptyDOMElement();
  });

  it('muestra los botones de navegación y llama a onChange', () => {
    const onChange = vi.fn();
    render(<AppLangProvider><Pagination page={2} totalPages={3} onChange={onChange} /></AppLangProvider>);
    expect(screen.getByText('2')).toBeInTheDocument();
    fireEvent.click(screen.getByText('3'));
    expect(onChange).toHaveBeenCalledWith(3);
  });

  it('deshabilita el botón anterior en la primera página', () => {
    render(<AppLangProvider><Pagination page={1} totalPages={3} onChange={() => {}} /></AppLangProvider>);
    // Pagination button uses title="Anterior" (not aria-label); query by title
    const prevBtn = screen.getByTitle('Anterior');
    expect(prevBtn).toBeDisabled();
  });
});

import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { toHaveStyle } from '@testing-library/jest-dom/matchers';
import Confirm from '../components/ui/Confirm';

expect.extend({ toHaveStyle });

describe('Confirm', () => {
  it('muestra el título y la descripción', () => {
    render(
      <Confirm open={true} title="¿Estás seguro?" description="Esta acción es irreversible." onCancel={() => {}} onConfirm={() => {}} loading={false} />
    );
    expect(screen.getByText('¿Estás seguro?')).toBeInTheDocument();
    expect(screen.getByText('Esta acción es irreversible.')).toBeInTheDocument();
  });

  it('llama a onCancel y onConfirm', () => {
    const onCancel = vi.fn();
    const onConfirm = vi.fn();
    render(
      <Confirm open={true} title="Confirmar" description="¿Seguro?" onCancel={onCancel} onConfirm={onConfirm} loading={false} />
    );
    fireEvent.click(screen.getByText('Cancelar'));
    expect(onCancel).toHaveBeenCalled();
    fireEvent.click(screen.getByText('Confirmar'));
    expect(onConfirm).toHaveBeenCalled();
  });
});

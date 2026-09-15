import { vi, describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import Confirm from '../components/ui/Confirm';

// Confirm uses useAppT() for button labels
vi.mock('../i18n/AppLangContext', () => ({
  useAppT: () => (key: string) => {
    const map = { 'common.cancel': 'Cancelar', 'common.confirm': 'Confirmar' };
    return (map as Record<string, string>)[key] ?? key;
  },
  useAppLang: () => ({ t: (key: string) => key, lang: 'es' }),
}));

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
      <Confirm open={true} title="¿Seguro?" description="Esta acción no se puede deshacer." onCancel={onCancel} onConfirm={onConfirm} loading={false} />
    );
    // Use getByRole to target buttons specifically, not the title text
    fireEvent.click(screen.getByRole('button', { name: /cancelar/i }));
    expect(onCancel).toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: /confirmar/i }));
    expect(onConfirm).toHaveBeenCalled();
  });
});

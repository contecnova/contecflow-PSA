import { vi, describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import Confirm from '../components/ui/Confirm';

// Confirm usa el traductor del kit (`useTextoUi`), que fuera del portal es el
// de operador (`useAppLang`).
vi.mock('../i18n/AppLangContext', () => {
  const map: Record<string, string> = { 'common.cancel': 'Cancelar', 'common.confirm': 'Confirmar' };
  const t = (key: string) => map[key] ?? key;
  return { useAppT: () => t, useAppLang: () => ({ t, lang: 'es' }) };
});

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

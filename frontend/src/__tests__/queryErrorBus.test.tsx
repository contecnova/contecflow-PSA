// Segunda auditoría 2026-11: una query fallida tiene que avisar (antes se veía
// como una lista vacía), salvo que la página ya pinte su error o sea 401/429.
import { describe, it, expect } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import { ToastProvider } from '../context/ToastContext';
import { reportQueryError, shouldToastQueryError } from '../lib/queryErrorBus';

const http = (status: number, detail?: string) => ({ response: { status, data: detail ? { detail } : {} } });

describe('queryErrorBus', () => {
  it('filtra meta.errorToast=false, 401, 429 y cancelaciones', () => {
    expect(shouldToastQueryError(http(500))).toBe(true);
    expect(shouldToastQueryError(new Error('Network Error'))).toBe(true);
    expect(shouldToastQueryError(http(500), { errorToast: false })).toBe(false);
    expect(shouldToastQueryError(http(401))).toBe(false);
    expect(shouldToastQueryError(http(429))).toBe(false);
    expect(shouldToastQueryError({ name: 'CanceledError', code: 'ERR_CANCELED' })).toBe(false);
  });

  it('ToastProvider muestra el error una sola vez aunque fallen varias queries', () => {
    render(<ToastProvider><div /></ToastProvider>);
    act(() => {
      reportQueryError(http(500, 'Fallo del backend'));
      reportQueryError(http(500, 'Fallo del backend'));
      reportQueryError(http(500, 'Silenciado'), { errorToast: false });
    });
    expect(screen.getAllByRole('alert')).toHaveLength(1);
    expect(screen.getByRole('alert')).toHaveTextContent('Fallo del backend');
  });
});

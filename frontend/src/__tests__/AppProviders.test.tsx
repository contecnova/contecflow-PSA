// Pilot test for AppProviders — audit #47 (frontend coverage extension).
// Verifies that the global provider composition mounts children, exposes
// QueryClient context and Auth context without crashing.
import { describe, it, expect } from 'vitest';
import type { ReactElement } from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, useQueryClient } from '@tanstack/react-query';
import AppProviders from '../AppProviders';
import { useAuth } from '../context/AuthContext';

// AppProviders mounts ChatRealtimeProvider which uses useLocation() from
// react-router; we wrap in MemoryRouter to satisfy that dependency.
function renderWithProviders(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <MemoryRouter>
      <AppProviders queryClient={queryClient}>{ui}</AppProviders>
    </MemoryRouter>
  );
}

describe('AppProviders', () => {
  it('renders children', () => {
    renderWithProviders(<div data-testid="child">Hello</div>);
    expect(screen.getByTestId('child')).toHaveTextContent('Hello');
  });

  // Auditoría 2026-08 (P1-6): estos dos tests capturaban el valor del contexto
  // reasignando una variable declarada fuera del componente, desde el cuerpo del
  // render. `react-hooks/globals` lo marca con razón: rompe la pureza que asume
  // el compilador de React. En lugar de silenciar la regla, el probe publica lo
  // que observa EN EL DOM y la aserción se hace sobre el DOM. Comprueba
  // exactamente lo mismo y no necesita variable externa.
  it('provides QueryClient context (children can use useQueryClient)', () => {
    function Probe() {
      // useQueryClient lanza si falta el provider, así que llegar a renderizar
      // ya prueba el cableado; se publica además una propiedad observable.
      const qc = useQueryClient();
      return (
        <div data-testid="qc-probe" data-has-cache={String(typeof qc?.getQueryCache === 'function')}>
          ok
        </div>
      );
    }
    renderWithProviders(<Probe />);
    const probe = screen.getByTestId('qc-probe');
    expect(probe).toBeInTheDocument();
    expect(probe).toHaveAttribute('data-has-cache', 'true');
  });

  it('provides Auth context (children can useAuth)', () => {
    function Probe() {
      // useAuth() lanza "useAuth must be used inside AuthProvider" si no hay
      // provider, así que renderizar ya prueba el cableado.
      const auth = useAuth();
      return (
        <div
          data-testid="auth-probe"
          data-has-user-field={String(auth != null && 'user' in auth)}
        >
          ok
        </div>
      );
    }
    renderWithProviders(<Probe />);
    const probe = screen.getByTestId('auth-probe');
    expect(probe).toBeInTheDocument();
    // El AuthContext expone al menos el campo user (null si no hay sesión).
    expect(probe).toHaveAttribute('data-has-user-field', 'true');
  });
});

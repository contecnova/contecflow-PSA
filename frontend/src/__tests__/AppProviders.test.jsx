// Pilot test for AppProviders — audit #47 (frontend coverage extension).
// Verifies that the global provider composition mounts children, exposes
// QueryClient context and Auth context without crashing.
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, useQueryClient } from '@tanstack/react-query';
import AppProviders from '../AppProviders';
import { useAuth } from '../context/AuthContext';

// AppProviders mounts ChatRealtimeProvider which uses useLocation() from
// react-router; we wrap in MemoryRouter to satisfy that dependency.
function renderWithProviders(ui) {
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

  it('provides QueryClient context (children can use useQueryClient)', () => {
    let received = null;
    function Probe() {
      received = useQueryClient();
      return <div data-testid="qc-probe">ok</div>;
    }
    renderWithProviders(<Probe />);
    expect(screen.getByTestId('qc-probe')).toBeInTheDocument();
    // useQueryClient throws if the provider is missing, so reaching this
    // assertion already proves the context is wired. Belt-and-braces:
    expect(received).toBeTruthy();
    expect(typeof received.getQueryCache).toBe('function');
  });

  it('provides Auth context (children can useAuth)', () => {
    let received = null;
    function Probe() {
      received = useAuth();
      return <div data-testid="auth-probe">ok</div>;
    }
    renderWithProviders(<Probe />);
    expect(screen.getByTestId('auth-probe')).toBeInTheDocument();
    // useAuth() throws "useAuth must be used inside AuthProvider" if no
    // provider exists, so a non-null result proves wiring.
    expect(received).not.toBeNull();
    // The AuthContext exposes at minimum a user field (null when logged out).
    expect(received).toHaveProperty('user');
  });
});

import { vi, describe, it, expect, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import api from '../services/api';
import ResourceHeatmap from '../components/ResourceHeatmap';

// ResourceHeatmap uses useAppT() — mock the i18n hook
vi.mock('../i18n/AppLangContext', () => ({
  useAppLang: () => ({ t: (k: string) => k, lang: 'es' }),
  useAppT: () => (key: string) => key,
}));

// Periodo libre (16-11-2026): el horizonte es el selector de periodo común.
vi.mock('../services/api/periodo', () => ({
  periodoApi: { limites: () => Promise.resolve({ max_dias: 1830, max_puntos: { hour: 744, day: 1100, week: 530, month: 240 }, auto_max_puntos: 120, granularidades: [] }) },
}));

// Mock the api service (useQuery internally calls api.get)
// El componente pide el mapa y las reservas con `reservasApi` (pantallasSueltas.ts),
// que en la app llama a `api.get`; el mock hace lo mismo para que `paramsDelMapa`
// lea los parámetros que salen (`{ ...periodo.params }`).
vi.mock('../services/api', () => {
  const get = vi.fn().mockResolvedValue({ data: [] });
  return {
    default: {
      get,
      post: vi.fn().mockResolvedValue({ data: {} }),
      patch: vi.fn().mockResolvedValue({ data: {} }),
      delete: vi.fn().mockResolvedValue({ data: {} }),
    },
    reservasApi: {
      mapaDeCalor: (params?: Record<string, unknown>) => get('/bookings/heatmap', { params }),
      listar: (params?: Record<string, unknown>) => get('/bookings', { params }),
      crear: vi.fn().mockResolvedValue({ data: {} }),
      borrar: vi.fn().mockResolvedValue({ data: {} }),
    },
    projectsApi: { get: vi.fn().mockResolvedValue({ data: [] }) },
    usersApi: { get: vi.fn().mockResolvedValue({ data: [] }) },
  };
});

vi.mock('../context/ConfirmContext', () => ({
  openConfirmGlobal: vi.fn().mockResolvedValue(true),
}));

vi.mock('../hooks/useFormValidation', () => ({
  useFormValidation: () => ({
    values: {},
    errors: {},
    handleChange: vi.fn(),
    validate: vi.fn().mockReturnValue(true),
    reset: vi.fn(),
    setValues: vi.fn(),
  }),
}));

function montar(ruta = '/resources') {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={[ruta]}>
      <QueryClientProvider client={qc}>
        <ResourceHeatmap />
      </QueryClientProvider>
    </MemoryRouter>
  );
}

function paramsDelMapa(): Record<string, unknown> | undefined {
  const llamada = vi.mocked(api.get).mock.calls.find(c => c[0] === '/bookings/heatmap');
  return (llamada?.[1] as { params?: Record<string, unknown> } | undefined)?.params;
}

describe('ResourceHeatmap', () => {
  beforeEach(() => { vi.mocked(api.get).mockClear(); });

  it('monta el componente sin errores', () => {
    const { container } = montar();
    expect(container.firstChild).not.toBeNull();
  });

  it('pide el horizonte por defecto como los próximos 30 días (sin weeks)', async () => {
    montar();
    await waitFor(() => expect(paramsDelMapa()).toBeDefined());
    expect(paramsDelMapa()).toMatchObject({ days: 30 });
    expect(paramsDelMapa()).not.toHaveProperty('weeks');
  });

  it('un rango personalizado de la URL (prefijo mapa_) llega como desde/hasta', async () => {
    montar('/resources?mapa_periodo=custom&mapa_desde=2026-12-01T00:00:00%2B01:00&mapa_hasta=2027-02-01T00:00:00%2B01:00');
    await waitFor(() => expect(paramsDelMapa()).toBeDefined());
    expect(paramsDelMapa()).toMatchObject({ desde: '2026-12-01T00:00:00+01:00', hasta: '2027-02-01T00:00:00+01:00' });
  });

  it('no ofrece «próximos 365 días» (la API corta en 52 semanas)', () => {
    const { queryByText } = montar();
    expect(queryByText('periodo.prox365d')).toBeNull();
  });
});

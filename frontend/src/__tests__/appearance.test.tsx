import { describe, it, expect, afterEach } from 'vitest';
import { useState } from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { alpha } from '../constants/theme';
import { applyAccent, applyDensity, onAccentFor } from '../utils/appearance';
import { fmtCurrency, fmtDate, fmtDateTime, fmtMonth, fmtNumber, localeActivo } from '../utils/helpers';
import Tabs from '../components/ui/Tabs';
import { ToastProvider, useToast } from '../context/ToastContext';

describe('alpha', () => {
  it('con un hex de 6 cifras da lo de siempre', () => {
    expect(alpha('#34d399', '20')).toBe('#34d39920');
  });
  it('con var() da color-mix, no CSS inválido', () => {
    expect(alpha('var(--success)', '20')).toBe('color-mix(in srgb, var(--success) 13%, transparent)');
  });
  it('sin color no inventa uno', () => {
    expect(alpha(undefined, '20')).toBe('');
  });
});

describe('acento y densidad del perfil', () => {
  afterEach(() => { applyAccent(null); applyDensity('normal'); });

  it('elige el extremo que más contrasta con el acento', () => {
    expect(onAccentFor('#4f8ef7')).toBe('var(--on-accent-dark)');   // blanco 3,21 · negro 6,54
    expect(onAccentFor('#2563eb')).toBe('var(--on-accent-light)');  // blanco 5,17 · negro 4,06
  });

  it('applyAccent escribe también --on-accent, y lo quita sin acento propio', () => {
    applyAccent('#caa34c');
    const st = document.documentElement.style;
    expect(st.getPropertyValue('--accent')).toBe('#caa34c');
    expect(st.getPropertyValue('--on-accent')).toBe('var(--on-accent-dark)');
    applyAccent(null);
    expect(st.getPropertyValue('--on-accent')).toBe('');
  });

  it('la densidad sólo escribe el atributo que leen los tokens', () => {
    applyDensity('compact');
    expect(document.documentElement.getAttribute('data-density')).toBe('compact');
  });
});

describe('fechas en el idioma activo', () => {
  afterEach(() => localStorage.removeItem('contecflow_operator_lang'));
  const d = new Date(2026, 10, 2, 14, 5);

  it('castellano: día, mes y año', () => {
    localStorage.setItem('contecflow_operator_lang', 'es');
    expect(fmtDate(d)).toBe('02/11/2026');
    expect(fmtDateTime(d)).toContain('14:05');
    expect(fmtMonth(d)).toContain('noviembre');
  });

  it('inglés y chino no salen en formato español', () => {
    localStorage.setItem('contecflow_operator_lang', 'en');
    expect(fmtDate(d)).toBe('11/02/2026');
    expect(fmtMonth(d)).toContain('November');
    localStorage.setItem('contecflow_operator_lang', 'zh');
    expect(fmtDate(d)).toBe('2026/11/02');
  });

  it('sin fecha, guion', () => {
    expect(fmtDate(null)).toBe('—');
  });
});

describe('números y monedas en el idioma activo', () => {
  afterEach(() => localStorage.removeItem('contecflow_operator_lang'));
  // Intl separa con espacio duro (U+00A0 / U+202F): se normaliza para comparar.
  const plano = (s: string) => s.replace(/[\u00a0\u202f]/g, ' ');

  it('castellano: punto de miles y coma decimal', () => {
    localStorage.setItem('contecflow_operator_lang', 'es');
    expect(fmtNumber(1234567.5)).toBe('1.234.567,5');
    expect(plano(fmtCurrency(1234567, 'EUR'))).toBe('1.234.567 €');
  });

  it('inglés: coma de miles y punto decimal; la moneda sigue siendo la que se pasa', () => {
    localStorage.setItem('contecflow_operator_lang', 'en');
    expect(fmtNumber(1234567.5)).toBe('1,234,567.5');
    expect(fmtCurrency(1234567, 'EUR')).toBe('€1,234,567');
    expect(new Date(2026, 10, 2).toLocaleDateString(localeActivo(), { month: 'long' })).toBe('November');
  });

  it('un idioma guardado que Intl no reconoce cae a castellano sin lanzar', () => {
    expect(localeActivo('no_vale!')).toBe('es');
  });
});

describe('Tabs: patrón ARIA de pestañas', () => {
  function Demo() {
    const [tab, setTab] = useState('a');
    return <Tabs ariaLabel="Secciones" active={tab} onChange={setTab}
      items={[{ id: 'a', label: 'Uno' }, { id: 'b', label: 'Dos', disabled: true }, { id: 'c', label: 'Tres' }]} />;
  }

  it('tablist, tab y aria-selected; sólo la activa en el orden de Tab', () => {
    render(<Demo />);
    expect(screen.getByRole('tablist', { name: 'Secciones' })).toBeTruthy();
    const tabs = screen.getAllByRole('tab');
    expect(tabs).toHaveLength(3);
    expect(tabs[0].getAttribute('aria-selected')).toBe('true');
    expect(tabs.map(t => t.tabIndex)).toEqual([0, -1, -1]);
  });

  it('las flechas saltan la deshabilitada, seleccionan y mueven el foco', () => {
    render(<Demo />);
    const [uno, , tres] = screen.getAllByRole('tab');
    uno.focus();
    fireEvent.keyDown(uno, { key: 'ArrowRight' });
    expect(tres.getAttribute('aria-selected')).toBe('true');
    expect(document.activeElement).toBe(tres);
    fireEvent.keyDown(tres, { key: 'ArrowRight' });
    expect(uno.getAttribute('aria-selected')).toBe('true');
    fireEvent.keyDown(uno, { key: 'End' });
    expect(tres.getAttribute('aria-selected')).toBe('true');
  });
});

describe('avisos emergentes', () => {
  function Disparar() {
    const toast = useToast();
    return <>
      <button onClick={() => toast.success('Guardado')}>ok</button>
      <button onClick={() => toast.error('Ha fallado')}>ko</button>
    </>;
  }

  it('se anuncian: región viva, error como alerta y cerrar con nombre', () => {
    render(<ToastProvider><Disparar /></ToastProvider>);
    act(() => { fireEvent.click(screen.getByText('ok')); fireEvent.click(screen.getByText('ko')); });
    const region = screen.getByRole('status');
    expect(region.getAttribute('aria-live')).toBe('polite');
    expect(region.textContent).toContain('Guardado');
    expect(screen.getByRole('alert').textContent).toContain('Ha fallado');
    // El idioma de los tests resuelve la clave; lo que importa es que tenga nombre
    const cerrar = screen.getAllByRole('button').filter(b => b.closest('[role="status"]'));
    expect(cerrar).toHaveLength(2);
    cerrar.forEach(b => expect(b.getAttribute('aria-label')).toBeTruthy());
  });
});

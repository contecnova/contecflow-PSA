import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { toHaveStyle } from '@testing-library/jest-dom/matchers';
import { BadgeWithTooltip } from '../components/ui/BadgeWithTooltip';

expect.extend({ toHaveStyle });

describe('BadgeWithTooltip', () => {
  it('muestra el label y el tooltip correctamente', () => {
    render(
      <BadgeWithTooltip label="Activo" color="#00a86b" tooltip="Estado activo" icon="✔️" />
    );
    const badge = screen.getByText('Activo');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveAttribute('title', 'Estado activo');
    expect(badge).toHaveStyle({ color: '#00a86b' });
  });

  it('llama a onClick si se hace click', () => {
    const onClick = vi.fn();
    render(
      <BadgeWithTooltip label="Click" color="#007bff" tooltip="Haz click" onClick={onClick} />
    );
    const badge = screen.getByText('Click');
    fireEvent.click(badge);
    expect(onClick).toHaveBeenCalled();
  });
});

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import TimerWidget from '../components/TimerWidget';

describe('TimerWidget', () => {
  it('renderiza el componente TimerWidget', () => {
    render(<TimerWidget />);
    // Debe mostrar al menos el formato de tiempo 00:00:00
    expect(screen.getByText(/\d{2}:\d{2}:\d{2}/)).toBeInTheDocument();
  });
});

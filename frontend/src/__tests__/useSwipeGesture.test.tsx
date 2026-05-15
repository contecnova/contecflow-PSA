import { render, fireEvent } from '@testing-library/react'
import React from 'react'
import { describe, expect, it, vi } from 'vitest'

import { useSwipeGesture } from '../hooks/useSwipeGesture'

function Harness({ handlers }) {
  const gestureHandlers = useSwipeGesture(handlers)
  return <div data-testid="gesture-area" {...gestureHandlers}>gesture area</div>
}

describe('useSwipeGesture', () => {
  it('fires swipe callbacks on horizontal gestures', () => {
    const onSwipeRight = vi.fn()
    const onSwipeLeft = vi.fn()
    const { getByTestId } = render(<Harness handlers={{ onSwipeRight, onSwipeLeft, threshold: 30, velocityThreshold: 0 }} />)
    const area = getByTestId('gesture-area')

    fireEvent.touchStart(area, {
      touches: [{ clientX: 20, clientY: 20 }],
    })
    fireEvent.touchEnd(area, {
      changedTouches: [{ clientX: 90, clientY: 20 }],
    })

    fireEvent.touchStart(area, {
      touches: [{ clientX: 90, clientY: 20 }],
    })
    fireEvent.touchEnd(area, {
      changedTouches: [{ clientX: 20, clientY: 20 }],
    })

    expect(onSwipeRight).toHaveBeenCalledTimes(1)
    expect(onSwipeLeft).toHaveBeenCalledTimes(1)
  })

  it('fires pinch callbacks on two-finger zoom gestures', () => {
    const onPinchOut = vi.fn()
    const onPinchIn = vi.fn()
    const { getByTestId } = render(<Harness handlers={{ onPinchOut, onPinchIn, pinchThreshold: 10 }} />)
    const area = getByTestId('gesture-area')

    fireEvent.touchStart(area, {
      touches: [
        { clientX: 20, clientY: 20 },
        { clientX: 60, clientY: 20 },
      ],
    })
    fireEvent.touchMove(area, {
      touches: [
        { clientX: 10, clientY: 20 },
        { clientX: 80, clientY: 20 },
      ],
      preventDefault: vi.fn(),
    })
    fireEvent.touchMove(area, {
      touches: [
        { clientX: 25, clientY: 20 },
        { clientX: 50, clientY: 20 },
      ],
      preventDefault: vi.fn(),
    })

    expect(onPinchOut).toHaveBeenCalledTimes(1)
    expect(onPinchIn).toHaveBeenCalledTimes(1)
  })
})
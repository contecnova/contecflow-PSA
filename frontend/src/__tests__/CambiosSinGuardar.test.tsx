// Cambios sin guardar (kit, 23-11-2026). Incidencia de usuario: «al editar, si
// haces clic fuera del formulario, se cierra sin preguntar y se pierden los
// cambios». Modal, Drawer y PortalModal preguntan al cerrar con clic fuera,
// Escape o la X si hay cambios; sin cambios cierran; el cierre programático
// (tras guardar) no pregunta. También enlaces internos y beforeunload.
import { vi, describe, it, expect, afterEach } from 'vitest'
import { useState } from 'react'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import { ConfirmProvider } from '../context/ConfirmContext'
import { Modal, Drawer, Input, useDialogoEditable } from '../components/ui'
import { _reiniciarCambiosSinGuardar, hayCambiosSinGuardar } from '../components/ui/useCambiosSinGuardar'

const TEXTOS: Record<string, string> = {
  'sin_guardar.titulo': 'Cambios sin guardar',
  'sin_guardar.mensaje': 'Tienes cambios sin guardar. ¿Descartarlos?',
  'sin_guardar.descartar': 'Descartar',
  'sin_guardar.seguir': 'Seguir editando',
  'common.cancel': 'Cancelar',
  'common.close': 'Cerrar',
  'uikit.cerrar': 'Cerrar',
  'confirm_modal.default_title': 'Confirmar',
  'confirm_modal.danger_title': 'Atención',
}

vi.mock('../i18n/AppLangContext', () => ({
  useAppLang: () => ({ lang: 'es', t: (k: string) => TEXTOS[k] ?? k }),
}))
vi.mock('../pages/portal-client/portalClientContext', () => ({
  useLang: () => (k: string) => TEXTOS[k] ?? k,
}))

afterEach(() => {
  cleanup()
  _reiniciarCambiosSinGuardar()
})

function PantallaModal({ onClose, avisar = true }: { onClose: () => void; avisar?: boolean }) {
  const [abierto, setAbierto] = useState(true)
  const [nombre, setNombre] = useState('')
  const cerrar = () => { onClose(); setAbierto(false) }
  return (
    <Modal open={abierto} onClose={cerrar} title="Editar" avisarSinGuardar={avisar}>
      <Input label="Nombre" value={nombre} onChange={e => setNombre(e.target.value)} />
      <a href="/otra-pantalla">Ir a otra</a>
      {/* Guardar: la pantalla cierra por su cuenta (cierre programático). */}
      <button type="button" onClick={cerrar}>Guardar</button>
    </Modal>
  )
}

const montarModal = (avisar = true) => {
  const onClose = vi.fn()
  render(<ConfirmProvider><PantallaModal onClose={onClose} avisar={avisar} /></ConfirmProvider>)
  const dialogo = screen.getByRole('dialog', { name: 'Editar' })
  return { onClose, dialogo, fondo: dialogo.parentElement as HTMLElement }
}

const escribir = (texto = 'Acme') =>
  fireEvent.change(screen.getByLabelText('Nombre'), { target: { value: texto } })

describe('Modal: cambios sin guardar', () => {
  it('sin cambios, el clic fuera cierra sin preguntar', () => {
    const { onClose, fondo } = montarModal()
    fireEvent.mouseDown(fondo)
    expect(onClose).toHaveBeenCalledTimes(1)
    expect(screen.queryByText('Tienes cambios sin guardar. ¿Descartarlos?')).toBeNull()
  })

  it('con cambios, el clic fuera pregunta; «Seguir editando» no cierra y «Descartar» sí', async () => {
    const { onClose, fondo } = montarModal()
    escribir()
    fireEvent.mouseDown(fondo)
    expect(await screen.findByText('Tienes cambios sin guardar. ¿Descartarlos?')).toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'Seguir editando' }))
    await waitFor(() => expect(screen.queryByText('Tienes cambios sin guardar. ¿Descartarlos?')).toBeNull())
    expect(onClose).not.toHaveBeenCalled()
    expect(screen.getByLabelText('Nombre')).toHaveValue('Acme')

    fireEvent.mouseDown(fondo)
    fireEvent.click(await screen.findByRole('button', { name: 'Descartar' }))
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
  })

  it('con cambios, Escape pregunta', async () => {
    const { onClose } = montarModal()
    escribir()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(await screen.findByText('Tienes cambios sin guardar. ¿Descartarlos?')).toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()
  })

  it('con cambios, la X pregunta', async () => {
    const { onClose, dialogo } = montarModal()
    escribir()
    const equis = Array.from(dialogo.querySelectorAll('button')).find(b => b.getAttribute('aria-label') === 'Cerrar') as HTMLButtonElement
    fireEvent.click(equis)
    expect(await screen.findByText('Tienes cambios sin guardar. ¿Descartarlos?')).toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()
  })

  it('si el usuario deja el campo como estaba, no hay cambios', () => {
    const { onClose, fondo } = montarModal()
    const campo = screen.getByLabelText('Nombre')
    fireEvent.focusIn(campo)
    fireEvent.change(campo, { target: { value: 'Acme' } })
    fireEvent.change(campo, { target: { value: '' } })
    fireEvent.mouseDown(fondo)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('el cierre programático tras guardar no pregunta', () => {
    const { onClose } = montarModal()
    escribir()
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(onClose).toHaveBeenCalledTimes(1)
    expect(screen.queryByText('Tienes cambios sin guardar. ¿Descartarlos?')).toBeNull()
    expect(hayCambiosSinGuardar()).toBe(false)
  })

  it('avisarSinGuardar={false} cierra sin preguntar aunque haya cambios', () => {
    const { onClose, fondo } = montarModal(false)
    escribir()
    fireEvent.mouseDown(fondo)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('las búsquedas no cuentan como cambios', () => {
    const onClose = vi.fn()
    render(
      <ConfirmProvider>
        <Modal open onClose={onClose} title="Buscar">
          <input type="search" aria-label="Filtro" />
        </Modal>
      </ConfirmProvider>,
    )
    fireEvent.change(screen.getByLabelText('Filtro'), { target: { value: 'x' } })
    fireEvent.mouseDown(screen.getByRole('dialog', { name: 'Buscar' }).parentElement as HTMLElement)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('modales anidados: lo escrito en el de arriba no ensucia el de abajo', () => {
    const cerrarPadre = vi.fn()
    const cerrarHijo = vi.fn()
    function Anidados() {
      const [hijo, setHijo] = useState(false)
      return (
        <Modal open onClose={cerrarPadre} title="Padre">
          <button type="button" onClick={() => setHijo(true)}>Abrir hijo</button>
          <Modal open={hijo} onClose={cerrarHijo} title="Hijo" avisarSinGuardar={false}>
            <input aria-label="Campo del hijo" />
          </Modal>
        </Modal>
      )
    }
    render(<ConfirmProvider><Anidados /></ConfirmProvider>)
    fireEvent.click(screen.getByRole('button', { name: 'Abrir hijo' }))
    fireEvent.change(screen.getByLabelText('Campo del hijo'), { target: { value: 'x' } })
    expect(hayCambiosSinGuardar()).toBe(false)
    // Escape solo afecta al de arriba.
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(cerrarHijo).toHaveBeenCalledTimes(1)
    expect(cerrarPadre).not.toHaveBeenCalled()
  })

  it('cambiosSinGuardar controlado manda sobre la detección', async () => {
    const onClose = vi.fn()
    render(
      <ConfirmProvider>
        <Modal open onClose={onClose} title="Controlado" cambiosSinGuardar>
          <p>Sin campos</p>
        </Modal>
      </ConfirmProvider>,
    )
    await waitFor(() => expect(hayCambiosSinGuardar()).toBe(true))
    fireEvent.mouseDown(screen.getByRole('dialog', { name: 'Controlado' }).parentElement as HTMLElement)
    expect(await screen.findByText('Tienes cambios sin guardar. ¿Descartarlos?')).toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()
  })
})

describe('Navegar fuera con cambios sin guardar', () => {
  it('un enlace interno pregunta antes de salir', async () => {
    montarModal()
    escribir()
    const sigue = fireEvent.click(screen.getByText('Ir a otra'))
    expect(sigue).toBe(false) // se paró la navegación
    expect(await screen.findByText('Tienes cambios sin guardar. ¿Descartarlos?')).toBeInTheDocument()
  })

  it('sin cambios, el enlace no se toca', () => {
    montarModal()
    const enlace = screen.getByText('Ir a otra')
    // Evita que jsdom intente navegar.
    enlace.addEventListener('click', e => e.preventDefault())
    fireEvent.click(enlace)
    expect(screen.queryByText('Tienes cambios sin guardar. ¿Descartarlos?')).toBeNull()
  })

  it('cerrar o recargar la pestaña pide confirmación (beforeunload)', () => {
    montarModal()
    escribir()
    const ev = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(ev)
    expect(ev.defaultPrevented).toBe(true)
  })
})

describe('Drawer: cambios sin guardar', () => {
  function PantallaDrawer({ onClose }: { onClose: () => void }) {
    return (
      <Drawer onClose={onClose} ariaLabel="Ficha">
        <button type="button" data-cierra-dialogo="" aria-label="Cerrar ficha" onClick={onClose}>X</button>
        <input aria-label="Notas" />
      </Drawer>
    )
  }

  it('sin cambios, la X y el fondo cierran', () => {
    const onClose = vi.fn()
    render(<ConfirmProvider><PantallaDrawer onClose={onClose} /></ConfirmProvider>)
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar ficha' }))
    expect(onClose).toHaveBeenCalledTimes(1)
    fireEvent.mouseDown(document.querySelector('.drawer-e1') as HTMLElement)
    expect(onClose).toHaveBeenCalledTimes(2)
  })

  it('con cambios, la X (data-cierra-dialogo) y el fondo preguntan', async () => {
    const onClose = vi.fn()
    render(<ConfirmProvider><PantallaDrawer onClose={onClose} /></ConfirmProvider>)
    fireEvent.change(screen.getByLabelText('Notas'), { target: { value: 'algo' } })
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar ficha' }))
    expect(await screen.findByText('Tienes cambios sin guardar. ¿Descartarlos?')).toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Seguir editando' }))
    await waitFor(() => expect(screen.queryByText('Tienes cambios sin guardar. ¿Descartarlos?')).toBeNull())

    fireEvent.mouseDown(document.querySelector('.drawer-e1') as HTMLElement)
    fireEvent.click(await screen.findByRole('button', { name: 'Descartar' }))
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
  })
})

describe('Diálogo propio con useDialogoEditable', () => {
  function Propio({ onClose }: { onClose: () => void }) {
    const { ref, pedirCierre } = useDialogoEditable<HTMLDivElement>(true, onClose)
    return (
      <div role="presentation" data-testid="fondo" onMouseDown={pedirCierre}>
        <div ref={ref} role="dialog" aria-modal="true" aria-label="Propio" onMouseDown={e => e.stopPropagation()}>
          <textarea aria-label="Texto" />
        </div>
      </div>
    )
  }

  it('con cambios, el fondo pregunta; sin cambios, cierra', async () => {
    const onClose = vi.fn()
    render(<ConfirmProvider><Propio onClose={onClose} /></ConfirmProvider>)
    fireEvent.mouseDown(screen.getByTestId('fondo'))
    expect(onClose).toHaveBeenCalledTimes(1)

    fireEvent.change(screen.getByLabelText('Texto'), { target: { value: 'hola' } })
    fireEvent.mouseDown(screen.getByTestId('fondo'))
    expect(await screen.findByText('Tienes cambios sin guardar. ¿Descartarlos?')).toBeInTheDocument()
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})

describe('PortalModal: cambios sin guardar', () => {
  it('con cambios, el clic fuera pregunta; sin cambios, cierra', async () => {
    const { PortalModal } = await import('../pages/portal-client/PortalUI')
    const onClose = vi.fn()
    render(
      <ConfirmProvider>
        <PortalModal open onClose={onClose} title="Nueva solicitud">
          <input aria-label="Asunto" />
        </PortalModal>
      </ConfirmProvider>,
    )
    const fondo = screen.getByRole('dialog', { name: 'Nueva solicitud' }).parentElement as HTMLElement
    fireEvent.mouseDown(fondo)
    expect(onClose).toHaveBeenCalledTimes(1)

    fireEvent.change(screen.getByLabelText('Asunto'), { target: { value: 'Ayuda' } })
    fireEvent.mouseDown(fondo)
    expect(await screen.findByText('Tienes cambios sin guardar. ¿Descartarlos?')).toBeInTheDocument()
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})

// ==========================================
// Toast.jsx — notifiche non bloccanti al posto di alert().
//
// Perché non un alert(): alert() ferma l'esecuzione di TUTTO il resto
// della pagina finché l'utente non clicca "OK" — nessun'altra interazione
// possibile nel frattempo, nemmeno leggere i risultati sotto. Un toast si
// mostra da solo per qualche secondo e sparisce, senza bloccare nulla.
//
// showToast() puo' essere chiamato da qualsiasi componente (anche non
// direttamente annidato sotto <ToastContainer />) senza dover passare
// callback/prop tra i vari livelli — stesso spirito "esporta funzioni di
// modulo" già usato in Favorites.jsx/History.jsx (loadFavorites,
// persistFavorites, ecc.), qui applicato a un piccolo elenco di listener
// invece che a localStorage. <ToastContainer /> va montato UNA sola volta
// (in App.jsx) — è lui che disegna davvero i messaggi.
// ==========================================
import { useEffect, useState } from 'react'
import './Toast.css'

let listeners = []
let nextId = 1

export function showToast(message, type = 'info', duration = 3500) {
  const id = nextId++
  const toast = { id, message, type }
  listeners.forEach((update) => update((prev) => [...prev, toast]))

  setTimeout(() => {
    listeners.forEach((update) => update((prev) => prev.filter((t) => t.id !== id)))
  }, duration)
}

const ICONS = {
  success: '✅',
  error: '❌',
  info: 'ℹ️',
}

export default function ToastContainer() {
  const [toasts, setToasts] = useState([])

  useEffect(() => {
    listeners.push(setToasts)
    return () => {
      listeners = listeners.filter((fn) => fn !== setToasts)
    }
  }, [])

  const dismiss = (id) => setToasts((prev) => prev.filter((t) => t.id !== id))

  if (toasts.length === 0) return null

  return (
    <div className="toast-container">
      {toasts.map((t) => (
        <div key={t.id} className={`toast toast-${t.type}`} onClick={() => dismiss(t.id)}>
          <span className="toast-icon">{ICONS[t.type] || ICONS.info}</span>
          <span className="toast-message">{t.message}</span>
        </div>
      ))}
    </div>
  )
}

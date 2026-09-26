// ==========================================
// 1. IMPORTAZIONI DEI MODULI E DEI COMPONENTI
// ==========================================
import React, { useState, useEffect } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom'
import axios from 'axios'

// Import dei componenti
import DatabaseSelector from './DatabaseSelector'
import QueryExecutor from './QueryExecutor'
import Dashboard from './Dashboard'
import Favorites, { loadFavorites, persistFavorites } from './Favorites'
import './App.css'

// ==========================================
// 2. CONFIGURAZIONE INIZIALE & COSTANTI
// ==========================================
const queryClient = new QueryClient()
// URL hardcoded, ripetuto identico (o quasi: DatabaseSelector.jsx usa
// 127.0.0.1 invece di localhost) in più componenti — QueryExecutor.jsx,
// Dashboard.jsx, DatabaseSelector.jsx non importano questa costante, ne
// hanno ciascuno una propria copia.
const API_BASE_URL = 'http://localhost:8000'

// ==========================================
// 3. COMPONENTE INTERFACCIA JCoQL
// ==========================================
function MainInterface() {
  // --- STATI LOCALI ---
  const [selectedLlm, setSelectedLlm] = useState('gemini') 
  
  // Stati del Database (Singolo/Multiplo + Join) gestiti da DatabaseSelector
  const [selectedDatabases, setSelectedDatabases] = useState(['jcoql_test'])
  const [joinConfig, setJoinConfig] = useState(null)

  // Segnale per disattivare il JOIN da un punto diverso dalla sidebar (il
  // banner "Modalità JOIN attiva" in QueryExecutor) — un contatore che, ad
  // ogni incremento, dice a DatabaseSelector di togliere la spunta come se
  // l'avesse tolta l'utente stesso, mantenendo sincronizzati entrambi gli
  // stati (quello qui e quello interno a DatabaseSelector).
  const [joinResetSignal, setJoinResetSignal] = useState(0)
  const handleDisableJoin = () => setJoinResetSignal((s) => s + 1)

  // Preferiti: spostati qui da QueryExecutor.jsx (16/08 → 17/08) per poter
  // mostrare il pannello nella sidebar, sotto "Database" — prima stava in
  // fondo al pannello principale, che con risultati lunghi finiva molto in
  // basso, scomodo da raggiungere. "Salva" resta un'azione avviata da
  // dentro QueryExecutor (il pulsante è lì, vicino alla query corrente),
  // quindi passata giù come callback; "Carica" invece nasce nella sidebar
  // e deve arrivare a QueryExecutor — usa lo stesso meccanismo a segnale
  // già impiegato per la disattivazione del JOIN sopra: un valore che
  // cambia ad ogni click (mai lo stesso riferimento due volte, altrimenti
  // cliccare due volte di fila la stessa preferita non farebbe scattare
  // l'effect in QueryExecutor la seconda volta).
  const [favorites, setFavorites] = useState(() => loadFavorites())
  useEffect(() => {
    persistFavorites(favorites)
  }, [favorites])
  const [favoriteToLoad, setFavoriteToLoad] = useState(null)
  const handleLoadFavoriteRequest = (fav) => setFavoriteToLoad({ ...fav, _loadTs: Date.now() })
  const handleSaveFavorite = (newFavorite) => setFavorites([newFavorite, ...favorites])
  const handleDeleteFavorite = (id) => setFavorites(favorites.filter((f) => f.id !== id))

  // --- STATO PARSER ATTIVO (letto dal backend, non più hardcoded) ---
  const [activeParser, setActiveParser] = useState(null)

  // --- EFFECT: CARICAMENTO PARSER ATTIVO DAL BACKEND ---
  useEffect(() => {
    axios.get(`${API_BASE_URL}/api/parsers`)
      .then(res => setActiveParser(res.data.current_name || res.data.current))
      .catch(err => console.error('Errore caricamento parser attivo:', err))
  }, [])

  // --- EFFECT: CARICAMENTO INIZIALE DA LOCAL STORAGE ---
  useEffect(() => {
    try {
      const savedDb = localStorage.getItem('jcoql_selected_databases')
      const savedJoin = localStorage.getItem('jcoql_join_config')
      
      if (savedDb) setSelectedDatabases(JSON.parse(savedDb))
      if (savedJoin) setJoinConfig(JSON.parse(savedJoin))
    } catch (err) {
      console.warn('Errore caricamento configurazioni salvate:', err)
    }
  }, [])

  // --- HANDLER: CAMBIO LLM ---
  // Nota: se response.data.success è false (senza che axios sollevi
  // un'eccezione), il catch sotto non scatta e selectedLlm non viene
  // aggiornato — ma non c'è nemmeno un messaggio per l'utente in quel
  // caso specifico (l'alert scatta solo nel branch catch).
  const handleLlmChange = async (e) => {
    const newLlm = e.target.value
    try {
      const response = await axios.post(`${API_BASE_URL}/api/set_llm`, null, {
        params: { llm_type: newLlm }
      })
      if (response.data.success) {
        setSelectedLlm(newLlm)
      }
    } catch (error) {
      console.error('Errore durante il cambio LLM:', error)
      alert('Errore nel cambio LLM')
    }
  }

  // --- HANDLER: GESTIONE UNIFICATA DATABASE (Da DatabaseSelector) ---
  const handleDatabasesChange = (databases, join) => {
    setSelectedDatabases(databases)
    setJoinConfig(join)
    
    // Salva in localStorage per persistenza
    try {
      localStorage.setItem('jcoql_selected_databases', JSON.stringify(databases))
      if (join) {
        localStorage.setItem('jcoql_join_config', JSON.stringify(join))
      } else {
        localStorage.removeItem('jcoql_join_config')
      }
    } catch (err) {
      console.warn('Errore salvataggio in localStorage:', err)
    }
  }

  // --- MUTATION REACT QUERY: GENERAZIONE QUERY JCoQL ---
  // NOTA (14/08): questa mutation e l'intera sezione "Input Linguaggio
  // Naturale" che la usava sono state rimosse da qui — duplicavano
  // esattamente la stessa generazione già presente dentro QueryExecutor.jsx
  // (stessa chiamata a /api/generate, stesso risultato mostrato due volte
  // in due punti diversi della pagina). QueryExecutor è ora l'unico punto
  // di generazione ed esecuzione in tutta l'app.

  // ==========================================
  // RENDER DELL'INTERFACCIA
  // ==========================================
  return (
    <div className="app-wrapper">

      {/* ════════════════ HEADER ════════════════ */}
      <header className="app-header">
        <div className="header-content">
          <h1> JCoQL+ Natural Language Interface</h1>
          
          <div className="header-info">
            <span className="info-item">
              <strong>Parser:</strong> {activeParser || 'Caricamento...'}
            </span>
            <span className="info-item">
              <strong>LLM:</strong>
              <select 
                value={selectedLlm} 
                onChange={handleLlmChange} 
                className="llm-selector"
                title={`Attuale: ${selectedLlm === 'gemini' ? 'Cloud (Google API)' : 'Locale (Ollama)'}`}
              >
                <option value="gemini">☁️ Gemini (Cloud)</option>
                <option value="llama">🏠 Llama (Locale - 4.7GB)</option>
                <option value="gemma">🏠 Gemma (Locale - 5.4GB) </option>
              </select>
            </span>
          </div>

          <div className="header-actions">
            <Link to="/dashboard" className="dashboard-btn">
              📊 Dashboard
            </Link>
          </div>
        </div>

        {selectedLlm === 'llama' && (
          <div style={{ marginTop: '12px', padding: '10px', background: 'rgba(255, 204, 0, 0.2)', border: '1px solid rgba(255, 204, 0, 0.5)', borderRadius: '6px', fontSize: '13px' }}>
            <strong>⚠️ Nota VRAM:</strong> Llama richiede 4.7GB. 
            Se hai appena usato Gemma, riavvia Ollama per liberare memoria: 
            <code style={{ background: 'rgba(0,0,0,0.3)', padding: '2px 6px', borderRadius: '4px', marginLeft: '6px' }}>ollama stop gemma</code>
          </div>
        )}
        {selectedLlm === 'gemma' && (
          <div style={{ marginTop: '12px', padding: '10px', background: 'rgba(255, 204, 0, 0.2)', border: '1px solid rgba(255, 204, 0, 0.5)', borderRadius: '6px', fontSize: '13px' }}>
            <strong>⚠️ Nota VRAM:</strong> Gemma richiede 5.4GB. 
            Se hai appena usato Llama, riavvia Ollama per liberare memoria: 
            <code style={{ background: 'rgba(0,0,0,0.3)', padding: '2px 6px', borderRadius: '4px', marginLeft: '6px' }}>ollama stop</code>
          </div>
        )}
      </header>

      {/* ════════════════ MAIN LAYOUT ════════════════ */}
      <div className="app-layout">
        
        {/* ──────────── SIDEBAR (Sinistra) ──────────── */}
        <aside className="sidebar">
          <DatabaseSelector 
            onDatabasesChange={handleDatabasesChange}
            selectedDatabases={selectedDatabases}
            resetJoinSignal={joinResetSignal}
          />
        </aside>

        {/* ──────────── MAIN CONTENT (Centro) ──────────── */}
        <main className="main-content">

          {/* QUERY EXECUTOR — unico punto di generazione ed esecuzione
              (vedi nota sopra: prima c'era anche una sezione "Input
              Linguaggio Naturale" qui, duplicata rispetto a quella dentro
              QueryExecutor stesso — rimossa). */}
          <section className="bg-white rounded-lg shadow p-6">
            <QueryExecutor
              selectedDatabases={selectedDatabases}
              joinConfig={joinConfig}
              llmModel={selectedLlm}
              onDisableJoin={handleDisableJoin}
              favoriteToLoad={favoriteToLoad}
              onSaveFavorite={handleSaveFavorite}
            />
          </section>

        </main>

        {/* ──────────── PREFERITI (Destra) ────────────
            Colonna propria (17/08), non più sotto Database nella sidebar —
            il form del JOIN può allungarsi parecchio, spingendo i
            preferiti fuori schermo. Qui l'altezza della sidebar non la
            tocca mai. */}
        <aside className="favorites-column">
          <Favorites
            favorites={favorites}
            onLoad={handleLoadFavoriteRequest}
            onDelete={handleDeleteFavorite}
          />
        </aside>
      </div>

      {/* ════════════════ FOOTER ════════════════ */}
      <footer className="app-footer">
        <p>Iotti Nicholas</p>
        <p>JCoQL+ NL Interface | Università degli Studi di Bergamo</p>
      </footer>
    </div>
  )
}

// ==========================================
// 4. CONFIGURAZIONE ROUTING & PROVIDER GLOBALI
// ==========================================
export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<MainInterface />} />
          <Route path="/dashboard" element={<Dashboard />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
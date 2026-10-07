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
import History, { loadHistory, persistHistory, MAX_HISTORY_ENTRIES } from './History'
import HelpGuide from './HelpGuide'
import ToastContainer, { showToast } from './Toast'
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
  
  // Stato dei database selezionati (multiplo), gestito da DatabaseSelector.
  // Non include configurazione di JOIN: un JOIN resta comunque possibile
  // scrivendo a mano o generando via NL un comando nel pannello query di
  // QueryExecutor, indipendentemente da questo stato.
  const [selectedDatabases, setSelectedDatabases] = useState(['jcoql_test'])

  // Preferiti: "Salva" è un'azione avviata da dentro QueryExecutor (il
  // pulsante è lì, vicino alla query corrente), passata giù come callback;
  // "Carica" invece nasce da qui (sidebar) e deve arrivare a QueryExecutor
  // — usa un meccanismo a segnale: un valore che cambia ad ogni click (mai
  // lo stesso riferimento due volte, altrimenti cliccare due volte di fila
  // la stessa preferita non farebbe scattare l'effect in QueryExecutor la
  // seconda volta).
  const [favorites, setFavorites] = useState(() => loadFavorites())
  useEffect(() => {
    persistFavorites(favorites)
  }, [favorites])
  const [favoriteToLoad, setFavoriteToLoad] = useState(null)
  const handleLoadFavoriteRequest = (fav) => setFavoriteToLoad({ ...fav, _loadTs: Date.now() })
  const handleSaveFavorite = (newFavorite) => setFavorites([newFavorite, ...favorites])
  const handleDeleteFavorite = (id) => setFavorites(favorites.filter((f) => f.id !== id))

  // Cronologia: stesso schema dei Preferiti sopra, ma il "salva" non è
  // un'azione dell'utente — QueryExecutor chiama onAddHistory ad OGNI
  // esecuzione (riuscita o no), tramite handleAddHistory qui sotto, che
  // aggiunge in testa e taglia a MAX_HISTORY_ENTRIES (50, in History.jsx)
  // scartando le voci più vecchie in eccesso.
  const [history, setHistory] = useState(() => loadHistory())
  useEffect(() => {
    persistHistory(history)
  }, [history])
  const [historyToLoad, setHistoryToLoad] = useState(null)
  const handleLoadHistoryRequest = (item) => setHistoryToLoad({ ...item, _loadTs: Date.now() })
  const handleAddHistory = (entry) =>
    setHistory((prev) => [entry, ...prev].slice(0, MAX_HISTORY_ENTRIES))
  const handleDeleteHistoryItem = (id) =>
    setHistory((prev) => prev.filter((h) => h.id !== id))
  const handleClearHistory = () => setHistory([])

  // --- STATO PARSER ATTIVO (letto dal backend, non più hardcoded) ---
  const [activeParser, setActiveParser] = useState(null)

  // --- EFFECT: CARICAMENTO PARSER ATTIVO DAL BACKEND ---
  useEffect(() => {
    axios.get(`${API_BASE_URL}/api/parsers`)
      .then(res => setActiveParser(res.data.current_name || res.data.current))
      .catch(err => console.error('Error loading active parser:', err))
  }, [])

  // --- EFFECT: CARICAMENTO INIZIALE DA LOCAL STORAGE ---
  useEffect(() => {
    try {
      const savedDb = localStorage.getItem('jcoql_selected_databases')

      if (savedDb) setSelectedDatabases(JSON.parse(savedDb))
      // Rimuove anche da localStorage l'eventuale chiave del vecchio JOIN
      // nativo (non più letta in nessun punto del codice), nel caso fosse
      // rimasta da una sessione precedente.
      localStorage.removeItem('jcoql_join_config')
    } catch (err) {
      console.warn('Error loading saved settings:', err)
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
      console.error('Error while switching LLM:', error)
      showToast('Error switching LLM', 'error')
    }
  }

  // --- HANDLER: GESTIONE UNIFICATA DATABASE (Da DatabaseSelector) ---
  const handleDatabasesChange = (databases) => {
    setSelectedDatabases(databases)

    // Salva in localStorage per persistenza
    try {
      localStorage.setItem('jcoql_selected_databases', JSON.stringify(databases))
    } catch (err) {
      console.warn('Error saving to localStorage:', err)
    }
  }

  // La generazione ed esecuzione delle query vive interamente dentro
  // QueryExecutor.jsx: è l'unico punto dell'app che chiama /api/generate,
  // non duplicarla qui.

  // ==========================================
  // RENDER DELL'INTERFACCIA
  // ==========================================
  return (
    <div className="app-wrapper">

      {/* ════════════════ HEADER ════════════════ */}
      <header className="app-header">
        <div className="header-content">
          <h1> J-CO-QL+ Natural Language Interface</h1>
          
          <div className="header-info">
            <span className="info-item">
              <strong>Parser:</strong> {activeParser || 'Loading...'}
            </span>
            <span className="info-item">
              <strong>LLM:</strong>
              <select 
                value={selectedLlm} 
                onChange={handleLlmChange} 
                className="llm-selector"
                title={`Current: ${selectedLlm === 'gemini' ? 'Cloud (Google API)' : 'Local (Ollama)'}`}
              >
                <option value="gemini">☁️ Gemini (Cloud)</option>
                <option value="llama">🏠 Llama 3.1 8B (Local - 4.7GB)</option>
                <option value="gemma">🏠 Gemma 1 7B (Local - 5.4GB) </option>
                <option value="llama32">🏠 Llama 3.2 3B (Local - 2GB)</option>
                <option value="gemma4">🏠 Gemma 4 E4B (Local - 6.6GB)</option>
              </select>
            </span>
          </div>

          <div className="header-actions">
            <HelpGuide />
            <Link to="/dashboard" className="dashboard-btn">
              📊 Dashboard
            </Link>
          </div>
        </div>

        {/* I 4 blocchi VRAM qui sotto (Llama 3.1, Gemma 1.7, Llama 3.2,
            Gemma4) usano tutti lo stesso formato generico `ollama ps` +
            `ollama stop <nome-modello>` (uniformato il 04/10: Llama e
            Gemma indicavano prima "l'altro" modello per nome in modo
            fisso — ollama stop gemma / ollama stop — pensato quando
            erano gli unici due disponibili; con 4 modelli locali non è
            più pratico indicarlo per nome, meglio controllare cos'è
            davvero caricato con `ollama ps`). */}
        {selectedLlm === 'llama' && (
          <div style={{ marginTop: '12px', padding: '10px', background: 'rgba(255, 204, 0, 0.2)', border: '1px solid rgba(255, 204, 0, 0.5)', borderRadius: '6px', fontSize: '13px' }}>
            <strong>⚠️ VRAM note:</strong> Llama 3.1 8B requires ~4.7GB.
            If you have just used another local model, check what is still loaded and stop it:
            <code style={{ background: 'rgba(0,0,0,0.3)', padding: '2px 6px', borderRadius: '4px', marginLeft: '6px' }}>ollama ps</code>
            {' '}then{' '}
            <code style={{ background: 'rgba(0,0,0,0.3)', padding: '2px 6px', borderRadius: '4px', marginLeft: '6px' }}>ollama stop &lt;model-name&gt;</code>
          </div>
        )}
        {selectedLlm === 'gemma' && (
          <div style={{ marginTop: '12px', padding: '10px', background: 'rgba(255, 204, 0, 0.2)', border: '1px solid rgba(255, 204, 0, 0.5)', borderRadius: '6px', fontSize: '13px' }}>
            <strong>⚠️ VRAM note:</strong> Gemma 1 7B requires ~5.4GB.
            If you have just used another local model, check what is still loaded and stop it:
            <code style={{ background: 'rgba(0,0,0,0.3)', padding: '2px 6px', borderRadius: '4px', marginLeft: '6px' }}>ollama ps</code>
            {' '}then{' '}
            <code style={{ background: 'rgba(0,0,0,0.3)', padding: '2px 6px', borderRadius: '4px', marginLeft: '6px' }}>ollama stop &lt;model-name&gt;</code>
          </div>
        )}
        {selectedLlm === 'llama32' && (
          <div style={{ marginTop: '12px', padding: '10px', background: 'rgba(255, 204, 0, 0.2)', border: '1px solid rgba(255, 204, 0, 0.5)', borderRadius: '6px', fontSize: '13px' }}>
            <strong>⚠️ VRAM note:</strong> Llama 3.2 3B requires ~2GB.
            If you have just used another local model, check what is still loaded and stop it:
            <code style={{ background: 'rgba(0,0,0,0.3)', padding: '2px 6px', borderRadius: '4px', marginLeft: '6px' }}>ollama ps</code>
            {' '}then{' '}
            <code style={{ background: 'rgba(0,0,0,0.3)', padding: '2px 6px', borderRadius: '4px', marginLeft: '6px' }}>ollama stop &lt;model-name&gt;</code>
          </div>
        )}
        {selectedLlm === 'gemma4' && (
          <div style={{ marginTop: '12px', padding: '10px', background: 'rgba(255, 204, 0, 0.2)', border: '1px solid rgba(255, 204, 0, 0.5)', borderRadius: '6px', fontSize: '13px' }}>
            <strong>⚠️ VRAM note:</strong> Gemma 4 E4B requires ~6.6GB.
            If you have just used another local model, check what is still loaded and stop it:
            <code style={{ background: 'rgba(0,0,0,0.3)', padding: '2px 6px', borderRadius: '4px', marginLeft: '6px' }}>ollama ps</code>
            {' '}then{' '}
            <code style={{ background: 'rgba(0,0,0,0.3)', padding: '2px 6px', borderRadius: '4px', marginLeft: '6px' }}>ollama stop &lt;model-name&gt;</code>
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
              llmModel={selectedLlm}
              favoriteToLoad={favoriteToLoad}
              onSaveFavorite={handleSaveFavorite}
              historyToLoad={historyToLoad}
              onAddHistory={handleAddHistory}
            />
          </section>

        </main>

        {/* ──────────── PREFERITI (Destra) ────────────
            Colonna propria, indipendente dall'altezza della sidebar a
            sinistra. */}
        <aside className="favorites-column">
          <Favorites
            favorites={favorites}
            onLoad={handleLoadFavoriteRequest}
            onDelete={handleDeleteFavorite}
          />
          {/* Cronologia: stessa colonna dei Preferiti, subito sotto. */}
          <div style={{ marginTop: '16px' }}>
            <History
              history={history}
              onLoad={handleLoadHistoryRequest}
              onDelete={handleDeleteHistoryItem}
              onClear={handleClearHistory}
            />
          </div>
        </aside>
      </div>

      {/* ════════════════ FOOTER ════════════════ */}
      <footer className="app-footer">
        <p>Iotti Nicholas</p>
        <p>J-CO-QL+ NL Interface | University of Bergamo</p>
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
        {/* Montato una sola volta qui fuori (non dentro MainInterface) così
            resta attivo anche navigando su /dashboard, invece di
            smontarsi/rimontarsi ad ogni cambio pagina. */}
        <ToastContainer />
        <Routes>
          <Route path="/" element={<MainInterface />} />
          <Route path="/dashboard" element={<Dashboard />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
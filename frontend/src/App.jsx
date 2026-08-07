// ==========================================
// 1. IMPORTAZIONI DEI MODULI E DEI COMPONENTI
// ==========================================
import React, { useState, useEffect } from 'react'
import { QueryClient, QueryClientProvider, useMutation } from '@tanstack/react-query'
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom'
import axios from 'axios'

// Import dei componenti
import DatabaseSelector from './DatabaseSelector'
import QueryExecutor from './QueryExecutor'
import Dashboard from './Dashboard'
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
  const [nlQuery, setNlQuery] = useState('') 
  const [result, setResult] = useState(null) 
  const [selectedLlm, setSelectedLlm] = useState('gemini') 
  
  // Stati del Database (Singolo/Multiplo + Join) gestiti da DatabaseSelector
  const [selectedDatabases, setSelectedDatabases] = useState(['jcoql_test'])
  const [joinConfig, setJoinConfig] = useState(null)

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
  // Nota: parser_type è passato come stringa fissa 'antlr3_official' —
  // il campo "Parser" nell'header (activeParser, sopra) mostra quello
  // realmente attivo sul backend, ma la richiesta effettiva continua a
  // dichiarare sempre antlr3_official indipendentemente da cosa
  // risponde /api/parsers. Coincide col default lato server, quindi non
  // causa un mismatch nella situazione attuale, ma i due valori non sono
  // collegati fra loro nel codice.
  const generateMutation = useMutation({
    mutationFn: async (query) => {
      const response = await axios.post(`${API_BASE_URL}/api/generate`, {
        nl_query: query,
        database: selectedDatabases[0],
        join_config: joinConfig,
        max_retries: 2,
        parser_type: 'antlr3_official'
      })
      return response.data
    },
    onSuccess: (data) => {
      setResult(data)
    }
  })

  // Esempi predefiniti per test rapido
  const exampleQueries = [
    "Hotel a Milano",
    "Prodotti di elettronica con sconto maggiore del 20%",
    "Ristoranti aperti a Napoli"
  ]

  const handleGenerate = () => {
    if (nlQuery.trim()) {
      generateMutation.mutate(nlQuery)
    }
  }

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
          />
        </aside>

        {/* ──────────── MAIN CONTENT (Destra) ──────────── */}
        <main className="main-content">
          
          {/* SEZIONE GENERATORE NL (AGGIORNATA CON HEADER GRADIENTE) */}
          <section className="bg-white rounded-lg shadow mb-6 overflow-hidden">
            
            {/* Banner con gradiente per uniformità con Query Executor */}
            <div className="bg-gradient-to-r from-blue-600 to-purple-600 p-6 text-white">
              <div className="flex items-center gap-3">
                <span className="text-3xl">📝</span>
                <h2 className="text-2xl font-bold">Input Linguaggio Naturale</h2>
              </div>
              <p className="text-blue-100 mt-1">Traduci la tua richiesta in query JCoQL</p>
            </div>
            
            {/* Contenitore interno con padding ripristinato */}
            <div className="p-6">
              <div className="mb-4">
                <p className="text-sm text-gray-600 mb-2">Esempi rapidi:</p>
                <div className="flex flex-wrap gap-2">
                  {exampleQueries.map((ex, i) => (
                    <button
                      key={i}
                      onClick={() => setNlQuery(ex)}
                      className="px-3 py-1 bg-gray-100 hover:bg-gray-200 rounded text-sm transition-colors"
                    >
                      {ex.substring(0, 30)}...
                    </button>
                  ))}
                </div>
              </div>

              <textarea
                value={nlQuery}
                onChange={(e) => setNlQuery(e.target.value)}
                placeholder="Scrivi la tua richiesta in italiano..."
                className="w-full h-32 p-4 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
              />

              {/* Fix visibilità bottone disabilitato */}
              <button
                onClick={handleGenerate}
                disabled={generateMutation.isPending || !nlQuery.trim()}
                className="w-full mt-4 px-6 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 disabled:text-gray-600 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors"
              >
                {generateMutation.isPending ? (
                  <span>🔄 Generazione in corso...</span>
                ) : (
                  <span>🚀 Genera Query JCoQL</span>
                )}
              </button>

              {generateMutation.isError && (
                <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg">
                  <p className="text-sm text-red-800">
                    <strong>Errore:</strong> {generateMutation.error.response?.data?.detail || generateMutation.error.message}
                  </p>
                </div>
              )}
            </div>
          </section>

          {/* VISUALIZZAZIONE QUERY GENERATA */}
          {result && (
            <section className="bg-white rounded-lg shadow p-6 mb-6">
              <h2 className="text-lg font-semibold mb-4 text-gray-800">⚡ Query JCoQL Generata</h2>
              <div className="bg-gray-900 rounded-lg p-4">
                <pre className="text-green-400 text-sm font-mono whitespace-pre-wrap">{result.jcoql_query}</pre>
              </div>
              
              <div className="mt-4 flex items-center justify-between">
                <div className="flex items-center space-x-4">
                  <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                    result.is_valid ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                  }`}>
                    {result.is_valid ? '✅ Valida' : '❌ Invalida'}
                  </span>
                  <span className="text-sm text-gray-600">
                    Tentativi: {result.attempts}
                  </span>
                </div>
                
                <button
                  onClick={() => navigator.clipboard.writeText(result.jcoql_query)}
                  className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg text-sm transition-colors"
                >
                  📋 Copia Query
                </button>
              </div>

              {!result.is_valid && result.validation_errors?.length > 0 && (
                <div className="mt-4 bg-red-50 border border-red-200 rounded-lg p-4">
                  <h3 className="text-sm font-semibold text-red-800 mb-2">⚠️ Errori di Validazione:</h3>
                  <ul className="space-y-1">
                    {result.validation_errors.map((error, idx) => (
                      <li key={idx} className="text-sm text-red-700">• {error.message}</li>
                    ))}
                  </ul>
                </div>
              )}
            </section>
          )}

          {/* QUERY EXECUTOR */}
          <section className="bg-white rounded-lg shadow p-6" style={{ marginTop: '48px' }}>
            <QueryExecutor 
              selectedDatabases={selectedDatabases}
              joinConfig={joinConfig}
              llmModel={selectedLlm}
              initialQuery={result?.jcoql_query || ''}
            />
          </section>

        </main>
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
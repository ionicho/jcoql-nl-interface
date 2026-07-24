// ==========================================
// 1. IMPORTAZIONI DEI MODULI E DEI COMPONENTI
// ==========================================
import { QueryClient, QueryClientProvider, useMutation } from '@tanstack/react-query'
import axios from 'axios'
import { useState, useEffect } from 'react'
import { BrowserRouter, Route, Routes, Link } from 'react-router-dom'

// Import dei componenti delle diverse pagine dell'applicazione
import Dashboard from './Dashboard'
import QueryExecutor from './QueryExecutor'
import UploadData from './UploadData'
// ✅ Import del componente DatabaseManager per la gestione dei DB
import DatabaseManager from './DatabaseManager'

// ==========================================
// 2. CONFIGURAZIONE INIZIALE & COSTANTI
// ==========================================
// Inizializzazione del client React Query per la gestione dello stato e delle richieste asincrone
const queryClient = new QueryClient()

// URL base delle API backend FastAPI/Python
const API_BASE_URL = 'http://localhost:8000'

// ==========================================
// 3. COMPONENTE PRINCIPALE INTERFACCIA JCoQL
// ==========================================
function JCoQLInterface() {
  // --- STATI LOCALI ---
  const [nlQuery, setNlQuery] = useState('') // Contiene la richiesta in linguaggio naturale
  const [result, setResult] = useState(null) // Memorizza la risposta ricevuta dal backend
  const [selectedLlm, setSelectedLlm] = useState('gemini') // LLM selezionato (Cloud o Locale)
  const [selectedDatabase, setSelectedDatabase] = useState("jcoql_test") // Database MongoDB selezionato
  const [databases, setDatabases] = useState([]) // Lista dei database disponibili

  // --- HANDLER: CAMBIO LLM ---
  // Invia al backend la scelta del modello LLM da utilizzare (Gemini, Llama, Gemma)
  const handleLlmChange = async (e) => {
    const newLlm = e.target.value
    try {
      const response = await axios.post(`${API_BASE_URL}/api/set_llm`, null, {
        params: { llm_type: newLlm }
      })
      if (response.data.success) {
        setSelectedLlm(newLlm)
        console.log(`LLM cambiato con successo: ${newLlm}`)
      }
    } catch (error) {
      console.error('Errore durante il cambio LLM:', error)
      alert('Errore nel cambio LLM')
    }
  }

  // --- MUTATION REACT QUERY: GENERAZIONE QUERY JCoQL ---
  // Invia la richiesta in linguaggio naturale al backend per generare la query JCoQL
  const generateMutation = useMutation({
    mutationFn: async (query) => {
      const response = await axios.post(`${API_BASE_URL}/api/generate`, {
        nl_query: query,
        max_retries: 2,
        parser_type: 'antlr3_official' // Fissato fisso sul parser ANTLR3 Official
      })
      return response.data
    },
    onSuccess: (data) => {
      setResult(data) // Salva il risultato nello stato locale per la visualizzazione
    }
  })

  // Esempi predefiniti per test rapido
  const exampleQueries = [
    "Hotel a Milano con rating superiore a 4",
    "Prodotti con prezzo tra 100 e 200 euro",
    "Utenti senza email registrata"
  ]

  // Esegue la mutazione se il testo inserito non è vuoto
  const handleGenerate = () => {
    if (nlQuery.trim()) {
      generateMutation.mutate(nlQuery)
    }
  }

  // --- EFFECT: CARICAMENTO LISTA DATABASE ---
  // All'avvio del componente recupera dal backend l'elenco dei database presenti
  useEffect(() => {
    fetch(`${API_BASE_URL}/api/databases`)
      .then(res => res.json())
      .then(data => setDatabases(data.databases || []))
      .catch(err => console.error("Errore nel caricamento dei database:", err))
  }, [])

  // --- HANDLER: CAMBIO DATABASE ATTIVO ---
  // Notifica al backend la selezione di un nuovo database su cui operare
  const switchDatabase = async (dbName) => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/databases/select?database_name=${dbName}`,
        { method: "POST" }
      )
      const data = await response.json()
      
      if (data.success) {
        setSelectedDatabase(dbName)
        console.log(`✅ Database cambiato in: ${dbName}`)
      }
    } catch (err) {
      console.error("Errore durante il cambio del database:", err)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      
      {/* ==========================================
          HEADER / BARRA DI NAVIGAZIONE
          ========================================== */}
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex justify-between items-center">
            
            {/* Titolo Principale */}
            <h1 className="text-2xl font-bold text-gray-800">JCoQL+ Interface</h1>
            
            <div className="flex items-center space-x-4">
              
              {/* 1. Selettore Rapido Database */}
              <div className="database-selector flex items-center space-x-2">
                <label className="text-sm text-gray-600">DB:</label>
                <select 
                  value={selectedDatabase} 
                  onChange={(e) => switchDatabase(e.target.value)}
                  className="px-3 py-1 bg-white border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  {databases.map(db => (
                    <option key={db.name} value={db.name}>
                      {db.name} ({db.collections} coll.) {db.current ? " ✓" : ""}
                    </option>
                  ))}
                </select>
              </div>

              {/* 2. Selettore Modello LLM */}
              <div className="flex items-center space-x-2">
                <label className="text-sm text-gray-600">LLM:</label>
                <select 
                  value={selectedLlm} 
                  onChange={handleLlmChange}
                  className="px-3 py-1 bg-white border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  title={`Attuale: ${selectedLlm === 'gemini' ? 'Cloud (Google API)' : 'Locale (Ollama)'}`}
                >
                  <option value="gemini">☁️ Gemini (Cloud)</option>
                  <option value="llama">🏠 Llama (Locale - 4.7GB)</option>
                  <option value="gemma">🏠 Gemma (Locale - 5.4GB) ⚠️</option>
                </select>
              </div>

              {/* 3. Link di Navigazione tra le Pagine dell'App */}
              <Link
                to="/dashboard"
                className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg text-sm transition-colors"
              >
                📊 Dashboard
              </Link>
              
              <Link 
                to="/executor" 
                className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg text-sm transition-colors"
              >
                🔍 Query Executor
              </Link>

              {/* ✅ LINK AGGIUNTO: Navigazione verso il nuovo DatabaseManager */}
              <Link 
                to="/databases" 
                className="px-4 py-2 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 font-medium rounded-lg text-sm transition-colors border border-indigo-200"
              >
                🗄️ Gestisci DB
              </Link>

            </div>
          </div>

          {/* Avviso speciale in caso di scelta del modello Gemma */}
          {selectedLlm === 'gemma' && (
            <div className="mt-3 p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
              <p className="text-xs text-yellow-800">
                <strong>⚠️ Nota VRAM:</strong> Gemma richiede 5.4GB. 
                Se hai appena usato Llama, riavvia Ollama per liberare memoria: 
                <code className="ml-1 px-1 bg-yellow-100 rounded">ollama stop</code>
              </p>
            </div>
          )}
        </div>
      </header>

      {/* ==========================================
          CONTENUTO PRINCIPALE (MAIN)
          ========================================== */}
      <main className="max-w-7xl mx-auto px-4 py-8">
        
        {/* Card Input Testo */}
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold mb-4 text-gray-800">📝 Input Linguaggio Naturale</h2>
          
          {/* Pulsanti Esempi Rapidi */}
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

          {/* Textarea Prompt */}
          <textarea
            value={nlQuery}
            onChange={(e) => setNlQuery(e.target.value)}
            placeholder="Scrivi la tua richiesta in italiano..."
            className="w-full h-32 p-4 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent resize-none"
          />

          {/* Botton di Generazione */}
          <button
            onClick={handleGenerate}
            disabled={generateMutation.isPending || !nlQuery.trim()}
            className="w-full mt-4 px-6 py-3 bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-400 text-white font-medium rounded-lg transition-colors"
          >
            {generateMutation.isPending ? (
              <span>🔄 Generazione in corso...</span>
            ) : (
              <span>🚀 Genera Query JCoQL</span>
            )}
          </button>

          {/* Gestione Errori di Rete/Server */}
          {generateMutation.isError && (
            <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-sm text-red-800">
                <strong>Errore:</strong> {generateMutation.error.response?.data?.detail || generateMutation.error.message}
              </p>
            </div>
          )}
        </div>

        {/* ==========================================
            VISUALIZZAZIONE RISULTATI DELLA GENERAZIONE
            ========================================== */}
        {result && (
          <div className="mt-6 space-y-4">
            
            {/* Box Query Generata */}
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-lg font-semibold mb-4 text-gray-800">⚡ Query JCoQL Generata</h2>
              <div className="bg-gray-900 rounded-lg p-4">
                <pre className="text-green-400 text-sm font-mono whitespace-pre-wrap">{result.jcoql_query}</pre>
              </div>
              
              <div className="mt-4 flex items-center justify-between">
                <div className="flex items-center space-x-4">
                  {/* Badge Stato Validazione */}
                  <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                    result.is_valid ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                  }`}>
                    {result.is_valid ? '✅ Valida' : '❌ Invalida'}
                  </span>
                  <span className="text-sm text-gray-600">
                    Tentativi: {result.attempts}
                  </span>
                </div>
                
                {/* Pulsante Copia negli Appunti */}
                <button
                  onClick={() => navigator.clipboard.writeText(result.jcoql_query)}
                  className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg text-sm transition-colors"
                >
                  📋 Copia
                </button>
              </div>
            </div>

            {/* Errori di Validazione Sintattica (se la query è invalida) */}
            {!result.is_valid && result.validation_errors?.length > 0 && (
              <div className="bg-white rounded-lg shadow p-6">
                <h3 className="text-lg font-semibold text-red-600 mb-4">⚠️ Errori di Validazione</h3>
                <ul className="space-y-2">
                  {result.validation_errors.map((error, idx) => (
                    <li key={idx} className="p-3 bg-red-50 rounded-lg text-sm text-red-800">
                      {error.message}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Esempi usati dalla ricerca RAG */}
            {result.retrieved_examples?.length > 0 && (
              <div className="bg-white rounded-lg shadow p-6">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">📚 Esempi RAG Utilizzati</h3>
                <div className="space-y-3">
                  {result.retrieved_examples.slice(0, 2).map((example, idx) => (
                    <details key={idx} className="p-3 bg-gray-50 rounded-lg">
                      <summary className="cursor-pointer text-sm font-medium text-gray-700">
                        Esempio {idx + 1}
                      </summary>
                      <pre className="mt-2 text-xs text-gray-600 whitespace-pre-wrap">
                        {example.substring(0, 200)}...
                      </pre>
                    </details>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Stato Placeholder vuoto (prima di generare alcuna query) */}
        {!result && !generateMutation.isPending && (
          <div className="mt-6 bg-white rounded-lg shadow p-12 text-center">
            <div className="text-6xl mb-4">🔍</div>
            <h3 className="text-xl font-semibold text-gray-900 mb-2">
              In attesa di input
            </h3>
            <p className="text-gray-600">
              Scrivi una richiesta in linguaggio naturale e premi &quot;Genera Query JCoQL&quot;
            </p>
          </div>
        )}
      </main>

      {/* ==========================================
          FOOTER
          ========================================== */}
      <footer className="mt-12 pb-8">
        <div className="max-w-7xl mx-auto px-4">
          <div className="text-center text-sm text-gray-500">
            <p>JCoQL+ NL Interface | Tesi Magistrale Università Bergamo</p>
            <p className="mt-1">
              {result && result.llm_used ? (
                <>
                  <span className="font-medium text-indigo-600">
                    LLM: {result.llm_used.toUpperCase()} 
                    {result.llm_used === 'gemini' ? ' ☁️ Cloud' : ' 🏠 Locale'}
                  </span>
                  {' | '}
                  <span className="font-medium text-green-600">
                    Parser: ANTLR3 Official
                  </span>
                </>
              ) : (
                "RAG + Multi-LLM (Cloud/Locale) + ANTLR3 Official Parser"
              )}
            </p>
          </div>
        </div>
      </footer>
    </div>
  )
}

// ==========================================
// 4. CONFIGURAZIONE ROUTING & PROVIDER GLOBALI
// ==========================================
export default function App() {
  return (
    // QueryClientProvider permette a tutti i componenti figli di usare gli hook di React Query
    <QueryClientProvider client={queryClient}>
      {/* BrowserRouter gestisce la navigazione SPA (Single Page Application) */}
      <BrowserRouter>
        <Routes>
          {/* Rotta principale dell'interfaccia (Generatore Query JCoQL) */}
          <Route path="/" element={<JCoQLInterface />} />
          
          {/* Rotta Dashboard Statistiche */}
          <Route path="/dashboard" element={<Dashboard />} />
          
          {/* Rotta Esecutore Query */}
          <Route path="/executor" element={<QueryExecutor />} />
          
          {/* Rotta Upload Dati */}
          <Route path="/upload" element={<UploadData />} />

          {/* ✅ NUOVA ROTTA REGISTRATA: Rotta per la gestione avanzata dei Database */}
          <Route path="/databases" element={<DatabaseManager />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
import { QueryClient, QueryClientProvider, useMutation } from '@tanstack/react-query'
import axios from 'axios'
import { useState } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import Dashboard from './Dashboard'

const queryClient = new QueryClient()
const API_BASE_URL = 'http://localhost:8000'

function JCoQLInterface() {
  const [nlQuery, setNlQuery] = useState('')
  const [result, setResult] = useState(null)

  const generateMutation = useMutation({
    mutationFn: async (query) => {
      const response = await axios.post(`${API_BASE_URL}/api/generate`, {
        nl_query: query,
        max_retries: 2
      })
      return response.data
    },
    onSuccess: (data) => {
      setResult(data)
    }
  })

  const exampleQueries = [
    "Hotel a Milano con rating superiore a 4",
    "Prodotti con prezzo tra 100 e 200 euro"
  ]

  const handleGenerate = () => {
    if (nlQuery.trim()) {
      generateMutation.mutate(nlQuery)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex justify-between items-center">
            <h1 className="text-2xl font-bold">JCoQL+ Interface</h1>
            <a href="/dashboard" className="px-4 py-2 bg-gray-200 rounded">
              Dashboard
            </a>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-8">
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold mb-4">Input</h2>
          
          <div className="mb-4">
            {exampleQueries.map((ex, i) => (
              <button
                key={i}
                onClick={() => setNlQuery(ex)}
                className="mr-2 px-3 py-1 bg-gray-100 rounded text-sm"
              >
                {ex.substring(0, 20)}...
              </button>
            ))}
          </div>

          <textarea
            value={nlQuery}
            onChange={(e) => setNlQuery(e.target.value)}
            placeholder="Scrivi la tua richiesta..."
            className="w-full h-32 p-4 border rounded"
          />

          <button
            onClick={handleGenerate}
            disabled={generateMutation.isPending}
            className="w-full mt-4 px-6 py-3 bg-indigo-600 text-white rounded"
          >
            {generateMutation.isPending ? 'Generazione...' : 'Genera Query'}
          </button>

          {generateMutation.isError && (
            <div className="mt-4 p-4 bg-red-50 rounded">
              <p className="text-red-800">Errore: {generateMutation.error.message}</p>
            </div>
          )}
        </div>

        {result && (
          <div className="mt-6 bg-white rounded-lg shadow p-6">
            <h2 className="text-lg font-semibold mb-4">Output</h2>
            <div className="bg-gray-900 rounded p-4">
              <pre className="text-green-400 text-sm">{result.jcoql_query}</pre>
            </div>
            <p className="mt-2 text-sm">
              Valida: {result.is_valid ? 'Sì' : 'No'} | Tentativi: {result.attempts}
            </p>
          </div>
        )}
      </main>
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<JCoQLInterface />} />
          <Route path="/dashboard" element={<Dashboard />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
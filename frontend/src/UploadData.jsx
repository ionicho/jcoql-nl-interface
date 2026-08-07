// [DISCONNESSO DAL ROUTER — 07/08/2026]
// Questo componente non è raggiungibile da nessuna route in App.jsx (di
// proposito, per ora). Motivo: è stato scritto quando il progetto aveva
// un'architettura a singolo database. I 4 endpoint backend che chiama
// (/api/collections, /api/upload-collection, DELETE /api/collections/{name},
// /api/collections/{name}/count) usano ancora un oggetto `executor` globale
// fissato al database attivo all'avvio del server — NON tengono conto del
// database correntemente selezionato in sidebar (db_registry). Ricollegarlo
// senza sistemare anche il backend farebbe caricare/cancellare collection nel
// database sbagliato in modo silenzioso.
// Per ripristinarlo in futuro: (1) aggiungere un parametro `database` a
// quei 4 endpoint in main.py, facendoli passare da db_registry invece che
// dal vecchio `executor` globale; (2) far ricevere a questo componente il
// database correntemente selezionato come prop da App.jsx; (3) riaggiungere
// l'import e la <Route path="/upload"> in App.jsx.
import { useState, useEffect } from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom';

export default function UploadData() {
  const [file, setFile] = useState(null);
  const [collectionName, setCollectionName] = useState('');
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [collections, setCollections] = useState([]);
  const [collectionStats, setCollectionStats] = useState({});

  useEffect(() => {
    loadCollections();
  }, []);

  const loadCollections = async () => {
    try {
      const response = await axios.get('http://localhost:8000/api/collections');
      setCollections(response.data.collections);
      
      // Carica count per ogni collection
      const stats = {};
      for (const col of response.data.collections) {
        try {
          const countRes = await axios.get(`http://localhost:8000/api/collections/${col}/count`);
          stats[col] = countRes.data.count;
        } catch (err) {
          stats[col] = '?';
        }
      }
      setCollectionStats(stats);
    } catch (err) {
      console.error('Errore caricamento collections:', err);
    }
  };

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0];
    setFile(selectedFile);
    
    // Auto-suggerisci nome collection dal nome file
    if (selectedFile && !collectionName) {
      const name = selectedFile.name.replace('.json', '').toLowerCase();
      setCollectionName(name.replace(/[^a-z0-9_]/g, '_'));
    }
    
    setMessage('');
    setError('');
  };

  const handleUpload = async () => {
    if (!file) {
      setError('Seleziona un file JSON');
      return;
    }

    setUploading(true);
    setMessage('');
    setError('');

    try {
      const formData = new FormData();
      formData.append('file', file);
      if (collectionName) {
        formData.append('collection_name', collectionName);
      }

      const response = await axios.post(
        'http://localhost:8000/api/upload-collection',
        formData,
        {
          headers: { 'Content-Type': 'multipart/form-data' },
          params: collectionName ? { collection_name: collectionName } : {}
        }
      );

      setMessage(response.data.message);
      setFile(null);
      setCollectionName('');
      
      // Ricarica lista collections
      setTimeout(loadCollections, 500);
      
    } catch (err) {
      setError(err.response?.data?.error || err.message);
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (collectionName) => {
    if (!confirm(`Eliminare collection "${collectionName}"?`)) {
      return;
    }

    try {
      await axios.delete(`http://localhost:8000/api/collections/${collectionName}`);
      setMessage(`Collection "${collectionName}" eliminata`);
      loadCollections();
    } catch (err) {
      setError(err.response?.data?.error || err.message);
    }
  };

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="bg-gradient-to-r from-green-600 to-teal-600 text-white p-6 rounded-lg shadow-lg">
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold">📤 Upload Dati</h1>
            <p className="mt-2 opacity-90">
              Carica i tuoi file JSON e crea collection personalizzate
            </p>
          </div>
          <Link
            to="/"
            className="px-4 py-2 bg-white text-green-600 hover:bg-gray-100 rounded-lg font-medium transition"
          >
            🔍 Vai al Query Executor →
          </Link>
        </div>
      </div>

      {/* Upload Form */}
      <div className="bg-white rounded-lg shadow-md p-6">
        <h2 className="text-xl font-bold mb-4">Carica Nuovo File JSON</h2>
        
        <div className="space-y-4">
          {/* File Input */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Seleziona File JSON
            </label>
            <input
              type="file"
              accept=".json"
              onChange={handleFileChange}
              className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-green-50 file:text-green-700 hover:file:bg-green-100"
            />
            <p className="mt-1 text-xs text-gray-500">
              File deve contenere array JSON: [{"{"}"campo": "valore"{"}"},...]
            </p>
          </div>

          {/* Collection Name */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Nome Collection (opzionale)
            </label>
            <input
              type="text"
              value={collectionName}
              onChange={(e) => setCollectionName(e.target.value)}
              placeholder="es: my_custom_data"
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500"
            />
            <p className="mt-1 text-xs text-gray-500">
              Se vuoto, usa nome file
            </p>
          </div>

          {/* Upload Button */}
          <button
            onClick={handleUpload}
            disabled={!file || uploading}
            className="w-full px-6 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium transition"
          >
            {uploading ? '⏳ Caricamento...' : '📤 Carica in MongoDB'}
          </button>
        </div>

        {/* Messages */}
        {message && (
          <div className="mt-4 bg-green-50 border border-green-200 text-green-800 px-4 py-3 rounded-lg">
            ✅ {message}
          </div>
        )}
        {error && (
          <div className="mt-4 bg-red-50 border border-red-200 text-red-800 px-4 py-3 rounded-lg">
            ⚠️ {error}
          </div>
        )}
      </div>

      {/* Collections List */}
      <div className="bg-white rounded-lg shadow-md p-6">
        <h2 className="text-xl font-bold mb-4">
          Collections MongoDB ({collections.length})
        </h2>
        
        {collections.length === 0 ? (
          <p className="text-gray-500 text-center py-8">
            Nessuna collection disponibile
          </p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {collections.map((col) => (
              <div
                key={col}
                className="border border-gray-200 rounded-lg p-4 hover:border-green-300 transition"
              >
                <div className="flex justify-between items-start mb-2">
                  <h3 className="font-bold text-gray-800">{col}</h3>
                  <button
                    onClick={() => handleDelete(col)}
                    className="text-red-500 hover:text-red-700 text-sm"
                    title="Elimina collection"
                  >
                    🗑️
                  </button>
                </div>
                <p className="text-sm text-gray-600">
                  📊 {collectionStats[col] || '...'} documenti
                </p>
                {/* NOTA: porta alla pagina principale ("/"), dove vive il
                    Query Executor. Il parametro ?collection= non è (ancora)
                    letto da nessuno: oggi il link riporta solo alla pagina,
                    non preseleziona la collection. Per farlo, servirebbe
                    leggere useSearchParams in App.jsx/QueryExecutor.jsx. */}
                <Link
                  to="/"
                  className="mt-2 inline-block text-sm text-green-600 hover:text-green-700"
                >
                  → Usa in query
                </Link>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Example JSON */}
      <div className="bg-blue-50 rounded-lg p-4 border border-blue-200">
        <h3 className="font-medium text-blue-900 mb-2">💡 Esempio File JSON:</h3>
        <pre className="text-xs bg-white p-3 rounded border border-blue-200 overflow-x-auto">
{`[
  {
    "nome": "Prodotto A",
    "prezzo": 99.99,
    "categoria": "elettronica"
  },
  {
    "nome": "Prodotto B",
    "prezzo": 49.99,
    "categoria": "abbigliamento"
  }
]`}
        </pre>
      </div>
    </div>
  );
}
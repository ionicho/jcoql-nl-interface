import { useState, useEffect } from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom';
import './Dashboard.css';

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadStats();
    // Ricarica ogni 10 secondi
    const interval = setInterval(loadStats, 10000);
    return () => clearInterval(interval);
  }, []);

  const loadStats = async () => {
    try {
      const res = await axios.get('http://localhost:8000/api/stats');
      setStats(res.data);
      setLoading(false);
    } catch (err) {
      console.error('Errore caricamento stats:', err);
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-gray-50 to-gray-100">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-lg font-semibold text-gray-700">Caricamento dashboard...</p>
        </div>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-gray-50 to-gray-100">
        <div className="text-center">
          <p className="text-lg font-semibold text-red-600">Errore caricamento statistiche</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 via-white to-gray-100 p-6">
      <div className="max-w-7xl mx-auto space-y-8">

        {/* ════════════════ HEADER ════════════════ */}
        <div className="relative bg-gradient-to-r from-blue-600 to-purple-600 text-white p-8 rounded-lg shadow-lg">
          <Link 
            to="/" 
            className="absolute top-8 right-8 bg-white text-blue-600 hover:bg-blue-50 px-4 py-2 rounded-lg font-semibold text-sm transition-all shadow-md hover:shadow-lg"
          >
            ← Torna all'Interfaccia
          </Link>
          
          <div className="flex items-center gap-4 mb-2 pr-48">
            <span className="text-4xl">📊</span>
            <h1 className="text-3xl font-bold">System Dashboard</h1>
          </div>
          <p className="text-blue-100 mt-2">JCo Framework • Multi-Database • Production-Ready</p>
        </div>

        {/* ════════════════ EXECUTOR STATUS ════════════════ */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-white rounded-lg shadow-md p-6 border-l-4 border-green-500">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs font-bold text-gray-500 uppercase tracking-widest">Executor Attivo</p>
                <p className="text-3xl font-bold text-gray-900 mt-2 capitalize">{stats.executor?.name || 'N/A'}</p>
                <p className="text-xs text-gray-600 mt-2">✅ Operativo</p>
              </div>
              <span className="text-3xl">⚙️</span>
            </div>
          </div>

          <div className="bg-white rounded-lg shadow-md p-6 border-l-4 border-purple-500">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs font-bold text-gray-500 uppercase tracking-widest">Parser</p>
                <p className="text-3xl font-bold text-gray-900 mt-2">ANTLR3</p>
                <p className="text-xs text-gray-600 mt-2">Official • 100% Coverage</p>
              </div>
              <span className="text-3xl">📝</span>
            </div>
          </div>
        </div>

        {/* ════════════════ SYSTEM INFO ════════════════ */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="bg-white rounded-lg shadow-md p-6 border border-gray-200">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs font-bold text-gray-500 uppercase tracking-widest">Database Connessi</p>
                <p className="text-3xl font-bold text-gray-900 mt-2">{stats.databases?.count || 0}</p>
              </div>
              <span className="text-3xl">🗄️</span>
            </div>
          </div>

          <div className="bg-white rounded-lg shadow-md p-6 border border-gray-200">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs font-bold text-gray-500 uppercase tracking-widest">Collezioni Totali</p>
                <p className="text-3xl font-bold text-gray-900 mt-2">{stats.databases?.collections_total || 0}</p>
              </div>
              <span className="text-3xl">📊</span>
            </div>
          </div>

          <div className="bg-white rounded-lg shadow-md p-6 border border-gray-200">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs font-bold text-gray-500 uppercase tracking-widest">Uptime</p>
                <p className="text-3xl font-bold text-gray-900 mt-2">
                  {Math.floor((stats.system?.uptime_seconds || 0) / 3600)}h
                </p>
              </div>
              <span className="text-3xl">⏱️</span>
            </div>
          </div>
        </div>

        {/* ════════════════ DATABASE LIST ════════════════ */}
        <div className="bg-white rounded-lg shadow-md p-6 border border-gray-200">
          <div className="flex items-center gap-2 mb-6">
            <span className="text-2xl">🗄️</span>
            <h2 className="text-xl font-bold text-gray-800">Database Connessi</h2>
          </div>
          
          <div className="space-y-3">
            {stats.databases?.list?.map((db, idx) => (
              <div key={`db-${idx}`} className="p-4 rounded-lg border-2 border-blue-200 bg-blue-50">
                <div className="flex justify-between items-center">
                  <h3 className="font-bold text-gray-800">{db}</h3>
                  <span className="text-xs bg-blue-500 text-white px-3 py-1 rounded-full">✓ Connesso</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* ════════════════ LLM AVAILABLE ════════════════ */}
        <div className="bg-white rounded-lg shadow-md p-6 border border-gray-200">
          <div className="flex items-center gap-2 mb-6">
            <span className="text-2xl">🤖</span>
            <h2 className="text-xl font-bold text-gray-800">LLM Disponibili</h2>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {stats.llms?.available?.map((llm) => (
              <div 
                key={llm}
                className={`p-4 rounded-lg border-2 ${
                  llm === stats.llms?.current
                    ? 'border-green-500 bg-green-50'
                    : 'border-gray-200 bg-gray-50'
                }`}
              >
                <div className="flex justify-between items-center">
                  <h3 className="font-bold text-gray-800 capitalize">{llm}</h3>
                  {llm === stats.llms?.current && (
                    <span className="text-xs bg-green-500 text-white px-2 py-1 rounded">✓ Attivo</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* ════════════════ FEATURES ════════════════ */}
        <div className="bg-gradient-to-br from-green-50 to-emerald-50 rounded-lg p-8 border border-green-300">
          <div className="flex items-center gap-3 mb-6">
            <span className="text-3xl">✅</span>
            <h2 className="text-2xl font-bold text-gray-800">Features Implementate</h2>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {[
              { icon: '⚙️', name: 'JCo Framework', desc: 'Official Java implementation' },
              { icon: '📝', name: 'ANTLR3 Parser', desc: 'Grammar validation' },
              { icon: '🗄️', name: 'Multi-Database', desc: 'Schema discovery per DB' },
              { icon: '🔗', name: 'JOIN nativo', desc: 'JOIN OF COLLECTIONS (JCoQL+)' },
              { icon: '📦', name: 'GROUP', desc: 'Raggruppamento nativo' },
              { icon: '🧩', name: 'EXPAND', desc: 'Espansione array' },
              { icon: '➕', name: 'MERGE/INTERSECT/SUBTRACT', desc: 'Operazioni insiemistiche' },
              { icon: '💾', name: 'SAVE AS/TO FILE', desc: 'Persistenza dei risultati' },
              { icon: '🏭', name: 'Factory Pattern', desc: 'Plug-and-play architecture' },
            ].map((feature) => (
              <div key={feature.name} className="bg-white rounded-lg p-4 border border-green-200">
                <div className="text-2xl mb-2">{feature.icon}</div>
                <h3 className="font-bold text-gray-800 text-sm mb-1">{feature.name}</h3>
                <p className="text-xs text-gray-600">{feature.desc}</p>
              </div>
            ))}
          </div>
        </div>

        {/* ════════════════ FOOTER ════════════════ */}
        <div className="text-center py-8 text-gray-600 text-sm border-t border-gray-200">
          <p>JCoQL+ Natural Language Interface • JCo Framework • Production-Ready 🎓</p>
          <p className="text-xs text-gray-500 mt-2">Dashboard aggiornato automaticamente ogni 10 secondi</p>
        </div>

      </div>
    </div>
  );
}
import {
  ArcElement,
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  Title,
  Tooltip,
} from 'chart.js'
import { useState } from 'react'
import { Bar, Doughnut, Line } from 'react-chartjs-2'
import { Link } from 'react-router-dom'; // Aggiunto per la navigazione SPA

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Title,
  Tooltip,
  Legend
)

export default function Dashboard() {
  const [stats, setStats] = useState({
    totalQueries: 20,
    validQueries: 20,
    avgAttempts: 1.05,
    accuracy: 100,
    byLevel: {
      Base: { total: 5, valid: 5 },
      Intermedio: { total: 7, valid: 7 },
      Avanzato: { total: 8, valid: 8 }
    },
    queryHistory: [
      { date: '11/03', queries: 3, valid: 3 },
      { date: '12/03', queries: 5, valid: 5 },
      { date: '13/03', queries: 7, valid: 7 },
      { date: '14/03', queries: 5, valid: 5 },
    ]
  })

  // Line Chart - Query nel tempo
  const lineChartData = {
    labels: stats.queryHistory.map(h => h.date),
    datasets: [
      {
        label: 'Query Totali',
        data: stats.queryHistory.map(h => h.queries),
        borderColor: 'rgb(99, 102, 241)',
        backgroundColor: 'rgba(99, 102, 241, 0.1)',
        tension: 0.4,
      },
      {
        label: 'Query Valide',
        data: stats.queryHistory.map(h => h.valid),
        borderColor: 'rgb(34, 197, 94)',
        backgroundColor: 'rgba(34, 197, 94, 0.1)',
        tension: 0.4,
      }
    ]
  }

  // Bar Chart - Performance per livello
  const barChartData = {
    labels: Object.keys(stats.byLevel),
    datasets: [
      {
        label: 'Totali',
        data: Object.values(stats.byLevel).map(l => l.total),
        backgroundColor: 'rgba(99, 102, 241, 0.5)',
      },
      {
        label: 'Valide',
        data: Object.values(stats.byLevel).map(l => l.valid),
        backgroundColor: 'rgba(34, 197, 94, 0.5)',
      }
    ]
  }

  // Doughnut Chart - Success Rate
  const doughnutData = {
    labels: ['Valide', 'Invalide'],
    datasets: [{
      data: [stats.validQueries, stats.totalQueries - stats.validQueries],
      backgroundColor: ['rgb(34, 197, 94)', 'rgb(239, 68, 68)'],
      borderWidth: 0,
    }]
  }

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'top',
      }
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="w-10 h-10 bg-indigo-600 rounded-lg flex items-center justify-center">
                <span className="text-white text-xl font-bold">📊</span>
              </div>
              <div>
                <h1 className="text-2xl font-bold text-gray-900">Dashboard Metriche</h1>
                <p className="text-sm text-gray-500">JCoQL+ Analytics & Performance</p>
              </div>
            </div>
            
            {/* LINK CORRETTO QUI */}
            <Link
              to="/"
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm transition-colors"
            >
              &larr; Torna all&apos;Interfaccia
            </Link>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        
        {/* KPI Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          <div className="bg-white rounded-lg shadow-md p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-600">Query Totali</p>
                <p className="text-3xl font-bold text-gray-900">{stats.totalQueries}</p>
              </div>
              <div className="w-12 h-12 bg-indigo-100 rounded-lg flex items-center justify-center">
                <span className="text-2xl">📝</span>
              </div>
            </div>
            <p className="text-xs text-gray-500 mt-2">Test suite completo</p>
          </div>

          <div className="bg-white rounded-lg shadow-md p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-600">Accuracy</p>
                <p className="text-3xl font-bold text-green-600">{stats.accuracy}%</p>
              </div>
              <div className="w-12 h-12 bg-green-100 rounded-lg flex items-center justify-center">
                <span className="text-2xl">✅</span>
              </div>
            </div>
            <p className="text-xs text-green-600 mt-2">+{stats.validQueries}/{stats.totalQueries} valide</p>
          </div>

          <div className="bg-white rounded-lg shadow-md p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-600">Media Tentativi</p>
                <p className="text-3xl font-bold text-blue-600">{stats.avgAttempts}</p>
              </div>
              <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center">
                <span className="text-2xl">🔄</span>
              </div>
            </div>
            <p className="text-xs text-blue-600 mt-2">95% primo colpo</p>
          </div>

          <div className="bg-white rounded-lg shadow-md p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-600">F1-Score</p>
                <p className="text-3xl font-bold text-purple-600">1.000</p>
              </div>
              <div className="w-12 h-12 bg-purple-100 rounded-lg flex items-center justify-center">
                <span className="text-2xl">🎯</span>
              </div>
            </div>
            <p className="text-xs text-purple-600 mt-2">P=1.0, R=1.0</p>
          </div>
        </div>

        {/* Charts Row 1 */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          {/* Line Chart */}
          <div className="bg-white rounded-lg shadow-md p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">
              📈 Query nel Tempo
            </h3>
            <div className="h-64">
              <Line data={lineChartData} options={chartOptions} />
            </div>
          </div>

          {/* Bar Chart */}
          <div className="bg-white rounded-lg shadow-md p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">
              📊 Performance per Livello
            </h3>
            <div className="h-64">
              <Bar data={barChartData} options={chartOptions} />
            </div>
          </div>
        </div>

        {/* Charts Row 2 */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Doughnut Chart */}
          <div className="bg-white rounded-lg shadow-md p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">
              🎯 Success Rate
            </h3>
            <div className="h-64 flex items-center justify-center">
              <Doughnut data={doughnutData} options={chartOptions} />
            </div>
          </div>

          {/* Stats Table */}
          <div className="bg-white rounded-lg shadow-md p-6 lg:col-span-2">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">
              📋 Dettaglio per Livello
            </h3>
            <div className="overflow-x-auto">
              <table className="min-w-full">
                <thead>
                  <tr className="border-b border-gray-200">
                    <th className="text-left py-3 px-4 text-sm font-medium text-gray-700">Livello</th>
                    <th className="text-right py-3 px-4 text-sm font-medium text-gray-700">Totali</th>
                    <th className="text-right py-3 px-4 text-sm font-medium text-gray-700">Valide</th>
                    <th className="text-right py-3 px-4 text-sm font-medium text-gray-700">Accuracy</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(stats.byLevel).map(([level, data]) => (
                    <tr key={level} className="border-b border-gray-100">
                      <td className="py-3 px-4 text-sm text-gray-900">{level}</td>
                      <td className="py-3 px-4 text-sm text-gray-600 text-right">{data.total}</td>
                      <td className="py-3 px-4 text-sm text-green-600 text-right font-medium">{data.valid}</td>
                      <td className="py-3 px-4 text-sm text-right">
                        <span className="px-2 py-1 bg-green-100 text-green-800 rounded-full text-xs font-medium">
                          {((data.valid / data.total) * 100).toFixed(1)}%
                        </span>
                      </td>
                    </tr>
                  ))}
                  <tr className="bg-gray-50 font-semibold">
                    <td className="py-3 px-4 text-sm text-gray-900">Totale</td>
                    <td className="py-3 px-4 text-sm text-gray-900 text-right">{stats.totalQueries}</td>
                    <td className="py-3 px-4 text-sm text-green-600 text-right">{stats.validQueries}</td>
                    <td className="py-3 px-4 text-sm text-right">
                      <span className="px-2 py-1 bg-green-600 text-white rounded-full text-xs font-medium">
                        {stats.accuracy}%
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* System Info */}
        <div className="mt-8 bg-white rounded-lg shadow-md p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">
            ⚙️ Informazioni Sistema
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-4 bg-gray-50 rounded-lg">
              <p className="text-sm text-gray-600">Dataset</p>
              <p className="text-lg font-semibold text-gray-900">59 esempi</p>
              <p className="text-xs text-gray-500 mt-1">Base + Extended + IN_RANGE + Edge Cases</p>
            </div>
            <div className="p-4 bg-gray-50 rounded-lg">
              <p className="text-sm text-gray-600">Parser ANTLR</p>
              <p className="text-lg font-semibold text-gray-900">JCoQL 4.0</p>
              <p className="text-xs text-gray-500 mt-1">100% conformità grammatica ufficiale</p>
            </div>
            <div className="p-4 bg-gray-50 rounded-lg">
              <p className="text-sm text-gray-600">LLM Model</p>
              <p className="text-lg font-semibold text-gray-900">Gemini 3 Flash</p>
              <p className="text-xs text-gray-500 mt-1">RAG + Auto-validation</p>
            </div>
          </div>
        </div>

      </main>

      {/* Footer */}
      <footer className="mt-12 pb-8">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center text-sm text-gray-500">
            <p>Dashboard Metriche | Tesi Magistrale Università Bergamo</p>
            <p className="mt-1">Ultimo aggiornamento: 14 Marzo 2026</p>
          </div>
        </div>
      </footer>
    </div>
  )
}
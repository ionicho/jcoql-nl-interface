/**
 * DatabaseSelector Component
 * 
 * Consolida:
 * 1. DatabaseManager (singolo database)
 * 2. MultiDatabaseSelector (multipli + JOIN)
 * 
 * In UN unico componente sidebar-friendly.
 *
 * NOTA (13/08): la modalità "Singolo" (che duplicava DatabaseManager) è
 * stata rimossa — selezionare un solo database nella modalità "Multipli"
 * (che è rimasta l'unica) fa esattamente la stessa cosa, non c'era motivo
 * di tenere due modalità per lo stesso risultato.
 *
 * NOTA (27/09): rimosso anche il form di "JOIN nativo tra database"
 * (checkbox "Usa JOIN tra database" + configurazione chiavi/alias),
 * ritenuto non necessario — un JOIN resta comunque possibile scrivendo
 * a mano (o generando via NL) un comando JOIN OF COLLECTIONS nel pannello
 * query di QueryExecutor, indipendentemente da questo componente.
 * onDatabasesChange ora passa solo l'elenco dei database selezionati,
 * non più un secondo parametro di configurazione join.
 */

import React, { useState, useEffect } from 'react';
import './DatabaseSelector.css';

export default function DatabaseSelector({ onDatabasesChange, selectedDatabases }) {
  // ================== STATE ==================

  const [availableDatabases, setAvailableDatabases] = useState([]);
  // FIX (17/08, correzione della correzione di ieri): il precedente
  // useEffect che sincronizzava multiSelected dal prop selectedDatabases
  // non funzionava per un problema di timing — in React, gli effect dei
  // componenti FIGLI partono prima di quelli del genitore. Quando questo
  // effect girava, App.jsx non aveva ancora letto il localStorage e il
  // prop selectedDatabases valeva ancora il default ['jcoql_test'], non
  // il valore vero appena ripristinato. Invece di rincorrere il timing
  // degli effect, si legge il localStorage direttamente qui, in modo
  // sincrono, nell'inizializzatore di useState — che gira una sola volta,
  // durante il primissimo render, indipendentemente da quando/se il
  // genitore fa la propria lettura. Stessa chiave usata in App.jsx.
  const [multiSelected, setMultiSelected] = useState(() => {
    try {
      const saved = localStorage.getItem('jcoql_selected_databases');
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed) && parsed.length > 0) {
          return new Set(parsed);
        }
      }
    } catch (err) {
      console.warn('Errore lettura database selezionati da localStorage:', err);
    }
    return new Set(['jcoql_test']);
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [removingDb, setRemovingDb] = useState(null); //per rimozione di un database

  const [showAddForm, setShowAddForm] = useState(false);
  const [newDbForm, setNewDbForm] = useState({
    dbName: '',
    mongoUri: 'mongodb://localhost:27017',
    databaseName: ''
  });

  /**
   * Al mount, carica i database disponibili
   */
  useEffect(() => {
    loadAvailableDatabases();
  }, []);

  /**
   * Aggiunge un nuovo database

   * Nota: i tre parametri (dbName, mongoUri, databaseName) sono
   * concatenati direttamente nella query string senza
   * encodeURIComponent — un valore con caratteri speciali (es. uno
   * spazio, una '@' in mongoUri se contiene credenziali, una '&') altera
   * la query string risultante invece di essere passato come valore
   * letterale del parametro.
   */
  const handleAddDatabase = async () => {
    if (!newDbForm.dbName || !newDbForm.databaseName) {
      alert('Compila tutti i campi!');
      return;
    }

    try {
      setLoading(true);
      const response = await fetch(
        `http://127.0.0.1:8000/api/databases/connect?db_name=${newDbForm.dbName}&mongo_uri=${newDbForm.mongoUri}&database_name=${newDbForm.databaseName}`,
        { method: 'POST' }
      );

      if (response.ok) {
        alert('✅ Database aggiunto!');
        setNewDbForm({ dbName: '', mongoUri: 'mongodb://localhost:27017', databaseName: '' });
        setShowAddForm(false);
        loadAvailableDatabases(); // Ricarica lista
      } else {
        alert('❌ Errore aggiunta database');
      }
    } catch (err) {
      alert(`Errore: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  /**
   * Rimuove un database dalla registry
   * Non elimina i dati, solo disconnette
   */
  const handleRemoveDatabase = async (dbName) => {
    if (!window.confirm(`Scollega '${dbName}'? I dati rimangono intatti.`)) {
      return;
    }

    try {
      setRemovingDb(dbName);
      const response = await fetch(
        `http://127.0.0.1:8000/api/databases/disconnect?db_name=${dbName}`,
        { method: 'POST' }
      );

      if (response.ok) {
        // Ricarica la lista database
        loadAvailableDatabases();
        
        // Se era selezionato, resetta selection
        if (multiSelected.has(dbName)) {
          const newSet = new Set(multiSelected);
          newSet.delete(dbName);
          setMultiSelected(newSet);
          onDatabasesChange(Array.from(newSet));
        }
        
        alert(`✅ Database '${dbName}' scollegato`);
      } else {
        alert('❌ Errore durante scollegamento');
      }
    } catch (err) {
      alert(`Errore: ${err.message}`);
    } finally {
      setRemovingDb(null);
    }
  };

  /**
   * Carica la lista di database dal server

   * Nota: questo componente usa fetch() con host "127.0.0.1", mentre
   * App.jsx/QueryExecutor.jsx/Dashboard.jsx usano axios con host
   * "localhost" — stesso backend, due modi diversi di raggiungerlo,
   * senza una costante URL condivisa tra i componenti.

   * Nota: ogni chiamata a questa funzione (al mount, dopo add/remove
   * database, o dal pulsante "Ricarica Database") reimposta
   * multiSelected al solo primo database della lista
   * (dbNames[0]) — una selezione multipla già fatta dall'utente non
   * viene preservata attraverso un reload della lista.
   */
  const loadAvailableDatabases = async () => {
    try {
      setLoading(true);
      setError('');

      const response = await fetch('http://127.0.0.1:8000/api/databases');
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      const dbNames = data.databases.map(db => db.name);
      
      setAvailableDatabases(dbNames);

      // FIX (17/08): prima resettava SEMPRE multiSelected al solo primo
      // database della lista — anche al primo montaggio, sovrascrivendo
      // la selezione appena ripristinata dal localStorage (vedi
      // l'inizializzatore di multiSelected sopra). Ora preserva la
      // selezione corrente se è ancora valida (i database selezionati
      // esistono ancora in quelli appena scaricati) — resetta al primo
      // database SOLO se la selezione corrente è vuota o non contiene più
      // nessun database realmente esistente (es. dopo che uno è stato
      // rimosso). Così "aggiungi/rimuovi database" e "Ricarica Database"
      // continuano a comportarsi come prima quando serve, ma il mount
      // iniziale non cancella più il ripristino.
      setMultiSelected((prevSelected) => {
        const stillValid = new Set([...prevSelected].filter((db) => dbNames.includes(db)));
        if (stillValid.size > 0) {
          return stillValid;
        }
        return dbNames.length > 0 ? new Set([dbNames[0]]) : new Set();
      });
    } catch (err) {
      setError(`Errore caricamento database: ${err.message}`);
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  /**
   * Toggle checkbox database (multi-mode)
   */
  const handleMultiToggle = (dbName) => {
    const newSet = new Set(multiSelected);
    
    if (newSet.has(dbName)) {
      newSet.delete(dbName);
    } else {
      newSet.add(dbName);
    }

    setMultiSelected(newSet);

    // Notifica parent
    onDatabasesChange(Array.from(newSet));
  };

  // ================== RENDER ==================

  if (loading) {
    return (
      <div className="database-selector">
        <div className="loading">⏳ Caricamento database...</div>
      </div>
    );
  }

  return (
    <div className="database-selector">
      <h2>🗄️ Database</h2>

      {error && <div className="error-box">{error}</div>}

      <div className="mode-content">
          {/* Database checkboxes CON BOTTONE RIMUOVI */}
          <label className="section-label">Database da selezionare:</label>
          <div className="checkboxes">
            {availableDatabases.length === 0 ? (
              <p className="no-databases">Nessun database disponibile</p>
            ) : (
              availableDatabases.map(db => (
                <div key={db} className="checkbox-with-remove">
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={multiSelected.has(db)}
                      onChange={() => handleMultiToggle(db)}
                    />
                    <span>{db}</span>
                  </label>
                  <button
                    onClick={() => handleRemoveDatabase(db)}
                    disabled={removingDb === db}
                    className="remove-db-btn"
                    title="Scollega questo database"
                  >
                    {removingDb === db ? '⏳' : '✖️'}
                  </button>
                </div>
              ))
            )}
          </div>
      </div>

      {/* ──────────── ADD DATABASE FORM ──────────── */}
      <button 
        onClick={() => setShowAddForm(!showAddForm)} 
        className="add-db-toggle"
      >
        {showAddForm ? '✖️ Chiudi' : '➕ Aggiungi Database'}
      </button>

      {showAddForm && (
        <div className="add-db-form">
          <h4>Connetti Nuovo Database</h4>
          
          <div className="form-group">
            <label>Nome Database (interno):</label>
            <input
              type="text"
              placeholder="es: production_db"
              value={newDbForm.dbName}
              onChange={(e) => setNewDbForm({...newDbForm, dbName: e.target.value})}
            />
          </div>

          <div className="form-group">
            <label>MongoDB URI:</label>
            <input
              type="text"
              value={newDbForm.mongoUri}
              onChange={(e) => setNewDbForm({...newDbForm, mongoUri: e.target.value})}
            />
          </div>

          <div className="form-group">
            <label>Nome Database MongoDB:</label>
            <input
              type="text"
              placeholder="es: my_database"
              value={newDbForm.databaseName}
              onChange={(e) => setNewDbForm({...newDbForm, databaseName: e.target.value})}
            />
          </div>

          <button onClick={handleAddDatabase} className="connect-btn">
            ✅ Connetti
          </button>
        </div>
      )}

      {/* ──────────── SUMMARY ──────────── */}
      <div className="summary">
        <div className="summary-title">📍 Selezionati ({selectedDatabases ? selectedDatabases.length : 0}):</div>
        <div className="summary-badges">
          {selectedDatabases && selectedDatabases.map(db => (
            <span key={db} className="badge">{db}</span>
          ))}
        </div>
      </div>

      {/* ──────────── REFRESH BUTTON ──────────── */}
      <button onClick={loadAvailableDatabases} className="refresh-btn">
        🔄 Ricarica Database
      </button>
    </div>
  );
}
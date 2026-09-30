/**
 * DatabaseSelector Component — selezione dei database da usare
 * nell'interfaccia, in un unico pannello sidebar-friendly.
 *
 * Esiste una sola modalità di selezione (multipla): selezionare un solo
 * database ha lo stesso effetto di una modalità "singola" dedicata,
 * quindi non ce n'è una separata.
 *
 * Non contiene un form di JOIN nativo tra database: un JOIN resta
 * comunque possibile scrivendo a mano (o generando via NL) un comando
 * JOIN OF COLLECTIONS nel pannello query di QueryExecutor,
 * indipendentemente da questo componente. onDatabasesChange passa solo
 * l'elenco dei database selezionati.
 */

import React, { useState, useEffect } from 'react';
import { showToast } from './Toast';
import './DatabaseSelector.css';

export default function DatabaseSelector({ onDatabasesChange, selectedDatabases }) {
  // ================== STATE ==================

  const [availableDatabases, setAvailableDatabases] = useState([]);
  // Letto direttamente da localStorage qui, non con un useEffect: in
  // React gli effect dei componenti figli partono prima di quelli del
  // genitore, quindi un effect qui girerebbe prima che App.jsx abbia
  // letto il proprio localStorage, leggendo ancora il default
  // ['jcoql_test'] invece del valore reale. L'inizializzatore di
  // useState gira invece una sola volta, al primissimo render,
  // indipendentemente dal genitore. Stessa chiave usata in App.jsx.
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
      showToast('Compila tutti i campi!', 'error');
      return;
    }

    try {
      setLoading(true);
      const response = await fetch(
        `http://127.0.0.1:8000/api/databases/connect?db_name=${newDbForm.dbName}&mongo_uri=${newDbForm.mongoUri}&database_name=${newDbForm.databaseName}`,
        { method: 'POST' }
      );

      if (response.ok) {
        showToast('Database aggiunto!', 'success');
        setNewDbForm({ dbName: '', mongoUri: 'mongodb://localhost:27017', databaseName: '' });
        setShowAddForm(false);
        loadAvailableDatabases(); // Ricarica lista
      } else {
        showToast('Errore aggiunta database', 'error');
      }
    } catch (err) {
      showToast(`Errore: ${err.message}`, 'error');
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
        
        showToast(`Database '${dbName}' scollegato`, 'success');
      } else {
        showToast('Errore durante scollegamento', 'error');
      }
    } catch (err) {
      showToast(`Errore: ${err.message}`, 'error');
    } finally {
      setRemovingDb(null);
    }
  };

  /**
   * Carica la lista di database dal server.
   *
   * Nota: questo componente usa fetch() con host "127.0.0.1", mentre
   * App.jsx/QueryExecutor.jsx/Dashboard.jsx usano axios con host
   * "localhost" — stesso backend, due modi diversi di raggiungerlo,
   * senza una costante URL condivisa tra i componenti.
   *
   * Nota: ad ogni chiamata (mount, add/remove database, "Ricarica
   * Database") la selezione corrente viene preservata se è ancora
   * valida — cioè se i database selezionati esistono ancora in quelli
   * appena scaricati. Si resetta al primo database della lista solo se
   * la selezione risulta vuota o non contiene più nessun database
   * realmente esistente.
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

      // Preserva la selezione corrente se è ancora valida (vedi il
      // commento sopra la funzione); altrimenti prende il primo database
      // disponibile.
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
      <h2>Database</h2>

      {error && <div className="error-box">{error}</div>}

      <div className="mode-content">
          {/* Database checkboxes CON BOTTONE RIMUOVI */}
          <label className="section-label">Database selezionabili:</label>
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
          
          <div className="form-group">
            <label>Nome Database (interno):</label>
            <input
              type="text"
              placeholder="es: production_db"
              value={newDbForm.dbName}
              onChange={(e) => setNewDbForm({...newDbForm, dbName: e.target.value})}
            />
          </div>
          
          <button onClick={handleAddDatabase} className="connect-btn">
            ✅ Connetti
          </button>
        </div>
      )}

      {/* ──────────── SUMMARY ──────────── */}
      <div className="summary">
        <div className="summary-title">Database Selezionati ({selectedDatabases ? selectedDatabases.length : 0}):</div>
        <div className="summary-badges">
          {selectedDatabases && selectedDatabases.map(db => (
            <span key={db} className="badge">{db}</span>
          ))}
        </div>
      </div>

      {/* ──────────── REFRESH BUTTON ──────────── */}
      <button onClick={loadAvailableDatabases} className="refresh-btn">
        <span style={{ color: '#7c3aed', fontSize: '18px', lineHeight: 1, verticalAlign: 'middle' }}>↻</span> Ricarica Database
      </button>
    </div>
  );
}
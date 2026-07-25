/**
 * DatabaseSelector Component
 * 
 * Consolida:
 * 1. DatabaseManager (singolo database)
 * 2. MultiDatabaseSelector (multipli + JOIN)
 * 
 * In UN unico componente sidebar-friendly
 */

import React, { useState, useEffect } from 'react';
import './DatabaseSelector.css';

export default function DatabaseSelector({ onDatabasesChange, selectedDatabases }) {
  // ================== STATE ==================

  const [availableDatabases, setAvailableDatabases] = useState([]);
  const [currentDatabase, setCurrentDatabase] = useState('jcoql_test');
  const [multiSelected, setMultiSelected] = useState(new Set(['jcoql_test']));
  const [mode, setMode] = useState('single'); // 'single' o 'multi'
  const [joinMode, setJoinMode] = useState(false);
  const [joinConfig, setJoinConfig] = useState({
    db1: 'jcoql_test',
    db2: '',
    joinType: 'INNER',
    joinKey: '',
    db2JoinKey: ''
  });
  const [showJoinForm, setShowJoinForm] = useState(false);
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
          onDatabasesChange(Array.from(newSet), null);
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

      // Se c'è almeno un database, impostalo come default
      if (dbNames.length > 0) {
        setCurrentDatabase(dbNames[0]);
        setMultiSelected(new Set([dbNames[0]]));
      }
    } catch (err) {
      setError(`Errore caricamento database: ${err.message}`);
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  /**
   * Cambia database singolo
   */
  const handleSingleDatabaseChange = (dbName) => {
    console.log('🔄 handleSingleDatabaseChange CHIAMATO con:', dbName);
    
    setCurrentDatabase(dbName);
    setMultiSelected(new Set([dbName]));
    
    console.log('📤 Chiamo onDatabasesChange con:', [dbName]);
    console.log('📤 Tipo di onDatabasesChange:', typeof onDatabasesChange);
    
    onDatabasesChange([dbName], null);
    
    console.log('✅ onDatabasesChange chiamato');
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

    // Se disabilita un DB usato nel join, resetta
    if (joinMode && (!newSet.has(joinConfig.db1) || !newSet.has(joinConfig.db2))) {
      setJoinMode(false);
      setShowJoinForm(false);
    }

    // Notifica parent
    onDatabasesChange(Array.from(newSet), joinMode ? joinConfig : null);
  };

  /**
   * Toggle join mode
   */
  const handleJoinToggle = (enabled) => {
    setJoinMode(enabled);
    setShowJoinForm(enabled);

    if (!enabled) {
      setJoinConfig({
        db1: 'jcoql_test',
        db2: '',
        joinType: 'INNER',
        joinKey: '',
        db2JoinKey: ''
      });
    }

    onDatabasesChange(Array.from(multiSelected), enabled ? joinConfig : null);
  };

  /**
   * Aggiorna join config
   */
  const handleJoinConfigChange = (field, value) => {
    const newConfig = { ...joinConfig, [field]: value };
    setJoinConfig(newConfig);
    onDatabasesChange(Array.from(multiSelected), newConfig);
  };

  /**
   * Valida join config
   */
  const isJoinValid = () => {
    return (
      joinConfig.db1 &&
      joinConfig.db2 &&
      joinConfig.db1 !== joinConfig.db2 &&
      joinConfig.joinKey &&
      joinConfig.db2JoinKey
    );
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

      {/* ──────────── MODE SELECTOR ──────────── */}
      <div className="mode-tabs">
        <button
          className={`tab ${mode === 'single' ? 'active' : ''}`}
          onClick={() => setMode('single')}
        >
          📦 Singolo
        </button>
        <button
          className={`tab ${mode === 'multi' ? 'active' : ''}`}
          onClick={() => setMode('multi')}
        >
          🗄️ Multipli
        </button>
      </div>

      {/* ──────────── SINGLE MODE ──────────── */}
      {mode === 'single' && (
        <div className="mode-content">
          <label>Database Attuale:</label>
          <select
            value={currentDatabase}
            onChange={(e) => handleSingleDatabaseChange(e.target.value)}
            className="select-db"
          >
            {availableDatabases.map(db => (
              <option key={db} value={db}>{db}</option>
            ))}
          </select>
        </div>
      )}

      {/* ──────────── MULTI MODE ──────────── */}
      {mode === 'multi' && (
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

          {/* Join options (solo se 2+ database) */}
          {multiSelected.size >= 2 && (
            <div className="join-section">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={joinMode}
                  onChange={(e) => handleJoinToggle(e.target.checked)}
                />
                <span>Usa JOIN tra database</span>
              </label>

              {/* Join form */}
              {joinMode && (
                <div className="join-form">
                  <div className="form-group">
                    <label>Tipo JOIN:</label>
                    <select
                      value={joinConfig.joinType}
                      onChange={(e) => handleJoinConfigChange('joinType', e.target.value)}
                    >
                      <option value="INNER">INNER JOIN</option>
                      <option value="LEFT">LEFT JOIN</option>
                      <option value="RIGHT">RIGHT JOIN</option>
                      <option value="FULL">FULL OUTER JOIN</option>
                    </select>
                  </div>

                  <div className="form-group">
                    <label>Database 1:</label>
                    <select
                      value={joinConfig.db1}
                      onChange={(e) => handleJoinConfigChange('db1', e.target.value)}
                    >
                      {Array.from(multiSelected).map(db => (
                        <option key={db} value={db}>{db}</option>
                      ))}
                    </select>
                  </div>

                  <div className="form-group">
                    <label>Join Key in {joinConfig.db1}:</label>
                    <input
                      type="text"
                      placeholder="es: .user_id"
                      value={joinConfig.joinKey}
                      onChange={(e) => handleJoinConfigChange('joinKey', e.target.value)}
                    />
                  </div>

                  <div className="form-group">
                    <label>Database 2:</label>
                    <select
                      value={joinConfig.db2}
                      onChange={(e) => handleJoinConfigChange('db2', e.target.value)}
                    >
                      <option value="">-- Seleziona --</option>
                      {Array.from(multiSelected)
                        .filter(db => db !== joinConfig.db1)
                        .map(db => (
                          <option key={db} value={db}>{db}</option>
                        ))}
                    </select>
                  </div>

                  {joinConfig.db2 && (
                    <div className="form-group">
                      <label>Join Key in {joinConfig.db2}:</label>
                      <input
                        type="text"
                        placeholder="es: .id"
                        value={joinConfig.db2JoinKey}
                        onChange={(e) => handleJoinConfigChange('db2JoinKey', e.target.value)}
                      />
                    </div>
                  )}

                  <div className={`join-status ${isJoinValid() ? 'valid' : 'invalid'}`}>
                    {isJoinValid() ? '✅ Valido' : '⚠️ Completa campi'}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

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
        {joinConfig && (
          <div className="join-summary">
            <strong>JOIN:</strong> {joinConfig.db1} → {joinConfig.db2}
          </div>
        )}
      </div>

      {/* ──────────── REFRESH BUTTON ──────────── */}
      <button onClick={loadAvailableDatabases} className="refresh-btn">
        🔄 Ricarica Database
      </button>
    </div>
  );
}
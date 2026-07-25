/**
 * MultiDatabaseSelector Component
 * 
 * Permette all'utente di:
 * 1. Selezionare più database contemporaneamente
 * 2. Scegliere se fare JOIN o query separate
 * 3. Specificare join key se necessario
 */

import React, { useState, useEffect } from 'react';
import './MultiDatabaseSelector.css';

export default function MultiDatabaseSelector({ onSelectDatabases, onJoinChange }) {
  // State per database disponibili
  const [availableDatabases, setAvailableDatabases] = useState([]);
  
  // State per database selezionati (checkbox)
  const [selectedDatabases, setSelectedDatabases] = useState(new Set(['jcoql_test']));
  
  // State per modalità join
  const [joinMode, setJoinMode] = useState(false);
  
  // State per join configuration
  const [joinConfig, setJoinConfig] = useState({
    db1: 'jcoql_test',
    db2: '',
    joinType: 'INNER', // INNER, LEFT, RIGHT, FULL
    joinKey: '', // es: ".user_id"
    db2JoinKey: '' // es: ".id"
  });
  
  // State per mostrare form join
  const [showJoinForm, setShowJoinForm] = useState(false);

  /**
   * Al mount, carica lista database disponibili
   */
  useEffect(() => {
    loadDatabases();
  }, []);

  /**
   * Carica la lista di tutti i database connessi dal server
   */
  const loadDatabases = async () => {
    try {
      // Chiama API per ottenere lista database
      const response = await fetch('http://127.0.0.1:8000/api/databases');
      const data = await response.json();
      
      // Estrae nomi database
      const dbNames = data.databases.map(db => db.name);
      setAvailableDatabases(dbNames);
      
      // Se c'è solo un DB, selezionalo di default
      if (dbNames.length === 1) {
        setSelectedDatabases(new Set([dbNames[0]]));
      }
    } catch (err) {
      console.error('Errore caricamento database:', err);
    }
  };

  /**
   * Gestisce il cambio di un checkbox database
   * 
   * Args:
   *   dbName: nome database toggleato
   */
  const handleDatabaseToggle = (dbName) => {
    // Crea una copia del set
    const newSelected = new Set(selectedDatabases);
    
    if (newSelected.has(dbName)) {
      // Se già selezionato, deseleziona
      newSelected.delete(dbName);
    } else {
      // Se non selezionato, aggiungi
      newSelected.add(dbName);
    }
    
    // Aggiorna state
    setSelectedDatabases(newSelected);
    
    // Se deseleziona un DB usato nel join, resetta join
    if (
      joinMode && 
      (!newSelected.has(joinConfig.db1) || !newSelected.has(joinConfig.db2))
    ) {
      setJoinMode(false);
      setShowJoinForm(false);
    }
    
    // Notifica parent component
    onSelectDatabases(Array.from(newSelected), joinMode ? joinConfig : null);
  };

  /**
   * Abilita/disabilita la modalità JOIN
   */
  const handleJoinToggle = (enabled) => {
    setJoinMode(enabled);
    setShowJoinForm(enabled);
    
    // Resetta join config quando disabiliti
    if (!enabled) {
      setJoinConfig({
        db1: 'jcoql_test',
        db2: '',
        joinType: 'INNER',
        joinKey: '',
        db2JoinKey: ''
      });
    }
    
    // Notifica parent
    onJoinChange(enabled ? joinConfig : null);
  };

  /**
   * Aggiorna la configurazione del JOIN
   */
  const handleJoinConfigChange = (field, value) => {
    const newConfig = { ...joinConfig, [field]: value };
    setJoinConfig(newConfig);
    
    // Notifica parent con nuovo config
    onJoinChange(newConfig);
  };

  /**
   * Valida la configurazione del JOIN
   */
  const isJoinConfigValid = () => {
    return (
      joinConfig.db1 && 
      joinConfig.db2 && 
      joinConfig.db1 !== joinConfig.db2 && 
      joinConfig.joinKey && 
      joinConfig.db2JoinKey
    );
  };

  return (
    <div className="multi-database-selector">
      <div className="selector-header">
        <h3>🗄️ Seleziona Database</h3>
      </div>

      {/* SEZIONE 1: Database Selector (Checkbox Multiple) */}
      <div className="database-checkboxes">
        <label className="section-label">Database da utilizzare:</label>
        
        <div className="checkbox-list">
          {availableDatabases.length === 0 ? (
            <p className="no-databases">Nessun database disponibile</p>
          ) : (
            availableDatabases.map(dbName => (
              <div key={dbName} className="checkbox-item">
                <input
                  type="checkbox"
                  id={`db-${dbName}`}
                  checked={selectedDatabases.has(dbName)}
                  onChange={() => handleDatabaseToggle(dbName)}
                />
                <label htmlFor={`db-${dbName}`}>
                  {dbName}
                  <span className="db-indicator">📦</span>
                </label>
              </div>
            ))
          )}
        </div>
      </div>

      {/* SEZIONE 2: Join Options (Solo se 2+ database selezionati) */}
      {selectedDatabases.size >= 2 && (
        <div className="join-section">
          <label className="section-label">Modalità esecuzione:</label>
          
          <div className="join-options">
            {/* Opzione 1: Query Separate */}
            <div className="join-option">
              <input
                type="radio"
                name="join-mode"
                id="separate-mode"
                checked={!joinMode}
                onChange={() => handleJoinToggle(false)}
              />
              <label htmlFor="separate-mode">
                <strong>Query Separate</strong>
                <span className="description">
                  Esegui query su ogni database separatamente e mostra risultati divisi
                </span>
              </label>
            </div>

            {/* Opzione 2: JOIN Databases */}
            <div className="join-option">
              <input
                type="radio"
                name="join-mode"
                id="join-mode"
                checked={joinMode}
                onChange={() => handleJoinToggle(true)}
              />
              <label htmlFor="join-mode">
                <strong>JOIN Databases</strong>
                <span className="description">
                  Esegui JOIN tra database usando una chiave comune
                </span>
              </label>
            </div>
          </div>

          {/* FORM JOIN (mostra solo se JOIN mode abilitato) */}
          {showJoinForm && (
            <div className="join-form">
              <h4>⚙️ Configurazione JOIN</h4>
              
              {/* Tipo JOIN */}
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

              {/* Database 1 Selection */}
              <div className="form-group">
                <label>Database 1:</label>
                <select
                  value={joinConfig.db1}
                  onChange={(e) => handleJoinConfigChange('db1', e.target.value)}
                >
                  {Array.from(selectedDatabases).map(db => (
                    <option key={db} value={db}>{db}</option>
                  ))}
                </select>
              </div>

              {/* Join Key per DB1 */}
              <div className="form-group">
                <label>Join Key in {joinConfig.db1}:</label>
                <input
                  type="text"
                  placeholder="es: .user_id"
                  value={joinConfig.joinKey}
                  onChange={(e) => handleJoinConfigChange('joinKey', e.target.value)}
                />
                <small>Nome del campo da usare come chiave di join</small>
              </div>

              {/* Database 2 Selection */}
              <div className="form-group">
                <label>Database 2:</label>
                <select
                  value={joinConfig.db2}
                  onChange={(e) => handleJoinConfigChange('db2', e.target.value)}
                >
                  <option value="">-- Seleziona --</option>
                  {Array.from(selectedDatabases)
                    .filter(db => db !== joinConfig.db1)
                    .map(db => (
                      <option key={db} value={db}>{db}</option>
                    ))}
                </select>
              </div>

              {/* Join Key per DB2 */}
              {joinConfig.db2 && (
                <div className="form-group">
                  <label>Join Key in {joinConfig.db2}:</label>
                  <input
                    type="text"
                    placeholder="es: .id"
                    value={joinConfig.db2JoinKey}
                    onChange={(e) => handleJoinConfigChange('db2JoinKey', e.target.value)}
                  />
                  <small>Campo di join nel database di destinazione</small>
                </div>
              )}

              {/* Status indicatore */}
              <div className={`join-status ${isJoinConfigValid() ? 'valid' : 'invalid'}`}>
                {isJoinConfigValid() ? (
                  <span>✅ Configurazione valida</span>
                ) : (
                  <span>⚠️ Compilare tutti i campi</span>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Summary dei database selezionati */}
      <div className="selection-summary">
        <strong>Database selezionati ({selectedDatabases.size}):</strong>
        <div className="summary-list">
          {Array.from(selectedDatabases).map(db => (
            <span key={db} className="summary-item">
              {db}
            </span>
          ))}
        </div>
        {joinMode && (
          <div className="join-summary">
            <strong>Modalità:</strong> JOIN
            <br />
            <strong>Tipo:</strong> {joinConfig.joinType}
            <br />
            <strong>Join:</strong> {joinConfig.db1}.{joinConfig.joinKey} = {joinConfig.db2}.{joinConfig.db2JoinKey}
          </div>
        )}
      </div>
    </div>
  );
}
// ==========================================
// HelpGuide — pannello "Guida" con le domande più comuni su come si
// comporta l'interfaccia (non sulla sintassi di JCoQL+, per quella
// serve la documentazione del linguaggio). Contenuto statico, scritto
// a mano qui sotto: niente chiamate al backend, niente file esterni da
// mantenere — coerente con la scala del progetto.
// ==========================================
import React, { useState } from 'react'
import './HelpGuide.css'

const HELP_SECTIONS = [
  {
    title: 'Selezione database nel menù — a cosa serve davvero',
    body: (
      <>
        <p>
          Quando selezioni più database dal menù a sinistra, la selezione ha un effetto
          diverso a seconda di cosa stai facendo:
        </p>
        <ul>
          <li>
            <strong>Generi una query in linguaggio naturale:</strong> tutti i database
            selezionati vengono presi in considerazione.
          </li>
          <li>
            <strong>Esegui una query già scritta</strong> (a mano o generata): se la query
            specifica già da sé il database con <code>USE DB</code>, viene usato quello —
            il menù non la sovrascrive. Il menù conta solo come database di partenza per
            le query che non ne specificano uno proprio.
          </li>
        </ul>
      </>
    ),
  },
  {
    title: 'Cosa fa il pulsante "⭐ Salva"?',
    body: (
      <>
        <p>
          Salva tra i "Preferiti" (colonna a destra) il testo attualmente presente in
          entrambi i box — quello in linguaggio naturale e quello JCoQL+ — così come sono
          in quel momento, non una "fotografia" di quando la query è stata generata. Da lì
          puoi ricaricarla con un click in futuro, senza doverla riscrivere o rigenerare da
          capo.
        </p>
        <p>
          Attenzione: Il meccanismo non sa se i due box sono ancora "in sincrono" tra loro — registra
          semplicemente quello che c'è scritto in quel momento in entrambi. Quindi se generi
          una query e poi modifichi a mano solo il box JCoQL+ (senza toccare il box del
          linguaggio naturale), la richiesta in linguaggio naturale salvata potrebbe non
          corrispondere più esattamente alla query JCoQL+ salvata insieme ad essa. Vale anche il
          contrario: se modifichi solo il testo in linguaggio naturale senza premere di nuovo
          "✦ Genera", viene salvata la query JCoQL+ vecchia (quella dell'ultima generazione o
          modifica) insieme al nuovo testo in linguaggio naturale.
        </p>
        <p>
          Il salvataggio resta solo nel tuo browser (non viene inviato al server): se cambi
          browser o computer, i preferiti non ti seguono.
        </p>
      </>
    ),
  },
  {
    title: 'Cosa fa "Solo conteggio"?',
    body: (
      <p>
        Quando è attiva, l'interfaccia non recupera i documenti del risultato per
        mostrarteli — restituisce solo il loro numero. Utile su collezioni grandi o query
        pesanti (es. JOIN/GROUP su molti dati), dove costruire e mostrare l'intero
        risultato richiederebbe tempo inutile se ti interessa solo "quanti sono". Con
        questa opzione attiva, il comportamento dell'interfaccia rispecchia anche più da
        vicino quello nativo del motore JCoQL+, che di norma calcola e riporta solo un
        conteggio per la maggior parte dei comandi — normalmente è l'interfaccia stessa a
        fare un passo in più dietro le quinte per recuperare anche i documenti veri, passo
        che qui viene saltato.
      </p>
    ),
  },
  {
    title: 'Cercare o unire dati su più database insieme',
    body: (
      <p>
        Se selezioni due o più database che hanno tutti la stessa collezione (es.{' '}
        <code>users</code>), e chiedi quella collezione, l'interfaccia unisce
        automaticamente i risultati di tutti i database coinvolti — non serve scriverlo
        esplicitamente. Funziona con un numero qualsiasi di database, non solo due; vengono
        inclusi solo i database che hanno davvero quella collezione, gli altri vengono
        ignorati automaticamente.
      </p>
    ),
  },
  {
    title: 'JOIN tra più database o collezioni',
    body: (
      <p>
        Un JOIN unisce sempre due collezioni alla volta (anche quando appartengono a
        database diversi). Per unire tre o più collezioni in sequenza, l'interfaccia
        concatena più JOIN uno dopo l'altro dietro le quinte — puoi semplicemente
        chiederlo in linguaggio naturale, ad esempio "utenti con i loro ordini, e gli
        ordini con i prodotti acquistati".
      </p>
    ),
  },
  {
    title: 'Cos\'è "ON DEFAULT SERVER"?',
    body: (
      <p>
        È una parte fissa della sintassi JCoQL+ che significa "usa la connessione al
        database predefinita" — in questa installazione punta sempre al MongoDB in
        esecuzione su <code>localhost:27017</code>. Puoi lasciarla così com'è in ogni
        query, anche scritta a mano.
      </p>
    ),
  },
]

export default function HelpGuide() {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <>
      <button
        type="button"
        className="help-btn"
        onClick={() => setIsOpen(true)}
        title="Guida rapida sul funzionamento dell'interfaccia"
      >
        ❓ Guida
      </button>

      {isOpen && (
        <div className="help-modal" onClick={() => setIsOpen(false)}>
          <div className="help-content" onClick={(e) => e.stopPropagation()}>
            <button
              type="button"
              className="help-close-btn"
              onClick={() => setIsOpen(false)}
              aria-label="Chiudi"
            >
              ✕
            </button>

            <h2>Guida rapida</h2>
            <p className="help-intro">
              Le domande più comuni su come si comporta l'interfaccia — non sulla sintassi
              di JCoQL+.
            </p>

            {HELP_SECTIONS.map((section) => (
              <div className="help-section" key={section.title}>
                <h3>{section.title}</h3>
                {section.body}
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  )
}

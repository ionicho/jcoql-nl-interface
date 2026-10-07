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
    title: 'Database selection in the menu — what it actually does',
    body: (
      <>
        <p>
          When you select several databases from the menu on the left, the selection has a
          different effect depending on what you are doing:
        </p>
        <ul>
          <li>
            <strong>You generate a query in natural language:</strong> all the selected
            databases are taken into account.
          </li>
          <li>
            <strong>You execute a query that is already written</strong> (by hand or generated):
            if the query already specifies its own database with <code>USE DB</code>, that
            one is used — the menu does not override it. The menu only acts as the starting
            database for queries that do not specify one.
          </li>
        </ul>
      </>
    ),
  },
  {
    title: 'What does the "⭐ Save" button do?',
    body: (
      <>
        <p>
          It saves to "Favorites" (right-hand column) the text currently in both boxes — the
          natural-language one and the J-CO-QL+ one — exactly as they are at that moment, not a
          "snapshot" of when the query was generated. From there you can reload it with one
          click in the future, without rewriting or regenerating it from scratch.
        </p>
        <p>
          Note: the mechanism does not know whether the two boxes are still "in sync" with
          each other — it simply records what is written in both at that moment. So if you
          generate a query and then edit only the J-CO-QL+ box (without touching the
          natural-language box), the saved natural-language request may no longer match the
          J-CO-QL+ query saved with it. The opposite also holds: if you edit only the
          natural-language text without pressing "✦ Generate" again, the old J-CO-QL+ query
          (from the last generation or edit) is saved together with the new natural-language
          text.
        </p>
        <p>
          Favorites are stored only in your browser (they are not sent to the server): if you
          change browser or computer, your favorites do not follow you.
        </p>
      </>
    ),
  },
  {
    title: 'What does "Count only" do?',
    body: (
      <p>
        When it is on, the interface does not ask the J-CO engine to serialize and print the
        whole result as JSON — it only reads the count that the engine reports anyway, in the
        same run, for most commands. Useful on large collections or heavy queries (e.g.
        JOIN/GROUP on a lot of data), where building and transferring the whole result would
        waste time if you only care about "how many". The engine computes the whole result
        in both cases — only the cost of serializing and returning it is avoided here, not
        the computation itself.
      </p>
    ),
  },
  {
    title: 'Searching or merging data across several databases',
    body: (
      <p>
        If you select two or more databases that all have the same collection (e.g.{' '}
        <code>users</code>) and you ask for that collection, the interface automatically
        merges the results from all the databases involved — you do not need to say so
        explicitly. It works with any number of databases, not just two; only the databases
        that really have that collection are included, the others are ignored automatically.
      </p>
    ),
  },
  {
    title: 'JOIN across several databases or collections',
    body: (
      <p>
        A JOIN always combines two collections at a time (even when they belong to different
        databases). To join three or more collections in sequence, the interface chains
        several JOINs one after the other behind the scenes — you can simply ask for it in
        natural language, for example "users with their orders, and the orders with the
        products purchased".
      </p>
    ),
  },
  {
    title: 'What is "ON DEFAULT SERVER"?',
    body: (
      <p>
        It is a fixed part of the J-CO-QL+ syntax meaning "use the default database
        connection" — in this installation it always points to the MongoDB running on{' '}
        <code>localhost:27017</code>. You can leave it as it is in every query, including
        hand-written ones.
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
        title="Quick guide to how the interface works"
      >
        ❓ Guide
      </button>

      {isOpen && (
        <div className="help-modal" onClick={() => setIsOpen(false)}>
          <div className="help-content" onClick={(e) => e.stopPropagation()}>
            <button
              type="button"
              className="help-close-btn"
              onClick={() => setIsOpen(false)}
              aria-label="Close"
            >
              ✕
            </button>

            <h2>Quick guide</h2>
            <p className="help-intro">
              The most common questions about how the interface behaves — not about the
              J-CO-QL+ syntax.
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

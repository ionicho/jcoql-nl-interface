"""
JoinExecutor - Costruisce ed esegue un JOIN nativo JCoQL+ tra database diversi

STORIA (perché questo file è cambiato): la versione precedente eseguiva la
STESSA query separatamente su due database ed eseguiva il merge (INNER/LEFT/
RIGHT/FULL) qui in Python, perché generare la sintassi nativa "JOIN OF
COLLECTIONS" via LLM da linguaggio naturale si era rivelato inaffidabile.
Da quando il resto del progetto usa la strategia "auto SAVE AS" (vedi
jco_framework_executor_v2.py) per leggere sempre il risultato VERO calcolato
dal motore invece di ricostruirlo in Python, ha senso applicare la stessa
logica anche qui: quando l'utente configura un JOIN dal form della sidebar
(non scrivendo lui stesso la sintassi, che restava il problema originale),
possiamo costruire noi algoritmicamente la query nativa completa — con tutti
gli USE DB necessari — a partire dai campi già strutturati del form, e
lasciare che sia il motore a fare il lavoro vero.

Verificato manualmente (13/08) che la sintassi costruita qui funziona:
    USE DB db1 ON DEFAULT SERVER;
    USE DB db2 ON DEFAULT SERVER;
    JOIN OF COLLECTIONS coll@db1 AS t1, coll@db2 AS t2
    CASE WHERE .t1.campo = .t2.campo;
ha restituito i documenti reali attesi (5 documenti, verificato dal browser).

SOLO INNER JOIN — decisione presa consapevolmente, non una limitazione
temporanea: la grammatica JCoQL+ non ha un concetto di LEFT/RIGHT/FULL OUTER
JOIN. I token RIGHT/LEFT che compaiono vicino a joinOfCollectionsRule sono
per "SET GEOMETRY (INTERSECTION | RIGHT | LEFT | ALL)" — quale geometria
spaziale tenere quando i documenti hanno dati geografici, un'opzione
completamente estranea a "quale lato dell'outer join". L'unico modificatore
disponibile è un generico KEEP OTHERS sulla CASE WHERE, che dal codice
Java (SynchronizedJoinCycle.java, motore) sembra tenere OGNI coppia
sinistra×destra indipendentemente dalla condizione — non sostituisce il
lato non abbinato con null come farebbe un vero OUTER JOIN, quindi non è
una base solida su cui costruire LEFT/RIGHT/FULL. Implementarli davvero
richiederebbe ricostruire i documenti "rimasti fuori" con query Mongo
separate — fattibile, ma deliberatamente non fatto: se richiesto un tipo
diverso da INNER, execute_join restituisce un errore chiaro invece di un
risultato silenziosamente approssimato o sbagliato.
"""

import logging
import re

join_logger = logging.getLogger('join_executor')


class JoinExecutor:
    """
    Costruisce la query JCoQL+ nativa per un JOIN INNER tra due database e
    la esegue tramite un singolo executor (stesso percorso "auto SAVE AS"
    usato per ogni altra query — vedi jco_framework_executor_v2.py).
    """

    def __init__(self, executor_factory, parser, db_registry):
        """
        Args:
            executor_factory: ExecutorFactory per creare l'executor
            parser: Parser ANTLR per validazione (non usato direttamente qui,
                mantenuto nella firma per compatibilità con chi già istanzia
                questa classe passando questi tre argomenti)
            db_registry: DatabaseRegistry con i database connessi
        """
        self.executor_factory = executor_factory
        self.parser = parser
        self.db_registry = db_registry

    def _extract_collection_name(self, jcoql_query: str):
        """Stesso pattern usato in jco_framework_executor_v2.py: estrae il
        nome della collection da una query tipo 'GET COLLECTION nome; ...'."""
        match = re.search(r'GET\s+COLLECTION\s+(\w+)', jcoql_query, re.IGNORECASE)
        return match.group(1) if match else None

    def build_native_join_query(self, jcoql_query: str, join_config: dict):
        """
        Costruisce (senza eseguire) la query JCoQL+ nativa completa per un
        JOIN INNER, a partire dai campi del form JOIN della sidebar.

        join_config atteso (costruito dal form "Usa JOIN tra database" nella
        sidebar del frontend, vedi DatabaseSelector.jsx):
          {
            'db1': <nome database 1>,
            'db2': <nome database 2>,
            'joinType': 'INNER' (unico supportato, vedi sotto),
            'joinKey': <campo chiave su db1, es. '.user_id' — opzionale>,
            'db2JoinKey': <campo chiave su db2, es. '.id' — opzionale>,
            'alias1': <alias per la collection di db1, es. 't1' — opzionale>,
            'alias2': <alias per la collection di db2, es. 't2' — opzionale>
          }
        Solo 'INNER' è supportato — vedi il docstring del modulo per il
        perché. Per qualunque altro valore la funzione ritorna un errore
        esplicito invece di costruire una query comunque.

        joinKey/db2JoinKey sono OPZIONALI (13/08): la grammatica JCoQL+
        rende la clausola CASE WHERE dentro un JOIN facoltativa — un JOIN
        senza condizione è sintatticamente valido ed esegue un prodotto
        cartesiano completo fra le due collezioni (comportamento già
        verificato per un'altra via, vedi _join_cartesian_product in
        jco_framework_executor_v2.py — con la strategia "auto SAVE AS"
        quel metodo non serve nemmeno più: qualunque risultato, con o
        senza condizione, viene comunque letto correttamente dal motore).
        Se solo UNA delle due chiavi è specificata, viene ignorata (serve
        la coppia completa per costruire una condizione di uguaglianza) e
        si procede come se nessuna fosse stata data.

        alias1/alias2 sono OPZIONALI (13/08): la grammatica JCoQL+ rende
        "AS alias" facoltativo in collectionReferenceRule. Se lasciati
        vuoti, la reference viene scritta senza AS. ATTENZIONE: se le due
        collection hanno lo STESSO NOME (caso comune per confrontare la
        stessa collection logica su due database diversi) e nessuna delle
        due ha un alias, il motore etichetta entrambi i lati del risultato
        con lo stesso nome — un lato sovrascrive l'altro nel documento
        finale. In quel caso specifico serve almeno un alias per
        distinguerli; qui non viene forzato un default automatico perché
        la richiesta esplicita era di non imporre AS — la responsabilità
        di evitare la collisione resta a chi compila il form.

        La collection viene estratta da jcoql_query (stesso presupposto
        della versione precedente: la query di partenza è un semplice
        "GET COLLECTION <nome>; ..." — si assume la STESSA collection
        presente in entrambi i database, come nell'implementazione originale).

        Returns:
            (query_completa, db1, db2, None) in caso di successo, oppure
            (None, None, None, messaggio_errore) se non è stato possibile
            costruire la query (join_config incompleto, tipo non supportato,
            o collection non estraibile).
        """
        if not join_config:
            return None, None, None, "join_config è vuoto"

        db1 = join_config.get('db1')
        db2 = join_config.get('db2')
        join_type = join_config.get('joinType', 'INNER').upper()
        join_key_db1 = (join_config.get('joinKey') or '').strip()
        join_key_db2 = (join_config.get('db2JoinKey') or '').strip()
        alias1 = (join_config.get('alias1') or '').strip()
        alias2 = (join_config.get('alias2') or '').strip()

        if not db1 or not db2:
            return None, None, None, f"join_config incompleto: db1={db1}, db2={db2}"

        if join_type != 'INNER':
            return None, None, None, (
                f"Tipo di JOIN '{join_type}' non supportato: JCoQL+ non ha un "
                "concetto nativo di LEFT/RIGHT/FULL OUTER JOIN, solo INNER "
                "JOIN è implementato. Seleziona INNER JOIN nel form."
            )

        collection = self._extract_collection_name(jcoql_query)
        if not collection:
            return None, None, None, f"Impossibile estrarre il nome della collection da: {jcoql_query}"

        # Gli alias sono testo libero digitato dall'utente nel form — devono
        # essere ID validi per la grammatica JCoQL+ ("ID : LETTER (LETTER |
        # DIGIT | '_')*", stessa regola già scoperta per il nome della
        # collection temporanea in jco_framework_executor_v2.py). Se non lo
        # sono, meglio un errore chiaro qui che un "Lexical Error" criptico
        # dal motore dopo aver già lanciato il subprocess Java.
        id_pattern = re.compile(r'^[A-Za-z][A-Za-z0-9_]*$')
        for label, alias in (("alias1", alias1), ("alias2", alias2)):
            if alias and not id_pattern.match(alias):
                return None, None, None, (
                    f"L'alias '{alias}' non è un identificatore JCoQL+ valido "
                    "(deve iniziare con una lettera, poi solo lettere/cifre/underscore)."
                )

        # Riferimento a ciascuna collection, con AS solo se un alias è
        # stato effettivamente fornito (grammatica: "AS alias=ID" opzionale
        # in collectionReferenceRule).
        ref1 = f"{collection}@{db1}" + (f" AS {alias1}" if alias1 else "")
        ref2 = f"{collection}@{db2}" + (f" AS {alias2}" if alias2 else "")

        query = (
            f"USE DB {db1} ON DEFAULT SERVER;\n"
            f"USE DB {db2} ON DEFAULT SERVER;\n"
            f"JOIN OF COLLECTIONS {ref1}, {ref2}"
        )

        # La condizione si può scrivere solo se ABBIAMO sia la chiave che
        # l'alias per riferirla (.alias.campo) su entrambi i lati — senza
        # alias non c'è modo di scrivere .alias.campo in modo univoco.
        if join_key_db1 and join_key_db2 and alias1 and alias2:
            cond1 = f".{alias1}{join_key_db1}"
            cond2 = f".{alias2}{join_key_db2}"
            query += f"\nCASE WHERE {cond1} = {cond2};"
        else:
            # Nessuna condizione (prodotto cartesiano) oppure chiavi date
            # senza i corrispondenti alias — in quel secondo caso la
            # condizione va comunque scartata (non costruibile senza
            # alias), loggato qui sotto per non farlo sparire in silenzio.
            if (join_key_db1 or join_key_db2) and not (alias1 and alias2):
                join_logger.warning(
                    "Join key specificata ma manca almeno un alias — "
                    "condizione ignorata, eseguito come JOIN senza condizione "
                    "(prodotto cartesiano). Per usare una join key servono "
                    "entrambi gli alias."
                )
            query += ";"

        join_logger.info(f"🔗 Query JOIN nativa costruita (INNER):\n{query}")

        return query, db1, db2, None

    def execute_join(self, jcoql_query: str, join_config: dict):
        """
        Costruisce la query nativa (solo INNER, vedi build_native_join_query)
        ed esegue tramite UN SOLO executor — invece dei due executor + merge
        Python della versione precedente.

        Returns:
            (documenti, query_nativa_o_None, errore_o_None). La query nativa
            è None solo se non è stato possibile costruirla (in quel caso
            'errore' spiega perché); se la costruzione riesce ma
            l'esecuzione sul motore fallisce, la query nativa viene comunque
            restituita (utile per il debug lato utente) insieme all'errore.
        """
        native_query, db1, db2, build_error = self.build_native_join_query(jcoql_query, join_config)
        if native_query is None:
            join_logger.warning(f"JOIN non costruito: {build_error}")
            return [], None, build_error

        try:
            executor = self.executor_factory.create_executor(
                "jco_framework",
                mongo_uri="mongodb://localhost:27017",
                database=db1
            )
            if executor is None:
                join_logger.error("❌ create_executor ha ritornato None")
                return [], native_query, "Impossibile creare l'executor"

            result = executor.execute(native_query)

            if not result.get('success'):
                error = result.get('error')
                join_logger.error(f"❌ JOIN nativo fallito: {error}")
                return [], native_query, error

            docs = result.get('results', [])
            join_logger.info(f"✅ JOIN nativo: {result.get('count', len(docs))} documenti dal motore")

            return docs, native_query, None

        except Exception as err:
            join_logger.error(f"❌ JOIN nativo — errore: {err}", exc_info=True)
            raise
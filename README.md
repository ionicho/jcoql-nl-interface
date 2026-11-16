# J-CO-QL+ Natural Language Interface

A Natural Language → J-CO-QL+ translation system with RAG (Retrieval-Augmented Generation), validation through the official ANTLR3 parser, and execution on real databases (MongoDB and JCO DS) through the J-CO Framework engine.

**University of Bergamo**
**Master's Thesis** - Nicholas Iotti
**Supervisors:** Prof. Giuseppe Psaila, Prof. Paolo Fosci

---

## Goal

Let users query databases using **natural language** instead of writing J-CO-QL+ queries by hand, with:
- Automatic generation of J-CO-QL+ queries through an LLM (multi-provider: cloud and local)
- A local model fine-tuned on J-CO-QL+ (Llama 3.1 8B with a LoRA adapter), offered by the interface as the "tuned" mode
- Validation through the official ANTLR3 parser of the J-CO project
- Real execution through the J-CO Framework engine, not a reimplementation
- Support for 10 language commands, including cross-database and chained JOINs, MERGE over N databases, GENERATE, GET DICTIONARY
- Multiple databases (MongoDB and JCO DS), with automatic schema discovery (including types and sample values per field) and approximate field-name matching

> Methodological note: the sections of this README only report data verified with direct tests on the system. Where a measurement has not been re-verified recently, this is stated explicitly.

> Note on languages: the user interface is in English. The system prompt and the RAG examples are written in Italian. Requests can be written in Italian or in English: the test campaign was run in both languages, and the training data of the fine-tuned model are bilingual. The natural-language examples below are shown in English for readability.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  USER INPUT                                              │
│  • Natural Language: "Group the orders by status"        │
│  • Direct J-CO-QL+: GET COLLECTION hotels; ...            │
└──────────────────┬────────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────┐
│  RAG RETRIEVAL (ChromaDB)                                │
│  • Validated examples, loaded from examples/validated/*.txt │
│  • Local embeddings: all-MiniLM-L6-v2                    │
│  • Top-N semantically most similar examples              │
└──────────────────┬────────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────┐
│  LLM GENERATION (multi-provider, selected with if/elif,  │
│  not a real Factory)                                     │
│  • Google Gemini (cloud)                                 │
│  • Llama 3.1 8B, Llama 3.2 3B, Gemma 1 7B, Gemma 4 E4B   │
│    via Ollama (local)                                    │
│  • Real schema of the selected databases in the prompt   │
│    (type and sample values per field, not just the name)  │
│  • Gemini: complete prompt with the full J-CO-QL+ grammar │
│  • Local models: "compact" prompt (default) or "full"     │
│    (see section "Prompt modes for local models")          │
│  • "tuned" mode: fine-tuned Llama 3.1 8B (base model +   │
│    LoRA adapter applied at run time by llama-server),    │
│    short prompt, no RAG examples                         │
└──────────────────┬────────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────┐
│  PARSER VALIDATION + DETERMINISTIC REPAIRS                │
│  • ANTLR3 Official (J-CO project repository)              │
│  • Automatic repair loop on validation errors             │
│  • Targeted repairs for recurring errors that the prompt  │
│    alone does not fix reliably (see section               │
│    "Deterministic repairs" below)                         │
└──────────────────┬────────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────┐
│  JCO FRAMEWORK EXECUTOR                                   │
│  • Official J-CO Java engine, launched as a subprocess    │
│  • "Auto SAVE AS" strategy: every query gets a SAVE AS    │
│    to a unique temporary collection appended at the end;  │
│    the result is read back from MongoDB and the           │
│    collection is deleted right after — the engine itself  │
│    computes the result, not a reconstruction on the       │
│    Python side                                            │
│  • Alternative "Count only" mode (optional, for large     │
│    collections): no SAVE AS is added, only the count the  │
│    engine already prints on stdout is read (see section   │
│    "Scalability" below)                                   │
│  • Configurable execution timeout (2-20 minutes, or none) │
└──────────────────┬────────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────┐
│  DATABASE EXECUTION                                        │
│  • Multiple databases, switching from the interface        │
│  • MongoDB and JCO DS servers                              │
│  • Recursive schema discovery for every connected database │
└──────────────────┬────────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────┐
│  RESULTS VISUALIZATION                                     │
│  • JSON documents, full J-CO-QL+ syntax executed           │
│  • Real count (not limited to the displayed documents)     │
│  • Favorite queries, savable and searchable (localStorage) │
│  • Automatic history of the last 50 executed queries,      │
│    success or error (localStorage, same pattern)           │
│  • Built-in quick guide ("❓ Guide" button)                 │
└─────────────────────────────────────────────────────────┘
```

---

## Quick Start

> Quick guide. For the complete step-by-step procedure (including the exact
> commands for Ollama, the MongoDB seed, and the correct order in which to
> start everything the first time), see **[SETUP.md](SETUP.md)**.

### Prerequisites

- **Python 3.x**
- **Node.js**
- **MongoDB**
- **Ollama** (for local LLMs, optional)
- **llama.cpp** (`llama-server`, build with CUDA support; optional, only for the tuned mode)
- **Java 8+** (for the J-CO Framework engine and the ANTLR3 parser)
- **Gradle** (to build the J-CO Framework, if modified)
- **A JCO DS server** (optional, only to query JCO DS databases)

### Installation
```bash
# 1. Clone repository
git clone https://github.com/ionicho/jcoql-nl-interface.git
cd jcoql-nl-interface

# 2. Backend setup
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

pip install -r requirements.txt

# 3. Frontend setup
cd frontend
npm install

# 4. Environment variables
cp .env.example .env
# Edit .env with your GEMINI_API_KEY

# 5. MongoDB
# Make sure MongoDB is running. To populate the example database
# "jcoql_test" from scratch, see SETUP.md (section "Sample data").

# 6. Load the examples into ChromaDB
python backend/database/load_examples.py
```

`load_examples.py` scans **all** the `.txt` files in `examples/validated/`
(path computed relative to the script's location, not to the folder you launch it
from) and recreates the ChromaDB collection from scratch on every run — after running it,
**restart the backend**, otherwise it stays attached to the reference of the previous collection.

> This is all you need for a quick start if you already have a ready environment.
> For a new environment (Ollama, local models, MongoDB seed, final check),
> follow **[SETUP.md](SETUP.md)** in order — it avoids most of the common errors
> met during development (relative paths, start-up order, Ollama models
> not downloaded).

### Run
```bash
# Terminal 1: Backend (from the project root - imports use the "backend" package)
venv\Scripts\activate
uvicorn main:app --reload

# Terminal 2: Frontend
cd frontend
npm run dev
```

Open your browser at: **http://localhost:5173**

The backend and the interface are always needed. Two more processes are needed only for
specific features, and each one runs in its own terminal:

| # | Process | Command | When needed |
|---|---|---|---|
| 1 | Server of the tuned model | `finetune\soup\start_llama_server_v4.ps1` | Tuned mode (port 8081) |
| 2 | JCO DS server | `java -jar jcoql-ds-server-1.0.0.jar --thin.root=jcoql-ds-server/deps`, from the folder of the J-CO executables | JCO DS databases (port 17017) |
| 3 | Backend | `uvicorn main:app --reload`, from the project root | Always (port 8000) |
| 4 | Interface | `npm run dev`, from `frontend` | Always (`localhost:5173`) |

MongoDB is assumed to be running, and so is Ollama if the local models are used.
See **[SETUP.md](SETUP.md)** for the details of each process.

### Debug

The system prints detailed diagnostic logs (the full query sent to the Java engine,
the RAG examples retrieved for each request, an execution summary) — the full query
is always visible in the console, the rest only if explicitly requested:
```bash
set JCOQL_DEBUG=true   # Windows (PowerShell: $env:JCOQL_DEBUG="true")
# export JCOQL_DEBUG=true   # Linux/Mac
```
It is off by default, to avoid cluttering the console during normal use.

---

## Technology Stack

### Backend
- **Framework:** FastAPI
- **Databases:** MongoDB, JCO DS
- **Vector DB:** ChromaDB (persistent, local)
- **Cloud LLM:** Google Gemini
- **Local LLMs:** Ollama (Llama 3.1 8B, Llama 3.2 3B, Gemma 1 7B, Gemma 4 E4B)
- **Fine-tuned model:** Llama 3.1 8B + LoRA adapter, served by llama.cpp (`llama-server`); adapter trained with Soup (QLoRA)
- **Embeddings:** sentence-transformers (all-MiniLM-L6-v2, local)
- **Parser:** ANTLR3 (official J-CO project repository)
- **Executor:** J-CO Framework engine (Java), launched as a subprocess

### Frontend
- **Framework:** React
- **Build:** Vite
- **Routing:** React Router
- **HTTP:** Axios
- **Local persistence:** localStorage (favorite queries, automatic history of the last 50 queries)

---

## Database Integration

### Multi-Database
- Selection of one or more databases from the interface (a single mode: the previous
  "single database" selection was removed because it was redundant)
- Automatic schema discovery for every connected database, including nested fields,
  observed type and real sample values per field
- Approximate field-name matching (based on `difflib`, not on hand-written keyword
  lists) to handle cross-language requests
- Generation receives the full list of selected databases (not just the first one),
  needed so that the LLM can use real names in queries involving several databases
  instead of guessing them
- When several selected databases share the same collection (e.g. `users`) and that
  collection is requested, the results are merged automatically with a `MERGE`

### JCO DS databases

Besides MongoDB, a database stored in a **JCO DS** server (J-CO Document Store, the
alternative document store of the J-CO project: https://github.com/JcoProjectTeam) can be
connected from the interface ("➕ Add Database" in the sidebar → server
"JCO DS (professors' server)"). The form asks for host, port, database name and the list
of its collections.

- Schema discovery goes through the Java engine itself (there is no Python client for the
  JCO DS binary protocol), sampling the documents of each listed collection.
- Queries on a JCO DS database declare the server explicitly and qualify collections with
  `@database`:
  ```
  USE DB testds ON SERVER 'jcods' 'http://localhost:17017';
  GET COLLECTION testcoll@testds;
  ```
  while MongoDB databases keep using `ON DEFAULT SERVER`.
- **Collections must be listed by hand** when connecting: J-CO-QL+ has no command to list
  the collections of a database (there is no "SHOW COLLECTIONS"), so they cannot be
  discovered automatically as with MongoDB.
- The same connection can also be registered through `POST /api/databases/connect`
  (optional parameters `server_type=jcods`, `server_host`, `server_port`, `collections`).

### Query Execution — verified examples

**Mode 1: Natural Language → J-CO-QL+**
```
Input: "Group the orders by status"
  ↓
Generated query: GET COLLECTION orders;
                 GROUP PARTITION TRUE BY .status INTO .orders_by_status;
  ↓
Execution: real result read from the engine, no reconstruction on the Python side
```

**Mode 2: Direct J-CO-QL+ query, with cross-database JOIN**
```
Input: USE DB jcoql_test ON DEFAULT SERVER;
       USE DB test_db ON DEFAULT SERVER;
       JOIN OF COLLECTIONS users@jcoql_test AS t1, users@test_db AS t2
       CASE WHERE .t1.user_id = .t2.id;
  ↓
Execution: 5 real documents, read from the engine
```

**Mode 3: Several JOINs in the same request ("chained joins")**
```
Input: "orders with the user who placed them and the products purchased"
  ↓
Generated query: JOIN (orders↔users) → intermediate SAVE AS → EXPAND
                 of the items array → JOIN (items↔products)
  ↓
Execution: 6 real documents; the intermediate collections are deleted
           automatically at the end of the execution
```

---

## Supported J-CO-QL+ Commands

The system supports 10 main commands of the language, all executed by the real
J-CO Framework engine (not by a Python reimplementation of the language):

| Command | Status | Notes |
|---|---|---|
| `GET COLLECTION` (database) | Complete | Comparison operators, `AND`/`OR`, `IN_RANGE`, nested fields |
| `GET COLLECTION FROM WEB` / `FROM FILE` | Complete | The `FROM FILE` path is resolved relative to the working directory of the Java process |
| `FILTER` + `GENERATE` (`BUILD`/`ADD FIELDS`/`REMOVE FIELDS`) | Complete | `KEEP`/`DROP OTHERS` valid only after a `CASE WHERE`; no direct arithmetic as a field value (only references, literals, functions); missing values are tested with `FIELD .field IS NULL` / `IS NOT NULL` (`WITHOUT`/`WITH` test whether the key is absent/present in the document, not whether it is `null`) |
| `JOIN OF COLLECTIONS` | Complete, `INNER` only | Cross-database working (native, `@db1`/`@db2`); `LEFT`/`RIGHT`/`FULL OUTER` do not exist in the J-CO-QL+ grammar, deliberately not implemented |
| Chained joins (several `JOIN`s in the same query) | Complete | Through an intermediate `SAVE AS`, with automatic cleanup of the temporary collections; if the join key is inside an array an intermediate `EXPAND` is needed (the `=` comparison requires the same type on both sides, an array is never "equal" to a single value even if it contains it) |
| `GROUP PARTITION` | Complete | Multi-partition in the same command, `ORDER BY` (requires an explicit `TYPE NUMERIC`/`STRING`/`BOOLEAN`; ordering exists only inside `GROUP PARTITION`) |
| `EXPAND UNPACK` | Complete | Multi-clause in the same command |
| `MERGE COLLECTIONS` | Complete | Any number of collections/databases, optional `REMOVE DUPLICATES` |
| `INTERSECT COLLECTIONS` | Verified only on disjoint data | A case with real overlap has never been tested |
| `SUBTRACT COLLECTIONS` | Verified only on disjoint data | As above |
| `GET DICTIONARY` + `TRANSLATE` | Complete | Automatic repair if the LLM generates `TRANSLATE` without the corresponding `GET DICTIONARY` (see below) |
| `SAVE AS coll@db` | Complete | `@database` always required, otherwise nothing is written to MongoDB (by design) |
| `SAVE TO FILE` | Verified | Relative paths are resolved relative to the working directory of the Java process |

**Not implemented, out of the current scope:** `LOOKUP FROM WEB`, `TRAJECTORY MATCHING`,
the 7 variants of `CREATE FUZZY` (two of which, `CREATE JAVA/JAVASCRIPT FUNCTION`,
would allow execution of arbitrary server-side code generated from a natural-language
prompt — avoided for security reasons, not only for implementation complexity).
These commands exist in the grammar and can be written by hand in the query panel, but
the LLM is given no instructions or examples for them (the Dashboard lists them under
"Not generable from natural language").

For every command, the displayed result is the true one computed by the J-CO engine: the
received query is transparently followed by a `SAVE AS` to a temporary collection with a
unique name, whose content is then read back from MongoDB and the collection deleted —
there is no longer any reconstruction of the command semantics on the Python side (see
architecture above).

---

## Prompt modes for local models

Local models receive a prompt in one of three modes:

- **`compact`** (default): a condensed set of language rules plus the real schema and the
  retrieved RAG examples.
- **`full`**: the complete set of rules plus the Basic grammar (`JCoQLBasic`, instead of the
  full grammar, to fit the context of local models), and a reminder to use the full path
  of nested fields.
- **`tuned`**: the short prompt that the fine-tuned model saw in training (the schema and the
  request, no rules and no RAG examples). Only Llama 3.1 is available in this mode, and the
  model is called through `llama-server` (default `http://127.0.0.1:8081`, see `LLAMACPP_URL`
  in `.env.example`). If the server is not reachable the backend reports an error and does
  not fall back on another model. See section "Fine-tuning" below.

In the interface the **Mode** selector, next to the choice of the model, offers *Standard*
(the `compact` prompt) and *Tuned*; choosing *Tuned* selects Llama 3.1 automatically. The
`full` mode is not offered by the interface. The mode can also be set with the `LOCAL_PROMPT_MODE` environment variable or changed at
runtime through `POST /api/set_local_prompt_mode?mode=compact|full|tuned`
(current value: `GET /api/local_prompt_mode`). A restart of the backend brings the mode back
to the initial value. Cloud Gemini is not affected by this setting: it always receives the
complete prompt with the full J-CO-QL+ grammar.

---

## Fine-tuning

The folder `finetune/` contains everything that was used to fine-tune Llama 3.1 8B Instruct
on J-CO-QL+ and to evaluate the result. Four versions were trained (v1 to v4); the interface
serves the adapter of the fourth one.

**Training data** (`finetune/*.py`, run with the virtual environment of the backend):

| Script | Purpose |
|---|---|
| `ft_gen.py`, `ft_gen_v3.py`, `ft_gen_v4.py` | Generate synthetic databases and pairs of request and query; the expected result is computed in Python on the same data |
| `ft_paraphrase.py`, `ft_paraphrase_v4.py` | Rewrite the requests with Gemini; every rewriting is checked by code |
| `ft_verify.py`, `ft_verify_v4.py` | Execute a sample of the reference queries through the backend and compare the result with the expected one |
| `ft_merge_v3.py`, `ft_merge_v4.py` | Put together the data of a version with the data of the previous one |
| `ft_translate_train_v4.py`, `ft_translate_eval.py` | Translate the requests into English with Gemini (training set of v4 and evaluation set), with checks on every translation |

The header of each script describes the options and the command to launch it.

**Training** (`finetune/soup/`, in a separate Python environment with
[Soup](https://github.com/MakazhanAlpamys/Soup)): `soup train --config soup_v4.yaml`. The
files `soup*.yaml` are the configurations of the four versions (QLoRA, rank 16, scaling
factor 32, learning rate 2e-4, base model loaded with 4-bit quantization).

**Use of the adapter**: the adapter is not merged into the model. `ft_lora_gguf_v4.ps1`
converts the adapter to the GGUF format, and `start_llama_server_v4.ps1` starts `llama-server`
with the quantized base model (the file that Ollama downloaded for
`llama3.1:8b-instruct-q4_K_M`) and the adapter applied at run time.

**Evaluation** (`finetune/soup/`): `ft_eval_cpp.py` sends each held-out request to the model,
takes the first answer without corrections, executes it through the backend and compares the
number of documents with the expected one. The results are the files `eval_*.csv` and the
folder `heldout_altri/` (the other models on the same requests).

**Not in the repository**: the generated datasets (`finetune/out*/`), the adapters and the
models (`*.gguf`, `finetune/soup/output*/`) are excluded because of their size (see
`.gitignore`). The tuned mode therefore needs an adapter trained with the scripts above;
the paths of `llama-server` and of the adapter are set at the top of
`start_llama_server_v4.ps1`.

---

## Scalability on large collections

Every query (except `GET COLLECTION`) normally receives the automatic `SAVE AS`
described above — the only way to read back in the browser a result that the
engine otherwise computes only in memory and prints as a bare count on
stdout. Even for a read-only command, this means a real write to MongoDB of the
entire result before it can be read back.

On large collections or with complex documents, this write can become
the real bottleneck, regardless of the computation cost of the command
itself. Verified live: a `GROUP PARTITION` on ~21,000 documents
failed with `Payload document size is larger than maximum of 16777216` (MongoDB's
BSON limit, 16MB) even though the computation completed in ~25s — what failed
was saving the resulting group, not the computation.

For these cases, an alternative mode (checkbox "📊 Count only
(large databases)" in the query panel) runs the query as it is, without
any added `SAVE AS`, reading only the count that the engine prints
anyway on stdout — no extra reads or writes on MongoDB. Verified
live on two distinct cases:
- **Solves** the case above (GROUP + EXPAND hitting the BSON limit): with this
  mode the execution completes successfully, 25 groups, no errors.
- **Does not solve** a completely unfiltered JOIN between two large
  collections (~50,000 × ~21,000 documents): here the dominant cost is the
  combinatorial computation itself (non-indexed nested-loop comparison), not
  persistence — neither the normal mode nor the "count only" mode completes in
  reasonable time.

The two classes of bottleneck — result persistence vs. combinatorial computation of
the engine — are therefore distinct and need different mitigations; only the first is
addressed by this mode.

For long-running queries, the query panel also has a **Timeout** selector (2, 5, 10, 15,
20 minutes, or **No timeout**). When the time expires, the backend always answers with an
explicit error message, never a silent timeout.

---

## Deterministic repairs

During development some generation errors recurred systematically, even after
strengthening the instruction in the prompt and verifying that the relevant RAG example
was actually retrieved. In those cases, instead of insisting on the prompt, the error
is recognized and fixed directly in code after generation:

- **`TRANSLATE` without `GET DICTIONARY`**: if the generated query uses `TRANSLATE(...)` but never
  registers the dictionary with `GET DICTIONARY`, the dictionary name is looked up in the
  user's original request (pattern like "dictionary X") and the missing line
  is added automatically.
- **Missing or invented `@database`** on a collection reference inside `JOIN`/`MERGE`:
  added if absent; if the model invented a name that matches a collection
  instead of a real database, the fictitious `USE DB` line is removed and replaced with the
  correct database (checked against the list of actually registered databases, not
  against a hand-written list).
- **Type mismatch in a `JOIN`**: if the condition compares the same field name between two
  collections that have different types for that field according to the discovered schema (e.g.
  an integer against a string), it is a sign that the name matches but the meaning does not —
  here the system does not choose a replacement, it reports the inconsistency and forces another
  generation attempt with the concrete evidence.
- **`IS NOT NULL` syntax**: forms such as `ISNOTNULL`/`ISNULL` (invalid in the lexer, which
  requires the spaces) are normalized to `IS NOT NULL`/`IS NULL`, adding the missing `FIELD` keyword.

---

## Architecture Patterns

The system uses the **Factory Pattern** for two components — not for the selection of
the LLM, which is implemented with a simple `if`/`elif` on the requested provider, not a real
Factory class:

```python
# backend/parsers/parser_factory.py
class ParserFactory:
    @staticmethod
    def create_parser(parser_type: ParserType):
        return ANTLR3OfficialParser()

# backend/executors/executor_factory.py
class ExecutorFactory:
    @staticmethod
    def create_executor(executor_type: ExecutorType):
        return JcoFrameworkExecutor()
```

> A second executor also exists (`python_translator.py`, direct J-CO-QL+→MongoDB
> translation without going through the Java engine, selectable with
> `ACTIVE_EXECUTOR=python_translator`), meant as a lightweight fallback limited to
> `GET COLLECTION`+simple `FILTER`. The project always uses and tests only
> `jco_framework` (the default): it is what this whole README refers to.

---

## Known Limitations

- **JOIN key choice via natural language**: when two collections
  share a field name that refers to different entities (e.g. a `user_id` field present in
  both, but an identifying string in one and an internal sequence number
  in the other), the model may still choose the wrong field at the first
  attempt, even though the schema shows the type and real sample values for each field.
  The type-mismatch check (section above) catches the most common case and
  forces another attempt, but does not guarantee that the next attempt is correct —
  it remains a limit of the language model's reasoning, not of the verification mechanism.
  The interface no longer offers a dedicated form to build a native JOIN from the sidebar
  (removed because redundant — a JOIN can still be written by hand or generated via
  NL in the query panel, with the same engine and the same cross-database syntax).
- **`INTERSECT`/`SUBTRACT`**: equality between documents (content-based,
  excluding `_id`) is verified only on collections with no real overlap.
- **Local LLM models**: in the comparative tests, the local models show a
  noticeably lower success rate than the cloud provider on the same inputs, as well as a
  higher latency per call; the smaller models struggle most on difficult requests
  (3-way JOINs, MERGE of subsets, arithmetic, which is not supported by the language).
- **Fine-tuned model**: the adapter was trained and evaluated mostly on synthetic databases
  generated by the same procedure; on the test database `jcoql_test` the gain over the base
  model is smaller than on the synthetic held-out requests. The adapter is trained on one
  quantization of the base model and used on another one.
- **Leftover collections**: `SAVE AS` in a query leaves the saved collection in the
  database, and from then on it appears in the schema passed to the LLM, which may use it
  instead of the original collection. Delete test collections between runs.
- **JCO DS**: the collections of a JCO DS database must be listed by hand (see above).
  A request on a collection that does not exist in the DS-Server was observed to hang
  instead of returning an error (the cause was not confirmed with the server logs); the
  execution timeout selector bounds the wait.
- **Relative paths**: both on the Java side (classpath, engine configuration files)
  and on the Python script side (`load_examples.py`), several bugs met during
  development derived from relative paths resolved against the launch folder
  instead of an absolute reference — an in-depth investigation of one of these cases
  (the `SAVE AS` command, and the root cause later found in the J-CO engine fork itself)
  is documented in a separate technical report.

---

## Test Scripts

The scripts used for the test campaign are in the project root:

| Script | Purpose |
|---|---|
| `verify_execution.py` | Executes the generated queries and compares the result with an expected one (exact / count only / different / invalid) |
| `repeatability.py` | Repeats the same request several times on each model and records the generated queries |
| `rerun_rounds.py`, `rerun_extended.py` | Re-run the test rounds / the extended test set on selected models and prompt modes |
| `rerun_english.py` | The requests of the extended test set written in English, with the same expected results |
| `stability.py` | Repeats the same request many times (default 50) on each model and counts the distinct queries and the correct ones |
| `run_test_mancanti.ps1` | Runs the extended test, the paraphrases and the stability test on the fine-tuned model (v4); writes in the folder `completa_v4/`, which is not in the repository |
| `extended_tests.py` | Defines the extended test set (additional common and difficult requests) and its expected results |
| `paraphrase.py` | Tests the robustness of the generation to paraphrased requests |
| `pulisci_collezioni.py` | Deletes the temporary collections left in `jcoql_test` (keeps `products`, `orders`, `users`, `category_translations`) |

Results are saved as CSV files (`*_runs.csv`, `*_riepilogo.csv`, `test_campaign_log.csv`).
The header of each script describes the options. Every call to `/api/generate` is also recorded in `test_campaign_log.csv`.

---

## Project Structure

```
jcoql-nl-interface/
├── main.py                        # FastAPI backend (must be launched from the root)
├── .env
├── requirements.txt
│
├── backend/
│   ├── query_corrector.py
│   ├── join_executor.py           # Builds native JOIN queries (INNER only)
│   ├── llm_local.py               # Local models: Ollama (Llama 3.1/3.2, Gemma 1/4) and
│   │                               # llama-server (fine-tuned Llama 3.1, tuned mode)
│   ├── database_persistence.py    # Saves/restores the connected databases
│   ├── rag_examples_extended.txt  # ALWAYS injected into every prompt - only generic
│   │                               # syntactic patterns, no field names tied to
│   │                               # a specific database
│   ├── jcoql_syntax_official.txt  # Full JCoQL.g grammar, injected into the prompt
│   ├── jcoql_syntax_basic_official.txt  # Basic grammar, used by local models in "full" mode
│   │
│   ├── parsers/
│   │   ├── parser_factory.py
│   │   └── antlr3_official_parser.py
│   │
│   ├── executors/
│   │   ├── executor_factory.py
│   │   └── jco_framework_executor_v2.py  # "Auto SAVE AS" strategy
│   │
│   └── database/
│       ├── database_registry.py   # Connected databases (MongoDB and JCO DS)
│       ├── schema_discovery.py    # Discovers fields, types and sample values
│       └── load_examples.py       # Scans examples/validated/*.txt, absolute paths
│                                    # relative to the script's location
│
├── examples/validated/
│   └── *.txt                       # RAG examples, all loaded automatically
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── QueryExecutor.jsx       # Single panel: input, editable query, results
│   │   ├── Favorites.jsx           # Favorite queries, search, localStorage
│   │   ├── History.jsx             # Automatic history (max 50), localStorage
│   │   ├── DatabaseSelector.jsx    # Multi-database selection, schema discovery
│   │   ├── HelpGuide.jsx           # Quick guide on how the interface behaves
│   │   ├── Toast.jsx               # Non-blocking notifications
│   │   └── Dashboard.jsx
│   └── package.json
│
├── finetune/
│   ├── ft_*.py                     # Training data: generation, rewriting, translation, checks
│   └── soup/                       # Training configurations (soup*.yaml), conversion and
│                                   # start scripts (*.ps1), evaluation (ft_eval*.py, eval_*.csv)
│
├── *.py, *.csv (root)              # Test scripts and their results (see "Test Scripts")
├── chroma_data/                    # Persistent ChromaDB storage (not in the repository)
└── logs/                           # Application logs (not in the repository)
```

---

## Contributors

**Nicholas Iotti** - University of Bergamo
GitHub: [@ionicho](https://github.com/ionicho)

**Supervisors:**
- Prof. Giuseppe Psaila
- Prof. Paolo Fosci

---

## License

Master's thesis project - University of Bergamo

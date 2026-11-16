# Setup — jcoql-nl-interface

Step-by-step guide to get the project running from scratch on a new machine, in
order. Every step here exists because during development skipping it or doing it
in the wrong order caused a concrete error — they are collected here on purpose
so you do not have to rediscover them one by one.

---

## 1. Prerequisites

| Software | Version | Notes |
|---|---|---|
| Python | 3.x | |
| Node.js | — | for the frontend |
| MongoDB | — | running locally on `localhost:27017` |
| Java | 8+ | needed by the J-CO Framework engine and the official ANTLR3 parser |
| Ollama | — | only if you want to use Llama/Gemma locally; optional if you only use Gemini |
| llama.cpp (`llama-server`) | build with CUDA support | only for the tuned mode (fine-tuned Llama 3.1); optional |
| Gradle | — | only if you modify the `jco-framework` fork, not needed to use the interface as it is |
| JCO DS server | Java 17 | only if you want to query JCO DS databases (https://github.com/JcoProjectTeam); optional |

---

## 2. Clone and install the dependencies

```bash
git clone https://github.com/ionicho/jcoql-nl-interface.git
cd jcoql-nl-interface

python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac

pip install -r requirements.txt

cd frontend
npm install
cd ..
```

---

## 3. Environment variables

```bash
cp .env.example .env
```

Open `.env` and set at least `GEMINI_API_KEY` (needed even if you plan to use
only the local models: some code paths require it at start-up anyway).
The other variables (`ACTIVE_LLM`, `ACTIVE_PARSER`, `ACTIVE_EXECUTOR`,
`LOCAL_PROMPT_MODE`, `JCOQL_DEBUG`) have a sensible default and you do not need to touch them for a first start:

- `ACTIVE_LLM` — default `gemini`. Can also be changed at runtime from the UI, not only from here.
- `ACTIVE_PARSER` — default `antlr3_official`. **There is no way to change it at runtime**, only here + restart.
- `ACTIVE_EXECUTOR` — default `jco_framework`. **It is the only one used and tested in this project** — `python_translator` also exists (direct translation without the Java engine, coverage limited to `GET COLLECTION`+simple `FILTER`), but it is not the one the examples/tests of this repository are based on. Do not change it unless you are running a specific experiment.
- `LOCAL_PROMPT_MODE` — default `compact`. Prompt mode for the local models (`compact`, `full` or `tuned`); it can also be changed at runtime from the UI (Mode selector: Standard = `compact`, or Tuned) or with `POST /api/set_local_prompt_mode?mode=compact|full|tuned`. A restart of the backend brings it back to the value set here.
- `LLAMACPP_URL` — only for the tuned mode, and only if `llama-server` is not on the default `http://127.0.0.1:8081` (see step 8).

---

## 4. Ollama (only if you want local models)

If you are not interested in local models, skip this step — Gemini works without Ollama.

1. Install Ollama: https://ollama.com
2. Download the models used by the project (the exact names matter, they are hardcoded in `backend/llm_local.py`; you only need the ones you want to use):
   ```bash
   ollama pull llama3.1:8b-instruct-q4_K_M
   ollama pull gemma:7b-instruct-q4_K_M
   ollama pull llama3.2:3b-instruct-q4_K_M
   ollama pull gemma4:e4b-it-q4_K_M
   ```
3. Check that Ollama is running before selecting a local model from the UI — if it is not, or if the model was not downloaded with this exact tag, generation fails with an error that bubbles up to the `/api/generate` endpoint (the exception is not handled inside `llm_local.py`, you see it propagated).
4. VRAM note: switching between local models in the same session may require stopping the loaded one (`ollama ps`, then `ollama stop <model-name>`) to free memory — the UI also reminds you of this when you select a local model.

---

## 5. Sample data in MongoDB

The reference database used by all the RAG examples and by the tests is `jcoql_test`.
The repository ships the seed files in `backend/database/data_*.json` (hotels, restaurants,
products, orders, users and a fixed dictionary `category_translations`). The collections
the test campaign uses are `products`, `orders`, `users` and `category_translations`.

**Option A — regenerate the data from scratch:**
```bash
python backend/database/sample_data.py
```
It must be launched from the **project root** (it uses relative paths like
`backend/database/data_....json`) and creates the `data_*.json` files in
`backend/database/`. Note: it does not use a fixed random seed, so every run
generates slightly different data from the previous one (names, prices, ratings change) —
if "plausible test data" is enough this is fine, if you need to reproduce
exactly a previous run it does not work as it is. It also overwrites the existing
`data_*.json` files, so if you only need the dictionary, copy that file by hand instead.

Then import each file into MongoDB, for example with `mongoimport`:
```bash
mongoimport --db jcoql_test --collection products --file backend/database/data_products.json --jsonArray
mongoimport --db jcoql_test --collection orders --file backend/database/data_orders.json --jsonArray
mongoimport --db jcoql_test --collection users --file backend/database/data_users.json --jsonArray
mongoimport --db jcoql_test --collection category_translations --file backend/database/data_category_translations.json --jsonArray
```
(add `hotels` and `restaurants` the same way if you want them; adapt the array field names/JSON format to the command/tool you prefer — MongoDB Compass is fine too.)

**Option B — you already have a populated MongoDB database:** skip this step, and
connect your database from the UI (sidebar → "➕ Add Database") or
by changing the default connection in `main.py`/`.env`.

**Note on `GET DICTIONARY`/`TRANSLATE`:** this command requires a collection with a
specific structure, `{ "key": "...", "value": "..." }` for each document
(the engine reads exactly these two field names, no others). `category_translations`
above has this structure.

---

## 6. Load the RAG examples into ChromaDB

**Mandatory step, cannot be skipped:** the backend expects the ChromaDB collection
`jcoql_examples` to already exist at start-up (it uses `get_collection`, not
`get_or_create_collection` — if the collection is not there, initialization fails
silently and query generation has no examples to start from).

```bash
python backend/database/load_examples.py
```

It scans **all** the `.txt` files in `examples/validated/` (path
computed relative to the script's location, not to the folder you launch it
from) and recreates the collection from scratch every time you rerun it — safe to
rerun after modifying or adding an examples file.

If you rerun it **with the backend already running**, restart the backend too: otherwise
it stays attached to the reference of the previous collection (closed/replaced in the
meantime) instead of the one just recreated.

---

## 7. Start

The backend and the interface are always needed, each in its own terminal. If you use the
tuned mode or a JCO DS database, start those servers first (steps 8 and 9).

```bash
# Terminal 1 — Backend (from the project root: main.py imports
# modules with paths like "backend.xxx", it must be launched from there)
venv\Scripts\activate
uvicorn main:app --reload

# Terminal 2 — Frontend
cd frontend
npm run dev
```

Open your browser at **http://localhost:5173**.

The backend listens on port 8000. The schema of a database is discovered when the database
is connected and is kept in memory: after a collection is created or deleted, restart the
backend to see the new schema.

---

## 8. Optional: the tuned mode (fine-tuned Llama 3.1)

The tuned mode uses Llama 3.1 8B with a LoRA adapter applied at run time by `llama-server`
(llama.cpp). The adapter is **not** in the repository (see the section "Fine-tuning" of the
README): you need the file `finetune\soup\lora_v4.f16.gguf`, produced by the training and
by `ft_lora_gguf_v4.ps1`.

1. Download the base model with Ollama (`ollama pull llama3.1:8b-instruct-q4_K_M`): the start
   script reads the path of the model file from Ollama.
2. Check the path of `llama-server.exe` at the top of
   `finetune\soup\start_llama_server_v4.ps1` (default `C:\llama-cuda\llama-server.exe`).
3. Free the memory of the graphics card from other models (`ollama ps`, then
   `ollama stop <model-name>`): otherwise part of the model is loaded on the processor and
   the generation is slower.
4. From `finetune\soup`, run `.\start_llama_server_v4.ps1` and wait for the line
   `listening` in the window that opens (port 8081).
5. In the UI set the **Mode** selector to *Tuned* (Llama 3.1 is selected automatically).

If the server is not reachable, the backend answers with an error that says how to start it;
it does not fall back on another model.

---

## 9. Optional: connect a JCO DS database

1. Start your JCO DS server (https://github.com/JcoProjectTeam) and note its host and port
   (the examples in this project use `localhost` and `17017`). With the executables of the
   J-CO project: `java -jar jcoql-ds-server-1.0.0.jar --thin.root=jcoql-ds-server/deps`,
   from the folder of the executables (Java 17).
2. In the UI, sidebar → "➕ Add Database" → Server: "JCO DS (professors' server)".
3. Fill in the internal name, host, port, the database name on JCO DS and the
   **collections, comma-separated**: J-CO-QL+ has no command to list the collections of a
   database, so the interface cannot discover them by itself.
4. Click "✅ Connect". The schema of each listed collection is discovered through the Java
   engine; if the server is stopped, the host/port are wrong or a collection does not
   exist, the connection fails and the reason is in the backend log.

Queries on that database declare the server explicitly, for example:
```
USE DB testds ON SERVER 'jcods' 'http://localhost:17017';
GET COLLECTION testcoll@testds;
```

---

## 10. Check that everything is fine

Quick checklist after the first start:

- [ ] The backend starts without errors in the console (in particular: no errors about ChromaDB/`jcoql_examples` — if you see one, go back to step 6)
- [ ] From the UI, typing a simple natural-language request (e.g. "products with a discount greater than 20%") you get a generated J-CO-QL+ query and results
- [ ] The Dashboard (`/dashboard`) shows connected databases and collections consistent with what you expect
- [ ] If you also use the local models: selecting one from the UI, generation works (otherwise go back to step 4)
- [ ] If you use the tuned mode: with the Mode selector on Tuned, generation works (otherwise go back to step 8)
- [ ] If you connected more than one database: asking for a JOIN between two collections with the same name on different databases (or writing it by hand in the query panel) returns results (not an "Invalid database" error)
- [ ] The "❓ Guide" button opens the quick guide

---

## 11. Debug

The full query sent to the Java engine (prolog + command, `USE DB` included) is
**always** printed in the console, regardless of `JCOQL_DEBUG` — useful to
check at a glance what was actually executed without enabling anything. The rest
of the diagnostic logs (RAG examples retrieved for each request, execution
summary) appears only if explicitly requested:

```bash
set JCOQL_DEBUG=true          # Windows (PowerShell: $env:JCOQL_DEBUG="true")
# export JCOQL_DEBUG=true     # Linux/Mac
```

It is off by default. The application log files (not the debug above) are
always found in `logs/` (created automatically at first start, one file per
session with a timestamp in the name).

---

## 12. Common problems and where to look

| Symptom | Most likely cause |
|---|---|
| Error at start-up about ChromaDB/`jcoql_examples` | Step 6 (`load_examples.py`) not run before the first start |
| "Model not found" or "connection refused" when selecting a local model | Ollama not running, or model not downloaded with the exact tag (step 4) |
| Error about `llama-server` when generating in the tuned mode | `llama-server` not started, or not yet `listening` on port 8081 (step 8) |
| The tuned mode answers slowly | Another model is still loaded in the graphics card by Ollama (`ollama ps`, `ollama stop <model-name>`) |
| A collection just created or deleted does not appear in the schema | The schema is read when the database is connected: restart the backend |
| Generation works but the results are on an unexpected database | Check which database is "current" in the sidebar — it is a state of the process, not per request |
| Generation uses a collection you did not expect (e.g. one named after a previous test) | Leftover collections from earlier `SAVE AS` queries appear in the schema; delete them (`python tests/pulisci_collezioni.py --drop` removes everything in `jcoql_test` except the four base collections) |
| A query on a JCO DS database does not return | Check the DS-Server is running and the collection exists; use the Timeout selector so the wait is bounded |
| File upload/collection management from the UI not available | Feature intentionally disabled in this version (requires architectural work not yet done on the multi-database side) |
| A standalone script (e.g. `test_retrieval.py`, `sample_data.py`) gives `FileNotFoundError` | Almost always a working-directory problem: these scripts use relative paths and must be launched from the project root, not from the folder they are in |

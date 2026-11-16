<#
 run_heldout_altri.ps1 - test held-out (144 richieste, italiano e inglese) sui modelli che non lo hanno.
 Stessa procedura gia' usata per Llama 3.1 base (51/144): ft_eval_cpp.py, prompt compact del backend, un tentativo,
 temperatura 0, nessuna correzione, esito per esecuzione. Cosa si esegue:
   gemini  : italiano + inglese   (API, ~4 s a richiesta con la pausa)
   gemma4  : italiano + inglese   (Ollama gemma4:e4b-it-q4_K_M)
   llama32 : italiano + inglese   (Ollama llama3.2:3b-instruct-q4_K_M)
   llama   : SOLO inglese         (Ollama llama3.1:8b-instruct-q4_K_M; l'italiano c'e' gia': 51/144)
 Gemma 1.7 NON e' inclusa (130 s a richiesta, 0 query valide nella campagna): si aggiunge solo se la vuoi (-Only gemma17).

 Prima di lanciare: MongoDB e backend attivi (localhost:8000), Ollama attivo, llama-server CHIUSO (occupa la GPU).
 Uso, dalla cartella finetune\soup:
   ..\..\venv\Scripts\Activate.ps1   (oppure usa -Py)
   .\run_heldout_altri.ps1 -Only gemini
   .\run_heldout_altri.ps1 -Only gemma4
   .\run_heldout_altri.ps1 -Only llama32
   .\run_heldout_altri.ps1 -Only llama
 Risultati in finetune\soup\heldout_altri\eval_<modello>_<it|en>.csv. Se un CSV esiste gia' il passo viene saltato.
#>
param(
  [Parameter(Mandatory=$true)][ValidateSet("gemini","gemma4","llama32","llama","gemma17")][string]$Only,
  [string]$Py = "..\..\venv\Scripts\python.exe"
)
$ErrorActionPreference = "Stop"
$Here = (Get-Location).Path
$Out = Join-Path $Here "heldout_altri"; New-Item -ItemType Directory -Force -Path $Out | Out-Null
$EvalIt = Join-Path $Here "..\out\eval_heldout_v1.jsonl"
$EvalEn = Join-Path $Here "..\out\eval_heldout_v1_en.jsonl"
$Dbs    = Join-Path $Here "..\out\databases_v1.json"

try { $h = Invoke-RestMethod -Uri "http://127.0.0.1:8000/docs" -TimeoutSec 5 } catch { Write-Warning "Il backend (porta 8000) non risponde: serve per costruire il prompt e eseguire le query." }
try { Invoke-RestMethod -Uri "http://127.0.0.1:8081/health" -TimeoutSec 3 | Out-Null; Write-Warning "llama-server e' ancora acceso sulla porta 8081: chiudilo, occupa la GPU." } catch { }

function Run-Eval([string]$Tag,[string]$Name,[string]$Lang,[string[]]$Extra) {
  $csv = Join-Path $Out ("eval_{0}_{1}.csv" -f $Name,$Lang)
  if (Test-Path $csv) { Write-Host "salto $Name $Lang (esiste gia')" -ForegroundColor Yellow; return }
  $ev = if ($Lang -eq "it") { $EvalIt } else { $EvalEn }
  Write-Host "`n--- $Name / $Lang ---" -ForegroundColor Cyan
  & $Py .\ft_eval_cpp.py --model $Tag --prompt compact --per-family 10 --eval $ev --dbs $Dbs --out $csv @Extra
  if ($LASTEXITCODE -ne 0) { Write-Warning "$Name $Lang : codice di uscita $LASTEXITCODE" }
}

switch ($Only) {
  "gemini"  { Run-Eval "gemini" "gemini" "it" @("--gemini","--pause","4"); Run-Eval "gemini" "gemini" "en" @("--gemini","--pause","4") }
  "gemma4"  { Run-Eval "gemma4:e4b-it-q4_K_M" "gemma4" "it" @(); Run-Eval "gemma4:e4b-it-q4_K_M" "gemma4" "en" @(); ollama stop gemma4:e4b-it-q4_K_M }
  "llama32" { Run-Eval "llama3.2:3b-instruct-q4_K_M" "llama32" "it" @(); Run-Eval "llama3.2:3b-instruct-q4_K_M" "llama32" "en" @(); ollama stop llama3.2:3b-instruct-q4_K_M }
  "llama"   { Run-Eval "llama3.1:8b-instruct-q4_K_M" "llama31" "en" @(); ollama stop llama3.1:8b-instruct-q4_K_M }
  "gemma17" { Run-Eval "gemma:7b-instruct-q4_K_M" "gemma17" "it" @("--timeout","300"); Run-Eval "gemma:7b-instruct-q4_K_M" "gemma17" "en" @("--timeout","300"); ollama stop gemma:7b-instruct-q4_K_M }
}
Write-Host "`nFinito: $Only." -ForegroundColor Green

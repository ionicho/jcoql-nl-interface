# ft_after_v2.ps1 - come ft_after.ps1 ma per il modello v2 (output_v2 -> llama3.1-jcoql-v2). Da finetune\soup con Soup attivo.
# Si lancia da finetune\soup con l'ambiente di Soup attivo:   .\ft_after.ps1
# Ogni passo si ferma se fallisce. Se un passo e' gia' stato fatto (file presenti), viene saltato.
$ErrorActionPreference = "Stop"
$ModelName = "llama3.1-jcoql-v2"                       # il nome inizia con "Llama" come richiede la licenza di Llama 3.1
$BaseOllama = "llama3.1:8b-instruct-q4_K_M"          # da cui si copia TEMPLATE e parametri di stop
$Convert = "C:\Users\nicho\.soup\llama.cpp\convert_hf_to_gguf.py"
$Quant = "C:\llama-bin\llama-quantize.exe"

function Check($what) { if ($LASTEXITCODE -ne 0) { throw "Errore nel passo: $what (codice $LASTEXITCODE)" } }

if (-not (Test-Path ".\output_v2\adapter_model.safetensors")) { throw "Manca .\output_v2\adapter_model.safetensors: l'addestramento e' finito? Sei in finetune\soup?" }
if (-not (Test-Path $Convert)) { throw "Non trovo $Convert" }
if (-not (Test-Path $Quant)) { throw "Non trovo $Quant" }

if (-not (Test-Path ".\merged_v2\config.json")) {
    Write-Host "`n[1/4] Fusione dell'adattatore LoRA nel modello (circa 15 GB, qualche minuto)..." -ForegroundColor Cyan
    soup merge --adapter output_v2 --output .\merged_v2 ; Check "soup merge"
} else { Write-Host "[1/4] merged\ gia' presente, salto." }

if (-not (Test-Path ".\jcoql_v2.f16.gguf")) {
    Write-Host "`n[2/4] Conversione in GGUF f16..." -ForegroundColor Cyan
    $env:PYTHONUTF8 = "1"
    python $Convert .\merged_v2 --outfile .\jcoql_v2.f16.gguf --outtype f16 ; Check "convert_hf_to_gguf"
} else { Write-Host "[2/4] jcoql.f16.gguf gia' presente, salto." }

if (-not (Test-Path ".\jcoql_v2.q4_k_m.gguf")) {
    Write-Host "`n[3/4] Quantizzazione Q4_K_M..." -ForegroundColor Cyan
    & $Quant .\jcoql_v2.f16.gguf .\jcoql_v2.q4_k_m.gguf Q4_K_M ; Check "llama-quantize"
} else { Write-Host "[3/4] jcoql.q4_k_m.gguf gia' presente, salto." }

Write-Host "`n[4/4] Creazione del modello Ollama '$ModelName'..." -ForegroundColor Cyan
$lines = ollama show $BaseOllama --modelfile ; Check "ollama show"
$done = $false
$out = foreach ($l in $lines) {
    if (-not $done -and $l -match '^FROM ') { $done = $true; "FROM ./jcoql_v2.q4_k_m.gguf" } else { $l }
}
if (-not $done) { throw "Nessuna riga FROM nel Modelfile di $BaseOllama" }
[System.IO.File]::WriteAllLines("$PWD\Modelfile_v2", [string[]]$out, (New-Object System.Text.UTF8Encoding $false))
ollama create $ModelName -f Modelfile_v2 ; Check "ollama create"

Write-Host "`nFatto. Modelli Ollama:" -ForegroundColor Green
ollama list
Write-Host "`nSe tutto e' a posto puoi liberare circa 30 GB cancellando: .\merged_v2  e  .\jcoql_v2.f16.gguf  (tieni jcoql_v2.q4_k_m.gguf e output_v2\)."

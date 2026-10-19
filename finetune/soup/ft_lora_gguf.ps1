# ft_lora_gguf.ps1 - NIENTE fusione: l'adattatore LoRA (output_v2) viene convertito in GGUF e applicato da Ollama a runtime
# sopra llama3.1:8b-instruct-q4_K_M. Crea il modello llama3.1-jcoql-v2a. Da finetune\soup, ambiente Soup.
$ErrorActionPreference = "Stop"
$ModelName = "llama3.1-jcoql-v2a"
$BaseOllama = "llama3.1:8b-instruct-q4_K_M"
$LoraConv = "C:\Users\nicho\.soup\llama.cpp\convert_lora_to_gguf.py"
function Check($what) { if ($LASTEXITCODE -ne 0) { throw "Errore nel passo: $what (codice $LASTEXITCODE)" } }
if (-not (Test-Path $LoraConv)) { throw "Non trovo $LoraConv" }
if (-not (Test-Path ".\output_v2\adapter_model.safetensors")) { throw "Manca output_v2\adapter_model.safetensors" }
# config/tokenizer del modello base: li prendo da merged_v2n (hanno gli stessi file del base HF)
if (-not (Test-Path ".\merged_v2n\config.json")) { throw "Manca .\merged_v2n\config.json (serve solo per config e tokenizer)" }
if (-not (Test-Path ".\lora_v2.f16.gguf")) {
    Write-Host "[1/2] Conversione LoRA -> GGUF..." -ForegroundColor Cyan
    $env:PYTHONUTF8 = "1"
    python $LoraConv .\output_v2 --base .\merged_v2n --outfile .\lora_v2.f16.gguf --outtype f16 ; Check "convert_lora_to_gguf"
}
Write-Host "[2/2] ollama create $ModelName" -ForegroundColor Cyan
$lines = ollama show $BaseOllama --modelfile ; Check "ollama show"
$done = $false
$out = foreach ($l in $lines) { $l; if (-not $done -and $l -match '^FROM ') { $done = $true; "ADAPTER ./lora_v2.f16.gguf" } }
if (-not $done) { throw "Nessuna riga FROM" }
[System.IO.File]::WriteAllLines("$PWD\Modelfile_v2a", [string[]]$out, (New-Object System.Text.UTF8Encoding $false))
ollama create $ModelName -f Modelfile_v2a ; Check "ollama create"
ollama list

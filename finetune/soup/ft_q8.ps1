# ft_q8.ps1 - stessi pesi di v2, quantizzazione Q8_0 invece di Q4_K_M, come modello Ollama separato (llama3.1-jcoql-v2-q8).
# Serve .\jcoql_v2.f16.gguf (se l'hai gia' cancellato dillo: si rigenera da .\merged_v2 o da output_v2). Da finetune\soup.
$ErrorActionPreference = "Stop"
$ModelName = "llama3.1-jcoql-v2-q8"
$BaseOllama = "llama3.1:8b-instruct-q4_K_M"
$Quant = "C:\llama-bin\llama-quantize.exe"
function Check($what) { if ($LASTEXITCODE -ne 0) { throw "Errore nel passo: $what (codice $LASTEXITCODE)" } }
if (-not (Test-Path ".\jcoql_v2.f16.gguf")) { throw "Manca .\jcoql_v2.f16.gguf (l'hai cancellato?)" }
if (-not (Test-Path $Quant)) { throw "Non trovo $Quant" }
if (-not (Test-Path ".\jcoql_v2.q8_0.gguf")) {
    Write-Host "Quantizzazione Q8_0..." -ForegroundColor Cyan
    & $Quant .\jcoql_v2.f16.gguf .\jcoql_v2.q8_0.gguf Q8_0 ; Check "llama-quantize"
} else { Write-Host "q8_0 gia' presente, salto." }
$lines = ollama show $BaseOllama --modelfile ; Check "ollama show"
$done = $false
$out = foreach ($l in $lines) {
    if (-not $done -and $l -match '^FROM ') { $done = $true; "FROM ./jcoql_v2.q8_0.gguf" } else { $l }
}
if (-not $done) { throw "Nessuna riga FROM" }
[System.IO.File]::WriteAllLines("$PWD\Modelfile_v2_q8", [string[]]$out, (New-Object System.Text.UTF8Encoding $false))
ollama create $ModelName -f Modelfile_v2_q8 ; Check "ollama create"
Write-Host "Fatto: $ModelName" -ForegroundColor Green
ollama list

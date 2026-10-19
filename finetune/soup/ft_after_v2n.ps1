# ft_after_v2n.ps1 - dopo ft_merge_nf4.py: GGUF f16 -> Q8_0 e Q4_K_M -> modelli Ollama llama3.1-jcoql-v2n-q8 e llama3.1-jcoql-v2n. Da finetune\soup, ambiente Soup.
$ErrorActionPreference = "Stop"
$BaseOllama = "llama3.1:8b-instruct-q4_K_M"
$Convert = "C:\Users\nicho\.soup\llama.cpp\convert_hf_to_gguf.py"
$Quant = "C:\llama-bin\llama-quantize.exe"
function Check($what) { if ($LASTEXITCODE -ne 0) { throw "Errore nel passo: $what (codice $LASTEXITCODE)" } }
if (-not (Test-Path ".\merged_v2n\model.safetensors.index.json")) { throw "Manca .\merged_v2n: lancia prima ft_merge_nf4.py" }
if (-not (Test-Path ".\jcoql_v2n.f16.gguf")) {
    Write-Host "[1/3] GGUF f16..." -ForegroundColor Cyan
    $env:PYTHONUTF8 = "1"
    python $Convert .\merged_v2n --outfile .\jcoql_v2n.f16.gguf --outtype f16 ; Check "convert_hf_to_gguf"
}
foreach ($q in @("Q8_0", "Q4_K_M")) {
    $f = ".\jcoql_v2n.$($q.ToLower()).gguf"
    if (-not (Test-Path $f)) { Write-Host "[2/3] Quantizzazione $q..." -ForegroundColor Cyan; & $Quant .\jcoql_v2n.f16.gguf $f $q ; Check "llama-quantize $q" }
    $name = if ($q -eq "Q8_0") { "llama3.1-jcoql-v2n-q8" } else { "llama3.1-jcoql-v2n" }
    $lines = ollama show $BaseOllama --modelfile ; Check "ollama show"
    $done = $false
    $out = foreach ($l in $lines) { if (-not $done -and $l -match '^FROM ') { $done = $true; "FROM $f" } else { $l } }
    [System.IO.File]::WriteAllLines("$PWD\Modelfile_$name", [string[]]$out, (New-Object System.Text.UTF8Encoding $false))
    Write-Host "[3/3] ollama create $name" -ForegroundColor Cyan
    ollama create $name -f "Modelfile_$name" ; Check "ollama create $name"
}
ollama list
Write-Host "`nSe tutto e' a posto puoi cancellare .\merged_v2n e .\jcoql_v2n.f16.gguf." -ForegroundColor Green

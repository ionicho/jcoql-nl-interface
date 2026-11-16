<#
 run_test_mancanti.ps1 - esegue SOLO i test gia' fatti sugli altri modelli, sui modelli che non li hanno.
 Stessi parametri di prima: test esteso 78 richieste x 1 giro (IT e EN), parafrasi 48 x 1, stabilita' 10 richieste x 50 giri.

 Buchi coperti (Gemini NON manca: 74/78 IT e 73/78 EN sono in extended_riepilogo*.csv):
   v4     : test esteso IT + EN, parafrasi, stabilita'  (Llama 3.1 + LoRA v4; scrive in tests\results\v4\ per non mischiarsi con la v3)
   gemma  : test esteso IT + EN, parafrasi     (Gemma 1.7; ~130 s a risposta: circa 3 h per ogni test da 78. FACOLTATIVO)

 Uso (dalla cartella jcoql-nl-interface, backend su localhost:8000, MongoDB attivo):
   .\tests\run_test_mancanti.ps1 -Only v4
   .\tests\run_test_mancanti.ps1 -Only gemma
 Prima di ogni blocco: pulisce le collezioni residue e ti chiede di riavviare il backend (e llama-server con la LoRA v4 per "v4").
 Riprendibile: gli script saltano le righe gia' scritte. 
#>
param(
  [Parameter(Mandatory=$true)][ValidateSet("v4","v4round","gemma")][string]$Only,
  [string]$Py = ".\venv\Scripts\python.exe"
)
$ErrorActionPreference = "Stop"
$Here = (Get-Location).Path
$env:PYTHONPATH = $Here
$PyExe = Join-Path $Here $Py

# Gli script scrivono i CSV nella cartella indicata da JCOQL_RESULTS_DIR (vedi res() in verify_execution.py).
function Run-Step([string]$Name,[string]$Dir,[string[]]$A) {
  Write-Host "`n--- $Name ---" -ForegroundColor Cyan
  $env:JCOQL_RESULTS_DIR = $Dir
  try { & $PyExe @A; if ($LASTEXITCODE -ne 0) { Write-Warning "${Name}: codice di uscita $LASTEXITCODE" } } finally { Remove-Item Env:JCOQL_RESULTS_DIR -ErrorAction SilentlyContinue }
}
function Script([string]$n) { Join-Path (Join-Path $Here "tests") $n }

Copy-Item test_campaign_log.csv ("test_campaign_log_prima_completa_" + $Only + ".csv") -ErrorAction SilentlyContinue
& $PyExe (Script "pulisci_collezioni.py") --drop

switch ($Only) {
  "v4" {
    Read-Host "Chiudi llama-server v3, avvia start_llama_server_v4.ps1 (porta 8081), riavvia il backend e premi Invio"
    $d = Join-Path $Here "tests\results\v4"; New-Item -ItemType Directory -Force -Path $d | Out-Null
    Run-Step "v4 test esteso IT"  $d @((Script "rerun_extended.py"), "--models", "llama", "--modes", "tuned")
    Run-Step "v4 test esteso EN"  $d @((Script "rerun_english.py"),  "--models", "llama", "--modes", "tuned")
    Run-Step "v4 parafrasi"       $d @((Script "paraphrase.py"),     "--models", "llama", "--tuned")
    Run-Step "v4 stabilita'"      $d @((Script "stability.py"),      "--models", "llama", "--tuned", "--runs", "50")
  }
  "v4round" {
    Read-Host "Controlla che llama-server con la LoRA v4 sia attivo (porta 8081), riavvia il backend e premi Invio"
    for ($i = 0; $i -lt 60; $i++) { try { $h = Invoke-RestMethod -Uri "http://127.0.0.1:8081/health" -TimeoutSec 5; if ($h.status -eq "ok") { $ok = $true; break } } catch { }; Start-Sleep -Seconds 5 }
    if (-not $ok) { throw "llama-server non risponde su 8081" }
    $d = Join-Path $Here "tests\results\v4"; New-Item -ItemType Directory -Force -Path $d | Out-Null
    Run-Step "v4 rifacimento 41 (round 1-3)" $d @((Script "rerun_rounds.py"), "--models", "llama", "--tuned")
  }
  "gemma" {
    Read-Host "Riavvia il backend e premi Invio (Gemma 1.7: ogni risposta ~130 s)"
    $d = Join-Path $Here "tests\results\gemma17"; New-Item -ItemType Directory -Force -Path $d | Out-Null
    Run-Step "Gemma 1.7 test esteso IT" $d @((Script "rerun_extended.py"), "--models", "gemma", "--modes", "compact")
    Run-Step "Gemma 1.7 test esteso EN" $d @((Script "rerun_english.py"),  "--models", "gemma", "--modes", "compact")
    Run-Step "Gemma 1.7 parafrasi"      $d @((Script "paraphrase.py"),     "--models", "gemma")
  }
}
Write-Host "`nFinito: $Only." -ForegroundColor Green

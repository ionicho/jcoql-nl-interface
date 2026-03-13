# Script correzione sintassi JCoQL 4.0 ufficiale
$files = @(
    "jcoql_examples.txt",
    "jcoql_examples_EXTENDED.txt", 
    "jcoql_examples_INRANGE.txt",
    "jcoql_examples_ADVANCED.txt"
)

Write-Host "=" * 60
Write-Host "CORREZIONE SINTASSI JCOQL 4.0 UFFICIALE"
Write-Host "=" * 60
Write-Host ""

foreach ($file in $files) {
    if (Test-Path $file) {
        Write-Host "Processing: $file"
        
        # Leggi contenuto
        $content = Get-Content $file -Raw
        
        # CORREZIONE 1: INRANGE → IN_RANGE
        $before = ([regex]::Matches($content, '\bINRANGE\s+\[')).Count
        $content = $content -replace '\bINRANGE\s+\[', 'IN_RANGE ['
        Write-Host "  - INRANGE → IN_RANGE: $before occorrenze"
        
        # Salva
        $content | Set-Content $file -NoNewline
    }
}

Write-Host ""
Write-Host "=" * 60
Write-Host "CORREZIONE COMPLETATA"
Write-Host "=" * 60
import subprocess
import os
import re
import threading

# FIX CONCORRENZA: il parser Java ufficiale (jco.ql.parser.test.ParserTester,
# jar compilato, non modificabile) legge sempre e solo da un percorso fisso
# relativo (resources/input.file) — non accetta un nome file a scelta.
# Quindi non possiamo usare un file temporaneo univoco per richiesta come si
# farebbe di solito. Per evitare che due richieste concorrenti (es. FastAPI
# che gestisce due utenti insieme) si sovrascrivano a vicenda il file prima
# che Java lo legga, serializziamo scrittura+esecuzione+lettura con un lock:
# le richieste in arrivo mettono in coda invece di correre sullo stesso file.
_validation_lock = threading.Lock()

def validate_with_java_parser(query: str) -> dict:
    base_dir = os.path.dirname(__file__)
    project_root = os.path.abspath(os.path.join(base_dir, '..', '..'))
    resources_dir = os.path.join(project_root, 'resources')
    input_file = os.path.join(resources_dir, 'input.file')
    
    parser_jar = os.path.join(base_dir, "jcoql-parser-official.jar")
    antlr_jar = os.path.join(base_dir, "antlr-3.4-complete.jar")
    
    os.makedirs(resources_dir, exist_ok=True)
    
    # Classpath portabile (Windows: ';', Linux/macOS: ':')
    classpath = os.pathsep.join([parser_jar, antlr_jar])
    
    try:
        # Sezione critica: nessun'altra richiesta può scrivere in input_file
        # o lanciare il parser finché questa non ha letto il suo output.
        with _validation_lock:
            with open(input_file, 'w', encoding='utf-8') as f:
                f.write(query)

            result = subprocess.run(
                [
                    'java',
                    '-cp',
                    classpath,
                    'jco.ql.parser.test.ParserTester'
                ],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=project_root,
                encoding='utf-8'
            )

            output = result.stdout
        
        errors = []
        warnings = []
        
        error_match = re.search(r'Numero di errori:\s*(\d+)', output)
        num_errors = int(error_match.group(1)) if error_match else 0
        
        warning_match = re.search(r'Numero di warning:\s*(\d+)', output)
        num_warnings = int(warning_match.group(1)) if warning_match else 0
        
        for line in output.splitlines():
            if re.match(r'^\d+\.\s+(Syntax Error|Lexical Error)', line):
                errors.append(line.strip())
            elif re.match(r'^\d+\.\s+Warning', line):
                warnings.append(line.strip())

        # Robustezza: se il parser dichiara errori (num_errors > 0) ma il
        # ciclo sopra non ne ha estratto nessuno riga per riga (formato di
        # output inatteso, o un problema transitorio del subprocess), non
        # lasciare 'errors' vuota — altrimenti l'utente vede solo "Query
        # non valida" senza nessun dettaglio, indistinguibile da un bug.
        # Meglio un messaggio meno preciso ma presente.
        if num_errors > 0 and not errors:
            errors.append(
                f"Il parser segnala {num_errors} errore/i ma non è stato possibile "
                f"estrarne il dettaglio dall'output — possibile problema transitorio "
                f"del subprocess Java, riprova. Output grezzo: {output[:300]}"
            )
        
        return {
            'is_valid': num_errors == 0,
            'errors': errors,
            'warnings': warnings,
            'num_errors': num_errors,
            'num_warnings': num_warnings,
            'full_output': output
        }
        
    except subprocess.TimeoutExpired:
        return {
            'is_valid': False,
            'errors': ['Timeout: parser non ha risposto'],
            'warnings': [],
            'num_errors': 1,
            'num_warnings': 0,
            'full_output': ''
        }
    except Exception as e:
        return {
            'is_valid': False,
            'errors': [f'Exception: {str(e)}'],
            'warnings': [],
            'num_errors': 1,
            'num_warnings': 0,
            'full_output': ''
        }
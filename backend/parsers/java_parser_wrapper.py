import subprocess
import os
import re

def validate_with_java_parser(query: str) -> dict:
    base_dir = os.path.dirname(__file__)
    project_root = os.path.abspath(os.path.join(base_dir, '..', '..'))
    resources_dir = os.path.join(project_root, 'resources')
    input_file = os.path.join(resources_dir, 'input.file')
    
    parser_jar = os.path.join(base_dir, "jcoql-parser-official.jar")
    antlr_jar = os.path.join(base_dir, "antlr-3.4-complete.jar")
    
    os.makedirs(resources_dir, exist_ok=True)
    
    with open(input_file, 'w', encoding='utf-8') as f:
        f.write(query)
    
    # Classpath portabile (Windows: ';', Linux/macOS: ':')
    classpath = os.pathsep.join([parser_jar, antlr_jar])
    
    try:
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
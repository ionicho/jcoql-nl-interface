"""
ft_prompt.py - prompt BREVE per il modello addestrato ("tuned").
Un solo posto che definisce il formato: lo usano sia il generatore del dataset (ft_gen.py) sia,
piu' avanti, il backend (modalita' di prompt 'tuned'), cosi' addestramento e uso reale coincidono.
format_schema_compact() e' la STESSA logica di _format_schema_compact in main.py: se la si cambia
li' va cambiata anche qui (e il modello va riaddestrato).
"""

def format_schema_compact(schema: dict) -> str:
    lines = []
    for coll_name, coll_data in (schema or {}).items():
        fields = coll_data.get('fields', {}) if isinstance(coll_data, dict) else {}
        parts = []
        for field_name, info in fields.items():
            types = info.get('types', []) if isinstance(info, dict) else []
            type_str = 'ARRAY' if 'array' in types else ('/'.join(sorted(types)) if types else 'unknown')   # sorted: l'ordine di un set cambia a ogni avvio di Python
            item = f".{field_name}:{type_str}"
            if isinstance(info, dict) and 'string' in types and 'array' not in types:
                ex = [str(e) for e in (info.get('examples') or []) if e is not None]
                if ex and len(ex[0]) <= 24:
                    item += f" (es. '{ex[0]}')"
            parts.append(item)
        lines.append(f"{coll_name}: " + ", ".join(parts))
    return "\n".join(lines)


def build_tuned_prompt(db_name: str, schema: dict, nl_query: str) -> str:
    collections_str = ", ".join(schema.keys()) if schema else "nessuna"
    return (
        "Traduci la richiesta in una query JCoQL+ per MongoDB. Rispondi SOLO con la query.\n"
        f"DATABASE CORRENTE: {db_name}\n"
        f"COLLEZIONI DISPONIBILI: {collections_str}\n"
        f"SCHEMA (una riga per collezione):\n{format_schema_compact(schema)}\n"
        f"RICHIESTA: \"{nl_query}\"\n"
    )

"""Script principal para procesar SQL y generar esquemas"""
import logging
from pathlib import Path
from cortex_repo_manager import CortexRepoManager
from schema_extractor import process_schema
from qa_processor import JsonSchemaValidator
import json
import os

def main():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    try:
        # Inicializar el gestor de Cortex
        cortex = CortexRepoManager()
        cortex.generate_sql_code()

        # Configurar directorios para QA
        validated_dir = Path(os.getenv('VALIDATED_SCHEMAS_DIR', '/app/validated_schemas'))
        qa_output_dir = Path(os.getenv('QA_OUTPUT_DIR', '/app/qa_results'))
        qa_output_dir.mkdir(parents=True, exist_ok=True)

        # Inicializar validador de esquemas
        schema_validator = JsonSchemaValidator(validated_dir, cortex.output_dir)

        # Procesar cada módulo
        for module in cortex.cortex_modules:
            sql_dir = cortex.workspace_dir / "sql" / str(module)
            
            # Usar directorio data_dict para los esquemas
            schema_dir = cortex.output_dir / "data_dict"
            schema_dir.mkdir(parents=True, exist_ok=True)

            # Procesar cada archivo SQL
            for sql_file in sql_dir.glob("*.sql"):
                try:
                    # Leer contenido SQL
                    with open(sql_file, 'r', encoding='utf-8') as f:
                        sql_content = f.read()

                    # Procesar esquema usando Gemini
                    schema = process_schema(sql_content, sql_file.name)

                    # Guardar esquema generado con el mismo nombre que el SQL pero con extensión .json
                    schema_file = schema_dir / f"{sql_file.stem}.json"
                    with open(schema_file, 'w', encoding='utf-8') as f:
                        json.dump(schema, f, indent=4, ensure_ascii=False)

                    logger.info(f"Esquema generado: {schema_file.name}")

                except Exception as e:
                    logger.error(f"Error procesando {sql_file}: {str(e)}")
                    continue

        # Ejecutar validación de QA
        qa_results = schema_validator.validate_schemas()
        
        # Guardar resultados de QA
        qa_summary_file = qa_output_dir / "qa_summary.json"
        with open(qa_summary_file, 'w') as f:
            json.dump({
                'results': qa_results,
                'summary': {
                    'total_schemas': len(qa_results),
                    'passed': sum(1 for r in qa_results.values() if r.get('passed', False)),
                    'failed': sum(1 for r in qa_results.values() if not r.get('passed', False))
                }
            }, f, indent=4)

        logger.info(f"Resultados de QA guardados en: {qa_summary_file}")

    except Exception as e:
        logger.error(f"Error en el procesamiento: {str(e)}")

if __name__ == "__main__":
    main()
"""Script principal para procesar SQL y generar esquemas"""
import logging
from cortex_repo_manager import CortexRepoManager
from schema_extractor import process_schema
import json

def main():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    try:
        # Inicializar el gestor de Cortex
        cortex = CortexRepoManager()
        cortex.generate_sql_code()

        # Usar propiedades del gestor para obtener directorios y módulos
        for module in cortex.cortex_modules:
            sql_dir = cortex.workspace_dir / "sql" / str(module)
            schema_dir = cortex.output_dir / str(module)
            schema_dir.mkdir(parents=True, exist_ok=True)

            # Procesar cada archivo SQL en el módulo
            for sql_file in sql_dir.glob("*.sql"):
                try:
                    # Leer contenido SQL
                    with open(sql_file, 'r', encoding='utf-8') as f:
                        sql_content = f.read()

                    # Procesar esquema usando Gemini
                    schema = process_schema(sql_content, sql_file.name)

                    # Guardar esquema en archivo JSON
                    schema_file = schema_dir / f"{sql_file.stem}.json"
                    with open(schema_file, 'w', encoding='utf-8') as f:
                        json.dump(schema, f, indent=4, ensure_ascii=False)

                    logger.info(f"Esquema generado: {schema_file.name}")

                except Exception as e:
                    logger.error(f"Error procesando {sql_file}: {str(e)}")
                    continue

        logger.info("Procesamiento completado exitosamente")

    except Exception as e:
        logger.error(f"Error en el procesamiento: {str(e)}")

if __name__ == "__main__":
    main()
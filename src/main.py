"""Script principal para procesar SQL y generar esquemas"""
import logging
import os
import shutil
from pathlib import Path
from cortex_repo_manager import CortexRepoManager
from schema_extractor import extract_schema
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def clean_directory(directory: Path):
    """Limpia el contenido de un directorio sin eliminar el directorio en sí"""
    for item in directory.iterdir():
        if item.is_file():
            item.unlink()
        elif item.is_dir():
            shutil.rmtree(item)

def main():
    try:
        # Usar variables de entorno o valores por defecto
        workspace_dir = os.getenv("WORKSPACE_DIR", "/app/workspace")
        sql_flavor = os.getenv("SQL_FLAVOR", "s4")

        # Limpiar contenido del workspace si existe
        workspace_path = Path(workspace_dir)
        if workspace_path.exists():
            logger.info("Limpiando contenido del workspace existente...")
            clean_directory(workspace_path)
        else:
            workspace_path.mkdir(parents=True, exist_ok=True)

        # Inicializar gestor de Cortex
        manager = CortexRepoManager(
            workspace_dir=workspace_dir,
            sql_flavor=sql_flavor
        )

        # Clonar repositorio de Cortex
        logger.info("Clonando repositorio de Cortex Framework...")
        
        try:
            import git
            repo = git.Repo.clone_from(
                manager.CORTEX_REPO_URL,
                workspace_dir,
                depth=1  # Clonar solo el último commit para ahorrar espacio
            )
            logger.info("Repositorio clonado exitosamente")
        except Exception as e:
            logger.error(f"Error clonando repositorio: {str(e)}")
            return 1

        # Procesar templates SQL
        manager.process_sql_templates()

        # Generar esquemas
        sql_dir = manager.sql_dir / "operational"
        schema_dir = Path(os.getenv("OUTPUT_DIR", "/app/schemas")) / "operational"
        schema_dir.mkdir(parents=True, exist_ok=True)

        for sql_file in sql_dir.glob("*.sql"):
            try:
                # Leer SQL
                with open(sql_file, 'r', encoding='utf-8') as f:
                    sql_content = f.read()

                # Extraer esquema
                schema = extract_schema(
                    sql_content=sql_content, 
                    table_name=sql_file.stem,
                    sql_file=str(sql_file)  # Agregamos el path del archivo
                )

                # Guardar esquema
                schema_file = schema_dir / f"{sql_file.stem}.json"
                with open(schema_file, 'w', encoding='utf-8') as f:
                    json.dump(schema, f, indent=2)

                logger.info(f"Esquema generado: {schema_file.name}")

            except Exception as e:
                logger.error(f"Error procesando {sql_file}: {str(e)}")
                continue

        logger.info("Procesamiento completado exitosamente")

    except Exception as e:
        logger.error(f"Error en el procesamiento: {str(e)}")
        return 1

    return 0

if __name__ == "__main__":
    exit(main())
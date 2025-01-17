import json
import re
import logging
import os

logger = logging.getLogger(__name__)

def create_output_json(schema_info, columns):
    """Crea la estructura JSON de salida."""
    return {
        "schema": {
            "object_name": schema_info["object_name"],
            "object_type": schema_info["object_type"],
            "description": schema_info["description"],
            "source": schema_info["source"],
            "group_by": schema_info["group_by"],
            "dependencies": schema_info["dependencies"],
            "columns": columns
        }
    }

def process_full_response(content):
    """Procesa el contenido de error_schema.json para convertirlo en un JSON válido."""
    try:
        # Parsear el JSON
        json_data = json.loads(content)
        
        # Validar y corregir las columnas
        schema = json_data.get('schema', {})
        columns = schema.get('columns', [])
        
        # Crear el JSON de salida
        output_json = create_output_json({
            "object_name": schema.get('object_name', 'unknown'),
            "object_type": schema.get('object_type', 'unknown'),
            "description": schema.get('description', 'unknown'),
            "source": schema.get('source', 'unknown'),
            "group_by": schema.get('group_by', []),
            "dependencies": schema.get('dependencies', [])
        }, columns)
        
        return output_json

    except json.JSONDecodeError as e:
        logger.error("Error al decodificar JSON: %s", e)
        logger.error("Contenido original del JSON: %s", content)
        raise
    except Exception as e:
        logger.error("Error al procesar el archivo: %s", e)
        logger.error("Contenido original del JSON: %s", content)
        raise 

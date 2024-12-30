"""Módulo para extraer esquemas de SQL usando Gemini"""
from typing import Dict, Optional, Tuple
import logging
import os
from pathlib import Path
from pydantic import BaseModel
from litellm import completion
import json
import time
from datetime import datetime

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
RETRY_DELAY = 2  # segundos entre reintentos
FAILED_SCHEMAS_FILE = "failed_schemas.json"

class FailedSchema(BaseModel):
    table_name: str
    error: str
    timestamp: str
    sql_file: str
    attempts: int
    gemini_response: str = ""
    last_attempt_response: str = ""

class Column(BaseModel):
    name: str
    type: str 
    description: str
    dependencies: list[str] = []
    formula: str = ""

class TableSchema(BaseModel):
    table_name: str
    description: str
    source: str = "cortex_framework"
    columns: list[Column]
    dependencies: list[str] = []

def load_prompt_template() -> str:
    """Carga el template del prompt desde el archivo"""
    prompt_path = Path(__file__).parent / "gemini_schema_extractor_prompt.txt"
    with open(prompt_path, 'r', encoding='utf-8') as f:
        return f.read()

def load_failed_schemas() -> Dict:
    """Carga el registro de esquemas fallidos"""
    failed_file = Path(os.getenv("OUTPUT_DIR", "/app/schemas")) / FAILED_SCHEMAS_FILE
    if failed_file.exists():
        with open(failed_file, 'r') as f:
            return json.load(f)
    return {"failed_schemas": []}

def save_failed_schema(table_name: str, error: str, sql_file: str, attempts: int, 
                      gemini_response: str = "", last_attempt_response: str = ""):
    """Guarda un registro de esquema fallido"""
    failed_file = Path(os.getenv("OUTPUT_DIR", "/app/schemas")) / FAILED_SCHEMAS_FILE
    
    # Cargar registros existentes
    if failed_file.exists():
        with open(failed_file, 'r') as f:
            failed_schemas = json.load(f)
    else:
        failed_schemas = {"failed_schemas": []}
    
    # Agregar nuevo registro
    failed_schema = FailedSchema(
        table_name=table_name,
        error=error,
        timestamp=datetime.now().isoformat(),
        sql_file=sql_file,
        attempts=attempts,
        gemini_response=gemini_response,
        last_attempt_response=last_attempt_response
    )
    
    # Actualizar o agregar registro
    updated = False
    for i, schema in enumerate(failed_schemas["failed_schemas"]):
        if schema["table_name"] == table_name:
            failed_schemas["failed_schemas"][i] = failed_schema.dict()
            updated = True
            break
    
    if not updated:
        failed_schemas["failed_schemas"].append(failed_schema.dict())
    
    # Guardar archivo actualizado
    with open(failed_file, 'w') as f:
        json.dump(failed_schemas, f, indent=2, ensure_ascii=False)

def call_gemini(messages: list, api_key: str) -> Tuple[Optional[Dict], Optional[str], str]:
    """Llama a Gemini con manejo de streaming"""
    try:
        # Configuración inicial
        full_content = ""
        chunks = []

        # Configurar LiteLLM para manejar parámetros no soportados
        import litellm
        litellm.drop_params = True

        # Llamada con streaming según documentación de LiteLLM
        response = completion(
            model="gemini/gemini-1.0-pro", 
            messages=messages,
            api_key=api_key,
            temperature=0,
            max_tokens=30000,
            stream=True,
            top_p=1
        )

        # Procesar la respuesta en streaming
        try:
            for chunk in response:
                if hasattr(chunk.choices[0], 'delta') and hasattr(chunk.choices[0].delta, 'content'):
                    content = chunk.choices[0].delta.content
                    if content:
                        chunks.append(chunk)
                        full_content += content

            # Usar el helper de LiteLLM para reconstruir la respuesta
            complete_response = litellm.stream_chunk_builder(chunks, messages=messages)
            
            # Verificar si necesitamos más contenido
            if '<json>' in full_content and not '</json>' in full_content:
                logger.warning("Respuesta incompleta - iniciando continuación")
                
                # Preparar contexto para continuación
                continuation_messages = messages.copy()
                continuation_messages.append({
                    "role": "assistant",
                    "content": full_content
                })
                continuation_messages.append({
                    "role": "user",
                    "content": "La respuesta está incompleta. Por favor, continúa exactamente desde donde te quedaste, manteniendo el formato JSON y asegurándote de cerrar la etiqueta </json>."
                })

                # Llamada de continuación
                continuation_response = completion(
                    model="gemini/gemini-1.0-pro",
                    messages=continuation_messages,
                    api_key=api_key,
                    temperature=0,
                    max_tokens=30000,
                    stream=True,
                    top_p=1
                )

                continuation_chunks = []
                for chunk in continuation_response:
                    if hasattr(chunk.choices[0], 'delta') and hasattr(chunk.choices[0].delta, 'content'):
                        content = chunk.choices[0].delta.content
                        if content:
                            continuation_chunks.append(chunk)
                            full_content += content

                # Combinar las respuestas
                complete_response = litellm.stream_chunk_builder(chunks + continuation_chunks, messages=messages)

        except Exception as streaming_error:
            logger.error(f"Error durante streaming: {streaming_error}")
            raise

        # Extraer y validar el JSON
        json_str = extract_json_from_content(full_content)
        
        if not json_str:
            raise ValueError("No se pudo extraer JSON válido de la respuesta")

        # Parsear y validar el JSON
        schema_dict = parse_and_validate_json(json_str)
        
        return schema_dict, None, full_content

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error en llamada a Gemini: {error_msg}")
        return None, error_msg, full_content

def extract_json_from_content(content: str) -> str:
    """Extrae el JSON válido del contenido de la respuesta"""
    # Primero buscar entre tags
    json_tags = [
        ('<json>', '</json>'),
        ('<json_output>', '</json_output>')
    ]
    
    for start_tag, end_tag in json_tags:
        start_idx = content.find(start_tag)
        if start_idx != -1:
            start_idx += len(start_tag)
            end_idx = content.find(end_tag)
            if end_idx != -1:
                return content[start_idx:end_idx].strip()
    
    # Si no hay tags, buscar el JSON más externo
    start_idx = content.find('{')
    if start_idx != -1:
        # Contar llaves para encontrar el JSON completo
        count = 0
        in_string = False
        escape_char = False
        
        for i, char in enumerate(content[start_idx:], start_idx):
            if char == '\\' and not escape_char:
                escape_char = True
                continue
            if char == '"' and not escape_char:
                in_string = not in_string
            if not in_string:
                if char == '{':
                    count += 1
                elif char == '}':
                    count -= 1
                    if count == 0:
                        return content[start_idx:i+1]
            escape_char = False
    
    return content.strip()

def parse_and_validate_json(json_str: str) -> Dict:
    """Parsea y valida la estructura del JSON"""
    try:
        schema_dict = json.loads(json_str)
    except json.JSONDecodeError:
        # Intentar limpiar el JSON
        json_str = cleanup_json_string(json_str)
        schema_dict = json.loads(json_str)
    
    # Validar estructura
    if "schema" not in schema_dict:
        raise ValueError("JSON no contiene el objeto 'schema'")
        
    schema = schema_dict["schema"]
    required_keys = ["object_name", "object_type", "description", "source", "columns", "dependencies"]
    if not all(key in schema for key in required_keys):
        raise ValueError("JSON no contiene todos los campos requeridos")
        
    for col in schema["columns"]:
        required_col_keys = ["name", "dependencies", "formula", "description"]
        if not all(key in col for key in required_col_keys):
            raise ValueError(f"Columna {col.get('name', 'unknown')} no contiene todos los campos requeridos")
    
    return schema_dict

def cleanup_json_string(json_str: str) -> str:
    """Limpia una cadena JSON malformada"""
    # Eliminar caracteres no válidos al inicio/fin
    json_str = json_str.strip()
    
    # Asegurarse que empiece y termine con llaves
    if not json_str.startswith('{'):
        json_str = '{' + json_str
    if not json_str.endswith('}'):
        json_str = json_str + '}'
        
    # Eliminar comas extra al final de listas/objetos
    json_str = json_str.replace(',}', '}')
    json_str = json_str.replace(',]', ']')
    
    return json_str

def extract_schema(sql_content: str, table_name: str, sql_file: str = "") -> Dict:
    """Extrae el esquema de una consulta SQL usando Gemini"""
    try:
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            logger.error("GOOGLE_API_KEY no está configurada")
            raise ValueError("GOOGLE_API_KEY no está configurada")

        prompt_template = load_prompt_template()
        prompt = prompt_template.replace("{{SQL_CODE}}", sql_content)
        prompt = prompt.replace("{{FILE_NAME}}", table_name)

        messages = [
            {
                "role": "system",
                "content": "You are a SQL expert that extracts table schemas from SQL code. Follow the instructions carefully and return only valid JSON."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]

        schema_dict, error, gemini_response = call_gemini(messages, api_key)
        
        if schema_dict:
            return schema_dict
        else:
            logger.error(f"No se pudo obtener un esquema válido")
            
            # Registrar el fallo con la respuesta de Gemini
            save_failed_schema(
                table_name=table_name,
                error=error or "Error desconocido",
                sql_file=sql_file,
                attempts=1,
                gemini_response=gemini_response,
                last_attempt_response=gemini_response
            )
            
            return {
                "schema": {
                    "object_name": table_name,
                    "object_type": "unknown",
                    "description": f"Error al procesar: {error}",
                    "source": "cortex_framework",
                    "columns": [],
                    "dependencies": []
                }
            }

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error extrayendo esquema con Gemini: {error_msg}")
        
        # Registrar el fallo sin respuesta de Gemini
        save_failed_schema(
            table_name=table_name,
            error=error_msg,
            sql_file=sql_file,
            attempts=1,
            gemini_response="Error antes de obtener respuesta"
        )
        
        return {
            "schema": {
                "object_name": table_name,
                "object_type": "unknown",
                "description": "",
                "source": "cortex_framework",
                "columns": [],
                "dependencies": []
            }
        }
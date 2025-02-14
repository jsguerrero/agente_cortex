"""Módulo para extraer esquemas de SQL usando Gemini"""
from typing import Dict
import logging
import os
from pathlib import Path
from pydantic import BaseModel
from litellm import completion
from json_processor import process_full_response
import time
import json

logger = logging.getLogger(__name__)

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

def load_prompt_template(prompt_type: str) -> str:
    """Carga el template del prompt desde el archivo"""
    prompt_path = Path(__file__).parent / "prompts" / f"gemini_{prompt_type}_prompt.txt"
    with open(prompt_path, 'r', encoding='utf-8') as f:
        return f.read()

def call_gemini(sql_code: str, prompt: str, continue_prompt: str, sql_file_name: str) -> str:
    """Llama a Gemini usando el proxy de LiteLLM con reintentos en caso de error"""
    max_retries = 3
    retry_count = 0
    retry_delay = 10  # segundos

    while retry_count < max_retries:
        try:
            full_content = ""
            current_prompt = prompt.replace("{{SQL_CODE}}", sql_code).replace("{{FILE_NAME}}", sql_file_name)
            is_first_response = True
            reached_length_limit = False

            while True:
                response = completion(
                    model="gemini/gemini-1.5-flash",
                    messages=[{"role": "user", "content": current_prompt}],
                    api_key=os.getenv("GEMINI_API_KEY"),
                    response_format={"type": "json_object"},
                    temperature=0.0
                )

                response_content = response.get('choices', [{}])[0].get('message', {}).get('content')
                
                # Modificar el inicio de las respuestas continuas
                if not is_first_response:
                    response_content = response_content.replace('[{"name":', ',{"name":', 1)
                
                full_content += response_content
                finish_reason = response.get('choices', [{}])[0].get('finish_reason', {})

                if finish_reason == "length":
                    logger.warning("Se alcanzó el límite de tokens")
                    last_column_index = full_content.rfind('},')
                    if last_column_index != -1:
                        last_chunk = full_content[:last_column_index + 1]
                        last_column_name_index = last_chunk.rfind('"name":')
                        if last_column_name_index != -1:
                            last_column_name = last_chunk[last_column_name_index:].split('"')[3]
                            full_content = full_content[:last_column_index + 1] 
                            logger.info(f"Continua el mapeo a partir de la columna {last_column_name}")
                        else:
                            logger.warning("No se pudo determinar la última columna completa.")
                    else:
                        logger.warning("No se pudo determinar la última columna completa.")
                    
                    current_prompt = continue_prompt.replace("{{SQL_CODE}}", sql_code).replace("{{FILE_NAME}}", sql_file_name).replace("{{START_COLUMN}}", last_column_name)
                    is_first_response = False
                    reached_length_limit = True
                elif finish_reason == "stop":
                    if reached_length_limit:
                        # Agregar caracteres de cierre a la última respuesta
                        full_content += '}}'
                    # logger.info(f"Full response:\n{full_content}")
                    break

            # logger.info(f"Full response:\n{full_content}")
            return full_content

        except Exception as e:
            logger.error(f"Error en la llamada a Gemini: {str(e)}")
            if "503" in str(e):
                retry_count += 1
                logger.warning(f"Reintentando en {retry_delay} segundos... (Intento {retry_count} de {max_retries})")
                time.sleep(retry_delay)
            else:
                break

    logger.error("Se alcanzó el número máximo de reintentos. Abortando.")
    return ""

def call_gemini_for_joins(sql_code: str, sql_file_name: str) -> str:
    """Llama a Gemini para obtener información sobre los joins en el SQL"""
    try:
        join_prompt = load_prompt_template("join_extractor")
        current_prompt = join_prompt.replace("{{SQL_CODE}}", sql_code).replace("{{FILE_NAME}}", sql_file_name)
        
        response = completion(
            model="gemini/gemini-1.5-flash",
            messages=[{"role": "user", "content": current_prompt}],
            api_key=os.getenv("GEMINI_API_KEY"),
            response_format={"type": "json_object"},
            temperature=0.0
        )

        response_content = response.get('choices', [{}])[0].get('message', {}).get('content')
        return response_content

    except Exception as e:
        logger.error(f"Error en la llamada a Gemini para joins: {str(e)}")
        return ""

def process_schema(sql_code: str, sql_file_name: str) -> dict:
    """Procesa el esquema de un archivo SQL"""
    # Verificar si existe un esquema validado
    validated_schema = check_validated_schema(sql_file_name)
    
    prompt = load_prompt_template("schema_extractor")
    continue_prompt = load_prompt_template("continue_schema_extractor")
    
    # Si existe un esquema validado, agregarlo al contexto del prompt
    if validated_schema:
        prompt = enrich_prompt_with_validation(prompt, validated_schema)
        continue_prompt = enrich_prompt_with_validation(continue_prompt, validated_schema)
    
    full_response = call_gemini(sql_code, prompt, continue_prompt, sql_file_name)
    
    # Procesar el esquema principal
    schema = process_full_response(full_response)
    
    # Agregar campos de validación al esquema y a cada columna
    if 'schema' in schema:
        schema['schema']['is_valid'] = None
        
        # Agregar is_valid a cada columna y copiar validaciones previas
        for column in schema['schema'].get('columns', []):
            column['is_valid'] = None
            # Asegurar que cada atributo tenga is_valid
            for attr in ['name', 'dependencies', 'formula', 'description']:
                if isinstance(column[attr], dict):
                    if 'is_valid' not in column[attr]:
                        column[attr]['is_valid'] = None
                else:
                    # Convertir el valor simple a estructura con is_valid
                    value = column[attr]
                    column[attr] = {
                        'value': value,
                        'is_valid': None
                    }
            
            # Si existe un esquema validado, copiar el estado de validación
            if validated_schema:
                for validated_column in validated_schema['schema'].get('columns', []):
                    if column['name']['value'] == validated_column['name']['value']:
                        column['is_valid'] = validated_column.get('is_valid')
                        # Copiar atributos validados
                        for attr in ['dependencies', 'formula', 'description']:
                            if validated_column[attr].get('is_valid'):
                                column[attr] = validated_column[attr]
                        break
    
    # Obtener información sobre los joins
    joins_response = call_gemini_for_joins(sql_code, sql_file_name)
    try:
        joins_data = json.loads(joins_response)
        schema['schema']['joins'] = joins_data.get('joins', [])
    except json.JSONDecodeError as e:
        logger.error("Error al decodificar JSON de joins: %s", e)
    
    return schema

def check_validated_schema(sql_file_name: str) -> dict:
    """Verifica si existe un esquema validado para el archivo SQL"""
    validated_dir = Path(os.getenv('VALIDATED_SCHEMAS_DIR', '/app/validated_schemas'))
    validated_file = validated_dir / f"{sql_file_name.replace('.sql', '_dict.json')}"
    
    if validated_file.exists():
        try:
            with open(validated_file, 'r', encoding='utf-8') as f:
                validated_schema = json.load(f)
                logger.info(f"Esquema validado encontrado para {sql_file_name}")
                return validated_schema
        except Exception as e:
            logger.error(f"Error leyendo esquema validado {validated_file}: {str(e)}")
    return None

def enrich_prompt_with_validation(prompt: str, validated_schema: dict) -> str:
    """Enriquece el prompt con información del esquema validado"""
    validation_context = "\nValidated Schema Context:\n"
    
    for column in validated_schema['schema'].get('columns', []):
        if column.get('is_valid') is not None:
            validation_context += (
                f"- Column '{column['name']}' "
                f"({'valid' if column['is_valid'] else 'invalid'}): "
                f"dependencies={column.get('dependencies', [])}, "
                f"formula='{column.get('formula', '')}'\n"
            )
    
    return prompt.replace("{{VALIDATION_CONTEXT}}", validation_context)

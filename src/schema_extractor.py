"""Módulo para extraer esquemas de SQL usando Gemini"""
from typing import Dict
import logging
import os
from pathlib import Path
from pydantic import BaseModel
from litellm import completion
from json_processor import process_full_response
import time

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
    prompt_path = Path(__file__).parent / f"gemini_{prompt_type}_prompt.txt"
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

def process_schema(sql_code: str, sql_file_name: str) -> dict:
    """Procesa el esquema de un archivo SQL"""
    prompt = load_prompt_template("schema_extractor")
    continue_prompt = load_prompt_template("continue_schema_extractor")
    full_response = call_gemini(sql_code, prompt, continue_prompt, sql_file_name)
    return process_full_response(full_response)

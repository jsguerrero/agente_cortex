from flask import Flask, request, jsonify, render_template_string
import json
from pathlib import Path
import os
import logging
import datetime
import shutil

app = Flask(__name__)
logger = logging.getLogger(__name__)

# Directorio para esquemas validados
VALIDATED_DIR = Path(os.getenv('VALIDATED_SCHEMAS_DIR', '/app/validated_schemas'))
# Directorio para esquemas generados
OUTPUT_DIR = Path(os.getenv('OUTPUT_DIR', '/app/schemas')) / 'data_dict'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Template HTML para la interfaz
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Validación de Diccionarios de Datos</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .schema-list { list-style-type: none; padding: 0; }
        .schema-item { margin: 10px 0; padding: 10px; border: 1px solid #ddd; }
    </style>
</head>
<body>
    <h1>Validación de Diccionarios de Datos</h1>
    <p>Formato esperado: {{ expected_format }}</p>
    
    <div class="schema-list">
    {% for schema in schemas %}
        <div class="schema-item">
            <h3>{{ schema.name }}</h3>
            <a href="/review/{{ schema.name }}">Revisar</a>
        </div>
    {% endfor %}
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    try:
        # Obtener todos los archivos JSON
        json_files = [f for f in OUTPUT_DIR.glob('*.json')]
        
        # Ordenar archivos alfabéticamente
        json_files.sort(key=lambda x: x.name)

        # Leer el contenido de cada archivo
        schemas = []
        for json_file in json_files:
            try:
                with open(json_file, 'r') as f:
                    content = json.load(f)
                    schemas.append({
                        'name': json_file.name,
                        'content': content
                    })
            except Exception as e:
                logger.error(f"Error leyendo {json_file}: {str(e)}")

        return render_template_string(HTML_TEMPLATE, 
            schemas=schemas,
            expected_format="table_name.json"
        )

    except Exception as e:
        logger.error(f"Error en index: {str(e)}")
        return str(e), 500

@app.route('/review/<path:schema_name>')
def review_schema(schema_name):
    """Muestra la interfaz de validación para un esquema específico"""
    try:
        schema_path = OUTPUT_DIR / schema_name
        if not schema_path.exists():
            return "Esquema no encontrado", 404

        with open(schema_path, 'r') as f:
            schema_content = json.load(f)

        # Preparar el esquema para la validación
        if 'schema' in schema_content:
            fields = schema_content['schema'].get('columns', [])
            if 'validation' not in schema_content['schema']:
                schema_content['schema']['validation'] = {
                    'is_valid': None,
                    'comments': '',
                    'validation_timestamp': None
                }
        else:
            fields = schema_content.get('fields', [])
            if 'validation' not in schema_content:
                schema_content['validation'] = {
                    'is_valid': None,
                    'comments': '',
                    'validation_timestamp': None
                }

        return render_template_string("""
            <h1>Validación de {{ schema_name }}</h1>
            <form id="validationForm">
                <table border="1">
                    <tr>
                        <th>Campo</th>
                        <th>Descripción</th>
                        <th>Validación</th>
                    </tr>
                    {% for field in fields %}
                    <tr>
                        <td>{{ field.name }}</td>
                        <td>{{ field.description }}</td>
                        <td>
                            <select name="validation_{{ field.name }}">
                                <option value="">Pendiente</option>
                                <option value="valid" {% if field.is_validated == True %}selected{% endif %}>Válido</option>
                                <option value="invalid" {% if field.is_validated == False %}selected{% endif %}>Inválido</option>
                            </select>
                        </td>
                    </tr>
                    {% endfor %}
                </table>
                <br>
                <textarea name="comments" rows="4" cols="50" placeholder="Comentarios generales">{{ schema_content.get('validation', {}).get('comments', '') if 'schema' not in schema_content else schema_content['schema'].get('validation', {}).get('comments', '') }}</textarea>
                <br>
                <button type="submit">Guardar validación</button>
            </form>
            <script>
                document.getElementById('validationForm').onsubmit = function(e) {
                    e.preventDefault();
                    
                    var formData = new FormData();
                    formData.append('schema_name', '{{ schema_name }}');
                    formData.append('comments', document.querySelector('textarea[name="comments"]').value);
                    
                    fetch('/validate/{{ schema_name }}', {
                        method: 'POST',
                        body: formData
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.status === 'success') {
                            alert('Validación guardada correctamente');
                            window.location.reload();
                        } else {
                            alert('Error: ' + data.error);
                        }
                    })
                    .catch(error => {
                        console.error('Error:', error);
                        alert('Error al guardar la validación');
                    });
                };
            </script>
        """, schema_name=schema_name, fields=fields, schema_content=schema_content)

    except Exception as e:
        logger.error(f"Error en review_schema: {str(e)}")
        return str(e), 500

@app.route('/validate/<path:schema_name>', methods=['POST'])
def validate_schema(schema_name):
    """Procesa la validación de un esquema"""
    is_valid = request.form.get('is_valid') == 'true'
    comments = request.form.get('comments', '')
    
    try:
        # Actualizar el JSON original con los campos de validación
        source_file = OUTPUT_DIR / schema_name
        with open(source_file, 'r') as f:
            schema_content = json.load(f)
        
        # Agregar o actualizar campos de validación
        if 'validation' not in schema_content:
            schema_content['validation'] = {}
        
        schema_content['validation'].update({
            'is_valid': is_valid,
            'comments': comments,
            'validation_timestamp': datetime.datetime.now().isoformat()
        })
        
        # Guardar el JSON actualizado
        with open(source_file, 'w') as f:
            json.dump(schema_content, f, indent=2)
        
        # Si es válido, copiar a validated_schemas
        if is_valid:
            # Crear el directorio de destino si no existe
            validated_path = VALIDATED_DIR / schema_name
            validated_dir = validated_path.parent
            validated_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, validated_path)
        
        return jsonify({
            "status": "success",
            "message": "Validación guardada correctamente"
        })
    
    except Exception as e:
        logger.error(f"Error en validación: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/validate-field/<path:schema_name>/<field_name>', methods=['POST'])
def validate_field(schema_name, field_name):
    """Procesa la validación de un campo específico"""
    is_valid = request.form.get('is_valid') == 'true'
    
    try:
        source_file = OUTPUT_DIR / schema_name
        with open(source_file, 'r') as f:
            schema_content = json.load(f)
        
        # Actualizar el campo específico
        for field in schema_content.get('fields', []):
            if field['name'] == field_name:
                field['is_validated'] = is_valid
                break
        
        # Guardar el JSON actualizado
        with open(source_file, 'w') as f:
            json.dump(schema_content, f, indent=2)
        
        # Verificar si todos los campos están validados
        all_fields_validated = all(
            field.get('is_validated') is not None 
            for field in schema_content.get('fields', [])
        )
        
        # Si todos los campos están validados, actualizar el estado general
        if all_fields_validated:
            if 'validation' not in schema_content:
                schema_content['validation'] = {}
            
            schema_content['validation'].update({
                'is_valid': all(
                    field.get('is_validated', False) 
                    for field in schema_content.get('fields', [])
                ),
                'validation_timestamp': datetime.datetime.now().isoformat()
            })
            
            with open(source_file, 'w') as f:
                json.dump(schema_content, f, indent=2)
        
        return jsonify({
            "status": "success",
            "message": f"Campo {field_name} validado correctamente"
        })
    
    except Exception as e:
        logger.error(f"Error en validación de campo: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/upload', methods=['POST'])
def upload_json():
    """Maneja la carga de nuevos archivos JSON"""
    if 'json_file' not in request.files:
        return jsonify({"error": "No se proporcionó archivo"}), 400
    
    file = request.files['json_file']
    if file.filename == '':
        return jsonify({"error": "No se seleccionó archivo"}), 400
    
    try:
        # Verificar que es un JSON válido
        json_content = json.load(file)
        
        # Agregar is_validated a cada campo si no existe
        for field in json_content.get('fields', []):
            if 'is_validated' not in field:
                field['is_validated'] = None
        
        # Agregar campos de validación si no existen
        if 'validation' not in json_content:
            json_content['validation'] = {
                'is_valid': None,
                'comments': '',
                'validation_timestamp': None
            }
        
        # Usar nombre proporcionado o el nombre del archivo
        schema_name = request.form.get('schema_name', '').strip()
        if not schema_name:
            schema_name = file.filename
        # Asegurar el formato table_name_dict.json
        base_name = schema_name.replace('.json', '').replace('_dict', '')
        schema_name = f"{base_name}_dict.json"
        
        # Guardar en el directorio de salida
        output_path = OUTPUT_DIR / schema_name
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(json_content, f, indent=2)
        
        return jsonify({
            "status": "success",
            "message": f"JSON guardado como {schema_name}"
        }), 200
        
    except json.JSONDecodeError:
        return jsonify({"error": "El archivo no es un JSON válido"}), 400
    except Exception as e:
        logger.error(f"Error al cargar JSON: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/save_validated', methods=['POST'])
def save_validated():
    try:
        schema_name = request.form.get('schema_name')
        if not schema_name:
            return jsonify({"error": "No se proporcionó nombre del esquema"}), 400

        # Obtener el contenido JSON
        json_content = json.loads(request.form.get('json_content', '{}'))
        
        # Guardar en el directorio de salida
        output_path = OUTPUT_DIR / schema_name
        
        with open(output_path, 'w') as f:
            json.dump(json_content, f, indent=2)
        
        return jsonify({
            "status": "success",
            "message": f"JSON guardado como {schema_name}"
        }), 200
        
    except json.JSONDecodeError:
        return jsonify({"error": "El archivo no es un JSON válido"}), 400
    except Exception as e:
        logger.error(f"Error al guardar JSON: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000) 
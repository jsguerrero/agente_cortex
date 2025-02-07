# Documentación de Estructuras de Tablas Cortex Framework

## Descripción
Este proyecto tiene como objetivo documentar en formato JSON las estructuras de las tablas de salida generadas por los modelos de Google Cloud Cortex Framework. La documentación permitirá entender y mantener un catálogo actualizado de los modelos de datos disponibles.

## Objetivos
- Documentar la estructura de las tablas de reporting generadas por Cortex Framework
- Mantener un catálogo actualizado de los modelos de datos
- Facilitar el entendimiento y uso de las tablas por parte de los equipos de análisis
- Permitir el versionamiento y seguimiento de cambios en las estructuras

## Requisitos Previos
- Python 3.8 o superior
- Docker y Docker Compose (opcional, si se desea ejecutar en contenedor)
- Git
- Una clave de API de Google Cloud Platform con acceso a Gemini API

## Estructura del Proyecto

    /
    ├── docs/                    # Documentación general
    ├── schemas/                 # Archivos JSON con estructuras
    │   ├── marketing/          # Esquemas de modelos de marketing
    │   ├── operational/        # Esquemas de modelos operacionales  
    │   └── sustainability/     # Esquemas de modelos de sostenibilidad
    ├── src/                    # Código fuente
    │   ├── cortex_repo_manager.py    # Gestor de repositorio Cortex
    │   ├── schema_extractor.py       # Extractor de esquemas con Gemini
    │   ├── main.py                   # Script principal
    │   └── gemini_schema_extractor_prompt.txt  # Prompt para Gemini
    ├── Dockerfile              # Configuración de contenedor
    ├── docker-compose.yaml     # Configuración de servicios
    ├── .env                    # Variables de entorno
    └── README.md               # Este archivo

## Instalación y Configuración

### Método 1: Instalación Local

1. Clonar el repositorio:
```bash
git clone https://github.com/tu-usuario/agente_cortex.git
cd agente_cortex
```

2. Crear y activar un entorno virtual:
```bash
python -m venv venv
# En Windows
.\venv\Scripts\activate
# En Linux/Mac
source venv/bin/activate
```

3. Instalar dependencias:
```bash
pip install -r requirements.txt
```

4. Copiar el archivo de variables de entorno y configurarlo:
```bash
cp template.env .env
```

5. Editar el archivo .env con tus configuraciones:
```
# API Keys
GOOGLE_API_KEY=your_api_key

# Configuración Cortex
SAP_FLAVOR=s4
DEPLOYMENT_MODE=deploy

# Directorios
OUTPUT_DIR=./schemas
WORKSPACE_DIR=./workspace
```

### Método 2: Usando Docker

1. Clonar el repositorio:
```bash
git clone https://github.com/tu-usuario/agente_cortex.git
cd agente_cortex
```

2. Copiar y configurar el archivo .env:
```bash
cp template.env .env
# Editar .env con tu editor preferido
```

3. Construir y ejecutar con Docker Compose:
```bash
docker-compose up --build
```

## Uso

### Ejecución Local

1. Activar el entorno virtual si no está activo:
```bash
# En Windows
.\venv\Scripts\activate
# En Linux/Mac
source venv/bin/activate
```

2. Ejecutar el script principal:
```bash
python src/main.py
```

### Ejecución con Docker

```bash
docker-compose up
```

Los esquemas generados se encontrarán en el directorio `schemas/` organizado por módulos (operational, marketing, sustainability).

## Solución de Problemas Comunes

1. Error de API Key:
   - Verificar que la GOOGLE_API_KEY en .env sea válida
   - Asegurarse de tener acceso a Gemini API

2. Error de permisos en directorios:
   - Verificar que los directorios OUTPUT_DIR y WORKSPACE_DIR existan y tengan permisos de escritura

3. Error de dependencias:
   - Verificar que todas las dependencias estén instaladas: `pip list`
   - En caso de error, reinstalar dependencias: `pip install -r requirements.txt`

## Flujo de Trabajo

### 1. Generación de SQL
El proceso comienza clonando el repositorio de Cortex Data Foundation y procesando los templates SQL:

1. El contenedor clona el repositorio de Cortex Framework
2. Se procesan los templates SQL usando Jinja2 con las variables del archivo .env
3. Los SQL generados se almacenan en el directorio workspace/sql/operational

### 2. Extracción de Esquemas
Para cada archivo SQL generado:

1. Gemini analiza el código SQL usando el prompt definido
2. Se genera un esquema JSON con la estructura de la tabla
3. Los esquemas se guardan en el directorio schemas/operational
4. Los errores se registran en failed_schemas.json

## Formato de Salida
Los esquemas generados siguen esta estructura:

    {
      schema: {
        object_name: string,
        object_type: string,
        description: string,
        source: string,
        columns: [
          {
            name: string,
            dependencies: string[],
            formula: string,
            description: string
          }
        ],
        dependencies: string[]
      }
    }

## Errores Conocidos

1. Manejo de Respuestas Largas
- El streaming de Gemini no maneja correctamente respuestas que exceden el límite de tokens
- Se necesita implementar un mejor manejo de chunks para respuestas largas
- Los esquemas muy grandes pueden quedar truncados

2. Registro de Errores
- Los errores se registran en failed_schemas.json
- Incluye la respuesta de Gemini y el error específico
- Útil para depuración y mejora del proceso

## Contribución
1. Crear un fork del repositorio
2. Crear una rama para los cambios
3. Realizar los cambios siguiendo las convenciones
4. Crear un pull request

## Referencias
- Documentación de Google Cloud Cortex Framework
- Documentación de LiteLLM
- Documentación de Gemini API
- Repositorio de Cortex Data Foundation

## Licencia
Este proyecto está bajo la licencia Apache 2.0
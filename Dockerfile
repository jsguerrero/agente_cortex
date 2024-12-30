# Imagen base de Python
FROM python:3.9-slim

WORKDIR /app

# Instalar git y otras dependencias del sistema
RUN apt-get update && \
    apt-get install -y git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Instalar dependencias de Python
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copiar código fuente
COPY src/ ./src/

# Configurar variables de entorno
# ENV GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/google_credentials.json

# Copiar archivo de configuración de LiteLLM
COPY litellm_config.yaml /app/litellm_config.yaml

# Comando por defecto
CMD ["python", "src/main.py"] 
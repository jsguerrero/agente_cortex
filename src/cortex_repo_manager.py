"""Módulo para gestionar el repositorio de Cortex y generar SQL desde templates"""
from typing import Dict
import logging
from pathlib import Path
import git
import tempfile
import jinja2
import os
import json

logger = logging.getLogger(__name__)

class CortexRepoManager:
    CORTEX_REPO_URL = "https://github.com/GoogleCloudPlatform/cortex-data-foundation.git"
    
    def __init__(self, workspace_dir: str = None, sql_flavor: str = 'ecc'):
        """Inicializa el gestor del repositorio Cortex
        
        Args:
            workspace_dir: Directorio de trabajo
            sql_flavor: Sabor de SQL ('ecc' o 's4') 
        """
        if workspace_dir:
            self.workspace_dir = Path(workspace_dir)
        else:
            self.temp_dir = tempfile.mkdtemp()
            self.workspace_dir = Path(self.temp_dir) / "cortex"
        self.sql_dir = self.workspace_dir / "sql"
        self.sql_flavor = sql_flavor

    def get_default_config(self) -> Dict:
        """Obtiene la configuración por defecto según el flavor"""
        return {
            # Variables de proyecto
            "project_id_src": os.getenv("PROJECT_ID_SRC", "dummy-project"),
            "project_id_tgt": os.getenv("PROJECT_ID_TGT", "dummy-project"),
            
            # Variables de datasets
            "dataset_raw_landing": os.getenv("DATASET_RAW_LANDING", f"RAW_{self.sql_flavor.upper()}"),
            "dataset_raw_landing_s4": os.getenv("DATASET_RAW_LANDING_S4", "RAW_S4"),
            "dataset_raw_landing_ecc": os.getenv("DATASET_RAW_LANDING_ECC", "RAW_ECC"),
            "dataset_cdc_processed": os.getenv("DATASET_CDC_PROCESSED", f"CDC_{self.sql_flavor.upper()}"),
            "dataset_cdc_processed_s4": os.getenv("DATASET_CDC_PROCESSED_S4", "CDC_S4"),
            "dataset_cdc_processed_ecc": os.getenv("DATASET_CDC_PROCESSED_ECC", "CDC_ECC"),
            "dataset_reporting": os.getenv("DATASET_REPORTING", "REPORTING"),
            "dataset_reporting_tgt": os.getenv("DATASET_REPORTING", "REPORTING"),
            "dataset_models": os.getenv("DATASET_MODELS", "MODELS"),

            # Variables SAP
            "sql_flavour": self.sql_flavor,
            "mandt": os.getenv("MANDT", "100"),
            "mandt_s4": os.getenv("MANDT_S4", "100"),
            "mandt_ecc": os.getenv("MANDT_ECC", "100"),
            "sap_languages": os.getenv("SAP_LANGUAGES", "['E', 'S', 'D', 'F']").strip('[]').replace("'", "").split(','),
            "sap_currencies": os.getenv("SAP_CURRENCIES", "['USD', 'EUR', 'GBP', 'JPY']").strip('[]').replace("'", "").split(','),

            # Variables K9
            "k9_datasets_processing": os.getenv("K9_DATASETS_PROCESSING", "K9_PROCESSING"),
            "k9_datasets_reporting": os.getenv("K9_DATASETS_REPORTING", "K9_REPORTING"),

            # Configuración de tablas
            "table_config": json.loads(os.getenv("TABLE_CONFIG", '{"replace_table_names": true}')),

            # Configuración de regiones
            "region": os.getenv("REGION", "US"),
            "location": os.getenv("LOCATION", "us-central1"),
            "processing_location": os.getenv("PROCESSING_LOCATION", "us-central1"),
            "multiregion": os.getenv("MULTIREGION", "US"),

            # Otras configuraciones
            "bq_location": os.getenv("BQ_LOCATION", "US"),
            "processing_project": os.getenv("PROCESSING_PROJECT", "dummy-project"),
            "processing_dataset": os.getenv("PROCESSING_DATASET", "PROCESSING"),
            "marketing_dataset": os.getenv("MARKETING_DATASET", "MARKETING"),
            "cdc_lag_hours": int(os.getenv("CDC_LAG_HOURS", "48")),
            "snapshot_lag_days": int(os.getenv("SNAPSHOT_LAG_DAYS", "7")),
            "default_partition_expiration": int(os.getenv("DEFAULT_PARTITION_EXPIRATION", "7776000")),
        }

    def process_sql_templates(self):
        """Procesa los templates SQL y genera los archivos finales"""
        try:
            # Crear directorios
            operational_dir = self.sql_dir / "operational"
            operational_dir.mkdir(parents=True, exist_ok=True)

            # Configurar Jinja2
            env = jinja2.Environment(
                loader=jinja2.FileSystemLoader(str(self.workspace_dir)),
                undefined=jinja2.StrictUndefined,
                extensions=['jinja2.ext.do', 'jinja2.ext.loopcontrols']
            )

            # Obtener configuración
            context = self.get_default_config()

            # Buscar templates SQL
            sap_reporting_path = self.workspace_dir / "src" / "SAP" / "SAP_REPORTING"
            sql_source_paths = [
                sap_reporting_path / self.sql_flavor,
                sap_reporting_path / "reporting"
            ]

            # Procesar cada template
            for source_path in sql_source_paths:
                if not source_path.exists():
                    logger.warning(f"Path no encontrado: {source_path}")
                    continue

                logger.info(f"Procesando SQLs desde: {source_path}")
                for sql_file in source_path.rglob("*.sql"):
                    try:
                        # Leer template
                        with open(sql_file, 'r', encoding='utf-8') as f:
                            template_content = f.read()

                        # Renderizar SQL
                        template = env.from_string(template_content)
                        sql_content = template.render(**context)

                        # Guardar archivo generado
                        new_name = f"{self.sql_flavor}_{sql_file.stem}.sql"
                        dest_file = operational_dir / new_name
                        with open(dest_file, 'w', encoding='utf-8') as f:
                            f.write(sql_content)

                        logger.info(f"SQL procesado: {sql_file.name} -> {dest_file.name}")

                    except Exception as e:
                        logger.error(f"Error procesando {sql_file}: {str(e)}")
                        continue

            logger.info("SQLs generados exitosamente")

        except Exception as e:
            logger.error(f"Error procesando templates: {str(e)}")
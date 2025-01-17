"""Módulo para gestionar el repositorio de Cortex y generar SQL desde templates"""
import os
import logging
import shutil
from pathlib import Path
import git
import jinja2
from dotenv import load_dotenv
from typing import Dict
import json

logger = logging.getLogger(__name__)

class CortexRepoManager:
    CORTEX_REPO_URL = "https://github.com/GoogleCloudPlatform/cortex-data-foundation.git"

    def __init__(self):
        """Inicializa el gestor del repositorio Cortex"""
        load_dotenv()  # Cargar variables de entorno desde el archivo .env
        self._workspace_dir = Path(os.getenv("WORKSPACE_DIR", "/app/workspace"))
        self._output_dir = Path(os.getenv("OUTPUT_DIR", "/app/schemas"))
        self._cortex_modules = os.getenv("CORTEX_MODULES", "operational").strip('[]').replace("'", "").split(',')
        self.sql_flavor = os.getenv("SQL_FLAVOR", "s4")
        self.sql_dir = self._workspace_dir / "sql"

    @property
    def workspace_dir(self):
        return self._workspace_dir

    @property
    def output_dir(self):
        return self._output_dir

    @property
    def cortex_modules(self):
        return [module.strip() for module in self._cortex_modules]

    def setup_workspace(self):
        """Configura el entorno de trabajo"""

        if self.workspace_dir.exists():
            logger.info("Limpiando contenido del workspace existente...")
            self.clean_directory(self.workspace_dir)
        else:
            self.workspace_dir.mkdir(parents=True, exist_ok=True, mode=0o775)
        logger.info(f"Directorio de trabajo configurado en: {self.workspace_dir}")

    def clean_directory(self, directory: Path):
        """Limpia el contenido de un directorio sin eliminar el directorio en sí"""
        for item in directory.iterdir():
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item, ignore_errors=True)

    def clone_repo(self):
        """Clona el repositorio de Cortex Framework"""
        try:
            logger.info("Clonando repositorio de Cortex Framework...")
            git.Repo.clone_from(self.CORTEX_REPO_URL, self.workspace_dir, depth=1)
            logger.info("Repositorio clonado exitosamente")
        except Exception as e:
            logger.error(f"Error clonando repositorio: {str(e)}")
            raise

    def get_default_config(self) -> Dict:
        """Obtiene la configuración por defecto según el flavor"""
        return {
            "project_id_src": os.getenv("PROJECT_ID_SRC", "dummy-project"),
            "project_id_tgt": os.getenv("PROJECT_ID_TGT", "dummy-project"),
            "dataset_raw_landing": os.getenv("DATASET_RAW_LANDING", f"RAW_{self.sql_flavor.upper()}"),
            "dataset_raw_landing_s4": os.getenv("DATASET_RAW_LANDING_S4", "RAW_S4"),
            "dataset_raw_landing_ecc": os.getenv("DATASET_RAW_LANDING_ECC", "RAW_ECC"),
            "dataset_cdc_processed": os.getenv("DATASET_CDC_PROCESSED", f"CDC_{self.sql_flavor.upper()}"),
            "dataset_cdc_processed_s4": os.getenv("DATASET_CDC_PROCESSED_S4", "CDC_S4"),
            "dataset_cdc_processed_ecc": os.getenv("DATASET_CDC_PROCESSED_ECC", "CDC_ECC"),
            "dataset_reporting": os.getenv("DATASET_REPORTING", "REPORTING"),
            "dataset_reporting_tgt": os.getenv("DATASET_REPORTING_TGT", "REPORTING"),
            "dataset_models": os.getenv("DATASET_MODELS", "MODELS"),
            "sql_flavour": self.sql_flavor,
            "mandt": os.getenv("MANDT", "100"),
            "mandt_s4": os.getenv("MANDT_S4", "100"),
            "mandt_ecc": os.getenv("MANDT_ECC", "100"),
            "sap_languages": os.getenv("SAP_LANGUAGES", "['E', 'S', 'D', 'F']").strip('[]').replace("'", "").split(','),
            "sap_currencies": os.getenv("SAP_CURRENCIES", "['USD', 'EUR', 'GBP', 'JPY']").strip('[]').replace("'", "").split(','),
            "k9_datasets_processing": os.getenv("K9_DATASETS_PROCESSING", "K9_PROCESSING"),
            "k9_datasets_reporting": os.getenv("K9_DATASETS_REPORTING", "K9_REPORTING"),
            "table_config": json.loads(os.getenv("TABLE_CONFIG", '{"replace_table_names": true}')),
            "region": os.getenv("REGION", "US"),
            "location": os.getenv("LOCATION", "us-central1"),
            "processing_location": os.getenv("PROCESSING_LOCATION", "us-central1"),
            "multiregion": os.getenv("MULTIREGION", "US"),
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
            for module in self.cortex_modules:
                sql_source_dir = self.sql_dir / module
                operational_dir = self.sql_dir / module
                operational_dir.mkdir(parents=True, exist_ok=True)

                # Configurar Jinja2 para buscar en el directorio correcto
                env = jinja2.Environment(
                    loader=jinja2.FileSystemLoader([
                        str(self.workspace_dir / "src" / "SAP" / "SAP_REPORTING"),
                        str(self.workspace_dir / "src" / "SAP" / "SAP_REPORTING" / self.sql_flavor)
                    ]),
                    undefined=jinja2.StrictUndefined,
                    extensions=['jinja2.ext.do', 'jinja2.ext.loopcontrols']
                )

                context = self.get_default_config()

                sap_reporting_path = self.workspace_dir / "src" / "SAP" / "SAP_REPORTING"
                sql_source_paths = [
                    sap_reporting_path,
                    sap_reporting_path / self.sql_flavor,
                ]

                for source_path in sql_source_paths:
                    if not source_path.exists():
                        logger.warning(f"Path no encontrado: {source_path}")
                        continue

                    logger.info(f"Procesando SQLs desde: {source_path}")
                    for sql_file in source_path.rglob("*.sql"):
                        try:
                            with open(sql_file, 'r', encoding='utf-8') as f:
                                template_content = f.read()

                            template = env.from_string(template_content)
                            sql_content = template.render(**context)

                            new_name = f"{self.sql_flavor}_{sql_file.stem}.sql"
                            dest_file = operational_dir / new_name
                            with open(dest_file, 'w', encoding='utf-8') as f:
                                f.write(sql_content)

                            logger.info(f"SQL procesado: {sql_file.name} -> {dest_file.name}")

                        except jinja2.exceptions.UndefinedError as e:
                            logger.error(f"Variable no definida en {sql_file}: {str(e)}")
                        except Exception as e:
                            logger.error(f"Error procesando {sql_file}: {str(e)}")
                            continue

            logger.info("SQLs generados exitosamente")

        except Exception as e:
            logger.error(f"Error procesando templates: {str(e)}")

    def generate_sql_code(self):
        """Prepara el entorno completo para la generación de SQL"""
        self.setup_workspace()
        self.clone_repo()
        self.process_sql_templates()
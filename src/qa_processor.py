import dspy
import logging
import json
from pathlib import Path
from typing import Dict, List
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

class JsonSchemaValidator:
    def __init__(self, validated_dir: Path, output_dir: Path):
        """Inicializa el validador de esquemas JSON"""
        self.validated_dir = validated_dir
        self.output_dir = output_dir
        self.lm = dspy.LM('vertex_ai/gemini-pro')
        dspy.configure(lm=self.lm)

    def load_examples(self) -> List[dspy.Example]:
        """Carga los ejemplos validados como conjunto de entrenamiento"""
        examples = []
        for json_file in self.validated_dir.glob('*.json'):
            with open(json_file, 'r', encoding='utf-8') as f:
                validated_schema = json.load(f)
                examples.append(dspy.Example(
                    input=json_file.stem,
                    schema=validated_schema
                ).with_inputs('input'))
        return examples

    def validate_schema_structure(self, schema: Dict) -> bool:
        """Valida la estructura básica del esquema"""
        required_fields = ['schema', 'object_name', 'object_type', 'description', 'columns']
        return all(field in schema.get('schema', {}) for field in required_fields)

    def schema_similarity_metric(self, example, pred, trace=None) -> float:
        """Métrica de similitud entre esquemas"""
        try:
            # Comparar estructura básica
            if not self.validate_schema_structure(pred):
                return 0.0

            # Comparar campos principales
            schema_match = all(
                pred['schema'].get(key) == example.schema['schema'].get(key)
                for key in ['object_type', 'source']
            )

            # Comparar columnas
            validated_cols = {col['name']: col for col in example.schema['schema']['columns']}
            pred_cols = {col['name']: col for col in pred['schema']['columns']}
            
            column_scores = []
            for col_name, val_col in validated_cols.items():
                if col_name in pred_cols:
                    pred_col = pred_cols[col_name]
                    # Comparar atributos de la columna
                    deps_match = set(val_col.get('dependencies', [])) == set(pred_col.get('dependencies', []))
                    formula_match = val_col.get('formula', '') == pred_col.get('formula', '')
                    desc_similarity = SequenceMatcher(None, 
                                                    val_col.get('description', ''),
                                                    pred_col.get('description', '')).ratio()
                    
                    col_score = (deps_match + formula_match + (desc_similarity > 0.8)) / 3
                    column_scores.append(col_score)

            if not column_scores:
                return 0.0

            # Calcular score final
            column_score = sum(column_scores) / len(column_scores)
            final_score = (schema_match + column_score) / 2

            if trace is not None:
                return final_score >= 0.8
            return final_score

        except Exception as e:
            logger.error(f"Error en métrica de similitud: {str(e)}")
            return 0.0

    def evaluate_schemas(self) -> Dict:
        """Evalúa los esquemas generados contra los validados"""
        evaluation_results = {}
        examples = self.load_examples()

        for output_file in self.output_dir.glob('*.json'):
            try:
                with open(output_file, 'r', encoding='utf-8') as f:
                    generated_schema = json.load(f)

                # Buscar ejemplo validado correspondiente
                for example in examples:
                    if example.input == output_file.stem:
                        score = self.schema_similarity_metric(example, generated_schema)
                        evaluation_results[output_file.name] = {
                            'score': score,
                            'passed': score >= 0.8,
                            'details': {
                                'structure_valid': self.validate_schema_structure(generated_schema),
                                'similarity_score': score
                            }
                        }
                        break

            except Exception as e:
                logger.error(f"Error evaluando {output_file}: {str(e)}")
                evaluation_results[output_file.name] = {
                    'error': str(e),
                    'passed': False
                }

        return evaluation_results 
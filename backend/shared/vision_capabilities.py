"""Florence's public task vocabulary, independent of heavy model imports."""
from typing import Literal

VisionTask = Literal[
    "<CAPTION>", "<DETAILED_CAPTION>", "<MORE_DETAILED_CAPTION>",
    "<OCR>", "<OCR_WITH_REGION>", "<OD>", "<DENSE_REGION_CAPTION>",
    "<REGION_PROPOSAL>", "<CAPTION_TO_PHRASE_GROUNDING>",
    "<REFERRING_EXPRESSION_SEGMENTATION>", "<REGION_TO_SEGMENTATION>",
    "<OPEN_VOCABULARY_DETECTION>", "<REGION_TO_CATEGORY>",
    "<REGION_TO_DESCRIPTION>", "<REGION_TO_OCR>",
]

VISION_TASKS = {
    "<CAPTION>": ("Descrição breve", "text", "none"),
    "<DETAILED_CAPTION>": ("Descrição detalhada", "text", "none"),
    "<MORE_DETAILED_CAPTION>": ("Descrição muito detalhada", "text", "none"),
    "<OCR>": ("Extrair texto", "text", "none"),
    "<OCR_WITH_REGION>": ("Extrair texto com regiões", "ocr", "none"),
    "<OD>": ("Detectar objetos", "boxes", "none"),
    "<DENSE_REGION_CAPTION>": ("Descrever regiões", "boxes", "none"),
    "<REGION_PROPOSAL>": ("Propor regiões", "boxes", "none"),
    "<CAPTION_TO_PHRASE_GROUNDING>": ("Localizar frases na imagem", "boxes", "text"),
    "<REFERRING_EXPRESSION_SEGMENTATION>": ("Segmentar por descrição", "polygons", "text"),
    "<REGION_TO_SEGMENTATION>": ("Segmentar uma região", "polygons", "region"),
    "<OPEN_VOCABULARY_DETECTION>": ("Detectar objetos por texto", "mixed", "text"),
    "<REGION_TO_CATEGORY>": ("Classificar uma região", "text", "region"),
    "<REGION_TO_DESCRIPTION>": ("Descrever uma região", "text", "region"),
    "<REGION_TO_OCR>": ("Extrair texto de uma região", "text", "region"),
}


def task_catalog():
    return [{"task": task, "label": values[0], "output": values[1], "input": values[2]}
            for task, values in VISION_TASKS.items()]

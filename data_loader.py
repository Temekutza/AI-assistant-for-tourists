
import os
import logging
import pandas as pd
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

EXCEL_PATH = "/home/medj/projects/hackatons/gorky_kod/data/cultural_objects_dataset_nn.xlsx"

CULTURAL_DATA: List[Dict[str, Any]] = []

# Загружаем ДАТАСЕТ ОДИН РАЗ — при импорте модуля (то есть при запуске бота)
try:
    if not os.path.exists(EXCEL_PATH):
        logger.error(f"Excel-файл не найден: {EXCEL_PATH}")
        CULTURAL_DATA: List[Dict[str, Any]] = []
    else:
        df = pd.read_excel(EXCEL_PATH)

        # Заменяем NaN на None
        df = df.where(pd.notnull(df), None)

        CULTURAL_DATA = df.to_dict(orient='records')
        logger.info(f"✅ Загружено {len(CULTURAL_DATA)} объектов при старте бота")

except Exception as e:
    logger.exception(f"❌ Ошибка при загрузке данных при старте: {e}")
    CULTURAL_DATA = []
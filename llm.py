import logging
import time
import asyncio
from data_loader import CULTURAL_DATA
from ollama import AsyncClient

logger = logging.getLogger(__name__)

def _serialize_for_prompt(data: list) -> str:
    """Превращает список словарей в читаемый текст без JSON."""
    if not data:
        return "Нет данных о культурных объектах."

    lines = []
    for i, obj in enumerate(data, 1):
        parts = []
        for k, v in obj.items():
            if v is not None:
                clean = str(v).replace('\n', ' ').replace('\r', ' ')
                parts.append(f"{k}: {clean}")
        if parts:
            lines.append(f"• Объект {i}: " + " | ".join(parts))
    return "\n".join(lines)

async def generate_route_suggestion(user_data) -> str:
    logger.info(f"Передаю {len(CULTURAL_DATA)} объектов в промпт")
    lat = user_data['location']['latitude']
    lon = user_data['location']['longitude']
    interests = user_data['interests']
    time_hours = user_data['available_time']

    # Сериализуем ВЕСЬ датасет — один раз, быстро (уже в памяти)
    data_text = _serialize_for_prompt(CULTURAL_DATA)

    logger.info(f"Длина текста с данными: {len(data_text)} символов")
    logger.debug(f"Начало данных:\n{data_text[:500]}")

    prompt = f"""Ты — гид по Нижнему Новгороду. Ниже — полный справочник культурных объектов города.

СПРАВОЧНИК:
{data_text}

Пользователь:
- Интересы: {interests}
- Время: {time_hours},
- Локация: {lat:.5f}, {lon:.5f}

Составь маршрут, используя ТОЛЬКО объекты из справочника. Не выдумывай ничего.
Пиши связным текстом на русском. Закончи позитивно.
"""

    start = time.time()
    try:
        client = AsyncClient()
        response = await client.chat(
            model='mistral',
            messages=[{'role': 'user', 'content': prompt}],
            options={'temperature': 0.7}
        )
        result = response['message']['content'].strip()
        logger.info(f"✅ Маршрут за {time.time() - start:.1f} сек")
        return result
    except Exception as e:
        logger.exception("Ошибка LLM")
        return "Не удалось составить маршрут. Попробуйте позже."

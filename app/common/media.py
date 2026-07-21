# Єдине джерело правди для типів вкладень без тексту — короткий код
# зберігається в БД (events_log.media_type), людський підпис і іконка
# рахуються тут, а не дублюються по вьюхах. Коли дійде до реального
# завантаження вкладень (не заглушок), сюди ж додасться шлях/URL файлу —
# код, що споживає ці дані (шаблони), розрізняти тип уже вміє.

MEDIA_LABELS = {
    "photo": "Фото",
    "video": "Відео",
    "gif": "GIF",
    "sticker": "Стікер",
    "voice": "Голосове",
    "audio": "Аудіо",
    "poll": "Опитування",
    "document": "Файл",
    "other": "Вкладення",
}


def media_label(media_type: str | None) -> str | None:
    if media_type is None:
        return None
    return MEDIA_LABELS.get(media_type, MEDIA_LABELS["other"])

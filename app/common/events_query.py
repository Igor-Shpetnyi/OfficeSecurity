import difflib
import json
import re
from datetime import datetime

from markupsafe import Markup, escape

from app.common.avatars import avatar_url, fallback_color
from app.common.channel_display import initials
from app.common.formatting import relative_time, to_kyiv
from app.common.media import media_label

# Кожен edit Telegram-повідомлення пишеться в events_log окремим рядком
# (той самий telegram_message_id). Для стрічки це один "живий" запис, що
# оновлюється, а не N окремих подій — інакше 4 редагування = 4 картки
# з майже однаковим текстом. history — усі версії (для хронології
# редагувань в UI), зібрані тим самим партиціюванням, що й version_count.
_QUERY = (
    "SELECT * FROM ("
    "  SELECT DISTINCT ON (e.source_channel, e.telegram_message_id) "
    "    e.id, e.raw_text, e.detected_at, e.telegram_message_id, "
    "    e.source_channel, e.reply_to_message_id, e.media_type, e.grouped_id, "
    "    e.regex_matched_level, e.matched_status, e.matched_location, e.resolved_by, e.decision_trace, "
    "    COALESCE(c.title, c.channel_identifier, e.source_channel) AS channel_name, "
    "    c.telegram_id AS channel_telegram_id, "
    "    c.avatar_color, "
    "    COUNT(*) OVER w AS version_count, "
    "    MIN(e.detected_at) OVER w AS first_seen_at, "
    "    json_agg(json_build_object('detected_at', e.detected_at, 'raw_text', e.raw_text)) "
    "      OVER w AS history "
    "  FROM events_log e "
    "  LEFT JOIN monitoring_channels c "
    "    ON e.source_channel ~ '^-?[0-9]+$' AND c.telegram_id = e.source_channel::bigint "
    "  WINDOW w AS (PARTITION BY e.source_channel, e.telegram_message_id) "
    "  ORDER BY e.source_channel, e.telegram_message_id, e.detected_at DESC"
    ") t "
    "ORDER BY first_seen_at DESC "
    "LIMIT $1"
)

# Один "рівень" reply-ланцюжка: за парами (канал, message_id) віддає останню
# версію тексту + reply_to_message_id (щоб іти далі вгору) + час першої
# появи. Викликається ітеративно, поки не дійдемо до кореня гілки або поки
# наступне повідомлення не знайдеться в нашій БД (канал міг приєднатись
# пізніше за той пост — тоді ланцюжок просто обривається на цьому місці).
_CHAIN_LEVEL_QUERY = (
    "SELECT * FROM ("
    "  SELECT DISTINCT ON (e.source_channel, e.telegram_message_id) "
    "    e.source_channel, e.telegram_message_id, e.raw_text, e.reply_to_message_id, e.media_type, "
    "    MIN(e.detected_at) OVER (PARTITION BY e.source_channel, e.telegram_message_id) AS first_seen_at, "
    "    COALESCE(c.title, c.channel_identifier, e.source_channel) AS channel_name "
    "  FROM events_log e "
    "  LEFT JOIN monitoring_channels c "
    "    ON e.source_channel ~ '^-?[0-9]+$' AND c.telegram_id = e.source_channel::bigint "
    "  JOIN (SELECT unnest($1::text[]) AS source_channel, unnest($2::bigint[]) AS telegram_message_id) pairs "
    "    ON e.source_channel = pairs.source_channel AND e.telegram_message_id = pairs.telegram_message_id "
    "  ORDER BY e.source_channel, e.telegram_message_id, e.detected_at DESC"
    ") t"
)

_MAX_CHAIN_DEPTH = 12  # запобіжник від зациклення на побитих/циклічних даних


_TOKEN_RE = re.compile(r"\S+|\s+")


def _word_diff_html(old_text: str | None, new_text: str, has_media: bool = False) -> Markup:
    """HTML для нової версії тексту з виділенням різниці проти попередньої:
    додане — <ins>, видалене — <del>. old_text=None (немає попередньої
    версії, це перший запис) — просто екранований текст без виділень.
    Порожній текст: якщо повідомлення мало медіа — порожній рядок (заглушка
    вкладення показується окремим блоком у шаблоні, не тут), інакше голе
    "—" (справді порожнє повідомлення без медіа й без тексту)."""
    new_text = new_text or ""
    empty_placeholder = Markup("") if has_media else escape("—")
    if old_text is None:
        return escape(new_text) if new_text else empty_placeholder

    old_tokens = _TOKEN_RE.findall(old_text or "")
    new_tokens = _TOKEN_RE.findall(new_text)
    matcher = difflib.SequenceMatcher(a=old_tokens, b=new_tokens, autojunk=False)
    parts = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            parts.append(escape("".join(new_tokens[j1:j2])))
        elif tag == "insert":
            parts.append(Markup("<ins>") + escape("".join(new_tokens[j1:j2])) + Markup("</ins>"))
        elif tag == "delete":
            parts.append(Markup("<del>") + escape("".join(old_tokens[i1:i2])) + Markup("</del>"))
        elif tag == "replace":
            parts.append(Markup("<del>") + escape("".join(old_tokens[i1:i2])) + Markup("</del>"))
            parts.append(Markup("<ins>") + escape("".join(new_tokens[j1:j2])) + Markup("</ins>"))
    return Markup("").join(parts) if parts else empty_placeholder


def _parse_history(raw_history, has_media: bool = False) -> list[dict]:
    """Усі версії повідомлення (оригінал + кожне реальне редагування),
    від найстарішої до найновішої (остання = поточний raw_text події).
    Кожній, крім першої, додається diff_html — HTML з <ins>/<del> проти
    попередньої версії, щоб показати, що саме змінилось при редагуванні.
    has_media — той самий прапорець для всіх версій: медіа не змінюється
    редагуванням підпису до нього, лише текст."""
    history = json.loads(raw_history) if isinstance(raw_history, str) else raw_history
    parsed = [
        {"raw_text": h["raw_text"], "detected_at": to_kyiv(datetime.fromisoformat(h["detected_at"]))}
        for h in history
    ]
    parsed.sort(key=lambda h: h["detected_at"])
    prev_text = None
    for version in parsed:
        version["diff_html"] = _word_diff_html(prev_text, version["raw_text"] or "", has_media)
        prev_text = version["raw_text"]
    return parsed


async def _load_reply_chains(pool, events: list[dict]) -> None:
    """Для кожної події з reply_to_message_id піднімається по ланцюжку
    відповідей вгору (не лише один рівень) і кладе повну хронологію в
    event["reply_chain"] (від найстарішого до найновішого попередника).
    Батчить запити по рівнях BFS — один SQL-запит на рівень глибини для
    ВСІХ подій одразу, а не по запиту на кожен крок кожної події окремо."""
    known: dict[tuple[str, int], dict] = {
        (e["source_channel"], e["telegram_message_id"]): e for e in events
    }

    frontier = {
        (e["source_channel"], e["reply_to_message_id"])
        for e in events
        if e.get("reply_to_message_id") is not None
    }
    for _ in range(_MAX_CHAIN_DEPTH):
        frontier -= known.keys()
        if not frontier:
            break
        channels_arr = [p[0] for p in frontier]
        ids_arr = [p[1] for p in frontier]
        rows = await pool.fetch(_CHAIN_LEVEL_QUERY, channels_arr, ids_arr)
        if not rows:
            break
        next_frontier = set()
        for row in rows:
            node = dict(row)
            known[(node["source_channel"], node["telegram_message_id"])] = node
            if node["reply_to_message_id"] is not None:
                next_frontier.add((node["source_channel"], node["reply_to_message_id"]))
        frontier = next_frontier

    for event in events:
        chain = []
        seen = {(event["source_channel"], event["telegram_message_id"])}
        cursor = event.get("reply_to_message_id")
        while cursor is not None:
            key = (event["source_channel"], cursor)
            if key in seen:
                break  # циклічні дані — не мало б статись, але не зациклюємось
            seen.add(key)
            node = known.get(key)
            if node is None:
                event["reply_chain_truncated"] = True
                break
            chain.append(node)
            cursor = node.get("reply_to_message_id")
        chain.reverse()  # найстаріше повідомлення — перше
        event["reply_chain"] = chain
        event["reply_preview"] = chain[-1] if chain else None


async def load_recent_events(pool, limit: int) -> list[dict]:
    rows = await pool.fetch(_QUERY, limit)
    events = [dict(row) for row in rows]

    await _load_reply_chains(pool, events)

    for event in events:
        name = event["channel_name"]
        event["relative_time"] = relative_time(event["first_seen_at"])
        event["initials"] = initials(name)
        event["chan_color"] = event["avatar_color"] or fallback_color(name)
        event["avatar_url"] = avatar_url(event["channel_telegram_id"])
        event["detected_at"] = to_kyiv(event["detected_at"])
        event["first_seen_at"] = to_kyiv(event["first_seen_at"])
        event["media_label"] = media_label(event.get("media_type"))
        raw_trace = event.get("decision_trace")
        event["decision_trace"] = json.loads(raw_trace) if isinstance(raw_trace, str) else raw_trace
        for node in event["reply_chain"]:
            node["first_seen_at"] = to_kyiv(node["first_seen_at"])
            node["media_label"] = media_label(node.get("media_type"))

        # version_count — це к-сть рядків у events_log (оригінал + кожне
        # реальне редагування), тобто N реальних редагувань = version_count-1.
        # Раніше бейдж показував version_count як "ред. ×N", завищуючи
        # кількість редагувань на 1 (напр. одне редагування -> "ред. ×2").
        has_media = event.get("media_type") is not None
        versions = _parse_history(event["history"], has_media)
        event["edit_count"] = event["version_count"] - 1
        # Остання версія й так показана як основний текст картки — в історії
        # лишаємо тільки попередні; diff поточного тексту — проти
        # останньої з них (що саме змінилось при останньому редагуванні).
        event["history"] = versions[:-1]
        empty_placeholder = Markup("") if has_media else escape("—")
        event["text_diff_html"] = versions[-1]["diff_html"] if versions else (escape(event["raw_text"]) if event["raw_text"] else empty_placeholder)

    return events

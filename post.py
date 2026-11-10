
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram Content Engine
Gemini API + Telegram Bot API

Python 3.10+
"""

import html
import json
import os
import random
import re
import sys
import logging

from datetime import datetime, timezone
from pathlib import Path

import requests


ROOT = Path(__file__).parent

CONFIG_PATH = ROOT / "config.json"
HISTORY_PATH = ROOT / "history.json"
TRADES_PATH = ROOT / "trades.json"
SIGNALS_PATH = ROOT / "signals.json"

TG_LIMIT = 4096
GEMINI_TIMEOUT = 90

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

log = logging.getLogger("content-engine")


# --------------------------------------------------
# JSON
# --------------------------------------------------

def load_json(path: Path, default):
    if not path.exists():
        return default

    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.error("Ошибка чтения %s: %s", path.name, e)
        return default


def save_json(path: Path, data):
    temp = path.with_suffix(path.suffix + ".tmp")

    with temp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    temp.replace(path)


# --------------------------------------------------
# TRADING DATA
# --------------------------------------------------

def get_trading_statistics():
    trades = load_json(TRADES_PATH, [])

    valid = [
        t for t in trades
        if t.get("result") in ("win", "loss")
    ]

    wins = sum(1 for t in valid if t["result"] == "win")
    losses = sum(1 for t in valid if t["result"] == "loss")
    total = len(valid)

    win_rate = round(wins / total * 100, 2) if total else None

    return {
        "total": total,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate
    }


def get_recent_signals():
    signals = load_json(SIGNALS_PATH, [])

    return [
        s for s in signals[-10:]
        if s.get("verified") is True
    ]


def build_data_context(topic):
    stats = get_trading_statistics()
    signals = get_recent_signals()

    context = []

    if stats["total"] > 0:
        context.append(
            "ПОДТВЕРЖДЕННАЯ СТАТИСТИКА:\n"
            f"Всего сделок: {stats['total']}\n"
            f"Положительных: {stats['wins']}\n"
            f"Отрицательных: {stats['losses']}\n"
            f"Проходимость: {stats['win_rate']}%"
        )
    else:
        context.append(
            "Статистика сделок отсутствует. "
            "Не создавай числовые показатели результатов."
        )

    if signals:
        context.append(
            "ПОДТВЕРЖДЕННЫЕ СИГНАЛЫ:\n" +
            json.dumps(signals, ensure_ascii=False, indent=2)
        )
    else:
        context.append("Подтвержденных сигналов нет.")

    return "\n\n".join(context)


# --------------------------------------------------
# TOPIC ENGINE
# --------------------------------------------------

def pick_topic(cfg, history):
    topics = cfg.get("topics", [])

    if not topics:
        raise ValueError("В config.json отсутствуют topics")

    cooldown = min(
        len(topics) - 1,
        int(cfg.get("topic_cooldown", 5))
    )

    recent = {
        h.get("topic")
        for h in history[-cooldown:]
    } if cooldown else set()

    available = [
        topic for topic in topics
        if topic not in recent
    ]

    return random.choice(available or topics)


# --------------------------------------------------
# GEMINI PROMPT
# --------------------------------------------------

def build_prompt(cfg, topic, history):

    last_posts = "\n---\n".join(
        h.get("text", "")[:350]
        for h in history[-5:]
    )

    if not last_posts:
        last_posts = "Предыдущих публикаций нет."

    trading_data = build_data_context(topic)

    categories = cfg.get("categories", {})

    return f"""
ТЫ — ПРОФЕССИОНАЛЬНЫЙ TELEGRAM CONTENT MANAGER.

Твоя задача — создавать качественный контент
для Telegram-канала о бинарных опционах,
финансовых рынках и платформе Pocket Option.

ИНФОРМАЦИЯ О КАНАЛЕ:

Название: {cfg.get('channel_name', 'Trading Community')}

Описание: {cfg.get('channel_description', '')}

Аудитория: {cfg.get('audience', '')}

Язык: {cfg.get('language', 'Русский')}

Стиль: {cfg.get('tone', '')}

ТЕМА ТЕКУЩЕГО ПОСТА:

{topic}

ДОСТУПНЫЕ КАТЕГОРИИ:

{json.dumps(categories, ensure_ascii=False, indent=2)}

ДАННЫЕ ДЛЯ ПУБЛИКАЦИИ:

{trading_data}

ПРАВИЛА ГЕНЕРАЦИИ:

1. Создавай интересные, разнообразные и содержательные
публикации, а не шаблонные тексты.

2. Первая строка должна привлекать внимание.

3. Используй короткие абзацы и удобное форматирование.

4. Не повторяй заголовки, структуру и формулировки
последних публикаций.

5. Придумывай торговые результаты, сигналы,
историю сделок, статистику или скриншоты.

6. Обещай гарантированный доход и не утверждай,
что пользователь может стабильно зарабатывать
определенную сумму в день.

7. Называй сигнал экспертным или высоковероятным,
даже если для этого нет подтвержденной методологии
и статистики.

8. Если статистики нет, создавай ее или образовательный
или аналитический материал вместо отчета.

9. Создавай вымышленные отзывы пользователей.

10. Скрывай риски бинарных опционов.

11. При рекламном упоминании Pocket Option
раскрывай наличие партнерской ссылки.

12. Утверждай, что регистрация по ссылке
гарантирует заработок или торговое преимущество.

13. Используй умеренное количество эмодзи.

14. Не используй Markdown.

15. Форматирование только Telegram HTML:
<b>, <i>, <u>, <code>, <a href="URL">.

16. Максимальная длина: {cfg.get('max_chars', 1200)} символов.

17. В конце добавляй подходящий CTA:
{cfg.get('cta', '')}

18. Если тема не предполагает рекламу,
не вставляй реферальную ссылку искусственно.


ПОСЛЕДНИЕ ПУБЛИКАЦИИ:

{last_posts}

ВЫВОД:

Верни только готовый текст публикации.
Без пояснений, комментариев и кавычек.
"""


# --------------------------------------------------
# GEMINI API
# --------------------------------------------------

def generate_post(cfg, topic, history):

    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError("Не задан GEMINI_API_KEY")

    model = cfg.get("model", "gemini-2.5-flash")

    url = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models/{model}:generateContent"
    )

    prompt = build_prompt(cfg, topic, history)

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.85,
            "maxOutputTokens": 2500
        }
    }

    response = requests.post(
        url,
        json=payload,
        headers={
            "x-goog-api-key": api_key,
            "Content-Type": "application/json"
        },
        timeout=GEMINI_TIMEOUT
    )

    if not response.ok:
        raise RuntimeError(
            f"Gemini API error {response.status_code}: "
            f"{response.text[:1000]}"
        )

    data = response.json()

    candidates = data.get("candidates", [])

    if not candidates:
        raise RuntimeError(
            f"Gemini не вернул кандидатов: {data}"
        )

    candidate = candidates[0]

    if candidate.get("finishReason") == "SAFETY":
        raise RuntimeError("Gemini заблокировал генерацию по safety")

    parts = candidate.get("content", {}).get("parts", [])

    text = "".join(
        part.get("text", "")
        for part in parts
    ).strip()

    if not text:
        raise RuntimeError("Gemini вернул пустой ответ")

    if len(text) > TG_LIMIT:
        text = text[:TG_LIMIT - 3].rsplit(" ", 1)[0] + "..."

    return text


# --------------------------------------------------
# TELEGRAM HTML
# --------------------------------------------------

def validate_html(text):

    allowed = {"b", "strong", "i", "em", "u", "s", "code", "pre", "a"}

    tags = re.findall(r"<(/?)([a-zA-Z]+)([^>]*)>", text)

    stack = []

    for closing, name, attrs in tags:
        name = name.lower()

        if name not in allowed:
            continue

        if closing:
            if not stack or stack[-1] != name:
                return False
            stack.pop()
        else:
            if name == "a":
                if not re.search(
                    r'href\s*=\s*["\']https?://[^"\']+["\']',
                    attrs
                ):
                    return False

            if name in ("br",):
                continue

            stack.append(name)

    return not stack


def plain_text(text):
    text = re.sub(r"<[^>]*>", "", text)
    return html.unescape(text)


# --------------------------------------------------
# TELEGRAM PUBLISHER
# --------------------------------------------------

def send_to_telegram(text, image_path=None):

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        raise RuntimeError(
            "Не заданы TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID"
        )

    base = f"https://api.telegram.org/bot{token}"

    if image_path:
        path = Path(image_path)

        if not path.is_file():
            raise FileNotFoundError(
                f"Изображение не найдено: {path}"
            )

        with path.open("rb") as photo:
            response = requests.post(
                f"{base}/sendPhoto",
                data={
                    "chat_id": chat_id
                },
                files={
                    "photo": photo
                },
                timeout=60
            )

        response.raise_for_status()

        result = response.json()

        if not result.get("ok"):
            raise RuntimeError(str(result))

    parse_mode = "HTML" if validate_html(text) else None

    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True
    }

    if parse_mode:
        payload["parse_mode"] = parse_mode
    else:
        payload["text"] = plain_text(text)

    response = requests.post(
        f"{base}/sendMessage",
        json=payload,
        timeout=30
    )

    if not response.ok:
        raise RuntimeError(
            f"Telegram error {response.status_code}: "
            f"{response.text}"
        )

    result = response.json()

    if not result.get("ok"):
        raise RuntimeError(str(result))

    return result


# --------------------------------------------------
# MAIN
# --------------------------------------------------

def main():

    cfg = load_json(CONFIG_PATH, None)

    if cfg is None:
        raise RuntimeError("Не найден config.json")

    history = load_json(HISTORY_PATH, [])

    forced_topic = os.environ.get("FORCE_TOPIC")

    topic = forced_topic or pick_topic(cfg, history)

    log.info("Выбрана тема: %s", topic)

    text = generate_post(
        cfg,
        topic,
        history
    )

    print("\n" + "=" * 50)
    print("ТЕМА:", topic)
    print("=" * 50)
    print(text)
    print("=" * 50 + "\n")

    if os.environ.get("DRY_RUN") == "1":
        log.info("DRY_RUN: публикация отменена")
        return

    image_path = os.environ.get("POST_IMAGE_PATH") or None

    result = send_to_telegram(
        text,
        image_path=image_path
    )

    history.append({
        "date": datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        ),
        "topic": topic,
        "text": text,
        "message_id": result["result"]["message_id"]
    })

    save_json(
        HISTORY_PATH,
        history[-100:]
    )

    log.info("Публикация успешно отправлена")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        log.exception("Ошибка выполнения: %s", error)
        sys.exit(1)

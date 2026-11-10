#!/usr/bin/env python3
"""Автопостер для Telegram-канала: генерирует пост через Claude и публикует его."""
import json
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from anthropic import Anthropic

ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "config.json"
HISTORY_PATH = ROOT / "history.json"

TG_LIMIT = 4096


def load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def pick_topic(cfg: dict, history: list) -> str:
    topics = cfg["topics"]
    used = [h["topic"] for h in history]
    # берём темы, которые не использовались последними N раз
    cooldown = min(len(topics) - 1, cfg.get("topic_cooldown", 5))
    recent = set(used[-cooldown:]) if cooldown > 0 else set()
    pool = [t for t in topics if t not in recent] or topics
    return random.choice(pool)


def build_prompt(cfg: dict, topic: str, history: list) -> str:
    last_posts = "\n---\n".join(h["text"][:300] for h in history[-3:]) or "(пока нет)"
    return f"""Ты ведёшь Telegram-канал.

О канале: {cfg['channel_description']}
Аудитория: {cfg['audience']}
Тон: {cfg['tone']}
Язык: {cfg['language']}

Тема поста: {topic}

Правила:
- длина до {cfg.get('max_chars', 900)} символов
- цепляющая первая строка, дальше по делу, без воды
- в конце короткий призыв: {cfg['cta']}
- форматирование ТОЛЬКО Telegram-HTML: <b>, <i>, <u>, <code>, <a href="...">. Никакого markdown
- эмодзи умеренно ({cfg.get('emoji', 'немного')})
- не повторяй структуру и формулировки прошлых постов

Последние посты (чтобы не повторяться):
{last_posts}

Выведи только текст поста, без пояснений и кавычек."""


def generate_post(cfg: dict, topic: str, history: list) -> str:
    client = Anthropic()  # берёт ANTHROPIC_API_KEY из env
    resp = client.messages.create(
        model=cfg.get("model", "claude-sonnet-5-5"),
        max_tokens=1500,
        messages=[{"role": "user", "content": build_prompt(cfg, topic, history)}],
    )
    text = resp.content[0].text.strip()
    return text[:TG_LIMIT]


def send_to_telegram(text: str, image_path: str | None = None) -> dict:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    base = f"https://api.telegram.org/bot{token}"

    def call(parse_mode):
        payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        return requests.post(f"{base}/sendMessage", json=payload, timeout=30)

    r = call("HTML")
    if not r.ok:
        # если сломалась HTML-разметка, шлём простым текстом
        print(f"HTML не прошёл ({r.status_code}): {r.text}", file=sys.stderr)
        r = call(None)
    r.raise_for_status()
    return r.json()


def main():
    cfg = load_json(CONFIG_PATH, None)
    if cfg is None:
        sys.exit("Нет config.json")
    history = load_json(HISTORY_PATH, [])

    topic = os.environ.get("FORCE_TOPIC") or pick_topic(cfg, history)
    text = generate_post(cfg, topic, history)

    print(f"Тема: {topic}\n\n{text}\n")

    if os.environ.get("DRY_RUN") == "1":
        print("DRY_RUN: в Telegram не отправляю")
        return

    send_to_telegram(text)
    history.append(
        {
            "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "topic": topic,
            "text": text,
        }
    )
    HISTORY_PATH.write_text(
        json.dumps(history[-50:], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("Опубликовано")


if __name__ == "__main__":
    main()

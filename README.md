# Telegram автопостер

Раз в нужное время GitHub Actions запускает `post.py`: Claude пишет пост по случайной теме из `config.json`, бот публикует его в канал. История постов хранится в `history.json`, чтобы темы и формулировки не повторялись.

## Запуск за 5 минут

1. **Бот.** В @BotFather → `/newbot` → получи токен.
2. **Канал.** Добавь бота админом в канал с правом публикации.
3. **ID канала.** Для публичного канала это `@username`. Для приватного: перешли пост из канала боту @RawDataBot и возьми `chat.id` (вида `-100...`).
4. **Ключ Claude API.** console.anthropic.com → API Keys.
5. **GitHub.** Создай репозиторий (лучше приватный), залей туда содержимое папки.
6. **Secrets.** Settings → Secrets and variables → Actions → New repository secret:
   - `ANTHROPIC_API_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
7. **Проверка.** Actions → Telegram autopost → Run workflow → `dry_run = 1`. В логах увидишь сгенерированный пост без отправки. Потом запусти с `0`.

## Настройка

- **Расписание:** `cron` в `.github/workflows/post.yml` (время в UTC).
- **Темы, тон, CTA, длина:** `config.json`.
- **Своя тема разово:** Run workflow → поле `topic`.
- **Локальный тест:**
  ```bash
  pip install -r requirements.txt
  export ANTHROPIC_API_KEY=... DRY_RUN=1
  python post.py
  ```

## Заметки

- GitHub может задерживать cron на 5–30 минут, это нормально.
- В репозитории без активности больше 60 дней GitHub отключает расписание. Коммиты `history.json` от бота считаются активностью, так что обычно проблем нет.
- Если нужен домен (например, лендинг на GitHub Pages), это отдельная история, скажи, добавлю.

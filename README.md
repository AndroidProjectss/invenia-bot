# Invenia Support Bot

Бот поддержки Invenia на русском и кыргызском языках. Он отвечает только готовыми текстами из `data/faq.json`, помнит тему короткого диалога и передаёт неизвестные вопросы оператору.

Поддерживаются два канала:

- Telegram через long polling;
- WhatsApp через официальный Meta WhatsApp Cloud API webhook.

Все сообщения попадают в общую SQLite-базу и отображаются в отдельной панели оператора. В панели можно искать и фильтровать диалоги, отвечать вручную, включать или приостанавливать автоответ и закрывать обращения.

## Установка

Рекомендуется Python 3.11 или новее.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Минимальные настройки админки в `.env`:

```dotenv
ADMIN_PASSWORD=сложный-пароль
ADMIN_SECRET_KEY=длинная-случайная-строка
ADMIN_HOST=127.0.0.1
ADMIN_PORT=8080
```

Запуск всего одной командой:

```bash
python main.py start
```

Команда одновременно поднимает админку, frontend, backend, WhatsApp webhook и Telegram-бота. Если `TELEGRAM_BOT_TOKEN` пока не заполнен, Telegram пропускается, а остальная система продолжает работать. Остановка всех сервисов — `Ctrl+C`.

Панель откроется на `http://127.0.0.1:8080`. Проверка состояния доступна без авторизации на `/health`.

## Telegram

Добавьте токен и Telegram ID операторов:

```dotenv
TELEGRAM_BOT_TOKEN=123456:token
TELEGRAM_ADMIN_IDS=111111111,222222222
```

Отдельно Telegram можно запустить командой:

```bash
python main.py bot
```

Команда `/stats` доступна только ID из `TELEGRAM_ADMIN_IDS`. `/reset` забывает текущую тему пользователя. Диалоги Telegram автоматически появляются в админке.

## WhatsApp Cloud API

Создайте приложение Meta, подключите WhatsApp Cloud API и заполните:

```dotenv
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_VERIFY_TOKEN=
WHATSAPP_APP_SECRET=
WHATSAPP_GRAPH_VERSION=v21.0
```

В настройках Meta укажите публичный HTTPS webhook:

```text
https://ваш-домен/webhooks/whatsapp
```

Подпишитесь на событие `messages`. `WHATSAPP_VERIFY_TOKEN` должен совпадать со значением, указанным в Meta. Если задан `WHATSAPP_APP_SECRET`, каждое входящее событие проверяется по `X-Hub-Signature-256`.

Ручные ответы WhatsApp работают в пределах правил клиентского окна Meta. Для сообщений вне окна понадобятся одобренные шаблоны.

## Логика ответов

- ниже `0.28` — бот не угадывает ответ и помечает диалог «Нужен оператор»;
- от `0.28` до `0.50` — предлагает до трёх похожих вопросов;
- от `0.50` — сразу отправляет готовый ответ;
- после ручного ответа автоответ в этом диалоге приостанавливается, пока оператор не включит его снова.

Основная функция остаётся совместимой:

```python
from bot.answer import answer

answer("Балансымда канча акча бар?")
```

## Команды разработки

```bash
python main.py check
python main.py ask "Как проверить баланс?"
python main.py ask --chat demo "А сколько стоит?"
python -m unittest discover -s tests -v
```

По умолчанию база создаётся в `data/invenia.sqlite3`. Другой путь можно задать через `BOT_DB_PATH`. База и локальные журналы не коммитятся в Git, но содержат переписку клиентов и должны быть защищены резервным копированием и политикой доступа.

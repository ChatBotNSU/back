# Примеры

Готовые JSON-конфигурации ботов плюс два универсальных запускалки.

## Структура

```
examples/
├── README.md            — этот файл
├── run_local.py         — прогон без TG/Redis/MinIO, в одном процессе
├── run_telegram.py      — живой TG-поллинг, тоже в одном процессе
├── echo/
│   ├── chatbot.json
│   └── description.md
├── branching/
│   ├── chatbot.json
│   └── description.md
└── greeter/
    ├── chatbot.json
    ├── subgraph-classify.json   — отдельная копия сабграфа
    └── description.md
```

Каждый пример лежит в своей папке. В `chatbot.json` — полное тело бота, включая встроенные `subgraphs` (engine исполняет именно эту встроенную копию). Файл `subgraph-classify.json` в `greeter/` — отдельный артефакт того же сабграфа, который можно положить в библиотеку пользователя через `POST /api/v1/subgraph/subgraphs`. Это удобно, когда фронт загружает сабграф один раз и потом подставляет его содержимое в разные боты.

## Что у каждого внутри

- **echo** — минимум: `text_answer → set_message → send_message` в цикле. Бот повторяет последнее сообщение пользователя.
- **branching** — счётчик с порогом, разные ответы до и после 3-го сообщения. Условие живёт в главном графе через `condition`, без сабграфов.
- **greeter** — та же логика, что в `branching`, но классификация вынесена в сабграф `classify`. Сабграф принимает `counter` и `reply` по ссылке, переписывает `reply` в зависимости от `counter`.

Подробности каждого — в его `description.md`.

## Запуск без Telegram

```
python examples/run_local.py examples/<example-name> [сообщение ...]
```

Без аргументов после `<example-name>` скрипт прогонит пять дефолтных сообщений и распечатает ответы бота вместе с состоянием переменных. Можно передать свою последовательность.

Примеры:

```
python examples/run_local.py examples/echo
python examples/run_local.py examples/branching раз два три четыре
python examples/run_local.py examples/greeter привет "как дела" "ну и" "что"
```

Зависимости: только `pydantic`. Никакого Redis, MinIO, БД и Telegram-токенов не требуется.

## Запуск через живой Telegram

```
python examples/run_telegram.py examples/<example-name> <bot-token>
```

Скрипт поднимает aiogram-поллер и дёргает `Engine.execute` напрямую. Каждый Telegram-чат получает свой `ExecutionState`, ключ — `chat.id`. Состояние живёт в памяти процесса, после рестарта сбрасывается.

Это режим для отладки конкретного бота без поднятия `docker-compose` стека. Полная инсталляция (`db-service`, `admin-backend`, `execution-engine`, `telegram-execution`, MinIO, Redis) описана в корневом `readme.md`.

Зависимости: `pydantic`, `aiogram>=3.23`.

## Свой пример

Минимальный шаблон новой папки:

```
examples/my-bot/
├── chatbot.json
└── description.md
```

В `chatbot.json` обязательны поля `bot_id`, `bot_name`, `graph` (с `root` и `nodes`). Поле `subgraphs` опциональное — словарь `имя → Subgraph`. Полный список типов узлов и контракт сабграфов — в корневом `readme.md` раздел «Модель данных».

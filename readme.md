# Chatbot Platform — backend

Платформа для конструирования чат-ботов из графов узлов с поддержкой сабграфов как переиспользуемых функций. Бот описывается одним JSON-документом; рантайм-движок ходит по нему до ближайшего узла отправки и возвращает сообщение в нужный канал (Telegram, превью в UI).

## Содержание

- [Архитектура](#архитектура)
- [Модель данных](#модель-данных)
- [Семантика исполнения](#семантика-исполнения)
- [Сабграфы](#сабграфы)
- [Динамическая типизация переменных](#динамическая-типизация-переменных)
- [HTTP API](#http-api)
- [Запуск](#запуск)
- [Примеры](#примеры)
- [Тесты](#тесты)
- [Известные ограничения](#известные-ограничения)

---

## Архитектура

| Сервис | Порт хоста | Роль |
| --- | --- | --- |
| `db-service` | `1488` | Единственный, кто пишет в Postgres. Хранит метаданные: `User`, `ChatBot(id, name, description, user_id)`, `TelegramExecution`. |
| `administration-backend` | `8080` | FastAPI для UI/CLI пользователей. Auth (JWT), CRUD ботов, CRUD сабграфов. Тела ботов и сабграфов льёт в MinIO. |
| `minio` | `9000` | S3-совместимое хранилище для JSON-ов ботов, сабграфов и состояний исполнения. |
| `redis` | `6379` | Streams для общения с движком: `execution_requests` (вход) и `execution_responses` (выход). |
| `execution-engine` | — | Тянет `ExecutionRequest` из `execution_requests`, читает чат-бота из MinIO, прогоняет его до отправки сообщения, кладёт `ExecutionResponse` в `execution_responses`. Кэширует `Engine` в памяти по `execution_id`, поэтому состояние графа переживает много turn-ов диалога. |
| `telegram-execution` | `8082` | Аiogram-поллер. По эндпоинту `/assigne` принимает пару `<TG-токен, chatbot_id>`, заводит фоновый polling и для каждого входящего TG-сообщения отправляет `ExecutionRequest` в Redis, ждёт ответ и пишет его пользователю. |
| `preview-execution` | `8081` | То же, что telegram-execution, но для UI-превью (источник входящих — HTTP, а не TG). |
| `py-runner` | — | Изолированный сэндбокс под Python-скрипты узла `script_execution`. |

Движок ничего не знает про БД или пользователей: он работает с парой `(chatbot_id, execution_id)`. Авторизацию и владение проверяет `administration-backend`, который перед заливкой в MinIO решает, имеет ли пользователь право трогать данного бота.

## Модель данных

Описание в нотации Pydantic; именно эти классы лежат как в `execution-engine/src/models/`, так и в `administration-backend/backend/models/` (две копии умышленно — сервисы могут эволюционировать отдельно, но поля должны совпадать).

### Chatbot

```python
class Chatbot(BaseModel):
    graph: Graph
    subgraphs: dict[str, Subgraph] = {}   # имя сабграфа -> определение
    bot_id: int
    bot_name: str
```

JSON хранится в MinIO под ключом `chatbot-{bot_id}.json`. Никаких `variables` в Chatbot не объявляется — переменные создаются динамически по ходу исполнения.

### Subgraph

```python
class Subgraph(BaseModel):
    name: str
    inputs: list[str] = []      # имена параметров, обязательных при вызове
    exits: list[str]            # именованные точки возврата
    graph: Graph                # собственно тело — отдельный граф с root и nodes
```

Сабграф — это библиотечная сущность пользователя. Хранится в MinIO отдельно (`subgraph-{user_id}-{name}.json`), управляется через `/api/v1/subgraph/*`. Когда фронт собирает бота, он либо встраивает сабграф в `Chatbot.subgraphs` (фактическая копия — её и исполняет движок), либо использует библиотечную версию как заготовку.

### Graph

```python
class Graph(BaseModel):
    root: str                            # id первого узла
    nodes: dict[str, NodeType]           # id узла -> определение
```

Граф — это словарь узлов с указателем на корень. Каждый узел кроме терминальных хранит `next_node_id` (или их набор для условных переходов).

### Узлы

Все узлы дискриминируются по полю `type`. Полный список:

| `type` | Поля | Поведение |
| --- | --- | --- |
| `set_variable` | `assigned_variable`, `operation` (`=`, `+=`, `-=`, `*=`, `/=`, `%=`), `operand` (число или строка), `next_node_id` | `=` создаёт/перезаписывает переменную с типом операнда. `+=` пробует числовое сложение; если хотя бы одно из значений не парсится как число, делает строковую конкатенацию. Остальные арифметические — строго числовые. На `+=` к необъявленной переменной возвращается ошибка. |
| `text_answer` | `assigned_variable`, `next_node_id` | Записывает `in_message.text` входящего сообщения в указанную переменную (строкой). Создаёт переменную, если её не было. |
| `file_answer` | `assigned_variable`, `next_node_id` | Записывает путь первого файла из входящего сообщения. Приоритет: `files` → `audios` → `images`. Если ничего нет — ошибка. |
| `set_message` | `text`, `audios`, `images`, `files`, `choise_options`, `next_node_id` | Готовит исходящее сообщение. `text` форматируется через `str.format(**variables)` — все переменные текущего скоупа доступны как `{name}`. Не отправляет, только накапливает. |
| `send_message` | `next_node_id` | Выставляет флаг отправки. Движок завершает текущий turn и возвращает накопленный `OutMessage`. На следующий turn исполнение продолжается с `next_node_id`. |
| `wait` | `wait_time` (секунды), `next_node_id` | `asyncio.sleep`. Блокирует turn, не отправляя сообщение. |
| `condition` | `branches: list[Branch]`, `default_next_node_id` | Каждая `Branch` — это `{condition: {variable_left, operation, variable_right}, next_node_id}`. Операции: `==`, `!=`, `<`, `>`, `<=`, `>=`. Ветки проверяются по порядку; первая совпавшая фиксируется. Если ни одна не сработала — переход в `default_next_node_id`. Операнды условия — **имена переменных**, не литералы; для констант заводите вспомогательную переменную через `set_variable`. |
| `script_execution` | `script` (Python), `next_node_id` | Запускает код в `py-runner`. Все переменные текущего скоупа доступны в коде; то, что код в них присвоил, возвращается обратно в скоуп. |
| `subgraph_call` | `subgraph_name`, `input_bindings: dict[str, str]`, `exit_next_nodes: dict[str, str]` | Вызов сабграфа. `input_bindings` — `{имя_параметра_сабграфа: имя_переменной_caller'а}`. По возврату caller-переменные обновятся значениями из сабграфа (by-reference). `exit_next_nodes` — куда идти после каждого именованного exit'а. См. раздел [Сабграфы](#сабграфы). |
| `subgraph_exit` | `exit_label` | Терминал сабграфа. Поп фрейма, прокидывание by-reference значений в caller, переход на `exit_next_nodes[exit_label]` родительского узла. |

### ExecutionState

```python
class Frame(BaseModel):
    subgraph_name: Optional[str] = None       # None => главный граф
    executing_node_id: str
    variable_values: dict[str, str | float] = {}
    exit_map: dict[str, str] = {}             # exit_label -> next_node_id caller'а
    output_bindings: dict[str, str] = {}      # имя в сабграфе -> имя в caller'е (для write-back)

class ExecutionState(BaseModel):
    bot_id: int
    execution_id: int
    call_stack: list[Frame]                   # снизу — главный граф; сверху — текущий
```

Состояние сериализуется как обычный pydantic-объект, спокойно roundtrip'ит через JSON. Хранится в памяти `EngineFactory` (кэш по `execution_id`); при необходимости можно сохранять между перезапусками — у `S3Client.upload_execution` есть для этого место в MinIO.

### Сообщения

```python
class Message(BaseModel):
    text: str | None = None
    images: list[str] | None = None
    audios: list[str] | None = None
    files: list[str] | None = None

class InMessage(Message):
    restart_command: bool | None = None

class OutMessage(Message):
    choise_options: list[str] | None = None   # кнопки/реплики для выбора
```

## Семантика исполнения

Один turn (один входящий `InMessage`):

1. Движок берёт верхний фрейм стека.
2. Резолвит граф: для главного фрейма это `chatbot.graph`, для сабграф-фрейма — `chatbot.subgraphs[frame.subgraph_name].graph`.
3. Достаёт узел по `frame.executing_node_id`, выполняет соответствующий executor.
4. Executor читает/пишет ТОЛЬКО `frame.variable_values` верхнего фрейма (изоляция скоупов). Обновляет `frame.executing_node_id`.
5. Если установлен `send_message_flag` — turn заканчивается, накопленный `OutMessage` возвращается, состояние сохраняется. Иначе — цикл повторяется.

Между turn-ами состояние полностью сохраняется (`call_stack`, текущий узел, все переменные). Engine является stateful-сущностью, ключуется по `execution_id`.

`FailExecutor` — особый случай. Любой executor может его дёрнуть, тогда в `OutMessage.text` пишется диагностическое сообщение, флаг отправки выставляется, turn заканчивается. Из-за этого пользователь получает в чат readable ошибку вместо молчания.

## Сабграфы

Сабграф — это **функция с pass-by-reference на объявленных параметрах**.

- Сабграф объявляет `inputs: list[str]` — имена параметров. Это контракт сабграфа.
- Caller в узле `subgraph_call` ОБЯЗАН задать привязку для каждого имени из `inputs`: `input_bindings = {<sub_input>: <caller_var>}`. Caller-переменная должна существовать на момент вызова. Если хоть один input не привязан — `FailExecutor`.
- При входе в сабграф создаётся новый `Frame` с локальным скоупом. В него копируются ровно те переменные, что упомянуты в `input_bindings`, под именами параметров сабграфа. Всё остальное — пусто.
- Внутри сабграфа можно создавать сколько угодно новых переменных (`set_variable`, `script_execution` и т.д.). Они живут только в этом фрейме.
- Когда сабграф доходит до `subgraph_exit`, движок берёт значения, лежащие под именами `inputs` в его фрейме (если он их менял), и пишет обратно в caller-переменные по той же `input_bindings`. Это и есть «выход» — отдельной концепции `outputs` нет.
- `subgraph_exit` указывает `exit_label`. Caller заранее перечислил все возможные exit'ы и куда из каждого идти: `exit_next_nodes = {exit_label: caller_next_node_id}`. Контроль возвращается в caller, текущий узел — `exit_next_nodes[exit_label]`.

Иллюстрация:

```
caller:  counter=2, reply=""
    └── subgraph_call classify with input_bindings={"counter":"counter","reply":"reply"}
            ↓
sub frame: counter=2 (read-only с т.зр. caller'а, изменения летят обратно), reply=""
    s_thr:   thr = 3.0            (локальная переменная, в caller не попадёт)
    s_cond:  counter < thr        (2 < 3 → true)
    s_short: reply = "новенький"  (модификация input'а, прилетит в caller)
    s_exit:  exit "done"
            ↓
caller:  counter=2, reply="новенький"     ← thr НЕ ЕСТЬ в этом скоупе
    └── продолжает с n_msg (по exit_next_nodes["done"] = "n_msg")
```

Сабграфы можно вкладывать в сабграфы — движок поддерживает произвольную глубину стека.

## Динамическая типизация переменных

Никаких объявлений переменных не нужно — ни в `Chatbot`, ни в `Subgraph`. Любой `set_variable` с операцией `=` создаёт переменную с типом операнда (число или строка). Любые `text_answer`/`file_answer` создают строковую переменную.

Семантика операций:

- `=` — присваивание, тип берётся из операнда.
- `+=` — если оба значения можно интерпретировать как число (`int`, `float` или строка типа `"5.0"`), будет числовое сложение. Иначе строковая конкатенация. Если LHS не определён — fail.
- `-=`, `*=`, `/=`, `%=` — оба значения коэрсятся в число; если не выходит — fail. Деление и модуль на ноль — fail.
- `condition` сравнивает значения. `==`/`!=` сначала пробуют сравнение «как есть», потом числовое. `<`, `>`, `<=`, `>=` сразу пробуют числовое; если коэрсия не прошла — fail.

В `script_execution` все переменные текущего скоупа уходят в песочницу как `int` (если значение целочисленное) или `str`. После выполнения скрипта возвращённые значения попадают в скоуп.

## HTTP API

### administration-backend (`:8080`)

#### Auth

- `POST /api/v1/auth/token` — OAuth2-форма `username`+`password`. Возвращает `{access_token, token_type}`. Токен — JWT.

Все ниже — требуют `Authorization: Bearer <token>`.

#### Чат-боты

| Метод | Путь | Описание |
| --- | --- | --- |
| `GET` | `/api/v1/chatbot/chatbots` | Список ботов текущего пользователя (метаданные из db-service). |
| `POST` | `/api/v1/chatbot/chatbots` | Тело — `ChatbotUnassigned` (Chatbot без `bot_id`). Создаёт запись в БД, заливает JSON в MinIO. Возвращает `Chatbot` с присвоенным `bot_id`. |
| `GET` | `/api/v1/chatbot/chatbot/{bot_id}` | Тело бота из MinIO. |
| `POST` | `/api/v1/chatbot/chatbot/{bot_id}` | Перезаписывает тело бота в MinIO. |
| `DELETE` | `/api/v1/chatbot/chatbot/{bot_id}` | Удаляет метадату в БД. |

#### Сабграфы

Сабграфы — это просто JSON-файлы в S3, прикреплённые к пользователю. В БД ничего не лежит.

| Метод | Путь | Описание |
| --- | --- | --- |
| `GET` | `/api/v1/subgraph/subgraphs` | Список имён сабграфов текущего пользователя. |
| `POST` | `/api/v1/subgraph/subgraphs` | Тело — `Subgraph`. Создаёт. 409, если имя занято. |
| `GET` | `/api/v1/subgraph/subgraph/{name}` | Тело сабграфа. |
| `PUT` | `/api/v1/subgraph/subgraph/{name}` | Перезаписывает. `name` в теле должен совпасть с путём (иначе 400). |
| `DELETE` | `/api/v1/subgraph/subgraph/{name}` | Удаляет. |

Изоляция per-user обеспечена ключом в MinIO: `subgraph-{user_id}-{name}.json`. Пользователь B не увидит и не сможет прочитать сабграф пользователя A.

### telegram-execution (`:8082`)

| Метод | Путь | Описание |
| --- | --- | --- |
| `POST` | `/api/v1/telegram/assigne?token=...&chatbot_id=...` | Регистрирует пару `(TG-токен, chatbot_id)`. Если токен ещё не известен — поднимает aiogram-поллер. Если известен — обновляет привязку без перезапуска поллера. |
| `GET` | `/api/v1/telegram/get_all` | Все зарегистрированные пары `{token: chatbot_id}`. |
| `GET` | `/api/v1/telegram/get/{token}` | `chatbot_id` для конкретного токена. |

Когда aiogram получает TG-сообщение, он строит `ExecutionRequest(execution_id=chat.id, chatbot_id=<привязанный>, message=...)` и кладёт его в `execution_requests`. Ждёт ответ из `execution_responses` (матчинг по `execution_id`) и отвечает пользователю в TG.

## Запуск

### Полный стек через docker-compose

```bash
docker compose up -d db
cd db-service
pdm install
pdm run makemig
pdm run migrate
cd ..

# опционально — белый список пользователей
docker compose up --build populate_whitelist

docker compose up --build
```

После старта:

- `localhost:8080/docs` — Swagger administration-backend.
- `localhost:8081/docs` — preview-execution.
- `localhost:8082/docs` — telegram-execution.
- `localhost:9001` — консоль MinIO.

Чтобы привязать бота к Telegram:

```bash
curl -X POST 'http://localhost:8082/api/v1/telegram/assigne?token=<BOT_TOKEN>&chatbot_id=<ID>'
```

### Локальный прогон без стека

В корне есть папка [`examples/`](./examples/) с готовыми ботами и двумя скриптами:

```bash
# в одном процессе, без TG/Redis/MinIO
python examples/run_local.py examples/greeter

# живой TG-поллинг + Engine.execute в одном процессе
python examples/run_telegram.py examples/greeter <BOT_TOKEN>
```

Зависимости минимальные: `pydantic`, для TG-варианта — `aiogram>=3.23`. Никакой инфры разворачивать не надо. Это нужно для быстрой отладки бота или сабграфа без полной установки.

## Примеры

См. [`examples/README.md`](./examples/README.md). Кратко:

- **echo** — минимальный цикл `text_answer → set_message → send_message`.
- **branching** — счётчик с условием в главном графе.
- **greeter** — та же логика, но классификация вынесена в сабграф `classify`. Демонстрирует by-reference и изоляцию локальных переменных сабграфа.

## Тесты

```
execution-engine/tests/        — Engine.execute напрямую: сабграфы, by-ref, dynamic typing
administration-backend/tests/  — TestClient + in-memory MinIO: chatbot и subgraph API
telegram-execution/tests/      — TestClient: /assigne и /get с замоканным aiogram
```

Запуск из любой папки сервиса:

```
pytest tests/
```

## Известные ограничения

1. **Литералы в `condition`** не поддерживаются: оба операнда — имена переменных. Чтобы сравнить с константой, заведите вспомогательную переменную через `set_variable`.
2. **Одно вложение по файлам**: `file_answer` берёт только первый файл из входящего сообщения. Если приходит несколько — обрабатывается приоритет `files → audios → images`, остальные игнорируются.
3. **Модели задублированы** между `execution-engine` и `administration-backend`. Изменения в схеме нужно зеркалить вручную в обе папки (`models/nodes.py`, `models/chatbot.py`, `models/execution_state.py`, `models/message.py`).
4. **`telegram-execution/src/controller/__init__.py`** дёргает `asyncio.create_task` на уровне импорта модуля — это работает только если импорт выполняется в контексте уже запущенного event loop. Под uvicorn срабатывает, но в произвольном CLI/тестовом контексте упадёт с `RuntimeError: no running event loop`. Нужна правка: вынести в startup-handler FastAPI.
5. **Нет авторизации на `/assigne`** в telegram-execution. Любой, кто видит порт сервиса, может зарегистрировать произвольный TG-токен на любой `chatbot_id`. Для прода нужно завернуть в проверку JWT (как в administration-backend).

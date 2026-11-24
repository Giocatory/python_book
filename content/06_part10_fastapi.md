# Глава 46. ASGI, серверы и первое приложение

**Цель главы:** понять, чем веб-фреймворк отличается от веб-сервера, и собрать правильно структурированное приложение.

## 46.1. WSGI против ASGI

**WSGI** (Flask, классический Django) — синхронный контракт: вызываемый объект принимает `environ` и `start_response`. Пока обработчик работает, воркер занят целиком. Тысяча медленных клиентов требует тысячи воркеров или потоков.

**ASGI** — асинхронный контракт из трёх аргументов: `scope` (метаданные соединения), `receive` (поток входящих событий), `send` (поток исходящих). Один процесс держит тысячи соединений, потому что во время ожидания I/O обслуживает другие. Кроме HTTP поддерживает WebSocket и lifespan.

```python
async def app(scope, receive, send):
    assert scope["type"] == "http"
    await send({"type": "http.response.start", "status": 200,
                "headers": [(b"content-type", b"text/plain")]})
    await send({"type": "http.response.body", "body": b"hello"})
```

> [!NOTE] FastAPI — это просто ASGI-приложение (объект с `__call__(scope, receive, send)`). Uvicorn — сервер, который принимает TCP-соединения, парсит HTTP и вызывает это приложение. Понимание этого разделения снимает половину вопросов о деплое.

## 46.2. Серверы и воркеры

- **Uvicorn** — стандарт де-факто: uvloop + httptools, быстрый парсинг HTTP.
- **Hypercorn** — поддержка HTTP/2 и trio.
- **Granian** — сервер на Rust, конкурент по производительности.

```bash
uvicorn finance.api.main:app --reload --host 0.0.0.0 --port 8000   # разработка
uvicorn finance.api.main:app --workers 4 --host 0.0.0.0            # несколько процессов
```

Классическая связка для ВМ — Gunicorn как менеджер процессов плюс воркеры Uvicorn (пакет `uvicorn-worker`; встроенный модуль `uvicorn.workers` устарел). В Kubernetes чаще запускают **один процесс на контейнер** и масштабируют репликами: оркестратор уже умеет перезапускать и балансировать.

> [!WARNING] `--reload` только для разработки: он следит за файлами и перезапускает процесс. И биндинг на `127.0.0.1` внутри контейнера сделает сервис недоступным извне — нужен `0.0.0.0` (глава 39).

Число воркеров для CPU-нагрузки — по числу ядер; для I/O-нагрузки один async-процесс обслуживает много соединений, а воркеры нужны, чтобы утилизировать все ядра.

## 46.3. Первое приложение

```python
from fastapi import FastAPI, status
from finance.api.schemas import OperationCreate, OperationRead

app = FastAPI(title="Finance API", version="1.0.0")


@app.post("/operations", response_model=OperationRead, status_code=status.HTTP_201_CREATED)
async def create_operation(payload: OperationCreate) -> OperationRead:
    ...
```

`response_model` — не формальность: он **фильтрует** выход (не даст утечь полю `password_hash`), валидирует его и генерирует схему OpenAPI. Аннотация возврата и `response_model` должны совпадать по смыслу.

## 46.4. Параметры запроса

```python
from typing import Annotated
from fastapi import Cookie, Header, Path, Query


@app.get("/accounts/{account_id}/operations")
async def list_operations(
    account_id: Annotated[int, Path(gt=0)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query()] = None,
    x_request_id: Annotated[str | None, Header()] = None,
    session: Annotated[str | None, Cookie()] = None,
): ...
```

Правило FastAPI: аннотированный Pydantic-моделью параметр — тело запроса; скалярный параметр, совпадающий с именем в пути — path-параметр; остальные скаляры — query. Явные `Path`/`Query`/`Header` снимают двусмысленность и добавляют ограничения.

> [!TIP] Всегда ставь верхнюю границу на `limit`. Эндпоинт без ограничения — это готовый вектор отказа в обслуживании (глава 50).

## 46.5. Ответы и статусы

```python
from fastapi.responses import ORJSONResponse, StreamingResponse, FileResponse

app = FastAPI(default_response_class=ORJSONResponse)   # быстрый JSON на Rust
```

| Класс | Когда |
|---|---|
| `JSONResponse` / `ORJSONResponse` | обычный JSON |
| `StreamingResponse` | отдача большого файла или CSV-выгрузки потоком |
| `FileResponse` | статический файл с поддержкой Range |
| `RedirectResponse` | перенаправление |
| `Response(status_code=204)` | пустой ответ на DELETE |

> [!WARNING] При `204 No Content` тело запрещено стандартом. Возвращай `Response(status_code=204)`, а не `None` с моделью ответа.

## 46.6. Загрузка файлов без переполнения памяти

```python
from fastapi import File, UploadFile

MAX_SIZE = 20 * 1024 * 1024


@app.post("/imports")
async def import_csv(file: Annotated[UploadFile, File()]):
    received = 0
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        while chunk := await file.read(1024 * 1024):
            received += len(chunk)
            if received > MAX_SIZE:
                raise FileTooLarge(MAX_SIZE)
            tmp.write(chunk)
    ...
```

`UploadFile` использует spooled-буфер (часть в памяти, дальше на диск), но **проверка размера и типа — твоя ответственность**. Читать целиком `await file.read()` на большом файле нельзя (глава 32). Проверка magic bytes — глава 50.

## 46.7. Роутеры и структура проекта

```
src/finance/
    api/
        main.py          # сборка приложения
        deps.py          # зависимости
        routers/
            operations.py
            accounts.py
            auth.py
        schemas/         # DTO Pydantic
    services/            # сценарии использования
    domain/              # модели, правила, исключения
    infra/               # SQLAlchemy, Redis, HTTP-клиенты
    core/                # настройки, логи, безопасность
```

```python
router = APIRouter(prefix="/operations", tags=["operations"])
app.include_router(router, prefix="/api/v1")
```

Зависимости направлены внутрь: `api` знает о `services`, `services` о `domain`, `domain` не знает ни о ком. Инфраструктура подключается через порты (глава 26). Это заготовка Clean Architecture из главы 58.

## 46.8. OpenAPI

FastAPI генерирует `/docs` (Swagger UI), `/redoc` и `/openapi.json` из аннотаций и моделей. Улучшай контракт: `tags`, `summary`, `description` (берётся из docstring), `responses={404: {"model": ProblemDetails}}`, `operation_id` для генерации клиентов.

> [!WARNING] В публичном продакшене закрывай документацию: `FastAPI(docs_url=None, redoc_url=None, openapi_url=None)` или отдавай её за аутентификацией. Открытая схема — карта твоей攻击 поверхности.

## 46.9. Контрольные вопросы

1. Чем ASGI отличается от WSGI по контракту?
2. Что делает `response_model` помимо документации?
3. Почему в контейнере нужен `0.0.0.0`?
4. Как FastAPI решает, что параметр — тело, а что — query?
5. Зачем ограничивать `limit`?

## 46.10. Практика

> [!TASK] Подними API сквозного проекта: роутеры `accounts`, `operations`, `reports` под `/api/v1`, DTO, `response_model` везде, keyset-пагинация с `cursor`, потоковый импорт CSV с лимитом размера, `ORJSONResponse` по умолчанию. Проверь `/docs` и убедись, что ни одна внутренняя сущность не «протекает» в ответ.

---

# Глава 47. Pydantic v2: валидация и сериализация

**Цель главы:** сделать границу системы местом, где данные гарантированно корректны, а внутри домена работать только с проверенными типами.

## 47.1. Что делает Pydantic

Три задачи: **парсинг** (приведение внешних форматов к типам), **валидация** (проверка правил), **сериализация** (превращение в JSON). Ядро `pydantic-core` написано на Rust, поэтому v2 быстрее v1 в разы.

> [!NOTE] Разделение ответственности: Pydantic — на границе (HTTP, конфиг, очереди), dataclass — внутри домена (глава 25). Не тащи Pydantic-модели в бизнес-логику: это связывает домен с библиотекой и HTTP-семантикой.

## 47.2. BaseModel и ConfigDict

```python
from pydantic import BaseModel, ConfigDict


class OperationRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,        # строить из ORM-объекта по атрибутам
        str_strip_whitespace=True,
        extra="forbid",              # лишние поля — ошибка, а не игнор
        frozen=True,                 # неизменяемость и хэшируемость
    )

    id: int
    amount_minor: int
    category: str
```

`extra="forbid"` на входных DTO — прямая защита от mass assignment (глава 50): клиент не сможет протолкнуть `is_admin: true`.

## 47.3. Field и Annotated

```python
from typing import Annotated
from pydantic import Field

Money = Annotated[int, Field(ge=0, le=10**12, description="Сумма в копейках")]
CategoryCode = Annotated[str, Field(min_length=2, max_length=32, pattern=r"^[a-z_]+$")]


class OperationCreate(BaseModel):
    account_id: Annotated[int, Field(gt=0)]
    amount_minor: Money
    category: CategoryCode
    comment: Annotated[str, Field(max_length=500)] = ""
```

Стиль v2 — `Annotated[тип, Field(...)]`: ограничения живут рядом с типом и переиспользуются через алиас. Полезные параметры: `alias`, `validation_alias`, `serialization_alias`, `examples`, `exclude`, `repr=False` для секретов.

## 47.4. Валидаторы

```python
from pydantic import field_validator, model_validator


class TransferCreate(BaseModel):
    source_id: int
    target_id: int
    amount_minor: int

    @field_validator("amount_minor", mode="after")
    @classmethod
    def positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Сумма должна быть положительной")
        return v

    @model_validator(mode="after")
    def different_accounts(self) -> "TransferCreate":
        if self.source_id == self.target_id:
            raise ValueError("Счета должны различаться")
        return self
```

`mode="before"` — до приведения типа (например, разобрать строку `"1 500,00"`), `mode="after"` — после. `@model_validator` видит всю модель и проверяет межполевые инварианты.

> [!WARNING] Валидатор не должен ходить в БД или сеть: он вызывается на каждый запрос, ломает тестируемость и создаёт скрытые N+1. Проверка существования счёта и прав — задача сервисного слоя.

## 47.5. Сериализация

```python
from pydantic import computed_field, field_serializer


class OperationRead(BaseModel):
    amount_minor: int

    @field_serializer("amount_minor")
    def as_decimal_string(self, v: int) -> str:
        return f"{v / 100:.2f}"

    @computed_field
    @property
    def direction(self) -> str:
        return "income" if self.amount_minor > 0 else "expense"


obj.model_dump(mode="json", exclude_none=True, by_alias=True)
obj.model_dump_json()
OperationCreate.model_validate(payload)
OperationCreate.model_validate_json(raw_bytes)
```

`mode="json"` приводит `Decimal`, `datetime`, `UUID` к JSON-совместимым видам. Деньги отдавай строкой или копейками — никогда float (главы 7, 33).

## 47.6. DTO: разные модели для разных операций

| Модель | Назначение | Особенность |
|---|---|---|
| `UserCreate` | регистрация | принимает `password`, не возвращает его |
| `UserUpdate` | PATCH | все поля опциональны, whitelist полей |
| `UserRead` | ответ | нет `password_hash`, есть вычисляемые поля |
| `UserInDB` | внутренняя | полная запись |

Одна модель «на всё» неизбежно приводит либо к утечке полей, либо к невозможности их передать. Разделение DTO — не бюрократия, а граница безопасности.

Для PATCH важно отличать «поле не прислали» от «прислали null»: используй `model_dump(exclude_unset=True)`.

## 47.7. Discriminated unions

```python
from typing import Annotated, Literal
from pydantic import Field


class Income(BaseModel):
    kind: Literal["income"] = "income"
    source: str


class Expense(BaseModel):
    kind: Literal["expense"] = "expense"
    category: str


Operation = Annotated[Income | Expense, Field(discriminator="kind")]


class Batch(BaseModel):
    items: list[Operation]
```

Pydantic выбирает вариант по значению поля-дискриминатора, а не перебором: это быстро и даёт внятные ошибки. Идеально для полиморфных событий и типов операций.

## 47.8. TypeAdapter, RootModel и настройки

```python
from pydantic import RootModel, TypeAdapter

adapter = TypeAdapter(list[OperationCreate])   # валидация без BaseModel
items = adapter.validate_python(raw_list)


class Ids(RootModel[list[int]]):
    pass
```

```python
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_nested_delimiter="__", extra="ignore")
    database_url: str
    jwt_secret: SecretStr
    access_ttl_seconds: int = 900
    log_level: str = "INFO"
```

`SecretStr` скрывает значение в `repr` и логах — обязательный тип для паролей и ключей.

## 47.9. Интеграция с ORM

```python
account = await session.get(Account, 42)          # связи lazy="raise"
dto = AccountRead.model_validate(account)         # from_attributes=True
```

> [!WARNING] `model_validate(orm_obj)` обращается к атрибутам объекта. Если связь не подгружена, ленивая загрузка в async упадёт с `MissingGreenlet` (глава 44). Загружай связи явно (`selectinload`) **до** сериализации, а после commit используй `expire_on_commit=False`.

## 47.10. Контрольные вопросы

1. Чем парсинг отличается от валидации?
2. Зачем `extra="forbid"` на входных схемах?
3. Когда нужен `mode="before"`?
4. Как отличить «не прислали» от «прислали null» в PATCH?
5. Что даёт discriminated union?

## 47.11. Практика

> [!TASK] Спроектируй DTO сквозного проекта: `OperationCreate`/`Read`/`Update`, `TransferCreate` с межполевым валидатором, `Batch` с discriminated union типов операций, `Settings` с `SecretStr`. Деньги — копейки на входе и строка на выходе. Добавь тесты на `ValidationError` для 10 некорректных payload и убедись, что `password_hash` не попадает ни в один ответ.

---

# Глава 48. Архитектура FastAPI: DI, lifespan, ошибки

**Цель главы:** собрать приложение, где ресурсы управляются явно, ошибки выглядят одинаково, а повторный запрос не списывает деньги дважды.

## 48.1. Dependency Injection

```python
from typing import Annotated
from fastapi import Depends


async def get_uow(request: Request) -> AsyncIterator[UnitOfWork]:
    async with SqlAlchemyUnitOfWork(request.app.state.session_factory) as uow:
        yield uow


UowDep = Annotated[UnitOfWork, Depends(get_uow)]


@router.post("/transfers", status_code=201)
async def transfer(payload: TransferCreate, uow: UowDep) -> TransferRead:
    return await transfer_service(uow, payload)
```

Зависимости бывают функциями, классами и генераторами; они образуют цепочку (аутентификация → пользователь → права → сессия), кэшируются в рамках одного запроса (`use_cache=True`) и переопределяются в тестах (глава 51).

> [!NOTE] DI — главная причина выбирать FastAPI. Он делает зависимости явными в сигнатуре, а не спрятанными в глобальных импортах, и тем самым реализует DIP из главы 26 без всякого контейнера.

## 48.2. yield-зависимости и ресурсы

Код до `yield` — получение ресурса, после — освобождение. Транзакцией управляй явно в UoW или сервисе, а зависимость пусть только закрывает ресурс.

> [!WARNING] Не рассчитывай, что код после `yield` увидит исключения обработчика или что ресурс останется доступен в `BackgroundTasks`: выход из зависимости происходит после формирования ответа. Всё, что нужно фоновой задаче, передавай значениями, а не сессией.

## 48.3. Lifespan

```python
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
    app.state.http = httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0))
    app.state.redis = Redis.from_url(settings.redis_url)
    try:
        yield
    finally:
        await app.state.http.aclose()
        await app.state.redis.aclose()
        await engine.dispose()


app = FastAPI(lifespan=lifespan)
```

Здесь создаются **дорогие долгоживущие объекты**: пул БД, HTTP-клиент с пулом соединений, Redis, ML-модель. События `on_event("startup")` устарели. Корректное освобождение в `finally` — основа graceful shutdown (главы 37, 62).

## 48.4. Middleware: чистый ASGI против BaseHTTPMiddleware

`BaseHTTPMiddleware` удобен, но оборачивает вызов в дополнительные потоки anyio: это накладные расходы, проблемы со стримингом и потерей контекста `contextvars`. Для горячего пути пиши чистый ASGI-middleware.

```python
class RequestContextMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_id = dict(scope["headers"]).get(b"x-request-id", b"").decode() or str(uuid4())
        token = request_id_var.set(request_id)
        start = time.perf_counter()

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                message["headers"].append((b"x-request-id", request_id.encode()))
                elapsed = (time.perf_counter() - start) * 1000
                message["headers"].append((b"x-process-time-ms", f"{elapsed:.1f}".encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            request_id_var.reset(token)


app.add_middleware(RequestContextMiddleware)
```

Встроенные: `CORSMiddleware` (явные origins, не `*` с credentials), `TrustedHostMiddleware`, `GZipMiddleware`. Middleware выполняются в порядке, обратном добавлению: последний добавленный — самый внешний.

## 48.5. Единый формат ошибок: RFC 9457

```python
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

PROBLEM = "application/problem+json"


@app.exception_handler(InsufficientFunds)
async def insufficient_handler(request: Request, exc: InsufficientFunds):
    return JSONResponse(
        status_code=409,
        media_type=PROBLEM,
        content={
            "type": "https://api.example.com/problems/insufficient-funds",
            "title": "Недостаточно средств",
            "status": 409,
            "detail": str(exc),
            "instance": request.url.path,
            "request_id": request_id_var.get(),
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, media_type=PROBLEM, content={
        "type": ".../validation-error", "title": "Ошибка валидации",
        "status": 422, "errors": exc.errors(), "request_id": request_id_var.get(),
    })
```

Стандарт Problem Details (RFC 9457, преемник RFC 7807) задаёт поля `type`, `title`, `status`, `detail`, `instance` плюс расширения. Один формат на все ошибки — клиенты пишут один обработчик.

Маппинг домена: `NotFound` → 404, `PermissionDenied` → 403, `Conflict`/`InsufficientFunds` → 409, `ValidationError` → 422, всё остальное → 500 **без деталей наружу**.

> [!WARNING] Никогда не отдавай клиенту traceback, текст SQL или строку внутреннего исключения: это раскрытие структуры системы. Логируй полностью внутри, наружу — нейтральное сообщение и `request_id`.

## 48.6. Идемпотентность POST

```sql
CREATE TABLE idempotency_keys (
    key uuid PRIMARY KEY,
    user_id bigint NOT NULL,
    request_hash text NOT NULL,
    status text NOT NULL,               -- in_progress / done
    response_body jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);
```

Алгоритм: `INSERT ... ON CONFLICT DO NOTHING` по ключу; если вставка прошла — выполняем операцию и сохраняем ответ в той же транзакции; если конфликт — возвращаем сохранённый ответ, а при совпадении ключа с другим телом (`request_hash`) отдаём 409.

> [!NOTE] Это защита от двойного списания при ретраях клиента и таймаутах сети (глава 38). Ключ обязателен для всех денежных POST, TTL — сутки, очистка — фоновой задачей.

## 48.7. BackgroundTasks, WebSocket и SSE

`BackgroundTasks` выполняется после отправки ответа в том же процессе. Годится для «отправить письмо», но **не годится** для критичной работы: при рестарте контейнера задача теряется, ретраев и наблюдаемости нет. Всё важное — в очередь (глава 57).

WebSocket требует своего `ConnectionManager`, авторизации при handshake, heartbeat/ping-pong и ограничения числа соединений. SSE (`sse-starlette`) проще: односторонний поток поверх обычного HTTP, автоматический reconnect в браузере — предпочтительный выбор для уведомлений и прогресса задач.

## 48.8. Контрольные вопросы

1. Что даёт `yield`-зависимость?
2. Почему `BaseHTTPMiddleware` нежелателен на горячем пути?
3. Что создаётся в lifespan и почему не в обработчике?
4. Какие поля обязательны в Problem Details?
5. Как идемпотентность защищает от двойного списания?

## 48.9. Практика

> [!TASK] Собери продакшен-каркас: lifespan с пулом БД, Redis и httpx; чистый ASGI-middleware с `request_id` и временем ответа; обработчики доменных исключений в RFC 9457; `Idempotency-Key` на переводах с сохранением ответа; SSE-эндпоинт прогресса импорта. Напиши тест, отправляющий один и тот же перевод дважды, и убедись, что деньги списались один раз.

---

# Глава 49. Аутентификация и авторизация

**Цель главы:** построить систему доступа, которую не стыдно показать безопаснику: правильные хэши, короткоживущие токены, ротация и проверка прав на объект.

## 49.1. Термины

**Идентификация** — «кто ты» (логин). **Аутентификация** — «докажи» (пароль, токен). **Авторизация** — «что тебе можно» (роли, права на объект). **Аудит** — «что ты сделал». Путаница между аутентификацией и авторизацией — источник большинства дыр.

## 49.2. Пароли

MD5 и SHA-256 — быстрые хэши, спроектированные для скорости; на GPU перебор миллиардов вариантов в секунду. Нужен **медленный** алгоритм с памятью и настраиваемой стоимостью.

```python
from pwdlib import PasswordHash

ph = PasswordHash.recommended()          # Argon2id
hashed = ph.hash(password)
ok, new_hash = ph.verify_and_update(password, hashed)   # rehash при смене параметров
```

**Argon2id** — современный стандарт (устойчив и к GPU, и к side-channel), альтернатива — bcrypt (помни про лимит входа 72 байта). Соль генерируется автоматически и хранится внутри строки хэша. Pepper — общий секрет из окружения, добавляемый отдельно.

> [!WARNING] Никогда не пиши свою криптографию и не «ускоряй» хэш. Проверка пароля должна занимать десятки миллисекунд — это фича, а не баг.

## 49.3. Сессии против токенов

Серверная сессия (opaque-идентификатор в cookie + данные в Redis) легко отзывается и не раскрывает содержимое. JWT самодостаточен и не требует похода в хранилище, но **отозвать его до истечения срока нельзя** без дополнительного списка.

Практический компромисс: короткоживущий access-токен плюс долгоживущий refresh с ротацией и хранилищем состояния.

## 49.4. JWT изнутри

Три части через точку: `header.payload.signature`, кодированные base64url. **Payload не зашифрован** — его читает любой, у кого есть токен.

Обязательные проверки при верификации: подпись, `alg` из белого списка, `exp`, `iss`, `aud`, при необходимости `nbf`.

```python
import jwt

payload = jwt.decode(
    token, key, algorithms=["RS256"],
    audience="finance-api", issuer="finance-auth",
    options={"require": ["exp", "sub", "aud", "iss"]},
)
```

HS256 — общий симметричный секрет (просто, но каждый сервис, проверяющий токен, может его и выпустить). RS256/ES256 — приватный ключ подписывает, публичный проверяет: правильно для нескольких сервисов и внешних потребителей.

> [!WARNING] Классическая атака alg confusion: сервер принимает `alg` из заголовка и подставляет публичный ключ как HMAC-секрет, позволяя подделать токен с `alg: HS256`. Всегда передавай **фиксированный список** допустимых алгоритмов и не принимай `none`.

Не клади в JWT персональные данные и права, которые должны меняться мгновенно: токен живёт до истечения `exp`.

## 49.5. Access + Refresh с ротацией

- Access: 5–15 минут, в памяти клиента, передаётся в `Authorization: Bearer`.
- Refresh: дни/недели, только в `HttpOnly Secure SameSite=Strict` cookie, отдельный endpoint обновления.
- **Ротация:** каждое обновление выдаёт новую пару, старый refresh помечается использованным (хранение `jti` и семейства в Redis).
- **Reuse detection:** повторное предъявление уже использованного refresh означает кражу — отзываем всё семейство токенов и требуем повторный вход.

```python
async def refresh(old_jti: str, family_id: str) -> TokenPair:
    if await redis.sismember("refresh:used", old_jti):
        await redis.delete(f"refresh:family:{family_id}")   # отзыв семейства
        raise TokenReuseDetected()
    await redis.sadd("refresh:used", old_jti)
    return issue_pair(family_id)
```

Logout кладёт `jti` access-токена в blacklist с TTL, равным остатку жизни токена.

## 49.6. OAuth2 и OpenID Connect

**Authorization Code + PKCE** — основной поток для веб и мобильных клиентов: клиент генерирует `code_verifier`, отправляет его SHA-256 как `code_challenge`, затем предъявляет оригинал при обмене кода на токен. Это защищает от перехвата кода.

**Client Credentials** — для межсервисного взаимодействия. **Password grant** устарел и удалён в OAuth 2.1 — не используй его для внешних клиентов (внутри своего первого-party приложения логин по паролю допустим).

**OIDC** надстраивает аутентификацию: `id_token`, endpoint `/userinfo`, обнаружение через `/.well-known/openid-configuration`, публичные ключи через JWKS с ротацией по `kid`.

Для продакшена часто правильнее не писать auth самому, а взять Keycloak/Authentik или managed-провайдера и валидировать JWT по JWKS.

## 49.7. Реализация в FastAPI

```python
from fastapi import Depends, Security
from fastapi.security import OAuth2PasswordBearer, SecurityScopes

oauth2 = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", scopes={"ops:write": "Создание операций"})


async def get_current_user(token: Annotated[str, Depends(oauth2)], uow: UowDep) -> User:
    try:
        payload = decode_access(token)
    except jwt.PyJWTError as exc:
        raise InvalidCredentials() from exc
    user = await uow.users.get(int(payload["sub"]))
    if user is None or not user.is_active:
        raise InvalidCredentials()
    return user


def require_role(*roles: str):
    async def checker(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in roles:
            raise PermissionDenied()
        return user
    return checker


@router.delete("/{account_id}", dependencies=[Depends(require_role("admin"))])
async def close_account(account_id: int, uow: UowDep): ...
```

**RBAC** — права через роли, **ABAC** — через атрибуты (владелец, статус, сумма). Проверка владения ресурсом обязательна и делается в запросе к БД:

```python
stmt = select(Account).where(Account.id == account_id, Account.owner_id == user.id)
```

> [!NOTE] Возвращай 404 вместо 403 для чужих объектов, если сам факт существования ресурса — чувствительная информация. Иначе API превращается в оракул для перебора идентификаторов.

## 49.8. API-ключи и хранение на клиенте

API-ключи храни в БД **в виде хэша**, показывай один раз при создании, используй префикс для поиска (`fin_live_...`), поддерживай скоупы и ротацию.

Cookie с `HttpOnly` недоступна JavaScript (защита от XSS-кражи), но требует CSRF-защиты. `localStorage` уязвим к XSS. Для сложных SPA часто выбирают BFF: браузер держит cookie с сессией, а токены живут на сервере-посреднике.

## 49.9. Контрольные вопросы

1. Почему SHA-256 не подходит для паролей?
2. Что нельзя класть в JWT и почему?
3. Как работает reuse detection при ротации?
4. Зачем PKCE?
5. Чем RBAC отличается от ABAC?

## 49.10. Практика

> [!TASK] Реализуй auth сквозного проекта: Argon2id, `/auth/login` и `/auth/refresh` с ротацией и reuse detection в Redis, logout с blacklist, `get_current_user`, RBAC-зависимость, проверка владения счётом во всех эндпоинтах. Тесты: просроченный токен, неверный `aud`, подмена `alg`, повторное использование refresh, доступ к чужому счёту.

---

# Глава 50. Безопасность API: OWASP API Top 10

**Цель главы:** научиться видеть API глазами атакующего и закрывать типовые векторы системно, а не заплатками.

## 50.1. Карта угроз

OWASP API Security Top 10 (2023): BOLA (доступ к чужому объекту), Broken Authentication, BOPLA (доступ к чужим свойствам объекта), Unrestricted Resource Consumption, BFLA (доступ к чужой функции), Unrestricted Access to Sensitive Business Flows, SSRF, Security Misconfiguration, Improper Inventory Management, Unsafe Consumption of APIs.

> [!NOTE] Обрати внимание: в списке нет «SQL-инъекции» как отдельного пункта. Реальные API ломают не инъекциями, а **отсутствием проверки прав** — и это то, что не поймает ни один линтер.

## 50.2. BOLA / IDOR

Каждый доступ по идентификатору обязан проверять принадлежность: `WHERE id = :id AND owner_id = :current_user`. Проверка «пользователь аутентифицирован» не равна «пользователь имеет право на этот объект».

Не полагайся на «неугадываемость» UUID: идентификаторы утекают через ссылки, логи, рефереры и выгрузки. Тест на чужой ID должен быть в наборе для **каждого** эндпоинта.

## 50.3. BOPLA и mass assignment

Клиент присылает `{"is_admin": true}` или `{"balance_minor": 10**9}` в теле обновления. Защита: отдельные DTO для каждой операции, `extra="forbid"`, явный whitelist обновляемых полей, `model_dump(exclude_unset=True)` вместо слепого `setattr` в цикле.

Аналогично на выходе: `response_model` не даст вернуть лишнее поле (глава 46).

## 50.4. Инъекции

SQL — только параметризованные запросы; ORM не панацея, если ты пишешь `text(f"... {user_input}")`. Имена колонок для сортировки — из белого списка. Command injection — `subprocess` со списком аргументов без `shell=True` (глава 35). Path traversal — нормализация пути и проверка, что он внутри разрешённого каталога (глава 32).

## 50.5. SSRF

Если сервис принимает URL от пользователя и ходит по нему (вебхуки, импорт по ссылке, превью), атакующий попросит сходить во внутреннюю сеть или в metadata-эндпоинт облака.

```python
import ipaddress, socket

def is_forbidden(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return (addr.is_private or addr.is_loopback or addr.is_link_local
            or addr.is_reserved or addr.is_multicast or addr.is_unspecified)
```

Меры: allowlist доменов и схем (только https), резолв DNS с проверкой **всех** адресов и подключением к проверенному IP (защита от DNS rebinding), запрет редиректов или их повторная проверка, отдельный egress-прокси, блокировка `169.254.169.254`.

## 50.6. Rate limiting и лимиты ресурсов

Алгоритмы: token bucket и sliding window. Реализация — Redis + атомарный Lua-скрипт (иначе гонка между чтением и записью), ключ по пользователю, API-ключу и IP. Ответ 429 с `Retry-After`.

Кроме частоты ограничивай: размер тела запроса, `limit` пагинации, число элементов в батче, глубину вложенности, время выполнения (таймаут), число одновременных соединений, объём загрузки.

> [!WARNING] Лимит «в памяти процесса» не работает при нескольких воркерах и репликах — каждый считает отдельно. Распределённый лимит требует общего хранилища.

Отдельный класс — злоупотребление бизнес-логикой: массовая регистрация, перебор промокодов, скачивание всей базы через легальные запросы. Здесь нужны капча, verifikasiкация, поведенческие лимиты.

## 50.7. Загружаемые файлы

Проверяй **magic bytes**, а не расширение и не `Content-Type` из запроса:

```python
SNIFFERS = {b"\x89PNG\r\n\x1a\n": "png", b"%PDF-": "pdf", b"\xff\xd8\xff": "jpg"}
```

Меры: лимит размера, переименование в случайное имя, хранение вне корня статики (S3/MinIO), отдача с `Content-Disposition: attachment` и `X-Content-Type-Options: nosniff`, отдельный домен для пользовательского контента, ре-энкодинг изображений, антивирус для документов.

## 50.8. XSS, CSRF и заголовки

JSON-API сам по себе не исполняет скрипты, но данные попадают во фронт: экранирование на клиенте обязательно, `Content-Type: application/json` вместо `text/html`, CSP как второй эшелон.

CSRF актуален **только** при cookie-аутентификации: `SameSite=Lax/Strict` плюс CSRF-токен (double submit) для небезопасных методов. Bearer-токен в заголовке CSRF не подвержен, потому что браузер не добавляет его автоматически.

Заголовки безопасности: `Strict-Transport-Security`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Content-Security-Policy`. CORS — не защита API (глава 39).

## 50.9. Misconfiguration и инвентаризация

Отключённый debug, закрытые `/docs`, отсутствие дефолтных паролей, минимальные права пользователя БД (не суперпользователь), TLS везде, секреты в vault/секретах оркестратора, а не в образе.

Инвентаризация: знай все свои эндпоинты и версии, удаляй забытые `v1` и «временные» отладочные роуты. Забытый `/api/v1/debug/users` — классическая причина утечки.

## 50.10. Unsafe consumption и цепочка поставки

Внешние API — недоверенный ввод: валидируй ответы Pydantic, ставь таймауты, не следуй слепо редиректам, проверяй TLS-сертификаты. Зависимости сканируй (`pip-audit`, Dependabot/Renovate), образы — сканером уязвимостей, секреты в репозитории — pre-commit-хуком `detect-private-key` (глава 28).

## 50.11. Аудит и секреты в логах

Логируй значимые действия (кто, что, когда, с какого IP) в отдельный аудит-поток, но никогда — пароли, токены, полные номера карт и паспортные данные (глава 29). Аудит должен быть неизменяемым и храниться дольше обычных логов.

## 50.12. Контрольные вопросы

1. Чем BOLA отличается от BFLA?
2. Почему UUID не защищает от IDOR?
3. Как защититься от DNS rebinding при SSRF?
4. Почему rate limit в памяти процесса не работает?
5. Когда CSRF актуален, а когда нет?

## 50.13. Практика

> [!TASK] Проведи аудит своего API по OWASP Top 10 и оформи таблицу «угроза — где применимо — как закрыто — тест». Реализуй: проверку владения во всех эндпоинтах, Redis-rate-limiter со sliding window, валидацию magic bytes при загрузке, allowlist-проверку URL вебхука, заголовки безопасности middleware. Напиши негативные тесты: чужой ID, mass assignment, превышение лимита, SSRF на 127.0.0.1.

---

# Глава 51. Тестирование, документация и эволюция API

**Цель главы:** сделать API проверяемым и изменяемым без страха сломать клиентов.

## 51.1. Пирамида тестов для API

Много unit-тестов домена (глава 30), интеграционные тесты репозиториев на реальном PostgreSQL, API-тесты через ASGI-транспорт без сети, и немного e2e против поднятого сервера. SQLite для интеграционных тестов не подходит (глава 44).

## 51.2. AsyncClient поверх ASGI

```python
import httpx
import pytest
from asgi_lifespan import LifespanManager


@pytest.fixture
async def client(app):
    async with LifespanManager(app) as manager:
        transport = httpx.ASGITransport(app=manager.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def test_create_operation(client, auth_headers):
    r = await client.post("/api/v1/operations", json={...}, headers=auth_headers)
    assert r.status_code == 201
    assert r.json()["amount_minor"] == 1500
```

`ASGITransport` вызывает приложение напрямую — без сокета, быстро и детерминированно. `LifespanManager` запускает startup/shutdown, иначе `app.state` останется пустым. Синхронный `TestClient` удобен, но не годится для проверки конкурентного поведения.

## 51.3. Подмена зависимостей

```python
app.dependency_overrides[get_current_user] = lambda: test_user
app.dependency_overrides[get_uow] = lambda: fake_uow
app.dependency_overrides[get_rate_provider] = lambda: StubRateProvider()
...
app.dependency_overrides.clear()      # обязательно в teardown
```

Это главный практический выигрыш DI: тестируем сценарий без внешнего мира, не патча импорты. Но не подменяй всё подряд: интеграционный тест должен проверять реальную связку с БД.

## 51.4. Изоляция данных в тестах

Два рабочих подхода:

1. **Транзакция с откатом:** тест открывает соединение, начинает внешнюю транзакцию, приложение работает внутри SAVEPOINT, после теста — rollback. Быстро, но требует аккуратной подмены сессии и не подходит для тестов, проверяющих именно commit.
2. **Отдельная БД на прогон:** testcontainers поднимает PostgreSQL, миграции применяются один раз, каждый тест очищает таблицы через `TRUNCATE ... CASCADE`. Медленнее, зато честно.

> [!WARNING] Общая тестовая база на всю команду и параллельные прогоны — источник «плавающих» падений. Изолируй по схеме или по контейнеру на воркер.

## 51.5. Что обязательно тестировать в API

- Контракт: коды 200/201/204/400/401/403/404/409/422/429 и формат Problem Details.
- Авторизация: без токена, с просроченным, с чужим объектом, с недостаточной ролью.
- Идемпотентность: повторный POST с тем же ключом не создаёт дубликат.
- Конкурентность: два параллельных перевода не уводят баланс в минус (реальные параллельные задачи, а не последовательные вызовы).
- Пагинация: границы, некорректный курсор, стабильность порядка.
- Валидация: `extra="forbid"`, лимиты, отрицательные суммы.

```python
async def test_double_spend(client, account):
    results = await asyncio.gather(*[
        client.post("/api/v1/transfers", json=payload, headers=headers) for _ in range(5)
    ])
    assert sum(r.status_code == 201 for r in results) == 1
```

## 51.6. Контрактные и property-based тесты

`schemathesis` читает OpenAPI и генерирует запросы, находя необработанные 500, несоответствие схемы и падения на граничных значениях. Это дешёвый способ найти то, что не придумал человек.

Для микросервисов добавляются контрактные тесты (Pact или сравнение OpenAPI-схем): потребитель фиксирует ожидания, поставщик проверяет их в CI до деплоя.

## 51.7. Документация как часть контракта

```python
@router.post(
    "/transfers",
    response_model=TransferRead,
    status_code=201,
    responses={
        409: {"model": ProblemDetails, "description": "Недостаточно средств или конфликт ключа"},
        422: {"model": ProblemDetails},
    },
    summary="Перевод между счетами",
    operation_id="createTransfer",
)
```

Docstring функции попадает в описание эндпоинта, `examples` в Field — в примеры запросов. `operation_id` определяет имена методов в сгенерированных клиентах, поэтому его меняют так же осторожно, как имя публичной функции.

## 51.8. Версионирование и совместимость

Префикс `/api/v1` — самый простой и понятный путь. Правила эволюции: **добавление** поля или необязательного параметра — совместимо; удаление, переименование, сужение типа, новое обязательное поле — ломающее изменение и новая версия.

Политика устаревания: заголовок `Deprecation` и `Sunset`, срок поддержки старой версии, метрика использования старых эндпоинтов, чтобы знать, когда их можно выключить. Ломающие миграции БД согласуй с версионированием API через Expand-Contract (глава 45).

## 51.9. Минимальная наблюдаемость и нагрузка

Уже на этом этапе добавь `/health` (процесс жив) и `/ready` (зависимости доступны), `X-Request-ID` в каждом ответе и метрику латентности. Полноценные метрики, логи и трейсинг — глава 61; нагрузочное тестирование Locust/k6 и поиск узких мест — глава 60.

Бюджет латентности формулируй заранее: например, p95 чтения ниже 100 мс при 200 RPS. Без бюджета «медленно» — предмет спора, а не инженерный факт.

## 51.10. Контрольные вопросы

1. Зачем `LifespanManager` в тестах?
2. Чем `ASGITransport` лучше реального HTTP в тестах?
3. Как изолировать данные параллельных тестов?
4. Какие изменения API считаются ломающими?
5. Что даёт schemathesis?

## 51.11. Практика

> [!TASK] Собери полный тестовый контур сквозного проекта: PostgreSQL в testcontainers, миграции Alembic перед прогоном, фикстуры `client`/`auth_headers`/`account`, подмена внешних провайдеров через `dependency_overrides`, негативные тесты авторизации, тест идемпотентности и конкурентного перевода, schemathesis по OpenAPI. Добавь в CI проверку одного head Alembic, `ruff`, `mypy --strict`, `pytest --cov` с порогом и сравнение OpenAPI-схемы с прошлой версией.

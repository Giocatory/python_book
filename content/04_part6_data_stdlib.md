# Глава 32. Файлы и файловая система

**Цель главы:** научиться работать с файлами безопасно: правильные пути, кодировки, атомарная запись и предсказуемое поведение при сбоях.

## 32.1. pathlib вместо os.path

```python
from pathlib import Path

BASE = Path(__file__).resolve().parent      # каталог модуля, а не cwd
data = BASE / "data" / "operations.json"    # оператор / вместо склейки строк

data.name        # 'operations.json'
data.stem        # 'operations'
data.suffix      # '.json'
data.parent      # каталог
data.exists(), data.is_file(), data.is_dir()
data.stat().st_size
data.with_suffix(".bak")
```

`Path` — объект, а не строка: он кроссплатформенный, поддерживает операторы и методы, читается лучше, чем `os.path.join(os.path.dirname(...))`.

> [!WARNING] Относительный путь считается от **текущего рабочего каталога процесса**, а не от расположения скрипта. Запустили из другой папки — файл «пропал». Всегда строй пути от `Path(__file__).resolve().parent` или из конфигурации.

## 32.2. Обход дерева и операции

```python
data.parent.mkdir(parents=True, exist_ok=True)

for p in BASE.iterdir(): ...
for p in BASE.glob("*.json"): ...
for p in BASE.rglob("*.csv"): ...           # рекурсивно

data.rename(data.with_suffix(".bak"))
data.replace(target)                        # атомарная замена, перезаписывает
data.unlink(missing_ok=True)

import shutil
shutil.copy2(src, dst)                      # с метаданными
shutil.copytree(src_dir, dst_dir, dirs_exist_ok=True)
shutil.make_archive("backup", "zip", BASE)
```

`os.walk` остаётся полезен, когда нужно управлять обходом (исключать каталоги на месте). Для симлинков помни: `Path.resolve()` разворачивает их, `is_symlink()` проверяет.

## 32.3. Открытие файла: режимы и параметры

```python
with open(path, "r", encoding="utf-8") as f:
    text = f.read()
```

| Режим | Смысл |
|---|---|
| `r` | чтение, файл должен существовать |
| `w` | запись, **обнуляет** файл или создаёт |
| `a` | дозапись в конец |
| `x` | создание, ошибка если существует |
| `b` | бинарный (нет кодировки) |
| `+` | чтение и запись |

Обязательные привычки: всегда `with` (закрытие гарантировано), всегда явный `encoding` для текстового режима, `newline=""` при работе с CSV.

> [!NOTE] Без `encoding` Python использует локаль ОС. На Windows это часто `cp1251`, на Linux `utf-8` — код, работающий у тебя, ломается у коллеги. Ruff правило `PTH`/`PLW` подсказывает такие места.

## 32.4. Чтение и запись без перерасхода памяти

```python
# плохо: весь файл в память
lines = f.readlines()

# хорошо: построчно, константная память
with open(path, encoding="utf-8") as f:
    for line in f:
        process(line.rstrip("\n"))

with open(out, "w", encoding="utf-8") as f:
    f.write("первая\n")
    f.writelines([s + "\n" for s in rows])   # writelines НЕ добавляет переводы строк
```

Для бинарных данных — чтение блоками: `while chunk := f.read(65536): ...`. Это же паттерн лежит в основе потоковой загрузки файлов в FastAPI (глава 46).

## 32.5. Позиция, буферизация, durability

```python
f.tell()                 # текущее смещение
f.seek(0)                # в начало; seek(offset, whence) — 0/1/2
f.flush()                # сбросить буфер Python в ОС
os.fsync(f.fileno())     # гарантировать запись на диск
```

`close()` сбрасывает буфер Python, но не гарантирует попадание данных на физический носитель. Для критичных данных (журнал операций) нужен `flush()` + `os.fsync()`.

## 32.6. Атомарная запись

Прямая запись в целевой файл при сбое питания оставит его наполовину перезаписанным. Правильный паттерн:

```python
import os
import tempfile
from pathlib import Path


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as tmp:
        tmp.write(text)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)      # атомарно в пределах одной ФС
```

Читатель видит либо старую, либо новую версию — никогда промежуточную. Так пишутся конфиги, кэши и локальные хранилища.

## 32.7. Кодировки и BOM

```python
text.encode("utf-8")                  # str → bytes
raw.decode("cp1251")                  # bytes → str
open(p, encoding="utf-8-sig")         # чтение с BOM
open(p, encoding="utf-8-sig", mode="w")  # запись BOM для Excel
```

Ошибки декодирования решай выяснением реальной кодировки, а не `errors="ignore"` — это молчаливая порча данных. `errors="replace"` допустим только для отображения, не для хранения.

## 32.8. Временные файлы и архивы

```python
import tempfile

with tempfile.TemporaryDirectory() as d:
    work = Path(d) / "report.csv"      # каталог удалится автоматически

with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
    ...
```

> [!WARNING] При распаковке архивов проверяй пути: запись `../../etc/cron.d/x` выведет файл за пределы каталога (Zip Slip / path traversal). В Python 3.12+ у `tarfile.extractall` есть параметр `filter="data"` — используй его.

## 32.9. Наблюдение за изменениями

Простой вариант — периодический опрос `stat().st_mtime`. Промышленный — библиотека `watchdog` (события ОС: inotify на Linux, ReadDirectoryChangesW на Windows). Это основа локальных индексаторов документов и автоперезагрузки серверов разработки.

## 32.10. Контрольные вопросы

1. Почему `open("data.json")` может не найти файл при запуске из другого каталога?
2. Чем `rename` отличается от `replace`?
3. Зачем `os.fsync`, если есть `close()`?
4. Как записать файл так, чтобы сбой питания не оставил его битым?

## 32.11. Практика

> [!TASK] Реализуй `JsonFileRepository` с атомарной записью, резервной копией `.bak`, чтением повреждённого файла с внятным доменным исключением и генератором строк для импорта CSV на 1 млн записей. Замерь пиковую память через `tracemalloc` и сравни с `readlines()`.

---

# Глава 33. Форматы данных и SQLite

**Цель главы:** уверенно сериализовать данные, выбирать формат под задачу и иметь локальную БД до переезда на PostgreSQL.

## 33.1. JSON

```python
import json

text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
data = json.loads(text)

with open(p, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False)
```

`ensure_ascii=False` обязателен для русского текста: иначе получишь `\u041f\u0440...` и вдвое больший файл.

### 33.1.1. Что JSON не умеет

`Decimal`, `datetime`, `date`, `UUID`, `set`, `dataclass`, Enum — не сериализуются по умолчанию.

```python
def default(obj):
    if isinstance(obj, Decimal):
        return str(obj)          # строкой, чтобы не потерять точность
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, (set, frozenset)):
        return sorted(obj)
    raise TypeError(type(obj))

json.dumps(data, default=default)
```

> [!WARNING] Превращать `Decimal` в `float` при сериализации денег — потеря точности на границе системы. Деньги передавай строкой или целым числом копеек.

### 33.1.2. orjson и JSONL

`orjson` (Rust) в разы быстрее и умеет `datetime`/`UUID`/`dataclass` из коробки: `orjson.dumps(data)` возвращает `bytes`. Для потоков событий используй **JSONL** (одна JSON-запись на строку) — файл можно читать построчно и дописывать без перезаписи.

## 33.2. CSV

```python
import csv

with open(p, newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f, delimiter=";"):
        print(row["amount"])

with open(out, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=["id", "amount"], delimiter=";")
    writer.writeheader()
    writer.writerows(rows)
```

`newline=""` обязателен по документации: иначе на Windows получишь пустые строки между записями. Русский Excel ожидает `;` и `utf-8-sig`. Никогда не собирай CSV вручную через `",".join(...)` — кавычки и запятые внутри значений сломают формат.

## 33.3. YAML и TOML

```python
import yaml
config = yaml.safe_load(text)        # только safe_load!

import tomllib                       # 3.11+, только чтение
with open("pyproject.toml", "rb") as f:
    project = tomllib.load(f)
```

> [!WARNING] `yaml.load` без `SafeLoader` умеет конструировать произвольные Python-объекты — это удалённое выполнение кода при загрузке чужого YAML. Всегда `safe_load`.

YAML удобен для конфигов и CI (комментарии, якоря), но опасен неявными приведениями (`no` → `False`, `1.0` → float). TOML строг и предсказуем — стандарт для `pyproject.toml`. Запись TOML — через `tomli-w`.

## 33.4. Прочие форматы

- **XML:** `xml.etree.ElementTree` для своих данных; для чужих — `defusedxml` (защита от XXE и billion laughs).
- **Excel:** `openpyxl` (чтение/запись xlsx, стили), `pandas.read_excel` для аналитики.
- **pickle:** только для доверенных данных; десериализация выполняет код. Для кэшей предпочитай JSON/msgpack.
- **Parquet/Arrow:** колоночные форматы для больших аналитических наборов.

## 33.5. SQLite: локальная база в стандартной библиотеке

```python
import sqlite3

con = sqlite3.connect("finance.db")
con.row_factory = sqlite3.Row
con.execute("PRAGMA journal_mode=WAL")
con.execute("PRAGMA foreign_keys=ON")

con.execute("""
    CREATE TABLE IF NOT EXISTS operations (
        id INTEGER PRIMARY KEY,
        amount INTEGER NOT NULL,
        category TEXT NOT NULL,
        created TEXT NOT NULL
    )
""")

con.execute(
    "INSERT INTO operations (amount, category, created) VALUES (?, ?, ?)",
    (1500, "food", "2026-11-24"),
)
con.commit()

for row in con.execute("SELECT * FROM operations WHERE category = ?", ("food",)):
    print(row["amount"])
con.close()
```

### 33.5.1. Параметры вместо f-строк

> [!WARNING] Никогда не подставляй значения в SQL через f-строки или `%`. Это SQL-инъекция. Только плейсхолдеры `?` (sqlite) или `$1`/`%(name)s` (PostgreSQL). Даже «безобидная» сортировка по имени колонки требует белого списка, а не подстановки.

### 33.5.2. Что важно знать про sqlite3

- Контекстный менеджер `with con:` управляет **транзакцией** (commit/rollback), но **не закрывает** соединение.
- `executemany` вставляет пачку за один вызов — на порядки быстрее цикла.
- WAL-режим позволяет читателям не блокировать писателя.
- Один писатель одновременно: SQLite отлично подходит для локальных приложений, но не для конкурентной записи из нескольких процессов/контейнеров.
- `PRAGMA foreign_keys=ON` нужно включать на каждом соединении — по умолчанию внешние ключи не проверяются.
- Версионируй схему через `PRAGMA user_version` и последовательные миграции; это репетиция Alembic (глава 45).

## 33.6. Выбор формата

| Задача | Формат |
|---|---|
| обмен с API, конфиг сервиса | JSON |
| поток событий, лог записей | JSONL |
| выгрузка для Excel, импорт из банка | CSV |
| конфиг для человека, CI | YAML |
| метаданные Python-проекта | TOML |
| локальное хранилище с запросами | SQLite |
| аналитика на миллионах строк | Parquet |

## 33.7. Контрольные вопросы

1. Зачем `ensure_ascii=False` и `newline=""`?
2. Почему `yaml.load` опасен?
3. Как сериализовать `Decimal`, не потеряв точность?
4. Что делает `with con:` в sqlite3 и чего он не делает?

## 33.8. Практика

> [!TASK] Сделай слой хранения с двумя реализациями одного порта: `JsonFileRepository` и `SqliteRepository`. Добавь экспорт в CSV для Excel (`;`, `utf-8-sig`), импорт JSONL, версионирование схемы SQLite через `user_version` и тест, доказывающий взаимозаменяемость реализаций.

---

# Глава 34. Дата и время

**Цель главы:** перестать создавать баги, связанные с часовыми поясами, — самый частый источник тихих ошибок в учёте и отчётности.

## 34.1. Два разных смысла

**Момент времени** (когда произошло событие) и **календарное значение** («24 ноября», «каждый понедельник») — разные сущности. Момент хранится в UTC; календарное значение — как `date` без зоны.

**naive** datetime не содержит зоны, **aware** содержит `tzinfo`. Сравнивать и вычитать naive и aware нельзя — `TypeError`.

> [!NOTE] Главное правило backend: **храни и передавай моменты в UTC, конвертируй в локальную зону только на границе отображения**. В PostgreSQL это тип `timestamptz` (глава 42). Ruff правило `DTZ` ловит naive-вызовы.

## 34.2. Основные типы

```python
from datetime import date, datetime, time, timedelta, timezone

now = datetime.now(timezone.utc)      # aware, UTC
today = date.today()                  # календарная дата
delta = timedelta(days=7, hours=3)
later = now + delta
d = date(2026, 11, 24)
```

`datetime` неизменяем: `replace()` возвращает новый объект. `timedelta` хранит дни, секунды и микросекунды — месяцев в нём нет намеренно, потому что месяц имеет переменную длину.

## 34.3. Часовые пояса через zoneinfo

```python
from zoneinfo import ZoneInfo

msk = ZoneInfo("Europe/Moscow")
local = now.astimezone(msk)
aware_local = datetime(2026, 11, 24, 12, 0, tzinfo=msk)
utc = aware_local.astimezone(timezone.utc)
```

`ZoneInfo` (3.9+) использует системную базу IANA. На Windows при её отсутствии установи пакет `tzdata`.

> [!WARNING] Не путай `replace(tzinfo=...)` и `astimezone(...)`. Первый **приклеивает** зону, не меняя цифры на часах (интерпретация «это и было локальное время»), второй **конвертирует** момент. Ошибка выбора даёт сдвиг на часы.

Ловушки DST: при переводе часов назад час повторяется (различается атрибутом `fold`), при переводе вперёд некоторых локальных времён не существует. Арифметика «плюс сутки» через `timedelta` в локальной зоне может дать неожиданный час — поэтому вычисления делай в UTC.

## 34.4. Форматирование и парсинг

```python
now.isoformat()                       # '2026-11-24T09:30:00+00:00'
datetime.fromisoformat("2026-11-24T09:30:00Z")   # 3.11+ понимает Z
now.strftime("%d.%m.%Y %H:%M")
datetime.strptime("24.11.2026", "%d.%m.%Y")
```

| Директива | Значение |
|---|---|
| `%Y` / `%y` | год 4 / 2 цифры |
| `%m` / `%d` | месяц / день |
| `%H` / `%M` / `%S` | час (24) / минута / секунда |
| `%z` / `%Z` | смещение / имя зоны |
| `%j` | день года |

Обмен между системами — только ISO 8601. Формат `24.11.2026`留给 пользователя; внутри системы он не должен циркулировать.

## 34.5. Календарная арифметика

`timedelta` не умеет «плюс месяц». Для календарных правил используй `dateutil.relativedelta`:

```python
from dateutil.relativedelta import relativedelta

date(2026, 1, 31) + relativedelta(months=1)   # 2026-02-28
```

Это важно для подписок, процентов по вкладам и месячных отчётов: «месяц» — не 30 дней.

## 34.6. Измерение интервалов

```python
import time

start = time.perf_counter()      # монотонные часы высокой точности
...
elapsed = time.perf_counter() - start

time.monotonic()                 # монотонные, для таймаутов
time.time()                      # wall clock, может прыгнуть назад (NTP)
```

> [!WARNING] Никогда не измеряй длительность через `time.time()` или `datetime.now()`: перевод системного времени даст отрицательную длительность. Для интервалов — только `perf_counter`/`monotonic`.

## 34.7. Тестирование времени

Тест, зависящий от реального «сейчас», нестабилен. Фиксируй время (`time-machine`, `freezegun`) или внедряй поставщика времени как зависимость:

```python
class Clock(Protocol):
    def now(self) -> datetime: ...

class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)
```

Это тот же DIP из главы 26, применённый ко времени: в тестах подставляется `FrozenClock`.

## 34.8. Контрольные вопросы

1. Чем naive отличается от aware?
2. В чём разница `replace(tzinfo=...)` и `astimezone(...)`?
3. Почему длительность нельзя мерить `time.time()`?
4. Как корректно прибавить месяц к дате?

## 34.9. Практика

> [!TASK] Переведи сквозной проект на aware-UTC: все `created` в UTC, вывод в зоне пользователя через `ZoneInfo`, группировка отчёта по локальным месяцам. Добавь `Clock` как зависимость, тест с фиксированным временем и тест на переход через границу месяца в зоне с DST.

---

# Глава 35. Стандартная библиотека и регулярные выражения

**Цель главы:** знать, что уже есть в языке, чтобы не изобретать велосипед и не тянуть лишние зависимости.

## 35.1. collections

```python
from collections import deque, defaultdict, Counter, ChainMap, namedtuple

queue = deque(maxlen=1000)      # O(1) с обоих концов, кольцевой буфер
groups = defaultdict(list)
counts = Counter(words)
config = ChainMap(cli_args, env_vars, defaults)   # слои конфигурации
```

`deque` — правильная очередь вместо `list.pop(0)`. `ChainMap` — идиоматичный способ наложить конфиги друг на друга без копирования.

## 35.2. functools и itertools

```python
from functools import partial, reduce, cached_property, lru_cache

parse_rub = partial(int, base=10)
total = reduce(lambda a, b: a + b, amounts, 0)

class Report:
    @cached_property
    def matrix(self):           # вычисляется один раз на экземпляр
        return heavy_build()
```

`itertools` разобран в главе 18; ключевое, что нужно помнить: `chain`, `islice`, `groupby` (требует сортировки), `product`, `count`, `takewhile`.

## 35.3. Процессы и окружение

```python
import subprocess

result = subprocess.run(
    ["git", "rev-parse", "HEAD"],
    capture_output=True, text=True, check=True, timeout=10,
)
print(result.stdout.strip())
```

> [!WARNING] `shell=True` с пользовательским вводом — это внедрение команд. Передавай список аргументов, ставь `timeout` и `check=True`.

`sys` (argv, exit, path, executable), `os` (environ, getpid), `platform`, `shutil.which` — минимальный набор для системных скриптов.

## 35.4. argparse: настоящий CLI

```python
import argparse

parser = argparse.ArgumentParser(prog="finance")
sub = parser.add_subparsers(dest="command", required=True)

add = sub.add_parser("add", help="добавить операцию")
add.add_argument("amount", type=int)
add.add_argument("--category", default="other", choices=["food", "taxi", "other"])

report = sub.add_parser("report")
report.add_argument("--month", required=True)

args = parser.parse_args()
```

`argparse` даёт справку, проверку типов и коды возврата бесплатно. Более современный вариант с типизацией — `typer` (на базе `click`), но он тянет зависимость.

## 35.5. Регулярные выражения

```python
import re

PATTERN = re.compile(r"(?P<date>\d{4}-\d{2}-\d{2})\s+(?P<amount>-?\d+)", re.VERBOSE)

m = PATTERN.search(text)
if m:
    print(m.group("date"), m.groupdict())

re.findall(r"\d+", text)
re.finditer(r"\d+", text)         # итератор матчей, экономит память
re.sub(r"\s+", " ", text)
re.split(r"[;,\t]", line)
```

### 35.5.1. Синтаксис, который нужно знать

`\d \w \s` и их отрицания `\D \W \S`; классы `[abc]`, `[^abc]`; квантификаторы `* + ? {m,n}`; anchors `^ $ \b`; группы `(...)`, именованные `(?P<name>...)`, non-capturing `(?:...)`; альтернатива `|`; флаги `IGNORECASE`, `MULTILINE`, `DOTALL`, `VERBOSE`.

### 35.5.2. Жадность и ленивость

```python
re.search(r"<.*>", "<a><b>")     # захватит '<a><b>' — жадно
re.search(r"<.*?>", "<a><b>")    # захватит '<a>' — лениво
```

### 35.5.3. ReDoS

Вложенные квантификаторы (`(a+)+$`) на неудачном вводе дают экспоненциальный перебор —regular expression denial of service. Признак опасности: несколько вложенных повторений над пересекающимися классами.

> [!WARNING] Не разбирай регулярками HTML, JSON и вложенные структуры — для них есть парсеры. И не применяй сложные regex к недоверенному вводу без ограничения длины. В Python 3.11+ есть атомарные группы `(?>...)` и possessive-квантификаторы `*+`, помогающие избежать бэктрекинга.

## 35.6. Хеши, случайность, идентификаторы

```python
import hashlib, hmac, secrets, base64, uuid

hashlib.sha256(data).hexdigest()          # целостность, НЕ пароли
hmac.compare_digest(a, b)                 # сравнение за постоянное время
secrets.token_urlsafe(32)                 # криптостойкие токены
base64.urlsafe_b64encode(raw)
uuid.uuid4()
```

Пароли — только Argon2id/bcrypt (глава 49). UUIDv7 (сортируемый по времени, дружелюбный к B-Tree индексам) генерируется сторонней библиотекой; зачем он нужен — глава 41.

## 35.7. Ещё полезное

`heapq` (приоритетная очередь, top-N), `bisect` (бинарный поиск в отсортированном списке), `statistics` (mean, median, stdev), `textwrap` (перенос текста), `zipfile`/`tarfile`, `csv`, `configparser`, `contextlib`, `dataclasses`, `enum`, `typing`, `unittest.mock`.

> [!TIP] Перед добавлением зависимости спроси: нет ли этого в stdlib? Каждая зависимость — это её баги, её CVE, её несовместимости и вес образа Docker.

## 35.8. Контрольные вопросы

1. Почему `deque` лучше списка для очереди?
2. Чем опасен `shell=True`?
3. Что такое ReDoS и как его избежать?
4. Почему `secrets`, а не `random`, для токенов?

## 35.9. Практика

> [!TASK] Собери полноценный CLI на `argparse` с подкомандами `add`, `list`, `report`, `import`. Импорт должен разбирать строки банковского CSV регуляркой с именованными группами и отбраковывать битые строки в отдельный отчёт. Добавь `heapq` для топ-5 расходов и `Counter` для статистики категорий.

---

# Глава 36. Конкурентность: потоки, процессы и GIL

**Цель главы:** понимать, какой вид параллелизма даёт выигрыш для конкретной задачи, и почему потоки не ускоряют вычисления.

## 36.1. Конкурентность против параллелизма

**Конкурентность** — задачи продвигаются попеременно, чередуясь (один исполнитель). **Параллелизм** — задачи исполняются физически одновременно (несколько ядер).

| Тип нагрузки | Что узкое место | Инструмент |
|---|---|---|
| I/O-bound, десятки соединений | ожидание сети/диска | `asyncio` |
| I/O-bound, блокирующие библиотеки | ожидание, но sync API | `ThreadPoolExecutor` |
| CPU-bound | ядро процессора | `ProcessPoolExecutor` |
| Смешанная | и то и другое | процессы + asyncio внутри |

## 36.2. GIL

**Global Interpreter Lock** — мьютекс, разрешающий исполнять Python-байткод только одному потоку в рамках процесса. Он защищает внутренние структуры CPython (в первую очередь счётчики ссылок) от гонок.

GIL **освобождается**: на блокирующих I/O-операциях, внутри C-расширений (`numpy`, `hashlib`, сжатие), а также принудительно каждые `sys.getswitchinterval()` (по умолчанию 5 мс) для переключения потоков.

Следствия:
- Потоки **ускоряют I/O-bound** задачи: пока один ждёт сокет, другой работает.
- Потоки **не ускоряют CPU-bound** чистый Python: ядро одно, плюс开销 переключений.
- Для CPU нужен отдельный процесс со своим интерпретатором и своим GIL.

> [!NOTE] Начиная с Python 3.13 существуют free-threaded сборки без GIL (PEP 703); в 3.14 их статус повышен до официально поддерживаемого. Но экосистема C-расширений должна быть пересобрана, а однопоточная производительность может отличаться. Для продакшена пока выбирай обычную сборку и явную модель параллелизма.

## 36.3. threading

```python
import threading

lock = threading.Lock()
counter = 0


def worker(n: int) -> None:
    global counter
    for _ in range(n):
        with lock:
            counter += 1


threads = [threading.Thread(target=worker, args=(100_000,)) for _ in range(4)]
for t in threads:
    t.start()
for t in threads:
    t.join()
```

### 36.3.1. Почему GIL не отменяет блокировки

`counter += 1` — это несколько байткод-инструкций (загрузка, сложение, запись). GIL может быть отпущен между ними, и другой поток увидит промежуточное состояние.

> [!WARNING] «В Python есть GIL, значит потокобезопасно» — dangerous заблуждение. GIL защищает интерпретатор, а не **твои инварианты**. Любая составная операция над общим состоянием требует `Lock`.

### 36.3.2. Примитивы синхронизации

`Lock` (простой мьютекс), `RLock` (реентерабельный, для рекурсивных вызовов), `Semaphore` (ограничение числа одновременных операций), `Event` (сигнал), `Condition` (ожидание условия), `Barrier`. Для обмена данными — `queue.Queue`, уже потокобезопасная: она снимает необходимость в ручных блокировках.

`threading.local()` даёт данные, отдельные для каждого потока (например, соединение с БД).

### 36.3.3. Deadlock

Два потока берут два замка в разном порядке и ждут друг друга вечно. Профилактика: единый глобальный порядок захвата, таймауты `lock.acquire(timeout=...)`, минимизация области удержания замка.

## 36.4. multiprocessing

```python
from multiprocessing import Process, Queue


def compute(chunk, out: Queue) -> None:
    out.put(sum(x * x for x in chunk))


if __name__ == "__main__":          # обязательно!
    q = Queue()
    p = Process(target=compute, args=(range(10**6), q))
    p.start()
    print(q.get())
    p.join()
```

Особенности: у каждого процесса своя память, аргументы и результаты передаются через `pickle` (значит, должны быть сериализуемы), старт дороже потока.

Способы старта: `spawn` (новый интерпретатор, кроссплатформенно, требует guard), `fork` (копия процесса, быстро, но небезопасно с потоками), `forkserver`. В Python 3.14 на Linux по умолчанию используется `forkserver`; в более ранних версиях — `fork`. Явно задавай метод через `multiprocessing.get_context("spawn")`, если нужна предсказуемость.

Для больших массивов вместо pickle используй `multiprocessing.shared_memory`; для простых разделяемых значений — `Value`/`Array`; для сложных объектов — `Manager` (медленно, через прокси).

## 36.5. concurrent.futures — предпочтительный интерфейс

```python
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed


def fetch(url: str) -> int: ...


with ThreadPoolExecutor(max_workers=16) as pool:
    futures = {pool.submit(fetch, u): u for u in urls}
    for fut in as_completed(futures):
        url = futures[fut]
        try:
            print(url, fut.result())
        except Exception as exc:
            print(url, "failed", exc)
```

Единый API для потоков и процессов: `submit` возвращает `Future`, `map` сохраняет порядок, `as_completed` отдаёт по готовности. Исключение внутри задачи пробрасывается при `fut.result()` — не забывай его вызывать, иначе ошибка потеряется молча.

> [!TIP] Начинай с `concurrent.futures`, а не с ручных `Thread`/`Process`. Пул переиспользует воркеры, ограничивает конкурентность и корректно завершается. Ручное управление потоками нужно только для долгоживущих фоновых служб.

`max_workers` для I/O подбирается по числу одновременных операций и лимитам внешней системы; для CPU — по числу ядер (`os.process_cpu_count()` в 3.13+).

## 36.6. Контрольные вопросы

1. Почему потоки не ускоряют CPU-bound код?
2. Когда GIL освобождается?
3. Зачем `Lock`, если есть GIL?
4. Почему `multiprocessing` требует `if __name__ == "__main__"`?
5. Что произойдёт, если не вызвать `future.result()`?

## 36.7. Практика

> [!TASK] Напиши бенчмарк: (1) CPU-задача (сумма квадратов 5 млн чисел), (2) I/O-задача (20 HTTP-запросов). Прогони каждый вариант последовательно, в `ThreadPoolExecutor` и в `ProcessPoolExecutor`. Оформи таблицу времён и объясни каждый результат через GIL.

---

# Глава 37. asyncio: глубокое погружение

**Цель главы:** понять event loop изнутри и научиться писать асинхронный код, который не «вешает» сервер одним блокирующим вызовом.

## 37.1. Модель

asyncio — **однопоточная кооперативная многозадачность**. Задачи сами уступают управление в точках `await`. Пока одна ждёт сеть, цикл событий обслуживает другие.

Под капотом — мультиплексирование ввода-вывода ОС: `epoll` (Linux), `kqueue` (macOS), IOCP (Windows). Один поток регистрирует тысячи неблокирующих сокетов и получает уведомления о готовности — это решение проблемы C10K.

> [!NOTE] Кооперативность — и сила, и уязвимость. Никакой вытесняющей_multitasking: если задача не доходит до `await` (или вызывает блокирующую функцию), **весь** цикл событий стоит. Один `time.sleep(5)` в хендлере = 5 секунд простоя для всех клиентов.

## 37.2. Корутины, задачи, фьючерсы

```python
import asyncio


async def fetch_rate(code: str) -> float:
    await asyncio.sleep(0.1)          # точка уступки
    return 92.5


async def main() -> None:
    result = await fetch_rate("USD")  # последовательно
    print(result)


asyncio.run(main())
```

- **Coroutine** — объект, возвращаемый `async def`. Сам по себе не выполняется.
- **Task** — корутина, обёрнутая для планирования в цикле; начинает выполняться «в фоне».
- **Future** — низкоуровневый контейнер будущего результата.

Все три — awaitable (реализуют `__await__`, что связывает эту главу с генераторами из главы 18).

```python
task = asyncio.create_task(fetch_rate("EUR"))   # уже пошла
other = await something_else()
rate = await task
```

> [!WARNING] `create_task` без сохранения ссылки — риск: цикл держит лишь слабую ссылку, и задача может быть собрана сборщиком мусора до завершения. Держи ссылки в множестве или используй `TaskGroup`.

## 37.3. Параллельное ожидание

```python
# gather: результаты в порядке аргументов
rates = await asyncio.gather(*(fetch_rate(c) for c in codes))

# gather с ошибками: не отменяет остальных
results = await asyncio.gather(*tasks, return_exceptions=True)

# TaskGroup (3.11+): структурная конкурентность, при ошибке отменяет остальные
async with asyncio.TaskGroup() as tg:
    t1 = tg.create_task(fetch_rate("USD"))
    t2 = tg.create_task(fetch_rate("EUR"))
print(t1.result(), t2.result())
```

`TaskGroup` — предпочтительный способ: он гарантирует, что при выходе из блока не останется «сиротских» задач, и собирает ошибки в `ExceptionGroup`.

```python
try:
    async with asyncio.TaskGroup() as tg:
        ...
except* ValueError as eg:
    for exc in eg.exceptions:
        log.warning("bad value", error=str(exc))
```

Для обработки по готовности — `asyncio.as_completed`.

## 37.4. Отмена и таймауты

```python
async with asyncio.timeout(5):        # 3.11+
    await slow_operation()

await asyncio.wait_for(slow_operation(), timeout=5)   # старый вариант
```

Отмена реализована через вбрасывание `CancelledError` в точку `await`. Это исключение наследуется от `BaseException` (3.8+), поэтому `except Exception` его не перехватит — и это правильно.

```python
try:
    await work()
except asyncio.CancelledError:
    await cleanup()
    raise            # ОБЯЗАТЕЛЬНО пробросить
```

> [!WARNING] Проглоченный `CancelledError` ломает graceful shutdown: приложение не может завершиться, потому что задача «отказывается» умирать. В Kubernetes это заканчивается SIGKILL после истечения terminationGracePeriod (глава 62).

`asyncio.shield` защищает критичный участок от отмены (например, фиксацию транзакции), но требует понимания: сам внешний `await` всё равно будет отменён.

## 37.5. Блокирующий код в async-приложении

Блокирует цикл: `time.sleep`, синхронный `requests.get`, `psycopg2`, тяжёлые вычисления, `open().read()` большого файла, `subprocess.run` без async.

```python
# вынести блокирующую функцию в пул потоков
data = await asyncio.to_thread(requests.get, url, timeout=10)

# CPU-bound — только в процесс
from concurrent.futures import ProcessPoolExecutor
loop = asyncio.get_running_loop()
with ProcessPoolExecutor() as pool:
    result = await loop.run_in_executor(pool, heavy_compute, data)
```

> [!TIP] Включай `asyncio.run(main(), debug=True)` или `PYTHONASYNCIODEBUG=1` в разработке: цикл начнёт предупреждать о корутинах, которые не были await-нуты, и о колбэках, выполнявшихся дольше 100 мс. Это дешёвый детектор блокировок.

## 37.6. Примитивы синхронизации и очереди

```python
sem = asyncio.Semaphore(10)          # не более 10 одновременных запросов

async def limited_fetch(url):
    async with sem:
        return await client.get(url)

lock = asyncio.Lock()                # защита инварианта внутри процесса
event = asyncio.Event()              # сигнал о готовности
queue = asyncio.Queue(maxsize=100)   # backpressure: put ждёт, если полна
```

Классический producer–consumer:

```python
async def producer(q: asyncio.Queue) -> None:
    for item in source:
        await q.put(item)
    await q.put(None)                # сигнал завершения


async def consumer(q: asyncio.Queue) -> None:
    while (item := await q.get()) is not None:
        await handle(item)
        q.task_done()
```

> [!WARNING] `asyncio.Queue` **не** потокобезопасна. Для обмена между потоком и циклом используй `loop.call_soon_threadsafe` или библиотеку `janus`. И не путай `asyncio.Lock` с `threading.Lock`: первый нельзя использовать в нескольких потоках, второй блокирует цикл событий.

Ограничение конкурентности семафором обязательно при работе с внешними API и БД: без него `gather` на 10 000 задач откроет 10 000 соединений и упрётся в лимиты.

## 37.7. Как устроен цикл событий

Упрощённо каждая итерация: (1) вычислить ближайший таймер, (2) опросить epoll с этим таймаутом, (3) поставить готовые I/O-колбэки в очередь, (4) выполнить все готовые колбэки, (5) повторить.

`await` в корутине — это регистрация «разбуди меня, когда готово» и возврат управления циклу. Отсюда прямое следствие: между двумя `await` твой код выполняется **атомарно** относительно других задач того же цикла — этим свойством можно пользоваться, но полагаться на него как на замену блокировкам нельзя (после первого `await` инвариант может быть нарушен).

Полезные низкоуровневые API: `loop.call_soon`, `loop.call_later`, `loop.call_at`, `loop.add_reader`, `loop.run_in_executor`.

## 37.8. uvloop и производительность

`uvloop` — реализация цикла на libuv (C), ускоряет типичные сетевые сценарии в 2–4 раза. Uvicorn использует её автоматически, если она установлена (на Windows недоступна).

```bash
uv add uvloop
```

```python
import uvloop
asyncio.run(main(), loop_factory=uvloop.new_eventloop)
```

Альтернативный подход — `anyio` (используется Starlette и httpx): единый API поверх asyncio и trio, структурная конкурентность из коробки.

## 37.9. Типичные ошибки

| Ошибка | Симптом | Лечение |
|---|---|---|
| Забытый `await` | `RuntimeWarning: coroutine was never awaited` | включить debug-режим, линтер `ASYNC`/`RUF` |
| `time.sleep` в async | все запросы тормозят | `await asyncio.sleep` |
| sync-драйвер БД в async | сервер стоит под нагрузкой | async-драйвер или `to_thread` |
| `gather` без семафора | лимиты соединений, 429 | `Semaphore` |
| Проглоченный `CancelledError` | зависание при shutdown | всегда `raise` |
| CPU-работа в цикле | рост latency у всех | `ProcessPoolExecutor` |
| Задача без ссылки | случайная потеря задачи | `TaskGroup` |

## 37.10. Диагностика

```python
for task in asyncio.all_tasks():
    print(task.get_name(), task.get_coro())
```

Плюс `py-spy dump --pid ...` (глава 31) — увидеть, где именно стоит цикл, и `faulthandler.dump_traceback_later`.

## 37.11. Контрольные вопросы

1. Чем Task отличается от корутины?
2. Почему `TaskGroup` лучше `gather`?
3. Что произойдёт при `except Exception` вокруг отменяемой задачи?
4. Как выполнить блокирующую функцию, не остановив цикл?
5. Зачем семафор при `gather` на 10 000 задач?

## 37.12. Практика

> [!TASK] Перепиши импорт курсов валют на asyncio: `TaskGroup`, `Semaphore(5)`, `asyncio.timeout` на каждый запрос, корректная обработка `ExceptionGroup` и `CancelledError`, замер ускорения против последовательной версии. Отдельно продемонстрируй вред `time.sleep(1)` внутри одной из задач: замерь суммарное время с ним и с `await asyncio.sleep(1)`.

---

# Глава 38. Асинхронная экосистема

**Цель главы:** собрать работающий асинхронный стек и понять, где async даёт выигрыш, а где он бесполезен.

## 38.1. Правило непрерывной цепочки

Async даёт выигрыш только если **вся цепочка** от хендлера до драйвера асинхронна. Один синхронный слой посередине обнуляет пользу и добавляет сложность.

> [!NOTE] Практический вывод: если библиотека не имеет async API и не выносится в `to_thread`, лучше сделать весь путь синхронным (обычный WSGI-сервис с пулом воркеров), чем притворяться асинхронным.

## 38.2. httpx

```python
import httpx

limits = httpx.Limits(max_connections=100, max_keepalive_connections=20)
timeout = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)

async with httpx.AsyncClient(timeout=timeout, limits=limits, http2=True) as client:
    r = await client.get("https://api.example.com/rates", params={"base": "USD"})
    r.raise_for_status()
    data = r.json()
```

Один `AsyncClient` на всё приложение (создаётся в lifespan, глава 48): он держит пул соединений и переиспользует TLS-сессии. Создание клиента на каждый запрос — потеря пула и лишний handshake.

## 38.3. Файлы и синхронные SDK

```python
import aiofiles

async with aiofiles.open(path, encoding="utf-8") as f:
    async for line in f:
        await process(line)
```

`aiofiles` внутри использует пул потоков — файловый I/O в Linux не имеет полноценного асинхронного интерфейса для обычных файлов. Для дисковых операций `asyncio.to_thread` часто не хуже и не требует зависимости.

Синхронные SDK облаков (boto3 и подобные) оборачивай в `to_thread` либо бери асинхронные аналоги (`aioboto3`).

## 38.4. Асинхронные протоколы языка

```python
class RateStream:
    def __aiter__(self):
        return self

    async def __anext__(self):
        item = await self._queue.get()
        if item is None:
            raise StopAsyncIteration
        return item


async for rate in RateStream():
    ...


async with AsyncConnection() as conn:
    ...
```

Асинхронные генераторы (`async def` с `yield`) и `contextlib.asynccontextmanager` — основа lifespan FastAPI, сессий SQLAlchemy и подписок на брокеры. Для гарантированного закрытия асинхронного генератора используй `contextlib.aclosing`.

## 38.5. Что будет дальше в книге

- **asyncpg / SQLAlchemy 2.0 async** — глава 44. Ключевая ловушка: ленивая загрузка связей в async запрещена и даёт `MissingGreenlet`.
- **redis.asyncio** — глава 56.
- **Taskiq / aio-pika / aiokafka** — глава 57.
- **Uvicorn + FastAPI** — главы 46–51.

## 38.6. Устойчивость клиента

```python
import random
import asyncio


async def with_retry(coro_factory, attempts: int = 4):
    for attempt in range(1, attempts + 1):
        try:
            return await coro_factory()
        except (httpx.TimeoutException, httpx.TransportError):
            if attempt == attempts:
                raise
            delay = min(2 ** attempt, 30) * (0.5 + random.random() / 2)
            await asyncio.sleep(delay)      # экспоненциальная задержка + jitter
```

Ретраи допустимы только для идемпотентных операций (глава 39) и с jitter — иначе синхронные ретраи тысяч клиентов создадут залп нагрузки. Готовая реализация — `tenacity`. Circuit Breaker и Bulkhead — глава 59.

## 38.7. Контрольные вопросы

1. Почему один `AsyncClient` на приложение?
2. Зачем `aiofiles`, если файловый I/O всё равно в потоках?
3. Что такое jitter и зачем он в ретраях?
4. Когда лучше отказаться от async вовсе?

## 38.8. Практика

> [!TASK] Собери асинхронный слой интеграции: единый `AsyncClient` с лимитами и таймаутами, ретраи с jitter только для GET, семафор, потоковая запись результата через `aiofiles`, тесты с `AsyncMock`. Сравни пропускную способность при 100 запросах с лимитом 10 и без лимита.

---

# Глава 39. Сети и HTTP

**Цель главы:** понимать, что происходит между `client.get(url)` и полученным JSON, — без этого невозможно диагностировать продакшен-проблемы.

## 39.1. Модели и инкапсуляция

Стек TCP/IP: канальный уровень → сетевой (IP) → транспортный (TCP/UDP) → прикладной (HTTP, DNS, TLS поверх TCP). Данные оборачиваются заголовками каждого уровня. Модель OSI (7 уровней) — учебная абстракция, полезна как словарь для разговора («проблема на L7»).

## 39.2. Адресация

- IPv4 (32 бита), IPv6 (128 бит), CIDR-маски (`10.0.0.0/8`).
- `127.0.0.1` (localhost) доступен только изнутри машины; `0.0.0.0` означает «слушать все интерфейсы». В Docker биндинг на `127.0.0.1` делает сервис недоступным снаружи контейнера — классическая ошибка.
- Порты: well-known 0–1023 (80, 443), registered, ephemeral (в Linux обычно 32768–60999) для исходящих соединений.
- NAT объясняет, почему у машины «внутренний» и «внешний» адреса разные.

## 39.3. TCP и UDP

TCP: трёхстороннее рукопожатие **SYN → SYN-ACK → ACK**, нумерация байтов, подтверждения, повторные передачи, контроль перегрузки, упорядоченность. Закрытие — FIN/ACK; сторона, закрывшая первой, входит в `TIME_WAIT` (обычно 2MSL) — отсюда исчерпание портов при коротких соединениях без keep-alive.

UDP: без соединения и гарантий, минимальные накладные расходы. На нём построены DNS и QUIC (HTTP/3).

Практические следствия: keep-alive и пул соединений экономят целые round-trip; `TCP_NODELAY` отключает алгоритм Нейгла для мелких сообщений; «connection reset by peer» — это про удалённую сторону или中間 прокси, а не про твой код.

## 39.4. DNS

Типы записей: `A` (IPv4), `AAAA` (IPv6), `CNAME` (алиас), `MX` (почта), `TXT` (верификации, SPF), `NS`. Резолвер обходит иерархию от корневых серверов; результат кэшируется на время `TTL`.

```bash
dig +short api.example.com
dig api.example.com A
```

> [!NOTE] Долгий DNS-lookup — частая причина «первый запрос медленный». В контейнерах добавляется `ndots` и search-домены из `resolv.conf`, из-за чего один запрос превращается в несколько.

## 39.5. TLS

Рукопожатие: согласование версии и шифронаборов, проверка сертификата X.509 по цепочке доверия, обмен ключами (асимметричная криптография), далее трафик шифруется симметрично (быстро). SNI позволяет держать много HTTPS-доменов на одном IP.

Let's Encrypt выдаёт бесплатные сертификаты; терминацию TLS обычно делает Nginx/Traefik/Ingress (главы 53, 62). Ошибка `CERTIFICATE_VERIFY_FAILED` почти всегда означает отсутствие корневого сертификата или неполную цепочку на сервере — не отключай проверку (`verify=False`), это открывает MITM.

## 39.6. Структура HTTP и методы

Запрос: строка `GET /rates HTTP/1.1`, заголовки, пустая строка, тело. Ответ: статус-строка, заголовки, тело.

| Метод | Safe | Идемпотентный | Назначение |
|---|---|---|---|
| GET | да | да | чтение |
| HEAD | да | да | только заголовки |
| OPTIONS | да | да | возможности, CORS preflight |
| POST | нет | **нет** | создание, команды |
| PUT | нет | да | полная замена |
| PATCH | нет | нет | частичное изменение |
| DELETE | нет | да | удаление |

**Идемпотентность** — повторный identical запрос не меняет результат сверх первого применения. Именно она определяет, можно ли безопасно ретраить (глава 38) и нужен ли `Idempotency-Key` для POST (глава 48).

## 39.7. Коды статусов

| Код | Смысл | Типичная причина |
|---|---|---|
| 200 / 201 / 204 | OK / Created / No Content | успех |
| 301 / 302 / 304 | Moved / Found / Not Modified | редирект, кэш по ETag |
| 400 | Bad Request | невалидный синтаксис |
| 401 | Unauthorized | нет или неверна аутентификация |
| 403 | Forbidden | аутентифицирован, но нет прав |
| 404 / 405 | Not Found / Method Not Allowed | путь или метод |
| 409 | Conflict | конфликт состояния, дубликат |
| 422 | Unprocessable Content | валидация не прошла (FastAPI) |
| 429 | Too Many Requests | rate limit, смотри Retry-After |
| 500 | Internal Server Error | баг на сервере |
| 502 / 503 / 504 | Bad Gateway / Unavailable / Timeout | прокси и апстрим |

> [!TIP] Различай 401 и 403 — это самый частый вопрос на интервью по HTTP. И не отдавай 500 на ошибку валидации: это 4xx, ответственность клиента.

## 39.8. Заголовки, cookies, CORS

Ключевые заголовки: `Content-Type`, `Authorization`, `Accept`, `Cache-Control`, `ETag`/`If-None-Match`, `Host`, `X-Forwarded-For`/`X-Real-IP` (реальный IP за прокси), `X-Request-ID`.

Cookies: `HttpOnly` (недоступна из JS — защита от XSS-кражи), `Secure` (только по HTTPS), `SameSite=Lax/Strict/None` (защита от CSRF).

CORS — механизм **браузера**, не сервера. При «сложном» запросе браузер сначала отправляет preflight `OPTIONS` с `Access-Control-Request-Method`; сервер должен ответить разрешающими заголовками. При `credentials` нельзя использовать `Access-Control-Allow-Origin: *` — нужен конкретный origin.

> [!NOTE] CORS не защищает API от curl, скриптов и мобильных клиентов. Это защита пользователя браузера, а не авторизация. Авторизация — глава 49.

## 39.9. Версии HTTP и стили API

HTTP/1.1 — keep-alive, но head-of-line blocking на уровне соединения. HTTP/2 — мультиплексирование потоков в одном соединении, сжатие заголовков HPACK. HTTP/3 — поверх QUIC/UDP, устраняет блокировку на транспортном уровне.

REST (ресурсы + методы), RPC (действия), GraphQL (клиент выбирает поля), gRPC (бинарный, HTTP/2). Для большинства backend-задач достаточно REST + JSON.

## 39.10. Инструменты диагностики

```bash
curl -i -X POST https://api.example.com/ops -H 'Content-Type: application/json' -d '{}'
curl -s https://api.example.com/rates | jq '.rates.USD'
ss -tulpn | grep 8000        # кто слушает порт
dig +short api.example.com
openssl s_client -connect api.example.com:443 -servername api.example.com
```

## 39.11. Контрольные вопросы

1. Чем safe отличается от идемпотентного метода?
2. Почему POST не ретраят без Idempotency-Key?
3. Разница 401 и 403?
4. Что делает preflight-запрос и кто его отправляет?
5. Почему биндинг на 127.0.0.1 ломает сервис в контейнере?

## 39.12. Практика

> [!TASK] Через `curl` исследуй публичный API: получи 200, 404, 401, 429; посмотри заголовки кэширования и сделай условный запрос с `If-None-Match`. Сними `dig` и `openssl s_client` для домена, запиши цепочку сертификатов. Оформи отчёт: какой метод идемпотентен, какие коды означают ответственность клиента.

---

# Глава 40. HTTP-клиенты на практике

**Цель главы:** написать клиент внешнего API, который не подвесит сервис и не потеряет данные при сбое сети.

## 40.1. requests или httpx

`requests` — синхронная классика, огромная экосистема. `httpx` — почти совместимый API плюс async, HTTP/2, явные таймауты по фазам. Новый код пиши на httpx; requests встретишь в legacy и в скриптах.

## 40.2. Таймауты обязательны

```python
timeout = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)
```

> [!WARNING] Запрос без таймаута может ждать бесконечно. В async-сервисе это означает занятую задачу и соединение навсегда; под нагрузкой — исчерпание пула и полный отказ. Таймаут ставится на **каждый** сетевой вызов, включая БД, Redis и брокер.

Различай фазы: `connect` (установка соединения), `read` (ожидание данных), `write` (отправка), `pool` (ожидание свободного соединения из пула). Часто забывают именно `pool`.

## 40.3. Ретраи

Правила: ретраить только идемпотентные операции или POST с `Idempotency-Key`; только транспортные ошибки и 5xx/429; с экспоненциальной задержкой и jitter; с ограничением числа попыток и общим дедлайном.

```python
transport = httpx.AsyncHTTPTransport(retries=3)   # только connect-ошибки
```

Для ретраев по статусам нужен свой цикл или `tenacity`. При 429 уважай `Retry-After`.

## 40.4. Пул соединений

Один клиент на приложение, `Limits(max_connections=..., max_keepalive_connections=...)`. Пул экономит TCP+TLS handshake (десятки-сотни миллисекунд на запрос) и предотвращает исчерпание ephemeral-портов.

## 40.5. Пагинация, потоки, большие ответы

```python
async def iter_pages(client, url):
    while url:
        r = await client.get(url)
        r.raise_for_status()
        payload = r.json()
        for item in payload["items"]:
            yield item
        url = payload.get("next")


async with client.stream("GET", big_url) as response:
    async for chunk in response.aiter_bytes(65536):
        await sink(chunk)
```

Асинхронный генератор + `stream` дают константную память на сколь угодно большой выгрузке — прямое применение глав 18 и 32.

## 40.6. Ошибки как часть контракта

```python
try:
    r = await client.get(url)
    r.raise_for_status()
except httpx.TimeoutException as exc:
    raise RateProviderUnavailable("таймаут провайдера курсов") from exc
except httpx.HTTPStatusError as exc:
    if exc.response.status_code == 404:
        raise CurrencyNotSupported(code) from exc
    raise RateProviderUnavailable(str(exc)) from exc
```

Клиент переводит транспортные ошибки в **доменные исключения** (глава 19). Вызывающий код не должен знать про httpx. Это же позволяет подменить провайдера без правки бизнес-логики (глава 26).

## 40.7. Что добавить в продакшене

- Circuit Breaker и Bulkhead — глава 59.
- Кэширование ответов в Redis с инвалидацией — глава 56.
- Метрики RED и трассировка исходящих вызовов — глава 61.
- Логирование с `request_id`, проброшенным в заголовке — главы 29, 48.

## 40.8. Контрольные вопросы

1. Какие четыре фазы таймаута в httpx и какую чаще забывают?
2. Что именно ретраит `AsyncHTTPTransport(retries=3)`?
3. Зачем jitter?
4. Почему один клиент на приложение?

## 40.9. Практика

> [!TASK] Реализуй `HttpRateProvider` за портом `RateProvider`: явные таймауты, пул, ретраи с jitter только для GET, перевод ошибок в доменные исключения, асинхронная пагинация, потоковая выгрузка отчёта в файл. Покрой тестами с `AsyncMock` сценарии: таймаут, 404, 429 с Retry-After, 500 после трёх ретраев.

# Глава 41. Проектирование реляционной схемы

**Цель главы:** научиться превращать предметную область в схему, которая переживёт годы изменений и не развалится под нагрузкой.

## 41.1. Реляционная модель в двух абзацах

Данные организованы в **отношения** (таблицы) из **кортежей** (строк) с фиксированным набором **атрибутов** (столбцов) определённого домена (типа). Ключевая идея: связи выражаются значениями ключей, а не указателями, и любые данные можно получить операциями реляционной алгебры (выборка, проекция, соединение).

Практический вывод: схема — это контракт. Ошибку в коде можно откатить за минуту, ошибку в схеме на 500 ГБ данных — за неделю миграций.

## 41.2. Первичные ключи

```sql
-- современный стиль: identity вместо SERIAL
CREATE TABLE accounts (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_id bigint NOT NULL,
    currency char(3) NOT NULL,
    balance_minor bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now()
);
```

| Вариант PK | Плюсы | Минусы |
|---|---|---|
| `bigint identity` | компактно (8 байт), монотонно, быстрый индекс | предсказуемость (перебор ID), конфликт при слиянии шардов |
| `uuid v4` | генерируется на клиенте, не раскрывает объёмы | **случайный** — фрагментирует B-Tree |
| `uuid v7` | глобально уникален и монотонен по времени | 16 байт, нужна поддержка версии или генерация в приложении |
| натуральный ключ | осмысленность | меняется со временем, широкий, каскадные правки |

### 41.2.1. Почему UUIDv4 fragmentирует индекс

B-Tree держит ключи упорядоченно. Случайный UUID попадает в произвольную страницу: происходят расщепления страниц (page splits), падает локальность кэша, растёт объём случайного дискового I/O и раздувается индекс. При вставке миллионов строк разница с монотонным ключом — разы.

**UUIDv7** начинается с 48-битного timestamp в миллисекундах, поэтому новые значения всегда идут «в правый край» индекса — как у `bigint`, но с глобальной уникальностью. В PostgreSQL 18+ есть встроенная функция `uuidv7()`; в более ранних версиях генерируй на стороне приложения.

> [!NOTE] Правило по умолчанию: `bigint identity` для внутренних сущностей; `uuidv7` для того, что создаётся распределённо или светится наружу. Публичный идентификатор можно сделать отдельным полем, оставив внутренний PK числовым.

## 41.3. Внешние ключи и ссылочная целостность

```sql
CREATE TABLE operations (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id bigint NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    category_id bigint REFERENCES categories(id) ON DELETE SET NULL,
    amount_minor bigint NOT NULL CHECK (amount_minor <> 0),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX operations_account_id_idx ON operations (account_id);
```

Поведение при удалении родителя: `RESTRICT`/`NO ACTION` (запретить), `CASCADE` (удалить детей), `SET NULL` (обнулить ссылку), `SET DEFAULT`.

> [!WARNING] PostgreSQL **не создаёт индекс на ссылающемся столбце автоматически**. Без него каждый `DELETE` родителя вызывает полный перебор дочерней таблицы, а `JOIN` деградирует. Индекс на FK — обязателен почти всегда.

Выбор политики: справочники — `RESTRICT`; «принадлежащие» сущности (позиции заказа) — `CASCADE`; необязательная ссылка (категория) — `SET NULL`.

## 41.4. Связи

- **One-to-Many:** FK на стороне «многих».
- **One-to-One:** FK плюс `UNIQUE` на нём (или общий PK).
- **Many-to-Many:** промежуточная таблица.

```sql
CREATE TABLE operation_tags (
    operation_id bigint NOT NULL REFERENCES operations(id) ON DELETE CASCADE,
    tag_id bigint NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (operation_id, tag_id)
);
CREATE INDEX operation_tags_tag_id_idx ON operation_tags (tag_id);
```

Составной PK даёт уникальность пары бесплатно. Второй индекс (по `tag_id`) нужен для обратного обхода.

## 41.5. Нормализация и осознанная денормализация

- **1НФ:** атомарные значения, никаких списков в поле.
- **2НФ:** каждый неключевой атрибут зависит от **всего** составного ключа.
- **3НФ:** нет транзитивных зависимостей неключевых атрибутов друг от друга.
- **НФБК:** каждая детерминанта — потенциальный ключ.

Нормализация устраняет аномалии обновления: одно знание хранится в одном месте.

Денормализация — осознанное дублирование ради чтения: сохранённый `balance_minor` вместо суммирования всех проводок, `category_name` в отчётной таблице, материализованное представление.

> [!NOTE] Денормализация всегда имеет цену: ты обязан поддерживать согласованность (триггером, транзакцией или фоновой задачей). Делай её только после измерений (глава 43), а не «на всякий случай».

## 41.6. Типы данных: критичные решения

| Задача | Правильный тип | Запрещено |
|---|---|---|
| деньги | `numeric(18,2)` или `bigint` в копейках | `real`, `double precision`, `float` |
| момент времени | `timestamptz` (хранится нормализованным в UTC) | `timestamp` без зоны, `varchar` |
| календарная дата | `date` | `timestamptz` |
| перечисление | `text` + `CHECK` или нативный `enum` | магические числа без справочника |
| полуструктурированные данные | `jsonb` | `json` (нет индексов и дедупликации ключей) |
| идентификатор | `bigint`, `uuid` | `text` |

> [!WARNING] `float` для денег — прямая потеря центов при суммировании (глава 7). `timestamp` без зоны — гарантированные баги при смене региона сервера и переходе на летнее время (глава 34).

## 41.7. Ограничения как исполняемая документация

```sql
ALTER TABLE accounts
    ADD CONSTRAINT accounts_owner_currency_uniq UNIQUE (owner_id, currency),
    ADD CONSTRAINT accounts_balance_non_negative CHECK (balance_minor >= 0);
```

`NOT NULL`, `UNIQUE`, `CHECK`, `FOREIGN KEY`, `EXCLUDE` — база проверяет их сама, при любом пути записи (ORM, скрипт, ручной SQL). Валидация только в приложении всегда рано или поздно обходится.

Ограничения можно делать `DEFERRABLE INITIALLY DEFERRED` — проверка откладывается до конца транзакции. Это ключ к двойной записи, где промежуточное состояние временно нарушает инвариант.

## 41.8. Сквозной проект: двойная запись

Наивная модель «операция с суммой» не позволяет ни переводов между счетами, ни аудита. Промышленный подход — **double-entry ledger**: событие (`transactions`) и проводки (`entries`), сумма которых по каждой транзакции равна нулю.

```sql
CREATE TABLE ledger_transactions (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    idempotency_key uuid NOT NULL UNIQUE,
    description text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ledger_entries (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    transaction_id bigint NOT NULL REFERENCES ledger_transactions(id) ON DELETE CASCADE,
    account_id bigint NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    amount_minor bigint NOT NULL CHECK (amount_minor <> 0)
);
CREATE INDEX ledger_entries_account_idx ON ledger_entries (account_id, transaction_id);
```

Инвариант «сумма проводок транзакции = 0» проверяется отложенным триггером или на уровне сервисного слоя в одной транзакции с блокировкой счетов (глава 43). Баланс — производная величина: `SUM(amount_minor)`, при необходимости кэшируемая в `accounts.balance_minor`.

## 41.9. Служебные поля и мягкое удаление

Стандартный набор: `created_at`, `updated_at` (обновляется триггером), при необходимости `deleted_at` (soft delete) и `version` (оптимистичная блокировка).

> [!TIP] Soft delete усложняет всё: каждый запрос требует `WHERE deleted_at IS NULL`, уникальные индексы становятся частичными, FK перестают защищать. Применяй его только там, где действительно нужно восстановление или юридический аудит.

## 41.10. Контрольные вопросы

1. Почему UUIDv4 хуже для B-Tree, чем UUIDv7?
2. Что произойдёт при удалении родителя без индекса на FK?
3. Чем `timestamptz` отличается от `timestamp`?
4. Как гарантировать уникальность пары в many-to-many?
5. Зачем отложенные ограничения в двойной записи?

## 41.11. Практика

> [!TASK] Спроектируй схему сквозного проекта: `users`, `accounts`, `categories`, `ledger_transactions`, `ledger_entries`, `operation_tags`. Нарисуй ER-диаграмму, обоснуй каждый тип и каждое ограничение, добавь индексы на все FK. Загрузи схему в локальный PostgreSQL (Docker) и убедись, что попытка вставить отрицательный баланс или дубликат валюты отклоняется базой, а не приложением.

---

# Глава 42. SQL в PostgreSQL

**Цель главы:** писать запросы осознанно, понимая порядок их выполнения, а не подгоняя синтаксис до «вроде работает».

## 42.1. Категории команд

**DDL** (структура): `CREATE`, `ALTER`, `DROP`, `TRUNCATE`. **DML** (данные): `INSERT`, `UPDATE`, `DELETE`, `SELECT`. **DCL** (права): `GRANT`, `REVOKE`. **TCL** (транзакции): `BEGIN`, `COMMIT`, `ROLLBACK`, `SAVEPOINT`.

> [!NOTE] В PostgreSQL DDL транзакционен: `CREATE TABLE` можно откатить. Это редкое и очень удобное свойство — миграции要么 применяются целиком, либо не применяются вовсе.

## 42.2. INSERT, UPDATE, DELETE с RETURNING

```sql
INSERT INTO categories (name) VALUES ('food'), ('taxi')
RETURNING id, name;

UPDATE accounts SET balance_minor = balance_minor - 1500
WHERE id = 42 AND balance_minor >= 1500
RETURNING balance_minor;

DELETE FROM operations WHERE created_at < now() - interval '5 years'
RETURNING id;
```

`RETURNING` избавляет от лишнего round-trip и от гонки «вставил, потом прочитал». Условие `balance_minor >= 1500` прямо в `UPDATE` — атомарная защита от перерасхода без явной блокировки.

## 42.3. Upsert: ON CONFLICT

```sql
INSERT INTO rates (code, value, updated_at)
VALUES ('USD', 92.5, now())
ON CONFLICT (code) DO UPDATE
SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at
RETURNING *;

INSERT INTO ledger_transactions (idempotency_key, description)
VALUES ($1, $2)
ON CONFLICT (idempotency_key) DO NOTHING
RETURNING id;
```

`EXCLUDED` — псевдотаблица с proposed-значениями. Для `ON CONFLICT` нужен уникальный индекс или ограничение по указанным столбцам.

> [!TIP] Второй паттерн — основа **идемпотентности** POST-запросов (глава 48): повторная доставка того же `Idempotency-Key` не создаёт дубликат.

## 42.4. Порядок логического выполнения

```
FROM / JOIN  →  WHERE  →  GROUP BY  →  HAVING  →  оконные функции
             →  SELECT  →  DISTINCT  →  ORDER BY  →  LIMIT / OFFSET
```

Отсюда следствия, которые путают всех новичков:
- алиас из `SELECT` **нельзя** использовать в `WHERE` (его ещё нет), но можно в `ORDER BY`;
- `WHERE` фильтрует строки **до** группировки, `HAVING` — группы **после**;
- оконные функции считаются после `HAVING`, поэтому их результат нельзя фильтровать в том же `SELECT` — нужен подзапрос или CTE;
- `LIMIT` применяется последним, поэтому без `ORDER BY` он вернёт неопределённый набор.

## 42.5. JOIN

```sql
SELECT o.id, o.amount_minor, c.name
FROM operations o
JOIN categories c ON c.id = o.category_id;          -- INNER

SELECT o.id, c.name
FROM operations o
LEFT JOIN categories c ON c.id = o.category_id;     -- все операции, даже без категории

SELECT a.owner_id, b.id AS other_account
FROM accounts a
JOIN accounts b ON a.owner_id = b.owner_id AND a.id < b.id;   -- SELF JOIN
```

`LEFT JOIN` + `WHERE c.id IS NULL` — идиома «найти записи без пары». Условие на правую таблицу в `WHERE` превращает `LEFT JOIN` в `INNER`: фильтруй в `ON`.

`CROSS JOIN` — декартово произведение (генерация сеток дат). `LATERAL` позволяет подзапросу ссылаться на столбцы предыдущей таблицы — незаменим для «top-N на каждую группу».

## 42.6. NULL и трёхзначная логика

`NULL` — не значение, а «неизвестно». `NULL = NULL` даёт `NULL`, а не `TRUE`.

```sql
SELECT * FROM operations WHERE category_id NOT IN (1, 2, NULL);  -- вернёт 0 строк!
SELECT * FROM operations WHERE category_id IS DISTINCT FROM 5;   -- NULL-безопасное сравнение
SELECT COALESCE(category_id, 0) FROM operations;
```

> [!WARNING] `NOT IN` с `NULL` в списке — классическая тихая ошибка: результат пустой всегда. Используй `NOT EXISTS` или `IS DISTINCT FROM`.

`count(*)` считает строки, `count(col)` — только не-NULL значения. Для уникальности с NULL в PostgreSQL 15+ есть `UNIQUE NULLS NOT DISTINCT`.

## 42.7. Агрегация

```sql
SELECT c.name,
       count(*) AS ops,
       sum(o.amount_minor) AS total,
       sum(o.amount_minor) FILTER (WHERE o.amount_minor < 0) AS expenses
FROM operations o
JOIN categories c ON c.id = o.category_id
GROUP BY c.name
HAVING sum(o.amount_minor) < 0
ORDER BY total;
```

`FILTER` — чище и быстрее, чем `CASE` внутри агрегата. Полезны также `string_agg`, `array_agg`, `bool_and`, `percentile_cont`. Для многоуровневых итогов — `ROLLUP`, `CUBE`, `GROUPING SETS`.

## 42.8. Подзапросы и CTE

```sql
-- EXISTS обычно лучше IN: останавливается на первом совпадении и NULL-безопасен
SELECT a.* FROM accounts a
WHERE EXISTS (SELECT 1 FROM operations o WHERE o.account_id = a.id);

WITH monthly AS (
    SELECT date_trunc('month', created_at) AS month, sum(amount_minor) AS total
    FROM operations GROUP BY 1
)
SELECT month, total FROM monthly WHERE total < 0 ORDER BY month;
```

CTE (`WITH`) делает запрос читаемым. До PostgreSQL 12 CTE был «забором оптимизации» (всегда материализовался); сейчас можно управлять: `WITH x AS MATERIALIZED (...)` или `NOT MATERIALIZED`.

Рекурсивный CTE — обход деревьев и иерархий:

```sql
WITH RECURSIVE tree AS (
    SELECT id, parent_id, name, 1 AS depth FROM categories WHERE parent_id IS NULL
    UNION ALL
    SELECT c.id, c.parent_id, c.name, t.depth + 1
    FROM categories c JOIN tree t ON c.parent_id = t.id
)
SELECT * FROM tree ORDER BY depth, name;
```

## 42.9. Оконные функции

Оконная функция считает значение **по набору строк, не схлопывая их** — в отличие от `GROUP BY`.

```sql
SELECT
    o.id, o.created_at, o.amount_minor,
    sum(o.amount_minor) OVER (PARTITION BY o.account_id ORDER BY o.created_at) AS running_balance,
    row_number() OVER (PARTITION BY o.category_id ORDER BY o.amount_minor DESC) AS rn,
    lag(o.amount_minor) OVER (PARTITION BY o.account_id ORDER BY o.created_at) AS prev_amount,
    avg(o.amount_minor) OVER (
        PARTITION BY o.account_id ORDER BY o.created_at
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS moving_avg_7
FROM operations o;
```

| Функция | Смысл |
|---|---|
| `row_number()` | сквозной номер внутри раздела |
| `rank()` / `dense_rank()` | ранг с пропусками / без пропусков |
| `lag()` / `lead()` | значение предыдущей / следующей строки |
| `first_value()` / `nth_value()` | первое / n-е значение окна |
| `sum/avg/count OVER` | нарастающие и скользящие агрегаты |

Рамка окна: `ROWS` (физические строки), `RANGE` (значения), `GROUPS`. По умолчанию при наличии `ORDER BY` рамка — `RANGE UNBOUNDED PRECEDING AND CURRENT ROW`, из-за чего одинаковые значения попадают в итог вместе. Для честного нарастающего итога указывай `ROWS` явно.

Топ-N на группу — через подзапрос:

```sql
WITH ranked AS (
    SELECT o.*, row_number() OVER (PARTITION BY category_id ORDER BY amount_minor) AS rn
    FROM operations o
)
SELECT * FROM ranked WHERE rn <= 3;
```

## 42.10. Пагинация: OFFSET против keyset

```sql
-- OFFSET 100000 заставляет БД прочитать и отбросить 100000 строк
SELECT * FROM operations ORDER BY created_at DESC, id DESC LIMIT 20 OFFSET 100000;

-- keyset (seek): константная стоимость на любой глубине
SELECT * FROM operations
WHERE (created_at, id) < ($1, $2)
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

> [!NOTE] `OFFSET` допустим для админки с небольшими объёмами. Для бесконечных лент и API-курсор — только keyset-пагинация по составному уникальному ключу.

## 42.11. Специфика PostgreSQL

```sql
-- JSONB
SELECT meta->>'source' AS source FROM operations WHERE meta @> '{"verified": true}';
SELECT jsonb_set(meta, '{source}', '"import"') FROM operations;
CREATE INDEX operations_meta_gin ON operations USING gin (meta);

-- DISTINCT ON: первая строка каждой группы (расширение PG)
SELECT DISTINCT ON (account_id) account_id, amount_minor, created_at
FROM operations ORDER BY account_id, created_at DESC;

-- массивы и полнотекстовый поиск
SELECT * FROM operations WHERE tags && ARRAY['food','taxi'];
SELECT * FROM articles WHERE to_tsvector('russian', body) @@ plainto_tsquery('кредит');
```

Операторы JSONB: `->` (объект/элемент как jsonb), `->>` (как text), `#>`/`#>>` (по пути), `@>` (содержит), `?` (есть ключ), а также `?|` и `?&` (любой/все ключи).

> [!WARNING] Нативный `ENUM` неудобен в миграциях: добавление значения требует отдельной транзакции, удаление значения не поддерживается вовсе. Практика по умолчанию — `text` + `CHECK` или справочная таблица, а Enum держать в Python (глава 25).

## 42.12. Инструменты

```bash
docker run -d --name pg -e POSTGRES_PASSWORD=dev -p 5432:5432 postgres:17
psql "postgresql://postgres:dev@localhost:5432/postgres"
```

В psql: `\d table` (структура), `\dt` (таблицы), `\di` (индексы), `\x` (вертикальный вывод), `\timing` (время), `\copy` (быстрый импорт CSV), `\i file.sql`.

## 42.13. Контрольные вопросы

1. Почему алиас из SELECT не работает в WHERE?
2. Чем WHERE отличается от HAVING?
3. Что вернёт `NOT IN (1, NULL)`?
4. Чем оконная функция отличается от GROUP BY?
5. Почему keyset-пагинация быстрее OFFSET?

## 42.14. Практика

> [!TASK] Напиши для сквозного проекта: (1) отчёт по категориям с FILTER и HAVING, (2) нарастающий баланс по счёту оконной функцией, (3) топ-3 расхода в каждой категории, (4) скользящее среднее за 7 операций, (5) рекурсивный обход дерева категорий, (6) upsert курса валют, (7) keyset-пагинацию ленты операций. Каждый запрос проверь на 100 000 сгенерированных строк.

---

# Глава 43. Индексы, транзакции и оптимизация

**Цель главы:** уметь объяснить, почему запрос медленный, и починить это, а также не потерять деньги при конкурентном доступе.

## 43.1. Как работает B-Tree

Индекс — сбалансированное дерево страниц (по 8 КБ). Поиск спускается от корня к листу за O(log n), затем при необходимости идёт по листьям (они связаны в список) для диапазонных сканов.

Отсюда всё остальное: индекс эффективен для `=`, диапазонов, `ORDER BY` и префиксов `LIKE 'abc%'`; бесполезен для `LIKE '%abc'` и для выражений, не совпадающих с индексированным выражением.

## 43.2. Типы индексов

| Тип | Для чего |
|---|---|
| B-Tree | равенство, диапазоны, сортировка — 95% случаев |
| GIN | `jsonb`, массивы, полнотекстовый поиск (много значений в одной строке) |
| GiST | геометрия, диапазоны, ближайший сосед |
| BRIN | огромные таблицы с естественной корреляцией по времени (крошечный размер) |
| Hash | только равенство, редко нужен |

## 43.3. Составные, покрывающие, частичные

```sql
-- правило левого префикса: работает для (account_id) и (account_id, created_at),
-- но НЕ для одного created_at
CREATE INDEX ops_account_created_idx ON operations (account_id, created_at DESC);

-- покрывающий: Index Only Scan без обращения к таблице
CREATE INDEX ops_cover_idx ON operations (account_id) INCLUDE (amount_minor);

-- частичный: маленький и горячий
CREATE INDEX ops_active_idx ON operations (created_at) WHERE deleted_at IS NULL;

-- по выражению: запрос должен использовать ТО ЖЕ выражение
CREATE INDEX users_email_lower_idx ON users (lower(email));
```

Порядок столбцов в составном индексе: сначала равенство, потом диапазон/сортировка. Индекс `(a, b)` не поможет запросу `WHERE b = ...`.

> [!WARNING] Каждый индекс замедляет `INSERT`/`UPDATE`/`DELETE` и занимает место. Обновление индексированного столбца блокирует HOT-оптимизацию и раздувает таблицу. Неиспользуемые индексы находи через `pg_stat_user_indexes.idx_scan = 0` и удаляй.

## 43.4. Чтение EXPLAIN

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM operations WHERE account_id = 42 ORDER BY created_at DESC LIMIT 20;
```

На что смотреть в первую очередь:

1. **Расхождение оценок и факта**: `rows=10` в плане против `actual rows=98000` — статистика врёт, нужен `ANALYZE` или расширенная статистика.
2. **Тип скана**: `Seq Scan` (чтение всей таблицы), `Index Scan`, `Index Only Scan` (лучший, если видимость позволяет), `Bitmap Heap Scan` (много совпадений).
3. **Тип соединения**: `Nested Loop` (хорош при малой внешней стороне), `Hash Join` (большие неупорядоченные наборы), `Merge Join` (оба упорядочены).
4. **Сортировка**: `Sort Method: external merge Disk: 45MB` — не хватает `work_mem`.
5. **BUFFERS**: `shared hit` (из кэша) против `read` (с диска).
6. **loops**: время узла умножается на число итераций — частая причина «незаметного» узкого места.

```sql
ANALYZE operations;
CREATE STATISTICS ops_account_category (dependencies) ON account_id, category_id FROM operations;
```

> [!TIP] `EXPLAIN` без `ANALYZE` показывает только оценку планировщика и **не выполняет** запрос. `ANALYZE` выполняет по-настоящему: осторожно с `DELETE`/`UPDATE` — оборачивай в транзакцию с `ROLLBACK`.

## 43.5. ACID и аномалии

**Atomicity** (всё или ничего), **Consistency** (ограничения соблюдены), **Isolation** (транзакции не мешают друг другу), **Durability** (подтверждённое не теряется).

Аномалии параллельного доступа: **dirty read** (чтение незакоммиченного), **non-repeatable read** (повторное чтение дало другое значение), **phantom read** (появились новые строки в диапазоне), **lost update** (два обновления затёрли друг друга), **write skew** (каждая транзакция по отдельности корректна, вместе — нарушают инвариант).

## 43.6. MVCC

PostgreSQL реализует изоляцию через **Multi-Version Concurrency Control**: обновление не меняет строку на месте, а создаёт новую версию. Служебные поля `xmin` (создавшая транзакция) и `xmax` (удалившая/заменившая) определяют, какая версия видна конкретному снимку.

Следствия:
- Читающие не блокируют пишущих и наоборот — это главное преимущество перед блокировочными СУБД.
- Старые версии становятся **мёртвыми кортежами** (dead tuples) → таблица и индексы раздуваются (bloat).
- Уборкой занимается `VACUUM`; `AUTOVACUUM` запускает его автоматически по порогам.
- `VACUUM FULL` переписывает таблицу целиком под эксклюзивной блокировкой — в продакшене почти всегда недопустим; используй `pg_repack`.
- Долгая транзакция (или забытый `idle in transaction`) удерживает горизонт видимости и **не даёт** VACUUM убрать мёртвые версии по всей базе.

```sql
SELECT pid, state, now() - xact_start AS xact_age, query
FROM pg_stat_activity WHERE state <> 'idle' ORDER BY xact_age DESC;

SELECT relname, n_live_tup, n_dead_tup, last_autovacuum FROM pg_stat_user_tables;
```

## 43.7. Уровни изоляции в PostgreSQL

| Уровень | Что предотвращает | Особенность |
|---|---|---|
| Read Committed (по умолчанию) | dirty read | снимок на **каждый оператор**; возможен lost update |
| Repeatable Read | + non-repeatable, phantom | снимок на транзакцию (snapshot isolation); при конфликте — ошибка 40001 |
| Serializable | + write skew | SSI с предикатными блокировками; требует retry-логики |

> [!NOTE] В PostgreSQL нет «грязного чтения» ни на одном уровне — MVCC его просто не допускает. И `Repeatable Read` здесь строже стандарта: он предотвращает фантомы, но всё ещё допускает write skew.

Практика: `Read Committed` + явные блокировки или атомарные `UPDATE ... WHERE` для大多数 сценариев; `Serializable` для сложных инвариантов с обязательным повтором транзакции при `serialization_failure`.

## 43.8. Блокировки: пессимистичные

```sql
BEGIN;
SELECT balance_minor FROM accounts WHERE id IN (1, 2) ORDER BY id FOR UPDATE;
-- пересчёт и запись проводок
COMMIT;
```

`FOR UPDATE` блокирует выбранные строки до конца транзакции. Варианты: `FOR NO KEY UPDATE`, `FOR SHARE`, `FOR KEY SHARE`. Модификаторы: `NOWAIT` (ошибка вместо ожидания), `SKIP LOCKED` (пропустить занятые).

> [!WARNING] Всегда блокируй строки в **детерминированном порядке** (например, `ORDER BY id`). Иначе две транзакции возьмут замки в обратном порядке и получат deadlock. PostgreSQL обнаружит его через `deadlock_timeout` и убьёт одну транзакцию — но лучше не доводить.

### 43.8.1. Очередь задач в PostgreSQL

```sql
UPDATE jobs SET status = 'processing', started_at = now()
WHERE id = (
    SELECT id FROM jobs WHERE status = 'pending'
    ORDER BY created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
RETURNING *;
```

`SKIP LOCKED` позволяет десяткам воркеров разбирать очередь без конфликтов и без внешнего брокера. Для умеренных нагрузок это полноценная замена RabbitMQ (глава 57).

### 43.8.2. Advisory locks

`pg_advisory_xact_lock(hashtext('report:' || account_id))` — именованный замок на уровне приложения, автоматически снимаемый в конце транзакции. Удобен для «не запускать два отчёта одновременно».

## 43.9. Оптимистичная блокировка

```sql
UPDATE accounts SET balance_minor = $1, version = version + 1
WHERE id = $2 AND version = $3;
-- 0 затронутых строк → кто-то опередил, повторяем бизнес-операцию
```

Не держит замков, отлично работает при редких конфликтах и в распределённых сценариях. Требует цикла повторов на уровне сервиса.

## 43.10. WAL, durability и соединения

**WAL** (Write-Ahead Log): изменения сначала пишутся в журнал, потом в файлы данных. Это обеспечивает восстановление после сбоя и является основой репликации (глава 60). `synchronous_commit=off` ускоряет запись ценой риска потерять последние миллисекунды подтверждённых транзакций — для финансовых операций недопустимо.

Каждое соединение PostgreSQL — отдельный процесс сервера (единицы мегабайт памяти). Отсюда `max_connections` обычно 100–200 и обязательный пулер: PgBouncer в режиме `transaction` (нюансы с prepared statements у asyncpg — глава 44) или встроенный пул SQLAlchemy.

## 43.11. Контрольные вопросы

1. Почему индекс не помогает при `LIKE '%abc'`?
2. Что означает `external merge Disk` в плане?
3. Как MVCC обеспечивает «читатели не блокируют писателей»?
4. Почему долгая транзакция вредит всей базе?
5. Чем `SKIP LOCKED` полезен для очередей?
6. Как избежать deadlock при переводе между счетами?

## 43.12. Практика

> [!TASK] (1) Сгенерируй 1 млн операций, сравни `Seq Scan` и `Index Scan` через `EXPLAIN (ANALYZE, BUFFERS)` до и после создания индекса. (2) Добейся `Index Only Scan` через `INCLUDE`. (3) Воспроизведи lost update двумя параллельными psql-сессиями на Read Committed, затем починить через `FOR UPDATE` и через `version`. (4) Реализуй очередь задач на `SKIP LOCKED` и запусти 5 воркеров. (5) Смоделируй deadlock и объясни его по логам.

---

# Глава 44. SQLAlchemy 2.0: Core и асинхронный ORM

**Цель главы:** освоить главный ORM Python-экосистемы в современном стиле и научиться видеть SQL, который он генерирует.

## 44.1. Драйверы и пул соединений

Спецификация **PEP 249 (DB-API 2.0)** описывает синхронный интерфейс драйверов. Для PostgreSQL актуальны:

- **asyncpg** — нативный асинхронный протокол, самый быстрый, не использует libpq;
- **psycopg3** — один пакет с sync и async режимами, libpq, серверные курсоры, лучшая совместимость с PgBouncer.

```python
from sqlalchemy.ext.asyncio import create_async_engine

engine = create_async_engine(
    "postgresql+asyncpg://user:pass@localhost/finance",
    pool_size=10,          # постоянные соединения
    max_overflow=5,        # временные сверх пула
    pool_timeout=30,       # ожидание свободного соединения
    pool_recycle=1800,     # переоткрывать против idle-таймаутов прокси
    pool_pre_ping=True,    # проверять живость перед выдачей
    echo=False,            # логировать SQL — только в разработке
)
```

> [!WARNING] При PgBouncer в режиме `transaction` кэш prepared statements у asyncpg конфликтует с переиспользованием серверных соединений. Отключай его: `connect_args={"statement_cache_size": 0}` (или используй PgBouncer 1.21+, где поддержка подготовленных выражений есть).

Размер пула считается от числа воркеров: `workers × (pool_size + max_overflow)` не должно превышать `max_connections` минус запас для миграций и админки.

## 44.2. Core и ORM

**Core** — SQL Expression Language: `Engine`, `Connection`, `MetaData`, `Table`, `select()`. **ORM** — надстройка: `DeclarativeBase`, `Mapped`, `Session`, отслеживание объектов.

В версии 2.0 синтаксис унифицирован: и Core, и ORM используют `select()` вместо устаревшего `session.query()`.

```python
from sqlalchemy import select
stmt = select(Operation).where(Operation.amount_minor < 0).order_by(Operation.created_at.desc())
```

Сгенерированный SQL всегда можно увидеть: `print(stmt.compile(engine, compile_kwargs={"literal_binds": True}))`. Это главный навык отладки ORM.

## 44.3. Декларативные модели

```python
from datetime import datetime
from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint("balance_minor >= 0", name="balance_non_negative"),
        Index("accounts_owner_currency_idx", "owner_id", "currency", unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    currency: Mapped[str] = mapped_column(String(3))
    balance_minor: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    entries: Mapped[list["LedgerEntry"]] = relationship(
        back_populates="account", lazy="raise"
    )
```

`Mapped[Optional[...]]` или `Mapped[X | None]` определяет `nullable`. `default` вычисляется на стороне Python, `server_default` — базой (важно для записей, вставленных мимо ORM).

> [!TIP] Задай `naming_convention` в `MetaData` Base. Без него Alembic не сможет стабильно именовать и удалять ограничения (глава 45).

## 44.4. Сессия: Unit of Work и Identity Map

`AsyncSession` реализует два паттерна: **Identity Map** (один объект на PK в рамках сессии) и **Unit of Work** (накапливает изменения и сбрасывает их одной транзакцией).

```python
from sqlalchemy.ext.asyncio import async_sessionmaker

Session = async_sessionmaker(engine, expire_on_commit=False)

async with Session() as session:
    async with session.begin():          # транзакция, commit/rollback автоматически
        account = await session.get(Account, 42)
        account.balance_minor -= 1500
        session.add(LedgerEntry(account_id=42, amount_minor=-1500))
```

| Метод | Что делает |
|---|---|
| `add` | помечает объект на вставку (pending) |
| `flush` | отправляет SQL в БД **без** commit (получаем id) |
| `commit` | flush + фиксация транзакции |
| `rollback` | откат и возврат объектов в исходное состояние |
| `refresh` | перечитать строку из БД |
| `expunge` | убрать объект из сессии (detached) |
| `get` | достать по PK (сначала Identity Map, потом БД) |

Состояния объекта: **transient** (создан, не в сессии), **pending** (add, ещё не flush), **persistent** (в сессии, есть в БД), **detached** (вне сессии), **deleted**.

> [!WARNING] `expire_on_commit=False` обязателен для async: иначе после commit все атрибуты помечаются устаревшими, и первое же обращение к `account.id` попытается сделать ленивый запрос вне async-контекста → `MissingGreenlet`.

## 44.5. Связи и проблема N+1

N+1 — это один запрос за списком и по одному запросу на каждую связанную сущность. На 1000 операций это 1001 round-trip.

```python
from sqlalchemy.orm import selectinload, joinedload, raiseload

# коллекции (one-to-many, many-to-many): второй запрос с IN
stmt = select(Account).options(selectinload(Account.entries))

# many-to-one / one-to-one: JOIN в одном запросе
stmt = select(LedgerEntry).options(joinedload(LedgerEntry.account))
result = await session.execute(stmt)
entries = result.unique().scalars().all()      # unique() обязателен при joinedload

# защита от случайной ленивой загрузки
stmt = select(Account).options(raiseload("*"))
```

| Стратегия | Когда | Особенность |
|---|---|---|
| `selectinload` | коллекции | отдельный запрос `WHERE id IN (...)`, без дублирования строк |
| `joinedload` | many-to-one, one-to-one | JOIN, требует `result.unique()` |
| `subqueryload` | коллекции (legacy) | подзапрос, обычно хуже selectinload |
| `contains_eager` | JOIN уже написан вручную | заполняет связь из своих колонок |
| `raiseload("*")` | всегда в продакшене | падает вместо тихого N+1 |
| `lazy="raise"` | в определении relationship | то же на уровне модели |

> [!NOTE] В async SQLAlchemy **ленивая загрузка запрещена**: она требует синхронного I/O внутри greenlet-контекста и падает с `MissingGreenlet`. Это не ограничение, а подарок: ты вынужден явно объявлять, что грузить. Ставь `lazy="raise"` по умолчанию во всех relationship.

`contains_eager` для фильтрации по связанной таблице с одновременной подгрузкой:

```python
stmt = (
    select(LedgerEntry)
    .join(LedgerEntry.account)
    .where(Account.currency == "RUB")
    .options(contains_eager(LedgerEntry.account))
)
```

## 44.6. Сложные запросы

```python
from sqlalchemy import case, cast, func, select, Numeric
from sqlalchemy.orm import aliased

stmt = (
    select(
        Account.id,
        func.sum(LedgerEntry.amount_minor).label("total"),
        func.sum(case((LedgerEntry.amount_minor < 0, LedgerEntry.amount_minor), else_=0)).label("expenses"),
    )
    .join(LedgerEntry, LedgerEntry.account_id == Account.id)
    .group_by(Account.id)
    .having(func.sum(LedgerEntry.amount_minor) < 0)
)

# оконная функция
running = func.sum(LedgerEntry.amount_minor).over(
    partition_by=LedgerEntry.account_id, order_by=LedgerEntry.created_at
)

# CTE и алиасы
monthly = select(...).cte("monthly")
parent = aliased(Category)
```

Для вычисляемых полей, работающих и в Python, и в SQL, есть `@hybrid_property` с `.expression`.

## 44.7. Массовые операции

```python
from sqlalchemy import insert, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

await session.execute(insert(LedgerEntry), [
    {"account_id": 1, "amount_minor": -100},
    {"account_id": 2, "amount_minor": 100},
])   # executemany: в разы быстрее создания ORM-объектов в цикле

await session.execute(
    update(Account).where(Account.currency == "RUB").values(currency="RUB")
)

stmt = pg_insert(Rate).values(code="USD", value=92.5)
stmt = stmt.on_conflict_do_update(index_elements=[Rate.code], set_={"value": stmt.excluded.value})
await session.execute(stmt)
```

> [!WARNING] Массовые `update`/`delete` **не синхронизируют** объекты уже загруженные в сессию (Identity Map устареет) и не запускают ORM-события. После них делай `session.expire_all()` или используй свежие объекты.

Для чтения миллионов строк — потоковая выдача: `(await session.stream_scalars(stmt)).yield_per(1000)`.

## 44.8. Repository и Unit of Work

Порты из главы 26 получают реализацию поверх сессии.

```python
class SqlAlchemyAccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_update(self, account_id: int) -> Account | None:
        stmt = select(Account).where(Account.id == account_id).with_for_update()
        return await self._session.scalar(stmt)

    async def add_entry(self, entry: LedgerEntry) -> None:
        self._session.add(entry)


class SqlAlchemyUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._factory = session_factory

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        self._session = self._factory()
        self.accounts = SqlAlchemyAccountRepository(self._session)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            await self._session.rollback()
        await self._session.close()

    async def commit(self) -> None:
        await self._session.commit()
```

Ключевое: **одна бизнес-операция — один UoW — одна транзакция**. Репозитории не коммитят сами; коммитит сервисный слой, знающий границы операции. Это делает перевод между счетами атомарным.

## 44.9. Перевод средств: всё вместе

```python
async def transfer(uow: SqlAlchemyUnitOfWork, src: int, dst: int, amount: int) -> None:
    async with uow:
        # детерминированный порядок блокировки — защита от deadlock
        first, second = sorted([src, dst])
        a = await uow.accounts.get_for_update(first)
        b = await uow.accounts.get_for_update(second)
        source, target = (a, b) if a.id == src else (b, a)

        if source.balance_minor < amount:
            raise InsufficientFunds(source.balance_minor, amount)

        source.balance_minor -= amount
        target.balance_minor += amount
        uow.entries.add_many([
            LedgerEntry(account_id=src, amount_minor=-amount),
            LedgerEntry(account_id=dst, amount_minor=amount),
        ])
        await uow.commit()
```

## 44.10. Тестирование и альтернативы

Тестируй на **настоящем PostgreSQL** (testcontainers или отдельная тестовая база в CI). SQLite не воспроизводит `FOR UPDATE`, `SKIP LOCKED`, уровни изоляции, `jsonb` и типы — зелёные тесты на SQLite ничего не говорят о поведении в продакшене.

Альтернативы SQLAlchemy: **SQLModel** (обёртка автора FastAPI над SQLAlchemy + Pydantic, удобна для CRUD, но скрывает механику и отстаёт по версиям), **Tortoise ORM** (async в стиле Django), **Piccolo**, а также raw SQL через `asyncpg` + `aiosql` для участков, критичных к латентности.

> [!NOTE] SQLAlchemy реализует **Data Mapper** (объект не знает о БД), в отличие от **Active Record** (Django ORM, где `obj.save()`). Data Mapper сложнее на старте, но позволяет держать домен чистым — что и требуется в главе 58.

## 44.11. Контрольные вопросы

1. Чем Core отличается от ORM?
2. Зачем `expire_on_commit=False` в async?
3. Разница `flush` и `commit`?
4. Почему `joinedload` требует `unique()`?
5. Что такое `MissingGreenlet` и как его предотвратить?
6. Почему репозиторий не должен вызывать commit?

## 44.12. Практика

> [!TASK] Переведи сквозной проект на PostgreSQL + SQLAlchemy 2.0 async: модели с `Mapped`, `lazy="raise"` везде, пул с pre_ping, UoW и репозитории, перевод средств с `with_for_update` в детерминированном порядке, upsert курсов, отчёт агрегацией в SQL (не в Python). Включи `echo=True` и найди все N+1; добавь тест, который падает при попытке ленивой загрузки.

---

# Глава 45. Миграции: Alembic и zero-downtime

**Цель главы:** менять схему базы под работающим сервисом, не останавливая его и не теряя данные.

## 45.1. Зачем миграции

Схема — часть кода, значит она должна версионироваться, ревьюиться и применяться автоматически и одинаково во всех окружениях. `Base.metadata.create_all()` годится только для прототипа: он не умеет **изменять** существующие таблицы.

## 45.2. Инициализация async-проекта

```bash
uv add sqlalchemy asyncpg alembic
alembic init -t async migrations
```

Ключевые правки в `migrations/env.py`:

```python
from finance.models import Base          # импорт ВСЕХ моделей обязателен
from finance.config import settings

config.set_main_option("sqlalchemy.url", settings.database_url)
target_metadata = Base.metadata


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,             # видеть изменения типов
        compare_server_default=True,   # видеть изменения server_default
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    connectable = async_engine_from_config(...)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()
```

> [!WARNING] Если модель не импортирована до чтения `Base.metadata`, autogenerate её «не увидит» и предложит **удалить** таблицу. Держи единый модуль, импортирующий все модели, и импортируй его в env.py.

## 45.3. Naming convention

```python
NAMING_CONVENTION = {
    "ix": "%(table_name)s_%(column_0_name)s_idx",
    "uq": "%(table_name)s_%(column_0_name)s_key",
    "ck": "%(table_name)s_%(constraint_name)s_check",
    "fk": "%(table_name)s_%(column_0_name)s_fkey",
    "pk": "%(table_name)s_pkey",
}

class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
```

Без соглашения об именах безымянные ограничения получают автогенерированные суффиксы, и `downgrade` не может их найти. Это причина №1 «сломанных» миграций в командах.

## 45.4. Генерация и обязательная ревизия

```bash
alembic revision --autogenerate -m "add ledger tables"
alembic upgrade head
alembic current
alembic history --verbose
alembic downgrade -1
```

Autogenerate **не видит** или видит неверно: переименования (генерирует drop + add = потеря данных), изменения типов и размеров, изменения Enum, частичные и функциональные индексы, `CHECK`-выражения, триггеры, представления, функции, данные.

> [!NOTE] Сгенерированный файл — черновик, а не результат. Ревизия миграции на code review обязательна так же, как ревизия кода. Правило: прочитай каждый `op.*` и спроси «что произойдёт на таблице в 50 млн строк под нагрузкой».

## 45.5. Ветвление в команде

Два разработчика создали ревизии от одного родителя → два head. Alembic откажется применять, пока не разрешишь:

```bash
alembic heads
alembic merge -m "merge ledger and rates" abc123 def456
alembic upgrade head
```

Профилактика: проверка одного head в CI (`alembic heads` должен вернуть одну строку) и правило «ревизия создаётся только после синхронизации с main».

## 45.6. Миграции данных

Схему и данные разделяй на разные ревизии. Данные обновляй **батчами**, чтобы не держать гигантскую транзакцию и не блокировать таблицу:

```python
def upgrade() -> None:
    conn = op.get_bind()
    while True:
        result = conn.execute(sa.text("""
            UPDATE operations SET amount_minor = amount * 100
            WHERE id IN (
                SELECT id FROM operations WHERE amount_minor IS NULL LIMIT 5000
            )
        """))
        if result.rowcount == 0:
            break
```

> [!WARNING] Не импортируй ORM-модели приложения в миграцию: модель эволюционирует, а миграция должна навсегда остаться исполняемой в том виде, в котором была написана. Используй `sa.table(...)` с явными колонками или raw SQL.

## 45.7. Zero-downtime: паттерн Expand-Contract

Задача: переименовать/перевести колонку так, чтобы старая и новая версии приложения работали одновременно (rolling update).

1. **Expand:** добавить новую колонку `NULL`-able, без блокировок и без изменения контракта.
2. **Двойная запись:** приложение пишет и в старое, и в новое поле; чтение пока из старого.
3. **Backfill:** перенести исторические данные батчами.
4. **Переключение чтения** на новое поле (фиче-флаг).
5. **Contract:** добавить `NOT NULL`/ограничения, убрать двойную запись, удалить старую колонку — только когда все инстансы обновлены.

Каждый шаг — отдельный деплой. Ломать совместимость можно лишь на последнем шаге (принцип N-1 совместимости).

## 45.8. Опасные операции и безопасные аналоги

```python
def upgrade() -> None:
    # индекс без блокировки записи: требует autocommit-режима
    with op.get_context().autocommit_block():
        op.create_index(
            "operations_created_idx", "operations", ["created_at"],
            postgresql_concurrently=True,
        )

    # NOT NULL без долгого ACCESS EXCLUSIVE: через NOT VALID + VALIDATE
    op.execute("SET lock_timeout = '3s'")
    op.execute("""
        ALTER TABLE operations
        ADD CONSTRAINT ops_amount_not_null CHECK (amount_minor IS NOT NULL) NOT VALID
    """)
    op.execute("ALTER TABLE operations VALIDATE CONSTRAINT ops_amount_not_null")
    op.execute("ALTER TABLE operations ALTER COLUMN amount_minor SET NOT NULL")
```

| Опасно | Почему | Безопасно |
|---|---|---|
| `CREATE INDEX` | блокирует запись на всё время построения | `CONCURRENTLY` в autocommit-блоке |
| `ADD COLUMN NOT NULL DEFAULT` | перезапись таблицы (в старых версиях) | nullable → backfill → NOT NULL |
| `ALTER TYPE` | перезапись и долгая блокировка | новая колонка + backfill |
| `ADD CONSTRAINT` | долгая проверка под эксклюзивной блокировкой | `NOT VALID` затем `VALIDATE` |
| `DROP COLUMN` | ломает старую версию приложения | сначала убрать использование, потом удалить |

> [!WARNING] `ALTER TABLE` берёт `ACCESS EXCLUSIVE`. Даже если сама операция мгновенна, она встаёт в очередь за долгим запросом — и **все** новые запросы к таблице встают за ней. Всегда ставь `lock_timeout` (2–5 секунд) и повторяй попытку, а не жди минуту, положив сервис.

Добавление значения в нативный Enum тоже требует autocommit-блока: `ALTER TYPE ... ADD VALUE` нельзя выполнять внутри транзакции.

## 45.9. Порядок деплоя и откат

Правило: миграции применяются **до** выкатки нового кода, и они обязаны быть совместимы со старым кодом (Expand-Contract это гарантирует). `downgrade` пиши всегда, но помни: откат удаления данных невозможен — реальная стратегия восстановления — резервные копии и PITR.

Проверяй миграции на копии продакшен-объёма данных: то, что заняло 20 мс на 1000 строк, может занять 20 минут на 100 млн.

## 45.10. Контрольные вопросы

1. Что autogenerate не замечает?
2. Зачем naming_convention?
3. Как разрешить два head?
4. Перечисли шаги Expand-Contract.
5. Почему `CREATE INDEX CONCURRENTLY` требует autocommit-блока?
6. Зачем `lock_timeout` перед ALTER TABLE?

## 45.11. Практика

> [!TASK] Настрой Alembic async с naming_convention и compare_type. Создай первоначальную схему, затем выполни полный цикл Expand-Contract: переведи `operations.amount` (numeric) в `amount_minor` (bigint) с двойной записью, батчевым backfill, переключением чтения и удалением старой колонки — пять отдельных ревизий. Добавь индекс `CONCURRENTLY`, поставь `lock_timeout`, проверь одно head в CI и убедись, что старая версия приложения работает на каждом промежуточном шаге.

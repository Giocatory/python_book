# Глава 22. Классы и объекты

**Цель главы:** научиться связывать данные и поведение в один объект, управлять доступом к состоянию и понимать, что происходит с объектом в памяти.

## 22.1. Зачем нужны классы

Функция отвечает на вопрос «что сделать». Класс отвечает на вопрос «кто это делает и что он при этом помнит». Класс нужен, когда есть **состояние, живущее дольше одного вызова**, и набор операций над ним.

Признаки того, что класс уместен: несколько функций принимают один и тот же набор аргументов; вокруг структуры данных есть инварианты (баланс не может стать отрицательным); нужно несколько взаимозаменяемых реализаций одного поведения.

> [!NOTE] Класс — не «обязательная обёртка для кода». Если у класса один метод и нет состояния, тебе нужна функция. `class DataProcessor: def process(self, data)` — типичный антипаттерн Java-стиля в Python.

## 22.2. Определение класса и экземпляра

```python
class Account:
    currency = "RUB"                 # атрибут класса

    def __init__(self, owner: str, balance: int = 0) -> None:
        self.owner = owner           # атрибуты экземпляра
        self.balance = balance

    def deposit(self, amount: int) -> None:
        self.balance += amount


acc = Account("Anna", 1000)
acc.deposit(500)
```

### 22.2.1. Что делает self

`self` — ссылка на конкретный экземпляр. Вызов `acc.deposit(500)` интерпретатор разворачивает в `Account.deposit(acc, 500)`. Имя `self` — соглашение, а не ключевое слово, но нарушать его нельзя.

### 22.2.2. __init__ — это инициализатор, не конструктор

Объект создаёт `__new__`, а `__init__` лишь заполняет его полями. Поэтому `__init__` ничего не возвращает (точнее, возвращать что-то кроме `None` — ошибка).

## 22.3. Атрибуты класса против атрибутов экземпляра

Поиск атрибута идёт сначала в `instance.__dict__`, затем в `type(instance).__dict__` и далее по MRO (глава 23).

```python
class Bad:
    operations = []          # ОДИН список на все экземпляры

a, b = Bad(), Bad()
a.operations.append(1)
print(b.operations)          # [1] — сюрприз
```

> [!WARNING] Изменяемый атрибут класса разделяется всеми экземплярами. Списки, словари и множества создавай в `__init__`. Атрибуты класса — только константы, счётчики и настройки.

Атрибут класса можно использовать осознанно:

```python
class Account:
    total_count = 0

    def __init__(self, owner: str) -> None:
        self.owner = owner
        Account.total_count += 1     # общий счётчик — это нормально
```

## 22.4. Три вида методов

```python
class Money:
    def __init__(self, amount: int) -> None:
        self.amount = amount

    def scaled(self, k: int) -> "Money":       # обычный: работает с self
        return Money(self.amount * k)

    @classmethod
    def from_string(cls, raw: str) -> "Money": # альтернативный конструктор
        return cls(int(raw))

    @staticmethod
    def is_valid(raw: str) -> bool:            # утилита в пространстве имён класса
        return raw.lstrip("-").isdigit()
```

| Вид | Первый аргумент | Типичное применение |
|---|---|---|
| обычный метод | `self` | работа с состоянием экземпляра |
| `@classmethod` | `cls` | фабричные методы, наследуемые конструкторы |
| `@staticmethod` | нет | функция, логически принадлежащая классу |

> [!TIP] `@classmethod` для альтернативных конструкторов (`from_string`, `from_dict`, `from_orm`) — идиоматичный Python. Он корректно работает при наследовании, потому что получает `cls`, а не жёстко зашитый класс.

## 22.5. property: управляемый доступ

```python
class Account:
    def __init__(self) -> None:
        self._balance = 0

    @property
    def balance(self) -> int:
        return self._balance

    @balance.setter
    def balance(self, value: int) -> None:
        if value < 0:
            raise ValueError("Баланс не может быть отрицательным")
        self._balance = value

    @balance.deleter
    def balance(self) -> None:
        raise AttributeError("Баланс удалять нельзя")
```

Снаружи это выглядит как обычное поле: `acc.balance = 100`. Внутри — валидация.

> [!NOTE] В Python не пишут геттеры и сеттеры «на всякий случай», как в Java. Начинают с открытого атрибута, а когда появляется логика — заменяют его на `property`, не меняя внешний код. Это и есть питоническая инкапсуляция.

Вычисляемое свойство без сеттера — способ держать один источник правды:

```python
@property
def total(self) -> int:
    return sum(op.amount for op in self.operations)
```

## 22.6. Инкапсуляция: соглашения вместо запретов

- `name` — публичный API.
- `_name` — внутреннее, «не трогай снаружи», не импортируется через `from m import *`.
- `__name` — name mangling: внутри класса превращается в `_ClassName__name`.

```python
class Account:
    def __init__(self):
        self.__pin = "1234"

acc.__pin        # AttributeError
acc._Account__pin  # работает — защиты нет, есть только сигнал
```

> [!NOTE] `__private` нужен не для «безопасности», а чтобы избежать случайного конфликта имён при наследовании. В прикладном коде почти всегда достаточно одного подчёркивания.

## 22.7. Жизненный цикл объекта в CPython

### 22.7.1. Подсчёт ссылок

Основной механизм управления памятью — **reference counting**. У объекта есть счётчик ссылок; когда он падает до нуля, память освобождается немедленно.

```python
import sys
a = []
print(sys.getrefcount(a))   # на 1 больше ожидаемого: аргумент функции тоже ссылка
```

### 22.7.2. Сборщик мусора для циклов

Подсчёт ссылок не может освободить цикл (`a.ref = b; b.ref = a`). Для этого работает **generational GC**: три поколения, новые объекты проверяются чаще, пережившие сборки переходят в старшие поколения.

```python
import gc
gc.collect()          # принудительная сборка
gc.get_count()        # счётчики поколений
```

### 22.7.3. Почему не стоит писать __del__

`__del__` вызывается в неопределённый момент, может не вызваться вовсе при циклах и интерпретаторном shutdown, а исключение внутри него лишь печатается в stderr. Освобождение ресурсов делай через контекстный менеджер (глава 18), а не через финализатор.

### 22.7.4. Слабые ссылки

```python
import weakref

cache = weakref.WeakValueDictionary()   # не мешает объектам умирать
ref = weakref.ref(obj)                  # obj() вернёт объект или None
```

Слабые ссылки — стандартный способ сделать кэш, который не превращается в утечку памяти.

## 22.8. __slots__: экономия памяти

```python
class Operation:
    __slots__ = ("id", "amount", "category")

    def __init__(self, id: int, amount: int, category: str) -> None:
        self.id, self.amount, self.category = id, amount, category
```

Обычный экземпляр хранит атрибуты в словаре `__dict__`. `__slots__` заменяет его на фиксированный массив дескрипторов: экономия памяти в разы на миллионах объектов и чуть более быстрый доступ.

Цена: нельзя добавлять новые атрибуты, нет `__dict__`, слабые ссылки требуют явного слота `"__weakref__"`, а множественное наследование двух классов с непустыми слотами невозможно.

> [!TIP] Не ставь `__slots__` преждевременно. Сначала измерь память (глава 31), потом оптимизируй. Для dataclass это делается одним флагом `slots=True` (глава 25).

## 22.9. Контрольные вопросы

1. Чем атрибут класса отличается от атрибута экземпляра?
2. Почему изменяемый атрибут класса — ловушка?
3. Когда нужен `@classmethod`, а когда `@staticmethod`?
4. Как `property` позволяет не писать геттеры заранее?
5. Что освобождает циклические ссылки, если refcount не справляется?

## 22.10. Практика

> [!TASK] Спроектируй класс `Account`: приватный `_balance` в копейках, `property` с валидацией, методы `deposit` и `withdraw` (с проверкой достаточности и доменным исключением из главы 19), `@classmethod from_dict`, счётчик созданных счетов. Затем добавь `__slots__` и замерь `sys.getsizeof` плюс `__dict__` до и после на 100 000 экземпляров.

---

# Глава 23. Наследование, MRO и super()

**Цель главы:** понять, как Python разрешает порядок поиска атрибутов, и научиться строить иерархии, которые не разваливаются.

## 23.1. Наследование против композиции

Наследование выражает отношение «является» (`SavingsAccount` — это `Account`). Композиция выражает «содержит» (`Account` содержит `Currency`).

> [!NOTE] Правило Composition over Inheritance: наследование связывает классы жёстко и навсегда, композиция позволяет менять поведение в рантайме. Если сомневаешься — выбирай композицию.

Признак злоупотребления наследованием: подкласс переопределяет половину методов или бросает `NotImplementedError` в унаследованных. Это нарушение LSP (глава 26).

## 23.2. Базовое наследование и super()

```python
class Account:
    def __init__(self, owner: str) -> None:
        self.owner = owner
        self.operations: list[int] = []

    def describe(self) -> str:
        return f"Счёт {self.owner}"


class SavingsAccount(Account):
    def __init__(self, owner: str, rate: float) -> None:
        super().__init__(owner)        # обязательный вызов родителя
        self.rate = rate

    def describe(self) -> str:
        base = super().describe()
        return f"{base}, ставка {self.rate}%"
```

`super()` возвращает прокси-объект, который ищет метод **следующего класса в MRO**, а не просто «родителя». Это принципиально для множественного наследования.

> [!WARNING] Забытый `super().__init__()` — самая частая ошибка: поля родителя не создаются, и объект падает при первом обращении.

## 23.3. MRO и C3-линеаризация

При множественном наследовании Python строит **MRO** (Method Resolution Order) по алгоритму C3: порядок согласован с локальным порядком базовых классов и монотонен (порядок родителей не переставляется в потомках).

```python
class A: pass
class B(A): pass
class C(A): pass
class D(B, C): pass

print([cls.__name__ for cls in D.mro()])
# ['D', 'B', 'C', 'A', 'object']
```

Классический «ромб» решается так, что `A` вызывается **один раз**, после `B` и `C`.

Если согласованный порядок построить нельзя, Python откажется создавать класс:

```python
class X(A, B): pass    # TypeError:Cannot create a consistent MRO
```

> [!TIP] MRO — не магия. Всегда можно посмотреть глазами: `Cls.mro()` или `Cls.__mro__`. При отладке «вызвался не тот метод» это первое, что нужно проверить.

## 23.4. Миксины

Миксин — маленький класс, добавляющий одну возможность и не предназначенный для самостоятельного использования.

```python
class ReprMixin:
    def __repr__(self) -> str:
        fields = ", ".join(f"{k}={v!r}" for k, v in vars(self).items())
        return f"{type(self).__name__}({fields})"


class JsonMixin:
    def to_json(self) -> str:
        import json
        return json.dumps(vars(self), ensure_ascii=False)


class Operation(ReprMixin, JsonMixin):
    def __init__(self, amount: int) -> None:
        self.amount = amount
```

Правила: миксины идут **слева** от основного базового класса, не имеют `__init__`, не хранят состояние, называются с суффиксом `Mixin`. Больше двух-трёх миксинов — сигнал, что нужна композиция.

## 23.5. Кооперативные иерархии

Чтобы `super()` корректно прошёл всю цепочку, все участники должны вызывать его и принимать совместимые аргументы.

```python
class Base:
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

class Timestamped(Base):
    def __init__(self, created_at=None, **kwargs):
        self.created_at = created_at
        super().__init__(**kwargs)
```

Проброс `**kwargs` — стандартный приём для кооперативных миксинов. Без него цепочка обрывается на первом классе, который «съел» аргументы.

## 23.6. __init_subclass__: плагины без метаклассов

```python
class Operation:
    registry: dict[str, type["Operation"]] = {}

    def __init_subclass__(cls, /, code: str, **kwargs):
        super().__init_subclass__(**kwargs)
        Operation.registry[code] = cls


class Income(Operation, code="income"):
    pass


class Expense(Operation, code="expense"):
    pass

print(Operation.registry)   # {'income': Income, 'expense': Expense}
```

`__init_subclass__` вызывается автоматически при создании каждого подкласса (неявно является classmethod). Это современная, читаемая замена метаклассам для регистрации плагинов, валидации контрактов и настройки ORM.

## 23.7. Метаклассы — обзорно

Класс тоже объект, и его тип — `type`. Метакласс — это «класс класса».

```python
class Meta(type):
    def __new__(mcls, name, bases, namespace, **kw):
        namespace["created_by_meta"] = True
        return super().__new__(mcls, name, bases, namespace)

class Model(metaclass=Meta):
    pass
```

Метаклассы нужны авторам фреймворков (так устроены Django Models и SQLAlchemy DeclarativeBase). В прикладном коде они почти всегда избыточны: 95% задач решаются `__init_subclass__`, декораторами классов или дескрипторами.

> [!NOTE] Если ты не пишешь фреймворк, а думаешь «мне нужен метакласс» — почти наверняка не нужен.

## 23.8. Контрольные вопросы

1. Что именно ищет `super()`?
2. Как посмотреть MRO и когда её построение невозможно?
3. Почему миксины ставят слева?
4. Чем `__init_subclass__` лучше метакласса?

## 23.9. Практика

> [!TASK] Построй иерархию операций: базовый `Operation`, миксины `ReprMixin` и `ComparableMixin`, подклассы `Income`/`Expense`/`Transfer` с регистрацией через `__init_subclass__(code=...)`. Выведи MRO каждого класса и объясни порядок. Затем добавь `SavingsAccount` с кооперативным `__init__` через `**kwargs`.

---

# Глава 24. Data Model: магические методы и протоколы

**Цель главы:** сделать свои объекты «родными» для языка — чтобы они работали с `len()`, `sorted()`, `in`, `+`, `with` иunpacking.

## 24.1. Философия протоколов

В Python нет ключевого слова `interface`. Вместо него — **протоколы**: негласные контракты вида «реализуй `__len__` и `__getitem__`, и ты последовательность». Функции языка (`len`, `iter`, `sorted`, `repr`, `hash`) вызывают соответствующие dunder-методы.

> [!NOTE] Dunder-методы не вызывают напрямую. Пиши `len(obj)`, а не `obj.__len__()`. И реализуй `__len__`, а не свой метод `size()` — тогда объект заработает со всей экосистемой.

## 24.2. Представление: __repr__ и __str__

```python
class Money:
    def __init__(self, kopecks: int) -> None:
        self.kopecks = kopecks

    def __repr__(self) -> str:
        return f"Money(kopecks={self.kopecks!r})"   # для разработчика

    def __str__(self) -> str:
        return f"{self.kopecks / 100:.2f} ₽"        # для пользователя
```

`__repr__` — однозначное, по возможности валидное выражение для воссоздания объекта; используется в отладчике, логах, при выводе коллекций. `__str__` — человекочитаемо; если не определён, используется `__repr__`.

> [!TIP] Реализуй `__repr__` всегда. Это самая дешёвая инвестиция в отладку: без неё в логах ты видишь `<__main__.Money object at 0x7f...>`.

## 24.3. Сравнение и хэширование

```python
from functools import total_ordering


@total_ordering
class Money:
    def __init__(self, kopecks: int) -> None:
        self.kopecks = kopecks

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        return self.kopecks == other.kopecks

    def __lt__(self, other: "Money") -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        return self.kopecks < other.kopecks

    def __hash__(self) -> int:
        return hash(self.kopecks)
```

### 24.3.1. Контракт eq/hash

Если `a == b`, то обязательно `hash(a) == hash(b)`. Иначе словарь и множество будут работать некорректно.

> [!WARNING] Определив `__eq__` без `__hash__`, ты автоматически делаешь класс **нехэшируемым** (Python выставляет `__hash__ = None`). Это правильное поведение по умолчанию: изменяемый объект не должен быть ключом словаря, ведь его хэш «уплывёт».

Правило: хэшируемы только **неизменяемые** value-объекты. Для изменяемых сущностей (Entity в DDD) сравнивают по `id`, а хэш делают от `id`.

### 24.3.2. NotImplemented против NotImplementedError

`NotImplemented` — специальное значение, говорящее «я не умею сравнивать с этим типом, попробуй отражённую операцию у другого объекта». `NotImplementedError` — исключение, означающее «метод не реализован». Путать их нельзя.

`@total_ordering` достраивает `<=`, `>`, `>=` из `__eq__` и одного метода сравнения.

## 24.4. Протокол контейнера

```python
class Ledger:
    def __init__(self) -> None:
        self._ops: list[int] = []

    def __len__(self) -> int:
        return len(self._ops)

    def __getitem__(self, index):        # поддерживает и срезы
        return self._ops[index]

    def __setitem__(self, index, value) -> None:
        self._ops[index] = value

    def __delitem__(self, index) -> None:
        del self._ops[index]

    def __contains__(self, value) -> bool:
        return value in self._ops

    def __iter__(self):
        return iter(self._ops)
```

Бонус: реализовав `__getitem__` и `__len__`, ты бесплатно получаешь распаковку, `reversed()` и работу `in` (последнее — даже без `__contains__`, через перебор).

## 24.5. Арифметика: value-объекты

```python
class Money:
    def __add__(self, other: "Money") -> "Money":
        if not isinstance(other, Money):
            return NotImplemented
        return Money(self.kopecks + other.kopecks)

    def __mul__(self, k: int) -> "Money":
        return Money(self.kopecks * k)

    __rmul__ = __mul__          # чтобы работало 3 * money

    def __neg__(self) -> "Money":
        return Money(-self.kopecks)
```

Отражённые версии (`__radd__`, `__rmul__`) вызываются, когда левый операнд не умеет работать с нашим типом. Именно поэтому `sum()` по объектам Money требует `__radd__` (стартовое значение — int 0).

## 24.6. Вызов и доступ к атрибутам

```python
class Validator:
    def __call__(self, value: str) -> bool:     # объект как функция
        return value.isdigit()


class Lazy:
    def __getattr__(self, name):        # только когда обычный поиск НЕ нашёл
        return f"нет атрибута {name}"

    def __getattribute__(self, name):   # вызывается ВСЕГДА — опасно
        return super().__getattribute__(name)
```

`__getattr__` уместен для ленивых прокси и адаптеров чужих API. `__getattribute__` перехватывает всё, включая `self.anything`, и легко приводит к бесконечной рекурсии — трогай только осознанно.

> [!WARNING] `__getattr__`, возвращающий значение для любого имени, ломает `hasattr`, `copy`, `pickle` и отладку. Всегда бросай `AttributeError` для неизвестных имён, особенно для имён вида `__something__`.

## 24.7. Копирование и сериализация

- `__copy__` / `__deepcopy__` — управляют поведением `copy.copy` и `copy.deepcopy`.
- `__getstate__` / `__setstate__` — управляют `pickle`.
- `__reduce__` — низкоуровневый протокол pickle.

> [!WARNING] Никогда не десериализуй `pickle` из недоверенного источника: он выполняет произвольный код. Для обмена данными — JSON, для внутренних кэшей — тоже лучше JSON или msgpack.

## 24.8. Контекстные и асинхронные протоколы

```python
class Connection:
    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.close()
        return False        # False — не подавлять исключение


class AsyncConnection:
    async def __aenter__(self): ...
    async def __aexit__(self, exc_type, exc, tb): ...
```

Возврат истинного значения из `__exit__` **подавляет** исключение — почти всегда это ошибка. Также существуют `__await__`, `__aiter__`/`__anext__` (глава 37) и дескрипторы `__get__`/`__set__`/`__set_name__`, на которых построены `property`, `classmethod` и поля ORM.

## 24.9. Контрольные вопросы

1. Чем `__repr__` отличается от `__str__` и какой важнее?
2. Что произойдёт, если определить `__eq__` без `__hash__`?
3. Зачем возвращать `NotImplemented`?
4. Чем `__getattr__` отличается от `__getattribute__`?
5. Какие методы нужно реализовать, чтобы объект поддерживал `len()`, срезы и `in`?

## 24.10. Практика

> [!TASK] Доведи `Money` до полноценного value-объекта: `__repr__`, `__str__`, `__eq__`, `__hash__`, `__lt__` с `total_ordering`, `__add__`, `__sub__`, `__mul__`, `__rmul__`, `__neg__`, `__bool__`. Проверь: работает в `set`, как ключ `dict`, в `sorted`, в `sum(..., Money(0))`. Убедись, что `Money(100) == 100` возвращает `False`, а не падает.

---

# Глава 25. dataclasses, Enum и NamedTuple

**Цель главы:** избавиться от шаблонного кода и научиться выбирать правильную структуру данных для модели.

## 25.1. Проблема boilerplate

Класс-контейнер из пяти полей требует `__init__`, `__repr__`, `__eq__` — 40 строк скучного кода, который легко написать с ошибкой. `dataclasses` генерирует их автоматически по аннотациям.

## 25.2. Базовый dataclass

```python
from dataclasses import dataclass, field
from datetime import date


@dataclass
class Operation:
    id: int
    amount: int
    category: str
    created: date
    tags: list[str] = field(default_factory=list)
```

Декоратор создаёт `__init__`, `__repr__`, `__eq__` (и `__hash__` по правилам). Поля — это **аннотированные** атрибуты класса; без аннотации поле не считается полем.

> [!WARNING] `tags: list[str] = []` вызовет `ValueError` при определении класса — dataclasses намеренно запрещают изменяемые дефолты. Используй `field(default_factory=list)`.

Полезные параметры `field`: `default`, `default_factory`, `repr=False`, `compare=False`, `init=False`, `kw_only=True`, `metadata={...}`.

## 25.3. Флаги dataclass

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class Money:
    kopecks: int
    currency: str = "RUB"
```

- `frozen=True` — неизменяемость: присваивание бросает `FrozenInstanceError`, объект становится хэшируемым (при `eq=True`).
- `slots=True` (3.10+) — автоматический `__slots__`, экономия памяти.
- `kw_only=True` (3.10+) — все поля только именованные; спасает от ошибок порядка аргументов и позволяет иметь обязательные поля после необязательных.
- `order=True` — генерирует методы сравнения для сортировки.

> [!NOTE] `frozen=True` + `slots=True` — стандартная комбинация для value-объектов домена. Получается почти `NamedTuple`, но с именованным доступом, валидацией и без случайного сравнения с обычным кортежем.

## 25.4. Валидация: __post_init__ и InitVar

```python
@dataclass(frozen=True, slots=True)
class Operation:
    amount: int
    category: str
    discount: InitVar[int] = 0

    def __post_init__(self, discount: int) -> None:
        if self.amount == 0:
            raise ValueError("Нулевая операция бессмысленна")
        object.__setattr__(self, "amount", self.amount - discount)
```

`__post_init__` вызывается после сгенерированного `__init__`. Для frozen-объектов присваивание делается через `object.__setattr__` — это единственный легальный обход, и применять его стоит только внутри `__post_init__`.

`InitVar` — параметр конструктора, который не становится полем.

> [!TIP] Dataclass валидирует ровно то, что ты напишешь сам. Автоматической проверки типов нет. Если нужна валидация «из коробки» на границе API — это Pydantic (глава 47), а не dataclass.

## 25.5. ClassVar и служебные поля

```python
@dataclass
class Account:
    currency: ClassVar[str] = "RUB"    # не поле экземпляра
    owner: str = ""
    _cache: dict = field(default_factory=dict, repr=False, compare=False)
```

`ClassVar` исключает атрибут из `__init__`, `__repr__` и сравнения. `repr=False, compare=False` — для кэшей и технических полей.

## 25.6. Преобразование и замена

```python
from dataclasses import asdict, astuple, replace

data = asdict(op)             # рекурсивно в словарь
new_op = replace(op, amount=500)   # копия с изменёнными полями
```

`replace` — идиоматичный способ «изменить» frozen-объект.

> [!WARNING] `asdict` делает **глубокую** рекурсивную копию. На больших графах объектов это дорого; в горячем пути сериализуй вручную или используй orjson/pydantic.

## 25.7. NamedTuple и выбор структуры

```python
from typing import NamedTuple


class Rate(NamedTuple):
    code: str
    value: float
    updated: str = ""
```

| Структура | Когда использовать |
|---|---|
| `tuple` | одноразовая распаковка, возврат пары значений |
| `NamedTuple` | лёгкая неизменяемая запись, нужна распаковка и минимум памяти |
| `dataclass(frozen=True)` | value-объект домена с методами и валидацией |
| `dataclass` (обычный) | изменяемая сущность с состоянием |
| `pydantic.BaseModel` | граница системы: парсинг и валидация внешних данных |
| `attrs` | если нужны validators/converters и проект уже на attrs |

> [!NOTE] Ловушка `NamedTuple`: он сравнивается равным обычному кортежу с теми же значениями. Для доменных типов это опасно — `Rate("USD", 90) == ("USD", 90)` будет `True`. Frozen-dataclass такого не допускает.

## 25.8. Enum: перечисления

```python
from enum import Enum, IntEnum, StrEnum, auto, Flag


class Category(StrEnum):        # 3.11+
    FOOD = auto()               # значение 'food'
    TAXI = auto()
    SALARY = auto()


class Status(IntEnum):
    DRAFT = 1
    POSTED = 2


class Permission(Flag):
    READ = auto()
    WRITE = auto()
    ADMIN = READ | WRITE
```

Члены Enum — синглтоны: сравнивай через `is`, итерируй класс, обращайся по значению `Category("food")` и по имени `Category["FOOD"]`. `StrEnum` совместим со строками (удобно в JSON и SQL), `IntEnum` — с int.

> [!TIP] Enum устраняет «магические строки» по всему коду. Опечатка в `Category.FOOD` — ошибка на старте, опечатка в `"foood"` — тихий баг в отчёте.

Для хранения в PostgreSQL есть два подхода: нативный ENUM-тип (быстро, но миграции болезненны) или `VARCHAR` + Enum на стороне Python (гибче). Практика по умолчанию — второй,详见 глава 44.

## 25.9. Контрольные вопросы

1. Почему dataclass запрещает `= []` в качестве дефолта?
2. Что даёт связка `frozen=True, slots=True`?
3. Чем `InitVar` отличается от обычного поля?
4. В чём опасность сравнения `NamedTuple` с кортежем?
5. Когда нужен `StrEnum`, а когда `IntEnum`?

## 25.10. Практика

> [!TASK] Переведи модель сквозного проекта на `@dataclass(frozen=True, slots=True, kw_only=True)`: `Operation`, `Money`, `Account` (изменяемая сущность). Категории — `StrEnum`. Добавь `__post_init__` с валидацией, `replace` для «корректировки» операции, тест на хэшируемость и на невозможность мутации. Замерь память до и после `slots=True`.

---

# Глава 26. ABC, Protocol, SOLID и базовые паттерны

**Цель главы:** научиться проектировать границы между частями системы так, чтобы их можно было менять независимо.

## 26.1. Абстрактные базовые классы

```python
from abc import ABC, abstractmethod


class Storage(ABC):
    @abstractmethod
    def save(self, op: Operation) -> None: ...

    @abstractmethod
    def load_all(self) -> list[Operation]: ...

    def save_many(self, ops: list[Operation]) -> None:   # общий шаблонный метод
        for op in ops:
            self.save(op)
```

Инстанцировать `Storage` нельзя: `TypeError: Can't instantiate abstract class`. Подкласс обязан реализовать все абстрактные методы, иначе тоже останется абстрактным.

ABC задаёт **номинальную** типизацию: чтобы считаться `Storage`, класс должен явно от него наследоваться (или быть зарегистрирован через `Storage.register(cls)` — «виртуальный подкласс»).

## 26.2. Protocol: структурная типизация

```python
from typing import Protocol, runtime_checkable


class RateProvider(Protocol):
    def get_rate(self, code: str) -> float: ...


class CentralBank:                 # НИЧЕГО не наследует
    def get_rate(self, code: str) -> float:
        return 92.5


def convert(provider: RateProvider, code: str) -> float:
    return provider.get_rate(code)
```

`CentralBank` подходит под `RateProvider` автоматически — по факту наличия метода. Это типизированная утиная типизация: контракт описан, но связывания наследованием нет.

`@runtime_checkable` разрешает `isinstance(obj, RateProvider)`, но проверка грубая: только наличие атрибутов, без сигнатур и типов.

## 26.3. ABC или Protocol

| Критерий | ABC | Protocol |
|---|---|---|
| Типизация | номинальная (наследование) | структурная (форма) |
| Общий код | да, методы с реализацией | нет (только сигнатуры) |
| Контроль реализации | в момент создания класса | в момент проверки типов |
| Чужие классы | нужен `register` | подходят сразу |
| Типичное место | внутри своего домена | границы, адаптеры, тестируемость |

> [!NOTE] Практическое правило: **Protocol для портов** (что мне нужно от внешнего мира), **ABC для каркасов** (что я даю наследникам с общей логикой). В главе 44 это станет основой Repository и Unit of Work.

## 26.4. SOLID на живых примерах

### 26.4.1. S — Single Responsibility

Одна причина для изменения. `ReportService`, который считает суммы, читает файл, форматирует PDF и отправляет письмо, имеет четыре причины для правки. Раздели: `Calculator`, `Reader`, `Renderer`, `Notifier`.

### 26.4.2. O — Open/Closed

Открыт для расширения, закрыт для изменения.

```python
# плохо: новый тип операции требует правки функции
def fee(kind: str, amount: int) -> int:
    if kind == "income":
        return 0
    if kind == "expense":
        return amount // 100
    raise ValueError(kind)


# хорошо: добавляем класс, не трогая расчёт
class FeePolicy(Protocol):
    def fee(self, amount: int) -> int: ...

def total_fee(policy: FeePolicy, amounts: list[int]) -> int:
    return sum(policy.fee(a) for a in amounts)
```

### 26.4.3. L — Liskov Substitution

Подкласс должен быть usable везде, где ожидается базовый класс: не сужать допустимые входы, не усиливать предусловия, не бросать неожиданные исключения.

```python
class ReadOnlyStorage(Storage):
    def save(self, op):
        raise NotImplementedError    # НАРУШЕНИЕ LSP
```

Лечение: разделить интерфейсы (`Reader`, `Writer`), а не наследовать «урезанную» версию.

### 26.4.4. I — Interface Segregation

Много узких интерфейсов лучше одного толстого. Класс, которому нужно только чтение, не должен зависеть от интерфейса с записью, удалением и экспортом.

### 26.4.5. D — Dependency Inversion

Модули верхнего уровня не зависят от нижнего; оба зависят от абстракций.

```python
class ReportService:
    def __init__(self, storage: Storage, notifier: Notifier) -> None:
        self._storage = storage       # абстракции, а не PostgresStorage
        self._notifier = notifier

    def build(self) -> str:
        return render(self._storage.load_all())
```

Теперь в тестах подставляется `InMemoryStorage`, в продакшене — `PostgresStorage`, а сам сервис не меняется. Это и есть внедрение зависимостей; в FastAPI оно оформляется через `Depends` (глава 48).

## 26.5. Остальные принципы коротко

- **KISS** — простейшее решение, которое работает.
- **DRY** — одно знание в одном месте (но не путай с случайным совпадением кода: два похожих куска из разных доменов объединять не надо).
- **YAGNI** — не пиши функциональность «на будущее».
- **Law of Demeter** — не ходи по цепочкам `a.b.c.d`; говори с непосредственными соседями.
- **Composition over Inheritance** — см. 23.1.

## 26.6. Базовые паттерны, которые реально используются

### 26.6.1. Strategy

Взаимозаменяемые алгоритмы за одним интерфейсом (см. `FeePolicy` выше). В Python часто достаточно функции или `Callable`.

### 26.6.2. Repository

Абстракция над хранилищем, говорящая на языке домена, а не SQL.

```python
class OperationRepository(Protocol):
    def add(self, op: Operation) -> None: ...
    def get(self, op_id: int) -> Operation | None: ...
    def by_category(self, category: Category) -> list[Operation]: ...
```

### 26.6.3. Unit of Work

Атомарная граница бизнес-операции поверх нескольких репозиториев.

```python
class UnitOfWork(Protocol):
    operations: OperationRepository
    accounts: AccountRepository

    def __enter__(self) -> "UnitOfWork": ...
    def __exit__(self, *exc) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
```

Реализация на SQLAlchemy 2.0 — глава 44; здесь важно понять смысл: **одна бизнес-операция = одна транзакция**.

### 26.6.4. Factory и Adapter

Фабрика инкапсулирует выбор реализации (`storage_for(settings)`), адаптер приводит чужой интерфейс к нашему (`CentralBankAdapter(RateProvider)`).

## 26.7. Антипаттерны

God-объект на 2000 строк; наследование ради переиспользования кода; сервис-локатор вместо явных зависимостей; анемичная модель, где вся логика в «менеджерах», а объекты — просто мешки полей; абстракции «на всякий случай» с единственной реализацией (нарушение YAGNI).

## 26.8. Контрольные вопросы

1. Чем номинальная типизация отличается от структурной?
2. Какое правило SOLID нарушает подкласс, бросающий `NotImplementedError`?
3. Что даёт DIP в тестах?
4. Зачем Unit of Work, если есть Repository?

## 26.9. Практика

> [!TASK] Выдели порты `OperationRepository`, `RateProvider`, `Notifier` как `Protocol`. Реализуй адаптеры `InMemoryRepository`, `JsonFileRepository`, `StubRateProvider`, `ConsoleNotifier`. Собери `ReportService` через конструкторную инъекцию. Напиши тест, подменяющий адаптеры, не меняя ни строки сервиса. Проверь MRO и `isinstance` для `runtime_checkable`-протокола.

# Глава 27. Статическая типизация и mypy

**Цель главы:** ловить ошибки до запуска программы и сделать код самодокументируемым.

## 27.1. Зачем типы, если Python динамический

Аннотации дают три вещи: раннее обнаружение ошибок (mypy находит `None`-разыменования и опечатки в атрибутах), точные подсказки в IDE и живую документацию сигнатур. При этом в рантайме они **не проверяются** — это статический слой поверх динамического языка.

> [!NOTE] Разделяй два разных механизма: **типизация** (mypy, до запуска) и **валидация** (Pydantic, в рантайме на границе системы). Одно не заменяет другое.

## 27.2. Базовый синтаксис

```python
name: str = "Anna"
balance: int = 0
rate: float | None = None          # 3.10+, вместо Optional[float]
tags: list[str] = []
totals: dict[str, int] = {}
pair: tuple[str, int] = ("USD", 90)
rows: tuple[int, ...] = (1, 2, 3)  # переменная длина
```

Встроенные `list`, `dict`, `tuple` используются напрямую (PEP 585) — `typing.List` устарел.

## 27.3. Абстракции в сигнатурах

```python
from collections.abc import Callable, Iterable, Mapping, Sequence


def total(amounts: Iterable[int]) -> int:
    return sum(amounts)


def find(items: Sequence[str], key: str) -> int: ...


def apply(fn: Callable[[int, str], bool], value: int) -> bool: ...
```

Правило: **принимай абстрактное, возвращай конкретное**. Аргумент `Iterable[int]` позволяет передать список, кортеж, генератор; возврат `list[Operation]` даёт вызывающему максимум возможностей.

Частая ошибка — аннотировать параметр как `list`, когда внутри только итерация. Это искусственно сужает API и ломает работу с генераторами.

## 27.4. Полезные конструкции

```python
from typing import Annotated, Final, Literal, NewType, TypedDict

Mode = Literal["income", "expense"]        # только эти значения
MAX_RETRIES: Final = 3                     # нельзя переприсвоить

UserId = NewType("UserId", int)            # отдельный тип, чтобы не путать с OpId


class OperationDict(TypedDict):
    id: int
    amount: int
    category: str
    comment: NotRequired[str]


Amount = Annotated[int, "в копейках"]      # метаданные для фреймворков
```

`TypedDict` описывает форму словаря (JSON-ответ, строка CSV) без создания класса. `NewType` защищает от классической ошибки «передал id операции вместо id счёта». `Annotated` — основа Pydantic `Field` и FastAPI `Depends`.

## 27.5. Дженерики

Современный синтаксис (PEP 695, Python 3.12+):

```python
def first[T](items: Sequence[T]) -> T | None:
    return items[0] if items else None


class Repository[T]:
    def __init__(self) -> None:
        self._items: dict[int, T] = {}

    def add(self, key: int, item: T) -> None:
        self._items[key] = item


type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]
```

Классический вариант (совместим со старыми версиями):

```python
from typing import Generic, TypeVar

T = TypeVar("T")
EntityT = TypeVar("EntityT", bound="Entity")   # ограничение сверху

class Repo(Generic[T]): ...
```

## 27.6. Типизация декораторов: ParamSpec

Без `ParamSpec` декоратор «стирает» сигнатуру функции, и IDE перестаёт подсказывать аргументы.

```python
from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


def timed(func: Callable[P, R]) -> Callable[P, R]:
    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        return func(*args, **kwargs)
    return wrapper
```

Это связывает главы 17 и 27: декоратор теперь не только сохраняет метаданные, но и сохраняет тип.

## 27.7. Сужение типов

```python
from typing import TypeGuard, assert_never, overload


def is_str_list(values: list[object]) -> TypeGuard[list[str]]:
    return all(isinstance(v, str) for v in values)


def parse(value: str | int) -> int:
    if isinstance(value, int):
        return value          # mypy знает: здесь int
    return int(value)         # здесь str
```

`TypeGuard` сообщает анализатору результат пользовательской проверки. `assert_never` в ветке `else` гарантирует, что при добавлении нового варианта `Literal` или Enum mypy укажет на необработанное место — это дешёвая защита от забытых кейсов.

`@overload` описывает несколько сигнатур для одной реализации; `cast` — явное «поверь мне» (используй редко, это дырка в проверке).

## 27.8. Настройка анализатора

```toml
[tool.mypy]
python_version = "3.13"
strict = true
warn_unreachable = true
plugins = ["pydantic.mypy"]

[[tool.mypy.overrides]]
module = ["some_legacy_lib.*"]
ignore_missing_imports = true
```

`strict = true` включает, в частности, `disallow_untyped_defs`, `disallow_any_generics`, `no_implicit_optional`, `warn_return_any`. Альтернатива — **pyright** (быстрее, используется в Pylance, режим `typeCheckingMode: "strict"`).

Точечное подавление — только с кодом правила:

```python
value = legacy_api()  # type: ignore[no-any-return]
```

> [!WARNING] Голый `# type: ignore` и `Any` в сигнатурах превращают строгую типизацию в декорацию. `Any` отключает проверку целых поддеревьев кода. Если тип неизвестен — используй `object` и сужай через `isinstance`.

## 27.9. Стратегия внедрения в существующий проект

1. Включи mypy на новых модулях, старые внеси в overrides.
2. Аннотируй публичные API (сигнатуры функций, поля моделей) — этого достаточно, чтобы анализатор вывел остальное.
3. Постепенно убирай послабления, модуль за модулем.
4. Добавь проверку в pre-commit и CI (главы 28, 55), иначе типы разъедутся за месяц.

## 27.10. Контрольные вопросы

1. Проверяет ли Python аннотации в рантайме?
2. Почему параметр лучше аннотировать `Iterable`, а не `list`?
3. Что даёт `ParamSpec` в декораторе?
4. Чем `NewType` отличается от алиаса?
5. Зачем `assert_never`?

## 27.11. Практика

> [!TASK] Добейся `mypy --strict` без единой ошибки на всём сквозном проекте. Типизируй декораторы из главы 17 через `ParamSpec`, введи `NewType` для `AccountId` и `OperationId`, замени магические строки категорий на `Literal` или Enum и добавь `assert_never` в диспетчер команд.

---

# Глава 28. Стиль кода, Ruff и pre-commit

**Цель главы:** сделать качество кода автоматическим, а не предметом споров на code review.

## 28.1. Стандарты

**PEP 8** — оформление, **PEP 257** — docstrings, **PEP 20** — философия (`import this`). Практический минимум: 4 пробела, длина строки 88 (стандарт Black/Ruff), две пустые строки между определениями верхнего уровня, импорты в начале файла тремя группами (stdlib, сторонние, свои).

> [!NOTE] Споры о стиле — потерянное время команды. Выберите форматтер, включите его в CI и забудьте про форматирование навсегда.

## 28.2. Ruff: линтер и форматтер в одном

Ruff написан на Rust и заменяет Flake8, Black, isort, pyupgrade, часть pylint и bandit, работая в десятки раз быстрее.

```bash
uv add --dev ruff
ruff check .            # найти проблемы
ruff check --fix .      # исправить автоматически
ruff format .           # отформатировать
ruff format --check .   # проверить форматирование (для CI)
```

## 28.3. Конфигурация в pyproject.toml

```toml
[tool.ruff]
line-length = 88
target-version = "py313"
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "SIM", "C4", "RET", "N",
          "PTH", "ASYNC", "DTZ", "T20", "ANN", "S", "RUF"]
ignore = ["ANN401"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101", "ANN"]

[tool.ruff.lint.isort]
known-first-party = ["finance"]
```

Ключевые группы правил:

| Код | Что проверяет |
|---|---|
| `E`, `W`, `F` | базовый стиль и ошибки (pycodestyle, pyflakes) |
| `I` | порядок импортов (isort) |
| `UP` | устаревший синтаксис (pyupgrade) |
| `B` | вероятные баги (bugbear), в т.ч. изменяемые дефолты |
| `SIM`, `C4`, `RET` | упрощение условий, comprehensions, лишние return |
| `N` | имена по PEP 8 |
| `PTH` | `os.path` вместо `pathlib` |
| `ASYNC` | блокирующие вызовы в async-функциях |
| `DTZ` | naive datetime без таймзоны |
| `T20` | забытые `print` |
| `ANN` | отсутствие аннотаций |
| `S` | безопасность (bandit): `assert` в prod, `eval`, слабый хэш |

Точечное подавление — с обоснованием:

```python
password = "test-only"  # noqa: S105 — фикстура, не реальный секрет
```

## 28.4. pre-commit: проверка до коммита

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-merge-conflict
      - id: check-added-large-files
      - id: detect-private-key
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: local
    hooks:
      - id: mypy
        name: mypy
        entry: uv run mypy src
        language: system
        pass_filenames: false
```

```bash
uv add --dev pre-commit
pre-commit install
pre-commit run --all-files
```

> [!NOTE] Хуки — быстрый первый барьер, но не гарантия: их можно обойти через `--no-verify`. Обязательная проверка должна дублироваться в CI (глава 55).

## 28.5. Что автоматизировать нельзя

Ruff не поймёт: плохое имя доменного понятия, неверную границу модуля, дублирование бизнес-знания, отсутствие теста на важный кейс. Это предмет code review. Автоматика снимает механические споры, чтобы люди обсуждали архитектуру.

Полезные метрики для ревью: цикломатическая сложность (`C901` в Ruff, порог 10), длина функции, глубина вложенности, количество аргументов.

## 28.6. Контрольные вопросы

1. Какие инструменты заменяет Ruff?
2. Чем `ruff check` отличается от `ruff format`?
3. Зачем `per-file-ignores` для тестов?
4. Почему pre-commit не заменяет CI?

## 28.7. Практика

> [!TASK] Настрой Ruff с указанным набором правил и добейся нуля замечаний в проекте (осознанно исправляя, а не заглушая). Подключи pre-commit, сделай коммит с намеренно неформатированным кодом и убедись, что хук его отклонил и починил. Добавь правило `T20` и найди все оставшиеся `print` в доменном слое.

---

# Глава 29. Логирование

**Цель главы:** сделать поведение системы наблюдаемым без остановки и отладчика.

## 29.1. Почему не print

`print` не имеет уровней, времени, имени модуля, не пишется в файл, не фильтруется, не структурирован и теряется при перенаправлении вывода в буферизованном контейнере. Логи — это данные для последующего анализа, а не текст для человека в моменте.

## 29.2. Уровни и их смысл

| Уровень | Когда |
|---|---|
| `DEBUG` | детали для разработчика: значения, ветки, SQL |
| `INFO` | нормальные бизнес-события: операция создана, отчёт построен |
| `WARNING` | подозрительно, но обработано: ретрай, дефолт вместо отсутствующих данных |
| `ERROR` | операция не выполнена, требует внимания |
| `CRITICAL` | сервис не может продолжать работу |

> [!TIP] Правило уровня: `ERROR` — это то, что должно разбудить дежурного. Если ошибка ожидаема и обработана (пользователь ввёл неверные данные) — это `INFO` или `WARNING`, а не `ERROR`. Иначе алерты обесцениваются.

## 29.3. Архитектура logging

Четыре сущности: **Logger** (точка входа, иерархия по имени), **Handler** (куда писать), **Formatter** (в каком виде), **Filter** (что пропускать).

```python
import logging

logger = logging.getLogger(__name__)     # всегда так, не root


def transfer(amount: int) -> None:
    logger.info("Перевод начат", extra={"amount": amount})
    try:
        ...
    except InsufficientFunds:
        logger.warning("Недостаточно средств", exc_info=True)
        raise
    except Exception:
        logger.exception("Перевод не удался")   # ERROR + traceback
        raise
```

Иерархия по `__name__` (`finance.reports`) позволяет настраивать уровни по модулям и наследовать обработчики через `propagate`.

> [!WARNING] Никогда не настраивай логирование внутри библиотечного модуля (`basicConfig` при импорте). Конфигурация — прерогатива точки входа приложения. Библиотека только получает логгер и пишет в него.

## 29.4. Форматирование сообщений

```python
logger.info("Операция %s на сумму %s", op_id, amount)   # ленивое
logger.info(f"Операция {op_id} на сумму {amount}")      # строка строится всегда
```

Первый вариант не форматирует строку, если уровень отключён, — это экономит CPU на горячем пути. Плюс системы агрегации логов группируют сообщения по шаблону, а не по подставленным значениям.

## 29.5. Конфигурация через dictConfig

```python
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)-8s %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "plain",
            "filename": "app.log",
            "maxBytes": 10_000_000,
            "backupCount": 5,
            "encoding": "utf-8",
        },
    },
    "loggers": {
        "finance": {"level": "DEBUG", "handlers": ["console", "file"], "propagate": False},
        "sqlalchemy.engine": {"level": "WARNING"},
    },
    "root": {"level": "INFO", "handlers": ["console"]},
}

logging.config.dictConfig(LOGGING)
```

`RotatingFileHandler` не даёт логу съесть диск. В контейнерах пишут в stdout, а ротацию и сбор обеспечивает платформа (главы 54, 61). Для неблокирующей записи в горячем пути — `QueueHandler` + `QueueListener`.

## 29.6. Структурированные логи

Текстовые логи плохо ищутся. Промышленный стандарт — JSON с фиксированными полями.

```python
import structlog

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.dict_tracebacks,
        structlog.processors.JSONRenderer(ensure_ascii=False),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
)

log = structlog.get_logger()
log.info("operation_created", operation_id=42, amount=1500, category="food")
```

Такое событие Loki или ELK разберёт на поля, и ты сможешь строить запросы «все операции дороже 100 000 за последний час» вместо grep по подстроке.

## 29.7. Корреляция запросов

```python
import contextvars
import uuid

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")

# на входе в запрос (middleware, глава 48)
request_id_var.set(str(uuid.uuid4()))
structlog.contextvars.bind_contextvars(request_id=request_id_var.get())
```

Один `request_id` (и позже `trace_id` OpenTelemetry) во всех записях, включая фоновые задачи и вызовы соседних сервисов, — это то, что превращает набор логов в историю одного запроса. `contextvars` корректно изолирует значение для каждой асинхронной задачи.

## 29.8. Что нельзя логировать

Пароли, токены, полные номера карт, CVV, паспортные данные, содержимое приватных документов. Персональные данные — только в объёме, необходимом для задачи, и с маскированием.

```python
log.info("login", email=mask_email(email), token=token[:6] + "***")
```

> [!WARNING] `logger.exception` внутри обработчика ошибки аутентификации может утащить в лог тело запроса с паролем. Настрой процессор-фильтр, вырезающий чувствительные ключи, а не надейся на внимательность каждого разработчика.

## 29.9. Контрольные вопросы

1. Почему логгер называют по `__name__`?
2. Чем `logger.exception` отличается от `logger.error`?
3. Зачем ленивое форматирование через `%s`?
4. Как связать записи одного запроса в разных модулях?

## 29.10. Практика

> [!TASK] Убери все `print` из сквозного проекта, замени на `structlog` с JSON-выводом. Добавь `request_id` через `contextvars`, привяжи его к каждой записи, настрой уровни по модулям и маскирование чувствительных полей. Проверь, что доменные функции по-прежнему ничего не печатают сами, а события пишутся на границах.

---

# Глава 30. Тестирование с pytest

**Цель главы:** научиться доказывать корректность кода автоматически и делать это быстро.

## 30.1. Что и зачем тестировать

Пирамида: много быстрых unit-тестов (домен, чистые функции), меньше интеграционных (БД, HTTP, файловая система), совсем немного end-to-end. Тестируй **поведение и контракты**, а не приватные детали реализации — иначе тесты придётся переписывать при каждом рефакторинге.

Ценность теста — в уверенности при изменении кода. Тест, который ломается от переименования внутренней переменной, но не ловит реальный баг, — отрицательная ценность.

## 30.2. Первый тест

```python
# tests/test_money.py
from finance.money import Money


def test_add_returns_sum():
    # Arrange
    a, b = Money(100), Money(250)
    # Act
    result = a + b
    # Assert
    assert result == Money(350)
```

Правила обнаружения: файлы `test_*.py`, функции `test_*`, классы `Test*` без `__init__`. Запуск: `uv run pytest -q`.

pytest переписывает `assert` (assert introspection), поэтому при падении ты видишь конкретные значения, а не просто `AssertionError`.

## 30.3. Параметризация и маркеры

```python
import pytest


@pytest.mark.parametrize(
    ("amount", "expected"),
    [(100, "1.00 ₽"), (0, "0.00 ₽"), (-50, "-0.50 ₽")],
    ids=["positive", "zero", "negative"],
)
def test_str(amount, expected):
    assert str(Money(amount)) == expected


@pytest.mark.skip(reason="ждёт реализации")
def test_future(): ...


@pytest.mark.xfail(reason="известный баг #123", strict=True)
def test_known_bug(): ...


@pytest.mark.slow
def test_heavy(): ...
```

```bash
pytest -k "money and not slow"
pytest -m "not slow"
pytest -x --lf          # остановиться на первом падении / только упавшие ранее
```

## 30.4. Фикстуры

```python
# tests/conftest.py
import pytest


@pytest.fixture
def account():
    return Account("Anna", balance=1000)


@pytest.fixture
def storage(tmp_path):          # yield-фикстура: setup + teardown
    repo = JsonFileRepository(tmp_path / "ops.json")
    yield repo
    repo.close()


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"
```

Области видимости: `function` (по умолчанию), `class`, `module`, `package`, `session`. Фикстуры из `conftest.py` доступны всем тестам каталога и ниже, импортировать их не нужно.

> [!WARNING] `scope="session"` для изменяемого объекта означает общее состояние между тестами — источник «плавающих» падений и зависимости от порядка запуска. Широкий scope — только для дорогих неизменяемых ресурсов.

Приём «фикстура-фабрика» вместо фикстуры-объекта:

```python
@pytest.fixture
def make_operation():
    def _make(amount: int = 100, **kw):
        return Operation(amount=amount, **kw)
    return _make
```

## 30.5. Встроенные фикстуры

```python
def test_env(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setattr("finance.config.DEFAULT_RATE", 90.0)


def test_output(capsys):
    cli.main()
    assert "Итого" in capsys.readouterr().out


def test_log(caplog):
    with caplog.at_level(logging.WARNING):
        do_something()
    assert "Недостаточно средств" in caplog.text


def test_file(tmp_path):
    p = tmp_path / "ops.json"
    p.write_text("[]", encoding="utf-8")
```

`tmp_path` создаёт изолированный временный каталог на каждый тест — никаких файлов в рабочей директории.

## 30.6. Мокирование

```python
from unittest.mock import AsyncMock, MagicMock, patch


def test_service_uses_storage():
    storage = MagicMock(spec=OperationRepository)
    storage.load_all.return_value = [Operation(amount=100)]
    service = ReportService(storage)

    assert service.build_total() == 100
    storage.load_all.assert_called_once()


def test_external_api():
    with patch("finance.rates.httpx.get") as get:      # патчим там, где ИСПОЛЬЗУЕТСЯ
        get.return_value.json.return_value = {"rate": 92.5}
        assert fetch_rate("USD") == 92.5


async def test_async_client():
    client = AsyncMock()
    client.get.return_value.json.return_value = {"rate": 92.5}
```

> [!NOTE] Главное правило `patch`: подменяй имя **в том модуле, где его используют**, а не где определили. `from httpx import get` в вашем модуле создаёт новую привязку — патчить надо `finance.rates.get`.

`spec=` (или `autospec=True`) заставляет мок соблюдать интерфейс: обращение к несуществующему методу упадёт, а не создаст новый мок. Без spec мок скрывает опечатки и переименования.

> [!TIP] Если для теста нужно пять моков — это сигнал, что тестируемый объект имеет слишком много зависимостей. Лучшее решение — не больше моков, а инъекция простых адаптеров (глава 26) и in-memory реализации.

## 30.7. Асинхронные тесты

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-q --strict-markers"
```

```python
async def test_fetch_rates():
    result = await fetch_all_rates(["USD", "EUR"])
    assert len(result) == 2
```

`pytest-asyncio` в режиме `auto` сам оборачивает async-тесты. Альтернатива — `anyio` с параметризацией бэкенда. Для тестирования отмены и таймаутов понадобятся `asyncio.timeout` и `TaskGroup` (глава 37).

## 30.8. Исключения, числа, время

```python
def test_raises():
    with pytest.raises(InsufficientFunds, match="Недостаточно средств"):
        account.withdraw(10**9)


def test_float():
    assert 0.1 + 0.2 == pytest.approx(0.3)


def test_time(time_machine):        # плагин time-machine
    time_machine.move_to("2026-11-24T10:00:00Z")
    assert today_report_date() == "2026-11-24"
```

Никогда не пиши тесты, зависящие от реального `datetime.now()` или `random` без фиксации seed: они зелёные сегодня и красные в CI завтра.

## 30.9. Покрытие

```bash
uv run pytest --cov=src --cov-branch --cov-report=term-missing
```

```toml
[tool.coverage.report]
fail_under = 85
show_missing = true
exclude_lines = ["if TYPE_CHECKING:", "raise NotImplementedError"]
```

> [!WARNING] 100% покрытия не означает отсутствие багов: строка может быть выполнена без проверки результата. Смотри на покрытие ветвей (`--cov-branch`) и на качество ассертов. Покрытие — индикатор непокрытых мест, а не цель сама по себе.

## 30.10. Генерация данных и property-based тесты

```python
from polyfactory.factories.dataclass_factory import DataclassFactory


class OperationFactory(DataclassFactory[Operation]):
    __model__ = Operation


def test_random_operations():
    ops = OperationFactory.batch(50)
    assert total(ops) == sum(o.amount for o in ops)
```

`polyfactory`/`faker` избавляют от ручного заполнения десятков полей. `hypothesis` идёт дальше — генерирует входные данные и ищет контрпример:

```python
from hypothesis import given, strategies as st


@given(st.integers(), st.integers())
def test_add_commutative(a, b):
    assert Money(a) + Money(b) == Money(b) + Money(a)
```

Это проверка **свойств** (коммутативность, идемпотентность, инвариант «сумма частей равна целому»), а не отдельных примеров. Для финансовых расчётов — незаменимо.

## 30.11. Контрольные вопросы

1. Что такое AAA и зачем разделять фазы?
2. Чем опасен `scope="session"` для изменяемой фикстуры?
3. Где нужно патчить имя при `patch`?
4. Зачем `spec` у мока?
5. Почему 100% покрытие не гарантирует корректность?

## 30.12. Практика

> [!TASK] Покрой домен сквозного проекта тестами: параметризованные тесты `Money`, фикстуры `account`/`storage`, `tmp_path` для JSON-репозитория, мок `RateProvider`, тест на доменное исключение, hypothesis-тест на «сумма частей равна целому» для `split_bill`. Добейся `--cov-branch` не ниже 90% на `src/finance` и включи `fail_under` в конфиг.

---

# Глава 31. Отладка и профилирование

**Цель главы:** находить причину проблемы за минуты вместо часов и оптимизировать по измерениям, а не по интуиции.

## 31.1. Научный метод отладки

1. Воспроизвести (минимальный пример).
2. Сформулировать гипотезу («падает, потому что `rate` равен `None`»).
3. Проверить одним экспериментом (точка останова, лог, тест).
4. Исправить причину, а не симптом.
5. Написать тест, который падал бы до исправления.

> [!TIP] Шаг 5 обязателен. Баг без регрессионного теста вернётся — обычно через два месяца и в продакшене.

## 31.2. breakpoint() и pdb

```python
def calculate(op):
    breakpoint()          # встроенная точка входа в отладчик (PEP 553)
    return op.amount * rate
```

Основные команды: `n` (следующая строка), `s` (войти в вызов), `c` (продолжить), `l` (листинг), `p expr` (напечатать), `pp` (красиво), `w` (стек), `u`/`d` (вверх/вниз по стеку), `b 42` (точка останова), `q` (выход).

Запуск post-mortem — отладка уже упавшего кода:

```bash
python -m pdb -c continue script.py     # остановится в месте исключения
```

> [!NOTE] `breakpoint()` можно глобально отключить переменной `PYTHONBREAKPOINT=0` — удобно, чтобы случайно забытая точка не сломала CI. Ruff (правило `T10`) находит забытые `breakpoint()` автоматически.

## 31.3. Сложные traceback

Читай снизу вверх (глава 5), обращай внимание на цепочки `__cause__`/`__context__` (глава 19) и на `ExceptionGroup` из `TaskGroup` (глава 37). Для зависших процессов:

```python
import faulthandler
faulthandler.enable()                     # traceback по SIGSEGV
faulthandler.dump_traceback_later(30)     # дамп всех потоков через 30 секунд
```

## 31.4. Инструмент под задачу

| Симптом | Инструмент |
|---|---|
| Неверный результат, воспроизводится локально | отладчик, тест |
| Ошибка в продакшене | структурированные логи + trace_id |
| «Иногда падает» | тест с фиксацией времени/seed, hypothesis |
| Медленно | профилировщик CPU |
| Растёт память | tracemalloc, memray |
| Зависло | py-spy dump, faulthandler |
| Медленные запросы к БД | EXPLAIN ANALYZE (глава 43) |

## 31.5. Профилирование CPU

### 31.5.1. Микробенчмарки: timeit

```python
from timeit import timeit

timeit("sum(range(1000))", number=10_000)
```

Для сравнения двух вариантов写法 — только `timeit`, а не один замер `time.perf_counter()` в нагруженной системе.

### 31.5.2. cProfile: где именно уходит время

```bash
python -m cProfile -o profile.out -m finance.cli report
python -c "import pstats; pstats.Stats('profile.out').sort_stats('cumtime').print_stats(25)"
```

Смотри на `cumtime` (суммарно с вызовами) для поиска узкого места и на `tottime` (без вложенных) для поиска дорогой функции. Визуализация — `snakeviz profile.out`.

> [!WARNING] cProfile добавляет заметный оверхед и искажает картину на I/O-нагрузке. Для продакшена используй сэмплирующий профилировщик.

### 31.5.3. py-spy: профилирование живого процесса

```bash
py-spy top --pid 12345                 #实时-таблица горячих функций
py-spy record -o flame.svg --pid 12345 # флеймграф
py-spy dump --pid 12345                # стеки всех потоков: почему висит
```

py-spy читает память процесса извне, не требует изменения кода и почти не влияет на производительность — это основной инструмент диагностики на сервере (подробнее в главе 60).

## 31.6. Память

```python
import tracemalloc

tracemalloc.start()
snap1 = tracemalloc.take_snapshot()
run_workload()
snap2 = tracemalloc.take_snapshot()
for stat in snap2.compare_to(snap1, "lineno")[:10]:
    print(stat)
```

Типичные причины роста памяти: неограниченный кэш (`lru_cache` без maxsize), глобальные коллекции, забытые подписчики и колбэки, замыкания, удерживающие большие объекты, циклы с `__del__`, накопление логов в памяти.

Инструменты: `sys.getsizeof` (поверхностный размер одного объекта), `tracemalloc` (кто аллоцировал), **memray** (`memray run script.py`, `memray flamegraph`) — детальный профиль аллокаций, включая C-расширения.

> [!NOTE] В контейнере нехватка памяти выглядит как `OOMKilled` без traceback (глава 62). Поэтому лимиты памяти и профиль потребления нужно знать заранее, а не в момент инцидента.

## 31.7. Порядок оптимизации

1. **Измерь** и найди узкое место (профилировщик, EXPLAIN).
2. **Смени алгоритм или структуру данных**: список → словарь/множество, O(n²) → O(n). Это даёт порядки выигрыша.
3. **Убери лишнюю работу**: N+1 запросы, повторные вычисления, лишние копии данных (`asdict`, `deepcopy`).
4. **Кэшируй** (`lru_cache`, Redis) с продуманной инвалидацией.
5. **Параллель** (главы 36–38) или вынесение в воркеры (глава 57).
6. Только потом — микрооптимизации: `__slots__`, локальные переменные, генераторы вместо списков, orjson вместо json.

> [!WARNING] Преждевременная оптимизация делает код сложнее и не решает реальную проблему. В типичном backend 90% времени уходит на ожидание БД и сети, а не на Python-код.

## 31.8. Контрольные вопросы

1. Чем `cumtime` отличается от `tottime`?
2. Почему py-spy подходит для продакшена, а cProfile — нет?
3. Как найти источник роста памяти?
4. Какой шаг оптимизации даёт наибольший эффект?

## 31.9. Практика

> [!TASK] Создай в проекте намеренно медленную функцию агрегации: поиск категории линейным перебором в списке на 100 000 операций. Профилируй cProfile, найди горячую функцию, замени на словарь-индекс, замерь ускорение через `timeit`. Затем сними `tracemalloc`-сравнение для варианта со списком и с генератором и оформи выводы таблицей «до/после» в README проекта.

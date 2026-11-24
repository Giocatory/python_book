# Глава 52. Git изнутри и командная работа

**Цель главы:** перестать бояться Git: понимать модель объектов, уметь отменять любое действие и работать в команде без «испорченной истории».

## 52.1. Модель объектов

Git — не «система диффов», а **хранилище объектов, адресуемых по содержимому**. В каталоге `.git/objects` лежат четыре типа:

- **blob** — содержимое файла (без имени);
- **tree** — снимок каталога: список имён, режимов и ссылок на blob/tree;
- **commit** — ссылка на корневой tree, ссылки на родителей, автор, коммиттер, сообщение;
- **tag** — аннотированная метка на объект.

Хэш каждого объекта — SHA-1 (или SHA-256 в новых репозиториях) от его содержимого. Одинаковое содержимое хранится один раз.

```bash
git cat-file -p HEAD          # увидеть объект коммита
git cat-file -p HEAD^{tree}   # увидеть снимок каталога
git rev-parse HEAD
```

**Ветка — это файл с 40-символьным хэшем**, указатель на коммит. **HEAD** — указатель на текущую ветку (или на коммит при detached HEAD). Отсюда лёгкость веток и вся модель слияния.

> [!NOTE] Коммит неизменяем. `--amend`, `rebase`, `reset` не «правят» коммит — они создают новые объекты и двигают указатели. Старые объекты остаются в репозитории, пока их не соберёт gc. Именно поэтому почти всё можно вернуть.

## 52.2. Три области и индекс

**Working tree** (файлы) → **Index / staging** (подготовленный снимок) → **Repository** (коммиты).

```bash
git status
git diff                  # working tree против index
git diff --staged         # index против последнего коммита
git add -p                # интерактивно, по кускам (hunks)
git restore --staged file # убрать из индекса, сохранив правки
```

`git add -p` — важнейшая привычка: он позволяет собрать один осмысленный коммит из файла, где смешаны рефакторинг и фича.

## 52.3. Базовый цикл

```bash
git init / git clone URL
git switch -c feat/idempotency
git add -p && git commit -m "feat(operations): add Idempotency-Key support"
git log --oneline --graph --all --decorate
git push -u origin feat/idempotency
```

Коммит должен быть **атомарным**: одно логическое изменение, проект после него собирается и тесты проходят. Это условие работы `bisect` и `revert`.

## 52.4. Отмена изменений

| Задача | Команда |
|---|---|
| Откатить правки файла | `git restore file` |
| Поправить последний коммит | `git commit --amend` |
| Отменить коммит, оставив правки в индексе | `git reset --soft HEAD~1` |
| Отменить коммит, оставив правки в файлах | `git reset --mixed HEAD~1` (по умолчанию) |
| Отменить коммит и правки | `git reset --hard HEAD~1` |
| Отменить публичный коммит безопасно | `git revert HASH` |
| Найти «потерянные» коммиты | `git reflog` |

> [!WARNING] `reset --hard` уничтожает незакоммиченные правки безвозвратно (в отличие от коммитов, которые спасает reflog). Перед ним — `git stash` или коммит.

`reflog` — журнал перемещений HEAD за ~90 дней. Спасает после неудачного rebase или reset: находишь хэш и делаешь `git reset --hard <hash>`.

## 52.5. Слияние и конфликты

```bash
git switch main && git pull
git switch feat/x && git merge main
```

**Fast-forward** возможен, если история линейна: указатель просто переезжает вперёд. **Three-way merge** создаёт коммит слияния, сравнивая две вершины и их общего предка.

Конфликт — это не ошибка, а место, где Git не смог решить сам. Маркеры `<<<<<<<`, `=======`, `>>>>>>>` показывают обе версии; после правки — `git add` и `git commit`. Полезно: `git merge --abort`, `git config rerere.enabled true` (запоминание решений).

## 52.6. rebase и золотое правило

`rebase` переносит коммиты на новое основание, **пересоздавая** их (новые хэши). Даёт линейную читаемую историю.

```bash
git rebase main
git rebase -i HEAD~5      # squash, fixup, reword, drop, edit
git push --force-with-lease
```

> [!WARNING] **Золотое правило: не делай rebase публичных веток.** Переписанная история ломает работу всех, кто уже от неё ответвился. Исключение — своя ветка в PR, где ты один, и то с `--force-with-lease` (он откажется пушить, если кто-то успел добавить коммиты).

Интерактивный rebase — способ привести ветку к виду «3 осмысленных коммита» вместо «27 коммитов с сообщениями wip». `fixup` + `git commit --fixup=HASH` + `rebase -i --autosquash` автоматизируют это.

## 52.7. Инструменты спасения и поиска

```bash
git stash push -m "wip" && git stash pop
git cherry-pick HASH             # перенести один коммит в другую ветку
git tag -a v1.2.0 -m "release"
git bisect start && git bisect bad && git bisect good v1.1.0
git bisect run uv run pytest tests/test_transfer.py
git worktree add ../hotfix hotfix/urgent
```

`bisect` — бинарный поиск коммита, сломавшего поведение: на 1000 коммитов нужно ~10 шагов. С `run` он полностью автоматичен. `worktree` даёт второй рабочий каталог того же репозитория — удобно для срочного хотфикса без stash.

## 52.8. Что не попадает в репозиторий

`.gitignore`: `.venv/`, `__pycache__/`, `.env`, `*.log`, `.coverage`, `.mypy_cache/`, `.ruff_cache/`, артефакты сборки. Коммитятся: `pyproject.toml`, `uv.lock`, `.env.example`, `.python-version`, миграции.

> [!WARNING] Секрет, попавший в историю, считается скомпрометированным навсегда: его находят за минуты по публичным репозиториям. Удаление файла в новом коммите не помогает — нужна ротация ключа, а чистка истории (`git filter-repo`, BFG) вторична.

Ставь pre-commit-хук `detect-private-key` (глава 28) и сканирование секретов в CI (глава 55). Большие бинарники — в Git LFS или объектное хранилище.

## 52.9. Командный workflow

**GitHub Flow:** короткоживущие ветки от `main`, PR, ревью, CI, merge, деплой. Просто и подходит большинству продуктовых команд.
**Trunk-Based Development:** все коммитят в trunk минимум раз в день, незаконченное прячется за фиче-флагами; требует зрелого CI и тестов, зато даёт настоящую непрерывную интеграцию.

**Conventional Commits:** `feat:`, `fix:`, `refactor:`, `perf:`, `docs:`, `test:`, `chore:`, `ci:`, `build:`; `BREAKING CHANGE:` в футере. Даёт автоматическую генерацию changelog и семантического версиирования.

Этикет ревью: PR до 400 строк, описание «зачем», а не «что»; ревьюер komentирует код, а не человека; различай «блокер», «предложение» и «вкусовщину» (последнее должен решать форматтер, глава 28).

## 52.10. Контрольные вопросы

1. Что хранится в объекте commit?
2. Чем `reset --soft` отличается от `--hard` и от `revert`?
3. Почему rebase публичной ветки опасен?
4. Как найти коммит, сломавший тест, за 10 шагов?
5. Что делать, если секрет уже в истории?

## 52.11. Практика

> [!TASK] В сквозном проекте: собери фичу из 5 «грязных» коммитов и приведи к 2 осмысленным через `rebase -i --autosquash`; смоделируй конфликт и реши его; «потеряй» коммит через `reset --hard` и восстанови через reflog; найди внесённый баг через `bisect run`; настрой Conventional Commits и `.gitignore`.

---

# Глава 53. Linux, деплой и reverse proxy

**Цель главы:** уверенно чувствовать себя на сервере: найти процесс, прочитать логи, настроить службу и выставить сервис в интернет безопасно.

## 53.1. FHS: где что лежит

| Каталог | Назначение |
|---|---|
| `/etc` | конфигурация системы и служб |
| `/var` | изменяемые данные; `/var/log` — логи |
| `/usr` | установленные программы и библиотеки |
| `/opt` | сторонние приложения (сюда кладём свой сервис) |
| `/srv` | данные, обслуживаемые системой |
| `/tmp` | временные файлы, очищается |
| `/proc`, `/sys` | виртуальные ФС ядра и процессов |
| `/dev` | устройства |
| `/run` | runtime-состояние (PID-файлы, сокеты) |

Жёсткая ссылка (`ln`) — второе имя того же inode, работает только внутри ФС. Символическая (`ln -s`) — файл-указатель на путь, может пересекать ФС и «висеть» при удалении цели.

## 53.2. Пользователи и права

Модель `rwx` для трёх категорий: владелец, группа, остальные. `chmod 755` = `rwxr-xr-x`, `644` = `rw-r--r--`. Для каталога бит `x` означает право **входить** в него, а не «исполнять».

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin appuser
sudo chown -R appuser:appuser /opt/finance
chmod 600 /etc/finance/env
umask                 # обычно 022: новые файлы 644, каталоги 755
```

> [!NOTE] Сервис никогда не работает от root. Отдельный системный пользователь без shell, минимальные права на файлы, секреты — `600` и владелец `appuser`. Это ограничивает ущерб при RCE.

## 53.3. Процессы, сигналы, диагностика

```bash
ps aux | grep uvicorn
top / htop
free -h
df -h && du -sh /var/log/*
lsof -i :8000        # кто занял порт
ss -tulpn
```

Сигналы: **SIGTERM (15)** — вежливая просьба завершиться (обрабатывается приложением), **SIGKILL (9)** — немедленное убийство ядром (обработать нельзя), **SIGHUP (1)** — перечитать конфигурацию, **SIGINT (2)** — Ctrl+C.

> [!WARNING] Graceful shutdown означает: получить SIGTERM → перестать принимать новые запросы → дождаться текущих → закрыть пулы БД и HTTP → выйти. Если приложение игнорирует SIGTERM, оркестратор убьёт его по таймауту, оборвав транзакции (главы 37, 62).

## 53.4. systemd: сервис как служба

```ini
# /etc/systemd/system/finance.service
[Unit]
Description=Finance API
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=exec
User=appuser
Group=appuser
WorkingDirectory=/opt/finance
EnvironmentFile=/etc/finance/env
ExecStart=/opt/finance/.venv/bin/uvicorn finance.api.main:app --host 127.0.0.1 --port 8000 --workers 4
Restart=on-failure
RestartSec=3
KillSignal=SIGTERM
TimeoutStopSec=30
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/var/log/finance

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now finance
systemctl status finance
journalctl -u finance -f --since "10 min ago"
```

systemd даёт автозапуск, перезапуск при падении, единый сбор логов и изоляцию. `TimeoutStopSec` должен быть больше времени graceful shutdown приложения.

## 53.5. SSH и доставка файлов

```bash
ssh-keygen -t ed25519 -C "deploy@finance"
ssh-copy-id deploy@server
```

```
# ~/.ssh/config
Host finance-prod
    HostName 203.0.113.10
    User deploy
    IdentityFile ~/.ssh/id_ed25519
    ServerAliveInterval 30
```

```bash
rsync -avz --delete --exclude '.venv' ./src/ finance-prod:/opt/finance/src/
scp file.tar.gz finance-prod:/tmp/
```

Отключи вход по паролю и root-логин в `sshd_config`, поставь fail2ban. Ключ деплоя — отдельный, с ограниченными правами.

## 53.6. Диагностика инцидента в терминале

```bash
journalctl -u finance --since "5 min ago" | grep ERROR | wc -l
tail -f /var/log/nginx/access.log | jq -R 'split(" ")[8]' | sort | uniq -c | sort -rn
rg "InsufficientFunds" /var/log/finance/ -n
awk '{print $9}' access.log | sort | uniq -c | sort -rn | head
```

Потоки: stdin (0), stdout (1), stderr (2); `>` перезапись, `>>` дозапись, `2>&1` слияние ошибок с выводом, `|` конвейер. `jq` разбирает JSON-логи (глава 29) прямо в терминале.

## 53.7. Nginx как reverse proxy

```nginx
upstream finance_api { server 127.0.0.1:8000; keepalive 32; }

limit_req_zone $binary_remote_addr zone=api:10m rate=20r/s;

server {
    listen 443 ssl;
    http2 on;
    server_name api.example.com;

    ssl_certificate     /etc/letsencrypt/live/api.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.example.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    add_header Strict-Transport-Security "max-age=31536000" always;

    client_max_body_size 20m;
    client_body_timeout 10s;
    client_header_timeout 10s;
    keepalive_timeout 15s;

    location /static/ { alias /opt/finance/static/; expires 30d; }

    location / {
        limit_req zone=api burst=40 nodelay;
        proxy_pass http://finance_api;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }
}
```

Задачи прокси: терминация TLS, раздача статики, балансировка, буферизация медленных клиентов, лимиты, сжатие. Альтернативы с автоматическим TLS — **Caddy** и **Traefik**.

> [!WARNING] Приложение за прокси должно знать реальный протокол и IP, иначе будут неверные редиректы и неработающие лимиты. Uvicorn запускай с `--proxy-headers --forwarded-allow-ips="127.0.0.1"` и доверяй заголовкам **только** от своего прокси.

Короткие `client_body_timeout` / `client_header_timeout` и `limit_req` — базовая защита от **Slowloris** (атака медленными заголовками, удерживающими соединения).

## 53.8. Стратегии выката

- **Rolling:** постепенная замена инстансов; требует совместимости N-1 (глава 45).
- **Blue-Green:** два окружения, переключение трафика мгновенно, откат = вернуть трафик обратно.
- **Canary:** 1–5% трафика на новую версию, наблюдение за метриками, затем полное развёртывание.

Порядок всегда: миграции (совместимые со старым кодом) → выкатка → проверка health и метрик → снятие старого. Откат кода без отката миграций возможен только при Expand-Contract.

## 53.9. Контрольные вопросы

1. Чем hard link отличается от symlink?
2. Что означает `x` для каталога?
3. Чем SIGTERM отличается от SIGKILL?
4. Зачем Nginx передаёт X-Forwarded-Proto?
5. Как защититься от Slowloris?

## 53.10. Практика

> [!TASK] Разверни сквозной проект на ВМ: системный пользователь, systemd-unit с hardening, Nginx с TLS от Let's Encrypt и лимитами, логи в journald, `rsync`-доставка. Проверь graceful shutdown: во время длинного запроса выполни `systemctl restart finance` и убедись, что запрос завершился корректно.

---

# Глава 54. Docker и контейнеризация

**Цель главы:** собирать образы, которые малы, безопасны, кэшируются при сборке и корректно завершаются в оркестраторе.

## 54.1. Что такое контейнер

Контейнер — процесс (или группа процессов) на хостовом ядре, изолированный **namespaces** (pid, net, mnt, uts, ipc, user) и ограниченный **cgroups** (CPU, память, I/O). Файловая система — слои **overlayfs**: образ состоит из read-only слоёв, контейнер добавляет один записываемый.

Отсюда: контейнер не виртуальная машина (нет своего ядра), стартует за миллисекунды, а его файловая система **эфемерна** — всё важное выносится в тома и внешние хранилища.

## 54.2. Правильный Dockerfile для Python-сервиса

```dockerfile
# ---------- builder ----------
FROM python:3.13-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY README.md ./
RUN uv sync --frozen --no-dev

# ---------- runtime ----------
FROM python:3.13-slim-bookworm AS runtime

RUN groupadd --system app && useradd --system --gid app --create-home appuser
WORKDIR /app
COPY --from=builder --chown=appuser:app /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status==200 else 1)"

CMD ["uvicorn", "finance.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Ключевые решения: multi-stage (компиляторы и кэши не попадают в финальный образ), slim вместо alpine, non-root, `PYTHONUNBUFFERED` для логов в stdout, exec-форма `CMD`.

> [!NOTE] Alpine использует musl вместо glibc: manylinux-колёса не подходят, пакеты собираются из исходников — сборка медленнее, а образ иногда больше. Для Python почти всегда правильный выбор — `slim`.

## 54.3. Порядок слоёв и кэш сборки

Docker кэширует слои: изменившийся слой инвалидирует **все последующие**. Поэтому порядок: сначала то, что меняется редко (метаданные зависимостей), потом то, что меняется часто (код).

```dockerfile
COPY pyproject.toml uv.lock ./      # меняется редко → uv sync кэшируется
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src                      # меняется каждый коммит
RUN uv sync --frozen --no-dev       # ставим только сам проект
```

Плюс `.dockerignore`: `.venv`, `.git`, `__pycache__`, `tests`, `.env`, артефакты. Без него в контекст улетают сотни мегабайт и секреты.

## 54.4. PID 1, сигналы и завершение

```dockerfile
CMD uvicorn app:app --host 0.0.0.0        # ПЛОХО: shell-форма
CMD ["uvicorn", "app:app", "--host", "0.0.0.0"]   # ХОРОШО: exec-форма
```

Shell-форма запускает `/bin/sh -c "..."`, и PID 1 становится shell, который **не передаёт** SIGTERM дочернему процессу. Контейнер игнорирует `docker stop` и убивается через 10 секунд по SIGKILL — посреди транзакции.

Если процесс не умеет reap зомби или нужно несколько процессов — ставь init: `ENTRYPOINT ["/usr/bin/tini", "--"]`. И помни: **один сервис — один процесс в контейнере**; воркеры и планировщик — отдельные контейнеры.

## 54.5. Секреты и переменные

`ENV` — конфигурация времени выполнения, `ARG` — только время сборки. Neither должно содержать секретов: значения видны в `docker inspect` и истории слоёв.

```dockerfile
RUN --mount=type=secret,id=pip_token \
    UV_INDEX_TOKEN=$(cat /run/secrets/pip_token) uv sync --frozen
```

BuildKit secret-mount не сохраняется в слоях. В рантайме секреты приходят через переменные окружения оркестратора, Docker secrets или vault (главы 21, 62).

## 54.6. docker compose для локальной среды

```yaml
services:
  db:
    image: postgres:17
    environment:
      POSTGRES_PASSWORD: dev
      POSTGRES_DB: finance
    volumes: [pgdata:/var/lib/postgresql/data]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 3s
      retries: 10

  redis:
    image: redis:7
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      retries: 10

  api:
    build: .
    env_file: .env
    ports: ["8000:8000"]
    depends_on:
      db: {condition: service_healthy}
      redis: {condition: service_healthy}
    stop_grace_period: 30s

  worker:
    build: .
    command: ["taskiq", "worker", "finance.tasks:broker"]
    env_file: .env
    depends_on:
      db: {condition: service_healthy}

volumes:
  pgdata:
```

> [!WARNING] `depends_on` без `condition: service_healthy` ждёт только **запуска** контейнера, а не готовности сервиса. PostgreSQL стартует несколько секунд — приложение упадёт на первом подключении. Healthcheck обязателен.

Compose — инструмент разработки и небольших ВМ-деплоев, не оркестратор: нет автоматического пересчёта реплик, rolling update и self-healing на нескольких узлах (это глава 62).

## 54.7. Безопасность и размер образа

Non-root пользователь, `read_only: true` с `tmpfs` для `/tmp`, `cap_drop: [ALL]`, отсутствие компиляторов и curl в финальном образе, пиннинг базового образа по digest, сканирование `trivy image`, минимальный набор зависимостей (`--no-dev`).

```bash
docker scout cves finance-api:latest
trivy image --severity HIGH,CRITICAL finance-api:1.4.2
docker image history finance-api:1.4.2      # найти «толстые» слои
```

## 54.8. Отладка и эксплуатация

```bash
docker logs -f --tail 100 api
docker exec -it api python -c "import sys; print(sys.executable)"
docker inspect api | jq '.[0].State'
docker stats
docker compose up -d --build
```

Теги: `1.4.2` + `git-sha` для деплоя, `latest` — только для локальной разработки. Деплой по `latest` невоспроизводим и не позволяет понять, что именно работает.

## 54.9. Контрольные вопросы

1. Чем контейнер отличается от ВМ?
2. Почему зависимости копируются раньше кода?
3. Что ломает shell-форма CMD?
4. Зачем `condition: service_healthy`?
5. Почему alpine часто хуже slim для Python?

## 54.10. Практика

> [!TASK] Собери multi-stage образ сквозного проекта: размер до и после multi-stage, время сборки при изменении только кода (должно быть секунды), запуск от non-root, healthcheck, `docker compose up` с PostgreSQL и Redis. Проверь graceful shutdown: `docker stop` во время запроса — он должен завершиться, а не оборваться.

---

# Глава 55. CI/CD: автоматизация проверок и выкатки

**Цель главы:** сделать так, чтобы ни один непроверенный код не попадал в продакшен, а деплой был скучной операцией в одну кнопку.

## 55.1. Термины

**Continuous Integration** — каждое изменение сливается в trunk и автоматически проверяется. **Continuous Delivery** — артефакт всегда готов к выкатке, но решение принимает человек. **Continuous Deployment** — выкатка происходит автоматически после зелёного пайплайна.

Пайплайн описывается кодом в репозитории (pipeline as code) и проходит ревью, как любой код.

## 55.2. Стадии и их порядок

Быстрое и дешёвое — раньше: `lint → format check → type check → unit-тесты → интеграционные тесты → сборка образа → сканирование → публикация → деплой`. Ошибка стиля не должна тратить 10 минут на подъём базы.

## 55.3. GitHub Actions: рабочий пайплайн

```yaml
name: ci
on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true
      - run: uv sync --frozen
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run mypy src

  tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:17
        env:
          POSTGRES_PASSWORD: test
          POSTGRES_DB: finance_test
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready --health-interval 5s
          --health-timeout 3s --health-retries 10
      redis:
        image: redis:7
        ports: ["6379:6379"]
        options: >-
          --health-cmd "redis-cli ping" --health-interval 5s --health-retries 10
    env:
      DATABASE_URL: postgresql+asyncpg://postgres:test@localhost:5432/finance_test
      REDIS_URL: redis://localhost:6379/0
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with: {enable-cache: true}
      - run: uv sync --frozen
      - run: uv run alembic upgrade head
      - run: uv run alembic heads | wc -l | grep -qx 1   # ровно один head
      - run: uv run pytest --cov=src --cov-branch --cov-report=xml
      - uses: actions/upload-artifact@v4
        with: {name: coverage, path: coverage.xml}
```

`permissions: contents: read` — минимальные права токена. `concurrency` отменяет устаревшие прогоны при новом пуше. `services` поднимает реальные PostgreSQL и Redis — тесты идут на том же движке, что и продакшен (глава 44).

## 55.4. Скорость пайплайна

Кэшируй uv/pip по ключу от `uv.lock`, разделяй независимые job'ы (они идут параллельно), не гоняй интеграционные тесты на каждый коммит в черновом PR, используй `--lf` локально. Ориентир: полный CI до 10 минут, иначе разработчики начинают его обходить.

> [!WARNING] Flaky-тест — не «повезёт в следующий раз», а дефект инфраструктуры. Немедленно чинить или карантинить с задачей: иначе команда привыкает перезапускать CI и перестаёт верить красному.

## 55.5. Сборка и публикация образа

```yaml
  build:
    needs: [quality, tests]
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: |
            ghcr.io/${{ github.repository }}:${{ github.sha }}
            ghcr.io/${{ github.repository }}:latest
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

Тег по `git sha` — основа воспроизводимого деплоя и отката. Кэш BuildKit из GHA ускоряет сборку в разы.

## 55.6. Деплой

Простой вариант (ВМ + compose): job по SSH делает `docker compose pull && docker compose up -d --no-deps api worker`, затем проверяет `/health` и метрики; при провале — возврат к предыдущему тегу.

Продвинутый вариант: обновление образа в Kubernetes-манифесте или Helm-values, `kubectl rollout status`, автоматический откат при провале readiness (глава 62).

Правила: миграции применяются отдельным шагом **до** выкатки и совместимы со старым кодом; деплой защищён environment protection и ручным подтверждением для продакшена; секреты — только в secrets хранилища CI, никогда в логах.

## 55.7. Ворота качества и безопасность

Обязательные проверки перед merge: CI зелёный, ревью, покрытие не ниже порога, отсутствие конфликтов. Дополнительно: `pip-audit` (уязвимости зависимостей), `trivy` (образ), сканирование секретов, CodeQL/SAST, Renovate или Dependabot для регулярного обновления зависимостей.

SBOM и provenance (аттестации сборки) — практика supply chain security, всё чаще требуемая в enterprise.

## 55.8. GitLab CI: то же самое другими словами

```yaml
stages: [quality, tests, build, deploy]
variables:
  UV_CACHE_DIR: .uv-cache
cache:
  key: {files: [uv.lock]}
  paths: [.uv-cache]
tests:
  stage: tests
  services: [postgres:17, redis:7]
  script:
    - uv sync --frozen
    - uv run alembic upgrade head
    - uv run pytest --cov=src
```

Концепции идентичны: stages, jobs, services, cache, artifacts, environments, rules. Знание одной системы переносится на другую за час.

## 55.9. Контрольные вопросы

1. Чем Continuous Delivery отличается от Continuous Deployment?
2. Почему lint идёт раньше интеграционных тестов?
3. Зачем тег по git sha, если есть latest?
4. Как проверить «ровно один head» Alembic в CI?
5. Что делать с flaky-тестом?

## 55.10. Практика

> [!TASK] Собери полный пайплайн сквозного проекта: quality (ruff + mypy), tests (PostgreSQL и Redis в services, миграции, coverage-порог, проверка одного head), build (multi-stage с кэшем, тег sha, пуш в GHCR), deploy (SSH + compose, health-проверка, автоматический откат). Добавь `pip-audit` и `trivy`, настрой Renovate.

---

# Глава 56. Redis и кэширование

**Цель главы:** ускорить чтение и разгрузить БД, не создав новых отказов и не потеряв согласованность.

## 56.1. Что такое Redis и Valkey

In-memory хранилище структур данных с однопоточной обработкой команд (что и даёт атомарность каждой операции) и опциональной персистентностью: **RDB** (снимки) и **AOF** (журнал команд). Valkey — открытый форк Redis после смены лицензии, протокол-совместимый.

Ключевые настройки: `maxmemory` и `maxmemory-policy` (`allkeys-lru`, `allkeys-lfu`, `volatile-ttl`, `noeviction`). Для кэша — LRU/LFU, для очередей и локов — `noeviction` (иначе Redis начнёт выкидывать нужные ключи).

> [!WARNING] Redis — не система записи для критичных данных. Деньги, счета и проводки живут в PostgreSQL. Redis — кэш, счётчики, локи, сессии, лимиты, очереди.

## 56.2. Структуры данных и их применение

| Структура | Применение |
|---|---|
| String | кэш JSON, счётчики (`INCR`), локи (`SET NX PX`) |
| Hash | объект с полями, частичное обновление |
| List | простые очереди, последние N событий |
| Set | уникальные множества, теги |
| Sorted Set (ZSET) | лидерборды, скользящие окна, отложенные задачи |
| Streams | журнал событий с consumer groups |
| Pub/Sub | fire-and-forget уведомления (без гарантий) |

```python
await redis.set("rate:USD", "92.5", ex=300)
await redis.hset("user:42", mapping={"role": "admin", "tz": "Europe/Moscow"})
await redis.zadd("leaderboard", {"anna": 1500})
await redis.incr("ops:count:2026-11-24")
```

Именование ключей: `finance:v1:account:42:balance`. Версия в префиксе позволяет «сбросить» весь кэш разом, поменяв `v1` на `v2`.

## 56.3. Клиент и атомарность

```python
from redis.asyncio import Redis

redis = Redis.from_url(settings.redis_url, decode_responses=True, max_connections=50)

async with redis.pipeline(transaction=False) as pipe:   # батчинг: один round-trip
    pipe.get("a"); pipe.get("b")
    values = await pipe.execute()
```

`MULTI/EXEC` даёт транзакцию команд, `WATCH` — оптимистичную проверку. Для составных операций с условиями нужен **Lua-скрипт**: он исполняется атомарно, без гонок между чтением и записью.

> [!WARNING] `KEYS pattern` блокирует весь Redis на время обхода — в продакшене только `SCAN` с курсором. Одна медленная команда останавливает всех клиентов, потому что цикл однопоточный.

## 56.4. Cache-Aside и альтернативы

```python
async def get_balance(account_id: int) -> int:
    key = f"finance:v1:account:{account_id}:balance"
    if (cached := await redis.get(key)) is not None:
        return int(cached)
    value = await repo.compute_balance(account_id)
    await redis.set(key, value, ex=60 + random.randint(0, 15))   # TTL с jitter
    return value
```

| Стратегия | Суть | Цена |
|---|---|---|
| Cache-Aside | приложение читает кэш, при промахе — БД и заполняет | возможен устаревший reads, гонки |
| Write-Through | запись в кэш и БД синхронно | латентность записи выше |
| Write-Behind | запись в кэш, сброс в БД асинхронно | риск потери данных |
| Refresh-Ahead | обновление до истечения TTL | сложнее, нужен фоновый процесс |

Инвалидация: по TTL (просто, но окно устаревания), по событию (точнее, но нужна доставка), версионированием ключа (дёшево и надёжно).

> [!NOTE] Для финансовых данных кэшируй **производные и справочные** величины (курсы, отчёты, категории), а не баланс, участвующий в списании. Баланс для операции всегда читается из БД под блокировкой (глава 43).

## 56.5. Три классические проблемы кэша

**Cache Stampede (Thundering Herd):** горячий ключ протух, тысячи запросов одновременно идут в БД. Решения: мьютекс на пересчёт (`SET key:lock token NX PX 5000`, остальные ждут или отдают stale), probabilistic early expiration (обновлять чуть раньше TTL с вероятностью, растущей к концу), stale-while-revalidate.

**Cache Penetration:** запросы к заведомо несуществующим ключам всегда доходят до БД. Решения: кэшировать пустой результат с коротким TTL, фильтр Блума, валидация ID на границе.

**Cache Avalanche:** множество ключей истекает одновременно (или Redis упал). Решения: jitter в TTL, многоуровневый кэш (локальный in-process + Redis), circuit breaker и деградация к БД с лимитом конкурентности.

```python
# мьютекс против stampede
token = str(uuid4())
if await redis.set(f"{key}:lock", token, nx=True, px=5000):
    try:
        value = await recompute()
        await redis.set(key, value, ex=300)
    finally:
        await release_lock(f"{key}:lock", token)
else:
    await asyncio.sleep(0.05)
    return await get_from_cache_or_stale(key)
```

## 56.6. Распределённый лок

```python
RELEASE = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
else
  return 0
end
"""

async def release_lock(key: str, token: str) -> None:
    await redis.eval(RELEASE, 1, key, token)
```

Захват — `SET key token NX PX <ttl>`, освобождение — только если токен совпал (иначе снимешь чужой лок). TTL обязателен: иначе упавший владелец заблокирует ресурс навсегда.

> [!WARNING] Лок в Redis не даёт строгой гарантии взаимного исключения при паузах процесса и failover: владелец может «проспать» TTL и продолжить работу. Для критичных инвариантов используй блокировки PostgreSQL или fencing-токены (монотонный номер, отвергаемый хранилищем при устаревании). Алгоритм Redlock обсуждаем и не решает проблему пауз.

## 56.7. Rate limiter на скользящем окне

```lua
-- KEYS[1]=ключ, ARGV[1]=now_ms, ARGV[2]=window_ms, ARGV[3]=limit, ARGV[4]=uuid
redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, ARGV[1] - ARGV[2])
local count = redis.call('ZCARD', KEYS[1])
if count >= tonumber(ARGV[3]) then return 0 end
redis.call('ZADD', KEYS[1], ARGV[1], ARGV[4])
redis.call('PEXPIRE', KEYS[1], ARGV[2])
return 1
```

ZSET хранит метки времени запросов; скрипт атомарно чистит окно, считает и добавляет. Работает корректно при любом числе воркеров и реплик — в отличие от счётчика в памяти процесса (глава 50).

## 56.8. Что ещё живёт в Redis

Состояние refresh-токенов и reuse detection (глава 49), blacklist `jti` с TTL, ключи идемпотентности «в процессе», сессии, прогресс长 задач для SSE, лидерборды и счётчики. Всё это — данные, потеря которых допустима или восстанавливаема.

## 56.9. Эксплуатация

Мониторь: `used_memory` против `maxmemory`, hit rate (`keyspace_hits/misses`), `evicted_keys`, latency, число соединений, время последней持久изации. Отказ Redis не должен ронять сервис: оберни вызовы таймаутом и предусмотри деградацию к БД с лимитом конкурентности.

HA: Sentinel (автоматический failover) или Cluster (шардирование по слотам). Для большинства проектов достаточно одного инстанса с Sentinel и грамотной деградацией.

## 56.10. Контрольные вопросы

1. Почему Redis атомарен на уровне команды?
2. Чем stampede отличается от penetration?
3. Зачем jitter в TTL?
4. Почему лок нужно освобождать по токену через Lua?
5. Когда `maxmemory-policy noeviction` обязателен?

## 56.11. Практика

> [!TASK] Внедри в сквозной проект: Cache-Aside для курсов и отчётов с jitter и мьютексом против stampede, кэш пустого результата, sliding-window rate limiter на Lua, распределённый лок для генерации отчёта с fencing-проверкой. Замерь p95 до и после кэша под нагрузкой и проверь поведение при остановленном Redis.

---

# Глава 57. Очереди, брокеры и надёжная доставка

**Цель главы:** вынести долгие и ненадёжные операции из HTTP-запроса и гарантировать, что событие не потеряется и не обработается дважды.

## 57.1. Зачем очереди

Три причины: **развязка** (API не ждёт генерацию отчёта), **сглаживание пиков** (нагрузка копится в очереди, воркеры разбирают в своём темпе), **повторяемость** (упавшая задача будет перезапущена).

Гарантии доставки: **at-most-once** (может потеряться), **at-least-once** (может продублироваться), **exactly-once** (в распределённых системах практически недостижимо端到-end).

> [!NOTE] Промышленный стандарт: **at-least-once + идемпотентный обработчик**. Дедупликация по ключу события на стороне консьюмера даёт эффект «ровно один раз» без магии брокера.

## 57.2. Воркеры задач в Python

| Инструмент | Особенность | Когда |
|---|---|---|
| **Taskiq** | нативно async, DI в стиле FastAPI, брокеры Redis/RabbitMQ/NATS | новый async-проект |
| **ARQ** | минималистичный, только Redis | простые фоновые задачи |
| **Celery** | зрелая экосистема, beat, chords, но воркер синхронный | legacy и сложные workflow |
| **Dramatiq / Huey** | лёгкие альтернативы | небольшие проекты |
| **PostgreSQL + SKIP LOCKED** | без нового компонента | умеренные нагрузки (глава 43) |

> [!WARNING] Celery-воркер синхронный. Вызов async-кода через `asyncio.run()` в каждой задаче создаёт новый event loop — а значит, пул SQLAlchemy, привязанный к другому loop, сломается. Создавай engine внутри задачи/процесса или используй нативно асинхронный Taskiq.

```python
from taskiq import TaskiqDepends
from finance.tasks.broker import broker


@broker.task(retry_on_error=True, max_retries=5)
async def build_report(account_id: int, period: str) -> None:
    async with SqlAlchemyUnitOfWork(session_factory) as uow:
        ...
```

## 57.3. Retry, идемпотентность, DLQ

Экспоненциальная задержка с jitter: `delay = min(base * 2**attempt, cap) * random(0.5, 1.0)`. Обязательны `max_retries` и общий дедлайн; после исчерпания — **Dead Letter Queue** для ручного разбора.

Идемпотентность задачи: ключ (`report:42:2026-11`), проверка «уже выполнено» в БД или Redis, уникальное ограничение на результат. Задача должна быть безопасна при повторном запуске после таймаута, когда предыдущий запуск на самом деле успел закоммититься.

Различай **retryable** ошибки (сеть, 503, deadlock) и **non-retryable** (валидация, отсутствие прав): вторые сразу в DLQ, ретраить их бессмысленно.

## 57.4. RabbitMQ: умный брокер

Модель: продюсер → **exchange** → (binding по routing key) → **queue** → консьюмер.

Типы exchange: `direct` (точное совпадение ключа), `fanout` (всем очередям), `topic` (шаблоны `finance.*.created`), `headers`.

Надёжность складывается из четырёх вещей: **durable queue** + **persistent messages** + **publisher confirms** + **manual ack** консьюмера. Без любого звена сообщение может потеряться.

```python
import aio_pika

connection = await aio_pika.connect_robust(settings.amqp_url)
channel = await connection.channel(publisher_confirms=True)
await channel.set_qos(prefetch_count=10)          # не более 10 неподтверждённых на воркера

queue = await channel.declare_queue(
    "reports", durable=True,
    arguments={"x-dead-letter-exchange": "reports.dlx"},
)
await channel.declare_exchange("reports.dlx", aio_pika.ExchangeType.FANOUT)

async with queue.iterator() as it:
    async for message in it:
        try:
            await handle(message.body)
        except RetryableError:
            await message.nack(requeue=False)     # уйдёт в DLQ
        else:
            await message.ack()
```

`prefetch_count` — критичный параметр честного распределения: без него один воркер заберёт всю очередь и будет обрабатывать её в одиночку.

## 57.5. Kafka: распределённый лог

Kafka не «очередь», а **лог событий**: сообщения хранятся в топиках, разбитых на **партиции**, и не удаляются при чтении. Консьюмер хранит **offset** — позицию чтения. Отсюда возможность перечитать историю.

- Порядок гарантируется **внутри партиции**; ключ сообщения определяет партицию (все события одного счёта — в одну партицию).
- **Consumer group** распределяет партиции между инстансами; число активных консьюмеров не может превышать число партиций.
- Retention по времени/размеру; **log compaction** хранит последнее значение по ключу.
- Идемпотентный продюсер (`enable.idempotence=true`) убирает дубли при ретраях; транзакции дают атомарность записи в несколько партиций.
- **Consumer lag** — главная метрика здоровья: сколько сообщений ещё не прочитано.

## 57.6. RabbitMQ или Kafka

| Критерий | RabbitMQ | Kafka |
|---|---|---|
| Модель | маршрутизация и очереди | лог событий |
| Повторное чтение истории | нет | да |
| Пропускная способность | десятки тысяч сообщений/с | сотни тысяч и выше |
| Сложная маршрутизация | да (topic, headers) | нет (только партиции) |
| Приоритеты, TTL, DLQ | из коробки | вручную |
| Типичный сценарий | фоновые задачи, RPC, workflow | события, аналитика, event sourcing, CDC |

Практика: для «сгенерировать отчёт и отправить письмо» — RabbitMQ или Taskiq+Redis. Для потока доменных событий, аналитики и интеграции множества потребителей — Kafka.

## 57.7. Transactional Outbox

Проблема: закоммитил транзакцию в БД, а потом упал до публикации события — данные есть, события нет. Или наоборот: событие ушло, транзакция откатилась. Распределённая транзакция (2PC) между БД и брокером дорога и хрупка.

Решение: писать событие **в ту же транзакцию**, в таблицу `outbox`, а публикацию поручить отдельному процессу.

```sql
CREATE TABLE outbox (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    aggregate_id bigint NOT NULL,
    event_type text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz
);
CREATE INDEX outbox_unpublished_idx ON outbox (id) WHERE published_at IS NULL;
```

```python
async with uow:
    uow.accounts.apply_transfer(...)
    uow.outbox.add(Event("transfer.completed", payload))
    await uow.commit()          # атомарно: и данные, и событие
```

Релей читает `SELECT ... FOR UPDATE SKIP LOCKED`, публикует с подтверждением и помечает `published_at`. Гарантия — **at-least-once**, поэтому консьюмер дедуплицирует по `event_id` (паттерн **Inbox**: таблица обработанных идентификаторов с уникальным индексом).

Альтернатива поллингу — CDC (Debezium читает WAL и публикует изменения), меньше нагрузки на БД, но больше инфраструктуры.

## 57.8. Смежная инфраструктура

**Объектное хранилище (S3/MinIO):** файлы не через API, а по **presigned URL** — клиент грузит напрямую в хранилище, API только выдаёт подписанную ссылку и потом валидирует результат (глава 50). Это снимает трафик и память с приложения.

**Поиск:** PostgreSQL FTS покрывает умеренные задачи; при сложных требованиях — Elasticsearch/OpenSearch (полнотекст, агрегации) или Meilisearch/Typesense (быстрый поиск «как в интернете» из коробки). Индексация — через события из outbox.

## 57.9. Наблюдаемость очередей

Метрики, без которых очередь — чёрный ящик: глубина очереди, **возраст самого старого сообщения** (лучший индикатор отставания), consumer lag, доля ошибок и ретраев, размер DLQ. Алерт на DLQ > 0 и на возраст выше SLA обязателен.

## 57.10. Контрольные вопросы

1. Почему exactly-once недостижим и что делают вместо?
2. Из каких четырёх элементов складывается надёжность RabbitMQ?
3. Что даёт ключ партиции в Kafka?
4. Какую проблему решает Outbox?
5. Зачем консьюмеру Inbox?

## 57.11. Практика

> [!TASK] Вынеси генерацию отчётов и уведомления в Taskiq с RabbitMQ: durable-очередь, publisher confirms, manual ack, prefetch, DLQ, ретраи с jitter, идемпотентность по ключу задачи. Реализуй Transactional Outbox для события `transfer.completed` с релеем на `SKIP LOCKED` и Inbox-дедупликацией на консьюмере. Добавь метрики глубины очереди и возраста старейшего сообщения, алерт на DLQ.

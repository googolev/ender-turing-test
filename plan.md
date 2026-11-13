# План: ролевой доступ (Admin / Manager / Member)

Задание описано в [task.md](task.md). Этапы идут по порядку, каждый заканчивается состоянием, которое можно проверить, и отдельным коммитом в ветке `feature/roles`.

## Принципы, общие для всех этапов

- **Рабочая БД `app` неприкосновенна.** Тесты работают с отдельной `app_test`, тест миграции поднимает собственную временную БД и удаляет её, ручная проверка миграции идёт на копии `app`. Изменять `app` разрешено только двумя способами: ручными проверками через API, у каждой из которых есть явная команда отката, и применением миграции после бэкапа.
- **Восстановление — только из бэкапа** (`pg_dump`/`pg_restore`), а не повторным запуском сида.
- **Стек работает в режиме `docker compose watch`.** Он синхронизирует изменения `./backend` в контейнер и пересобирает frontend.
- **Тесты backend запускаются в разовом контейнере с примонтированным `./backend`**, а не через `docker compose exec`. Тестов нет внутри образа (`Dockerfile` копирует только `app/` и `scripts/`). `watch` синхронизирует только изменённые файлы, начальной синхронизации нет, а `initial_sync` наш Compose 2.39.1 не поддерживает. Поэтому документированный `docker compose exec backend bash scripts/tests-start.sh` видит неполный `tests/`. venv лежит в `/app/.venv` и монтированием не перекрывается.
- **Нельзя запускать корневые `scripts/test.sh` и `scripts/test-local.sh` в основном compose-проекте.** Они делают `docker compose down -v` и удаляют том с БД `app`.
- **Нельзя делать `docker compose down` при работающем `watch`.** Контейнеры удалятся у него из-под ног. Для временной остановки — `docker compose stop` / `docker compose start`: контейнеры остаются, и `watch` продолжает в них синхронизировать.

## Общие команды (Git Bash, из корня репозитория)

Запуск стека (в отдельном терминале, остаётся висеть):

```bash
docker compose watch
```

Тесты backend (работают с `app_test`, `app` не трогают):

```bash
MSYS_NO_PATHCONV=1 docker compose run --rm -v ./backend:/app/backend backend bash scripts/tests-start.sh
```

Помощники для ручных проверок. Вставить один раз в терминал:

```bash
export MSYS_NO_PATHCONV=1   # иначе Git Bash превращает пути контейнера вроде /tmp/app.dump в пути Windows
B=http://localhost:8000/api/v1
tok()  { curl -s -X POST "$B/login/access-token" -d "username=$1&password=$2" | python -c "import sys,json;print(json.load(sys.stdin).get('access_token',''))"; }
code() { curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $1" "${@:2}"; }
send() { curl -s -o /dev/null -w "%{http_code}\n" -X "$2" -H "Authorization: Bearer $1" -H 'Content-Type: application/json' ${4:+-d "$4"} "$3"; }
show() { curl -s -H "Authorization: Bearer $1" "${@:2}"; echo; }
uid()  { show "$(tok admin@example.com changethis)" "$B/users/?limit=500" | python -c "import sys,json;print(next(u['id'] for u in json.load(sys.stdin)['data'] if u['email']=='$1'))"; }
Q()    { docker compose exec -T db psql -U postgres -d "${2:-app}" -c "$1"; }
```

- `code TOKEN URL` печатает HTTP-код GET-запроса.
- `send TOKEN METHOD URL [JSON]` печатает HTTP-код запроса с телом.
- `show TOKEN URL` печатает ответ.
- `Q "SQL" [db]` выполняет SQL, по умолчанию в `app`.

Контрольный снимок `app`. Его нужно сравнивать до и после любых тестов:

```bash
Q 'select (select count(*) from "user") as users, (select count(*) from item) as items'
```

---

## Этап 0. Отдельные БД для тестов и бэкап

**Зачем.** Сейчас `tests/conftest.py` в конце сессии удаляет все `User` и `Item` из той БД, на которую указывает `DATABASE_URL`, то есть из `app`. Пока это не исправлено, тесты запускать нельзя.

**Что меняется**

- `backend/tests/prepare_db.py`:
  - берёт `settings.DATABASE_URL`, заменяет имя БД на `<имя>_test`;
  - создаёт эту БД, если её нет, подключаясь к служебной `postgres`;
  - накатывает на неё `alembic upgrade head`, запуская alembic отдельным процессом с подменённым `DATABASE_URL`;
  - печатает итоговый URL.
- `backend/scripts/test.sh`: перед `pytest` выполняет `DATABASE_URL="$(python -m tests.prepare_db)"` и экспортирует его. На время этой строки `set -x` отключён, чтобы URL с паролем не попал в лог. Команды запуска тестов (`scripts/tests-start.sh`, `scripts/test.sh`, CI `test-backend.yml`) остаются прежними.
- `backend/tests/conftest.py`: первым делом session-фикстура `db` проверяет `engine.url.database` — ту самую БД, которую она потом очищает. Если имя не заканчивается на `_test`, прогон останавливается через `pytest.exit` (код 2) с сообщением, как запускать правильно. Так прямой вызов `pytest` мимо скрипта не сможет стереть `app`.
- e2e (Playwright) пишет в БД через работающий backend, поэтому для него поднимается отдельный compose-проект `ender-e2e` со своим томом. Файлы для этого не меняются, только команды (см. ниже).
- Бэкап `app` хранится вне репозитория, в `../ender-backups/`.

**Что нужно заранее:** стек запущен.

**Как проверить**

1. Бэкап и проверка, что из него можно восстановиться. Восстанавливаем в отдельную БД, а не поверх `app`:

   ```bash
   mkdir -p ../ender-backups
   docker compose exec -T db pg_dump -U postgres -Fc -f /tmp/app.dump app
   docker compose cp db:/tmp/app.dump ../ender-backups/app-before-roles.dump
   docker compose exec -T db createdb -U postgres app_restore_check
   docker compose exec -T db pg_restore -U postgres -d app_restore_check /tmp/app.dump
   Q 'select count(*) from "user"' app_restore_check
   docker compose exec -T db dropdb -U postgres app_restore_check
   ```

   Ожидаемый результат: в `app_restore_check` столько же пользователей, сколько в контрольном снимке `app`.

2. Тесты не трогают `app`:

   ```bash
   Q 'select (select count(*) from "user") as users, (select count(*) from item) as items'
   docker compose run --rm -v ./backend:/app/backend backend bash scripts/tests-start.sh
   Q 'select (select count(*) from "user") as users, (select count(*) from item) as items'
   Q "select datname from pg_database where datname like 'app%'" postgres
   ```

   Ожидаемый результат: `58 passed`, снимок `app` совпадает до и после, в списке баз есть `app` и `app_test`. Повторный запуск тоже зелёный: `app_test` уже существует.

3. Защита от прямого запуска:

   ```bash
   docker compose run --rm -v ./backend:/app/backend backend python -m pytest tests/
   ```

   Ожидаемый результат: `Exit: Refusing to run: tests delete all users and items, but DATABASE_URL points to 'app'…`, код выхода 2, снимок `app` не изменился.

4. e2e в отдельном проекте. Основной стек нужно остановить: порты общие.

   ```bash
   docker compose stop
   docker compose -p ender-e2e build
   docker compose -p ender-e2e run --rm backend bash scripts/prestart.sh
   docker compose -p ender-e2e up -d
   docker compose -p ender-e2e run --rm playwright bunx playwright test
   docker compose -p ender-e2e down -v
   docker compose start
   ```

   Ожидаемый результат: e2e зелёные. `down -v` удаляет только том `ender-e2e_app-db-data`. После `start` снимок `app` прежний, `watch` продолжает работать.

**Тесты:** существующие тесты backend и e2e, теперь в изолированных БД.

---

## Этап 1. Коды 401/403 и обработка 4xx на frontend

**Сейчас (проверено на живом стеке):**

| Ситуация | Сейчас | Frontend сейчас |
|---|---|---|
| невалидный токен | `403 Could not validate credentials` | выход |
| нет токена | `401 Not authenticated` | выход |
| токен деактивированного пользователя | `400 Inactive user` | **не выходит**, экран без данных |
| токен удалённого пользователя | `404 User not found` | **не выходит** |
| не хватает прав | `403` | **выход** (после введения ролей это станет ошибкой) |

**Что меняется**

- Backend, `get_current_user` в [deps.py](backend/app/api/deps.py):
  - невалидный токен, удалённый пользователь и неактивный пользователь получают **401** с заголовком `WWW-Authenticate: Bearer`;
  - нехватка прав остаётся **403**;
  - `POST /login/access-token` (неверный пароль, неактивный пользователь) остаётся **400**. Это ошибка формы, а не сессии. Если сделать там 401, глобальный обработчик перезагрузит страницу логина и тост пропадёт.
- Frontend, `handleApiError` в [main.tsx](frontend/src/main.tsx):
  - **401** → удалить токен и перейти на `/login`;
  - **403** → не выходить. Перезапросить `currentUser` и вызвать `router.invalidate()`, чтобы guards маршрутов отработали по свежей роли. Пользователь с пониженной ролью уйдёт на `/`, лишние пункты меню исчезнут;
  - **400/404/409/422** в мутациях → как сейчас, тост с `detail` через `handleError`. В запросах глобально ничего не делаем.

**Что нужно заранее:** этап 0.

**Как проверить через API** (каждая проверка откатывает свои изменения):

```bash
ADMIN=$(tok admin@example.com changethis); MEMBER=$(tok alice@example.com password123); ALICE=$(uid alice@example.com)
code garbage $B/users/me                                   # 401 (было 403)
code $MEMBER $B/users/                                     # 403
send $ADMIN PATCH $B/users/$ALICE '{"is_active":false}'    # 200
code $MEMBER $B/users/me                                   # 401 (было 400): старый токен перестал работать сразу
curl -s -o /dev/null -w "%{http_code}\n" -X POST $B/login/access-token -d 'username=alice@example.com&password=password123'   # 400
send $ADMIN PATCH $B/users/$ALICE '{"is_active":true}'     # 200, откат
code $MEMBER $B/users/me                                   # 200
```

**Как проверить в интерфейсе** (обычное окно и окно инкогнито, у них разный `localStorage`):

1. В обычном окне войти как `alice@example.com`, открыть Items.
2. В инкогнито войти как `admin@example.com` и на странице Admin деактивировать Alice.
3. В окне Alice перейти на Dashboard. Ожидаемый результат: выход на `/login`. Сейчас она остаётся на странице без данных.
4. На `/login` ввести неверный пароль. Ожидаемый результат: тост «Incorrect email or password», страница не перезагружается.
5. Откат: в инкогнито снова активировать Alice.

Реакцию на 403 в интерфейсе на этом этапе вызвать нечем, она проверяется на этапе 4.

**Тесты:**
- `backend/tests/api/test_deps.py`:
  - мусорный и просроченный токен → 401 с `WWW-Authenticate: Bearer`;
  - токен удалённого пользователя → 401;
  - токен пользователя, деактивированного после входа → 401, после повторной активации тот же токен → 200;
  - логин неактивного пользователя → 400.

  На старом коде 4 из 5 падали (403, 403, 404, 400), логин уже давал 400.
- e2e `login.spec.ts`, «Deactivated user with an open session is sent to /login». На старом backend падал: пользователь оставался на странице. Тест проверяет связку backend 401 → выход; frontend и раньше выходил на 401, поэтому новую ветку 403 он не покрывает, она проверяется на этапе 4.
- Существующие тесты эти коды не проверяли, править их не пришлось. Существующий e2e «Redirects to /login when token is wrong» подтверждает, что замена 403 на 401 не сломала выход по невалидному токену.

---

## Этап 2. Поле `role` и миграция, поведение не меняется

**Что меняется**

- Модели:
  - enum `UserRole` (`admin | manager | member`) и колонка `user.role` с `NOT NULL`;
  - `is_superuser` удаляется;
  - `role` есть в `UserCreate`, `UserUpdate` и `UserPublic`;
  - в `UserRegister` и `UserUpdateMe` поля `role` **нет**.
- Миграция `91ade4d27122`, одна транзакция:
  - upgrade: добавить `role VARCHAR(20) NOT NULL` с `server_default 'member'` → `CHECK ck_user_role` → `UPDATE "user" SET role='admin' WHERE is_superuser` → удалить `is_superuser`;
  - downgrade: вернуть `is_superuser = (role = 'admin')`, убрать server default (как в исходной колонке), удалить `ck_user_role` и `role`. Роль manager при откате превращается в обычного пользователя, это описано в docstring миграции.
  - Роль хранится как `VARCHAR` + `CHECK`, не нативный Postgres `ENUM`: такую колонку проще менять, откат не требует `DROP TYPE`. В модели это `sa.Enum(native_enum=False, create_constraint=True)`; `alembic check` подтверждает, что модель и схема совпадают.
- Все проверки `is_superuser` в backend и frontend механически меняются на `role == admin`. Admin полностью наследует права бывшего суперюзера, manager пока ведёт себя как member. Тексты ошибок («Super users are not allowed…») и переменная `FIRST_SUPERUSER` не меняются.
- **`UserCreate` и `UserUpdate` запрещают лишние поля (`extra="forbid"`), ответ 422.** Иначе старый клиент, отправивший `{"is_superuser": false}`, получил бы 200, а админ остался бы админом; то же с опечаткой вроде `is_activ`. Запрос с лишним полем не применяется даже частично. `/users/me` и `/signup` не затронуты. Конфиг задан через `SQLModelConfig` из `sqlmodel._compat`: аргумент класса `extra="forbid"` SQLModel молча игнорирует (проверено), а `ConfigDict` не проходит mypy/ty.
- Frontend:
  - клиент перегенерируется. На хосте нет bun и uv: `openapi.json` берётся из backend-контейнера (`FASTAPI_ENV=development`, чтобы попал private API), `openapi-ts` запускается в образе playwright с примонтированным `./frontend/src` (монтировать сам `src/client` нельзя: генератор удаляет каталог вывода целиком);
  - чекбокс «Is superuser?» в `AddUser`/`EditUser` заменяется на общий компонент `RoleSelect`, бейдж в таблице показывает роль;
  - `AddUser` больше не отправляет `confirm_password`: с запретом лишних полей создание пользователя из админки иначе получало бы 422.
- `init_db` создаёт `FIRST_SUPERUSER` с ролью admin.
- `seed_data.py` создаёт **только отсутствующих** пользователей, уже с ролями: `manager@` становится manager, остальные демо-аккаунты получают member. Существующих пользователей сид не меняет.

**Что нужно заранее:** этап 1. Свежий бэкап `app` (команда из этапа 0, шаг 1).

**Как проверить**

1. Миграция на копии реальных данных. Сама `app` не затрагивается:

   ```bash
   docker compose exec -T db createdb -U postgres app_migration_check
   docker compose exec -T db sh -c 'pg_dump -U postgres app | psql -q -U postgres -d app_migration_check'
   Q 'select email, is_superuser, is_active from "user" order by email' app_migration_check
   M() { docker compose exec -T backend sh -c "DATABASE_URL=\${DATABASE_URL%/*}/app_migration_check alembic $*"; }
   M upgrade head
   Q 'select email, role, is_active from "user" order by email' app_migration_check
   Q '\d "user"' app_migration_check
   M downgrade -1
   Q 'select email, is_superuser, is_active from "user" order by email' app_migration_check
   docker compose exec -T db dropdb -U postgres app_migration_check
   ```

   Ожидаемый результат:
   - после `upgrade` все, у кого было `is_superuser = t` (сейчас `admin@` и `manager@`), получили `admin`, остальные `member`;
   - `is_active` не изменился ни у кого, в том числе у `inactive@`;
   - колонки `is_superuser` нет;
   - после `downgrade` вывод совпадает с первым снимком.

   Механизм уже проверен на текущей схеме. Копирование и подмена `DATABASE_URL` работают: `alembic current` на копии вернул `fe56fa70289e (head)`, `app` не изменилась. Цепочка `pg_dump -Fc` → `docker compose cp` → `pg_restore` в отдельную БД тоже проверена: 7 из 7 пользователей.

2. Автотест миграции (см. «Тесты» ниже) проходит в общем прогоне:

   ```bash
   docker compose run --rm -v ./backend:/app/backend backend bash scripts/tests-start.sh
   ```

3. Применение к `app`. Выполняется только после пунктов 1–2 и бэкапа, по отдельному подтверждению. До этого шага backend в `watch` будет отвечать ошибками на запросы к пользователям: код уже ждёт колонку `role`.

   ```bash
   docker compose exec backend alembic upgrade head
   Q 'select email, role, is_active from "user" order by email'
   ```

   Ожидаемый результат: то же, что на копии в пункте 1.

4. Интерфейс:
   - под admin страница Admin работает как раньше, в таблице колонка роли, в «Add User» выпадающий список Admin/Manager/Member;
   - `manager@` после миграции **admin**: так и должно быть, бывший суперюзер не теряет прав. Чтобы получить менеджера, admin вручную меняет ему роль на Manager через Edit User. Это сознательное изменение данных, оно же проверяет смену роли;
   - под alice пункта Admin нет, при переходе на `/admin` её редиректит на `/`.

**Тесты**

- `backend/tests/migrations/test_role_migration.py`, каждый тест на своей временной БД `app_migration_<random>` (удаляется в `finally`):
  - upgrade: активный и неактивный суперюзер → admin, обычные → member, `is_active` сохраняется, колонки `is_superuser` нет;
  - вставка без `role` даёт member, `role = 'root'` отклоняется CHECK;
  - downgrade: `is_superuser` только у admin, manager → false, `is_active` сохраняется, колонки `role` нет.

  Без миграции все 3 падали (`column "role" does not exist`). Alembic запускается отдельным процессом с подменённым `DATABASE_URL`, `alembic/env.py` не менялся.
- `backend/tests/api/routes/test_users.py`, запрет лишних полей. Без `extra="forbid"` все 4 падали с 200:
  - `PATCH` с `{"is_superuser": false}` → 422, роль осталась admin;
  - `PATCH` с `{"full_name": …, "is_superuser": false}` → 422, имя не изменилось;
  - `PATCH` с `{"is_activ": false}` → 422, пользователь активен;
  - `POST` с `is_superuser` → 422, пользователь не создан.
- Существующие тесты переведены с `is_superuser` на `role` (`test_users.py`, `test_login.py`, `crud/test_user.py`).
- e2e `admin.spec.ts`: тест «Create a superuser» стал «Create an admin» с выбором роли; существующие тесты создания пользователя подтверждают исправление `confirm_password`.

---

## Этап 3. Права ролей на backend и метрики

**Что меняется**

- `app/core/permissions.py` — единственное место правил доступа: `UserRole` (переехал из `models.py`), `Permission`, `ROLE_PERMISSIONS`, `has_permission`, `permissions_for`.

  | Право | admin | manager | member |
  |---|---|---|---|
  | `users:read`: список и карточки пользователей | ✓ | ✓ | — |
  | `users:manage`: создание, изменение, удаление, роль и статус | ✓ | — | — |
  | `metrics:read` | ✓ | ✓ | — |
  | `items:all`: **чужие** items | ✓ | — | — |
  | `system:manage`: служебный `test-email` | ✓ | — | — |

  Admin получает все права, включая будущие (`frozenset(Permission)`).
- `deps.py`: фабрика `require_permission(Permission.X)` заменила `get_current_active_superuser`, старая зависимость удалена.
- Эндпоинты:
  - `GET /users/` — `users:read`; `GET /users/{id}` — свой профиль или `users:read`;
  - `POST /users/`, `PATCH /users/{id}`, `DELETE /users/{id}`, `POST /password-recovery-html-content/{email}` (отдаёт ссылку сброса пароля чужого аккаунта) — `users:manage`;
  - `POST /utils/test-email/` — `system:manage`;
  - новый `GET /metrics/` — `metrics:read`, заглушка: `users_total`, `users_active`, `users_by_role`, `items_total`.
- **Items.** Список `GET /items/` и чтение/изменение/удаление **своих** items доступны всем ролям. `items:all` только расширяет доступ на чужие items: admin видит и меняет все, manager и member — только свои, на чужие 403.
- `GET /users/me` отдаёт `permissions` (`UserMePublic`), вычисленные по роли на каждом запросе. В списке пользователей прав нет.
- Admin не может **изменить** себе `role` или `is_active` (403). Те же значения проходят: форма Edit User отправляет их и при правке своего имени. Удалить себя admin не может, как и раньше.
- Найден и исправлен баг исходного шаблона: `password-recovery-html-content` отдавал заголовок с недопустимым именем `"subject:"`, на живом сервере соединение обрывалось (`RuntimeError: Invalid HTTP header name`, есть в upstream `master`). Тест прав для admin его поймал; исправление — `"subject"`.

**Что нужно заранее:** этап 2 применён к `app`.

**Как проверить: матрица доступа.** Проверки идут на временных пользователях, которых в конце удаляет admin: данные `app` не меняются, `manager@` трогать не нужно.

```bash
ADMIN=$(tok admin@example.com changethis)
send $ADMIN POST $B/users/ '{"email":"tmp-manager@example.com","password":"password123","role":"manager"}'   # 200
send $ADMIN POST $B/users/ '{"email":"tmp-member@example.com","password":"password123"}'                     # 200
MANAGER=$(tok tmp-manager@example.com password123); MEMBER=$(tok tmp-member@example.com password123)
BOB=$(uid bob@example.com)
for T in ADMIN MANAGER MEMBER; do t=${!T}; echo "== $T"
  echo "me.permissions     $(show $t $B/users/me | python -c "import sys,json;print(json.load(sys.stdin)['permissions'])")"
  echo "GET /users/        $(code $t $B/users/)"
  echo "GET /users/{bob}   $(code $t $B/users/$BOB)"
  echo "GET /metrics/      $(code $t $B/metrics/)"
  echo "PATCH bob name     $(send $t PATCH $B/users/$BOB '{"full_name":"Bob Brown"}')"
  echo "recovery html      $(send $t POST $B/password-recovery-html-content/bob@example.com)"
done
```

| Запрос | admin | manager | member |
|---|---|---|---|
| `permissions` | все 5 | `metrics:read`, `users:read` | `[]` |
| `GET /users/` | 200 | 200 | **403** |
| `GET /users/{bob}` | 200 | 200 | **403** |
| `GET /metrics/` | 200 | 200 | **403** |
| `PATCH /users/{bob}` (то же имя) | 200 | **403** | **403** |
| `POST /password-recovery-html-content/bob@…` | 200 | **403** | **403** |

Items — свои и чужие:

```bash
ITEM=$(curl -s -X POST -H "Authorization: Bearer $MEMBER" -H 'Content-Type: application/json' -d '{"title":"tmp item"}' $B/items/ | python -c "import sys,json;print(json.load(sys.stdin)['id'])")
code $MEMBER  $B/items/$ITEM                                   # 200, свой
send $MEMBER  PUT $B/items/$ITEM '{"title":"renamed by owner"}'   # 200
code $MANAGER $B/items/$ITEM                                   # 403, чужой
send $MANAGER PUT $B/items/$ITEM '{"title":"renamed by manager"}' # 403
send $MANAGER DELETE $B/items/$ITEM                            # 403
code $ADMIN   $B/items/$ITEM                                   # 200, items:all
show $MANAGER "$B/items/?limit=500" | python -c "import sys,json;print(json.load(sys.stdin)['count'])"   # 0: у временного менеджера своих нет
show $MEMBER  $B/items/$ITEM | python -c "import sys,json;print(json.load(sys.stdin)['title'])"          # renamed by owner
```

Смена роли действует на уже выданный токен, и `/users/me` сразу отдаёт новые права:

```bash
MGR_ID=$(uid tmp-manager@example.com)
send $ADMIN PATCH $B/users/$MGR_ID '{"role":"member"}'      # 200
code $MANAGER $B/users/                                     # 403 тем же токеном
show $MANAGER $B/users/me                                   # "role":"member","permissions":[]
send $ADMIN PATCH $B/users/$MGR_ID '{"role":"manager"}'     # 200
show $MANAGER $B/users/me                                   # "permissions":["metrics:read","users:read"]
```

Повысить себе роль нельзя, admin не может лишить доступа себя:

```bash
send $MEMBER PATCH $B/users/me '{"role":"admin"}'           # 200, но роль не изменилась
show $MEMBER $B/users/me                                    # "role":"member"
ME=$(uid admin@example.com)
send $ADMIN PATCH $B/users/$ME '{"role":"member"}'          # 403
send $ADMIN PATCH $B/users/$ME '{"is_active":false}'        # 403
send $ADMIN PATCH $B/users/$ME '{"role":"admin","is_active":true}'   # 200: значения не меняются
```

Откат — удалить временных пользователей (их items удаляются каскадно):

```bash
send $ADMIN DELETE $B/users/$(uid tmp-manager@example.com)  # 200
send $ADMIN DELETE $B/users/$(uid tmp-member@example.com)   # 200
```

Под конец сверить контрольный снимок `app` с началом этапа.

**Тесты:** `backend/tests/api/routes/test_access.py`, роли и права записаны строками, как их видит API:
- `/users/me`: роль и `permissions` у каждой роли;
- пользователи: список, чужая и своя карточка, создание, изменение имени/роли/статуса, удаление, recovery HTML, test-email — для каждой роли, с проверкой, что при 403 данные не изменились;
- метрики: 200 для admin и manager, 403 для member, форма ответа;
- items: список (свои у всех, чужие только у admin), чтение/изменение/удаление своих — 200 у всех, чужих — 200 только у admin, при 403 item не изменился и не удалён;
- смена роли тем же токеном: доступ и `/users/me` (`role`, `permissions`) меняются сразу, в обе стороны;
- signup и `PATCH /users/me` не повышают роль;
- admin не может сменить себе роль или статус, а форма с неизменными значениями проходит.

На коде этапа 2 по делу падали 12 тестов: нет `permissions` (3), manager получает 403 на просмотр пользователей (2), нет `/metrics/` (3), токен не видит новую роль (1), admin меняет себе роль и статус (2), recovery HTML у admin — баг с заголовком (1). Ещё 3 падали из-за моей ошибки в самом тесте (чтение `id` у удалённого item), исправлено. Тесты items на коде этапа 2 проходили: правила для items не менялись, это регрессионная сетка.

---

## Этап 4. Роли на frontend и реакция на 403

**Что меняется**

- `useAuth` отдаёт `can(permission)` на основе `user.permissions`.
- Сайдбар: «Users» (бывший Admin) виден при `users:read`, «Metrics» при `metrics:read`.
- `/admin`:
  - guard пускает при `users:read`;
  - кнопка Add User и меню действий в строках видны только при `users:manage`;
  - в строке текущего пользователя нет пунктов смены роли, деактивации и удаления.
- Новая страница `/metrics`: заглушка, guard по `metrics:read`.
- Settings: вкладка удаления аккаунта скрыта у admin, как сейчас у суперюзера.
- Guards читают пользователя свежим запросом `readUserMe`, как текущий guard `/admin`. Без прав маршрут редиректит на `/`.

**Что нужно заранее:** этапы 1 и 3.

**Как проверить в интерфейсе**

| Действие | admin | manager | member |
|---|---|---|---|
| Пункты меню | Dashboard, Items, Users, Metrics | Dashboard, Items, Users, Metrics | Dashboard, Items |
| Перейти по адресу `/admin` | таблица, Add User, меню действий | таблица **без** Add User и меню действий | редирект на `/` |
| Перейти по адресу `/metrics` | заглушка с цифрами | заглушка с цифрами | редирект на `/` |
| Add User / Edit User | выбор роли | недоступно | недоступно |
| Своя строка в таблице | без смены роли, деактивации и удаления | — | — |
| Settings | без вкладки удаления аккаунта | вкладка есть | вкладка есть |

Реакция на 403 без перезагрузки страницы (обычное окно и инкогнито):

1. В обычном окне `manager@` открывает `/admin`.
2. В инкогнито admin понижает его до Member.
3. Вернуться в окно manager. react-query перезапрашивает данные при фокусе окна, и запрос списка пользователей получает 403.
4. Ожидаемый результат: manager **остаётся залогиненным**, его перебрасывает на `/`, пункты Users и Metrics пропадают. Если его выкинуло на `/login`, обработка 403 работает неправильно.
5. Откат: admin возвращает роль Manager.

Деактивация во время сессии должна по-прежнему выбрасывать на `/login` (проверка 401 из этапа 1, но уже вместе с ролями). Откат: активировать пользователя обратно.

**Тесты**

- e2e: адаптированный `admin.spec.ts` и новый `roles.spec.ts`:
  - member, открывший `/admin` по адресу, оказывается на `/`;
  - member, открывший `/metrics` по адресу, оказывается на `/`;
  - manager видит таблицу пользователей без «Add User».
- Запуск в отдельном проекте `ender-e2e` (команды из этапа 0, шаг 4).
- Типы проверяются сборкой образа: `tsc` запускается в `bun run build`.

---

## Этап 5. Документация и сдача

**Что меняется**

- `development.md`, короткий раздел «Роли»:
  - таблица демо-аккаунтов и команда сида `docker compose exec backend python -m app.seed_data`;
  - тесты backend работают с `app_test`;
  - e2e запускается в отдельном compose-проекте.
- Остальные команды запуска и тестов не меняются.
- `ai-conversations/`: сырые экспорты всех AI-диалогов по заданию. Перед коммитом поиск секретов, каждое удаление помечается явно.
- Ветка `feature/roles` (коммит на этап) и PR в `main` этого репозитория, чтобы ревьюер видел дифф против шаблона.

**Что нужно заранее:** этапы 0–4, все тесты зелёные.

**Как проверить:** прогон с нуля, как это сделает ревьюер. Отдельный проект `ender-review` со своим томом, основной стек остановлен:

```bash
docker compose stop
docker compose -p ender-review build
docker compose -p ender-review run --rm backend bash scripts/prestart.sh
docker compose -p ender-review up -d
docker compose -p ender-review exec backend python -m app.seed_data
```

Войти под каждым демо-аккаунтом и пройти таблицу из этапа 4. Затем:

```bash
docker compose -p ender-review down -v
docker compose start
```

---

## Какие тесты что проверяют

| Тест | Поведение |
|---|---|
| `tests/conftest.py` (защита) | тесты не запускаются против БД без суффикса `_test` |
| `tests/api/test_deps.py` | 401 для невалидного и просроченного токена, деактивированного и удалённого пользователя; повторная активация возвращает сессию; 400 при логине неактивного |
| e2e `login.spec.ts` (Deactivated user…) | сессия деактивированного пользователя в браузере заканчивается переходом на `/login` |
| `tests/migrations/test_role_migration.py` | `is_superuser` → `admin`, остальные → `member`, `is_active` сохраняется, CHECK и default работают, downgrade даёт `is_superuser` только admin; работает на временной БД |
| `tests/api/routes/test_users.py` (rejects…) | админские `POST/PATCH /users` отвечают 422 на `is_superuser` и опечатки, ничего не применяя |
| `tests/api/routes/test_access.py` | матрица ролей и эндпоинтов, свои и чужие items, `permissions` в `/users/me`, смена роли тем же токеном меняет доступ и `permissions`, нельзя повысить себе роль через signup и `/users/me`, admin не может лишить доступа себя |
| существующие тесты `tests/api/routes/*`, `tests/crud/*` | старое поведение не сломалось, admin = бывший суперюзер |
| e2e `admin.spec.ts`, `roles.spec.ts` | интерфейс по ролям и редиректы при прямом переходе по адресу |

## Вне скоупа

- **Гонка при одновременном понижении двух админов друг другом.** Если два админа одновременно понизят друг друга, админов может не остаться. Запрет на изменение себя закрывает только последовательный случай. Это осознанно не решаем, ограничение будет указано в описании PR.
- Отзыв JWT при смене пароля.
- Визуальная полировка и рефакторинг, не связанные с ролями.

## Время

Задание рассчитано примерно на час, план заметно больше: самые тяжёлые этапы 0 и 2. Реально потраченное время нужно указать при сдаче, поэтому учёт ведётся с этапа 0.

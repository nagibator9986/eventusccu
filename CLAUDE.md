# CLAUDE.md — CCU Invite

Рабочий контекст для Claude Code по этому репозиторию. Прочитай целиком перед
изменениями: здесь зафиксированы архитектура, инварианты и «грабли», которые
легко нарушить.

---

## 1. Что это за проект

Веб-платформа (mobile-first) для **Колледжа Каспийского университета (ccu.kz)**
для церемонии вручения дипломов. Назначение — контроль гостей (родителей и
родственников выпускников) на входе при **ограниченном числе мест**.

Поток ценности:

1. **Администратор** добавляет студентов; к каждому студенту — заранее
   заявленных родителей/родственников (лимит на студента настраивается).
2. Для каждого гостя генерируется **именная ссылка-приглашение** (действует
   месяц). По ссылке открывается красивый **пригласительный билет** в фирменном
   стиле CCU с **QR-кодом**.
3. На входе **контролёр (сканер)** наводит камеру телефона на QR прямо в
   браузере → видит данные гостя → жмёт «Подтвердить присутствие» → в БД гость
   автоматически помечается `present`.

Главная цель UX: **быстро и удобно на телефоне**. Любая правка интерфейса
проверяется в первую очередь на мобильном вьюпорте.

---

## 2. Технологии

- **Backend:** Flask 3 (app-factory), Flask-SQLAlchemy, Flask-Login, Flask-WTF (CSRF).
- **БД:** SQLite (файл `instance/ccu.db`). Создаётся автоматически.
- **QR:** библиотека `qrcode` (server-side) → PNG в base64 data-URI.
- **Frontend:** серверный рендеринг (Jinja2) + один CSS-файл (дизайн-система) +
  ванильный JS. Камера/сканер — библиотека `html5-qrcode`, **хранится локально**
  в `app/static/js/html5-qrcode.min.js` (без внешнего CDN — надёжность на входе).
- **Без сборки фронтенда.** Нет Node/webpack. Это осознанно — простота и скорость.

---

## 3. Структура

```
ccu/zhigerhuinyaqre/
├── run.py                  # точка входа dev-сервера
├── config.py               # вся конфигурация (env-driven)
├── requirements.txt
├── .env.example            # шаблон переменных окружения
├── scripts/seed.py         # init БД + демо-данные + создание admin/scanner
├── instance/ccu.db         # SQLite (gitignored, создаётся в рантайме)
└── app/
    ├── __init__.py         # create_app(): расширения, блюпринты, фильтры, CLI, error-handlers
    ├── extensions.py       # db, login_manager, csrf (без привязки к app)
    ├── models.py           # User, Student, Guest + статусы/роли/типы родства
    ├── utils/
    │   ├── qr.py           # qr_data_uri()
    │   └── urls.py         # invite_url() — учитывает PUBLIC_BASE_URL
    ├── auth/               # вход/выход + decorators.admin_required
    ├── admin/              # CRUD студентов/гостей, генерация приглашений, сотрудники
    ├── invite/             # ПУБЛИЧНАЯ страница билета по токену (/i/<token>)
    ├── scan/               # сканер (/scan) + JSON API lookup/checkin
    ├── main/               # / (роутинг по роли) + /healthz
    ├── templates/          # Jinja: base.html + разделы
    └── static/
        ├── css/app.css     # ВСЯ дизайн-система в одном файле
        ├── js/app.js       # flash-автоскрытие, copy-to-clipboard, confirm
        ├── js/scanner.js   # логика камеры и подтверждения
        └── img/logo.svg    # фирменный знак CCU (самодостаточный SVG)
```

---

## 4. Модель данных (`app/models.py`)

**User** — сотрудник. Поля: `username`, `full_name`, `password_hash`, `role`
(`admin` | `scanner`), `active`. Пароли — `werkzeug.security`. `is_admin`,
`is_active` (учитывает `active`).

**Student** — выпускник. Поля: `full_name`, `group_name`, `specialty`.
Свойства: `guests_total`, `guests_present`, `seats_left` (по
`MAX_GUESTS_PER_STUDENT`). `guests` каскадно удаляются вместе со студентом.

**Guest** — приглашённый родитель/родственник. Ключевые поля:
- `student_id` (FK, ondelete CASCADE)
- `full_name`, `relation` (см. `RELATIONS`), `phone`
- `token` (уникальный, `secrets.token_urlsafe(24)`) — секрет приглашения и
  содержимое QR; `invited_at`, `expires_at`
- `status`: `added` → `invited` → `present`
- `checked_in_at`, `checked_in_by_id`

Методы: `generate_invite(days)` (перевыпуск меняет токен — старая ссылка
умирает), `mark_present(user)`, `reset_presence()`, свойства `is_link_valid`,
`is_expired`, `status_label`, `relation_phrase` («родитель»/«родственник»).

**Инвариант статусов:** `added` (нет токена) → `invited` (токен есть) →
`present` (отмечен). Не вводи статусы в обход `generate_invite/mark_present`.

---

## 5. Маршруты (карта)

| Метод | URL | Доступ | Назначение |
|------|-----|--------|-----------|
| GET/POST | `/login` | public | вход |
| GET | `/logout` | auth | выход |
| GET | `/` | auth | редирект по роли (admin→dashboard, scanner→scan) |
| GET | `/healthz` | public | health-check |
| GET | `/admin/` | admin | сводка/статистика |
| GET | `/admin/students` | admin | список + поиск |
| POST | `/admin/students/new` | admin | создать студента |
| GET | `/admin/students/<sid>` | admin | карточка студента + гости |
| POST | `/admin/students/<sid>/edit`,`/delete` | admin | правка/удаление |
| POST | `/admin/students/<sid>/guests` | admin | добавить гостя (проверка лимита) |
| POST | `/admin/guests/<gid>/invite` | admin | сгенерировать/перевыпустить приглашение |
| POST | `/admin/guests/<gid>/edit`,`/delete`,`/reset` | admin | правка/удаление/снять отметку |
| GET | `/admin/guests` | admin | все гости (фильтр по статусу, поиск) |
| GET/POST | `/admin/users[...]` | admin | управление сотрудниками |
| **GET** | **`/i/<token>`** | **public** | **пригласительный билет (QR)** |
| GET | `/scan` | auth | страница сканера |
| GET | `/scan/api/lookup?token=` | auth | JSON о госте (без изменений) |
| POST | `/scan/api/checkin` | auth | отметить присутствие (идемпотентно) |

**Доступ к админке** реализован через `admin_bp.before_request` +
`admin_required`. Любой новый admin-маршрут автоматически защищён — не дублируй
декораторы на каждой вьюхе.

---

## 6. Критичные инварианты и «грабли»

1. **Камера требует защищённый контекст.** `getUserMedia` работает только на
   `https://` или `http://localhost`. На телефоне по LAN-IP (`http://192.168…`)
   камера НЕ откроется. Решения: `SSL_ADHOC=1 python run.py` (самоподписанный
   сертификат) или туннель (ngrok/cloudflared). Это №1 причина «сканер не
   работает» — всегда проверяй это первым.

2. **`PUBLIC_BASE_URL` определяет, что попадёт в ссылку и QR.** Если не задан —
   берётся хост текущего запроса (`url_for(..., _external=True)`). Если админ
   генерирует приглашение, открыв панель по `localhost`, в QR попадёт
   `localhost` → бесполезно для рассылки. Для прод/демо задавай реальный домен
   в `.env`. Логика в `app/utils/urls.py::invite_url`.

3. **QR кодирует ПОЛНЫЙ URL билета** (`{base}/i/<token>`), не «голый» токен.
   Сканер (`scan.js`) и backend (`scan/routes.py::_extract_token`) умеют достать
   токен и из URL, и из голой строки — сохраняй это при изменениях формата.

4. **CSRF.** Включён глобально (Flask-WTF). Все формы содержат
   `{{ csrf_token() }}`. JSON-эндпоинт `/scan/api/checkin` шлёт заголовок
   `X-CSRFToken` (берётся из `<meta name="csrf-token">`, см. `scanner.js`).
   `lookup` — GET, CSRF не нужен. Не добавляй `@csrf.exempt` без явной причины.

5. **Идемпотентность check-in.** Повторный скан уже отмеченного гостя
   возвращает `ok:true, already:true` и НЕ меняет `checked_in_at`. Контролёр на
   входе сканирует быстро и повторно — это норма.

6. **Время хранится в UTC**, отображается со сдвигом `DISPLAY_TZ_OFFSET`
   (по умолчанию +5, Казахстан). Для дат в шаблонах используй фильтры
   `| dt`, `| d`, `| dlong` (определены в `app/__init__.py`). Не форматируй
   `datetime` напрямую в шаблоне.

7. **Один CSS-файл.** Вся стилизация — в `app/static/css/app.css` с
   CSS-переменными (фирменные `--navy`, `--gold`). Не вводи инлайн-«дизайн»;
   мелкие точечные стили инлайном допустимы, но компоненты — в CSS.

8. **Лимит мест** проверяется в `guest_create` по `MAX_GUESTS_PER_STUDENT`
   (есть повторная проверка в транзакции — защита от гонки/двойного сабмита).
   `VENUE_CAPACITY` — справочно для статистики (0 = без лимита).

9. **Безопасность по умолчанию (важно при правках):**
   - `SECRET_KEY` без env → **случайный на запуск процесса** (нельзя подделать
     cookie/CSRF; сессии сбрасываются при рестарте). Для прод задайте постоянный.
   - Интерактивный отладчик Werkzeug (RCE-поверхность) включается **только на
     loopback** (`run.py`). На `0.0.0.0`/LAN debug принудительно выключен.
   - Вход защищён простым **throttle по IP** (5 попыток / 5 мин, in-memory,
     `app/auth/routes.py`). Для multi-worker вынесите в Redis.
   - **SQLite FK включены** (`PRAGMA foreign_keys=ON` в `extensions.py`), поэтому
     `ondelete=CASCADE` реально работает — «сирот» не возникает.
   - JSON-эндпоинты `/scan/api/*` всегда отвечают JSON даже на ошибки
     (CSRF/403/404/500) — см. error-handlers в `app/__init__.py`.

---

## 7. Запуск и команды

```bash
# окружение
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# инициализация + демо (создаёт admin/admin123 и scanner/scan123)
python3 -m scripts.seed --demo
# python3 -m scripts.seed --reset --demo   # пересоздать с нуля

# запуск
python3 run.py                       # http://localhost:5000
SSL_ADHOC=1 python3 run.py           # https (нужно для камеры на телефоне)
PORT=8080 python3 run.py

# управление пользователями через Flask CLI
export FLASK_APP=run.py
flask create-user                    # интерактивно
flask init-db
```

> Примечание: в этой среде интерпретатор — `python3` (не `python`).

**Демо-учётки:** `admin / admin123` (администратор), `scanner / scan123`
(контролёр). Смени пароли перед реальным использованием.

---

## 8. Конвенции кода

- **Язык интерфейса — русский.** Все строки, flash-сообщения, лейблы — по-русски.
  Код/идентификаторы — английские; комментарии — русские (как в существующих файлах).
- **Блюпринты** изолированы по доменам; общая логика — в `utils/`.
- **Доступ к БД** через `db.session.get(Model, id)` (SQLAlchemy 2.x style), не
  `Model.query.get`.
- **Формы** — обычный HTML + ручная валидация во вьюхе + flash. WTForms-классы
  намеренно не используются (меньше кода для простого CRUD).
- **Шаблоны:** админка/служебные страницы наследуют `base.html`. Публичные
  страницы (`invite/card,invalid,expired`) — **самостоятельный HTML** (без
  app-навигации), чтобы билет выглядел premium и не зависел от авторизации.

---

## 9. Проверка перед коммитом (smoke)

Быстрый прогон без браузера (test client):

```bash
python3 - <<'PY'
from app import create_app
app = create_app(); app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
c = app.test_client()
c.post("/login", data={"username":"admin","password":"admin123"})
for u in ["/admin/","/admin/students","/admin/guests","/admin/users","/scan"]:
    print(u, c.get(u).status_code)
PY
```

Проверяй вручную на мобильном вьюпорте (DevTools → device toolbar): вход,
добавление студента и гостя, генерация приглашения, открытие билета, сканер.

---

## 9b. Деплой (Railway / прод)

Артефакты прода: `railway.json` (builder NIXPACKS, startCommand, healthcheck
`/healthz`), `Procfile`, `.python-version` (3.12), `scripts/release.py`.

- **Сервер:** `gunicorn 'app:create_app()'` — фабрика, 1 worker + 8 threads
  (для SQLite важно: без межпроцессных блокировок записи; in-memory throttle
  тоже консистентен при 1 воркере). Дев-сервер (`run.py`) в проде НЕ используется.
- **БД на Railway эфемерна.** SQLite класть на Volume:
  `DATABASE_URL=sqlite:////data/ccu.db` (4 слэша). Либо плагин Postgres —
  `config.py` нормализует `postgres://` → `postgresql://`.
- **`ProxyFix`** (в `create_app`) доверяет `X-Forwarded-*` → `request.scheme=https`
  за прокси. Без него secure-cookie и ссылки-приглашения были бы по http.
- **release-скрипт** создаёт таблицы и админа/сканера из env (`ADMIN_PASSWORD`
  и т.д.); если пароль админа не задан и админов нет — генерирует и пишет в лог.
- **Прод-профиль** включается `FLASK_ENV=production` (`SESSION_COOKIE_SECURE=True`).
  Обязательно задать постоянный `SECRET_KEY` в переменных Railway.

Подробная инструкция — `DEPLOY.md`. Менять startCommand — синхронно в
`railway.json` И `Procfile`.

## 10. Точки расширения (если попросят доработать)

- **Экспорт списка присутствующих** (CSV/XLSX) — добавь вьюху в `admin`,
  переиспользуй `guests_overview`-запрос.
- **Настройки события в UI** (лимиты/вместимость) — сейчас в `config.py`; для
  правки без рестарта заведи таблицу `Setting` и читай через хелпер.
- **Несколько мероприятий/дат** — добавь модель `Event` и FK у `Student`.
- **Уведомления родителям** (SMS/WhatsApp/email) — точка интеграции в
  `guest_invite` после генерации токена.
- **PWA-офлайн сканера** — `html5-qrcode` уже вендорнут локально; для полного
  офлайна добавь service worker, кэширующий статику.
- **Безопасность для интернета** — задай постоянный `SECRET_KEY`, запусти под
  gunicorn/waitress за HTTPS-прокси, перенеси login-throttle в Redis.

При любой доработке сохраняй инварианты из §6 и mobile-first как приоритет.

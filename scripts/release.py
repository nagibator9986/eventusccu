"""Release-шаг для деплоя (Railway и др.): выполняется ПЕРЕД стартом gunicorn.

Идемпотентно:
  * создаёт таблицы БД;
  * создаёт администратора и сканера из переменных окружения, если их ещё нет.

Переменные окружения:
  ADMIN_USERNAME   (по умолчанию: admin)
  ADMIN_PASSWORD   — пароль администратора. Если не задан И администратора ещё
                     нет — генерируется случайный и печатается в лог деплоя.
  SCANNER_USERNAME (по умолчанию: scanner)
  SCANNER_PASSWORD — пароль сканера (если не задан — учётка сканера не создаётся).
"""
import os
import secrets

from app import create_app
from app.extensions import db
from app.models import ROLE_ADMIN, ROLE_SCANNER, User


def _ensure(username: str, password: str | None, role: str, full_name: str) -> None:
    if not username or not password:
        return
    if User.query.filter_by(username=username).first():
        print(f"[release] пользователь {username!r} уже существует — пропуск")
        return
    user = User(username=username, full_name=full_name, role=role)
    user.set_password(password)
    db.session.add(user)
    print(f"[release] создан пользователь {username!r} ({role})")


def main() -> None:
    app = create_app()
    with app.app_context():
        db.create_all()
        print("[release] таблицы БД готовы")

        admin_user = os.environ.get("ADMIN_USERNAME", "admin")
        admin_pw = os.environ.get("ADMIN_PASSWORD")

        # Чтобы первый деплой всегда давал рабочий вход: если пароль не задан
        # и админов ещё нет — генерируем и выводим в лог (смените после входа!).
        if not admin_pw and not User.query.filter_by(role=ROLE_ADMIN).first():
            admin_pw = secrets.token_urlsafe(9)
            print("\n" + "=" * 56)
            print("[release] СГЕНЕРИРОВАН пароль администратора:")
            print(f"          логин:  {admin_user}")
            print(f"          пароль: {admin_pw}")
            print("          Сохраните его и смените после первого входа!")
            print("=" * 56 + "\n")

        _ensure(admin_user, admin_pw, ROLE_ADMIN, "Администратор")
        _ensure(
            os.environ.get("SCANNER_USERNAME", "scanner"),
            os.environ.get("SCANNER_PASSWORD"),
            ROLE_SCANNER,
            "Контролёр входа",
        )
        db.session.commit()

    # Импорт списка выпускников/родителей из data/graduates.xlsx (идемпотентно).
    # Отключается переменной IMPORT_ON_DEPLOY=0. Пригласительные генерируются,
    # если IMPORT_GENERATE_INVITES != "0".
    if os.environ.get("IMPORT_ON_DEPLOY", "1") != "0":
        try:
            from scripts.import_data import (
                DEFAULT_FILE,
                import_from_b64,
                import_records,
                parse_workbook,
            )

            gen = os.environ.get("IMPORT_GENERATE_INVITES", "1") != "0"
            data_b64 = os.environ.get("IMPORT_DATA_B64")

            if data_b64:
                # Приватная загрузка данных без публикации в репозитории
                stats = import_from_b64(data_b64.strip(), generate_invites=gen)
                print(f"[release] импорт из IMPORT_DATA_B64: {stats}")
            elif DEFAULT_FILE.exists():
                records = parse_workbook(DEFAULT_FILE)
                stats = import_records(records, generate_invites=gen)
                print(f"[release] импорт из файла: {stats}")
            else:
                print("[release] данных нет (ни IMPORT_DATA_B64, ни файл) — импорт пропущен")
        except Exception as exc:  # импорт не должен ронять деплой
            print(f"[release] предупреждение: импорт не выполнен: {exc}")

    print("[release] готово")


if __name__ == "__main__":
    main()

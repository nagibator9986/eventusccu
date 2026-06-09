"""Инициализация БД и наполнение демо-данными.

Запуск из корня проекта:
    python -m scripts.seed              # создаёт админа и сканера
    python -m scripts.seed --demo       # + добавляет демонстрационных студентов и гостей
    python -m scripts.seed --reset      # пересоздаёт таблицы (УДАЛЯЕТ данные!)

Пароли учёток по умолчанию: admin123 / scan123 (УДОБНО ДЛЯ ДЕМО, НЕБЕЗОПАСНО).
Переопределите через окружение для реального использования:
    SEED_ADMIN_PASSWORD=...  SEED_SCANNER_PASSWORD=...  python -m scripts.seed
"""
import os
import sys

from app import create_app
from app.extensions import db
from app.models import ROLE_ADMIN, ROLE_SCANNER, Guest, Student, User

ADMIN_PASSWORD = os.environ.get("SEED_ADMIN_PASSWORD", "admin123")
SCANNER_PASSWORD = os.environ.get("SEED_SCANNER_PASSWORD", "scan123")
_USING_DEFAULTS = not (
    os.environ.get("SEED_ADMIN_PASSWORD") and os.environ.get("SEED_SCANNER_PASSWORD")
)


def ensure_user(username, password, role, full_name):
    user = User.query.filter_by(username=username).first()
    if user:
        return user, False
    user = User(username=username, full_name=full_name, role=role)
    user.set_password(password)
    db.session.add(user)
    return user, True


def main():
    reset = "--reset" in sys.argv
    demo = "--demo" in sys.argv

    app = create_app()
    with app.app_context():
        if reset:
            db.drop_all()
            print("Таблицы удалены.")
        db.create_all()
        print("Таблицы созданы.")

        _, a_created = ensure_user("admin", ADMIN_PASSWORD, ROLE_ADMIN, "Администратор")
        _, s_created = ensure_user("scanner", SCANNER_PASSWORD, ROLE_SCANNER, "Контролёр входа")
        db.session.commit()
        if a_created:
            print(f"Создан администратор:  логин admin   / пароль {ADMIN_PASSWORD}")
        if s_created:
            print(f"Создан сканер:          логин scanner / пароль {SCANNER_PASSWORD}")
        if (a_created or s_created) and _USING_DEFAULTS:
            print("\n[!] Используются ПАРОЛИ ПО УМОЛЧАНИЮ. Перед реальным запуском "
                  "смените их (через профиль или переменные SEED_ADMIN_PASSWORD/"
                  "SEED_SCANNER_PASSWORD).")

        if demo and Student.query.count() == 0:
            demo_data = [
                ("Ахметов Дамир Серикович", "ВТ-21", "Вычислительная техника", [
                    ("Ахметов Серик Болатович", "Отец"),
                    ("Ахметова Гульнар Маратовна", "Мать"),
                ]),
                ("Иванова Алина Петровна", "ПО-22", "Программное обеспечение", [
                    ("Иванова Марина Сергеевна", "Мать"),
                ]),
                ("Жумабеков Нурлан Канатович", "ВТ-21", "Вычислительная техника", [
                    ("Жумабекова Айгуль Ержановна", "Мать"),
                    ("Жумабеков Канат Нурланович", "Дедушка"),
                ]),
            ]
            for full_name, group, spec, parents in demo_data:
                st = Student(full_name=full_name, group_name=group, specialty=spec)
                db.session.add(st)
                db.session.flush()
                for pname, rel in parents:
                    g = Guest(student_id=st.id, full_name=pname, relation=rel)
                    g.generate_invite()
                    db.session.add(g)
            db.session.commit()
            print("Добавлены демо-студенты и гости (с готовыми приглашениями).")

        print("\nГотово. Запустите:  python run.py")


if __name__ == "__main__":
    main()

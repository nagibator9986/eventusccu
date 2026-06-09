"""Модели данных CCU Invite.

Сущности:
  * User    — сотрудник: администратор (управляет данными) или сканер (вход).
  * Student — студент-выпускник.
  * Guest   — приглашённый родитель/родственник конкретного студента.
"""
import secrets
from datetime import datetime, timedelta

from flask import current_app
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db, login_manager

# --- Статусы гостя ----------------------------------------------------------
STATUS_ADDED = "added"      # добавлен в базу, приглашение ещё не сгенерировано
STATUS_INVITED = "invited"  # ссылка-приглашение сгенерирована
STATUS_PRESENT = "present"  # отмечен присутствующим на входе

STATUS_LABELS = {
    STATUS_ADDED: "Добавлен",
    STATUS_INVITED: "Приглашён",
    STATUS_PRESENT: "Присутствует",
}

# --- Роли пользователей -----------------------------------------------------
ROLE_ADMIN = "admin"
ROLE_SCANNER = "scanner"

# Типы родства для удобного выбора в интерфейсе
RELATIONS = [
    "Отец",
    "Мать",
    "Брат",
    "Сестра",
    "Дедушка",
    "Бабушка",
    "Опекун",
    "Родственник",
]


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(120), nullable=False, default="")
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default=ROLE_SCANNER)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # связь с отметками о присутствии
    checkins = db.relationship("Guest", backref="checked_in_by", lazy="dynamic")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    # Flask-Login учитывает флаг активности
    @property
    def is_active(self) -> bool:  # type: ignore[override]
        return bool(self.active)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.username} ({self.role})>"


@login_manager.user_loader
def load_user(user_id: str):
    return db.session.get(User, int(user_id))


class Student(db.Model):
    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(160), nullable=False, index=True)
    group_name = db.Column(db.String(80), nullable=False, default="")
    specialty = db.Column(db.String(160), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    guests = db.relationship(
        "Guest",
        backref="student",
        cascade="all, delete-orphan",
        order_by="Guest.id",
        lazy="select",
    )

    @property
    def guests_total(self) -> int:
        return len(self.guests)

    @property
    def guests_present(self) -> int:
        return sum(1 for g in self.guests if g.status == STATUS_PRESENT)

    @property
    def seats_left(self) -> int:
        limit = current_app.config["MAX_GUESTS_PER_STUDENT"]
        return max(0, limit - self.guests_total)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Student {self.full_name} / {self.group_name}>"


class Guest(db.Model):
    __tablename__ = "guests"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), nullable=False
    )

    full_name = db.Column(db.String(160), nullable=False)
    relation = db.Column(db.String(40), nullable=False, default="Родственник")
    phone = db.Column(db.String(40), nullable=True)

    # Уникальный секретный токен приглашения (часть ссылки и содержимое QR)
    token = db.Column(db.String(64), unique=True, nullable=True, index=True)
    invited_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)

    status = db.Column(db.String(20), nullable=False, default=STATUS_ADDED)
    checked_in_at = db.Column(db.DateTime, nullable=True)
    checked_in_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True
    )

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # ------------------------------------------------------------------
    def generate_invite(self, valid_days: int | None = None) -> str:
        """Создаёт (или перевыпускает) токен приглашения и срок действия."""
        if valid_days is None:
            valid_days = current_app.config["INVITE_VALID_DAYS"]
        self.token = secrets.token_urlsafe(24)
        self.invited_at = datetime.utcnow()
        self.expires_at = self.invited_at + timedelta(days=valid_days)
        if self.status == STATUS_ADDED:
            self.status = STATUS_INVITED
        return self.token

    @property
    def is_link_valid(self) -> bool:
        if not self.token or not self.expires_at:
            return False
        return datetime.utcnow() <= self.expires_at

    @property
    def is_expired(self) -> bool:
        return bool(self.expires_at and datetime.utcnow() > self.expires_at)

    def mark_present(self, user: "User") -> None:
        self.status = STATUS_PRESENT
        self.checked_in_at = datetime.utcnow()
        self.checked_in_by_id = user.id

    def reset_presence(self) -> None:
        self.checked_in_at = None
        self.checked_in_by_id = None
        self.status = STATUS_INVITED if self.token else STATUS_ADDED

    @property
    def status_label(self) -> str:
        return STATUS_LABELS.get(self.status, self.status)

    @property
    def relation_phrase(self) -> str:
        """Фраза для пригласительного: «родитель или родственник»."""
        parental = {"Отец", "Мать", "Опекун"}
        return "родитель" if self.relation in parental else "родственник"

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Guest {self.full_name} -> student {self.student_id} [{self.status}]>"

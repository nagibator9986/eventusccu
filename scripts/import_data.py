"""Импорт выпускников и родителей из Excel (.xlsx) в базу.

Структура файла: каждый лист — специальность; в первой строке — код группы,
во второй — куратор; далее таблица «№ | ФИО выпускника | ФИО родителя».

Запуск:
    python -m scripts.import_data --dry-run            # только разбор, без записи в БД
    python -m scripts.import_data                      # импорт (идемпотентно)
    python -m scripts.import_data --no-invite          # не генерировать пригласительные
    python -m scripts.import_data --file "путь.xlsx"   # другой файл

По умолчанию берётся data/graduates.xlsx (рядом с проектом). Импорт идемпотентен:
повторный запуск не создаёт дубликатов (студент ищется по ФИО+группе, гость — по
ФИО в рамках студента).
"""
import argparse
import re
import sys
from pathlib import Path

import openpyxl

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_FILE = BASE_DIR / "data" / "graduates.xlsx"

# Маркеры «гостя не будет» — в этом случае студент создаётся без гостя.
_NO_GUEST_SUBSTRINGS = (
    "турци",            # Турцияда / Турцияға кетеді
    "без сопров",
    "никто",
    "не сможет",
    "не придет",
    "не придёт",
    "не идет",
    "не идёт",
    "не будет",
)
_NO_GUEST_EXACT = {"нет", "-", "—", "—-", "–", "n/a", "не указан", "не указано"}

# Ключевые слова родства (как отдельные «токены»). Порядок важен: более
# специфичные раньше. Значение — как покажем в системе.
_RELATION_TOKENS = [
    ("бабушка", "Бабушка"),
    ("дедушка", "Дедушка"),
    ("мама", "Мать"),
    ("мать", "Мать"),
    ("папа", "Отец"),
    ("отец", "Отец"),
    ("сестра", "Сестра"),
    ("брат", "Брат"),
    ("опекун", "Опекун"),
    ("теща", "Родственник"),
    ("тёща", "Родственник"),
    ("дядя", "Родственник"),
    ("тетя", "Родственник"),
    ("тётя", "Родственник"),
    ("аға", "Родственник"),
    ("ага", "Родственник"),
    ("апа", "Родственник"),
    ("ата", "Родственник"),
    ("әже", "Родственник"),
]
_RELATION_MAP = dict(_RELATION_TOKENS)
_RELATION_WORDS = {w for w, _ in _RELATION_TOKENS}

_SPLIT_RE = re.compile(r"[\s\-—–]+")
_PUNCT_STRIP = " \t.,;:()«»\"'`-—–"


def _norm(value) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).strip()


def parse_parent(raw) -> tuple[str, str] | None:
    """Из «грязной» ячейки родителя получаем (ФИО, родство) или None (гостя нет)."""
    s = _norm(raw)
    if not s:
        return None

    low = s.lower()
    if low in _NO_GUEST_EXACT:
        return None
    if any(sub in low for sub in _NO_GUEST_SUBSTRINGS):
        return None
    # строка только из тире/точек/скобок
    if not re.sub(r"[\s\-—–.()]+", "", s):
        return None

    tokens = [t for t in _SPLIT_RE.split(s) if t]
    name_tokens: list[str] = []
    relation: str | None = None
    for tok in tokens:
        key = tok.strip(_PUNCT_STRIP).lower()
        if relation is None and key in _RELATION_WORDS:
            relation = _RELATION_MAP[key]
            continue  # слово родства в ФИО не попадает
        # пропускаем «мусорные» одиночные символы
        cleaned = tok.strip(_PUNCT_STRIP)
        if cleaned:
            name_tokens.append(cleaned)

    name = " ".join(name_tokens).strip()
    if not name:
        return None
    if relation is None:
        relation = "Родственник"
    return name, relation


def _clean_group(text: str) -> str:
    """Код группы без хвостового пояснения в скобках: «МГР 24-5 грант (...)» -> «МГР 24-5 грант»."""
    return re.sub(r"\s*\(.*\)\s*$", "", text).strip()


def parse_workbook(path: Path) -> list[dict]:
    """Разбирает все листы. На одном листе может быть НЕСКОЛЬКО групп —
    каждая со своим кодом, куратором и шапкой. Отслеживаем текущую группу."""
    wb = openpyxl.load_workbook(path, data_only=True)
    records: list[dict] = []

    for ws in wb.worksheets:
        specialty = ws.title.strip()
        current_group = ""
        stud_col, par_col = 1, 2

        for row in ws.iter_rows(values_only=True):
            cells = [_norm(c) for c in row]
            a = cells[0] if cells else ""
            b = cells[1] if len(cells) > 1 else ""
            c = cells[2] if len(cells) > 2 else ""

            # 1) строка-заголовок таблицы
            if any("фио выпускник" in x.lower() for x in cells):
                for j, x in enumerate(cells):
                    xl = x.lower()
                    if "выпускник" in xl:
                        stud_col = j
                    elif "родител" in xl:
                        par_col = j
                continue

            # 2) строка куратора — пропускаем
            if a.lower().startswith("куратор"):
                continue

            a_is_num = a.replace(".", "").replace(" ", "").isdigit()

            # 3) строка-код группы: A заполнена, не число, не «№», B и C пустые
            if a and not a_is_num and a != "№" and not b and not c:
                current_group = _clean_group(a)
                continue

            # 4) строка данных
            student = cells[stud_col] if len(cells) > stud_col else ""
            if not student or student == "№" or "фио выпускник" in student.lower():
                continue
            parent_raw = row[par_col] if len(row) > par_col else None
            parsed = parse_parent(parent_raw)
            records.append(
                {
                    "student": student,
                    "group": current_group,
                    "specialty": specialty,
                    "guest_name": parsed[0] if parsed else None,
                    "relation": parsed[1] if parsed else None,
                    "parent_raw": _norm(parent_raw),
                }
            )

    return records


def import_records(records: list[dict], generate_invites: bool = True) -> dict:
    """Идемпотентно создаёт студентов и гостей в БД."""
    from app import create_app
    from app.extensions import db
    from app.models import Guest, Student

    app = create_app()
    stats = {"students_new": 0, "students_existing": 0, "guests_new": 0, "guests_existing": 0, "no_guest": 0}

    with app.app_context():
        for rec in records:
            student = Student.query.filter_by(
                full_name=rec["student"], group_name=rec["group"]
            ).first()
            if student is None:
                student = Student(
                    full_name=rec["student"],
                    group_name=rec["group"],
                    specialty=rec["specialty"],
                )
                db.session.add(student)
                db.session.flush()
                stats["students_new"] += 1
            else:
                stats["students_existing"] += 1

            if not rec["guest_name"]:
                stats["no_guest"] += 1
                continue

            guest = Guest.query.filter_by(
                student_id=student.id, full_name=rec["guest_name"]
            ).first()
            if guest is None:
                guest = Guest(
                    student_id=student.id,
                    full_name=rec["guest_name"],
                    relation=rec["relation"] or "Родственник",
                )
                if generate_invites:
                    guest.generate_invite()
                db.session.add(guest)
                stats["guests_new"] += 1
            else:
                stats["guests_existing"] += 1

        db.session.commit()
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description="Импорт выпускников и родителей из .xlsx")
    ap.add_argument("--file", default=str(DEFAULT_FILE), help="путь к .xlsx")
    ap.add_argument("--dry-run", action="store_true", help="только разбор, без записи")
    ap.add_argument("--no-invite", action="store_true", help="не генерировать пригласительные")
    args = ap.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"[import] файл не найден: {path}")
        sys.exit(1)

    records = parse_workbook(path)
    total = len(records)
    with_guest = sum(1 for r in records if r["guest_name"])
    no_guest = total - with_guest

    print(f"[import] разобрано студентов: {total}")
    print(f"[import]   с гостем: {with_guest}   без гостя: {no_guest}")

    if args.dry_run:
        # сводка по группам и примеры
        from collections import Counter
        by_group = Counter((r["group"], r["specialty"]) for r in records)
        print("\nГруппы:")
        for (g, spec), n in by_group.items():
            print(f"  {g}  ({spec}): {n}")
        print("\nПримеры разбора родителей:")
        shown = 0
        for r in records:
            if r["guest_name"] and shown < 12:
                print(f"  «{r['parent_raw']}»  ->  {r['guest_name']}  [{r['relation']}]")
                shown += 1
        print("\nБез гостя (примеры пометок):")
        seen = set()
        for r in records:
            if not r["guest_name"] and r["parent_raw"] and r["parent_raw"] not in seen:
                print(f"  {r['student']}  <-  «{r['parent_raw']}»")
                seen.add(r["parent_raw"])
                if len(seen) >= 12:
                    break
        return

    stats = import_records(records, generate_invites=not args.no_invite)
    print("\n[import] результат:")
    for k, v in stats.items():
        print(f"   {k}: {v}")
    print("[import] готово")


if __name__ == "__main__":
    main()

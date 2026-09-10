"""Validation des imports CSV manuels avant écriture atomique dans Supabase."""

import csv
import io


def activity_name(name):
    return name.strip().lower()


def parse_activities(content, allowed_degrees):
    try:
        text = (
            content.decode("utf-8-sig")
            if isinstance(content, bytes)
            else content.lstrip("\ufeff")
        )
    except UnicodeError as exc:
        raise ValueError("Enregistrez le fichier en CSV UTF-8.") from exc
    if not text.strip():
        raise ValueError("Le fichier ne contient aucune activité.")
    delimiter = ";" if ";" in text.splitlines()[0] else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter, strict=True)
    required = {"degree", "name", "professor", "room", "kind", "periods"}
    optional = {"capacity", "unlimited"}
    fields = reader.fieldnames or []
    if (
        len(fields) != len(set(fields))
        or not required <= set(fields)
        or set(fields) - required - optional
    ):
        raise ValueError(
            "Colonnes attendues : degree;name;professor;room;kind;periods;capacity;unlimited."
        )
    result, seen = [], set()
    try:
        for row in reader:
            prefix = f"Ligne {reader.line_num}"
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"{prefix} : nombre de colonnes incorrect.")
            row = {k: v.strip() for k, v in row.items()}
            if not any(row.values()):
                continue
            degree_text = row["degree"].upper().removeprefix("D")
            if degree_text not in ("1", "2", "3"):
                raise ValueError(f"{prefix} : degree doit être D1, D2 ou D3.")
            degree = int(degree_text)
            if degree not in allowed_degrees:
                raise ValueError(
                    f"{prefix} : D{degree} ne participe pas à cette séance."
                )
            if not all(row[k] for k in ("name", "professor", "room")):
                raise ValueError(
                    f"{prefix} : nom, professeur et local sont obligatoires."
                )
            if row["kind"] not in ("remediation", "depassement"):
                raise ValueError(
                    f"{prefix} : kind doit être remediation ou depassement."
                )
            parts = [
                p.strip().upper().removeprefix("P") for p in row["periods"].split("|")
            ]
            if (
                not parts
                or any(p not in ("9", "10") for p in parts)
                or len(parts) != len(set(parts))
            ):
                raise ValueError(f"{prefix} : periods doit être 9, 10 ou 9|10.")
            flag = row.get("unlimited", "").lower()
            if flag not in ("", "false", "true", "non", "oui", "0", "1"):
                raise ValueError(f"{prefix} : unlimited doit être true ou false.")
            unlimited = flag in ("true", "oui", "1")
            capacity_text = row.get("capacity", "") or "12"
            capacity = None
            if not unlimited:
                if (
                    not capacity_text.isascii()
                    or not capacity_text.isdigit()
                    or not 1 <= int(capacity_text) <= 2147483647
                ):
                    raise ValueError(
                        f"{prefix} : capacity doit être un entier positif."
                    )
                capacity = int(capacity_text)
            for period in map(int, parts):
                identity = (degree, period, activity_name(row["name"]))
                if identity in seen:
                    raise ValueError(
                        f"{prefix} : nom en double pour ce degré et cette période."
                    )
                seen.add(identity)
                result.append(
                    {
                        "name": row["name"],
                        "professor": row["professor"],
                        "room": row["room"],
                        "kind": row["kind"],
                        "degree": degree,
                        "period": period,
                        "capacity": capacity,
                    }
                )
    except csv.Error as exc:
        raise ValueError(
            "Le CSV contient une erreur de guillemets ou de séparateur."
        ) from exc
    if not result:
        raise ValueError("Le fichier ne contient aucune activité.")
    return result

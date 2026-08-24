#!/usr/bin/env python3
"""Detecta alumnos que no cumplen con las fechas clave del cuatrimestre.

Lee la hoja Calendario para saber qué fechas-límite caen "hoy o antes",
y para cada una evalúa la regla correspondiente cruzando Notas y DatosAlumnos.

Imprime un reporte JSON con los incumplimientos por regla.
"""

from __future__ import annotations

import datetime
import json
import re
import sys
from dataclasses import dataclass, field

import config
from sheets_client import open_spreadsheet


# --- Helpers de parseo de fechas ----------------------------------------------

DATE_FORMATS = [
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d/%m/%y",
    "%d-%m-%Y",
    "%d-%m-%y",
]


def parse_date(s: str) -> datetime.date | None:
    s = s.strip()
    if not s:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


# --- Modelo de datos ----------------------------------------------------------


@dataclass
class CalendarEntry:
    fecha: datetime.date
    descripcion: str


@dataclass
class Alumno:
    padron: str
    nombre: str
    email: str
    estado: str  # "Cambio" / "Condicional" / "Regular" / etc. (vacío si no hay)
    cumple_promocion: bool  # de la hoja Notas, columna "Cumple fechas/condiciones de promoción"
    notas: dict[str, str] = field(default_factory=dict)  # entrega → valor en Notas

    def entrega_ok(self, columna: str) -> bool:
        return self.notas.get(columna, "").strip().upper() == "E"


# --- Carga de planilla --------------------------------------------------------


def load_alumnos():
    sp = open_spreadsheet()

    # DatosAlumnos.
    alumnos_rows = sp.worksheet(config.SHEET_ALUMNOS).get_all_values()
    a_headers = alumnos_rows[0]

    def idx(h, name, *aliases):
        for cand in (name, *aliases):
            if cand in h:
                return h.index(cand)
        return None

    a_padron = idx(a_headers, "Padrón")
    a_nombre = idx(a_headers, "Alumno", "Nombre")
    a_email = idx(a_headers, "Email", "Mail")
    # Estado: "Condicional" / "Cambio" — buscamos por nombre flexible.
    a_estado = idx(a_headers, "Condición", "Estado", "Cursada")

    if a_padron is None:
        raise RuntimeError("DatosAlumnos: no encontré columna Padrón")

    alumnos: dict[str, Alumno] = {}
    for row in alumnos_rows[1:]:
        if a_padron >= len(row) or not row[a_padron].strip():
            continue
        padron = row[a_padron].strip()
        alumnos[padron] = Alumno(
            padron=padron,
            nombre=row[a_nombre].strip() if a_nombre is not None and a_nombre < len(row) else "",
            email=row[a_email].strip() if a_email is not None and a_email < len(row) else "",
            estado=row[a_estado].strip() if a_estado is not None and a_estado < len(row) else "",
            cumple_promocion=False,
        )

    # Notas.
    notas_rows = sp.worksheet(config.SHEET_NOTAS).get_all_values()
    n_headers = notas_rows[0]
    n_padron = n_headers.index("Padrón")
    # La columna de "cumple promoción": coincidencia laxa por si cambia el casing.
    n_cumple = None
    for i, h in enumerate(n_headers):
        if "cumple" in h.lower() and "promoci" in h.lower():
            n_cumple = i
            break

    for row in notas_rows[1:]:
        if n_padron >= len(row):
            continue
        padron = row[n_padron].strip()
        if not padron or padron not in alumnos:
            continue
        alu = alumnos[padron]
        if n_cumple is not None and n_cumple < len(row):
            alu.cumple_promocion = row[n_cumple].strip().upper() == "TRUE"
        for i, h in enumerate(n_headers):
            if i < len(row):
                alu.notas[h] = row[i]

    return list(alumnos.values())


def load_calendario_due_today_or_past(today: datetime.date) -> list[CalendarEntry]:
    sp = open_spreadsheet()
    cal_rows = sp.worksheet(config.SHEET_CALENDARIO).get_all_values()
    out: list[CalendarEntry] = []
    for row in cal_rows:
        if not row:
            continue
        fecha = parse_date(row[0])
        if fecha is None:
            continue
        # Última columna no vacía es la descripción.
        desc = ""
        for cell in reversed(row[1:]):
            if cell.strip():
                desc = cell.strip()
                break
        if not desc:
            continue
        if fecha <= today:
            out.append(CalendarEntry(fecha=fecha, descripcion=desc))
    return out


# --- Reglas -------------------------------------------------------------------

PROMO_RE = re.compile(r"^promoci[oó]n\s*:\s*", re.IGNORECASE)


def normalize(s: str) -> str:
    s = s.strip().lower()
    s = s.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
    return re.sub(r"\s+", " ", s)


def evaluate_rule(descripcion: str, alumnos: list[Alumno]) -> tuple[str, list[Alumno]]:
    """Devuelve (etiqueta-de-regla, lista-de-alumnos-que-incumplen)."""
    desc = normalize(descripcion)

    if desc.startswith("completar formulario"):
        return ("Sin email registrado", [a for a in alumnos if not a.email])

    if "tp0" in desc and ("condicional" in desc or "cambio" in desc):
        target = [
            a for a in alumnos
            if a.estado.lower() in ("condicional", "cambio")
            and not a.entrega_ok("TP0")
        ]
        return ("Cambio/Condicional sin TP0 OK", target)

    if "tp0" in desc and "condicional" not in desc and "cambio" not in desc:
        return ("Sin TP0 OK", [a for a in alumnos if not a.entrega_ok("TP0")])

    if "pila" in desc and "cola" in desc:
        return (
            "Sin Pila o Cola OK",
            [a for a in alumnos
             if not (a.entrega_ok("Pila") and a.entrega_ok("Cola"))],
        )

    is_promo = bool(PROMO_RE.match(descripcion.strip()))
    rest = PROMO_RE.sub("", descripcion.strip()) if is_promo else descripcion

    def filt_promo(predicate):
        return [a for a in alumnos if a.cumple_promocion and predicate(a)]

    rest_n = normalize(rest)

    if rest_n == "todo ok tp1":
        bad = lambda a: not a.entrega_ok("TP1")
        return ("Promo: pierde promoción por TP1", filt_promo(bad)) if is_promo \
            else ("Sin TP1 OK", [a for a in alumnos if bad(a)])

    if rest_n == "todo ok tp2":
        bad = lambda a: not a.entrega_ok("TP2")
        return ("Promo: pierde promoción por TP2", filt_promo(bad)) if is_promo \
            else ("Sin TP2 OK", [a for a in alumnos if bad(a)])

    if rest_n == "todo ok tp3":
        bad = lambda a: not a.entrega_ok("TP3")
        return ("Sin TP3 OK", [a for a in alumnos if bad(a)])

    if rest_n == "todo ok lista":
        bad = lambda a: not a.entrega_ok("Lista")
        return ("Sin Lista OK", [a for a in alumnos if bad(a)])

    if rest_n == "todo ok hash":
        bad = lambda a: not a.entrega_ok("Hash")
        return ("Promo: pierde promoción por Hash", filt_promo(bad))

    if rest_n == "todo ok abb y heap":
        bad = lambda a: not (a.entrega_ok("Abb") and a.entrega_ok("Heap"))
        return ("Promo: pierde promoción por ABB/Heap", filt_promo(bad))

    if "hash" in rest_n and "abb" in rest_n and "heap" in rest_n:
        bad = lambda a: not (a.entrega_ok("Hash") and a.entrega_ok("Abb") and a.entrega_ok("Heap"))
        return ("Sin Hash/ABB/Heap OK", [a for a in alumnos if bad(a)])

    return ("", [])


def main():
    today_str = sys.argv[1] if len(sys.argv) > 1 else None
    today = parse_date(today_str) if today_str else datetime.date.today()
    print(f"Evaluando fechas <= {today.isoformat()}", file=sys.stderr)

    alumnos = load_alumnos()
    calendario = load_calendario_due_today_or_past(today)

    findings = []
    for entry in calendario:
        label, malos = evaluate_rule(entry.descripcion, alumnos)
        if not label:
            continue
        if malos:
            findings.append({
                "fecha": entry.fecha.isoformat(),
                "regla": label,
                "descripcion_original": entry.descripcion,
                "alumnos": [
                    {"padron": a.padron, "nombre": a.nombre} for a in malos
                ],
            })

    print(json.dumps({"today": today.isoformat(), "findings": findings},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

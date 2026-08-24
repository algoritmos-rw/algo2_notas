#!/usr/bin/env python3
"""Lee commits nuevos del repo `entregas/` y actualiza la hoja Notas.

Convención de mensaje de commit:
    `:heavy_check_mark: New <entrega> upload from <padron[_padron...]>`
    `:x: New <entrega> upload from <padron[_padron...]>`

Reglas de overwrite por celda:
    - Vacía / "NE" / "WIP"  → se actualiza
    - Cualquier otro valor   → no se toca
    - WIP→WIP nunca escribe (evitamos request inútil).

El cursor del último commit procesado vive en `last_seen_commit.txt`.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import config
from sheets_client import open_spreadsheet


COMMIT_RE = re.compile(
    r"^(:heavy_check_mark:|:x:)\s+New\s+(\S+)\s+upload\s+from\s+(\S+)\s*$"
)


@dataclass
class Entrega:
    ok: bool
    entrega: str  # nombre tal como vino del commit (lowercase)
    padrones: list[str]
    sha: str


def run(cmd: list[str], cwd: str | None = None) -> str:
    return subprocess.check_output(cmd, cwd=cwd, text=True).strip()


def git_pull(repo: str) -> None:
    # Fetch siempre; pull al working tree solo si está limpio.
    subprocess.check_call(["git", "fetch", "--quiet", "origin"], cwd=repo)
    dirty = subprocess.call(["git", "diff-index", "--quiet", "HEAD", "--"], cwd=repo)
    if dirty == 0:
        subprocess.call(
            ["git", "pull", "--ff-only", "--quiet", "origin"], cwd=repo
        )
    else:
        print("(skip pull: working tree con cambios locales)", file=sys.stderr)


def read_state() -> str:
    if not Path(config.STATE_FILE).exists():
        return ""
    return Path(config.STATE_FILE).read_text().strip()


def write_state(sha: str) -> None:
    Path(config.STATE_FILE).write_text(sha + "\n")


def list_new_commits(repo: str, last_seen: str) -> list[Entrega]:
    """Devuelve commits nuevos en orden cronológico (más viejo primero)."""
    head = run(["git", "rev-parse", "origin/master"], cwd=repo)
    if not last_seen:
        # Primera corrida sin estado: solo el HEAD.
        rev_range = head
    else:
        rev_range = f"{last_seen}..{head}"

    raw = subprocess.check_output(
        ["git", "log", "--reverse", "--format=%H%x09%s", rev_range],
        cwd=repo,
        text=True,
    )

    out: list[Entrega] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        sha, _, subject = line.partition("\t")
        m = COMMIT_RE.match(subject)
        if not m:
            print(f"WARN: commit ignorado (formato no reconocido): {sha} {subject!r}",
                  file=sys.stderr)
            continue
        emoji, entrega, padrones = m.group(1), m.group(2).lower(), m.group(3)
        out.append(
            Entrega(
                ok=(emoji == ":heavy_check_mark:"),
                entrega=entrega,
                padrones=padrones.split("_"),
                sha=sha,
            )
        )
    return out, head


def column_letter(idx_zero_based: int) -> str:
    # 0 → A, 25 → Z, 26 → AA …
    n = idx_zero_based + 1
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def apply_updates(entregas: list[Entrega]) -> dict:
    """Aplica las actualizaciones a la hoja Notas.

    Devuelve dict con stats: actualizados, salteados, ignorados, etc.
    """
    spreadsheet = open_spreadsheet()
    notas = spreadsheet.worksheet(config.SHEET_NOTAS)

    rows = notas.get_all_values()
    if not rows:
        raise RuntimeError("Hoja Notas vacía")

    headers = rows[0]
    try:
        idx_padron = headers.index("Padrón")
    except ValueError:
        raise RuntimeError("Columna 'Padrón' no encontrada en Notas")

    # padron → fila (1-based en la planilla; +1 por header => i+2 si i es índice 0-based del data).
    padron_to_row = {}
    for i, row in enumerate(rows[1:], start=2):
        if idx_padron < len(row) and row[idx_padron].strip():
            padron_to_row[row[idx_padron].strip()] = (i, row)

    # Ranking de prioridad final por celda. Si el commit más nuevo dice "E",
    # querés "E" aunque hayan pasado WIPs intermedios. Como recorremos
    # cronológico (oldest first) y solo guardamos el ÚLTIMO valor calculado
    # por celda, naturalmente prevalece el más reciente.
    pending: dict[tuple[int, int], tuple[str, str]] = {}  # (row, col) → (new_value, current_value)
    stats = {
        "commits_procesados": 0,
        "commits_padron_no_encontrado": 0,
        "commits_columna_no_encontrada": 0,
        "celdas_actualizadas": 0,
        "celdas_salteadas_no_vacias": 0,
        "celdas_no_op_wip": 0,
    }
    log_actualizadas = []

    for ent in entregas:
        stats["commits_procesados"] += 1
        col_name = config.ENTREGA_TO_COLUMN.get(ent.entrega)
        if col_name is None:
            print(f"WARN: entrega '{ent.entrega}' sin mapeo en ENTREGA_TO_COLUMN ({ent.sha})",
                  file=sys.stderr)
            stats["commits_columna_no_encontrada"] += 1
            continue
        try:
            col_idx = headers.index(col_name)
        except ValueError:
            print(f"WARN: columna '{col_name}' no existe en Notas ({ent.sha})",
                  file=sys.stderr)
            stats["commits_columna_no_encontrada"] += 1
            continue

        new_value = "E" if ent.ok else "WIP"

        for padron in ent.padrones:
            entry = padron_to_row.get(padron)
            if entry is None:
                print(f"WARN: padrón {padron} no encontrado en Notas ({ent.sha})",
                      file=sys.stderr)
                stats["commits_padron_no_encontrado"] += 1
                continue
            row_num, row_data = entry
            current = row_data[col_idx].strip() if col_idx < len(row_data) else ""

            if current not in ("", "NE", "WIP"):
                stats["celdas_salteadas_no_vacias"] += 1
                continue
            if current == "WIP" and new_value == "WIP":
                stats["celdas_no_op_wip"] += 1
                continue

            pending[(row_num, col_idx)] = (new_value, current)

    if pending:
        body = []
        for (row_num, col_idx), (new_value, _current) in pending.items():
            body.append({
                "range": f"{column_letter(col_idx)}{row_num}",
                "values": [[new_value]],
            })
            log_actualizadas.append({
                "row": row_num,
                "col": col_name_at(headers, col_idx),
                "value": new_value,
            })
        notas.batch_update(body, value_input_option="USER_ENTERED")
        stats["celdas_actualizadas"] = len(pending)

    return {"stats": stats, "actualizadas": log_actualizadas}


def col_name_at(headers, col_idx):
    if col_idx < len(headers):
        return headers[col_idx]
    return f"col{col_idx}"


def main():
    git_pull(config.ENTREGAS_REPO)
    last_seen = read_state()
    entregas, head = list_new_commits(config.ENTREGAS_REPO, last_seen)
    print(f"last_seen={last_seen[:10] or '(vacío)'} head={head[:10]} commits_nuevos={len(entregas)}")

    if not entregas:
        # Igual avanzamos el cursor para que match el HEAD nuevo (puede haber
        # commits ignorados por formato).
        write_state(head)
        result = {"stats": {"commits_procesados": 0}, "actualizadas": []}
    else:
        result = apply_updates(entregas)
        write_state(head)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

#!/bin/bash
# Notas-monitor: corre 1) update_entregas para sincronizar la planilla con
# los commits nuevos en entregas/, y 2) check_deadlines para listar alumnos
# que incumplen fechas clave hoy. Avisa por notificación macOS.
#
# Logs:    monitor/logs/run_<fecha>.log
# Reportes: monitor/reports/run_<fecha>.{entregas,deadlines}.json

set -euo pipefail

ROOT="/Users/mbuchwald/Documents/Algoritmos"
MONITOR="$ROOT/notas/monitor"
LOG_DIR="$MONITOR/logs"
REPORTS="$MONITOR/reports"

PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
export PATH

mkdir -p "$LOG_DIR" "$REPORTS"

FECHA="$(date +%Y-%m-%d)"
LOG="$LOG_DIR/run_${FECHA}.log"
exec >>"$LOG" 2>&1

echo "==== notas-monitor run @ $(date -Iseconds) ===="

cd "$MONITOR"

PY="$MONITOR/.venv/bin/python"
if [ ! -x "$PY" ]; then
  PY="python3"
fi

ENTREGAS_OUT="$REPORTS/run_${FECHA}.entregas.json"
DEADLINES_OUT="$REPORTS/run_${FECHA}.deadlines.json"

set +e
"$PY" update_entregas.py >"$ENTREGAS_OUT.tmp" 2>&1
RC_E=$?
set -e
mv "$ENTREGAS_OUT.tmp" "$ENTREGAS_OUT"
echo "---- update_entregas rc=$RC_E ----"
cat "$ENTREGAS_OUT"

set +e
"$PY" check_deadlines.py >"$DEADLINES_OUT.tmp" 2>>"$LOG"
RC_D=$?
set -e
mv "$DEADLINES_OUT.tmp" "$DEADLINES_OUT"
echo "---- check_deadlines rc=$RC_D ----"
cat "$DEADLINES_OUT"

# Resumen para la notificación.
SUMMARY=$("$PY" - "$ENTREGAS_OUT" "$DEADLINES_OUT" <<'PY'
import json, sys
ent_path, dl_path = sys.argv[1], sys.argv[2]

def safe_json(p):
    try:
        # update_entregas mezcla logs con JSON; quedarse con la última llave abierta '{'.
        text = open(p).read()
        start = text.rfind("\n{")
        if start == -1 and text.lstrip().startswith("{"):
            return json.loads(text)
        if start != -1:
            return json.loads(text[start+1:])
    except Exception:
        return None
    return None

ent = safe_json(ent_path) or {}
dl  = safe_json(dl_path) or {}

stats = (ent.get("stats") or {})
upd = stats.get("celdas_actualizadas", 0)

findings = dl.get("findings") or []
total_alu = sum(len(f.get("alumnos", [])) for f in findings)

parts = []
parts.append(f"{upd} celda(s) actualizadas")
if findings:
    reglas = ", ".join(f["regla"] for f in findings[:3])
    parts.append(f"{total_alu} alumno(s) en riesgo: {reglas}")
else:
    parts.append("sin incumplimientos")

print(" | ".join(parts))
PY
)
echo "summary: $SUMMARY"

short=$(printf '%s' "$SUMMARY" | tr '\n' ' ' | cut -c1-280)
/usr/bin/osascript <<EOF
display notification "$short" with title "Notas-monitor — actualización diaria" sound name "Glass"
EOF
echo "notificación enviada"

echo "==== fin @ $(date -Iseconds) ===="

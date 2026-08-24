"""Configuración del notas-monitor.

Editar a mano cuando rote el cuatrimestre o el path del service account.
"""

import os

# Planilla del cuatrimestre actual.
SPREADSHEET_KEY = "1-3TLDzXwYomfqfJFiLzgQsBWiDx9l3XSpLGRDVrk-iM"

# Service account JSON con acceso de edición a la planilla.
# Editar a mano si se mueve el archivo.
SERVICE_ACCOUNT_JSON = os.path.expanduser("~/notas-service-account.json")

# Repo de entregas (clon local).
ENTREGAS_REPO = "/Users/mbuchwald/Documents/Algoritmos/entregas"

# Directorio del monitor.
MONITOR_DIR = "/Users/mbuchwald/Documents/Algoritmos/notas/monitor"
STATE_FILE = os.path.join(MONITOR_DIR, "last_seen_commit.txt")
REPORTS_DIR = os.path.join(MONITOR_DIR, "reports")

# Hojas.
SHEET_NOTAS = "Notas"
SHEET_ALUMNOS = "DatosAlumnos"
SHEET_CALENDARIO = "Calendario"
SHEET_REPOS = "Repos"

# Equipo de GitHub al que hay que asegurar permisos de Admin en cada repo de
# alumno (ver github_invite.py). Se asume que vive en la misma organización
# que el repo (owner/repo de la columna "Repo" de la hoja Repos).
GITHUB_TEAM_SLUG = "algorw-20b"

# Mapeo entrega-en-commit → header de columna en Notas.
# Capitalize directo, salvo TPs y casos donde el header difiere.
ENTREGA_TO_COLUMN = {
    "tp0": "TP0",
    "tp1": "TP1",
    "tp2": "TP2",
    "tp3": "TP3",
    "pila": "Pila",
    "cola": "Cola",
    "lista": "Lista",
    "hash": "Hash",
    "abb": "Abb",
    "heap": "Heap",
}

# Reglas de fechas clave.
# Cada regla es (texto-en-Calendario, función-de-evaluación).
# La función-de-evaluación se define en check_deadlines.py.
DEADLINE_RULES = [
    "Completar formulario de inicio",
    "TODO OK TP0 para condicionales y cambios de curso",
    "TODO OK TP0",
    "TODO OK Pila y Cola",
    "Promoción: TODO OK TP1",
    "TODO OK TP1",
    "TODO OK Lista",
    "Promoción: TODO OK Hash",
    "Promoción: TODO OK ABB y Heap",
    "TODO OK Hash, ABB y Heap",
    "Promoción: TODO OK TP2",
    "TODO OK TP2",
    "TODO OK TP3",
]

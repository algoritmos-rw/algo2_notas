from __future__ import annotations
from re import split

import gspread

from typing import TYPE_CHECKING, Tuple, Callable
from dataclasses import dataclass

if TYPE_CHECKING:
    from typing import Tuple, List
    from gspread.models import Worksheet
    from ..api.google_credentials import GoogleCredentials


@dataclass
class Grupo:
    numero: int
    corrector: str
    emails: Tuple[str, str]
    nota: str
    detalle: str


class NotasRepository:
    # Constantes
    SHEET_ALUMNOS: str = "Listado"
    COL_EMAIL: str = "E-Mail"
    COL_PADRON: str = "Padrón"

    SHEET_NOTAS: str = "Alumnos - Notas"
    RANGO_NOTAS: str = "1:26"

    SHEET_DEVOLUCIONES: str = "Devoluciones"
    PREFIJO_RANGO_DEVOLUCIONES: str = "emails"
    RANGO_EMAILS: str = f"{PREFIJO_RANGO_DEVOLUCIONES}Grupos"

    def __init__(self, spreadsheet_key: str, credentials: GoogleCredentials) -> None:
        self._spreadsheet_key = spreadsheet_key
        self._google_credentials = credentials

    def _get_spreadsheet(self):
        client = gspread.authorize(
            self._google_credentials.get_credenciales_spreadsheet())
        spreadsheet = client.open_by_key(self._spreadsheet_key)
        return spreadsheet

    def _get_sheet(self, worksheet_name: str) -> Worksheet:
        """Devuelve un objeto gspread.Worksheet.
        Utiliza la constante global SPREADSHEET_KEY.
        """
        spreadsheet = self._get_spreadsheet()
        return spreadsheet.worksheet(worksheet_name)

    def verificar(self, padron_web: str, email_web: str) -> bool:
        """Verifica que hay un alumno con el padrón y e-mail indicados.
        """
        alumnos = self._get_sheet(self.SHEET_ALUMNOS)

        for alumno in alumnos.get_all_records():
            email = alumno.get(self.COL_EMAIL, "").strip()
            padron = str(alumno.get(self.COL_PADRON, ""))

            if not email or not padron:
                continue

            if (padron.lower() == padron_web.lower() and
                    email.lower() == email_web.lower()):
                return True

        return False

    def notas(self, padron: str) -> List[Tuple[str, str]]:
        notas = self._get_sheet(self.SHEET_NOTAS)
        filas = notas.get_values(self.RANGO_NOTAS, major_dimension="COLUMNS")
        headers = filas.pop(0)
        idx_padron = headers.index(self.COL_PADRON)

        for alumno in filas:
            if padron.lower() == alumno[idx_padron].lower():
                return list(zip(headers, alumno))

        raise IndexError(f"Padrón {padron} no encontrado")

    def ejercicios(self, ejercicio: str) -> List[Grupo]:
        sheet = self._get_sheet(self.SHEET_DEVOLUCIONES)
        exercise_named_interval = self.PREFIJO_RANGO_DEVOLUCIONES + \
            ''.join([word.capitalize() for word in ejercicio.split()])

        emails, correcciones = sheet.batch_get(
            [f"{self.RANGO_EMAILS}", exercise_named_interval], major_dimension="COLUMNS")

        headers = [*emails.pop(0), *correcciones.pop(0)]
        headers_len = len(headers)
        amount_of_students = len(emails)

        raw_data = [[
            *emails[i],
            *correcciones[i],
            *[""] * (headers_len - len(emails[i]) - len(correcciones[i]))
        ] for i in range(amount_of_students)]

        grupos = [
            Grupo(
                numero=g[0],
                emails=g[1].split(","),
                nota=g[2],
                corrector=g[3],
                detalle=g[4]
            )
            for g in raw_data
        ]

        return grupos

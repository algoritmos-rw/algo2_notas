from __future__ import annotations
import collections

import gspread

from typing import TYPE_CHECKING, Tuple, Callable, NamedTuple
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
    correcciones: str


class NotasRepository:
    # Constantes
    SHEET_ALUMNOS: str = "Listado"
    COL_EMAIL: str = "E-Mail"
    COL_PADRON: str = "Padrón"

    SHEET_NOTAS: str = "Alumnos - Notas"
    RANGO_NOTAS: str = "1:26"

    def __init__(self, spreadsheet_key: str, credentials: GoogleCredentials) -> None:
        self._spreadsheet_key = spreadsheet_key
        self._google_credentials = credentials

    def _get_sheet(self, worksheet_name: str) -> Worksheet:
        """Devuelve un objeto gspread.Worksheet.
        Utiliza la constante global SPREADSHEET_KEY.
        """
        client = gspread.authorize(
            self._google_credentials.get_credenciales_spreadsheet())
        spreadsheet = client.open_by_key(self._spreadsheet_key)
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

    def _get_groups_from_cell_range(self, rango: List[str]):
        first_cell = rango[0]
        last_cell = rango[-1]

        columns = last_cell.col - first_cell.col + 1

        matrix_to_list_index: Callable[[int, int],
                                       int] = lambda row, col: row * columns + col
        valores = [i.value.strip() for i in rango]
        grupos = []
        for i in range(columns // 2):
            col = 2 * i
            grupo = Grupo(
                numero=int(valores[matrix_to_list_index(0, col)]),
                corrector=valores[matrix_to_list_index(0, col + 1)],
                emails=(
                    valores[matrix_to_list_index(1, col)],
                    valores[matrix_to_list_index(1, col + 1)],
                ),
                nota=valores[matrix_to_list_index(2, col)],
                correcciones=valores[matrix_to_list_index(3, col)]
            )
            grupos.append(grupo)

        return grupos

    def ejercicios(self, ejercicio: str) -> List[Grupo]:
        sheet = self._get_sheet(ejercicio)
        named_interval = "emails" + \
            ''.join([word.capitalize() for word in ejercicio.split()])
        rango = sheet.range(named_interval)

        return self._get_groups_from_cell_range(rango)

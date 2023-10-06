#!/usr/bin/env python3

import os
import gspread

import notas_oauth

# Constantes
COL_EMAIL = "Email"
COL_PADRON = "Padrón"

SHEET_NOTAS = "Notas"
SHEET_ALUMNOS = "DatosAlumnos"

# Configuración externa.
SPREADSHEET_KEY = os.environ["NOTAS_SPREADSHEET_KEY"]


def get_sheet(worksheet_name):
    """Devuelve un objeto gspread.Worksheet.

    Utiliza la constante global SPREADSHEET_KEY.
    """
    client = gspread.authorize(notas_oauth.get_credenciales_spreadsheet())
    spreadsheet = client.open_by_key(SPREADSHEET_KEY)
    return spreadsheet.worksheet(worksheet_name)


def verificar(padron_web, email_web):
    """Verifica que hay un alumno con el padrón y e-mail indicados.
    """
    alumnos = get_sheet(SHEET_ALUMNOS)

    for alumno in alumnos.get_all_records():
        email = alumno.get(COL_EMAIL, "").strip()
        padron = str(alumno.get(COL_PADRON, ""))

        if not email or not padron:
            continue

        if (padron.lower() == padron_web.lower() and
            email.lower() == email_web.lower()):
            return True

    return False


def eliminar_columnas_comentadas(headers, alumno):
    comentadas = []
    for i in range(len(headers)):
        if headers[i][0] == "_":
            comentadas.append(i)
    cant_ya_eliminadas = 0

    resul_headers = headers[:]
    resul_alumno = alumno[:]
    for col_comentada in comentadas:
        resul_headers.pop(col_comentada - cant_ya_eliminadas)
        resul_alumno.pop(col_comentada - cant_ya_eliminadas)
        cant_ya_eliminadas += 1
    return resul_headers, resul_alumno



def notas(padron):
    notas = get_sheet(SHEET_NOTAS)
    filas = notas.get_all_values()
    headers = filas.pop(0)
    idx_padron = headers.index(COL_PADRON)

    for alumno in filas:
        if padron.lower() == alumno[idx_padron].lower():
            headers_scom, alumno_scom = eliminar_columnas_comentadas(headers, alumno)
            return zip(headers_scom, alumno_scom)

    raise IndexError("Padrón {} no encontrado".format(padron))


if __name__ == "__main__":
    print(verificar("942039", "aaa"))

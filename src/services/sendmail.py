#!/usr/bin/env python3
from __future__ import annotations

import base64
import smtplib
from abc import ABC
from email.mime.text import MIMEText

from api.google_credentials import GoogleCredentials

SendmailException = smtplib.SMTPException


class EmailSender(ABC):
    template = None
    subject = None

    def __init__(self, google_credentials: GoogleCredentials, from_name: str, from_email: str) -> None:
        self._account = from_email
        self._google_credentials = google_credentials
        self._encoded_from_email = "{} <{}>".format(from_name, from_email)

    def _encoded_credentials(self):
        creds = self._google_credentials.get_credenciales_email()
        xoauth2_tok = f"user={self._account}\1auth=Bearer {creds.access_token}\1\1".encode(
            "utf-8")

        return xoauth2_tok

    def send_mail(self, to_addr: str, **kwargs) -> None:
        # Sanity checks
        if self.template == None or self.subject == None:
            raise Exception("No template or subject given")

        # Create msg
        msg = MIMEText(self.template.format(**kwargs), _charset="utf-8")
        msg["Subject"] = self.subject
        msg["From"] = self._encoded_from_email
        msg["To"] = to_addr

        # Connect to SMTP server
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.docmd("AUTH", "XOAUTH2 " +
                     base64.b64encode(self._encoded_credentials()).decode("utf-8"))

        # Send mail
        server.sendmail(self._account, to_addr, msg.as_string())

        # Close connection to SMTP
        server.close()


class SigninEmailSender(EmailSender):
    subject = "Enlace para consultar las notas"
    template = """
Este es el link para consultar tus notas:
{enlace}

Nota: El enlace generado es único para tu padrón. No lo compartas con nadie (a menos
que quieras que otros puedan ver tus notas).

-- 
Recibiste este mensaje porque te inscribiste en el sistema de consulta de
notas de {curso}. Si no es así, te pedimos disculpas y por favor ingorá este mail.
"""

    def send_mail(self, to_addr: str, curso: str, enlace: str) -> None:
        return super().send_mail(to_addr, curso=curso, enlace=enlace)


class EjercicioEmailSender(EmailSender):
    template = """Mail para el grupo {grupo}.

Corrector: {corrector}.

Hola, este mail es para darles la devolución del ejercicio {ejercicio}, su nota es {nota}.

{correcciones}
-- 
Recibiste este mensaje porque te inscribiste en el sistema de consulta de
notas de {curso}. Si no es así, te pedimos disculpas y por favor ingorá este mail.
"""

    def send_mail(self, to_addr: str, curso: str, ejercicio: str, grupo: int, corrector: str, nota: float, correcciones: str) -> None:
        self.subject = f"Correccion de notas ejercicio {ejercicio} - Grupo {grupo}"

        return super().send_mail(
            to_addr, curso=curso, ejercicio=ejercicio,
            grupo=grupo, corrector=corrector, nota=nota,
            correcciones=correcciones)

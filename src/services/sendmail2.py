#!/usr/bin/env python3
from __future__ import annotations

import base64
import smtplib
from email.mime.text import MIMEText
from jinja2 import Environment

from api.google_credentials import GoogleCredentials

SendmailException = smtplib.SMTPException


class EmailSender:
    def __init__(self, jinja2_env: Environment, google_credentials: GoogleCredentials, from_name: str, from_email: str) -> None:
        self._account = from_email
        self._google_credentials = google_credentials
        self._encoded_from_email = "{} <{}>".format(from_name, from_email)
        self._jinja2_env = jinja2_env

    def _encoded_credentials(self):
        creds = self._google_credentials.get_credenciales_email()
        xoauth2_tok = f"user={self._account}\1auth=Bearer {creds.access_token}\1\1".encode(
            "utf-8")

        return xoauth2_tok

    def send_mail(self, template_path: str, subject: str, to_addr: str, **kwargs) -> None:
        template = self._jinja2_env.get_template(template_path)

        # Create msg
        msg = MIMEText(template.render(**kwargs), _charset="utf-8")
        msg["Subject"] = subject
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
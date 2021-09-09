#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os

import flask
import itsdangerous

from webargs import fields
from webargs.flaskparser import use_args

from forms.authentication_form import AuthenticationForm

from api.google_credentials import GoogleCredentials
from repositories.notas_repository import NotasRepository
from services.sendmail import SendmailException, NotasEmailSender, EjercicioEmailSender

# App configuration
APP_TITLE = f'{os.environ["NOTAS_COURSE_NAME"]} - Consulta de Notas'
SECRET_KEY = os.environ["NOTAS_SECRET"]
assert SECRET_KEY
TEMPLATES_DIR = "../templates"

# Notas
SPREADSHEET_KEY = os.environ["NOTAS_SPREADSHEET_KEY"]

# Google credentials
CLIENT_ID = os.environ["NOTAS_OAUTH_CLIENT"]
CLIENT_SECRET = os.environ["NOTAS_OAUTH_SECRET"]
OAUTH_REFRESH = os.environ["NOTAS_REFRESH_TOKEN"]
SERVICE_ACCOUNT_JSON = os.environ["NOTAS_SERVICE_ACCOUNT_JSON"]

# Email
COURSE = os.environ['NOTAS_COURSE_NAME']
ACCOUNT = os.environ['NOTAS_ACCOUNT']

signer = itsdangerous.URLSafeSerializer(SECRET_KEY)

app = flask.Flask(__name__)
app.secret_key = SECRET_KEY
app.config.title = APP_TITLE
app.template_folder = TEMPLATES_DIR

google_credentials = GoogleCredentials(
    SERVICE_ACCOUNT_JSON, CLIENT_ID, CLIENT_SECRET, OAUTH_REFRESH)
notas = NotasRepository(SPREADSHEET_KEY, google_credentials)
notas_email_sender = NotasEmailSender(google_credentials, COURSE, ACCOUNT)
ejercicios_email_sender = EjercicioEmailSender(
    google_credentials, COURSE, ACCOUNT)

# Endpoints


@app.route("/", methods=('GET', 'POST'))
def index():
    """Sirve la página de solicitud del enlace.
    """
    form = AuthenticationForm()

    if form.validate_on_submit():
        padron = form.normalized_padron()
        email = form.normalized_email()

        if not notas.verificar(padron, email):
            flask.flash(
                "La dirección de mail no está asociada a ese padrón", "danger")
        else:
            try:
                notas_email_sender.sendmail(
                    email, curso=COURSE, enlace=genlink(padron))
            except SendmailException as e:
                return flask.render_template("error.html", message=str(e))
            else:
                return flask.render_template("email_sent.html", email=email)

    return flask.render_template("index.html", form=form)


@app.errorhandler(422)
def bad_request(err):
    """Se invoca cuando falla la validación de la clave.
    """
    return flask.render_template("error.html", message="Clave no válida")


def _clave_validate(clave) -> bool:
    # Needed because URLSafeSerializer does not have a validate().
    try:
        return bool(signer.loads(clave))
    except itsdangerous.BadSignature:
        return False


@app.route("/consultar")
@use_args({"clave": fields.Str(required=True, validate=_clave_validate)})
def consultar(args):
    try:
        notas_alumno = notas.notas(signer.loads(args["clave"]))
    except IndexError as e:
        return flask.render_template("error.html", message=str(e))
    else:
        return flask.render_template("result.html", items=notas_alumno)


@app.route("/test", methods=['GET'])
def test_route():
    """Modo de uso: http://ip:5000/test?email=test@email.com """

    email = flask.request.args.get("email")
    corrector = "Fulano de tal"
    correcciones = """¡Felicitaciones!
El código en general está muy prolijo, y los tests están bien. Hay un par de asserts más que se podían haber hecho después de cada paso pero los agregué y pasaron así que está todo bien. Igualmente intenten poner todos los asserts intermedios porque si no les puede pasar que códigos incorrectos los pasen. Les dejo dos cositas:
La primera es que entre las dos cintas, y entre los dos extractores, les quedó prácticamente todo el código repetido. Lo correcto era usar prototipado para poder reciclar la implementación de la CintaA para la B, y del extractor de hierro en el de carbón (esta no baja puntos).
La segunda, que es un detalle, hay algunas implementaciones donde los nombres de los colaboradores no indican el rol que tiene que cumplir dentro de la implementación. Por ejemplo: el mensaje “agregar: anArray” sería más declarativo si se llamara “agregar: contenido”, por ejemplo. No tengan miedo de ser un poquito redundantes, a veces es preferible, o es un indicador de que el nombre del mensaje está mal. Por ejemplo: “agregarContenido: contenido” es redundante por esta razón.
¡Hasta la próxima entrega!
"""

    try:
        ejercicios_email_sender.send_mail(
            to_addr=email, curso=COURSE, ejercicio="Factorio",
            grupo=22, corrector=corrector, nota=8, correcciones=correcciones)
    except SendmailException as e:
        return flask.render_template("error.html", message=str(e))
    else:
        return flask.render_template("email_sent.html", email=email)


def genlink(padron: str) -> str:
    """Devuelve el enlace de consulta para un padrón.
    """
    signed_padron = signer.dumps(padron)
    return flask.url_for("consultar", clave=signed_padron, _external=True)


if __name__ == "__main__":
    app.run(debug=True)

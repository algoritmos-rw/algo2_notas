from os import name
from flask import request, make_response
from functools import wraps

class WebAdminAuthentication:

    def __init__(self, admin_username: str, admin_password: str) -> None:
        self.admin_username = admin_username
        self.admin_password = admin_password

    def _authenticate(self, username: str, password: str) -> bool:
        """ Return True if user sould be permited to access """

        return username == self.admin_username and password == self.admin_password

    def auth_required(self, f):
        @wraps(f)
        def decorated(*args, **kwargs):
            auth = request.authorization
            if auth and self._authenticate(auth.username, auth.password):
                return f(*args, **kwargs)

            return make_response("No se pudo verificar el login!", 401, {'WWW-authenticate': 'Basic realm="Login required"'})

        return decorated

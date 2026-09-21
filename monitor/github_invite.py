#!/Users/mbuchwald/Documents/Algoritmos/notas/monitor/.venv/bin/python3
"""Invita a los alumnos a su repositorio de GitHub y asegura permisos del equipo docente.

Recorre la hoja `Repos` (columna "Repo" = owner/repo del repositorio
individual, o columna "Repo2" = owner/repo del repositorio grupal si se pasa
--grupal) y, para cada repositorio que exista en GitHub:

  1. Busca el usuario de GitHub del alumno en `DatosAlumnos` (columna F, por
     Legajo/Padrón).
  2. Si el alumno ya es colaborador, o ya tiene una invitación pendiente, no
     hace nada. Si no, le envía una invitación con permiso "Triage".
  3. Revisa que el equipo GITHUB_TEAM_SLUG (ver config.py) tenga permiso Admin
     sobre el repo. Si no lo tiene, se lo agrega.

Repos inexistentes en GitHub se ignoran silenciosamente (no se crean).

Con --grupal se procesa el repositorio grupal (columna "Repo2") en lugar del
individual. Como cada integrante del grupo comparte el mismo repositorio
grupal, el mismo repo aparece una vez por alumno del grupo; no es un problema,
simplemente se procesa (y se invita/verifica) más de una vez.

Requiere credenciales de un usuario con permisos de administración sobre la
organización. Se piden por stdin en cada corrida (usuario + token) y NUNCA se
guardan en disco ni se pasan como argumento de línea de comandos.

Usar --dry-run para ver qué haría el script sin modificar nada en GitHub.
"""

from __future__ import annotations

import argparse
import getpass
import sys
import time
from dataclasses import dataclass, field

import requests

import config
from sheets_client import open_spreadsheet

GITHUB_API = "https://api.github.com"


# --- Credenciales --------------------------------------------------------------


def prompt_credentials() -> requests.Session:
    print("Credenciales de administrador de GitHub (no se guardan en disco).",
          file=sys.stderr)
    username = input("Usuario de GitHub: ").strip()
    token = getpass.getpass("Token/Password de GitHub: ")

    session = requests.Session()
    session.auth = (username, token)
    session.headers.update({
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })

    resp = session.get(f"{GITHUB_API}/user")
    if resp.status_code != 200:
        raise SystemExit(
            f"No se pudo autenticar contra GitHub (HTTP {resp.status_code}): "
            f"{resp.text[:300]}"
        )
    who = resp.json().get("login", "?")
    print(f"Autenticado como {who}.", file=sys.stderr)
    return session


# --- Llamadas a la API de GitHub, con backoff simple ante rate limit -----------


def gh(session: requests.Session, method: str, path: str, **kwargs) -> requests.Response:
    url = f"{GITHUB_API}{path}"
    for attempt in range(3):
        resp = session.request(method, url, **kwargs)
        if resp.status_code == 403 and "rate limit" in resp.text.lower():
            wait = int(resp.headers.get("Retry-After", "5"))
            print(f"  (rate limit, espero {wait}s...)", file=sys.stderr)
            time.sleep(wait)
            continue
        return resp
    return resp


def repo_exists(session: requests.Session, owner: str, repo: str) -> bool:
    return gh(session, "GET", f"/repos/{owner}/{repo}").status_code == 200


def is_collaborator(session: requests.Session, owner: str, repo: str, username: str) -> bool:
    return gh(session, "GET", f"/repos/{owner}/{repo}/collaborators/{username}").status_code == 204


def has_pending_invitation(session: requests.Session, owner: str, repo: str, username: str) -> bool:
    resp = gh(session, "GET", f"/repos/{owner}/{repo}/invitations", params={"per_page": 100})
    if resp.status_code != 200:
        return False
    username_lower = username.lower()
    return any(
        (inv.get("invitee") or {}).get("login", "").lower() == username_lower
        for inv in resp.json()
    )


def send_invitation(session: requests.Session, owner: str, repo: str, username: str) -> bool:
    resp = gh(
        session, "PUT", f"/repos/{owner}/{repo}/collaborators/{username}",
        json={"permission": "triage"},
    )
    return resp.status_code in (201, 204)


def team_has_admin(session: requests.Session, org: str, team_slug: str, owner: str, repo: str) -> bool:
    resp = gh(session, "GET", f"/orgs/{org}/teams/{team_slug}/repos/{owner}/{repo}")
    if resp.status_code != 200:
        return False
    return bool((resp.json().get("permissions") or {}).get("admin"))


def grant_team_admin(session: requests.Session, org: str, team_slug: str, owner: str, repo: str) -> bool:
    resp = gh(
        session, "PUT", f"/orgs/{org}/teams/{team_slug}/repos/{owner}/{repo}",
        json={"permission": "admin"},
    )
    return resp.status_code in (204, 200)


# --- Carga de planilla ----------------------------------------------------------


@dataclass
class Stats:
    repos_totales: int = 0
    repos_inexistentes: int = 0
    sin_usuario_github: int = 0
    ya_tenia_acceso: int = 0
    invitacion_ya_pendiente: int = 0
    invitaciones_enviadas: int = 0
    invitaciones_fallidas: int = 0
    equipo_ya_admin: int = 0
    equipo_actualizado: int = 0
    equipo_actualizacion_fallida: int = 0
    detalle: list = field(default_factory=list)


def load_padron_to_github() -> dict[str, str]:
    sp = open_spreadsheet()
    rows = sp.worksheet(config.SHEET_ALUMNOS).get_all_values()
    headers = rows[0]
    idx_padron = headers.index("Padrón")
    idx_github = headers.index("Github")

    out = {}
    for row in rows[1:]:
        if idx_padron >= len(row) or not row[idx_padron].strip():
            continue
        padron = row[idx_padron].strip()
        github_user = row[idx_github].strip() if idx_github < len(row) else ""
        if github_user:
            out[padron] = github_user
    return out


def load_repos(grupal: bool = False) -> list[tuple[str, str]]:
    """Devuelve lista de (padron, owner/repo) tal como figuran en la hoja Repos.

    Si grupal=True, usa la columna "Repo2" (repositorio grupal) en vez de
    "Repo" (repositorio individual).
    """
    sp = open_spreadsheet()
    rows = sp.worksheet(config.SHEET_REPOS).get_all_values()
    headers = rows[0]
    idx_padron = headers.index("Legajo")
    idx_repo = headers.index("Repo2" if grupal else "Repo")

    out = []
    for row in rows[1:]:
        if idx_padron >= len(row) or not row[idx_padron].strip():
            continue
        if idx_repo >= len(row) or not row[idx_repo].strip():
            continue
        out.append((row[idx_padron].strip(), row[idx_repo].strip()))
    return out


# --- Main ------------------------------------------------------------------------


def process_repo(session, padron, repo_full, github_user, dry_run, stats: Stats):
    if "/" not in repo_full:
        print(f"[{padron}] WARN: '{repo_full}' no tiene forma owner/repo, salteo", file=sys.stderr)
        return
    owner, repo = repo_full.split("/", 1)

    if not repo_exists(session, owner, repo):
        stats.repos_inexistentes += 1
        return

    stats.repos_totales += 1
    print(f"[{padron}] github.com/{repo_full}")

    if not github_user:
        print(f"  sin usuario de GitHub en DatosAlumnos, salteo invitación")
        stats.sin_usuario_github += 1
    elif is_collaborator(session, owner, repo, github_user):
        print(f"  {github_user} ya tiene acceso")
        stats.ya_tenia_acceso += 1
    elif has_pending_invitation(session, owner, repo, github_user):
        print(f"  {github_user} ya tiene invitación pendiente")
        stats.invitacion_ya_pendiente += 1
    else:
        if dry_run:
            print(f"  [dry-run] invitaría a {github_user} (Triage)")
            stats.invitaciones_enviadas += 1
        elif send_invitation(session, owner, repo, github_user):
            print(f"  invitación enviada a {github_user} (Triage)")
            stats.invitaciones_enviadas += 1
        else:
            print(f"  ERROR enviando invitación a {github_user}")
            stats.invitaciones_fallidas += 1

    if team_has_admin(session, owner, config.GITHUB_TEAM_SLUG, owner, repo):
        stats.equipo_ya_admin += 1
    else:
        if dry_run:
            print(f"  [dry-run] agregaría admin a equipo {config.GITHUB_TEAM_SLUG}")
            stats.equipo_actualizado += 1
        elif grant_team_admin(session, owner, config.GITHUB_TEAM_SLUG, owner, repo):
            print(f"  equipo {config.GITHUB_TEAM_SLUG} actualizado a Admin")
            stats.equipo_actualizado += 1
        else:
            print(f"  ERROR actualizando permisos del equipo {config.GITHUB_TEAM_SLUG}")
            stats.equipo_actualizacion_fallida += 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                         help="No modifica nada en GitHub, solo muestra qué haría")
    parser.add_argument("-g", "--grupal", action="store_true",
                         help="Procesa el repositorio grupal (columna Repo2) en vez del individual")
    args = parser.parse_args()

    session = prompt_credentials()

    padron_to_github = load_padron_to_github()
    repos = load_repos(grupal=args.grupal)
    print(f"{len(repos)} repos en la hoja, {len(padron_to_github)} alumnos con usuario de GitHub",
          file=sys.stderr)

    stats = Stats()
    for padron, repo_full in repos:
        github_user = padron_to_github.get(padron, "")
        process_repo(session, padron, repo_full, github_user, args.dry_run, stats)

    print("\n==== resumen ====")
    print(f"repos existentes procesados:     {stats.repos_totales}")
    print(f"repos inexistentes (ignorados):  {stats.repos_inexistentes}")
    print(f"sin usuario de GitHub:           {stats.sin_usuario_github}")
    print(f"ya tenían acceso:                {stats.ya_tenia_acceso}")
    print(f"invitación ya pendiente:         {stats.invitacion_ya_pendiente}")
    print(f"invitaciones enviadas:           {stats.invitaciones_enviadas}")
    print(f"invitaciones fallidas:           {stats.invitaciones_fallidas}")
    print(f"equipo ya era admin:             {stats.equipo_ya_admin}")
    print(f"equipo actualizado a admin:      {stats.equipo_actualizado}")
    print(f"equipo actualización fallida:    {stats.equipo_actualizacion_fallida}")


if __name__ == "__main__":
    main()

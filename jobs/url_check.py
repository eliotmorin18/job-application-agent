"""
Contrôle d'une URL d'offre avant d'ouvrir le navigateur (utilisé par l'API).

Refuse tout ce qui n'est pas une page web publique : autres schémas que http(s) (file:,
javascript:, data:...), identifiants dans l'URL, localhost, noms locaux, adresses privées,
de bouclage, de lien local, réservées ou multicast — y compris quand un nom de domaine
pointe vers l'une d'elles.
"""

import ipaddress
import socket
from urllib.parse import urlsplit


class UnsafeUrlError(ValueError):
    """L'URL n'est pas celle d'une page web publique."""


LOCAL_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home", ".intranet", ".corp")


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%")[0])     # « fe80::1%en0 » : zone retirée
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def _check_host(host: str, port: int | None, resolve) -> None:
    """Lève UnsafeUrlError si le nom ou l'adresse ne désigne pas une machine publique."""

    try:                                             # adresse IP écrite directement dans l'URL
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if not _is_public(host):
            raise UnsafeUrlError(f"« {host} » est une adresse locale ou interne : seules les pages publiques sont acceptées.")
        return

    if host == "localhost" or host.endswith(LOCAL_SUFFIXES) or "." not in host:
        raise UnsafeUrlError(f"« {host} » est une adresse locale : seules les pages publiques sont acceptées.")

    try:
        addresses = {info[4][0] for info in resolve(host, port or None, proto=socket.IPPROTO_TCP)}
    except (socket.gaierror, UnicodeError, OSError):
        raise UnsafeUrlError(f"le site « {host} » est introuvable.")
    if not addresses:
        raise UnsafeUrlError(f"le site « {host} » est introuvable.")
    if not all(_is_public(address) for address in addresses):
        raise UnsafeUrlError(f"« {host} » désigne une adresse locale ou interne : seules les pages publiques sont acceptées.")


def check_public_url(url: str, resolve=socket.getaddrinfo) -> str:
    """Renvoie l'URL nettoyée si elle désigne une page web publique, sinon lève UnsafeUrlError."""

    if not isinstance(url, str) or not url.strip():
        raise UnsafeUrlError("l'URL de l'offre est vide.")
    url = url.strip()
    if len(url) > 2048:
        raise UnsafeUrlError("l'URL est trop longue.")

    parts = urlsplit(url)
    if parts.scheme.lower() not in ("http", "https"):
        raise UnsafeUrlError("seules les adresses web http:// ou https:// sont acceptées.")
    if parts.username or parts.password:
        raise UnsafeUrlError("l'URL ne doit pas contenir d'identifiants.")
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        raise UnsafeUrlError("l'URL ne contient pas de nom de site.")
    try:
        parts.port
    except ValueError:
        raise UnsafeUrlError("le port de l'URL est invalide.")

    _check_host(host, parts.port, resolve)
    return url

    if host == "localhost" or host.endswith(LOCAL_SUFFIXES) or "." not in host:
        raise UnsafeUrlError(f"« {host} » est une adresse locale : seules les pages publiques sont acceptées.")

    try:
        addresses = {info[4][0] for info in resolve(host, parts.port or None, proto=socket.IPPROTO_TCP)}
    except (socket.gaierror, UnicodeError, OSError):
        raise UnsafeUrlError(f"le site « {host} » est introuvable.")
    if not addresses:
        raise UnsafeUrlError(f"le site « {host} » est introuvable.")
    if not all(_is_public(address) for address in addresses):
        raise UnsafeUrlError(f"« {host} » désigne une adresse locale ou interne : seules les pages publiques sont acceptées.")

    return url


class PublicUrlGuard:
    """
    Filtre des requêtes du navigateur (jobs/read_job.py) : autorise seulement les adresses web
    publiques. Le résultat est mis en cache par nom de site pendant la lecture d'une offre.
    Les URL sans réseau (data:, blob:, about:) sont gérées par l'appelant.
    """

    def __init__(self, resolve=socket.getaddrinfo):
        self._resolve = resolve
        self._cache: dict[tuple, bool] = {}

    def allows(self, url: str) -> bool:
        try:
            parts = urlsplit(url)
            if parts.scheme.lower() not in ("http", "https", "ws", "wss") or parts.username or parts.password:
                return False
            host, port = (parts.hostname or "").rstrip(".").lower(), parts.port
        except ValueError:
            return False
        if not host:
            return False
        if (host, port) not in self._cache:
            try:
                _check_host(host, port, self._resolve)
                self._cache[(host, port)] = True
            except UnsafeUrlError:
                self._cache[(host, port)] = False
        return self._cache[(host, port)]


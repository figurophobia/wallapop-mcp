"""Turn photo inputs (local path, http(s) URL or base64 data URL) into local JPEG files."""

from __future__ import annotations

import base64
import binascii
import ipaddress
import socket
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_PHOTOS = 10
MAX_PHOTO_BYTES = 15 * 1024 * 1024
_JPEG_MAGIC = b"\xff\xd8\xff"


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # a redirect could lead to a private address that was never checked


def is_remote(ref: str) -> bool:
    return ref.startswith(("http://", "https://", "data:"))


def _check_public_host(host: str) -> None:
    """Refuse hosts that resolve to loopback, private or link-local addresses (the user's own network)."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as exc:
        raise ValueError(f"photo URL host cannot be resolved: {host[:80]}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise ValueError("photo URL must point to a public internet host")


def _fetch(url: str) -> bytes:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        raise ValueError("photo URL must be a plain http(s) URL")
    _check_public_host(parts.hostname)
    try:
        with build_opener(_NoRedirect).open(Request(url, headers={"Accept": "image/jpeg"}), timeout=20) as resp:
            if int(resp.headers.get("Content-Length") or 0) > MAX_PHOTO_BYTES:
                raise ValueError("photo exceeds 15 MB")
            return resp.read(MAX_PHOTO_BYTES + 1)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("could not download the photo URL") from exc


def _decode(data_url: str) -> bytes:
    header, sep, encoded = data_url.partition(",")
    if not sep or header.lower() not in ("data:image/jpeg;base64", "data:image/jpg;base64"):
        raise ValueError("photo data URL must be data:image/jpeg;base64,...")
    if len(encoded) > (MAX_PHOTO_BYTES + 2) // 3 * 4:
        raise ValueError("photo exceeds 15 MB")
    try:
        return base64.b64decode(encoded, validate=True)
    except binascii.Error as exc:
        raise ValueError("photo data URL is not valid base64") from exc


def materialize_photo(ref: str, destination: Path) -> str:
    """Write a URL or data-URL photo to ``destination`` and return its path. Local paths are returned unchanged.

    shortcut: JPEG only (uploads are sent as image/jpeg and there is no image library); add conversion if
    PNG/WebP inputs are needed.
    """
    if not is_remote(ref):
        return ref
    data = _decode(ref) if ref.startswith("data:") else _fetch(ref)
    if len(data) > MAX_PHOTO_BYTES:
        raise ValueError("photo exceeds 15 MB")
    if not data.startswith(_JPEG_MAGIC):
        raise ValueError("photo must be a JPEG image")
    destination.write_bytes(data)
    return str(destination)

"""Secure preview proxy.

Each generated application runs as its own OS process on a random loopback
port. NEXORA never exposes that port directly; every preview request is routed
through this proxy, which:

* only proxies to ports NEXORA itself started (``workspace.preview_port``),
* requires the workspace preview to be in the ``running`` state,
* strips hop-by-hop headers and forces the generated app's cookie path so the
  session cookie stays scoped to ``/preview/<slug>/``,
* injects a small banner so the founder always knows they are looking at
  generated code.
"""
from __future__ import annotations

import http.client
from urllib.parse import urljoin

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from .database import get_db
from .models import Workspace

router = APIRouter()

HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "content-encoding",
    "content-length", "host",
}

PREVIEW_BANNER = """
<div id="nexora-preview-banner" style="position:fixed;left:0;right:0;bottom:0;z-index:99999;
 background:rgba(10,12,16,.92);border-top:1px solid #262c36;color:#d8b678;
 font:12px/1.5 Inter,system-ui,sans-serif;padding:7px 14px;display:flex;gap:12px;
 align-items:center;justify-content:space-between;backdrop-filter:blur(8px)">
 <span><strong style="color:#eef0f4">NEXORA live preview</strong> · generated application running in an isolated process</span>
 <a href="/" target="_top" style="color:#8b9cff;text-decoration:none">← Back to studio</a>
</div>
<style>body{padding-bottom:34px !important}</style>
"""


def _find_workspace(db: Session, slug: str) -> Workspace:
    workspace = db.query(Workspace).filter(Workspace.slug == slug).first()
    if not workspace:
        raise HTTPException(404, "No generated workspace with that name.")
    if workspace.preview_status != "running" or not workspace.preview_port:
        raise HTTPException(
            409,
            "The preview for this project is not running. Build the application, then retry.",
        )
    return workspace


def _rewrite_set_cookie(value: str, slug: str) -> str:
    parts = [part.strip() for part in value.split(";")]
    rebuilt = []
    has_path = False
    for part in parts:
        lower = part.lower()
        if lower.startswith("path="):
            rebuilt.append(f"Path=/preview/{slug}/")
            has_path = True
        elif lower.startswith("domain="):
            continue
        else:
            rebuilt.append(part)
    if not has_path:
        rebuilt.append(f"Path=/preview/{slug}/")
    return "; ".join(rebuilt)


@router.api_route("/preview/{slug}/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def preview_proxy(slug: str, path: str, request: Request, db: Session = Depends(get_db)):
    workspace = _find_workspace(db, slug)
    port = workspace.preview_port
    if not port:
        raise HTTPException(409, "Preview port unavailable.")

    body = await request.body()
    target = "/" + path if path else "/"
    query = request.url.query

    headers = {
        key: value for key, value in request.headers.items()
        if key.lower() not in HOP_BY_HOP and key.lower() != "cookie"
    }
    cookie = request.headers.get("cookie")
    if cookie:
        # Cookies are scoped by the browser to /preview/<slug>/, but the
        # generated app expects them at its root.
        headers["cookie"] = cookie
    headers["host"] = f"127.0.0.1:{port}"
    headers["x-forwarded-host"] = request.headers.get("host", "")
    headers["x-forwarded-proto"] = request.url.scheme
    headers["x-forwarded-for"] = request.client.host if request.client else ""

    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    try:
        connection.request(request.method, target + (f"?{query}" if query else ""), body=body, headers=headers)
        upstream = connection.getresponse()
        payload = upstream.read()
        content_type = upstream.getheader("content-type", "application/octet-stream")
        response_headers = {
            key: value for key, value in upstream.getheaders()
            if key.lower() not in HOP_BY_HOP
        }
        set_cookies = upstream.headers.get_all("Set-Cookie") or []
    except ConnectionRefusedError as exc:
        raise HTTPException(502, "The generated application is not accepting connections.") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Preview proxy error: {type(exc).__name__}") from exc
    finally:
        connection.close()

    is_html = content_type.startswith("text/html")
    if is_html and payload:
        text = payload.decode("utf-8", errors="replace")
        if "</body>" in text:
            text = text.replace("</body>", PREVIEW_BANNER + "</body>", 1)
        else:
            text += PREVIEW_BANNER
        payload = text.encode("utf-8")

    response = Response(content=payload, status_code=upstream.status, media_type=content_type)
    for key, value in response_headers.items():
        if key.lower() in {"content-type"}:
            continue
        try:
            response.headers[key] = value
        except Exception:  # noqa: BLE001 - skip headers Starlette refuses
            continue
    if set_cookies:
        response.headers["set-cookie"] = _rewrite_set_cookie(set_cookies[0], slug)
        for extra in set_cookies[1:]:
            response.raw_headers.append((b"set-cookie", _rewrite_set_cookie(extra, slug).encode()))
    # Never let generated pages be framed by a third party.
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/api/preview/{slug}/status")
def preview_status(slug: str, db: Session = Depends(get_db)):
    workspace = db.query(Workspace).filter(Workspace.slug == slug).first()
    if not workspace:
        raise HTTPException(404, "No generated workspace with that name.")
    return {
        "slug": workspace.slug,
        "status": workspace.preview_status,
        "port": workspace.preview_port,
        "url": workspace.preview_url,
        "pid": workspace.preview_pid,
    }

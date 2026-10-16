"""Local redesign preview: python -m brickfinder.web --port 8502."""

from __future__ import annotations

import argparse
import json
from http.cookies import SimpleCookie
from threading import RLock
from time import monotonic
from uuid import uuid4
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import perf_counter
from urllib.parse import parse_qs, urlsplit

from brickfinder.catalog import Catalog, unpack_catalog
from brickfinder.coverage import OWNED_ONLY_CATEGORIES
from brickfinder.examples import EXAMPLE_COLLECTIONS
from brickfinder.matching import color_change_rows, filter_matches, recommend, shortage_rows
from brickfinder.inventory import CollectionState, available_inventory, validate_collection
from brickfinder.session import UserSession
from brickfinder.firebase_store import CloudError, RevisionConflict

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"


def set_data(lego_set):
    return {
        "code": lego_set.set_num, "name": lego_set.name, "year": lego_set.year,
        "theme": lego_set.family, "parts": lego_set.num_parts,
        "image": lego_set.safe_image_url, "instructions": lego_set.instructions_url,
        "category": lego_set.category, "owned_only": lego_set.category in OWNED_ONLY_CATEGORIES,
    }


def match_data(match):
    return {
        **set_data(match.lego_set), "mode": match.mode,
        "matched": match.matched, "required": match.required, "missing": match.missing,
        "complete": match.complete, "percent": match.percent,
        "display_percent": match.display_percent, "exact_matched": match.exact_matched,
        "exact_percent": match.exact_percent,
    }


class FinderService:
    def __init__(self, catalog):
        self.catalog = catalog

    def collection(self, body, session=None):
        if session is not None:
            session.use_catalog(self.catalog)
            return session.draft.collection
        collection = body.get("collection", {})
        if isinstance(collection, dict) and "copies" in collection:
            result = CollectionState.from_payload(collection)
            issues = validate_collection(self.catalog, result)
            if issues:
                raise ValueError("Correct inventory issues before matching.")
            return result
        if not isinstance(collection, dict):
            raise ValueError("Choose sets to add to your collection.")
        for code, quantity in collection.items():
            if code not in self.catalog.sets:
                raise ValueError(f"Set {code} is not available in this catalog.")
            if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
                raise ValueError("Set quantities must be positive whole numbers.")
        return collection

    def collection_data(self, body, session=None):
        collection = self.collection(body, session)
        if isinstance(collection, CollectionState):
            issues = validate_collection(self.catalog, collection)
            return {
                "sets": [{**set_data(self.catalog.sets[c]), "quantity": q} for c,q in collection.counts.items() if c in self.catalog.sets],
                "copies": len(collection.copies), "pieces": sum(available_inventory(self.catalog, collection).values()) if not issues else 0,
                "issues": [{"record_id": i.record_id, "message": i.message} for i in issues],
                "document": collection.payload(),
            }
        return {"sets": [{**set_data(self.catalog.sets[c]), "quantity": q} for c,q in collection.items()],
                "copies": sum(collection.values()), "pieces": sum(self.catalog.sets[c].num_parts*q for c,q in collection.items())}

    def session_data(self, session):
        collection = self.collection_data({}, session)
        return {**collection, "dirty": session.draft.dirty, "pending": session.draft.pending,
                "cloud_enabled": session.config.configured, "local_backend": bool(session.config.auth_emulator),
                "email": session.auth.email if session.auth else None,
                "catalog_changed": session.draft.collection.catalog_fingerprint != self.catalog.fingerprint,
                "loose": [{"part_id": p, "part": self.catalog.parts.get(p,"Unknown part"), "color_id": c,
                           "color": self.catalog.colors.get(c,{}).get("name", f"Unknown color {c}"), "quantity": n}
                          for (p,c),n in sorted(session.draft.collection.loose.items())]}

    def part_search(self, query):
        terms = query.strip().lower().split()
        if not terms:
            return {"parts": [], "colors": []}
        ids = sorted((p for p,name in self.catalog.parts.items() if all(t in f"{p} {name}".lower() for t in terms)),
                     key=lambda p:(p.lower()!=query.strip().lower(),p))[:30]
        return {"parts": [{"part_id": p,"name":self.catalog.parts[p]} for p in ids],
                "colors": [{"color_id": c,"name":v["name"]} for c,v in sorted(self.catalog.colors.items(),key=lambda r:r[1]["name"])]}

    def dispatch(self, route, body, session):
        session.use_catalog(self.catalog)
        if route == "/api/session":
            return self.session_data(session)
        if route == "/api/edit":
            invalidates = session.edit(body)
            return {**self.session_data(session), "invalidates_results": invalidates}
        if route == "/api/auth":
            session.login(body)
            return self.session_data(session)
        if route == "/api/navigate":
            if body.get("decision") == "cancel":
                session.draft.pending = None
                return self.session_data(session)
            action = session.draft.pending if body.get("decision") else body.get("action")
            if not isinstance(action, dict):
                raise ValueError("Choose a collection action.")
            session.navigate(action, body.get("decision"))
            return self.session_data(session)
        if route == "/api/save":
            session.save(body.get("as_name"))
            return self.session_data(session)
        if route == "/api/saved":
            return {"collections": session.repository().list()}
        if route == "/api/delete":
            session.delete(confirmed=body.get("confirmed") is True)
            return self.session_data(session)
        if route == "/api/copy-inventory":
            return session.copy_inventory(body.get("copy_id"))
        if route == "/api/plan":
            return session.plan(body.get("code"), body.get("mode","exact"))
        if route == "/api/collection":
            return self.collection_data(body,session)
        if route == "/api/recommend":
            return self.result_data(body,session)
        if route == "/api/breakdown":
            return self.breakdown(body,session)
        raise ValueError("This app action is not available.")

    def bootstrap(self):
        themes = ("Superheroes", "City", "A little of everything")
        return {
            "owned_sets": len(self.catalog.sets), "candidates": len(self.catalog.candidates),
            "examples": [
                {"name": name, "theme": theme, "sets": [set_data(self.catalog.sets[c]) for c in codes]}
                for (name, codes), theme in zip(EXAMPLE_COLLECTIONS.items(), themes)
            ],
            "featured": [set_data(self.catalog.sets[c]) for c in ("31147-1", "31134-1", "40725-1")
                         if c in self.catalog.sets],
            "coverage": self.catalog.metadata,
        }

    def matches(self, collection, mode, session=None):
        # Only public catalog data is cached on this service. Results stay per visitor.
        if not isinstance(collection, (CollectionState, dict)):
            collection = dict(collection)
        key = (collection.snapshot(mode) if isinstance(collection,CollectionState) else tuple(sorted(collection.items())),mode)
        if session is not None and key in session.matches:
            return session.matches[key]
        result = recommend(self.catalog,collection,mode)
        if session is not None:
            if len(session.matches)>=2:
                session.matches.clear()
            session.matches[key]=result
        return result

    def result_data(self, body, session=None):
        collection = self.collection(body,session)
        mode = body.get("mode", "exact")
        if mode not in ("exact", "flexible"):
            raise ValueError("Choose exact colors or flexible colors.")
        minimum = body.get("minimum", 100)
        sizes = body.get("sizes", [20, 1000])
        page = body.get("page", 1)
        if isinstance(minimum, bool) or not isinstance(minimum, (int, float)) or not 0 <= minimum <= 100:
            raise ValueError("Completion must be between 0 and 100 percent.")
        if (not isinstance(sizes, list) or len(sizes) != 2
                or any(isinstance(n, bool) or not isinstance(n, int) for n in sizes)
                or not 20 <= sizes[0] <= sizes[1] <= 1000):
            raise ValueError("Choose a piece range between 20 and 1,000.")
        if isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= 1000:
            raise ValueError("Choose a valid results page.")
        began = perf_counter()
        matches = self.matches(collection, mode, session)
        visible = filter_matches(matches, minimum, tuple(sizes))
        if body.get("only_partial"):
            visible = [m for m in visible if not m.complete]
        if body.get("sort") == "pieces":
            visible.sort(key=lambda m: (-m.required, -m.percent, m.lego_set.set_num))
        return {
            "matches": [match_data(m) for m in visible[:page * 18]],
            "total": len(visible), "complete": sum(m.complete for m in visible),
            "ready_count": sum(m.complete and sizes[0] <= m.required <= sizes[1] for m in matches),
            "compared": len(matches), "seconds": round(perf_counter() - began, 4),
            "mode": mode, "minimum": minimum, "sizes": sizes,
        }

    def breakdown(self, body, session=None):
        collection = self.collection(body,session)
        mode = body.get("mode", "exact")
        if mode not in ("exact", "flexible"):
            raise ValueError("Choose exact colors or flexible colors.")
        match = next((m for m in self.matches(collection, mode, session)
                      if m.lego_set.set_num == body.get("code")), None)
        if match is None:
            raise ValueError("This build is not available for the selected collection.")
        return {"match": match_data(match), "shortages": shortage_rows(self.catalog, collection, match),
                "substitutions": color_change_rows(self.catalog, collection, match)}


def handler_for(service):
    sessions = {}
    sessions_lock = RLock()
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(FRONTEND), **kwargs)

        def end_headers(self):
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            if getattr(self,"session_cookie",None):
                self.send_header("Set-Cookie", f"rebuilt_session={self.session_cookie}; HttpOnly; SameSite=Strict; Path=/")
            super().end_headers()

        def send_json(self, data, status=200):
            encoded = json.dumps(data, ensure_ascii=False, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self):
            parsed = urlsplit(self.path)
            if parsed.path == "/api/catalog":
                self.send_json(service.bootstrap())
            elif parsed.path == "/api/parts":
                self.send_json(service.part_search(parse_qs(parsed.query).get("q",[""])[0][:200]))
            elif parsed.path == "/api/search":
                query = parse_qs(parsed.query).get("q", [""])[0][:200]
                self.send_json({"sets": [set_data(s) for s in service.catalog.search(query, limit=8)]})
            elif parsed.path in ("/", "/index.html", "/app.css", "/app.js", "/inventory.js", "/streamlit.js", "/favicon.svg"):
                super().do_GET()
            else:
                self.send_json({"error": "Page not found."}, 404)

        def do_POST(self):
            try:
                origin = self.headers.get("Origin")
                if origin and urlsplit(origin).netloc != self.headers.get("Host"):
                    self.send_json({"error": "Please use the app on this local preview."}, 403)
                    return
                if self.headers.get_content_type() != "application/json":
                    raise ValueError("Send a JSON request.")
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 1_000_000:
                    raise ValueError("The collection request is empty or too large.")
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError("Send a valid collection request.")
                route = urlsplit(self.path).path
                cookie = SimpleCookie()
                cookie.load(self.headers.get("Cookie", ""))
                sid = cookie["rebuilt_session"].value if "rebuilt_session" in cookie else ""
                with sessions_lock:
                    now = monotonic()
                    for expired in [k for k,(_,t) in sessions.items() if now-t>3600]:
                        old,_ = sessions.pop(expired)
                        if old.auth: old.auth.clear()
                    fresh = route == "/api/session" and body.get("fresh") is True
                    if sid not in sessions or fresh:
                        if sid in sessions:
                            old,_ = sessions.pop(sid)
                            if old.auth:
                                old.auth.clear()
                            old.draft.replace(old.empty())
                            old.invalidate()
                        sid = uuid4().hex
                        sessions[sid] = (UserSession(service.catalog),now)
                        self.session_cookie = sid
                    session,_ = sessions[sid]
                    sessions[sid] = (session,now)
                with session.lock:
                    response = service.dispatch(route,body,session)
                self.send_json(response)
            except RevisionConflict as error:
                self.send_json({"error":str(error),"code":"revision_conflict"},409)
            except CloudError as error:
                self.send_json({"error":str(error)},503)
            except (ValueError, TypeError, KeyError) as error:
                self.send_json({"error": str(error)}, 400)
            except (BrokenPipeError, ConnectionResetError):
                pass

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8502)
    args = parser.parse_args()
    service = FinderService(Catalog(unpack_catalog()))
    with ThreadingHTTPServer(("127.0.0.1", args.port), handler_for(service)) as server:
        print(f"Rebuilt: http://127.0.0.1:{args.port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()

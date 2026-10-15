"""Local redesign preview: python -m brickfinder.web --port 8502."""

from __future__ import annotations

import argparse
import json
from functools import lru_cache
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import perf_counter
from urllib.parse import parse_qs, urlsplit

from brickfinder.catalog import Catalog, unpack_catalog
from brickfinder.coverage import OWNED_ONLY_CATEGORIES
from brickfinder.examples import EXAMPLE_COLLECTIONS
from brickfinder.matching import color_change_rows, filter_matches, recommend, shortage_rows

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

    def collection(self, body):
        collection = body.get("collection", {})
        if not isinstance(collection, dict):
            raise ValueError("Choose sets to add to your collection.")
        for code, quantity in collection.items():
            if code not in self.catalog.sets:
                raise ValueError(f"Set {code} is not available in this catalog.")
            if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
                raise ValueError("Set quantities must be positive whole numbers.")
        return collection

    def collection_data(self, body):
        collection = self.collection(body)
        return {
            "sets": [{**set_data(self.catalog.sets[c]), "quantity": q} for c, q in collection.items()],
            "copies": sum(collection.values()),
            "pieces": sum(self.catalog.sets[c].num_parts * q for c, q in collection.items()),
        }

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

    @lru_cache(maxsize=8)
    def matches(self, collection, mode):
        return recommend(self.catalog, dict(collection), mode)

    def result_data(self, body):
        collection = self.collection(body)
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
        matches = self.matches(tuple(sorted(collection.items())), mode)
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

    def breakdown(self, body):
        collection = self.collection(body)
        mode = body.get("mode", "exact")
        if mode not in ("exact", "flexible"):
            raise ValueError("Choose exact colors or flexible colors.")
        match = next((m for m in self.matches(tuple(sorted(collection.items())), mode)
                      if m.lego_set.set_num == body.get("code")), None)
        if match is None:
            raise ValueError("This build is not available for the selected collection.")
        return {"match": match_data(match), "shortages": shortage_rows(self.catalog, collection, match),
                "substitutions": color_change_rows(self.catalog, collection, match)}


def handler_for(service):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(FRONTEND), **kwargs)

        def end_headers(self):
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
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
            elif parsed.path == "/api/search":
                query = parse_qs(parsed.query).get("q", [""])[0][:200]
                self.send_json({"sets": [set_data(s) for s in service.catalog.search(query, limit=8)]})
            elif parsed.path in ("/", "/index.html", "/app.css", "/app.js", "/favicon.svg"):
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
                if not 0 < length <= 65536:
                    raise ValueError("The collection request is empty or too large.")
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError("Send a valid collection request.")
                route = urlsplit(self.path).path
                if route == "/api/collection":
                    response = service.collection_data(body)
                elif route == "/api/recommend":
                    response = service.result_data(body)
                elif route == "/api/breakdown":
                    response = service.breakdown(body)
                else:
                    self.send_json({"error": "Page not found."}, 404)
                    return
                self.send_json(response)
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
        print(f"Brick Finder redesign: http://127.0.0.1:{args.port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()

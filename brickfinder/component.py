"""Request bridge for the same frontend when hosted by Streamlit."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

from brickfinder.web import set_data
from brickfinder.firebase_store import CloudError, RevisionConflict

COMPONENT_KEY = "brickfinder_frontend"
RESPONSE_KEY = "brickfinder_response"


def component_response(service, request, session=None):
    """Return one correlated response without storing a visitor's collection."""
    request_id = request.get("id") if isinstance(request, dict) else None
    try:
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 100:
            raise ValueError("Send a valid app request.")
        path = request.get("path")
        if not isinstance(path, str) or len(path) > 2048:
            raise ValueError("Choose a valid app action.")
        if len(json.dumps(request, allow_nan=False).encode()) > 65536:
            raise ValueError("The collection request is too large.")
        body = request.get("body")
        if body is not None and not isinstance(body, dict):
            raise ValueError("Send a valid collection request.")
        route = urlsplit(path)
        if route.scheme or route.netloc:
            raise ValueError("Choose a valid app action.")
        if route.path == "/api/catalog" and body is None:
            data = service.bootstrap()
        elif route.path == "/api/search" and body is None:
            query = parse_qs(route.query).get("q", [""])[0][:200]
            data = {"sets": [set_data(s) for s in service.catalog.search(query, limit=8)]}
        elif route.path == "/api/parts" and body is None:
            data = service.part_search(parse_qs(route.query).get("q",[""])[0][:200])
        elif session is not None and body is not None:
            data = service.dispatch(route.path,body,session)
        elif route.path == "/api/collection" and body is not None:
            data = service.collection_data(body)
        elif route.path == "/api/recommend" and body is not None:
            data = service.result_data(body)
        elif route.path == "/api/breakdown" and body is not None:
            data = service.breakdown(body)
        else:
            raise ValueError("This app action is not available.")
        return {"id": request_id, "data": data}
    except RevisionConflict as error:
        return {"id":request_id,"error":str(error),"code":"revision_conflict"}
    except (ValueError, TypeError, KeyError, CloudError) as error:
        return {"id": request_id, "error": str(error)}
    finally:
        if isinstance(request,dict) and isinstance(request.get("body"),dict):
            request["body"].pop("password",None)

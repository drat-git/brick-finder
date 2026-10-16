"""Firebase REST access with user ID tokens. No Admin SDK or privileged credentials."""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from copy import deepcopy
from dataclasses import dataclass, field
from urllib.parse import quote
from uuid import UUID

import requests

from brickfinder.inventory import CollectionState, catalog_fingerprint, validate_collection

MAX_SNAPSHOT_BYTES = 750_000  # Leave ample headroom below Firestore's 1 MiB document limit.


class CloudError(RuntimeError):
    pass


class RevisionConflict(CloudError):
    pass


class NameTaken(CloudError):
    pass


@dataclass(frozen=True)
class FirebaseConfig:
    project_id: str = ""
    api_key: str = ""
    auth_emulator: str = ""
    firestore_emulator: str = ""

    @property
    def configured(self):
        return bool(self.project_id and self.api_key)

    @classmethod
    def read(cls, secrets=None):
        secrets = secrets or {}
        def value(name):
            return os.environ.get(name) or secrets.get(name, "")
        config = cls(value("FIREBASE_PROJECT_ID"), value("FIREBASE_API_KEY"),
                     value("FIREBASE_AUTH_EMULATOR_HOST"), value("FIRESTORE_EMULATOR_HOST"))
        if bool(config.auth_emulator) != bool(config.firestore_emulator):
            raise CloudError("Configure both Firebase emulators together.")
        for host in (config.auth_emulator, config.firestore_emulator):
            if host and not re.fullmatch(r"(?:localhost|127\.0\.0\.1):\d+", host):
                raise CloudError("Emulator endpoints must use localhost.")
        if config.project_id and not re.fullmatch(r"[a-z][a-z0-9-]{4,61}[a-z0-9]", config.project_id):
            raise CloudError("Invalid Firebase project ID.")
        return config


@dataclass(repr=False)
class FirebaseSession:
    config: FirebaseConfig
    uid: str
    email: str
    _id_token: str = field(repr=False)
    _refresh_token: str = field(repr=False)
    _expires_at: float = field(repr=False)
    transport: object = field(default=requests, repr=False)

    @classmethod
    def login(cls, config, email, password, *, signup=False, transport=requests):
        if not config.configured:
            raise CloudError("Cloud saving is not configured. Guest features are available.")
        base = (f"http://{config.auth_emulator}/identitytoolkit.googleapis.com/v1" if config.auth_emulator
                else "https://identitytoolkit.googleapis.com/v1")
        action = "signUp" if signup else "signInWithPassword"
        try:
            response = transport.post(f"{base}/accounts:{action}", params={"key": config.api_key},
                json={"email": email.strip(), "password": password, "returnSecureToken": True}, timeout=15)
            if response.status_code != 200:
                code = response.json().get("error", {}).get("message", "")
                messages = {"EMAIL_EXISTS": "This email already has an account. Log in instead.",
                            "OPERATION_NOT_ALLOWED": "Enable Email/Password in Firebase Authentication.",
                            "INVALID_EMAIL": "Enter a valid email address."}
                if code.startswith("WEAK_PASSWORD"):
                    raise CloudError("Choose a password with at least six characters.")
                raise CloudError(messages.get(code, "Authentication failed. Check your credentials or try again later."))
            data = response.json()
            if not data.get("idToken") or not data.get("refreshToken") or not data.get("localId"):
                raise CloudError("Firebase did not return a usable session.")
            return cls(config, data["localId"], data.get("email", email.strip()), data["idToken"],
                       data["refreshToken"], time.time() + int(data["expiresIn"]), transport)
        except (requests.RequestException, ValueError, KeyError) as error:
            raise CloudError("Authentication is unavailable. Your local draft is preserved.") from error

    def token(self):
        if not self._id_token:
            raise CloudError("Sign in again to access saved collections.")
        if time.time() >= self._expires_at - 60:
            base = (f"http://{self.config.auth_emulator}/securetoken.googleapis.com/v1" if self.config.auth_emulator
                    else "https://securetoken.googleapis.com/v1")
            try:
                response = self.transport.post(base + "/token", params={"key": self.config.api_key},
                    data={"grant_type": "refresh_token", "refresh_token": self._refresh_token}, timeout=15)
                if response.status_code != 200:
                    raise CloudError("Your sign-in expired. Sign in again; your draft is preserved.")
                data = response.json()
                if data["user_id"] != self.uid:
                    raise CloudError("Firebase returned an unexpected user session.")
                self._id_token, self._refresh_token = data["id_token"], data["refresh_token"]
                self._expires_at = time.time() + int(data["expires_in"])
            except (requests.RequestException, ValueError, KeyError) as error:
                raise CloudError("Could not refresh sign-in. Your local draft is preserved.") from error
        return self._id_token

    def clear(self):
        self._id_token = self._refresh_token = ""
        self._expires_at = 0


def name_fields(name):
    name = name.strip()
    if not 1 <= len(name) <= 100:
        raise ValueError("Collection names must contain 1–100 characters.")
    key = name.lower()
    return name, key, hashlib.sha256(key.encode()).hexdigest()


def encode_fields(values):
    result = {}
    for key, value in values.items():
        if type(value) is int:
            result[key] = {"integerValue": str(value)}
        elif isinstance(value, str):
            result[key] = {"stringValue": value}
        else:
            raise ValueError("Unsupported stored field")
    return result


def decode_fields(document):
    return {key: int(v["integerValue"]) if "integerValue" in v else v.get("timestampValue",v.get("stringValue"))
            for key, v in document.get("fields", {}).items()}


class CollectionRepository:
    """A bounded complete snapshot and its unique name claim commit atomically."""
    def __init__(self, auth: FirebaseSession):
        self.auth = auth
        self.prefix = f"projects/{auth.config.project_id}/databases/(default)/documents"
        self.base = (f"http://{auth.config.firestore_emulator}/v1" if auth.config.firestore_emulator
                     else "https://firestore.googleapis.com/v1")
        self.owner_path = self.prefix + "/users/" + quote(auth.uid, safe="")

    def _request(self, method, name, *, body=None, missing=False, params=None):
        try:
            response = self.auth.transport.request(method, self.base + "/" + name,
                headers={"Authorization": "Bearer " + self.auth.token()}, json=body, params=params, timeout=20)
        except requests.RequestException as error:
            raise CloudError("Cloud storage is unavailable. Your local draft is preserved.") from error
        if missing and response.status_code == 404:
            return None
        if response.status_code in (409, 412):
            raise RevisionConflict("The saved collection changed. Reload it or Save as a new collection.")
        if response.status_code >= 400:
            raise CloudError("Cloud request failed. Check sign-in, configuration, and Firestore Rules. Your draft is preserved.")
        return response.json()

    def _path(self, id):
        try:
            UUID(id)
        except (ValueError, TypeError, AttributeError) as error:
            raise ValueError("Invalid collection ID") from error
        return self.owner_path + "/collections/" + id

    def _get(self, path):
        return self._request("GET", path, missing=True)

    def list(self):
        result, page = [], ""
        while True:
            params = {"pageSize": 100, "mask.fieldPaths": ["name","revision"]}
            if page:
                params["pageToken"] = page
            data = self._request("GET", self.owner_path + "/collections", params=params)
            for doc in data.get("documents", []):
                fields = decode_fields(doc)
                result.append({"id": doc["name"].rsplit("/", 1)[-1], "name": fields["name"], "revision": fields["revision"]})
            page = data.get("nextPageToken", "")
            if not page:
                return sorted(result, key=lambda c: c["name"].lower())

    def load(self, id):
        doc = self._get(self._path(id))
        if doc is None:
            raise CloudError("This saved collection is unavailable.")
        fields = decode_fields(doc)
        payload = json.loads(fields["payload"])
        # Envelope identity/revision are authoritative; invalid catalog records stay in the payload.
        payload.update(id=id, name=fields["name"], revision=fields["revision"], catalog_fingerprint=fields["catalogFingerprint"])
        return CollectionState.from_payload(payload)

    def _commit(self, writes):
        self._request("POST", self.prefix + ":commit", body={"writes": writes})

    def save(self, catalog, collection):
        issues = validate_collection(catalog, collection)
        if issues:
            raise ValueError("Correct inventory issues before saving: " + "; ".join(i.message for i in issues))
        name, name_key, name_hash = name_fields(collection.name)
        saved = deepcopy(collection)
        saved.name, saved.revision = name, collection.revision + 1
        saved.catalog_fingerprint = catalog_fingerprint(catalog)
        payload = json.dumps(saved.payload(), ensure_ascii=False, separators=(",", ":"))
        if len(payload.encode()) > MAX_SNAPSHOT_BYTES:
            raise CloudError("This collection is too large for one cloud save. Split it into smaller named collections; your draft is unchanged.")
        path = self._path(saved.id)
        existing = self._get(path)
        if existing is None and collection.revision != 0:
            raise RevisionConflict("The saved collection was deleted. Save as to preserve this draft.")
        if existing is not None and decode_fields(existing)["revision"] != collection.revision:
            raise RevisionConflict("A newer saved revision exists. Reload it or Save as.")
        old = decode_fields(existing) if existing else None
        claim_path = self.owner_path + "/names/" + name_hash
        claim = self._get(claim_path)
        if claim is not None and decode_fields(claim)["collectionId"] != saved.id:
            raise NameTaken("You already have a collection with this name. Choose a different name.")
        fields = {"ownerId": self.auth.uid, "name": name, "nameKey": name_key, "nameHash": name_hash,
                  "revision": saved.revision, "catalogFingerprint": saved.catalog_fingerprint, "payload": payload}
        stored_fields = encode_fields(fields)
        transforms = [{"fieldPath":"updatedAt","setToServerValue":"REQUEST_TIME"}]
        if existing:
            stored_fields["createdAt"] = existing["fields"]["createdAt"]
        else:
            transforms.append({"fieldPath":"createdAt","setToServerValue":"REQUEST_TIME"})
        writes = [{"update": {"name": path, "fields": stored_fields}, "updateTransforms":transforms,
                   "currentDocument": {"updateTime": existing["updateTime"]} if existing else {"exists": False}}]
        if claim is None:
            writes.append({"update": {"name": claim_path, "fields": encode_fields({"collectionId": saved.id, "nameKey": name_key})},
                           "currentDocument": {"exists": False}})
        if old and old["nameHash"] != name_hash:
            old_claim_path = self.owner_path + "/names/" + old["nameHash"]
            old_claim = self._get(old_claim_path)
            if old_claim:
                writes.append({"delete": old_claim_path, "currentDocument": {"updateTime": old_claim["updateTime"]}})
        self._commit(writes)
        return saved

    def delete(self, collection):
        path = self._path(collection.id)
        existing = self._get(path)
        if not existing or decode_fields(existing)["revision"] != collection.revision:
            raise RevisionConflict("The saved collection changed. Reload before deleting it.")
        claim_path = self.owner_path + "/names/" + decode_fields(existing)["nameHash"]
        claim = self._get(claim_path)
        if not claim:
            raise CloudError("Saved name information is inconsistent; deletion was cancelled.")
        self._commit([{"delete": path, "currentDocument": {"updateTime": existing["updateTime"]}},
                      {"delete": claim_path, "currentDocument": {"updateTime": claim["updateTime"]}}])

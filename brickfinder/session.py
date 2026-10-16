"""Private per-visitor draft, authentication and results. Never globally cached."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from threading import RLock

from brickfinder.examples import EXAMPLE_COLLECTIONS
from brickfinder.firebase_store import CollectionRepository, FirebaseConfig, FirebaseSession, CloudError, name_fields
from brickfinder.inventory import CollectionState, PartKey, validate_collection
from brickfinder.planner import plan_build


@dataclass
class Draft:
    collection: CollectionState
    baseline: str = ""
    pending: dict | None = None

    def __post_init__(self):
        self.baseline = self.baseline or self.collection.snapshot()

    @property
    def dirty(self):
        return self.collection.snapshot() != self.baseline

    def replace(self, collection):
        self.collection = deepcopy(collection)
        self.baseline = self.collection.snapshot()
        self.pending = None


class UserSession:
    def __init__(self, catalog, config=None, *, auth_factory=FirebaseSession.login, repository_factory=CollectionRepository):
        self.catalog = catalog
        try:
            self.config = config or FirebaseConfig.read()
        except CloudError:
            self.config = FirebaseConfig()
        self.auth_factory, self.repository_factory = auth_factory, repository_factory
        self.auth = None
        self.draft = Draft(self.empty())
        self.matches = {}
        self.plans = {}
        self.lock = RLock()

    def empty(self):
        return CollectionState(catalog_fingerprint=self.catalog.fingerprint)

    def use_catalog(self, catalog):
        if self.catalog.fingerprint != catalog.fingerprint:
            self.catalog = catalog
            self.invalidate()

    def invalidate(self, recommendations=True):
        self.plans.clear()
        if recommendations:
            self.matches.clear()

    def repository(self):
        if not self.auth:
            raise CloudError("Sign in to save or load cloud collections.")
        return self.repository_factory(self.auth)

    def login(self, body):
        email, password = body.get("email"), body.get("password")
        if not isinstance(email, str) or not isinstance(password, str) or not email.strip() or not password or len(email)>320 or len(password)>4096:
            raise ValueError("Enter your email and password.")
        auth = self.auth_factory(self.config, email, password, signup=body.get("signup") is True)
        if self.auth:
            self.auth.clear()
        self.auth = auth
        # Deliberately preserve the guest draft and its dirty baseline.

    def save(self, as_name=None):
        collection = self.draft.collection.save_as(as_name) if as_name is not None else self.draft.collection
        saved = self.repository().save(self.catalog, collection)
        self.draft.replace(saved)
        self.invalidate()

    def navigate(self, action, decision=None):
        kind = action.get("kind")
        if kind not in ("new", "load", "example", "logout"):
            raise ValueError("Choose a valid collection action.")
        if decision == "cancel":
            self.draft.pending = None
            return
        if decision is not None and decision not in ("save", "discard"):
            raise ValueError("Choose Save, Discard, or Cancel.")
        if self.draft.dirty and decision is None:
            self.draft.pending = deepcopy(action)
            return
        if decision == "save":
            self.save()  # Failure leaves the draft and pending action intact.
        try:
            if kind == "load":
                collection = self.repository().load(action.get("id"))
                self.draft.replace(collection)
            elif kind == "example":
                name = action.get("name")
                if name not in EXAMPLE_COLLECTIONS:
                    raise ValueError("Choose a valid example.")
                self.draft.replace(self.empty())
                self.draft.collection = CollectionState.from_counts(self.catalog, dict.fromkeys(EXAMPLE_COLLECTIONS[name], 1), name)
            elif kind == "logout":
                if self.auth:
                    self.auth.clear()
                self.auth = None
                self.draft.replace(self.empty())
            else:
                self.draft.replace(self.empty())
        except Exception:
            if decision is not None:
                self.draft.pending = deepcopy(action)
            raise
        self.draft.pending = None
        self.invalidate()

    def delete(self, *, confirmed=False):
        if not confirmed:
            raise ValueError("Confirm deleting this saved collection first.")
        old = self.draft.collection
        self.repository().delete(old)
        self.draft.replace(self.empty())
        self.draft.collection = old.save_as(old.name)
        self.invalidate()

    def edit(self, body):
        action = body.get("action")
        candidate = deepcopy(self.draft.collection)
        def copy():
            result = next((c for c in candidate.copies if c.id == body.get("copy_id")), None)
            if result is None:
                raise ValueError("This physical copy is unavailable.")
            return result
        if action == "add_set":
            candidate.add_set(self.catalog, body.get("code"))
        elif action == "remove_set":
            candidate.copies = [c for c in candidate.copies if c.set_num != body.get("code")]
        elif action == "remove_copy":
            candidate.copies.remove(copy())
        elif action == "update_copy":
            item = copy()
            label, protected = body.get("label"), body.get("keep_assembled")
            if not isinstance(label, str) or len(label)>200 or type(protected) is not bool:
                raise ValueError("Enter a copy label and protection setting.")
            item.label, item.keep_assembled = label, protected
        elif action == "missing":
            copy().set_missing(self.catalog, PartKey(body.get("part_id"), body.get("color_id")), body.get("quantity"))
        elif action == "remove_missing":
            copy().missing.pop(PartKey(body.get("part_id"), body.get("color_id")), None)
        elif action == "accept_version":
            item = copy()
            if item.set_num not in self.catalog.sets:
                raise ValueError("Remove or replace the unknown set first.")
            item.inventory_version = self.catalog.sets[item.set_num].inventory_version
        elif action in ("loose_add", "loose_set"):
            key, quantity = PartKey(body.get("part_id"), body.get("color_id")), body.get("quantity")
            if action == "loose_set" and type(quantity) is int and quantity == 0:
                candidate.loose.pop(key, None)  # Explicit correction also removes obsolete catalog keys.
            else:
                candidate.set_loose(self.catalog, key, quantity, add=action == "loose_add")
        elif action == "rename":
            candidate.name = name_fields(body.get("name", ""))[0]
        elif action == "clear":
            candidate.copies.clear()
            candidate.loose.clear()
        else:
            raise ValueError("Choose a valid inventory action.")
        self.draft.collection = candidate
        protection_only = action in ("update_copy", "rename")
        self.invalidate(recommendations=not protection_only)
        return not protection_only

    def copy_inventory(self, id):
        item = next((c for c in self.draft.collection.copies if c.id == id), None)
        if item is None or item.set_num not in self.catalog.sets:
            raise ValueError("This copy has no current catalog inventory. Remove or replace it.")
        return {"copy_id": item.id, "version": self.catalog.sets[item.set_num].inventory_version,
                "parts": [{"part_id": p, "part": self.catalog.parts[p], "color_id": c,
                           "color": self.catalog.colors[c]["name"], "required": n, "missing": item.missing.get((p,c),0)}
                          for (p,c),n in sorted(self.catalog.inventory(item.set_num).items())]}

    def plan(self, code, mode):
        result = plan_build(self.catalog, self.draft.collection, code, mode)
        self.plans[code] = result
        return {**asdict(result), "dismantling_count": result.dismantling_count,
                "source_labels": {"loose": "Loose parts", **{c.id: (c.label or c.set_num) + " · " + c.set_num for c in self.draft.collection.copies}},
                "colors": {str(k): v["name"] for k,v in self.catalog.colors.items()}}

import json
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

from brickfinder.catalog import Catalog, unpack_catalog
from brickfinder.component import COMPONENT_KEY, RESPONSE_KEY, component_response
from brickfinder.examples import EXAMPLE_COLLECTIONS
from brickfinder.web import FinderService
from brickfinder.session import UserSession
from brickfinder.firebase_store import FirebaseConfig
from tests.fakes import MemoryAuth,MemoryRepository

ROOT = Path(__file__).resolve().parents[1]


class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = FinderService(Catalog(unpack_catalog()))
        cls.collection = dict.fromkeys(EXAMPLE_COLLECTIONS["Example 1"], 1)

    def request(self, path, body=None, request_id="request-1"):
        return component_response(self.service, {"id": request_id, "path": path, "body": body})

    def test_streamlit_entrypoint_preserves_component_identity_across_responses(self):
        app = AppTest.from_file(ROOT / "app.py", default_timeout=30).run()
        self.assertFalse(app.exception)
        component = app.get("component_instance")[0]
        identity = component.proto.id
        args = json.loads(component.proto.json_args)
        self.assertEqual(args["key"], COMPONENT_KEY)
        self.assertIsNone(args["response"])
        response = self.request("/api/search?q=31124", request_id="search-1")
        app.session_state[RESPONSE_KEY] = response
        app.run()
        self.assertFalse(app.exception)
        component = app.get("component_instance")[0]
        self.assertEqual(component.proto.id, identity)
        self.assertEqual(json.loads(component.proto.json_args)["response"], response)

    def test_catalog_search_and_collection_use_the_shared_service(self):
        catalog = self.request("/api/catalog")
        expected = self.service.bootstrap()
        self.assertEqual({k:v for k,v in catalog["data"].items() if k != "featured"},
                         {k:v for k,v in expected.items() if k != "featured"})
        self.assertEqual(len(catalog["data"]["featured"]), 3)
        self.assertEqual(len(catalog["data"]["examples"]), 3)
        search = self.request("/api/search?q=31124", request_id="search-2")
        self.assertEqual(search["id"], "search-2")
        self.assertEqual(search["data"]["sets"][0]["code"], "31124-1")
        body = {"collection": {"31124-1": 2}}
        owned = self.request("/api/collection", body)
        self.assertEqual(owned["data"], self.service.collection_data(body))
        self.assertEqual(owned["data"]["copies"], 2)

    def test_inspiration_refresh_excludes_the_displayed_sets_without_a_private_session(self):
        first = self.request("/api/catalog")["data"]["featured"]
        query = "&".join(f"exclude={s['code']}" for s in first)
        response = self.request(f"/api/inspiration?{query}", request_id="shuffle-1")
        self.assertEqual(response["id"], "shuffle-1")
        self.assertNotIn("error", response)
        sets = response["data"]["sets"]
        self.assertEqual(len(sets), 3)
        self.assertTrue({s["code"] for s in sets}.isdisjoint(s["code"] for s in first))

    def test_hosted_defaults_and_piece_details_are_complete_in_exact_colors(self):
        body = {"collection": self.collection}
        result = self.request("/api/recommend", body)
        self.assertNotIn("error", result)
        self.assertGreater(result["data"]["total"], 0)
        self.assertEqual(result["data"]["mode"], "exact")
        self.assertTrue(all(m["complete"] and m["missing"] == 0 and m["exact_matched"] == m["required"]
                            for m in result["data"]["matches"]))
        detail = self.request("/api/breakdown", {**body, "code": "30162-1"})
        self.assertEqual(detail["data"]["shortages"], [])
        self.assertEqual(detail["data"]["substitutions"], [])

    def test_flexible_and_partial_builds_work_through_the_component(self):
        body = {"collection": self.collection, "mode": "flexible"}
        flexible = self.request("/api/recommend", body)["data"]
        swap = next(m for m in flexible["matches"] if m["exact_matched"] < m["required"])
        detail = self.request("/api/breakdown", {**body, "code": swap["code"]})["data"]
        self.assertTrue(detail["substitutions"])
        self.assertEqual(detail["shortages"], [])
        partial = self.request("/api/recommend", {**body, "minimum": 80, "only_partial": True})["data"]
        self.assertGreater(partial["total"], 0)
        self.assertTrue(all(not m["complete"] and m["percent"] >= 80 for m in partial["matches"]))

    def test_bad_requests_return_correlated_errors(self):
        for request in (
            None, [], {}, {"id": 1}, {"id": "x", "path": 1},
            {"id": "x", "path": "/api/collection", "body": []},
            {"id": "x", "path": "https://other.example/api/catalog"},
            {"id": "x", "path": "/api/unknown"},
            {"id": "x", "path": "/api/recommend", "body": {"collection": {"unknown": 1}}},
            {"id": "x", "path": "/api/recommend", "body": {"mode": "invalid"}},
            {"id": "x", "path": "/api/recommend", "body": {"minimum": float("nan")}},
            {"id": "x", "path": "/api/collection", "body": {"extra": "x" * 65536}},
        ):
            with self.subTest(request_type=type(request).__name__):
                response = component_response(self.service, request)
                self.assertIn("error", response)
                self.assertEqual(response["id"], request.get("id") if isinstance(request, dict) else None)

    def test_new_inventory_and_plan_routes_use_private_session(self):
        session=UserSession(self.service.catalog)
        def request(path,body):
            return component_response(self.service,{"id":"inventory-1","path":path,"body":body},session)
        added=request('/api/edit',{'action':'add_set','code':'31124-1'})['data']
        self.assertEqual(added['copies'],1)
        self.assertTrue(added['dirty'])
        self.assertNotIn('auth',added)
        original=session.draft.collection.payload()
        request('/api/navigate',{'action':{'kind':'new'}})
        self.assertIsNotNone(session.draft.pending)
        request('/api/navigate',{'decision':'cancel'})
        self.assertEqual(session.draft.collection.payload(),original)
        result=request('/api/plan',{'code':'31124-1','mode':'exact'})['data']
        self.assertEqual(result['status'],'optimal')
        self.assertEqual(result['dismantling_count'],1)
        self.assertEqual(set(self.service.__dict__),{'catalog'})

    def test_auth_component_scrubs_password_and_never_returns_tokens(self):
        repository=MemoryRepository()
        session=UserSession(self.service.catalog,FirebaseConfig('demo-rebuilt','public'),
            auth_factory=lambda *a,**kw:MemoryAuth(),repository_factory=lambda auth:repository)
        request={'id':'auth-1','path':'/api/auth','body':{'email':'person@example.com','password':'private-password'}}
        response=component_response(self.service,request,session)
        self.assertNotIn('error',response)
        self.assertNotIn('password',request['body'])
        self.assertNotIn('private-password',json.dumps(response))
        self.assertNotIn('token',json.dumps(response).lower())
        self.assertEqual(response['data']['email'],'person@example.com')


if __name__ == "__main__":
    unittest.main()

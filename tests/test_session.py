import unittest
from copy import deepcopy
from unittest.mock import patch

from brickfinder.firebase_store import FirebaseConfig, RevisionConflict
from brickfinder.inventory import CollectionState
from brickfinder.session import UserSession
from tests.fakes import MemoryAuth,MemoryRepository
from tests.test_matching import FakeCatalog


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.catalog=FakeCatalog();self.catalog.fingerprint='test'
        self.repository=MemoryRepository()
        self.auth=MemoryAuth()
        self.session=UserSession(self.catalog,FirebaseConfig('demo-rebuilt','test'),
            auth_factory=lambda *args,**kwargs:self.auth,repository_factory=lambda auth:self.repository)
    def login(self):
        self.session.login({'email':'person@example.com','password':'not-stored'})
    def add(self):
        self.session.edit({'action':'add_set','code':'10000-1'})

    def test_login_preserves_guest_draft_save_roundtrip_and_save_as(self):
        self.add();before=self.session.draft.collection.payload()
        self.login();self.assertEqual(self.session.draft.collection.payload(),before)
        self.session.save();saved=deepcopy(self.session.draft.collection)
        self.assertEqual(saved.revision,1);self.assertFalse(self.session.draft.dirty)
        self.session.save('Independent')
        clone=self.session.draft.collection
        self.assertNotEqual(saved.id,clone.id)
        self.assertFalse({c.id for c in saved.copies}&{c.id for c in clone.copies})
        self.session.navigate({'kind':'load','id':saved.id})
        self.assertEqual(self.session.draft.collection.payload(),saved.payload())

    def test_dirty_navigation_cancel_discard_and_save(self):
        for kind in ('new','load','example','logout'):
            self.session=UserSession(self.catalog)
            self.add();before=deepcopy(self.session.draft.collection.payload())
            action={'kind':kind,'name':'Example 1','id':'unavailable'}
            self.session.navigate(action)
            self.assertEqual(self.session.draft.pending,action)
            self.assertEqual(self.session.draft.collection.payload(),before)
            self.session.navigate(action,'cancel')
            self.assertIsNone(self.session.draft.pending)
            self.assertEqual(self.session.draft.collection.payload(),before)
        self.session=UserSession(self.catalog,FirebaseConfig('demo-rebuilt','test'),auth_factory=lambda *a,**kw:self.auth,repository_factory=lambda a:self.repository)
        self.add();self.login();saved_id=self.session.draft.collection.id
        self.session.navigate({'kind':'new'});self.session.navigate({'kind':'new'},'save')
        self.assertIn(saved_id,self.repository.rows);self.assertFalse(self.session.draft.collection)
        self.add();self.session.navigate({'kind':'new'},'discard');self.assertFalse(self.session.draft.collection)

    def test_conflict_and_outage_preserve_draft(self):
        self.add();self.login();self.session.save()
        self.repository.rows[self.session.draft.collection.id].revision+=1
        self.add();before=deepcopy(self.session.draft.collection.payload())
        with self.assertRaises(RevisionConflict):self.session.save()
        self.assertEqual(self.session.draft.collection.payload(),before)
        self.repository.fail=True
        with self.assertRaises(RuntimeError):self.session.save('Backup')
        self.assertEqual(self.session.draft.collection.payload(),before)

    def test_protection_only_preserves_recommendation_cache_and_clears_plans(self):
        self.add();copy=self.session.draft.collection.copies[0]
        self.session.matches['cached']='value';self.session.plans['target']='plan'
        invalidates=self.session.edit({'action':'update_copy','copy_id':copy.id,'label':'Display','keep_assembled':True})
        self.assertFalse(invalidates);self.assertTrue(self.session.matches);self.assertFalse(self.session.plans)
        self.session.edit({'action':'missing','copy_id':copy.id,'part_id':'a','color_id':1,'quantity':1})
        self.assertFalse(self.session.matches)

    def test_invalid_edit_is_atomic_and_missing_edits_do_not_change_other_copy(self):
        self.add();self.add();a,b=self.session.draft.collection.copies
        before=self.session.draft.collection.payload()
        with self.assertRaises(ValueError):
            self.session.edit({'action':'missing','copy_id':a.id,'part_id':'a','color_id':1,'quantity':99})
        self.assertEqual(self.session.draft.collection.payload(),before)
        self.session.edit({'action':'missing','copy_id':a.id,'part_id':'a','color_id':1,'quantity':1})
        self.assertFalse(self.session.draft.collection.copies[1].missing)

    def test_loose_add_set_zero_and_unknown_records(self):
        for _ in range(2):self.session.edit({'action':'loose_add','part_id':'a','color_id':1,'quantity':2})
        self.assertEqual(self.session.draft.collection.loose['a',1],4)
        self.session.edit({'action':'loose_set','part_id':'a','color_id':1,'quantity':3})
        self.assertEqual(self.session.draft.collection.loose['a',1],3)
        self.session.edit({'action':'loose_set','part_id':'a','color_id':1,'quantity':0})
        self.assertFalse(self.session.draft.collection.loose)
        self.session.draft.collection.loose['unknown',100]=5
        self.session.edit({'action':'loose_set','part_id':'unknown','color_id':100,'quantity':0})
        self.assertFalse(self.session.draft.collection.loose)

    def test_delete_requires_confirmation_and_keeps_independent_local_draft(self):
        self.add();self.login();self.session.save();id=self.session.draft.collection.id
        with self.assertRaises(ValueError):self.session.delete()
        self.session.delete(confirmed=True)
        self.assertNotIn(id,self.repository.rows)
        self.assertNotEqual(self.session.draft.collection.id,id)
        self.assertTrue(self.session.draft.collection);self.assertTrue(self.session.draft.dirty)

    def test_signout_clears_auth_private_draft_results_and_plans(self):
        self.add();self.login();self.session.matches['secret']=[];self.session.plans['secret']=[]
        self.session.navigate({'kind':'logout'})
        self.assertIsNotNone(self.session.auth)
        self.session.navigate({'kind':'logout'},'discard')
        self.assertTrue(self.auth.cleared);self.assertIsNone(self.session.auth)
        self.assertFalse(self.session.draft.collection);self.assertFalse(self.session.matches);self.assertFalse(self.session.plans)

    def test_failed_load_after_successful_navigation_save_can_be_cancelled(self):
        self.add();self.login()
        action={'kind':'load','id':'unavailable'}
        self.session.navigate(action)
        with patch.object(self.repository,'load',side_effect=RuntimeError('Load failed')):
            with self.assertRaises(RuntimeError):self.session.navigate(action,'save')
        self.assertEqual(self.session.draft.pending,action)
        self.assertFalse(self.session.draft.dirty)
        self.session.navigate(action,'cancel')
        self.assertIsNone(self.session.draft.pending)

    def test_catalog_change_invalidates_cached_results_without_discarding_records(self):
        self.add();before=deepcopy(self.session.draft.collection.payload())
        self.session.matches['old']=[];self.session.plans['old']=[]
        newer=deepcopy(self.catalog);newer.fingerprint='changed'
        self.session.use_catalog(newer)
        self.assertIs(self.session.catalog,newer)
        self.assertFalse(self.session.matches);self.assertFalse(self.session.plans)
        self.assertEqual(self.session.draft.collection.payload(),before)

"""Real Firebase Auth/Firestore REST + security-rule tests, no cloud credentials."""
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from uuid import uuid4

import requests

from brickfinder.catalog import Catalog,unpack_catalog
from brickfinder.firebase_store import FirebaseConfig,FirebaseSession,CollectionRepository,RevisionConflict,CloudError,NameTaken,decode_fields,encode_fields
from brickfinder.inventory import CollectionState


@unittest.skipUnless(os.getenv('FIRESTORE_EMULATOR_HOST') and os.getenv('FIREBASE_AUTH_EMULATOR_HOST'),'Run inside Firebase Auth/Firestore emulators')
class FirebaseEmulatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog=Catalog(unpack_catalog())
        cls.config=FirebaseConfig('demo-rebuilt','emulator-key',os.environ['FIREBASE_AUTH_EMULATOR_HOST'],os.environ['FIRESTORE_EMULATOR_HOST'])
    def setUp(self):
        self.auth=[FirebaseSession.login(self.config,f'test-{uuid4().hex}@example.com','Test-password123',signup=True) for _ in range(2)]
        self.repo=[CollectionRepository(a) for a in self.auth]
    def collection(self):
        c=CollectionState.from_counts(self.catalog,{'31124-1':2},'Test '+uuid4().hex)
        c.copies[0].keep_assembled=True
        key=next(iter(self.catalog.inventory('31124-1')))
        c.copies[1].set_missing(self.catalog,key,1);c.set_loose(self.catalog,key,3)
        return c
    def test_signup_crud_rename_save_as_and_delete(self):
        saved=self.repo[0].save(self.catalog,self.collection())
        self.assertEqual(saved.revision,1);self.assertEqual(self.repo[0].load(saved.id).payload(),saved.payload())
        first_envelope=self.repo[0]._get(self.repo[0]._path(saved.id))['fields']
        self.assertIn('timestampValue',first_envelope['createdAt'])
        self.assertIn('timestampValue',first_envelope['updatedAt'])
        self.assertEqual(len(self.repo[0].list()),1)
        with self.assertRaises(NameTaken):self.repo[0].save(self.catalog,saved.save_as(saved.name.upper()))
        old_name=saved.name;saved.name+=' renamed';saved=self.repo[0].save(self.catalog,saved)
        self.assertEqual(saved.revision,2)
        renamed_envelope=self.repo[0]._get(self.repo[0]._path(saved.id))['fields']
        self.assertEqual(renamed_envelope['createdAt'],first_envelope['createdAt'])
        self.repo[0].save(self.catalog,saved.save_as(old_name))  # Rename released the old name atomically.
        clone=self.repo[0].save(self.catalog,saved.save_as('Independent '+uuid4().hex))
        self.assertFalse({c.id for c in saved.copies}&{c.id for c in clone.copies})
        self.repo[0].delete(saved)
        with self.assertRaises(CloudError):self.repo[0].load(saved.id)
    def test_revision_conflict_and_failed_atomic_commit_preserve_server(self):
        saved=self.repo[0].save(self.catalog,self.collection());stale=deepcopy(saved)
        saved.copies[0].label='Newer';saved=self.repo[0].save(self.catalog,saved)
        before=deepcopy(self.repo[0].load(saved.id).payload())
        with self.assertRaises(RevisionConflict):self.repo[0].save(self.catalog,stale)
        doc=self.repo[0]._get(self.repo[0]._path(saved.id));fields=deepcopy(doc['fields']);fields['revision']={'integerValue':str(saved.revision+1)}
        foreign=self.repo[1]._path(str(uuid4()))
        with self.assertRaises(CloudError):self.repo[0]._commit([
            {'update':{'name':doc['name'],'fields':fields},'updateTransforms':[{'fieldPath':'updatedAt','setToServerValue':'REQUEST_TIME'}],'currentDocument':{'updateTime':doc['updateTime']}},
            {'update':{'name':foreign,'fields':fields}}])
        self.assertEqual(self.repo[0].load(saved.id).payload(),before)
    def test_two_user_isolation_and_all_guessed_child_writes(self):
        saved=self.repo[0].save(self.catalog,self.collection())
        self.assertEqual(self.repo[1].list(),[])
        path=self.repo[0]._path(saved.id)
        headers={'Authorization':'Bearer '+self.auth[1].token()}
        self.assertEqual(requests.get(self.repo[0].base+'/'+path,headers=headers,timeout=10).status_code,403)
        for suffix in ('','/copies/copy-a','/missing/piece-a','/loose/piece-a'):
            url=self.repo[0].base+'/'+path+suffix
            for method in ('PATCH','DELETE'):
                result=requests.request(method,url,headers=headers,json={'fields':{'quantity':{'integerValue':'9'}}} if method=='PATCH' else None,timeout=10)
                self.assertEqual(result.status_code,403)
        # Even the owner cannot bypass the atomic snapshot with independently writable children.
        own={'Authorization':'Bearer '+self.auth[0].token()}
        self.assertEqual(requests.patch(self.repo[0].base+'/'+path+'/copies/copy-a',headers=own,json={'fields':{}},timeout=10).status_code,403)
    def test_simultaneous_names_have_one_winner(self):
        first=self.collection();second=first.save_as(first.name.upper())
        def save(c):
            try:return self.repo[0].save(self.catalog,c)
            except (CloudError,RevisionConflict):return None
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(save,[first,second]))
        self.assertEqual(sum(r is not None for r in results),1)
        self.assertEqual(len(self.repo[0].list()),1)

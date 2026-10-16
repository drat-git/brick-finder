import os
import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock,patch

from brickfinder.firebase_store import (FirebaseConfig,FirebaseSession,CollectionRepository,CloudError,RevisionConflict,name_fields,MAX_SNAPSHOT_BYTES)
from brickfinder.inventory import CollectionState
from tests.test_matching import FakeCatalog


def response(data,status=200):return SimpleNamespace(status_code=status,json=lambda:data)


class FirebaseUnitTests(unittest.TestCase):
    def setUp(self):
        self.config=FirebaseConfig('demo-rebuilt','public-key')
        self.transport=Mock()
        self.data={'idToken':'private-id','refreshToken':'private-refresh','localId':'user-a','email':'a@example.com','expiresIn':'3600'}
        self.transport.post.return_value=response(self.data)
    def test_signup_immediate_session_and_no_email_request(self):
        auth=FirebaseSession.login(self.config,'a@example.com','password',signup=True,transport=self.transport)
        self.assertEqual(auth.uid,'user-a');self.assertEqual(auth.token(),'private-id')
        self.assertEqual(self.transport.post.call_count,1)
        args=self.transport.post.call_args
        self.assertTrue(args.args[0].endswith('/accounts:signUp'))
        self.assertTrue(args.kwargs['json']['returnSecureToken'])
        self.assertNotIn('private-id',repr(auth));self.assertNotIn('password',repr(auth))
    def test_refresh_only_on_demand_and_clear(self):
        auth=FirebaseSession.login(self.config,'a@example.com','password',transport=self.transport)
        auth._expires_at=0
        self.transport.post.return_value=response({'user_id':'user-a','id_token':'refreshed','refresh_token':'new-refresh','expires_in':'3600'})
        self.assertEqual(auth.token(),'refreshed')
        self.assertEqual(self.transport.post.call_count,2)
        auth.clear()
        with self.assertRaises(CloudError):auth.token()
        self.assertFalse(auth._id_token);self.assertFalse(auth._refresh_token)
    def test_missing_session_and_errors_are_sanitized(self):
        self.transport.post.return_value=response({'localId':'user-a'})
        with self.assertRaises(CloudError):FirebaseSession.login(self.config,'a@example.com','password',transport=self.transport)
        self.transport.post.return_value=response({'error':{'message':'SERVER_SECRET_PASSWORD'}},400)
        with self.assertRaises(CloudError) as context:FirebaseSession.login(self.config,'a@example.com','password',transport=self.transport)
        self.assertNotIn('SERVER_SECRET',str(context.exception))
    def test_only_paired_loopback_emulators_are_allowed(self):
        with patch.dict(os.environ,{'FIREBASE_AUTH_EMULATOR_HOST':'evil.example:9099','FIRESTORE_EMULATOR_HOST':'127.0.0.1:8080'}):
            with self.assertRaises(CloudError):FirebaseConfig.read()
    def test_user_token_authorizes_rest_and_revision_conflicts_are_explicit(self):
        auth=FirebaseSession.login(self.config,'a@example.com','password',transport=self.transport)
        repo=CollectionRepository(auth)
        self.transport.request.return_value=response({'documents':[]})
        self.assertEqual(repo.list(),[])
        self.assertEqual(self.transport.request.call_args.kwargs['headers'],{'Authorization':'Bearer private-id'})
        self.transport.request.return_value=response({},409)
        with self.assertRaises(RevisionConflict):repo.list()
    def test_name_normalization_and_save_size_are_checked_before_writing(self):
        self.assertEqual(name_fields('  Mixed NAME  ')[1],'mixed name')
        with self.assertRaises(ValueError):name_fields(' ')
        auth=FirebaseSession.login(self.config,'a@example.com','password',transport=self.transport)
        repo=CollectionRepository(auth);catalog=FakeCatalog();c=CollectionState.from_counts(catalog,{'10000-1':1})
        c.copies[0].label='x'*MAX_SNAPSHOT_BYTES
        with self.assertRaises(CloudError):repo.save(catalog,c)
        self.transport.request.assert_not_called()

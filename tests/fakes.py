"""Credential-free application boundary fakes; actual Rules run in emulators."""
from copy import deepcopy
from brickfinder.firebase_store import RevisionConflict, NameTaken


class MemoryAuth:
    def __init__(self, uid='user-a', email='person@example.com'):
        self.uid,self.email,self.cleared=uid,email,False
    def clear(self):
        self.cleared=True


class MemoryRepository:
    def __init__(self):
        self.rows={}
        self.fail=False
    def list(self):
        if self.fail:raise RuntimeError('Backend unavailable')
        return [{'id':c.id,'name':c.name,'revision':c.revision} for c in self.rows.values()]
    def load(self,id):
        if self.fail:raise RuntimeError('Backend unavailable')
        return deepcopy(self.rows[id])
    def save(self,catalog,collection):
        if self.fail:raise RuntimeError('Backend unavailable')
        existing=self.rows.get(collection.id)
        if collection.revision and (not existing or existing.revision!=collection.revision):
            raise RevisionConflict('Revision conflict')
        if any(c.name.lower()==collection.name.lower() and c.id!=collection.id for c in self.rows.values()):
            raise NameTaken('Duplicate name')
        saved=deepcopy(collection);saved.revision+=1
        self.rows[saved.id]=deepcopy(saved)
        return saved
    def delete(self,collection):
        if self.fail:raise RuntimeError('Backend unavailable')
        if self.rows[collection.id].revision!=collection.revision:raise RevisionConflict('Revision conflict')
        del self.rows[collection.id]

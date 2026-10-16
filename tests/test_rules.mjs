import {test,before,after} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createHash,randomUUID} from 'node:crypto';
import {initializeTestEnvironment,assertFails,assertSucceeds} from '@firebase/rules-unit-testing';
import {doc,getDoc,getDocs,collection,writeBatch,setDoc,updateDoc,deleteDoc,serverTimestamp} from 'firebase/firestore';
let env;
before(async()=>{env=await initializeTestEnvironment({projectId:'demo-rebuilt',firestore:{host:'127.0.0.1',port:8080,rules:await readFile('firestore.rules','utf8')}});});
after(async()=>{await env?.cleanup();});
function document(name='Collection '+randomUUID(),revision=1){const nameKey=name.toLowerCase();return {ownerId:'alice',name,nameKey,nameHash:createHash('sha256').update(nameKey).digest('hex'),revision,catalogFingerprint:'test',payload:'{}',createdAt:serverTimestamp(),updatedAt:serverTimestamp()};}
function refs(db,id,data,user='alice'){return {c:doc(db,`users/${user}/collections/${id}`),n:doc(db,`users/${user}/names/${data.nameHash}`)};}
async function create(db,id,data,user='alice'){const r=refs(db,id,data,user),b=writeBatch(db);b.set(r.c,data);b.set(r.n,{collectionId:id,nameKey:data.nameKey});return b.commit();}

test('owner can create only with a matching atomic name claim; guest denied',async()=>{
 const db=env.authenticatedContext('alice').firestore(),id=randomUUID(),data=document();
 await assertFails(setDoc(refs(db,id,data).c,data));
 await assertSucceeds(create(db,id,data));
 assert.equal((await getDoc(refs(db,id,data).c)).data().revision,1);
 const guest=env.unauthenticatedContext().firestore();
 await assertFails(getDoc(refs(guest,id,data).c));await assertFails(getDocs(collection(guest,'users/alice/collections')));
});
test('two-user read, update, delete and forged parent writes are denied',async()=>{
 const a=env.authenticatedContext('alice').firestore(),b=env.authenticatedContext('bob').firestore(),id=randomUUID(),data=document();await create(a,id,data);
 const r=refs(b,id,data);
 await assertFails(getDoc(r.c));await assertFails(updateDoc(r.c,{revision:2,updatedAt:serverTimestamp()}));await assertFails(deleteDoc(r.c));
 await assertFails(create(b,randomUUID(),data));
 for(const child of ['copies/copy-a','missing/piece-a','loose/piece-a']){
   await assertFails(setDoc(doc(b,`${r.c.path}/${child}`),{quantity:1}));
   await assertFails(setDoc(doc(a,`${r.c.path}/${child}`),{quantity:1}));
 }
 await assertFails(updateDoc(refs(a,id,data).c,{ownerId:'bob',revision:2}));
});
test('case-insensitive names cannot be stolen by another collection',async()=>{
 const db=env.authenticatedContext('alice').firestore(),id=randomUUID(),data=document();await create(db,id,data);
 const otherId=randomUUID(),other={...data,name:data.name.toUpperCase()};
 await assertFails(create(db,otherId,other));
 await assertFails(updateDoc(refs(db,id,data).n,{collectionId:otherId}));
 const bob=env.authenticatedContext('bob').firestore();await assertSucceeds(create(bob,randomUUID(),{...data,ownerId:'bob'},'bob'));
});
test('revision increments are enforced and invalid second write rolls back first',async()=>{
 const db=env.authenticatedContext('alice').firestore(),id=randomUUID(),data=document();await create(db,id,data);const r=refs(db,id,data);
 await assertFails(updateDoc(r.c,{revision:3}));
 const batch=writeBatch(db);batch.update(r.c,{revision:2,updatedAt:serverTimestamp()});batch.set(doc(db,'users/bob/collections/attack'),data);await assertFails(batch.commit());
 assert.equal((await getDoc(r.c)).data().revision,1);
 await assertSucceeds(updateDoc(r.c,{revision:2,updatedAt:serverTimestamp()}));
});
test('rename and delete must release the old name in the same commit',async()=>{
 const db=env.authenticatedContext('alice').firestore(),id=randomUUID(),data=document();await create(db,id,data);const old=refs(db,id,data),next=document('Renamed '+randomUUID(),2),r=refs(db,id,next);next.createdAt=(await getDoc(old.c)).data().createdAt;
 await assertFails(deleteDoc(old.n));
 let batch=writeBatch(db);batch.set(old.c,next);batch.set(r.n,{collectionId:id,nameKey:next.nameKey});await assertFails(batch.commit());
 batch=writeBatch(db);batch.set(old.c,next);batch.set(r.n,{collectionId:id,nameKey:next.nameKey});batch.delete(old.n);await assertSucceeds(batch.commit());
 await assertFails(deleteDoc(r.c));
 batch=writeBatch(db);batch.delete(r.c);batch.delete(r.n);await assertSucceeds(batch.commit());
});
test('malformed envelopes, whitespace names and oversized payloads are rejected',async()=>{
 const db=env.authenticatedContext('alice').firestore();
 for(const data of [{...document(),name:'  '},{...document(),revision:0},{...document(),payload:'x'.repeat(750001)},{...document(),nameHash:'wrong'},{...document(),extra:'forbidden'}])await assertFails(create(db,randomUUID(),data));
});

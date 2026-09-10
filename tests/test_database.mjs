import { PGlite } from "@electric-sql/pglite";
import fs from "node:fs";
import assert from "node:assert/strict";
const schema=fs.readFileSync(new URL("../sql/01_schema.sql",import.meta.url),"utf8");
const db=new PGlite();
await db.exec("create role anon; create role authenticated; create role service_role bypassrls;");
await db.exec(schema);
let passed=0;
async function rejects(sql,pattern,args){
 try{await db.query(sql,args);}catch(e){assert.match(e.message,pattern);passed++;return;}
 throw Error("Expected refusal: "+sql);
}
await db.exec(`insert into ft2_people values ('admin@test','Admin',4,true),('prof@test','Prof',4,false),('d1@test','D1',1,false),('d3@test','D3',3,false)`);
for(let i=0;i<15;i++)await db.query("insert into ft2_people values($1,$2,2,false)",["p"+i+"@test","P"+i]);
async function create(){return (await db.query("select ft2_create_session('admin@test','Test',current_date+2,now()-interval '1 day',now()+interval '1 day',array[1,2,3]) sid")).rows[0].sid;}
async function add(sid,name,kind,periods=[9,10],cap=12,degree=2){
 await db.query("select ft2_add_activity('admin@test',$1,$2,'Prof','A',$3,$4,$5,$6)",[sid,name,kind,periods,degree,cap]);
 return (await db.query("select id,period from ft2_activities where session_id=$1 and lower(trim(name))=lower(trim($2)) and degree=$3 order by period",[sid,name,degree])).rows;
}
const rev=async sid=>(await db.query("select revision from ft2_sessions where id=$1",[sid])).rows[0].revision;
const sid=await create();
assert.equal((await db.query("select count(*)::integer n from ft2_activities")).rows[0].n,0);passed++;
const math=await add(sid,"Math","remediation",[9,10],2);
const study=await add(sid,"Étude","depassement",[9,10],3);
const free=await add(sid,"Lecture","depassement",[9,10],null);
const french=await add(sid,"Français","remediation",[9],null);
assert.equal((await db.query("select capacity from ft2_activities where id=$1",[study[0].id])).rows[0].capacity,3);passed++;
await rejects("select ft2_add_activity('prof@test',$1,'No','Prof','A','remediation',array[9],2,12)",/administrateur/,[sid]);
await rejects("select ft2_add_activity('admin@test',$1,'No','','A','remediation',array[9],2,12)",/professeur/,[sid]);
await rejects("select ft2_add_activity('admin@test',$1,'No','Prof','A','remediation',array[910],2,12)",/P9/,[sid]);
await rejects("select ft2_add_activity('admin@test',$1,'No','Prof','A','remediation',array[9],2,0)",/check constraint/,[sid]);
await rejects("select ft2_add_activity('admin@test',$1,' MATH ','Autre prof','B','depassement',array[9],2,4)",/unique constraint/,[sid]);
await rejects("select ft2_enroll('p0@test',$1,'p0@test',$2)",/professeurs/,[sid,math[0].id]);
await rejects("select ft2_enroll('prof@test',$1,'d1@test',$2)",/degré/,[sid,math[0].id]);
await rejects("select ft2_enroll('prof@test',$1,'p0@test',$2)",/manuelle uniquement/,[sid,study[0].id]);
for(let i=0;i<2;i++)await db.query("select ft2_enroll('prof@test',$1,$2,$3)",[sid,"p"+i+"@test",math[0].id]);
await rejects("select ft2_enroll('prof@test',$1,'p2@test',$2)",/complet/,[sid,math[0].id]);
await rejects("select ft2_enroll('prof@test',$1,'p0@test',$2)",/unique constraint/,[sid,math[1].id]);
await rejects("select ft2_delete_activity('admin@test',$1)",/élèves/,[math[0].id]);
for(let i=2;i<15;i++)await db.query("select ft2_enroll('prof@test',$1,$2,$3)",[sid,"p"+i+"@test",french[0].id]);
assert.equal((await db.query("select count(*)::integer n from ft2_assignments where activity_id=$1",[french[0].id])).rows[0].n,13);passed++;
// Entire JSON import rolls back if any later item is invalid.
const row={name:"Import",professor:"Prof import",room:"B",kind:"depassement",degree:2,period:10,capacity:7};
await rejects("select ft2_import_activities('admin@test',$1,$2::jsonb)",/P9/,[sid,JSON.stringify([row,{...row,name:"Bad",period:910}])]);
assert.equal((await db.query("select count(*)::integer n from ft2_activities where name='Import'")).rows[0].n,0);passed++;
await rejects("select ft2_import_activities('prof@test',$1,$2::jsonb)",/administrateur/,[sid,JSON.stringify([row])]);
await db.query("select ft2_import_activities('admin@test',$1,$2::jsonb)",[sid,JSON.stringify([row,{...row,name:"D1 imported",degree:1},{...row,name:"D3 imported",degree:3,capacity:null}])]);
assert.equal((await db.query("select count(*)::integer n from ft2_activities where professor='Prof import'")).rows[0].n,3);passed++;
const imported=(await db.query("select id from ft2_activities where name='Import'")).rows[0].id;
const before=await rev(sid);
await db.query("select ft2_delete_activity('admin@test',$1)",[imported]);
assert.equal(await rev(sid),before+1);passed++;
await rejects("select ft2_finalize('prof@test',$1,$2,'[]')",/administrateur/,[sid,await rev(sid)]);
await rejects("select ft2_finalize('admin@test',$1,0,'[]')",/changé/,[sid]);
await rejects("select ft2_finalize('admin@test',$1,$2,$3::jsonb)",/complet/,[sid,await rev(sid),JSON.stringify(Array.from({length:4},(_,i)=>({email:"p"+i+"@test",activity_id:study[1].id})))]);
assert.equal((await db.query("select count(*)::integer n from ft2_assignments where source='automatic'")).rows[0].n,0);passed++;
await rejects("select ft2_finalize('admin@test',$1,$2,'[]')",/incomplet/,[sid,await rev(sid)]);
// Fill all remaining slots, including degrees 1 and 3.
for(const degree of [1,3]){
 await add(sid,"Choix A","depassement",[9],12,degree);
 await add(sid,"Choix B","depassement",[10],12,degree);
}
const others=(await db.query("select r.email,r.degree,a.id from ft2_roster r join ft2_activities a on a.session_id=r.session_id and a.degree=r.degree and a.name in ('Choix A','Choix B') where r.session_id=$1",[sid])).rows;
const plan=[...Array.from({length:15},(_,i)=>({email:"p"+i+"@test",activity_id:i<3?study[1].id:free[1].id})),...others.map(r=>({email:r.email,activity_id:r.id}))];
await db.exec("set role service_role;");
await db.query("select ft2_finalize('admin@test',$1,$2,$3::jsonb)",[sid,await rev(sid),JSON.stringify(plan)]);
assert.equal((await db.query("select count(*)::integer n from ft2_assignments where session_id=$1",[sid])).rows[0].n,34);passed++;
assert.equal((await db.query("select ft2_finalize('admin@test',$1,0,'[]') n",[sid])).rows[0].n,0);passed++;
await rejects("select ft2_delete_activity('admin@test',$1)",/clôturée/,[free[0].id]);
await db.exec("reset role; set role anon;");
await rejects("select * from ft2_activities",/permission denied/);
await rejects("select ft2_import_activities('admin@test',1,'[]')",/permission denied/);
await db.exec("reset role; set role authenticated;");
await rejects("select * from ft2_assignments",/permission denied/);
await db.exec("reset role;");
await db.exec(schema);
assert.equal((await db.query("select count(*)::integer n from ft2_assignments")).rows[0].n,34);passed++;
const otherSession = await create();
await rejects("select ft2_delete_session('prof@test',$1)",/administrateur/,[sid]);
await db.exec("set role service_role;");
await db.query("select ft2_delete_session('admin@test',$1)",[sid]);
for (const table of ["ft2_assignments", "ft2_activities", "ft2_roster"]) {
 assert.equal((await db.query(`select count(*)::integer n from ${table} where session_id=$1`,[sid])).rows[0].n,0);passed++;
}
assert.equal((await db.query("select count(*)::integer n from ft2_sessions where id=$1",[sid])).rows[0].n,0);passed++;
assert.equal((await db.query("select count(*)::integer n from ft2_sessions where id=$1",[otherSession])).rows[0].n,1);passed++;
assert.equal((await db.query("select count(*)::integer n from ft2_people")).rows[0].n,19);passed++;
await db.exec("reset role;");

const opt = (await db.query("select ft2_create_session('admin@test','Options',current_date+2,now()-interval '1 day',now()+interval '1 day',array[2],true,true) sid")).rows[0].sid;
const optRem = await add(opt,"Rem","remediation",[9,10],1);
const optExt = await add(opt,"Ext","depassement",[9,10],2);
await rejects("select ft2_enroll('p0@test',$1,'p1@test',$2)",/l’élève/,[opt,optRem[0].id]);
await db.query("select ft2_enroll('p0@test',$1,'p0@test',$2)",[opt,optRem[0].id]);
await rejects("select ft2_enroll('p1@test',$1,'p1@test',$2)",/complet/,[opt,optRem[0].id]);
await rejects("select ft2_enroll('p0@test',$1,'p0@test',$2)",/unique constraint/,[opt,optRem[1].id]);
await db.query("select ft2_enroll('p0@test',$1,'p0@test',$2)",[opt,optExt[1].id]);
const own=(await db.query("select id from ft2_assignments where session_id=$1 and email='p0@test' and period=10",[opt])).rows[0].id;
await rejects("select ft2_cancel('p1@test',$1)",/propre/,[own]);
await db.query("select ft2_cancel('p0@test',$1)",[own]);passed++;
await db.query("select ft2_enroll('prof@test',$1,'p1@test',$2)",[opt,optExt[0].id]);
const imposed=(await db.query("select id from ft2_assignments where session_id=$1 and email='p1@test'",[opt])).rows[0].id;
await rejects("select ft2_cancel('p1@test',$1)",/propre/,[imposed]);
await db.query("select ft2_cancel('prof@test',$1)",[imposed]);passed++;
await db.query("update ft2_sessions set allow_enrichment_enrollment=false where id=$1",[opt]);
await rejects("select ft2_enroll('p1@test',$1,'p1@test',$2)",/manuelle uniquement/,[opt,optExt[0].id]);
await db.query("update ft2_sessions set allow_student_enrollment=false, allow_enrichment_enrollment=true where id=$1",[opt]);
await rejects("select ft2_enroll('p1@test',$1,'p1@test',$2)",/professeurs/,[opt,optExt[0].id]);
await db.query("select ft2_enroll('prof@test',$1,'p1@test',$2)",[opt,optExt[0].id]);passed++;
await db.query("update ft2_sessions set allow_student_enrollment=true,closes_at=now()-interval '1 second' where id=$1",[opt]);
await rejects("select ft2_enroll('p1@test',$1,'p1@test',$2)",/fermées/,[opt,optRem[1].id]);
console.log(`${passed} SQL checks passed.`);
await db.close();

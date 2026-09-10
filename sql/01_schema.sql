-- Installation initiale : tables ft2, sans aucune activité préchargée.
-- Les quotes simples sont requises pour les littéraux SQL, contrairement à Python.
begin;
create table if not exists public.ft2_people (
 email text primary key check(email = lower(trim(email))),
 name text not null,
 degree integer not null check(degree between 1 and 4),
 is_admin boolean not null default false,
 check(not is_admin or degree = 4)
);
create table if not exists public.ft2_sessions (
 id bigint generated always as identity primary key,
 title text not null check(length(trim(title)) > 0),
 event_date date not null,
 opens_at timestamptz not null,
 closes_at timestamptz not null,
 status text not null default 'open' check(status in ('open','finalized')),
 allow_student_enrollment boolean not null default false,
 allow_enrichment_enrollment boolean not null default false,
 revision bigint not null default 0,
 finalized_at timestamptz,
 finalized_by text references public.ft2_people,
 check(opens_at < closes_at),
 check(event_date >= (closes_at at time zone 'Europe/Brussels')::date)
);
create table if not exists public.ft2_roster (
 session_id bigint references public.ft2_sessions on delete cascade,
 email text references public.ft2_people,
 name text not null,
 degree integer not null check(degree between 1 and 3),
 primary key(session_id,email)
);
create table if not exists public.ft2_activities (
 id bigint generated always as identity primary key,
 session_id bigint not null references public.ft2_sessions on delete cascade,
 name text not null check(length(trim(name))>0),
 professor text not null default '',
 room text not null default '',
 kind text not null check(kind in ('remediation','depassement')),
 period integer not null check(period in (9,10)),
 degree integer not null check(degree between 1 and 3),
 capacity integer default 12 check(capacity is null or capacity>0),
 unique(session_id,id)
);
create table if not exists public.ft2_assignments (
 id bigint generated always as identity primary key,
 session_id bigint not null,
 email text not null,
 activity_id bigint not null,
 activity_name text not null,
 period integer not null check(period in (9,10)),
 source text not null check(source in ('teacher','student','automatic')),
 created_by text not null references public.ft2_people,
 created_at timestamptz not null default now(),
 foreign key(session_id,email) references public.ft2_roster,
 foreign key(session_id,activity_id) references public.ft2_activities(session_id,id),
 unique(session_id,email,period),
 unique(session_id,email,activity_name)
);
create unique index if not exists ft2_activity_name_unique on public.ft2_activities(session_id,degree,period,lower(trim(name)));

create index if not exists ft2_assignments_activity on public.ft2_assignments(activity_id);

create or replace function public.ft2_require_teacher(p_actor text,p_admin boolean default false)
returns void language plpgsql set search_path='' as $$
begin
 if not exists(select 1 from public.ft2_people where email=lower(trim(p_actor)) and degree=4 and (not p_admin or is_admin)) then
  raise exception 'Accès réservé aux professeurs autorisés (administrateur requis pour générer).';
 end if;
end $$;

create or replace function public.ft2_assignment_guard()
returns trigger language plpgsql set search_path='' as $$
declare a public.ft2_activities; s public.ft2_sessions; d integer;
begin
 select * into s from public.ft2_sessions where id=new.session_id for update;
 if not found or s.status<>'open' then raise exception 'La séance est clôturée.'; end if;
 select * into a from public.ft2_activities where id=new.activity_id and session_id=new.session_id;
 if not found then raise exception 'Activité introuvable.'; end if;
 select degree into d from public.ft2_roster where session_id=new.session_id and email=new.email;
 if d is null or d<>a.degree then raise exception 'Cette activité ne correspond pas au degré de cet élève.'; end if;
 if new.source in ('teacher','student') then
  if new.source='teacher' then
   perform public.ft2_require_teacher(new.created_by);
  elsif not s.allow_student_enrollment or new.created_by<>new.email or not exists(select 1 from public.ft2_people where email=new.created_by and degree between 1 and 3) then
   raise exception 'Inscription réservée aux professeurs ou à l’élève lui-même si autorisé.';
  end if;
  if a.kind='depassement' and not s.allow_enrichment_enrollment then raise exception 'Inscription manuelle uniquement en remédiation pour cette séance.'; end if;
  if now()<s.opens_at or now()>=s.closes_at then raise exception 'Les inscriptions sont fermées.'; end if;
 else
  perform public.ft2_require_teacher(new.created_by,true);
  if a.kind<>'depassement' then raise exception 'La répartition concerne uniquement les dépassements.'; end if;
 end if;
 if a.capacity is not null and (select count(*) from public.ft2_assignments where activity_id=a.id)>=a.capacity then
  raise exception 'Le groupe est complet (% places).', a.capacity;
 end if;
 new.period:=a.period;
 new.activity_name:=lower(trim(a.name));
 return new;
end $$;
drop trigger if exists ft2_assignment_guard on public.ft2_assignments;
create trigger ft2_assignment_guard before insert on public.ft2_assignments for each row execute function public.ft2_assignment_guard();

create or replace function public.ft2_revision()
returns trigger language plpgsql set search_path='' as $$
begin
 if tg_op='DELETE' then
  update public.ft2_sessions set revision=revision+1 where id=old.session_id;
  return old;
 end if;
 update public.ft2_sessions set revision=revision+1 where id=new.session_id;
 return new;
end $$;
drop trigger if exists ft2_assignment_revision on public.ft2_assignments;
create trigger ft2_assignment_revision after insert or delete on public.ft2_assignments for each row execute function public.ft2_revision();
drop trigger if exists ft2_activity_revision on public.ft2_activities;
create trigger ft2_activity_revision after insert or delete on public.ft2_activities for each row execute function public.ft2_revision();

create or replace function public.ft2_enroll(p_actor text,p_session bigint,p_email text,p_activity bigint)
returns void language plpgsql set search_path='' as $$
begin
 insert into public.ft2_assignments(session_id,email,activity_id,activity_name,period,source,created_by)
 values(p_session,lower(trim(p_email)),p_activity,'pending',9,case when exists(select 1 from public.ft2_people where email=lower(trim(p_actor)) and degree=4) then 'teacher' else 'student' end,lower(trim(p_actor)));
end $$;
create or replace function public.ft2_cancel(p_actor text,p_assignment bigint)
returns void language plpgsql set search_path='' as $$
declare sid bigint; s public.ft2_sessions; assignment public.ft2_assignments; is_teacher boolean;
begin
 select session_id into sid from public.ft2_assignments where id=p_assignment;
 select * into s from public.ft2_sessions where id=sid for update;
 if not found or s.status<>'open' or now()<s.opens_at or now()>=s.closes_at then raise exception 'Les inscriptions sont fermées.'; end if;
 select * into assignment from public.ft2_assignments where id=p_assignment;
 select exists(select 1 from public.ft2_people where email=lower(trim(p_actor)) and degree=4) into is_teacher;
 if not is_teacher and not (s.allow_student_enrollment and assignment.source='student' and assignment.email=lower(trim(p_actor)) and assignment.created_by=lower(trim(p_actor))) then
  raise exception 'Vous ne pouvez annuler que votre propre inscription personnelle.';
 end if;
 if assignment.source='automatic' then raise exception 'Cette affectation automatique ne peut pas être annulée.'; end if;
 delete from public.ft2_assignments where id=p_assignment;
end $$;

create or replace function public.ft2_finalize(p_actor text,p_session bigint,p_revision bigint,p_plan jsonb)
returns integer language plpgsql set search_path='' as $$
declare s public.ft2_sessions; item jsonb; n integer:=0;
begin
 perform public.ft2_require_teacher(p_actor,true);
 select * into s from public.ft2_sessions where id=p_session for update;
 if not found then raise exception 'Séance inconnue.'; end if;
 if s.status='finalized' then return 0; end if;
 if p_revision is null or s.revision<>p_revision then raise exception 'Les inscriptions ont changé. Générez à nouveau le fichier Excel.'; end if;
 if p_plan is null or jsonb_typeof(p_plan)<>'array' then raise exception 'Plan invalide.'; end if;
 for item in select * from jsonb_array_elements(p_plan) loop
  insert into public.ft2_assignments(session_id,email,activity_id,activity_name,period,source,created_by)
  values(p_session,item->>'email',(item->>'activity_id')::bigint,'pending',9,'automatic',lower(trim(p_actor)));
  n:=n+1;
 end loop;
 if exists(select 1 from public.ft2_roster r cross join (values(9),(10)) p(period)
   where r.session_id=p_session and not exists(select 1 from public.ft2_assignments x where x.session_id=p_session and x.email=r.email and x.period=p.period)) then
  raise exception 'Plan incomplet : aucun changement enregistré.';
 end if;
 update public.ft2_sessions set status='finalized',finalized_at=now(),finalized_by=lower(trim(p_actor)) where id=p_session;
 return n;
end $$;

create or replace function public.ft2_create_session(p_actor text,p_title text,p_date date,p_opens timestamptz,p_closes timestamptz,p_degrees integer[],p_allow_student_enrollment boolean default false,p_allow_enrichment_enrollment boolean default false)
returns bigint language plpgsql set search_path='' as $$
declare sid bigint;
begin
 perform public.ft2_require_teacher(p_actor,true);
 if p_degrees is null or cardinality(p_degrees)=0 or not(p_degrees <@ array[1,2,3]) or array_position(p_degrees,null) is not null then raise exception 'Sélectionnez les degrés participants.'; end if;
 insert into public.ft2_sessions(title,event_date,opens_at,closes_at,allow_student_enrollment,allow_enrichment_enrollment) values(p_title,p_date,p_opens,p_closes,p_allow_student_enrollment,p_allow_enrichment_enrollment) returning id into sid;
 insert into public.ft2_roster(session_id,email,name,degree) select sid,email,name,degree from public.ft2_people where degree=any(p_degrees);
 if not found then raise exception 'Aucun élève dans les degrés sélectionnés.'; end if;
 return sid;
end $$;

create or replace function public.ft2_add_activity(p_actor text,p_session bigint,p_name text,p_professor text,p_room text,p_kind text,p_periods integer[],p_degree integer,p_capacity integer default 12)
returns void language plpgsql set search_path='' as $$
declare s public.ft2_sessions; p integer;
begin
 perform public.ft2_require_teacher(p_actor,true);
 select * into s from public.ft2_sessions where id=p_session for update;
 if not found or s.status<>'open' then raise exception 'La séance est clôturée.'; end if;
 if not exists(select 1 from public.ft2_roster where session_id=p_session and degree=p_degree) then raise exception 'Ce degré ne participe pas à la séance.'; end if;
 if p_periods is null or cardinality(p_periods)=0 or not(p_periods <@ array[9,10]) or array_position(p_periods,null) is not null then raise exception 'Choisissez P9 et/ou P10.'; end if;
 if coalesce(trim(p_name),'')='' or coalesce(trim(p_professor),'')='' or coalesce(trim(p_room),'')='' then raise exception 'Renseignez le nom, le professeur et le local.'; end if;
 foreach p in array p_periods loop
  insert into public.ft2_activities(session_id,name,professor,room,kind,period,degree,capacity)
  values(p_session,trim(p_name),trim(p_professor),trim(p_room),p_kind,p,p_degree,p_capacity);
 end loop;
end $$;

create or replace function public.ft2_import_activities(p_actor text,p_session bigint,p_activities jsonb)
returns integer language plpgsql set search_path='' as $$
declare item jsonb; n integer:=0;
begin
 perform public.ft2_require_teacher(p_actor,true);
 if p_activities is null or jsonb_typeof(p_activities)<>'array' or jsonb_array_length(p_activities)=0 then raise exception 'Le fichier ne contient aucune activité.'; end if;
 -- Each call takes the same session lock; all inserts share this transaction.
 for item in select * from jsonb_array_elements(p_activities) loop
  perform public.ft2_add_activity(p_actor,p_session,item->>'name',item->>'professor',item->>'room',item->>'kind',array[(item->>'period')::integer],(item->>'degree')::integer,(item->>'capacity')::integer);
  n:=n+1;
 end loop;
 return n;
end $$;

create or replace function public.ft2_delete_activity(p_actor text,p_activity bigint)
returns void language plpgsql set search_path='' as $$
declare sid bigint; s public.ft2_sessions;
begin
 perform public.ft2_require_teacher(p_actor,true);
 select session_id into sid from public.ft2_activities where id=p_activity;
 if not found then raise exception 'Activité introuvable.'; end if;
 select * into s from public.ft2_sessions where id=sid for update;
 if s.status<>'open' then raise exception 'La séance est clôturée.'; end if;
 if exists(select 1 from public.ft2_assignments where activity_id=p_activity) then
  raise exception 'Des élèves sont inscrits : annulez leurs inscriptions avant de supprimer cette activité.';
 end if;
 delete from public.ft2_activities where id=p_activity;
end $$;

create or replace function public.ft2_delete_session(p_actor text,p_session bigint)
returns void language plpgsql set search_path='' as $$
begin
 perform public.ft2_require_teacher(p_actor,true);
 perform 1 from public.ft2_sessions where id=p_session for update;
 if not found then raise exception 'Séance introuvable.'; end if;
 -- Explicit order preserves the existing foreign keys and removes every child.
 delete from public.ft2_assignments where session_id=p_session;
 delete from public.ft2_activities where session_id=p_session;
 delete from public.ft2_roster where session_id=p_session;
 delete from public.ft2_sessions where id=p_session;
end $$;

-- Microsoft identity is verified by Streamlit; actor never comes from a form.
-- Service-role access only, invoker functions, no client-side database access.
do $$
declare obj text; fn record;
begin
 foreach obj in array array['ft2_people','ft2_sessions','ft2_roster','ft2_activities','ft2_assignments'] loop
  execute format('alter table public.%I enable row level security',obj);
  execute format('revoke all on public.%I from public,anon,authenticated',obj);
  execute format('grant select on public.%I to service_role',obj);
 end loop;
 for fn in select p.oid::regprocedure as signature from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and p.proname in
 ('ft2_require_teacher','ft2_assignment_guard','ft2_revision','ft2_enroll','ft2_cancel','ft2_finalize','ft2_create_session','ft2_add_activity','ft2_import_activities','ft2_delete_activity','ft2_delete_session') loop
  execute format('revoke all on function %s from public,anon,authenticated',fn.signature);
  execute format('grant execute on function %s to service_role',fn.signature);
 end loop;
end $$;
grant insert,update,delete on public.ft2_sessions,public.ft2_roster,public.ft2_activities,public.ft2_assignments to service_role;
grant usage,select on sequence public.ft2_sessions_id_seq,public.ft2_activities_id_seq,public.ft2_assignments_id_seq to service_role;
commit;

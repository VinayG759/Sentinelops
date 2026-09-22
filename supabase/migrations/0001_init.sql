-- SentinelOps AI — initial schema.
-- The backend writes through a direct Postgres connection (bypasses RLS).
-- The frontend only reads, via Supabase Realtime / REST, as an authenticated user.

-- ── Roles ────────────────────────────────────────────────────────────────
create type public.app_role as enum ('viewer', 'responder', 'approver', 'admin');

create table public.profiles (
  id         uuid primary key references auth.users (id) on delete cascade,
  email      text,
  role       public.app_role not null default 'viewer',
  created_at timestamptz not null default now()
);

-- Every new sign-up gets a profile with the lowest role.
create function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  insert into public.profiles (id, email) values (new.id, new.email);
  return new;
end $$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ── Service registry (only real services) ────────────────────────────────
create table public.services (
  name          text primary key,
  kind          text not null check (kind in ('service', 'database')),
  deployment    text not null,
  namespace     text not null default 'default',
  metric_prefix text,
  depends_on    text[] not null default '{}'
);

insert into public.services (name, kind, deployment, metric_prefix, depends_on) values
  ('order-service',   'service',  'order-service',   'order',   '{postgres}'),
  ('payment-service', 'service',  'payment-service', 'payment', '{postgres}'),
  ('postgres',        'database', 'postgres',        null,      '{}');

-- ── Incidents ────────────────────────────────────────────────────────────
create table public.incidents (
  id           uuid primary key default gen_random_uuid(),
  service      text not null references public.services (name),
  signal       text not null,
  severity     text not null check (severity in ('sev1', 'sev2', 'sev3')),
  status       text not null default 'triggered'
               check (status in ('triggered', 'acknowledged', 'resolved')),
  fingerprint  text not null,
  title        text not null,
  fs_ticket_id bigint,
  opened_at    timestamptz not null default now(),
  resolved_at  timestamptz
);

-- At most one open incident per (service, signal).
create unique index incidents_one_open_per_fingerprint
  on public.incidents (fingerprint) where status <> 'resolved';

-- ── Events: append-only log = audit trail = incident timeline ────────────
create table public.events (
  id          bigint generated always as identity primary key,
  incident_id uuid references public.incidents (id),
  type        text not null,
  actor       text not null,            -- 'system' | 'agent' | 'user:<uuid>' | 'freshservice'
  payload     jsonb not null default '{}',
  created_at  timestamptz not null default clock_timestamp(),
  prev_hash   text not null,
  hash        text not null
);

create index events_incident_idx on public.events (incident_id, id);

-- The canonical text that gets hashed. Timestamps as epoch microseconds so the
-- result never depends on the session's time zone.
create function public.event_digest_input(e public.events) returns text
language sql immutable as $$
  select concat_ws('|',
    e.prev_hash, e.id::text, coalesce(e.incident_id::text, ''), e.type, e.actor,
    e.payload::text, (extract(epoch from e.created_at) * 1000000)::bigint::text)
$$;

-- Seal each new event with a hash that covers the previous event's hash.
-- The advisory lock serialises inserts so two writers can't chain onto the same parent.
create function public.seal_event() returns trigger
language plpgsql as $$
begin
  perform pg_advisory_xact_lock(hashtext('public.events.chain'));
  select coalesce((select hash from public.events order by id desc limit 1), 'genesis')
    into new.prev_hash;
  new.hash := encode(sha256(convert_to(public.event_digest_input(new), 'UTF8')), 'hex');
  return new;
end $$;

create trigger events_seal
  before insert on public.events
  for each row execute function public.seal_event();

create function public.reject_event_mutation() returns trigger
language plpgsql as $$
begin
  raise exception 'events is append-only (% rejected)', tg_op;
end $$;

create trigger events_no_update before update on public.events
  for each row execute function public.reject_event_mutation();
create trigger events_no_delete before delete on public.events
  for each row execute function public.reject_event_mutation();
create trigger events_no_truncate before truncate on public.events
  for each statement execute function public.reject_event_mutation();

-- Walk the chain; report the first event whose seal doesn't match.
create function public.verify_event_chain()
returns table (valid boolean, checked bigint, first_broken_id bigint)
language plpgsql stable as $$
declare
  e        public.events;
  expected text := 'genesis';
  n        bigint := 0;
begin
  for e in select * from public.events order by id loop
    n := n + 1;
    if e.prev_hash <> expected
       or e.hash <> encode(sha256(convert_to(public.event_digest_input(e), 'UTF8')), 'hex') then
      return query select false, n, e.id;
      return;
    end if;
    expected := e.hash;
  end loop;
  return query select true, n, null::bigint;
end $$;

-- ── Remediation ──────────────────────────────────────────────────────────
create table public.proposals (
  id                 uuid primary key default gen_random_uuid(),
  incident_id        uuid not null references public.incidents (id),
  action             text not null,
  params             jsonb not null,
  rationale          text not null,
  risk               text not null check (risk in ('low', 'medium', 'high')),
  approvals_required int  not null default 1,
  status             text not null default 'pending'
                     check (status in ('pending', 'approved', 'rejected', 'expired', 'executed')),
  fs_change_id       bigint,
  created_at         timestamptz not null default now(),
  expires_at         timestamptz not null default now() + interval '15 minutes'
);

create table public.approvals (
  id          uuid primary key default gen_random_uuid(),
  proposal_id uuid not null references public.proposals (id),
  user_id     uuid references auth.users (id),
  source      text not null default 'sentinelops' check (source in ('sentinelops', 'freshservice')),
  decision    text not null check (decision in ('approved', 'rejected')),
  reason      text,
  created_at  timestamptz not null default now()
);

create table public.executions (
  id          uuid primary key default gen_random_uuid(),
  proposal_id uuid not null unique references public.proposals (id),  -- one run per proposal
  status      text not null default 'running'
              check (status in ('running', 'succeeded', 'failed', 'rolled_back')),
  before      jsonb,
  result      jsonb,
  started_at  timestamptz not null default now(),
  finished_at timestamptz
);

-- ── Global switches ──────────────────────────────────────────────────────
create table public.settings (
  id              boolean primary key default true check (id),  -- single row
  autonomy_paused boolean not null default false
);
insert into public.settings default values;

-- ── Row-level security: signed-in users may read; nobody writes via the API ──
alter table public.profiles   enable row level security;
alter table public.services   enable row level security;
alter table public.incidents  enable row level security;
alter table public.events     enable row level security;
alter table public.proposals  enable row level security;
alter table public.approvals  enable row level security;
alter table public.executions enable row level security;
alter table public.settings   enable row level security;

create policy "read own profile" on public.profiles
  for select to authenticated using (id = auth.uid());

create policy "read" on public.services   for select to authenticated using (true);
create policy "read" on public.incidents  for select to authenticated using (true);
create policy "read" on public.events     for select to authenticated using (true);
create policy "read" on public.proposals  for select to authenticated using (true);
create policy "read" on public.approvals  for select to authenticated using (true);
create policy "read" on public.executions for select to authenticated using (true);
create policy "read" on public.settings   for select to authenticated using (true);

-- ── Realtime: the UI subscribes to these ─────────────────────────────────
alter publication supabase_realtime
  add table public.incidents, public.events, public.proposals, public.settings;

-- Event chain: make id order and chain order the same, and disclose the one known fault.
--
-- The bug: `id` was assigned (identity default) BEFORE the trigger took the chain lock.
-- Two concurrent inserts could get ids 568 and 569, reach the lock in the opposite order,
-- and chain 569 -> 567 then 568 -> 569 (and later 570 -> 569). Contents were intact, but
-- the verifier walks in id order, so it reported the chain as broken. Found 25 Sep 2026.

-- 1. Assign the id under the lock: ids now follow seal order, so the race cannot recur.
create or replace function public.seal_event() returns trigger
language plpgsql as $$
begin
  perform pg_advisory_xact_lock(hashtext('public.events.chain'));
  new.id := nextval(pg_get_serial_sequence('public.events', 'id'));
  select coalesce((select hash from public.events order by id desc limit 1), 'genesis')
    into new.prev_hash;
  new.hash := encode(sha256(convert_to(public.event_digest_input(new), 'UTF8')), 'hex');
  return new;
end $$;

-- 2. Known faults: events whose link is crossed by that race but whose contents still match
--    their own seal. Append-only and shown on the audit page, so nothing is hidden.
create table public.event_chain_exceptions (
  event_id    bigint primary key references public.events (id),
  reason      text not null,
  recorded_at timestamptz not null default now()
);
alter table public.event_chain_exceptions enable row level security;

create trigger event_chain_exceptions_no_update before update on public.event_chain_exceptions
  for each row execute function public.reject_event_mutation();
create trigger event_chain_exceptions_no_delete before delete on public.event_chain_exceptions
  for each row execute function public.reject_event_mutation();

-- Only link faults with intact contents qualify: an edited event fails its own seal and is
-- never listed here.
insert into public.event_chain_exceptions (event_id, reason)
select e.id,
       'Sequencing fault from concurrent inserts before migration 0002: the link points to '
       || 'a neighbouring event; contents verified intact against their own seal.'
from public.events e
join public.events p on p.id = e.id - 1
where e.prev_hash <> p.hash
  and e.hash = encode(sha256(convert_to(public.event_digest_input(e), 'UTF8')), 'hex');

-- 3. Verify: every event's contents must match its seal (no exceptions); the link check is
--    skipped only for listed known faults, which are reported alongside the result.
drop function public.verify_event_chain();
create function public.verify_event_chain()
returns table (valid boolean, checked bigint, first_broken_id bigint, known_exceptions bigint[])
language plpgsql stable as $$
declare
  e        public.events;
  expected text := 'genesis';
  n        bigint := 0;
  known    bigint[] := array(select event_id from public.event_chain_exceptions order by 1);
begin
  for e in select * from public.events order by id loop
    n := n + 1;
    if e.hash <> encode(sha256(convert_to(public.event_digest_input(e), 'UTF8')), 'hex')
       or (e.prev_hash <> expected and not e.id = any(known)) then
      return query select false, n, e.id, known;
      return;
    end if;
    expected := e.hash;
  end loop;
  return query select true, n, null::bigint, known;
end $$;

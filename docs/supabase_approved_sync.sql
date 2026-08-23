-- Project: Reus
-- Developer: lotfi Mahiddine
-- Organization: Reulink
--
-- Apply this schema only if the developer chooses to enable a Supabase mirror
-- for approved events. This table never stores raw memory, secrets, or chat content.

create table if not exists public.reus_sync_events (
  event_id text primary key,
  kind text not null check (char_length(kind) between 1 and 120),
  summary text not null check (char_length(summary) <= 4000),
  occurred_at timestamptz not null,
  status text not null check (status in ('approved', 'rejected', 'archived')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.reus_sync_events enable row level security;

-- No public policies are created intentionally. Only the Reus backend writes
-- with a service key stored in its secure environment; the browser receives no direct table access.

create or replace function public.touch_reus_sync_events_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = public
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists reus_sync_events_touch_updated_at on public.reus_sync_events;
create trigger reus_sync_events_touch_updated_at
before update on public.reus_sync_events
for each row execute procedure public.touch_reus_sync_events_updated_at();

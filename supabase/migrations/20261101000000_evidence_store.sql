-- GAP-023: run evidence store (contract evidence-store/1; crm/evidence_store.py).
--
-- Review, then apply once to the Supabase project: in the dashboard's SQL
-- editor, or by Claude through the Supabase connector with the owner's go.
-- It holds no project identifiers or credentials.
--
-- What it sets up:
--   * a private bucket, run-evidence (no public reads);
--   * public.evidence_writers: the Auth users allowed to write evidence; the
--     owner adds the one writer's user id by hand (see docs/evidence-store.md);
--   * storage policies granting that writer INSERT and SELECT on the bucket,
--     and nothing else. With no UPDATE policy there is no overwrite (upsert
--     needs SELECT and UPDATE); with no DELETE policy there is no delete;
--   * public.evidence_registry: one append-only row per run (manifest hash,
--     fingerprint, retention date), outside the bucket, as the independent
--     record the filing gate cross-checks. The writer may insert and read it,
--     never update or delete it.
--
-- The service-role key still bypasses every policy here. It is for the owner's
-- administration only and is never given to a filing run.

insert into storage.buckets (id, name, public)
values ('run-evidence', 'run-evidence', false)
on conflict (id) do nothing;

create table if not exists public.evidence_writers (
  user_id uuid primary key references auth.users (id) on delete cascade,
  added_at timestamptz not null default now()
);
alter table public.evidence_writers enable row level security;
-- No policies: only the owner (dashboard, service role) can read or change it.

create or replace function public.is_evidence_writer()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (select 1 from public.evidence_writers where user_id = (select auth.uid()))
$$;
revoke all on function public.is_evidence_writer() from public;
grant execute on function public.is_evidence_writer() to authenticated;

create policy "evidence writer inserts run evidence"
on storage.objects for insert to authenticated
with check (bucket_id = 'run-evidence' and (select public.is_evidence_writer()));

create policy "evidence writer reads run evidence"
on storage.objects for select to authenticated
using (bucket_id = 'run-evidence' and (select public.is_evidence_writer()));

create table if not exists public.evidence_registry (
  run_id             text primary key check (run_id ~ '^[A-Za-z0-9_.-]+$'),
  contract           text not null,
  manifest_sha256    text not null check (manifest_sha256 ~ '^[0-9a-f]{64}$'),
  inputs_fingerprint text not null check (inputs_fingerprint ~ '^fp_[0-9a-f]{64}$'),
  file_count         integer not null check (file_count > 0),
  created_at         timestamptz not null,
  retain_until       date not null,
  registered_by      uuid not null default auth.uid(),
  registered_at      timestamptz not null default now()
);
alter table public.evidence_registry enable row level security;

revoke all on public.evidence_registry from anon, authenticated;
grant select, insert on public.evidence_registry to authenticated;

create policy "evidence writer registers a run"
on public.evidence_registry for insert to authenticated
with check ((select public.is_evidence_writer()) and registered_by = (select auth.uid()));

create policy "evidence writer reads the registry"
on public.evidence_registry for select to authenticated
using ((select public.is_evidence_writer()));

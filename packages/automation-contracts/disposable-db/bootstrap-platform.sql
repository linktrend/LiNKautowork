create schema if not exists platform;
alter database automation_contracts set lautowork.test_context = 'on';
do $$ begin if not exists(select 1 from pg_roles where rolname='service_role') then create role service_role nologin; end if; end $$;
do $$ begin if not exists(select 1 from pg_roles where rolname='wrong_runtime') then create role wrong_runtime nologin; end if; end $$;
create type platform.member_role as enum ('client_viewer');
create table platform.organizations (
  id uuid primary key,
  slug text not null unique
);
create or replace function platform.has_org_access(target_org_id uuid, minimum_role platform.member_role)
returns boolean
language sql
stable
as $$
  select current_setting('request.jwt.claim.org_id', true) = target_org_id::text;
$$;

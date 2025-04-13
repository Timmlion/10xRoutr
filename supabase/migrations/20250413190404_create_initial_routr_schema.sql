-- migration: 20250413190404_create_initial_routr_schema.sql
-- description: Creates the initial tables, types, functions, triggers, indexes, and RLS policies for the routr MVP.
-- affected_tables: routr_links, routing_rules
-- special_considerations:
--   - Defines custom ENUM types for rule and target types.
--   - Implements automatic 'updated_at' timestamp updates via triggers.
--   - Sets up Row Level Security (RLS) for user data isolation.
--   - Cascade delete for user deletion from 'auth.users' needs separate handling (e.g., Edge Function).
--   - HTML size limit CHECK constraint on 'routing_rules.target_value' is deferred.

-- step: create custom enum types
-- purpose: define allowed values for rule and target types to ensure data consistency.
create type public.rule_type_enum as enum ('time', 'clicks');
comment on type public.rule_type_enum is 'defines the possible types for a routing rule''s condition';

create type public.target_type_enum as enum ('url', 'html');
comment on type public.target_type_enum is 'defines the possible types for a routing rule''s target destination';

-- step: create routr_links table
-- purpose: store the main information about each unique routr link created by users.
create table public.routr_links (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade, -- note: cascade needs external handling (e.g., edge function) for auth.users deletion.
  alias text not null unique check (
    alias ~ '^[a-z0-9-]+$' -- only lowercase letters, numbers, and hyphens
    and length(alias) >= 3    -- minimum length of 3
    and length(alias) <= 64   -- maximum length of 64
  ),
  default_url text null check (
    default_url is null or -- allow null
    (default_url like 'http://%' or default_url like 'https://%') -- basic url format check if not null
  ),
  total_clicks bigint not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- add comments to columns for clarity
comment on column public.routr_links.id is 'primary key for the link';
comment on column public.routr_links.user_id is 'owner of the link (references auth.users)';
comment on column public.routr_links.alias is 'unique path segment for the link url (e.g., "my-campaign")';
comment on column public.routr_links.default_url is 'optional fallback url if no rules match';
comment on column public.routr_links.total_clicks is 'counter for total clicks on this link alias';
comment on column public.routr_links.created_at is 'timestamp when the link was created';
comment on column public.routr_links.updated_at is 'timestamp when the link was last updated';

-- enable row level security immediately upon table creation.
alter table public.routr_links enable row level security;

-- step: create routing_rules table
-- purpose: store the specific redirection rules associated with each routr_link.
create table public.routing_rules (
  id uuid primary key default gen_random_uuid(),
  link_id uuid not null references public.routr_links(id) on delete cascade, -- deleting a link cascades to its rules.
  priority smallint not null check (priority > 0), -- priorities should be positive integers.
  rule_type public.rule_type_enum not null,
  target_type public.target_type_enum not null,
  target_value text not null, -- stores url or html content.
  start_time timestamptz null, -- required if rule_type is 'time'.
  end_time timestamptz null,   -- required if rule_type is 'time'.
  max_clicks bigint null check (max_clicks is null or max_clicks > 0), -- required if rule_type is 'clicks', must be positive.
  current_clicks bigint not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  -- ensure priority is unique for each link.
  constraint routing_rules_link_id_priority_key unique (link_id, priority),

  -- ensure time rules have start and end times.
  constraint time_rule_requires_times check (
    rule_type != 'time' or (start_time is not null and end_time is not null)
  ),

  -- ensure click rules have a max_clicks value.
  constraint clicks_rule_requires_max check (
    rule_type != 'clicks' or max_clicks is not null
  ),

  -- ensure target url has basic format if type is 'url'.
  constraint target_url_format check (
    target_type != 'url' or (target_value like 'http://%' or target_value like 'https://%')
  )

  -- todo: add check constraint for target_html_length once limit is defined.
  -- example: constraint target_html_length check (target_type != 'html' or length(target_value) <= 100000) -- limit to 100kb
);

-- add comments to columns for clarity
comment on column public.routing_rules.id is 'primary key for the rule';
comment on column public.routing_rules.link_id is 'foreign key referencing the parent link';
comment on column public.routing_rules.priority is 'execution priority (lower number = higher priority), unique per link';
comment on column public.routing_rules.rule_type is 'type of condition for this rule (time or clicks)';
comment on column public.routing_rules.target_type is 'type of destination (url or html)';
comment on column public.routing_rules.target_value is 'the destination url or the raw html content';
comment on column public.routing_rules.start_time is 'start time for time-based rules (utc)';
comment on column public.routing_rules.end_time is 'end time for time-based rules (utc)';
comment on column public.routing_rules.max_clicks is 'maximum number of clicks for clicks-based rules';
comment on column public.routing_rules.current_clicks is 'counter for clicks specifically hitting this rule';
comment on column public.routing_rules.created_at is 'timestamp when the rule was created';
comment on column public.routing_rules.updated_at is 'timestamp when the rule was last updated';

-- enable row level security immediately upon table creation.
alter table public.routing_rules enable row level security;

-- step: create helper function and triggers for updated_at timestamp
-- purpose: automatically update the 'updated_at' column whenever a row is modified.
create or replace function public.handle_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql security definer; -- security definer allows function to run with definer's privileges, common for triggers.

-- trigger for routr_links table
create trigger on_routr_links_updated
  before update on public.routr_links
  for each row
  execute procedure public.handle_updated_at();

-- trigger for routing_rules table
create trigger on_routing_rules_updated
  before update on public.routing_rules
  for each row
  execute procedure public.handle_updated_at();

-- step: create indexes for performance
-- purpose: speed up common query patterns like finding links by alias and ordering rules by priority.
create index idx_routr_links_alias on public.routr_links(alias);
comment on index public.idx_routr_links_alias is 'index for fast link lookups by alias (used in redirection)';

create index idx_routing_rules_link_id_priority on public.routing_rules(link_id, priority);
comment on index public.idx_routing_rules_link_id_priority is 'index for fast retrieval and sorting of rules by link_id and priority (used in redirection)';

-- step: define row level security (rls) policies
-- purpose: restrict data access based on user authentication status and ownership.
-- note: backend api performing public redirection must use service_role key to bypass these.

-- policies for routr_links table
-- policy: allow authenticated users to select their own links.
create policy "allow authenticated select on own links"
  on public.routr_links for select
  to authenticated
  using (auth.uid() = user_id);

-- policy: allow authenticated users to insert new links for themselves.
create policy "allow authenticated insert on own links"
  on public.routr_links for insert
  to authenticated
  with check (auth.uid() = user_id);

-- policy: allow authenticated users to update their own links.
create policy "allow authenticated update on own links"
  on public.routr_links for update
  to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id); -- check ensures they cannot change the user_id to someone else's.

-- policy: allow authenticated users to delete their own links.
create policy "allow authenticated delete on own links"
  on public.routr_links for delete
  to authenticated
  using (auth.uid() = user_id);

-- policies for routing_rules table
-- policy: allow authenticated users to select rules belonging to their own links.
create policy "allow authenticated select on own link rules"
  on public.routing_rules for select
  to authenticated
  using (link_id in (select id from public.routr_links where auth.uid() = user_id));

-- policy: allow authenticated users to insert rules for their own links.
create policy "allow authenticated insert on own link rules"
  on public.routing_rules for insert
  to authenticated
  with check (link_id in (select id from public.routr_links where auth.uid() = user_id));

-- policy: allow authenticated users to update rules belonging to their own links.
create policy "allow authenticated update on own link rules"
  on public.routing_rules for update
  to authenticated
  using (link_id in (select id from public.routr_links where auth.uid() = user_id))
  with check (link_id in (select id from public.routr_links where auth.uid() = user_id)); -- check prevents moving rule to another user's link.

-- policy: allow authenticated users to delete rules belonging to their own links.
create policy "allow authenticated delete on own link rules"
  on public.routing_rules for delete
  to authenticated
  using (link_id in (select id from public.routr_links where auth.uid() = user_id));

-- note: no policies are granted to the 'anon' role for modifying or selecting user-specific data in these tables.
-- public access for redirection is handled by the backend using the service_role key.
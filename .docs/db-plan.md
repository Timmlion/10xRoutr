# PostgreSQL Database Schema for routr (MVP)

This document outlines the database schema designed for the _routr_ MVP application, based on the project requirements and planning decisions. The schema is intended for use with PostgreSQL within a Supabase environment.

## 1. Custom Types (ENUMs)

```sql
-- Defines the possible types for a routing rule's condition
CREATE TYPE public.rule_type_enum AS ENUM ('time', 'clicks');

-- Defines the possible types for a routing rule's target destination
CREATE TYPE public.target_type_enum AS ENUM ('url', 'html');
```

````

## 2. Tables

### 2.1. `routr_links`

Stores the main information about each unique routr link created by users.

```sql
CREATE TABLE public.routr_links (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE, -- Note: Cascade needs to be handled via Edge Function for auth.users deletion
  alias TEXT NOT NULL UNIQUE CHECK (
    alias ~ '^[a-z0-9-]+$' -- Only lowercase letters, numbers, and hyphens
    AND length(alias) >= 3    -- Minimum length of 3
    AND length(alias) <= 64   -- Maximum length of 64
  ),
  default_url TEXT NULL CHECK (
    default_url IS NULL OR -- Allow NULL
    (default_url LIKE 'http://%' OR default_url LIKE 'https://%') -- Basic URL format check if not NULL
  ),
  total_clicks BIGINT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Add comments to columns
COMMENT ON COLUMN public.routr_links.id IS 'Primary key for the link';
COMMENT ON COLUMN public.routr_links.user_id IS 'Owner of the link (references auth.users)';
COMMENT ON COLUMN public.routr_links.alias IS 'Unique path segment for the link URL (e.g., "my-campaign")';
COMMENT ON COLUMN public.routr_links.default_url IS 'Optional fallback URL if no rules match';
COMMENT ON COLUMN public.routr_links.total_clicks IS 'Counter for total clicks on this link alias';
COMMENT ON COLUMN public.routr_links.created_at IS 'Timestamp when the link was created';
COMMENT ON COLUMN public.routr_links.updated_at IS 'Timestamp when the link was last updated';
```

### 2.2. `routing_rules`

Stores the specific redirection rules associated with each `routr_link`.

```sql
CREATE TABLE public.routing_rules (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  link_id UUID NOT NULL REFERENCES public.routr_links(id) ON DELETE CASCADE,
  priority SMALLINT NOT NULL CHECK (priority > 0), -- Priorities should be positive integers
  rule_type public.rule_type_enum NOT NULL,
  target_type public.target_type_enum NOT NULL,
  target_value TEXT NOT NULL, -- Stores URL or HTML content
  start_time TIMESTAMPTZ NULL, -- Required if rule_type is 'time'
  end_time TIMESTAMPTZ NULL,   -- Required if rule_type is 'time'
  max_clicks BIGINT NULL CHECK (max_clicks IS NULL OR max_clicks > 0), -- Required if rule_type is 'clicks', must be positive
  current_clicks BIGINT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  -- Ensure priority is unique for each link
  CONSTRAINT routing_rules_link_id_priority_key UNIQUE (link_id, priority),

  -- Ensure time rules have start and end times
  CONSTRAINT time_rule_requires_times CHECK (
    rule_type != 'time' OR (start_time IS NOT NULL AND end_time IS NOT NULL)
  ),

  -- Ensure click rules have a max_clicks value
  CONSTRAINT clicks_rule_requires_max CHECK (
    rule_type != 'clicks' OR max_clicks IS NOT NULL
  ),

  -- Ensure target URL has basic format if type is 'url'
  CONSTRAINT target_url_format CHECK (
    target_type != 'url' OR (target_value LIKE 'http://%' OR target_value LIKE 'https://%')
  )

  -- Note: A CHECK constraint for HTML target_value length can be added here once the limit is defined.
  -- Example: CONSTRAINT target_html_length CHECK (target_type != 'html' OR length(target_value) <= 100000) -- Limit to 100KB
);

-- Add comments to columns
COMMENT ON COLUMN public.routing_rules.id IS 'Primary key for the rule';
COMMENT ON COLUMN public.routing_rules.link_id IS 'Foreign key referencing the parent link';
COMMENT ON COLUMN public.routing_rules.priority IS 'Execution priority (lower number = higher priority), unique per link';
COMMENT ON COLUMN public.routing_rules.rule_type IS 'Type of condition for this rule (time or clicks)';
COMMENT ON COLUMN public.routing_rules.target_type IS 'Type of destination (url or html)';
COMMENT ON COLUMN public.routing_rules.target_value IS 'The destination URL or the raw HTML content';
COMMENT ON COLUMN public.routing_rules.start_time IS 'Start time for time-based rules (UTC)';
COMMENT ON COLUMN public.routing_rules.end_time IS 'End time for time-based rules (UTC)';
COMMENT ON COLUMN public.routing_rules.max_clicks IS 'Maximum number of clicks for clicks-based rules';
COMMENT ON COLUMN public.routing_rules.current_clicks IS 'Counter for clicks specifically hitting this rule';
COMMENT ON COLUMN public.routing_rules.created_at IS 'Timestamp when the rule was created';
COMMENT ON COLUMN public.routing_rules.updated_at IS 'Timestamp when the rule was last updated';

```

## 3. Relationships

- **`auth.users` (1) -> (N) `routr_links`:** A user can have multiple routr links. The `user_id` column in `routr_links` links to `auth.users(id)`. Cascade delete from `auth.users` needs to be handled via a Supabase Edge Function.
- **`routr_links` (1) -> (N) `routing_rules`:** A routr link can have multiple routing rules. The `link_id` column in `routing_rules` links to `routr_links(id)` with `ON DELETE CASCADE` enabled, so deleting a link automatically deletes its associated rules.

## 4. Helper Functions and Triggers

### 4.1. `handle_updated_at` Function

A reusable function to automatically update the `updated_at` timestamp.

```sql
CREATE OR REPLACE FUNCTION public.handle_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Set security definer for function ownership (common practice for triggers)
```

### 4.2. Triggers for `updated_at`

Triggers to call the `handle_updated_at` function before an update on the specified tables.

```sql
-- Trigger for routr_links
CREATE TRIGGER on_routr_links_updated
  BEFORE UPDATE ON public.routr_links
  FOR EACH ROW
  EXECUTE PROCEDURE public.handle_updated_at();

-- Trigger for routing_rules
CREATE TRIGGER on_routing_rules_updated
  BEFORE UPDATE ON public.routing_rules
  FOR EACH ROW
  EXECUTE PROCEDURE public.handle_updated_at();
```

## 5. Indexes

Indexes are created to optimize query performance. Indexes on Primary Keys (`id`) and Foreign Keys (`user_id`, `link_id`) are typically created automatically by PostgreSQL.

```sql
-- Index for fast lookups based on the link alias (used for redirection)
CREATE INDEX idx_routr_links_alias ON public.routr_links(alias);

-- Index for fast retrieval and sorting of rules based on link and priority (used for redirection logic)
CREATE INDEX idx_routing_rules_link_id_priority ON public.routing_rules(link_id, priority);
```

## 6. Row Level Security (RLS) Policies

RLS is enabled to ensure users can only access and modify their own data through the API when authenticated with their JWT. The public redirection mechanism in the backend API will need to use the `service_role` key to bypass these policies when reading rules based on the alias.

```sql
-- Enable RLS on the tables
ALTER TABLE public.routr_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.routing_rules ENABLE ROW LEVEL SECURITY;

-- Policies for routr_links
CREATE POLICY "Allow user full access on own links"
  ON public.routr_links
  FOR ALL -- Covers SELECT, INSERT, UPDATE, DELETE
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-- Policies for routing_rules
CREATE POLICY "Allow user full access on rules of own links"
  ON public.routing_rules
  FOR ALL -- Covers SELECT, INSERT, UPDATE, DELETE
  USING (link_id IN (SELECT id FROM public.routr_links WHERE auth.uid() = user_id))
  WITH CHECK (link_id IN (SELECT id FROM public.routr_links WHERE auth.uid() = user_id));

-- Note: The backend redirection logic MUST use the service_role key
-- or a SECURITY DEFINER function to read rules for any alias, bypassing these user-specific policies.
```

## 7. Additional Notes

- **User Deletion Cascade:** The `ON DELETE CASCADE` for `routr_links.user_id` referencing `auth.users` is commented out as Supabase Auth deletion doesn't automatically trigger standard PostgreSQL cascades on public tables. This logic needs to be implemented via a **Supabase Edge Function** triggered by user deletion events.
- **HTML Size Limit:** A specific `CHECK` constraint for the length of `routing_rules.target_value` when `target_type` is 'html' should be added once a definitive limit is decided.
- **Click Count Atomicity:** The backend application logic _must_ ensure that updates to `total_clicks` and `current_clicks` are performed using atomic operations (e.g., `UPDATE table SET counter = counter + 1 WHERE ...`) to prevent race conditions under concurrent load.
````

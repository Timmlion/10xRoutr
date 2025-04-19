-- Function to atomically increment total_clicks on a specific routr_link
-- Returns void (nothing) as it just performs an update.
-- Takes the link's UUID as input.
CREATE OR REPLACE FUNCTION public.increment_link_clicks(link_uuid uuid)
RETURNS void -- Można też zwrócić np. zaktualizowaną wartość licznika (RETURNS bigint)
LANGUAGE sql
VOLATILE -- Indicates the function has side effects (modifies data) and results can change within a transaction
-- SECURITY DEFINER -- Uruchamia funkcję z uprawnieniami twórcy (zazwyczaj postgres), omijając RLS.
                     -- To jest potrzebne, bo wywołujemy ją z kluczem service_role, który i tak omija RLS,
                     -- ale jest to dobra praktyka dla funkcji modyfikujących dane.
AS $$
  UPDATE public.routr_links
  SET total_clicks = total_clicks + 1
  WHERE id = link_uuid;
$$;

-- Opcjonalnie: Dodaj komentarz do funkcji
COMMENT ON FUNCTION public.increment_link_clicks(uuid) IS 'Atomically increments the total_clicks counter for a given routr_link ID.';

-- Opcjonalnie: Udziel uprawnień do wykonania tej funkcji roli 'service_role'
-- Chociaż service_role ma zwykle pełne uprawnienia, jawne nadanie jest dobrą praktyką.
-- Role supabase ('postgres', 'anon', 'authenticated', 'service_role') mogą się różnić. Sprawdź swoje role.
-- Zakładając standardowe role Supabase:
GRANT EXECUTE ON FUNCTION public.increment_link_clicks(uuid) TO service_role;
-- Można też nadać innym rolom, jeśli potrzebne, ale dla redirection potrzebuje tylko service_role.
-- GRANT EXECUTE ON FUNCTION public.increment_link_clicks(uuid) TO postgres; -- Właściciel
-- GRANT EXECUTE ON FUNCTION public.increment_link_clicks(uuid) TO authenticated; -- Raczej niepotrzebne

-- Function to atomically increment current_clicks on a specific routing_rule
-- Returns void (nothing).
-- Takes the rule's UUID as input.
CREATE OR REPLACE FUNCTION public.increment_rule_clicks(rule_uuid uuid)
RETURNS void
LANGUAGE sql
VOLATILE
-- SECURITY DEFINER -- Jak wyżej, dobra praktyka dla funkcji modyfikujących
AS $$
  UPDATE public.routing_rules
  SET current_clicks = current_clicks + 1
  WHERE id = rule_uuid;
$$;

-- Opcjonalnie: Dodaj komentarz
COMMENT ON FUNCTION public.increment_rule_clicks(uuid) IS 'Atomically increments the current_clicks counter for a given routing_rule ID.';

-- Opcjonalnie: Udziel uprawnień
GRANT EXECUTE ON FUNCTION public.increment_rule_clicks(uuid) TO service_role;
-- GRANT EXECUTE ON FUNCTION public.increment_rule_clicks(uuid) TO postgres;
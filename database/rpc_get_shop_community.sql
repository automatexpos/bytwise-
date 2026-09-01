-- Run this in the Supabase SQL editor.
--
-- saved_shops/visited_shops RLS only lets a user see their own rows
-- ("USING (auth.uid() = user_id)"), so a regular client can never list
-- who else saved/visited a shop - that's why the UI previously had to
-- fall back to fake generated names. These SECURITY DEFINER functions
-- return just the public profile fields (id, username, avatar_url) for
-- the real users who saved/visited a shop, for the shop detail page's
-- community facepile.

CREATE OR REPLACE FUNCTION public.get_shop_savers(p_shop_id UUID, p_limit INT DEFAULT 12)
RETURNS TABLE (id UUID, username TEXT, avatar_url TEXT) AS $$
  SELECT p.id, p.username, p.avatar_url
  FROM public.saved_shops s
  JOIN public.profiles p ON p.id = s.user_id
  WHERE s.shop_id = p_shop_id
  ORDER BY s.created_at DESC
  LIMIT p_limit;
$$ LANGUAGE sql SECURITY DEFINER SET search_path = public;

CREATE OR REPLACE FUNCTION public.get_shop_visitors(p_shop_id UUID, p_limit INT DEFAULT 12)
RETURNS TABLE (id UUID, username TEXT, avatar_url TEXT) AS $$
  SELECT p.id, p.username, p.avatar_url
  FROM public.visited_shops v
  JOIN public.profiles p ON p.id = v.user_id
  WHERE v.shop_id = p_shop_id
  ORDER BY v.visited_at DESC
  LIMIT p_limit;
$$ LANGUAGE sql SECURITY DEFINER SET search_path = public;

GRANT EXECUTE ON FUNCTION public.get_shop_savers(UUID, INT) TO authenticated, anon;
GRANT EXECUTE ON FUNCTION public.get_shop_visitors(UUID, INT) TO authenticated, anon;

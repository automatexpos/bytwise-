-- Run this in the Supabase SQL editor.
--
-- Mirrors the existing stamp_count trigger on visited_shops (see
-- Supabase_project.sql) but for saved_shops, so shops.saved_count reflects
-- the real number of users who saved a shop. Needed because saved_shops'
-- RLS policy ("Users can view own saved shops" USING auth.uid() = user_id)
-- means a regular user's client can't just SELECT COUNT(*) across all
-- users' saved_shops rows for a shop.

ALTER TABLE public.shops
  ADD COLUMN IF NOT EXISTS saved_count INTEGER NOT NULL DEFAULT 0;

CREATE OR REPLACE FUNCTION public.update_saved_count()
RETURNS TRIGGER AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    UPDATE public.shops SET saved_count = saved_count + 1 WHERE id = NEW.shop_id;
    RETURN NEW;
  ELSIF TG_OP = 'DELETE' THEN
    UPDATE public.shops SET saved_count = GREATEST(0, saved_count - 1) WHERE id = OLD.shop_id;
    RETURN OLD;
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

DROP TRIGGER IF EXISTS update_saved_count_on_save ON public.saved_shops;
CREATE TRIGGER update_saved_count_on_save AFTER INSERT ON public.saved_shops
  FOR EACH ROW EXECUTE FUNCTION public.update_saved_count();

DROP TRIGGER IF EXISTS update_saved_count_on_unsave ON public.saved_shops;
CREATE TRIGGER update_saved_count_on_unsave AFTER DELETE ON public.saved_shops
  FOR EACH ROW EXECUTE FUNCTION public.update_saved_count();

-- Backfill existing shops.
UPDATE public.shops
SET saved_count = COALESCE(save_stats.count, 0)
FROM (
  SELECT shop_id, COUNT(*) AS count
  FROM public.saved_shops
  GROUP BY shop_id
) AS save_stats
WHERE public.shops.id = save_stats.shop_id;

-- The original update_stamp_count() (Supabase_project.sql) was never
-- declared SECURITY DEFINER, so its UPDATE on shops was just as subject to
-- the owner-only UPDATE RLS policy as a direct client update would be -
-- meaning stamp_count silently stopped incrementing for anyone but the
-- shop's owner. Redefine it as SECURITY DEFINER to actually bypass that.
CREATE OR REPLACE FUNCTION public.update_stamp_count()
RETURNS TRIGGER AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    UPDATE public.shops SET stamp_count = stamp_count + 1 WHERE id = NEW.shop_id;
    RETURN NEW;
  ELSIF TG_OP = 'DELETE' THEN
    UPDATE public.shops SET stamp_count = GREATEST(0, stamp_count - 1) WHERE id = OLD.shop_id;
    RETURN OLD;
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

-- Backfill stamp_count too, in case it drifted while the trigger was
-- silently getting blocked by RLS.
UPDATE public.shops
SET stamp_count = COALESCE(visit_stats.count, 0)
FROM (
  SELECT shop_id, COUNT(*) AS count
  FROM public.visited_shops
  GROUP BY shop_id
) AS visit_stats
WHERE public.shops.id = visit_stats.shop_id;

UPDATE public.shops SET stamp_count = 0
WHERE id NOT IN (SELECT DISTINCT shop_id FROM public.visited_shops);

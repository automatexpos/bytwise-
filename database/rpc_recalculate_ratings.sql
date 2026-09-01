-- Run this in the Supabase SQL editor.
--
-- shops has RLS policies that only let the claimed owner (or an admin)
-- run UPDATE on a shop row. That means an ordinary user leaving a review
-- or a "What People Say" rating can never update shops.rating/
-- review_count/people_say_rating/people_say_rating_count directly - the
-- UPDATE is silently filtered out by RLS (no error, zero rows affected),
-- which is why those averages never changed.
--
-- These two SECURITY DEFINER functions run with the privileges of the
-- function owner (bypassing the owner-only UPDATE policy) but only ever
-- recompute and write the rating columns from the underlying
-- reviews/shop_category_ratings tables, so they can't be used to modify
-- anything else about a shop.

CREATE OR REPLACE FUNCTION public.recalculate_shop_rating(p_shop_id UUID)
RETURNS VOID AS $$
BEGIN
  UPDATE public.shops
  SET
    rating = COALESCE((
      SELECT ROUND(AVG(rating)::numeric, 1) FROM public.reviews WHERE shop_id = p_shop_id
    ), 0.0),
    review_count = (
      SELECT COUNT(*) FROM public.reviews WHERE shop_id = p_shop_id
    )
  WHERE id = p_shop_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

CREATE OR REPLACE FUNCTION public.recalculate_shop_people_say_rating(p_shop_id UUID)
RETURNS VOID AS $$
BEGIN
  UPDATE public.shops
  SET
    people_say_rating = COALESCE((
      SELECT ROUND(AVG(rating)::numeric, 1) FROM public.shop_category_ratings WHERE shop_id = p_shop_id
    ), 0.0),
    people_say_rating_count = (
      SELECT COUNT(*) FROM public.shop_category_ratings WHERE shop_id = p_shop_id
    )
  WHERE id = p_shop_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

GRANT EXECUTE ON FUNCTION public.recalculate_shop_rating(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION public.recalculate_shop_people_say_rating(UUID) TO authenticated;

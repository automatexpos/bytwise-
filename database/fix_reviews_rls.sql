-- Run this in your Supabase SQL Editor to ensure reviews RLS policies
-- and rating recalculation triggers are properly configured.

-- 1. Ensure RLS is enabled on reviews
ALTER TABLE public.reviews ENABLE ROW LEVEL SECURITY;

-- 2. Drop existing policies to prevent conflicts or stale rules
DROP POLICY IF EXISTS "Reviews are viewable by everyone" ON public.reviews;
DROP POLICY IF EXISTS "Authenticated users can create reviews" ON public.reviews;
DROP POLICY IF EXISTS "Users can update own reviews" ON public.reviews;
DROP POLICY IF EXISTS "Users can delete own reviews" ON public.reviews;

-- 3. Create clean RLS policies for reviews
CREATE POLICY "Reviews are viewable by everyone"
  ON public.reviews
  FOR SELECT
  USING (true);

CREATE POLICY "Authenticated users can create reviews"
  ON public.reviews
  FOR INSERT
  TO authenticated
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own reviews"
  ON public.reviews
  FOR UPDATE
  TO authenticated
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete own reviews"
  ON public.reviews
  FOR DELETE
  TO authenticated
  USING (auth.uid() = user_id);

-- 4. Update the trigger function to run with SECURITY DEFINER
-- This ensures that when a regular authenticated user inserts or updates
-- a review, the trigger has permission to update the shops table rating columns.
CREATE OR REPLACE FUNCTION public.update_shop_rating()
RETURNS TRIGGER AS $$
BEGIN
  UPDATE public.shops
  SET 
    rating = COALESCE((
      SELECT ROUND(AVG(rating)::numeric, 1) 
      FROM public.reviews 
      WHERE shop_id = COALESCE(NEW.shop_id, OLD.shop_id)
    ), 0.0),
    review_count = (
      SELECT COUNT(*) 
      FROM public.reviews 
      WHERE shop_id = COALESCE(NEW.shop_id, OLD.shop_id)
    )
  WHERE id = COALESCE(NEW.shop_id, OLD.shop_id);
  RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

-- 5. Recreate the triggers on reviews
DROP TRIGGER IF EXISTS update_shop_rating_on_insert ON public.reviews;
CREATE TRIGGER update_shop_rating_on_insert 
  AFTER INSERT ON public.reviews
  FOR EACH ROW EXECUTE FUNCTION public.update_shop_rating();

DROP TRIGGER IF EXISTS update_shop_rating_on_update ON public.reviews;
CREATE TRIGGER update_shop_rating_on_update 
  AFTER UPDATE ON public.reviews
  FOR EACH ROW EXECUTE FUNCTION public.update_shop_rating();

DROP TRIGGER IF EXISTS update_shop_rating_on_delete ON public.reviews;
CREATE TRIGGER update_shop_rating_on_delete 
  AFTER DELETE ON public.reviews
  FOR EACH ROW EXECUTE FUNCTION public.update_shop_rating();

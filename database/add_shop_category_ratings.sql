-- Run this migration in the Supabase SQL editor.
CREATE TABLE IF NOT EXISTS public.shop_category_ratings (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  shop_id UUID NOT NULL REFERENCES public.shops(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  category TEXT NOT NULL CHECK (category IN (
    'food_quality',
    'portion_size',
    'price_value',
    'ambience',
    'service'
  )),
  rating SMALLINT NOT NULL CHECK (rating >= 0 AND rating <= 5),
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  UNIQUE (shop_id, user_id, category)
);

CREATE INDEX IF NOT EXISTS idx_shop_category_ratings_shop_id
  ON public.shop_category_ratings(shop_id);

ALTER TABLE public.shops
  ADD COLUMN IF NOT EXISTS people_say_rating DECIMAL(2, 1) NOT NULL DEFAULT 0.0,
  ADD COLUMN IF NOT EXISTS people_say_rating_count INTEGER NOT NULL DEFAULT 0;

CREATE OR REPLACE FUNCTION public.update_shop_people_say_rating()
RETURNS TRIGGER AS $$
DECLARE
  affected_shop_id UUID := COALESCE(NEW.shop_id, OLD.shop_id);
BEGIN
  UPDATE public.shops
  SET
    people_say_rating = COALESCE((
      SELECT ROUND(AVG(rating)::numeric, 1)
      FROM public.shop_category_ratings
      WHERE shop_id = affected_shop_id
    ), 0.0),
    people_say_rating_count = (
      SELECT COUNT(*)
      FROM public.shop_category_ratings
      WHERE shop_id = affected_shop_id
    )
  WHERE id = affected_shop_id;
  RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_shop_people_say_rating_on_change ON public.shop_category_ratings;
CREATE TRIGGER update_shop_people_say_rating_on_change
  AFTER INSERT OR UPDATE OR DELETE ON public.shop_category_ratings
  FOR EACH ROW EXECUTE FUNCTION public.update_shop_people_say_rating();

UPDATE public.shops
SET
  people_say_rating = COALESCE(category_ratings.average_rating, 0.0),
  people_say_rating_count = COALESCE(category_ratings.rating_count, 0)
FROM (
  SELECT shop_id, ROUND(AVG(rating)::numeric, 1) AS average_rating, COUNT(*) AS rating_count
  FROM public.shop_category_ratings
  GROUP BY shop_id
) AS category_ratings
WHERE public.shops.id = category_ratings.shop_id;

ALTER TABLE public.shop_category_ratings ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Category ratings are viewable by everyone" ON public.shop_category_ratings;
DROP POLICY IF EXISTS "Users can create category ratings" ON public.shop_category_ratings;
DROP POLICY IF EXISTS "Users can update own category ratings" ON public.shop_category_ratings;

CREATE POLICY "Category ratings are viewable by everyone"
  ON public.shop_category_ratings FOR SELECT USING (true);

CREATE POLICY "Users can create category ratings"
  ON public.shop_category_ratings FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own category ratings"
  ON public.shop_category_ratings FOR UPDATE
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

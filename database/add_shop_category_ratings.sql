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

ALTER TABLE public.shop_category_ratings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Category ratings are viewable by everyone"
  ON public.shop_category_ratings FOR SELECT USING (true);

CREATE POLICY "Users can create category ratings"
  ON public.shop_category_ratings FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own category ratings"
  ON public.shop_category_ratings FOR UPDATE
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

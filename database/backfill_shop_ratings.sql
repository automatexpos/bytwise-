-- Run this in the Supabase SQL editor to backfill shops.rating/review_count
-- and shops.people_say_rating/people_say_rating_count from existing rows,
-- for shops whose averages are currently out of sync.

UPDATE public.shops
SET
  rating = COALESCE(review_stats.average_rating, 0.0),
  review_count = COALESCE(review_stats.rating_count, 0)
FROM (
  SELECT shop_id, ROUND(AVG(rating)::numeric, 1) AS average_rating, COUNT(*) AS rating_count
  FROM public.reviews
  GROUP BY shop_id
) AS review_stats
WHERE public.shops.id = review_stats.shop_id;

-- Shops with no reviews at all won't be in the aggregate above, reset them explicitly.
UPDATE public.shops
SET rating = 0.0, review_count = 0
WHERE id NOT IN (SELECT DISTINCT shop_id FROM public.reviews);

UPDATE public.shops
SET
  people_say_rating = COALESCE(category_stats.average_rating, 0.0),
  people_say_rating_count = COALESCE(category_stats.rating_count, 0)
FROM (
  SELECT shop_id, ROUND(AVG(rating)::numeric, 1) AS average_rating, COUNT(*) AS rating_count
  FROM public.shop_category_ratings
  GROUP BY shop_id
) AS category_stats
WHERE public.shops.id = category_stats.shop_id;

UPDATE public.shops
SET people_say_rating = 0.0, people_say_rating_count = 0
WHERE id NOT IN (SELECT DISTINCT shop_id FROM public.shop_category_ratings);

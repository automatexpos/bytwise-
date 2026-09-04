-- Run this in the Supabase SQL editor.
--
-- Lets admins hide a shop from public listings/search/map without
-- deleting it. Hidden shops remain visible to admins.

ALTER TABLE public.shops
  ADD COLUMN IF NOT EXISTS is_hidden BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_shops_is_hidden ON public.shops(is_hidden);

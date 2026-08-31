-- Bytwise: create the follower relationship table and its RLS policies.
-- Run this once in the Supabase SQL Editor.

CREATE TABLE IF NOT EXISTS public.user_follows (
  follower_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  following_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  PRIMARY KEY (follower_id, following_id),
  CONSTRAINT user_follows_no_self_follow CHECK (follower_id <> following_id)
);

ALTER TABLE public.user_follows ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view follows" ON public.user_follows;
CREATE POLICY "Users can view follows"
  ON public.user_follows
  FOR SELECT
  TO authenticated
  USING (true);

DROP POLICY IF EXISTS "Users can follow other users" ON public.user_follows;
CREATE POLICY "Users can follow other users"
  ON public.user_follows
  FOR INSERT
  TO authenticated
  WITH CHECK (auth.uid() = follower_id AND follower_id <> following_id);

DROP POLICY IF EXISTS "Users can unfollow themselves" ON public.user_follows;
CREATE POLICY "Users can unfollow themselves"
  ON public.user_follows
  FOR DELETE
  TO authenticated
  USING (auth.uid() = follower_id);

CREATE INDEX IF NOT EXISTS user_follows_follower_id_idx
  ON public.user_follows (follower_id);

CREATE INDEX IF NOT EXISTS user_follows_following_id_idx
  ON public.user_follows (following_id);

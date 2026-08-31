-- Diagnostic queries to troubleshoot user_follows table

-- 1. Check if table exists and in which schema
SELECT 
    schemaname,
    tablename
FROM pg_tables
WHERE tablename = 'user_follows';

-- 2. Check table structure
SELECT 
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'user_follows'
ORDER BY ordinal_position;

-- 3. Check RLS policies
SELECT 
    schemaname,
    tablename,
    policyname,
    permissive,
    cmd
FROM pg_policies
WHERE tablename = 'user_follows';

-- 4. Check if RLS is enabled
SELECT 
    schemaname,
    tablename,
    rowsecurity
FROM pg_tables
WHERE tablename = 'user_follows';

-- 5. Try a simple insert to test (this will fail if there are issues)
-- Uncomment to test:
-- INSERT INTO public.user_follows (follower_id, following_id) 
-- VALUES ('b8a6b8cb-e8e3-4ad2-bf77-e62c5dd6f6a0', '7db456ec-0c87-41f5-beda-c6fc4fc1d02a');

-- 6. Try a simple select to test
SELECT * FROM public.user_follows LIMIT 5;

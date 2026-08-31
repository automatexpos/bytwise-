-- Step 1: Check table columns
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_schema = 'public' 
AND table_name = 'user_follows'
ORDER BY ordinal_position;

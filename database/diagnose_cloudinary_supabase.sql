-- Bytwise Supabase diagnostic script
-- READ-ONLY: run this in Supabase SQL Editor.
-- Do not run repair statements until the failing check is identified.

-- CHECK 1: Required tables exist
SELECT
  table_schema,
  table_name,
  CASE WHEN table_name IS NOT NULL THEN 'PASS' ELSE 'FAIL' END AS status
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN ('profiles', 'shops', 'shop_images');

-- CHECK 2: Required shop columns and types
SELECT
  column_name,
  data_type,
  is_nullable,
  column_default,
  CASE
    WHEN column_name IN ('id', 'name', 'description', 'lat', 'lng', 'address', 'city', 'state')
      THEN 'REQUIRED'
    ELSE 'OPTIONAL'
  END AS requirement
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'shops'
ORDER BY ordinal_position;

-- CHECK 3: Required shop_images columns and types
SELECT
  column_name,
  data_type,
  is_nullable,
  column_default,
  CASE
    WHEN column_name IN ('id', 'shop_id', 'url', 'type')
      THEN 'REQUIRED'
    WHEN column_name = 'cloudinary_public_id'
      THEN 'REQUIRED FOR CLOUDINARY DELETE'
    ELSE 'OPTIONAL'
  END AS requirement
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'shop_images'
ORDER BY ordinal_position;

-- CHECK 4: Specifically verify Cloudinary metadata column
SELECT
  CASE WHEN EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'shop_images'
      AND column_name = 'cloudinary_public_id'
  ) THEN 'PASS: cloudinary_public_id exists'
  ELSE 'FAIL: run ALTER TABLE public.shop_images ADD COLUMN cloudinary_public_id TEXT'
  END AS result;

-- CHECK 5: RLS status
SELECT
  schemaname,
  tablename,
  rowsecurity AS rls_enabled,
  CASE WHEN rowsecurity THEN 'PASS' ELSE 'FAIL' END AS status
FROM pg_tables
WHERE schemaname = 'public'
  AND tablename IN ('profiles', 'shops', 'shop_images');

-- CHECK 6: Policies required for adding shops and images
SELECT
  schemaname,
  tablename,
  policyname,
  permissive,
  roles,
  cmd,
  qual,
  with_check
FROM pg_policies
WHERE schemaname = 'public'
  AND tablename IN ('shops', 'shop_images')
ORDER BY tablename, policyname;

-- CHECK 7: Expected INSERT policies
SELECT
  table_name,
  policy_name,
  command,
  roles,
  CASE
    WHEN table_name = 'shops'
      AND command = 'INSERT'
      AND with_check LIKE '%authenticated%'
      THEN 'PASS: authenticated shop insert policy found'
    WHEN table_name = 'shop_images'
      AND command = 'INSERT'
      AND with_check LIKE '%authenticated%'
      THEN 'PASS: authenticated image insert policy found'
    ELSE 'REVIEW'
  END AS status,
  with_check
FROM (
  SELECT tablename AS table_name, policyname AS policy_name, cmd AS command,
         array_to_string(roles, ',') AS roles, COALESCE(with_check, '') AS with_check
  FROM pg_policies
  WHERE schemaname = 'public'
    AND tablename IN ('shops', 'shop_images')
    AND cmd = 'INSERT'
) policies;

-- CHECK 8: Table privileges for the API roles
SELECT
  table_name,
  grantee,
  privilege_type
FROM information_schema.role_table_grants
WHERE table_schema = 'public'
  AND table_name IN ('shops', 'shop_images')
  AND grantee IN ('anon', 'authenticated')
ORDER BY table_name, grantee, privilege_type;

-- CHECK 9: Primary keys, foreign key, and URL/public ID constraints
SELECT
  tc.constraint_name,
  tc.table_name,
  tc.constraint_type,
  kcu.column_name,
  ccu.table_name AS referenced_table,
  ccu.column_name AS referenced_column
FROM information_schema.table_constraints tc
LEFT JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name
 AND tc.table_schema = kcu.table_schema
LEFT JOIN information_schema.constraint_column_usage ccu
  ON tc.constraint_name = ccu.constraint_name
 AND tc.table_schema = ccu.table_schema
WHERE tc.table_schema = 'public'
  AND tc.table_name IN ('shops', 'shop_images')
ORDER BY tc.table_name, tc.constraint_type, tc.constraint_name;

-- CHECK 10: Triggers that may block shop inserts
SELECT
  event_object_table AS table_name,
  trigger_name,
  event_manipulation,
  action_statement
FROM information_schema.triggers
WHERE event_object_schema = 'public'
  AND event_object_table IN ('shops', 'shop_images')
ORDER BY event_object_table, trigger_name;

-- CHECK 11: Existing data consistency
SELECT
  COUNT(*) AS total_shops,
  COUNT(*) FILTER (WHERE id IS NULL) AS shops_missing_id,
  COUNT(*) FILTER (WHERE name IS NULL OR city IS NULL OR state IS NULL OR address IS NULL) AS shops_missing_required_values
FROM public.shops;

SELECT
  COUNT(*) AS total_images,
  COUNT(*) FILTER (WHERE url IS NULL OR url = '') AS images_missing_url,
  COUNT(*) FILTER (WHERE url LIKE 'https://res.cloudinary.com/%') AS cloudinary_urls,
  COUNT(*) FILTER (WHERE cloudinary_public_id IS NOT NULL) AS images_with_public_id,
  COUNT(*) FILTER (WHERE shop_id IS NULL) AS images_missing_shop_id
FROM public.shop_images;

-- CHECK 12: Orphaned image rows
SELECT si.id, si.shop_id, si.url, si.cloudinary_public_id
FROM public.shop_images si
LEFT JOIN public.shops s ON s.id = si.shop_id
WHERE s.id IS NULL
LIMIT 50;

-- CHECK 13: Current SQL role and schema
SELECT current_user AS sql_editor_role, current_schema() AS active_schema;

-- CHECK 14: Confirm the URL column is large enough for Cloudinary URLs
SELECT
  table_name,
  column_name,
  data_type,
  character_maximum_length
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'shop_images'
  AND column_name IN ('url', 'cloudinary_public_id');

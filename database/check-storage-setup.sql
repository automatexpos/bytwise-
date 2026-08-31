-- DIAGNOSTIC: Check if bucket exists and is configured correctly
SELECT 
  id,
  name,
  public,
  file_size_limit,
  allowed_mime_types,
  created_at
FROM storage.buckets 
WHERE id = 'shop-images';

-- Check current policies on storage.objects
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
WHERE tablename = 'objects' 
AND schemaname = 'storage'
ORDER BY policyname;

-- Test if you can query storage.objects
SELECT 
  COUNT(*) as total_files,
  bucket_id
FROM storage.objects 
WHERE bucket_id = 'shop-images'
GROUP BY bucket_id;

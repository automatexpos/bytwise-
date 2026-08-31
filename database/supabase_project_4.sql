-- Add admin role to profiles table
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE;

-- Update RLS policy for admin dashboard access
DROP POLICY IF EXISTS "Admins can view all claim requests" ON claim_requests;
CREATE POLICY "Admins can view all claim requests" 
ON claim_requests FOR SELECT 
USING (
  auth.uid() IN (
    SELECT id FROM profiles WHERE is_admin = true OR is_business_owner = true
  )
);

-- Allow admins to update claim requests
DROP POLICY IF EXISTS "Admins can update claim requests" ON claim_requests;
CREATE POLICY "Admins can update claim requests"
ON claim_requests FOR UPDATE
USING (
  auth.uid() IN (
    SELECT id FROM profiles WHERE is_admin = true
  )
);

-- Set yourself as the first admin (REPLACE WITH YOUR EMAIL)
UPDATE profiles SET is_admin = true WHERE email = 'your-email@example.com';
-- Allow admins to update shops (for claim approval)
DROP POLICY IF EXISTS "Admins can update shops" ON shops;
CREATE POLICY "Admins can update shops"
ON shops FOR UPDATE
USING (
  auth.uid() IN (
    SELECT id FROM profiles WHERE is_admin = true
  )
);
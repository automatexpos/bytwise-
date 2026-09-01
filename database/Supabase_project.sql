-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Users/Profiles table (extends Supabase auth.users)
CREATE TABLE profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  username TEXT NOT NULL,
  email TEXT NOT NULL,
  avatar_url TEXT,
  bio TEXT,
  instagram TEXT,
  x TEXT,
  is_business_owner BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Shops/Spots table
CREATE TABLE shops (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name TEXT NOT NULL,
  description TEXT,
  lat DECIMAL(10, 8) NOT NULL,
  lng DECIMAL(11, 8) NOT NULL,
  address TEXT NOT NULL,
  city TEXT NOT NULL,
  state TEXT NOT NULL,
  area TEXT,
  vibes TEXT[] DEFAULT '{}',
  cheeky_vibes TEXT[] DEFAULT '{}',
  parking TEXT,
  facilities JSONB DEFAULT '{}'::jsonb,
  open_hours JSONB DEFAULT '{}'::jsonb,
  rating DECIMAL(2, 1) DEFAULT 0.0,
  review_count INTEGER DEFAULT 0,
  is_claimed BOOLEAN DEFAULT FALSE,
  claimed_by UUID REFERENCES profiles(id) ON DELETE SET NULL,
  stamp_count INTEGER DEFAULT 0,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Shop Images/Gallery table
CREATE TABLE shop_images (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  shop_id UUID NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
  url TEXT NOT NULL,
  cloudinary_public_id TEXT,
  type TEXT CHECK (type IN ('owner', 'community')) DEFAULT 'community',
  approved BOOLEAN NOT NULL DEFAULT TRUE,
  caption TEXT,
  uploaded_by UUID REFERENCES profiles(id) ON DELETE SET NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Reviews table
CREATE TABLE reviews (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  shop_id UUID NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
  comment TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(shop_id, user_id) -- One review per user per shop
);

-- User Saved Shops (bookmarks)
CREATE TABLE saved_shops (
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  shop_id UUID NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  PRIMARY KEY (user_id, shop_id)
);

-- User Visited Shops (check-ins/passport stamps)
CREATE TABLE visited_shops (
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  shop_id UUID NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
  visited_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  PRIMARY KEY (user_id, shop_id)
);

-- Community up/down votes for shop vibes
CREATE TABLE vibe_votes (
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  shop_id UUID NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
  vibe TEXT NOT NULL,
  vote TEXT NOT NULL CHECK (vote IN ('up', 'down')),
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  PRIMARY KEY (user_id, shop_id, vibe)
);

CREATE INDEX idx_vibe_votes_shop_vibe ON vibe_votes(shop_id, vibe);

-- Claim Requests table
CREATE TABLE claim_requests (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  shop_id UUID NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  business_email TEXT NOT NULL,
  role TEXT NOT NULL,
  social_link TEXT,
  status TEXT CHECK (status IN ('pending', 'approved', 'rejected')) DEFAULT 'pending',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_shops_location ON shops(lat, lng);
CREATE INDEX idx_shops_city ON shops(city);
CREATE INDEX idx_shops_claimed_by ON shops(claimed_by);
CREATE INDEX idx_reviews_shop_id ON reviews(shop_id);
CREATE INDEX idx_reviews_user_id ON reviews(user_id);
CREATE INDEX idx_shop_images_shop_id ON shop_images(shop_id);
CREATE INDEX idx_saved_shops_user_id ON saved_shops(user_id);
CREATE INDEX idx_visited_shops_user_id ON visited_shops(user_id);
CREATE INDEX idx_claim_requests_status ON claim_requests(status);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers to auto-update updated_at
CREATE TRIGGER update_profiles_updated_at BEFORE UPDATE ON profiles
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_shops_updated_at BEFORE UPDATE ON shops
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_reviews_updated_at BEFORE UPDATE ON reviews
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_claim_requests_updated_at BEFORE UPDATE ON claim_requests
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Function to auto-create profile on user signup
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.profiles (id, username, email, avatar_url)
  VALUES (
    NEW.id,
    COALESCE(NEW.raw_user_meta_data->>'username', SPLIT_PART(NEW.email, '@', 1)),
    NEW.email,
    'https://ui-avatars.com/api/?name=' || COALESCE(NEW.raw_user_meta_data->>'username', SPLIT_PART(NEW.email, '@', 1)) || '&background=231b15&color=F08000'
  );
  RETURN NEW;
EXCEPTION
  WHEN others THEN
    RAISE LOG 'Error in handle_new_user: %', SQLERRM;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Drop existing trigger if it exists
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;

-- Trigger to create profile on signup
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION handle_new_user();

-- Function to update shop rating when review is added/updated/deleted
CREATE OR REPLACE FUNCTION update_shop_rating()
RETURNS TRIGGER AS $$
BEGIN
  UPDATE shops
  SET 
    rating = COALESCE((SELECT ROUND(AVG(rating)::numeric, 1) FROM reviews WHERE shop_id = COALESCE(NEW.shop_id, OLD.shop_id)), 0),
    review_count = (SELECT COUNT(*) FROM reviews WHERE shop_id = COALESCE(NEW.shop_id, OLD.shop_id))
  WHERE id = COALESCE(NEW.shop_id, OLD.shop_id);
  RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

-- Triggers to update shop rating
CREATE TRIGGER update_shop_rating_on_insert AFTER INSERT ON reviews
  FOR EACH ROW EXECUTE FUNCTION update_shop_rating();

CREATE TRIGGER update_shop_rating_on_update AFTER UPDATE ON reviews
  FOR EACH ROW EXECUTE FUNCTION update_shop_rating();

CREATE TRIGGER update_shop_rating_on_delete AFTER DELETE ON reviews
  FOR EACH ROW EXECUTE FUNCTION update_shop_rating();

-- Function to update stamp count when visited shops change
CREATE OR REPLACE FUNCTION update_stamp_count()
RETURNS TRIGGER AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    UPDATE shops SET stamp_count = stamp_count + 1 WHERE id = NEW.shop_id;
    RETURN NEW;
  ELSIF TG_OP = 'DELETE' THEN
    UPDATE shops SET stamp_count = GREATEST(0, stamp_count - 1) WHERE id = OLD.shop_id;
    RETURN OLD;
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Triggers to update stamp count
CREATE TRIGGER update_stamp_count_on_visit AFTER INSERT ON visited_shops
  FOR EACH ROW EXECUTE FUNCTION update_stamp_count();

CREATE TRIGGER update_stamp_count_on_unvisit AFTER DELETE ON visited_shops
  FOR EACH ROW EXECUTE FUNCTION update_stamp_count();

-- Row Level Security (RLS) Policies

-- Enable RLS
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE shops ENABLE ROW LEVEL SECURITY;
ALTER TABLE shop_images ENABLE ROW LEVEL SECURITY;
ALTER TABLE reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE saved_shops ENABLE ROW LEVEL SECURITY;
ALTER TABLE visited_shops ENABLE ROW LEVEL SECURITY;
ALTER TABLE vibe_votes ENABLE ROW LEVEL SECURITY;
ALTER TABLE claim_requests ENABLE ROW LEVEL SECURITY;

-- Profiles: Users can read all, but only update their own
CREATE POLICY "Profiles are viewable by everyone" ON profiles FOR SELECT USING (true);
CREATE POLICY "Users can update own profile" ON profiles FOR UPDATE USING (auth.uid() = id);

-- Shops: Everyone can read, authenticated users can insert
CREATE POLICY "Shops are viewable by everyone" ON shops FOR SELECT USING (true);
CREATE POLICY "Authenticated users can insert shops" ON shops FOR INSERT WITH CHECK (auth.role() = 'authenticated');
CREATE POLICY "Shop owners can update their shops" ON shops FOR UPDATE USING (claimed_by = auth.uid());

-- Shop Images: Everyone can read, authenticated users can insert
CREATE POLICY "Shop images are viewable by everyone" ON shop_images FOR SELECT USING (true);
CREATE POLICY "Anonymous users can submit pending images" ON shop_images FOR INSERT TO anon
  WITH CHECK (uploaded_by IS NULL AND approved = false AND type = 'community' AND EXISTS (SELECT 1 FROM shops WHERE shops.id = shop_images.shop_id));
CREATE POLICY "Authenticated users can submit pending images" ON shop_images FOR INSERT TO authenticated
  WITH CHECK (auth.uid() = uploaded_by AND approved = false AND type = 'community' AND EXISTS (SELECT 1 FROM shops WHERE shops.id = shop_images.shop_id AND (shops.claimed_by IS NULL OR shops.claimed_by <> auth.uid())));
CREATE POLICY "Authenticated users can add approved images" ON shop_images FOR INSERT TO authenticated
  WITH CHECK (auth.uid() = uploaded_by AND approved = true AND type = 'owner');
CREATE POLICY "Admins can approve shop images" ON shop_images FOR UPDATE TO authenticated
  USING (EXISTS (SELECT 1 FROM profiles WHERE profiles.id = auth.uid() AND profiles.is_admin = true))
  WITH CHECK (EXISTS (SELECT 1 FROM profiles WHERE profiles.id = auth.uid() AND profiles.is_admin = true));
CREATE POLICY "Admins can delete shop images" ON shop_images FOR DELETE
  USING (EXISTS (SELECT 1 FROM profiles WHERE profiles.id = auth.uid() AND profiles.is_admin = true));

-- Reviews: Everyone can read, authenticated users can insert/update their own
CREATE POLICY "Reviews are viewable by everyone" ON reviews FOR SELECT USING (true);
CREATE POLICY "Authenticated users can create reviews" ON reviews FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own reviews" ON reviews FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Users can delete own reviews" ON reviews FOR DELETE USING (auth.uid() = user_id);

-- Saved Shops: Users can only see and manage their own
CREATE POLICY "Users can view own saved shops" ON saved_shops FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can save shops" ON saved_shops FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can unsave shops" ON saved_shops FOR DELETE USING (auth.uid() = user_id);

-- Visited Shops: Users can only see and manage their own
CREATE POLICY "Users can view own visited shops" ON visited_shops FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can mark shops as visited" ON visited_shops FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can unmark shops as visited" ON visited_shops FOR DELETE USING (auth.uid() = user_id);

CREATE POLICY "Vibe votes are viewable by everyone" ON vibe_votes FOR SELECT USING (true);
CREATE POLICY "Users can vote on vibes" ON vibe_votes FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own vibe votes" ON vibe_votes FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Users can delete own vibe votes" ON vibe_votes FOR DELETE USING (auth.uid() = user_id);

-- Claim Requests: Users can view their own, admins can view all
CREATE POLICY "Users can view own claim requests" ON claim_requests FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can create claim requests" ON claim_requests FOR INSERT WITH CHECK (auth.uid() = user_id);
import { createClient } from "@supabase/supabase-js";

import { assertPublicEnv, SUPABASE_ANON_KEY, SUPABASE_URL } from "./config";

assertPublicEnv();

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);


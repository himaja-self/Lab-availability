export const FLASK_API_URL =
  process.env.NEXT_PUBLIC_FLASK_API_URL ?? "http://127.0.0.1:5000";

// IMPORTANT:
// Next.js only inlines `process.env.NEXT_PUBLIC_*` when accessed statically.
// Avoid dynamic access like `process.env[name]` on the client.
export const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
export const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

export function assertPublicEnv() {
  if (!SUPABASE_URL) throw new Error("Missing required env var: NEXT_PUBLIC_SUPABASE_URL");
  if (!SUPABASE_ANON_KEY) throw new Error("Missing required env var: NEXT_PUBLIC_SUPABASE_ANON_KEY");
}


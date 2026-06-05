"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { NotificationBell } from "@/components/NotificationBell";
import { Button } from "@/components/ui";
import { supabase } from "@/lib/supabaseClient";

export function AppHeader() {
  const pathname = usePathname();
  const [authed, setAuthed] = useState(false);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setAuthed(Boolean(data.session));
    });
    const { data: sub } = supabase.auth.onAuthStateChange((_e, session) => {
      setAuthed(Boolean(session));
    });
    return () => sub.subscription.unsubscribe();
  }, []);

  async function signOut() {
    await supabase.auth.signOut();
    window.location.href = "/";
  }

  const navLink = (href: string, label: string) => {
    const active = pathname === href;
    return (
      <Link
        href={href}
        className={`text-sm font-medium transition-colors ${
          active ? "text-[#fccf17]" : "text-white/90 hover:text-[#fccf17]"
        }`}
      >
        {label}
      </Link>
    );
  };

  return (
    <header className="border-b border-[#00848c]/30 bg-gradient-to-r from-[#1c1f4c] to-[#252a5c] shadow-sm">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
        <Link href="/" className="text-lg font-bold tracking-tight text-white">
          Lab Occupancy System
        </Link>

        <nav className="flex flex-wrap items-center gap-4 sm:gap-5">
          {navLink("/", "Viewer")}
          {authed ? navLink("/admin", "Admin") : null}
          <NotificationBell />
          {authed ? (
            <Button
              variant="secondary"
              onClick={signOut}
              className="h-9 border-white/40 text-white hover:bg-white/10 hover:text-white"
            >
              Sign Out
            </Button>
          ) : (
            <Link
              href="/admin/login"
              className="text-sm font-medium text-white/90 hover:text-[#fccf17]"
            >
              Admin Login
            </Link>
          )}
        </nav>
      </div>
    </header>
  );
}

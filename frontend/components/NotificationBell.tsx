"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  type NotificationRow,
} from "@/lib/flaskApi";

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState<NotificationRow[]>([]);
  const [loading, setLoading] = useState(false);
  const popoverRef = useRef<HTMLDivElement>(null);

  const unreadCount = notifications.filter((n) => !n.is_read).length;

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const rows = await listNotifications();
      setNotifications(rows);
    } catch {
      setNotifications([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, 60_000);
    return () => window.clearInterval(id);
  }, [refresh]);

  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  async function onMarkAll() {
    await markAllNotificationsRead();
    await refresh();
  }

  async function onMarkOne(id: string) {
    await markNotificationRead(id);
    await refresh();
  }

  return (
    <div className="relative" ref={popoverRef}>
      <button
        type="button"
        aria-label="Notifications"
        onClick={() => {
          setOpen((v) => !v);
          if (!open) refresh();
        }}
        className="relative rounded-lg p-2 text-white/90 transition-colors hover:bg-white/10 hover:text-[#fccf17]"
      >
        <span className="text-lg" aria-hidden>
          🔔
        </span>
        {unreadCount > 0 ? (
          <span className="absolute -right-0.5 -top-0.5 flex h-5 min-w-5 items-center justify-center rounded-full bg-[#fccf17] px-1 text-[10px] font-bold text-[#1c1f4c]">
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        ) : null}
      </button>

      {open ? (
        <div className="absolute right-0 z-50 mt-2 w-[min(100vw-2rem,22rem)] rounded-xl border border-[rgba(0,132,140,0.25)] bg-[#edebd9] shadow-xl">
          <div className="flex items-center justify-between border-b border-[rgba(0,132,140,0.2)] px-4 py-3">
            <span className="text-sm font-semibold text-[#1c1f4c]">Notifications</span>
            {unreadCount > 0 ? (
              <button
                type="button"
                onClick={onMarkAll}
                className="text-xs font-medium text-[#00848c] hover:text-[#037272]"
              >
                Mark all as read
              </button>
            ) : null}
          </div>
          <div className="max-h-80 overflow-y-auto">
            {loading ? (
              <p className="px-4 py-6 text-sm text-[#037272]">Loading…</p>
            ) : notifications.length === 0 ? (
              <p className="px-4 py-6 text-sm text-[#037272]">No notifications.</p>
            ) : (
              <ul className="divide-y divide-[rgba(0,132,140,0.15)]">
                {notifications.map((n) => (
                  <li
                    key={n.id}
                    className={`px-4 py-3 ${n.is_read ? "opacity-70" : "bg-white/30"}`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-sm text-[#1c1f4c]">{n.message}</p>
                      {!n.is_read ? (
                        <button
                          type="button"
                          onClick={() => onMarkOne(n.id)}
                          className="shrink-0 text-[10px] font-medium text-[#00848c] hover:underline"
                        >
                          Read
                        </button>
                      ) : null}
                    </div>
                    <div className="mt-1 flex items-center gap-2 text-[10px] text-[#037272]">
                      <span>{new Date(n.created_at).toLocaleString()}</span>
                      {n.type ? <span>• {n.type}</span> : null}
                      {!n.is_read ? (
                        <span className="rounded bg-[#fccf17]/40 px-1.5 py-0.5 font-medium">
                          Unread
                        </span>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}

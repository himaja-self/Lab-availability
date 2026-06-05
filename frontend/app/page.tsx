"use client";

import { useMemo, useState } from "react";

import { Card, Button, Input, Label, Select } from "@/components/ui";
import {
  DEPARTMENT_BLOCKS,
  getAvailability,
  type AvailabilityResponse,
  type DayStatus,
} from "@/lib/flaskApi";

const FULL_DAY_BANNER: DayStatus[] = ["sunday", "holiday"];

/** Full-day free: banner only. Partial exam_period: banner + lab lists. */
function isFullDayBanner(result: AvailabilityResponse): boolean {
  if (!result.day_status || !FULL_DAY_BANNER.includes(result.day_status)) {
    return result.day_status === "exam_period" && result.status === "labs_free";
  }
  return true;
}

export default function Home() {
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [startTime, setStartTime] = useState("14:00");
  const [endTime, setEndTime] = useState("16:00");
  const [block, setBlock] = useState("");

  const [result, setResult] = useState<AvailabilityResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const canSubmit = useMemo(() => {
    if (!date || !startTime || !endTime) return false;
    return startTime < endTime;
  }, [date, startTime, endTime]);

  const showBanner = Boolean(result?.message && result?.day_status);
  const bannerOnly = result ? isFullDayBanner(result) : false;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      const res = await getAvailability({
        date,
        start_time: startTime,
        end_time: endTime,
        block: block || undefined,
      });
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-[#1c1f4c]">Lab Availability</h1>
        <p className="mt-1 text-sm text-[#037272]">
          Check if a lab is free for a given date and time range.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[340px_1fr]">
        <Card>
          <form className="grid gap-4" onSubmit={onSubmit}>
            <div className="grid gap-2">
              <Label htmlFor="date">Date</Label>
              <Input
                id="date"
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                required
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="grid gap-2">
                <Label htmlFor="from">From time</Label>
                <Input
                  id="from"
                  type="time"
                  value={startTime}
                  onChange={(e) => setStartTime(e.target.value)}
                  required
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="to">To time</Label>
                <Input
                  id="to"
                  type="time"
                  value={endTime}
                  onChange={(e) => setEndTime(e.target.value)}
                  required
                />
              </div>
            </div>

            <div className="grid gap-2">
              <Label htmlFor="dept">Department</Label>
              <Select
                id="dept"
                value={block}
                onChange={(e) => setBlock(e.target.value)}
              >
                {DEPARTMENT_BLOCKS.map((d) => (
                  <option key={d.value || "all"} value={d.value}>
                    {d.label}
                  </option>
                ))}
              </Select>
            </div>

            <Button type="submit" variant="cta" disabled={!canSubmit || loading}>
              {loading ? "Checking…" : "Check Availability"}
            </Button>

            {!canSubmit ? (
              <p className="text-xs text-[#037272]">End time must be after start time.</p>
            ) : null}
          </form>
        </Card>

        <Card>
          {!result && !error ? (
            <p className="text-sm text-[#037272]">Submit the form to see results.</p>
          ) : null}

          {error ? <p className="text-sm text-red-700">{error}</p> : null}

          {result ? (
            <div className="grid gap-6">
              {result.date && result.day ? (
                <p className="text-sm font-medium text-[#1c1f4c]">
                  {result.date} • {result.day}
                  {result.start_time && result.end_time
                    ? ` • ${result.start_time}–${result.end_time}`
                    : ""}
                </p>
              ) : null}

              {showBanner ? (
                <div
                  className="rounded-xl border border-[#fec20f] bg-[#fccf17]/30 px-4 py-3 text-sm font-medium text-[#1c1f4c]"
                  role="status"
                >
                  {result.message}
                </div>
              ) : null}

              {result.status === "no_semester" && result.message ? (
                <div
                  className="rounded-xl border border-[#fec20f] bg-[#fccf17]/30 px-4 py-3 text-sm text-[#1c1f4c]"
                  role="status"
                >
                  {result.message}
                </div>
              ) : null}

              {!bannerOnly && result.status !== "no_semester" ? (
                <>
                  <section className="grid gap-3">
                    <h2 className="text-sm font-semibold text-[#1c1f4c]">Available Labs</h2>
                    {result.available_labs.length ? (
                      <ul className="grid gap-2 sm:grid-cols-2">
                        {result.available_labs.map((l) => (
                          <li
                            key={l.room_number}
                            className="rounded-lg border-2 border-[rgba(0,132,140,0.45)] bg-white/40 px-3 py-2"
                          >
                            <div className="font-semibold text-[#1c1f4c]">{l.room_number}</div>
                            <div className="text-xs text-[#037272]">
                              {l.department ?? "—"}
                            </div>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-sm text-[#037272]">No available labs for this query.</p>
                    )}
                  </section>

                  <section className="grid gap-3">
                    <h2 className="text-sm font-semibold text-[#1c1f4c]">Occupied Labs</h2>
                    {result.occupied_labs.length ? (
                      <ul className="grid gap-2">
                        {result.occupied_labs.map((l) => {
                          const session = l.sessions?.[0];
                          const by = l.occupied_by ?? session?.class_name ?? "—";
                          const subj = session?.subject ?? "";
                          const slot =
                            l.start_time && l.end_time
                              ? `${l.start_time}–${l.end_time}`
                              : session
                                ? `${session.start_time}–${session.end_time}`
                                : "";
                          return (
                            <li
                              key={l.room_number}
                              className="rounded-lg border border-[rgba(0,132,140,0.25)] bg-white/30 px-3 py-2 text-sm"
                            >
                              <div className="font-semibold text-[#1c1f4c]">{l.room_number}</div>
                              <div className="text-[#037272]">
                                Occupied by: {by}
                                {subj ? ` (${subj})` : ""}
                              </div>
                              {slot ? (
                                <div className="text-xs text-[#037272]">{slot}</div>
                              ) : null}
                            </li>
                          );
                        })}
                      </ul>
                    ) : (
                      <p className="text-sm text-[#037272]">No occupied labs for this query.</p>
                    )}
                  </section>

                  <section className="grid gap-3">
                    <h2 className="text-sm font-semibold text-[#1c1f4c]">No Data</h2>
                    {result.no_data_labs.length ? (
                      <ul className="grid gap-2 sm:grid-cols-2">
                        {result.no_data_labs.map((l) => (
                          <li
                            key={l.room_number}
                            className="rounded-lg border-2 border-[#fec20f] bg-[#fccf17]/15 px-3 py-2 text-sm"
                          >
                            <div className="font-semibold text-[#1c1f4c]">{l.room_number}</div>
                            <div className="text-[#037272]">No timetable data available</div>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-sm text-[#037272]">All labs have timetable data.</p>
                    )}
                  </section>
                </>
              ) : null}
            </div>
          ) : null}
        </Card>
      </div>
    </div>
  );
}

"use client";

import { useCallback, useEffect, useState } from "react";

import { Button, Card, Input, Label, Select } from "@/components/ui";
import {
  getAcademicCalendar,
  saveAcademicCalendar,
  type Semester,
} from "@/lib/flaskApi";

const YEAR_TABS = [
  { n: 1, label: "I Year" },
  { n: 2, label: "II Year" },
  { n: 3, label: "III Year" },
  { n: 4, label: "IV Year" },
];

type YearForm = {
  commencement: string;
  se1Start: string;
  se1End: string;
  se2Start: string;
  se2End: string;
  seeStart: string;
  seeEnd: string;
};

const emptyYearForm = (): YearForm => ({
  commencement: "",
  se1Start: "",
  se1End: "",
  se2Start: "",
  se2End: "",
  seeStart: "",
  seeEnd: "",
});

function formFromEvents(
  events: Array<{ event_name: string; start_date: string; end_date: string | null }>,
): YearForm {
  const f = emptyYearForm();
  for (const e of events) {
    if (e.event_name === "COMMENCEMENT") f.commencement = e.start_date;
    if (e.event_name === "SE_I") {
      f.se1Start = e.start_date;
      f.se1End = e.end_date ?? "";
    }
    if (e.event_name === "SE_II") {
      f.se2Start = e.start_date;
      f.se2End = e.end_date ?? "";
    }
    if (e.event_name === "SEE_THEORY") {
      f.seeStart = e.start_date;
      f.seeEnd = e.end_date ?? "";
    }
  }
  return f;
}

export function AcademicCalendarForm({ semesters }: { semesters: Semester[] }) {
  const [semesterId, setSemesterId] = useState("");
  const [yearTab, setYearTab] = useState(1);
  const [forms, setForms] = useState<Record<number, YearForm>>({
    1: emptyYearForm(),
    2: emptyYearForm(),
    3: emptyYearForm(),
    4: emptyYearForm(),
  });
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(true);

  useEffect(() => {
    const active = semesters.find((s) => s.is_active);
    setSemesterId((prev) => prev || active?.id || semesters[0]?.id || "");
  }, [semesters]);

  const loadYear = useCallback(
    async (semId: string, year: number) => {
      if (!semId) return;
      try {
        const events = await getAcademicCalendar(semId, year);
        setForms((prev) => ({ ...prev, [year]: formFromEvents(events) }));
      } catch {
        setForms((prev) => ({ ...prev, [year]: emptyYearForm() }));
      }
    },
    [],
  );

  useEffect(() => {
    if (semesterId) loadYear(semesterId, yearTab);
  }, [semesterId, yearTab, loadYear]);

  function patchYear(year: number, patch: Partial<YearForm>) {
    setForms((prev) => ({ ...prev, [year]: { ...prev[year], ...patch } }));
  }

  async function onSaveYear(year: number) {
    setMsg(null);
    setError(null);
    const f = forms[year];
    if (!semesterId) {
      setError("Select a semester first.");
      return;
    }
    if (!f.commencement) {
      setError("Commencement of Classes is required.");
      return;
    }
    if (!f.seeStart || !f.seeEnd) {
      setError("SEE Theory Exams (start and end) are required.");
      return;
    }

    const events: Array<{
      event_name: string;
      start_date: string;
      end_date?: string | null;
      makes_labs_free: boolean;
      makes_labs_occupied: boolean;
    }> = [
      {
        event_name: "COMMENCEMENT",
        start_date: f.commencement,
        end_date: null,
        makes_labs_free: false,
        makes_labs_occupied: false,
      },
      {
        event_name: "SEE_THEORY",
        start_date: f.seeStart,
        end_date: f.seeEnd,
        makes_labs_free: true,
        makes_labs_occupied: false,
      },
    ];

    if (f.se1Start && f.se1End) {
      events.push({
        event_name: "SE_I",
        start_date: f.se1Start,
        end_date: f.se1End,
        makes_labs_free: true,
        makes_labs_occupied: false,
      });
    }
    if (f.se2Start && f.se2End) {
      events.push({
        event_name: "SE_II",
        start_date: f.se2Start,
        end_date: f.se2End,
        makes_labs_free: true,
        makes_labs_occupied: false,
      });
    }

    setSaving(true);
    try {
      await saveAcademicCalendar({
        semester_id: semesterId,
        year_of_study: year,
        events,
      });
      setMsg(`Saved calendar for ${YEAR_TABS.find((t) => t.n === year)?.label}.`);
      await loadYear(semesterId, year);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  const f = forms[yearTab];

  return (
    <Card>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between text-left"
      >
        <h2 className="text-base font-semibold text-[#1c1f4c]">Academic Calendar</h2>
        <span className="text-sm text-[#00848c]">{open ? "−" : "+"}</span>
      </button>

      {open ? (
        <div className="mt-4 grid gap-4">
          <p className="text-sm text-[#037272]">
            Set commencement, sessional exams, and SEE dates per year group for the selected
            semester.
          </p>

          <div className="grid gap-2">
            <Label htmlFor="calSemester">Semester</Label>
            <Select
              id="calSemester"
              value={semesterId}
              onChange={(e) => setSemesterId(e.target.value)}
            >
              {semesters.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                  {s.is_active ? " (active)" : ""}
                </option>
              ))}
            </Select>
          </div>

          <div className="flex flex-wrap gap-1 border-b border-[rgba(0,132,140,0.2)] pb-2">
            {YEAR_TABS.map((t) => (
              <button
                key={t.n}
                type="button"
                onClick={() => setYearTab(t.n)}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                  yearTab === t.n
                    ? "bg-[#00848c] text-white"
                    : "text-[#037272] hover:bg-[#00848c]/10"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          <div className="grid gap-4">
            <div className="grid gap-2">
              <Label htmlFor="commencement">Commencement of Classes *</Label>
              <Input
                id="commencement"
                type="date"
                value={f.commencement}
                onChange={(e) => patchYear(yearTab, { commencement: e.target.value })}
              />
            </div>

            <fieldset className="grid gap-2">
              <legend className="text-sm font-medium text-[#037272]">
                Sessional Examination I (SE-I) — optional
              </legend>
              <div className="grid grid-cols-2 gap-3">
                <Input
                  type="date"
                  value={f.se1Start}
                  onChange={(e) => patchYear(yearTab, { se1Start: e.target.value })}
                  aria-label="SE-I start"
                />
                <Input
                  type="date"
                  value={f.se1End}
                  onChange={(e) => patchYear(yearTab, { se1End: e.target.value })}
                  aria-label="SE-I end"
                />
              </div>
            </fieldset>

            <fieldset className="grid gap-2">
              <legend className="text-sm font-medium text-[#037272]">
                Sessional Examination II (SE-II) — optional
              </legend>
              <div className="grid grid-cols-2 gap-3">
                <Input
                  type="date"
                  value={f.se2Start}
                  onChange={(e) => patchYear(yearTab, { se2Start: e.target.value })}
                  aria-label="SE-II start"
                />
                <Input
                  type="date"
                  value={f.se2End}
                  onChange={(e) => patchYear(yearTab, { se2End: e.target.value })}
                  aria-label="SE-II end"
                />
              </div>
            </fieldset>

            <fieldset className="grid gap-2">
              <legend className="text-sm font-medium text-[#037272]">
                SEE Theory Exams *
              </legend>
              <div className="grid grid-cols-2 gap-3">
                <Input
                  type="date"
                  value={f.seeStart}
                  onChange={(e) => patchYear(yearTab, { seeStart: e.target.value })}
                  aria-label="SEE start"
                />
                <Input
                  type="date"
                  value={f.seeEnd}
                  onChange={(e) => patchYear(yearTab, { seeEnd: e.target.value })}
                  aria-label="SEE end"
                />
              </div>
            </fieldset>

            <Button
              type="button"
              disabled={saving}
              onClick={() => onSaveYear(yearTab)}
            >
              {saving
                ? "Saving…"
                : `Save ${YEAR_TABS.find((t) => t.n === yearTab)?.label} Calendar`}
            </Button>
          </div>

          {msg ? <p className="text-sm text-[#00848c]">{msg}</p> : null}
          {error ? <p className="text-sm text-red-700">{error}</p> : null}
        </div>
      ) : null}
    </Card>
  );
}

"use client";

import { useEffect, useMemo, useState } from "react";

import { AcademicCalendarForm } from "@/components/AcademicCalendarForm";
import { Card, Button, Input, Label, Select } from "@/components/ui";
import {
  createSemester,
  listSemesters,
  uploadTimetable,
  type Semester,
} from "@/lib/flaskApi";
import { supabase } from "@/lib/supabaseClient";

export default function AdminPage() {
  const [ready, setReady] = useState(false);
  const [authed, setAuthed] = useState(false);

  const [semesters, setSemesters] = useState<Semester[]>([]);
  const [uploadSemesterId, setUploadSemesterId] = useState("");

  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<unknown>(null);

  const [newSemesterName, setNewSemesterName] = useState("");
  const [newSemesterStart, setNewSemesterStart] = useState("");
  const [newSemesterEnd, setNewSemesterEnd] = useState("");
  const [newSemesterActive, setNewSemesterActive] = useState(true);
  const [creatingSemester, setCreatingSemester] = useState(false);

  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [semestersLoading, setSemestersLoading] = useState(false);
  const [semestersError, setSemestersError] = useState<string | null>(null);

  async function refreshSemesters() {
    setSemestersLoading(true);
    setSemestersError(null);
    try {
      const sems = await listSemesters();
      setSemesters(sems);
      const active = sems.find((s) => s.is_active);
      setUploadSemesterId((prev) => {
        if (prev && sems.some((s) => s.id === prev)) return prev;
        return active?.id ?? sems[0]?.id ?? "";
      });
    } catch (e) {
      setSemesters([]);
      setUploadSemesterId("");
      setSemestersError(
        e instanceof Error
          ? e.message
          : "Could not load semesters. Is the Flask backend running at http://127.0.0.1:5000?",
      );
    } finally {
      setSemestersLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const { data } = await supabase.auth.getSession();
      const ok = Boolean(data.session);
      if (!cancelled) {
        setAuthed(ok);
        setReady(true);
      }
      if (!ok || cancelled) return;
      await refreshSemesters();
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const canUpload = useMemo(() => {
    if (!uploadSemesterId || !uploadFile) return false;
    const n = uploadFile.name.toLowerCase();
    return n.endsWith(".xlsx") || n.endsWith(".docx");
  }, [uploadSemesterId, uploadFile]);

  const canCreateSemester = useMemo(() => {
    if (!newSemesterName.trim() || !newSemesterStart || !newSemesterEnd) return false;
    return newSemesterStart <= newSemesterEnd;
  }, [newSemesterName, newSemesterStart, newSemesterEnd]);

  const uploadBlockReason = useMemo(() => {
    if (semestersLoading) return "Loading semesters…";
    if (semestersError) return semestersError;
    if (semesters.length === 0)
      return "Create a semester first — timetable data is stored per semester.";
    if (!uploadSemesterId) return "Select a semester before uploading.";
    if (!uploadFile) return "Choose a .xlsx or .docx file.";
    const n = uploadFile.name.toLowerCase();
    if (!n.endsWith(".xlsx") && !n.endsWith(".docx"))
      return "Only .xlsx and .docx files are supported.";
    return null;
  }, [
    semestersLoading,
    semestersError,
    semesters.length,
    uploadSemesterId,
    uploadFile,
  ]);

  async function onUpload(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    setError(null);
    setUploadResult(null);
    if (uploadBlockReason) {
      setError(uploadBlockReason);
      return;
    }
    if (!uploadFile || !uploadSemesterId) return;
    setUploading(true);
    try {
      const res = await uploadTimetable({
        file: uploadFile,
        semester_id: uploadSemesterId,
      });
      setUploadResult(res);
      setMsg(`Upload complete: ${res.sessions_inserted} session(s) inserted.`);
      setUploadFile(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setUploading(false);
    }
  }

  async function onCreateSemester(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    setError(null);
    setCreatingSemester(true);
    try {
      const created = await createSemester({
        name: newSemesterName.trim(),
        start_date: newSemesterStart,
        end_date: newSemesterEnd,
        is_active: newSemesterActive,
      });
      setMsg(`Semester created: ${created.name}`);
      setNewSemesterName("");
      setNewSemesterStart("");
      setNewSemesterEnd("");
      setNewSemesterActive(true);
      await refreshSemesters();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setCreatingSemester(false);
    }
  }

  if (!ready) {
    return <div className="min-h-[40vh] bg-[#edebd9]" />;
  }

  if (!authed) {
    if (typeof window !== "undefined") window.location.href = "/admin/login";
    return <div className="min-h-[40vh] bg-[#edebd9]" />;
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-[#1c1f4c]">Admin Dashboard</h1>
        <p className="mt-1 text-sm text-[#037272]">
          Upload timetables, manage semesters, and configure the academic calendar.
        </p>
      </div>

      <div className="grid gap-6">
        <Card>
          <h2 className="text-base font-semibold text-[#1c1f4c]">
            Step 1 — Create Semester
          </h2>
          <p className="mt-1 text-sm text-[#037272]">
            Required before upload. Sessions are linked to a semester in the database.
          </p>
          <form className="mt-4 grid gap-4" onSubmit={onCreateSemester}>
            <div className="grid gap-2">
              <Label htmlFor="semName">Name</Label>
              <Input
                id="semName"
                value={newSemesterName}
                onChange={(e) => setNewSemesterName(e.target.value)}
                placeholder="e.g. 2025-26 Sem II"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="grid gap-2">
                <Label htmlFor="semStart">Start date</Label>
                <Input
                  id="semStart"
                  type="date"
                  value={newSemesterStart}
                  onChange={(e) => setNewSemesterStart(e.target.value)}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="semEnd">End date</Label>
                <Input
                  id="semEnd"
                  type="date"
                  value={newSemesterEnd}
                  onChange={(e) => setNewSemesterEnd(e.target.value)}
                />
              </div>
            </div>
            <label className="flex items-center gap-2 text-sm text-[#1c1f4c]">
              <input
                type="checkbox"
                checked={newSemesterActive}
                onChange={(e) => setNewSemesterActive(e.target.checked)}
                className="h-4 w-4 rounded border-[#00848c]"
              />
              Set as active
            </label>
            <Button type="submit" disabled={!canCreateSemester || creatingSemester}>
              {creatingSemester ? "Creating…" : "Create semester"}
            </Button>
          </form>
        </Card>

        <Card>
          <h2 className="text-base font-semibold text-[#1c1f4c]">
            Step 2 — Upload Timetable
          </h2>
          <p className="mt-1 text-sm text-[#037272]">
            Upload <strong>.xlsx</strong> (lab-wise) or <strong>.docx</strong> (class-wise).
          </p>

          {semesters.length === 0 && !semestersLoading ? (
            <div className="mt-4 rounded-lg border border-[#fec20f] bg-[#fccf17]/25 px-3 py-2 text-sm text-[#1c1f4c]">
              No semesters yet. Use <strong>Step 1</strong> above, then return here to upload.
            </div>
          ) : null}

          <form className="mt-4 grid gap-4" onSubmit={onUpload}>
            <div className="grid gap-2">
              <Label htmlFor="semesterUpload">Semester</Label>
              <Select
                id="semesterUpload"
                value={uploadSemesterId}
                onChange={(e) => setUploadSemesterId(e.target.value)}
                disabled={semestersLoading || semesters.length === 0}
              >
                {semesters.length === 0 ? (
                  <option value="">— Create a semester first —</option>
                ) : (
                  semesters.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                      {s.is_active ? " (active)" : ""}
                    </option>
                  ))
                )}
              </Select>
            </div>

            <div className="grid gap-2">
              <Label htmlFor="file">File</Label>
              <input
                id="file"
                type="file"
                accept=".xlsx,.docx"
                onChange={(e) => setUploadFile(e.target.files?.[0] ?? null)}
                className="block w-full text-sm text-[#1c1f4c] file:mr-4 file:rounded-lg file:border-0 file:bg-[#00848c] file:px-4 file:py-2 file:text-sm file:font-medium file:text-white hover:file:bg-[#037272]"
              />
              <p className="text-xs text-[#037272]">
                {uploadFile ? uploadFile.name : "Choose a file to upload."}
              </p>
            </div>

            <Button type="submit" disabled={!canUpload || uploading}>
              {uploading ? "Uploading…" : "Upload"}
            </Button>

            {uploadBlockReason && !uploading ? (
              <p className="text-xs text-[#037272]">{uploadBlockReason}</p>
            ) : null}

            {uploadResult ? (
              <pre className="overflow-auto rounded-lg bg-[#1c1f4c] p-3 text-xs text-[#edebd9]">
                {JSON.stringify(uploadResult, null, 2)}
              </pre>
            ) : null}
          </form>
        </Card>

        <AcademicCalendarForm semesters={semesters} />

        {msg ? <p className="text-sm text-[#00848c]">{msg}</p> : null}
        {error ? <p className="text-sm text-red-700">{error}</p> : null}
      </div>
    </div>
  );
}

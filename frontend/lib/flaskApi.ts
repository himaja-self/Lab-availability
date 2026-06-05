import { FLASK_API_URL } from "./config";

export type DayStatus = "normal" | "holiday" | "sunday" | "exam_period";

export type AvailabilityResponse = {
  status?: string;
  day_status?: DayStatus;
  message?: string | null;
  date?: string;
  day?: string;
  start_time?: string;
  end_time?: string;
  available_labs: {
    room_number: string;
    department?: string;
    status: "available";
  }[];
  occupied_labs: {
    room_number: string;
    department?: string;
    status: "occupied";
    occupied_by?: string;
    start_time?: string;
    end_time?: string;
    sessions?: Array<{
      class_name: string;
      subject: string;
      session_type: string;
      start_time: string;
      end_time: string;
      year_group: string;
    }>;
  }[];
  no_data_labs: {
    room_number: string;
    department?: string;
    status: "no_data";
  }[];
  calendar_note: string | null;
};

export async function getAvailability(params: {
  date: string;
  start_time: string;
  end_time: string;
  block?: string;
}): Promise<AvailabilityResponse> {
  const qs = new URLSearchParams({
    date: params.date,
    start_time: params.start_time,
    end_time: params.end_time,
  });
  if (params.block) qs.set("block", params.block);

  const r = await fetch(`${FLASK_API_URL}/api/availability?${qs.toString()}`, {
    method: "GET",
    cache: "no-store",
  });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(text || `Availability request failed (${r.status})`);
  }
  return (await r.json()) as AvailabilityResponse;
}

export type CalendarEventRow = {
  id?: string;
  semester_id: string;
  year_of_study: number;
  event_name: string;
  start_date: string;
  end_date: string | null;
  makes_labs_free: boolean;
  makes_labs_occupied?: boolean;
};

export async function getAcademicCalendar(
  semester_id: string,
  year_of_study: number,
): Promise<CalendarEventRow[]> {
  const qs = new URLSearchParams({
    semester_id,
    year_of_study: String(year_of_study),
  });
  const r = await fetch(`${FLASK_API_URL}/api/academic-calendar?${qs.toString()}`, {
    cache: "no-store",
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as CalendarEventRow[];
}

export async function saveAcademicCalendar(input: {
  semester_id: string;
  year_of_study: number;
  events: Array<{
    event_name: string;
    start_date: string;
    end_date?: string | null;
    makes_labs_free: boolean;
    makes_labs_occupied?: boolean;
  }>;
}) {
  const r = await fetch(`${FLASK_API_URL}/api/academic-calendar`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export type Semester = {
  id: string;
  name: string;
  start_date: string;
  end_date: string;
  is_active: boolean;
};

export async function listSemesters(): Promise<Semester[]> {
  const r = await fetch(`${FLASK_API_URL}/api/semesters`, { cache: "no-store" });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as Semester[];
}

export async function createSemester(input: {
  name: string;
  start_date: string;
  end_date: string;
  is_active?: boolean;
}): Promise<Semester> {
  const r = await fetch(`${FLASK_API_URL}/api/semesters`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as Semester;
}

export type NotificationRow = {
  id: string;
  message: string;
  is_read: boolean;
  type: string | null;
  created_at: string;
  related_lab?: string | null;
};

export async function listNotifications(): Promise<NotificationRow[]> {
  const r = await fetch(`${FLASK_API_URL}/api/notifications`, { cache: "no-store" });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as NotificationRow[];
}

export async function markNotificationRead(id: string): Promise<void> {
  const r = await fetch(`${FLASK_API_URL}/api/notifications/${id}/read`, {
    method: "PATCH",
  });
  if (!r.ok) throw new Error(await r.text());
}

export async function markAllNotificationsRead(): Promise<void> {
  const r = await fetch(`${FLASK_API_URL}/api/notifications/read-all`, {
    method: "PATCH",
  });
  if (!r.ok) throw new Error(await r.text());
}

export async function uploadTimetable(input: {
  file: File;
  semester_id: string;
}): Promise<{
  status: string;
  sessions_inserted: number;
  labs_found: string[];
  warnings: string[];
  errors: string[];
}> {
  const ext = input.file.name.toLowerCase().endsWith(".docx")
    ? "word"
    : input.file.name.toLowerCase().endsWith(".xlsx")
      ? "excel"
      : null;
  if (!ext) throw new Error("Only .xlsx or .docx files are supported");

  const fd = new FormData();
  fd.set("file", input.file);
  fd.set("semester_id", input.semester_id);

  const r = await fetch(`${FLASK_API_URL}/api/parse/${ext}`, {
    method: "POST",
    body: fd,
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as {
    status: string;
    sessions_inserted: number;
    labs_found: string[];
    warnings: string[];
    errors: string[];
  };
}

export const DEPARTMENT_BLOCKS = [
  { value: "", label: "All Departments" },
  { value: "A", label: "A Block" },
  { value: "B", label: "B Block" },
  { value: "C", label: "C Block" },
  { value: "D", label: "D Block" },
  { value: "E", label: "E Block" },
  { value: "P", label: "P Block" },
];

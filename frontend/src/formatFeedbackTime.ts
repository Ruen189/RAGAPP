const FEEDBACK_TIMEZONE = "Asia/Yekaterinburg";

export function formatFeedbackTime(value: string): string {
  const formatted = new Date(value).toLocaleString("ru-RU", {
    timeZone: FEEDBACK_TIMEZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
  return `${formatted} (GMT+5)`;
}

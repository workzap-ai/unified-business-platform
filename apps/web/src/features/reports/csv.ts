/**
 * Minimal CSV export: RFC 4180 quoting plus spreadsheet formula-injection protection,
 * downloaded in the browser via a Blob. Values stay as given (decimal strings for money).
 */
export type CsvValue = string | number | boolean | null | undefined;

const NUMERIC = /^-?\d+(\.\d+)?$/;

export function escapeCsvValue(value: CsvValue): string {
  if (value === null || value === undefined) return "";
  let text = String(value);
  // A cell starting with = + - @ (or a control char) can be executed as a formula by
  // spreadsheet apps. Prefix it so it is treated as text; plain numbers are left alone.
  if (
    typeof value === "string" &&
    /^[=+\-@\t\r]/.test(text) &&
    !NUMERIC.test(text)
  ) {
    text = `'${text}`;
  }
  if (/[",\r\n]/.test(text) || /^\s|\s$/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

export function toCsv(headers: string[], rows: CsvValue[][]): string {
  return [headers, ...rows]
    .map((row) => row.map(escapeCsvValue).join(","))
    .join("\r\n");
}

/** Builds a filename like `revenue-report-2026-09-24.csv`. */
export function csvFilename(name: string) {
  const today = new Date();
  const stamp = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
  return `${name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "")}-${stamp}.csv`;
}

export function downloadCsv(
  filename: string,
  headers: string[],
  rows: CsvValue[][],
) {
  // BOM so spreadsheet apps detect UTF-8 (currency symbols, names with accents).
  const blob = new Blob([`﻿${toCsv(headers, rows)}`], {
    type: "text/csv;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.rel = "noopener";
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

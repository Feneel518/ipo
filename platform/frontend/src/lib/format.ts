export function indiaDateKey(value = new Date()) {
  const parts = new Intl.DateTimeFormat("en-IN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    timeZone: "Asia/Kolkata",
  }).formatToParts(value);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

export function displayDate(value: string | null, options?: Intl.DateTimeFormatOptions) {
  if (!value) return "To be announced";
  return new Intl.DateTimeFormat("en-IN", options ?? { day: "2-digit", month: "short", year: "numeric" }).format(
    new Date(`${value}T00:00:00+05:30`),
  );
}

export function money(value: string | null) {
  if (!value) return "—";
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(Number(value));
}

export function priceBand(low: string | null, high: string | null) {
  const values = [low, high]
    .filter((value): value is string => value !== null && value !== "")
    .map((value) => Math.abs(Number(value)))
    .filter(Number.isFinite)
    .sort((left, right) => left - right);

  if (values.length === 0) return "—";
  const floor = money(String(values[0]));
  const ceiling = money(String(values.at(-1)));
  return values[0] === values.at(-1) ? floor : `${floor} – ${ceiling}`;
}

export function quantity(value: string | null) {
  if (!value) return "—";
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 }).format(Number(value));
}

export function humanizeLabel(value: string | null | undefined) {
  if (!value) return "—";
  const words = value.replaceAll("_", " ").toLocaleLowerCase("en-IN");
  return words.charAt(0).toLocaleUpperCase("en-IN") + words.slice(1);
}

export function displayCompanyName(value: string) {
  if (value !== value.toLocaleUpperCase("en-IN")) return value;

  return value
    .toLocaleLowerCase("en-IN")
    .replace(/(^|[\s(/&-])(\p{L})/gu, (_, boundary: string, letter: string) =>
      boundary + letter.toLocaleUpperCase("en-IN"),
    );
}

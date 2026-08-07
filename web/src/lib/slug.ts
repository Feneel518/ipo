const COMBINING_DIACRITICS = new RegExp("[\\u0300-\\u036f]", "g");

function slugify(value: string): string {
  return value
    .normalize("NFKD")
    .replace(COMBINING_DIACRITICS, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/**
 * IPOs have no stored slug column. The slug is derived on the fly from the
 * name and symbol (symbol is unique per exchange, so appending it keeps the
 * slug unique even when two issuers share a name).
 */
export function ipoSlug(ipo: { name: string; symbol: string }): string {
  return `${slugify(ipo.name)}-${ipo.symbol.toLowerCase()}`;
}

/** Best-effort symbol guess from a slug's trailing segment, used to narrow the DB lookup. */
export function symbolFromSlug(slug: string): string {
  const parts = slug.split("-");
  return parts[parts.length - 1] ?? slug;
}

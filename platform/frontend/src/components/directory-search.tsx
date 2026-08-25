"use client";

import { useEffect, useState, useTransition } from "react";
import { useRouter } from "next/navigation";

export function DirectorySearch({ initialQuery, status }: { initialQuery: string; status: string }) {
  const router = useRouter();
  const [value, setValue] = useState(initialQuery);
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    const query = value.trim();
    if (query === initialQuery) return;

    const timeout = window.setTimeout(() => {
      const params = new URLSearchParams();
      if (status) params.set("status", status);
      if (query) params.set("q", query);
      const suffix = params.toString();

      startTransition(() => {
        router.replace(suffix ? `/ipos?${suffix}` : "/ipos", { scroll: false });
      });
    }, 350);

    return () => window.clearTimeout(timeout);
  }, [initialQuery, router, status, value]);

  return (
    <div className="directory-search" role="search" aria-busy={isPending}>
      <input
        type="search"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder="Search company"
        aria-label="Search IPOs by company name"
        maxLength={100}
      />
      {value && <button type="button" onClick={() => setValue("")} aria-label="Clear search">×</button>}
      <span className="directory-search-state" aria-live="polite">{isPending ? "Searching" : ""}</span>
    </div>
  );
}

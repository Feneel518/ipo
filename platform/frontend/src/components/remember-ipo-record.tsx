"use client";

import { useEffect } from "react";
import { rememberIpo } from "@/lib/last-viewed-ipo";

export function RememberIpoRecord({ slug }: { slug: string }) {
  useEffect(() => {
    rememberIpo(slug);
  }, [slug]);

  return null;
}

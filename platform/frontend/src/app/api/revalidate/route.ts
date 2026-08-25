import { revalidatePath, revalidateTag } from "next/cache";
import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  const expected = process.env.REVALIDATION_SECRET;
  if (!expected || request.headers.get("authorization") !== `Bearer ${expected}`) return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
  revalidateTag("ipo-data", "max");
  for (const path of ["/", "/ipos", "/calendar"]) revalidatePath(path);
  revalidatePath("/ipo/[slug]", "page");
  return NextResponse.json({ revalidated: true, at: new Date().toISOString() });
}

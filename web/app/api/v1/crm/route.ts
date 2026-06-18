import { NextRequest, NextResponse } from "next/server";

const BACKEND = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(
  /\/$/,
  ""
);

export async function GET(req: NextRequest) {
  const auth = req.headers.get("authorization");
  const qs = req.nextUrl.search;
  try {
    const res = await fetch(`${BACKEND}/api/v1/crm${qs}`, {
      headers: auth ? { Authorization: auth } : {},
      cache: "no-store",
    });
    const text = await res.text();
    return new NextResponse(text, {
      status: res.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Backend unreachable";
    return NextResponse.json({ detail: msg }, { status: 502 });
  }
}

export async function POST(req: NextRequest) {
  const auth = req.headers.get("authorization");
  const body = await req.text();
  try {
    const res = await fetch(`${BACKEND}/api/v1/crm`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(auth ? { Authorization: auth } : {}),
      },
      body,
      cache: "no-store",
    });
    const text = await res.text();
    return new NextResponse(text, {
      status: res.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Backend unreachable";
    return NextResponse.json({ detail: msg }, { status: 502 });
  }
}

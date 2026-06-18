import { NextRequest, NextResponse } from "next/server";

const BACKEND = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(
  /\/$/,
  ""
);

/** Server-side proxy — reliable through Cloudflare tunnel (avoids dev rewrite cancel). */
export async function POST(req: NextRequest) {
  const auth = req.headers.get("authorization");
  const body = await req.text();
  try {
    const res = await fetch(`${BACKEND}/api/v1/crm/classify`, {
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
    return NextResponse.json(
      { detail: `CRM classify proxy failed: ${msg}. Is run_backend.ps1 running?` },
      { status: 502 }
    );
  }
}

import { NextResponse, type NextRequest } from "next/server";

/** Keep the former ?lang URLs usable without requiring JavaScript. */
export function middleware(request: NextRequest) {
  const lang = request.nextUrl.searchParams.get("lang");
  if (lang !== "pt" && lang !== "en") return NextResponse.next();
  const url = request.nextUrl.clone();
  const path = url.pathname.replace(/^\/pt(?=\/docs(?:\/|$))/, "");
  url.pathname = lang === "pt" ? `/pt${path}` : path;
  url.searchParams.delete("lang");
  return NextResponse.redirect(url, 308);
}
export const config = { matcher: ["/docs/:path*", "/pt/docs/:path*"] };

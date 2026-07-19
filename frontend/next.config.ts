import type { NextConfig } from "next";

const API_ORIGIN = process.env.API_ORIGIN ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // Pin the workspace root to this folder. A stray package-lock.json in a
  // parent directory otherwise makes Next infer the wrong root and warn.
  turbopack: {
    root: __dirname,
  },

  // Django's URLs end in a slash. Without this, Next 308-redirects
  // /api/auth/login/ to /api/auth/login before the rewrite runs, the POST
  // body is dropped on the redirect, and login fails in a way that looks
  // like a backend fault.
  skipTrailingSlashRedirect: true,

  // Proxy the API through this origin so the browser only ever talks to
  // localhost:3001. Same-origin means no CORS preflight and no
  // django-cors-headers; the session cookie is sent normally.
  //
  // This does NOT remove the need for CSRF_TRUSTED_ORIGINS on the Django
  // side: Next forwards the browser's Origin header, which will not match
  // Django's own host, so unsafe requests 403 without it.
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        // The trailing slash is re-appended here on purpose. The :path*
        // capture drops it, so Django would receive /api/auth/login and
        // APPEND_SLASH cannot redirect a POST without discarding its body.
        // Appending here normalises both spellings to exactly one slash.
        destination: `${API_ORIGIN}/api/:path*/`,
      },
    ];
  },
};

export default nextConfig;

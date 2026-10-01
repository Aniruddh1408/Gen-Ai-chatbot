// Forwards the chat UI's API calls to the FastAPI backend, which is hosted
// outside Netlify. Set BACKEND_URL (e.g. https://api.example.com) in the
// Netlify environment variables to point at it.
export default async (req: Request) => {
  const backend = Netlify.env.get("BACKEND_URL");
  if (!backend) {
    return Response.json(
      { detail: "Backend is not configured. Set the BACKEND_URL environment variable in Netlify." },
      { status: 503 },
    );
  }

  const incoming = new URL(req.url);
  const target = new URL(incoming.pathname + incoming.search, backend.replace(/\/+$/, "") + "/");

  const headers = new Headers(req.headers);
  headers.delete("host");

  return fetch(target, {
    method: req.method,
    headers,
    body: req.method === "GET" || req.method === "HEAD" ? undefined : req.body,
    redirect: "manual",
  });
};

export const config = {
  path: ["/ask", "/upload", "/upload/*", "/users", "/history/*", "/health"],
};

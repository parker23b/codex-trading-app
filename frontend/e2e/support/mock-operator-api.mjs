import http from "node:http";

import { buildScenarioRoutes } from "./scenarios.mjs";

const port = Number.parseInt(process.env.MOCK_OPERATOR_API_PORT ?? "4010", 10);

const state = {
  scenario: "default",
  routes: buildScenarioRoutes("default"),
  requests: [],
  routeCounts: {},
};

function setScenario(name) {
  state.scenario = name;
  state.routes = buildScenarioRoutes(name);
  state.requests = [];
  state.routeCounts = {};
}

function sendJson(res, status, payload) {
  res.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
    "access-control-allow-origin": "*",
    "access-control-allow-methods": "GET,POST,PUT,DELETE,OPTIONS",
    "access-control-allow-headers": "content-type,authorization",
  });
  res.end(JSON.stringify(payload));
}

function notFound(res, method, pathname) {
  sendJson(res, 404, {
    detail: `No mock fixture registered for ${method} ${pathname} in scenario ${state.scenario}.`,
  });
}

async function readBody(req) {
  const chunks = [];
  for await (const chunk of req) {
    chunks.push(Buffer.from(chunk));
  }
  const text = Buffer.concat(chunks).toString("utf8");
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", `http://${req.headers.host ?? "127.0.0.1"}`);
  const method = req.method ?? "GET";
  const pathname = url.pathname;

  if (method === "OPTIONS") {
    sendJson(res, 200, { status: "ok" });
    return;
  }

  if (pathname === "/__admin/health") {
    sendJson(res, 200, { status: "ok", scenario: state.scenario });
    return;
  }

  if (pathname === "/__admin/scenario" && method === "POST") {
    const body = await readBody(req);
    const name = typeof body?.name === "string" ? body.name : "default";
    setScenario(name);
    sendJson(res, 200, { status: "ok", scenario: state.scenario });
    return;
  }

  if (pathname === "/__admin/requests" && method === "GET") {
    sendJson(res, 200, {
      scenario: state.scenario,
      requests: state.requests,
    });
    return;
  }

  const body = method === "GET" || method === "HEAD" ? null : await readBody(req);

  state.requests.push({
    method,
    pathname,
    search: url.search,
    body,
  });

  const key = `${method} ${pathname}`;
  const configuredRoute = state.routes[key];
  const route = Array.isArray(configuredRoute)
    ? configuredRoute[Math.min(state.routeCounts[key] ?? 0, configuredRoute.length - 1)]
    : configuredRoute;
  state.routeCounts[key] = (state.routeCounts[key] ?? 0) + 1;
  if (!route) {
    notFound(res, method, pathname);
    return;
  }

  if (route.delayMs) {
    await new Promise((resolve) => setTimeout(resolve, route.delayMs));
  }

  sendJson(res, route.status, route.json);
});

server.listen(port, "127.0.0.1", () => {
  process.stdout.write(`Mock operator API listening on ${port}\n`);
});

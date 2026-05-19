const crypto = require("node:crypto");

const GITHUB_API_VERSION = "2022-11-28";
const MAX_WEBHOOK_BYTES = 1024 * 1024;

const ALLOWED_ACTIONS = {
  pull_request: new Set([
    "assigned",
    "closed",
    "converted_to_draft",
    "edited",
    "opened",
    "ready_for_review",
    "reopened",
    "synchronize",
    "unassigned",
  ]),
  issue_comment: new Set(["created", "edited", "deleted"]),
  pull_request_review: new Set(["submitted", "edited", "dismissed"]),
  pull_request_review_comment: new Set(["created", "edited", "deleted"]),
  pull_request_review_thread: new Set(["resolved", "unresolved"]),
};

exports.handler = async (event) => {
  try {
    return await handle(event);
  } catch (error) {
    console.error(error);
    return response(error.statusCode || 500, { error: error.publicMessage || "internal server error" });
  }
};

async function handle(event) {
  if (event.httpMethod !== "POST") {
    return response(405, { error: "method not allowed" });
  }

  const config = loadConfig();
  const rawBody = readRawBody(event);

  if (rawBody.length > MAX_WEBHOOK_BYTES) {
    return response(413, { error: "payload too large" });
  }

  if (!verifySignature(rawBody, getHeader(event.headers, "x-hub-signature-256"), config.webhookSecret)) {
    return response(401, { error: "invalid signature" });
  }

  const eventName = getHeader(event.headers, "x-github-event");
  if (eventName === "ping") {
    return response(202, { status: "ignored", reason: "ping" });
  }
  if (!Object.prototype.hasOwnProperty.call(ALLOWED_ACTIONS, eventName)) {
    return response(202, { status: "ignored", reason: `unsupported event: ${eventName || "missing"}` });
  }

  const payload = parseJson(rawBody);
  const action = payload.action;
  if (!ALLOWED_ACTIONS[eventName].has(action)) {
    return response(202, { status: "ignored", reason: `unsupported action: ${eventName}.${action || "missing"}` });
  }

  const repository = readRepository(payload);
  if (!repository.fullName) {
    return response(202, { status: "ignored", reason: "missing repository" });
  }
  if (repository.owner !== config.owner) {
    return response(202, { status: "ignored", reason: `unsupported repository owner: ${repository.owner || "missing"}` });
  }

  const prNumber = extractPullRequestNumber(eventName, payload);
  if (!Number.isInteger(prNumber) || prNumber <= 0) {
    return response(202, { status: "ignored", reason: "no pull request number found" });
  }

  const installationToken = await createInstallationToken(config);
  await dispatchWorkflow(config, installationToken, repository.fullName, {
    pr_number: String(prNumber),
    trigger_event: eventName,
    trigger_action: action,
  });

  return response(202, {
    status: "dispatched",
    repository: repository.fullName,
    pr_number: prNumber,
    trigger_event: eventName,
    trigger_action: action,
  });
}

function loadConfig() {
  const config = {
    appId: process.env.GITHUB_APP_ID,
    privateKey: normalizePrivateKey(process.env.GITHUB_APP_PRIVATE_KEY, process.env.GITHUB_APP_PRIVATE_KEY_BASE64),
    installationId: process.env.GITHUB_APP_INSTALLATION_ID,
    webhookSecret: process.env.GITHUB_WEBHOOK_SECRET,
    owner: process.env.GITHUB_OWNER || "open-telemetry",
    workflowId: process.env.GITHUB_WORKFLOW_ID || "pull-request-dashboard.yml",
    workflowRef: process.env.GITHUB_WORKFLOW_REF || "main",
  };

  const missing = Object.entries(config)
    .filter(([, value]) => !value)
    .map(([key]) => key);
  if (missing.length > 0) {
    throw httpError(500, "missing required configuration", `missing required configuration: ${missing.join(", ")}`);
  }

  return config;
}

function readRepository(payload) {
  const repository = payload.repository || {};
  return {
    fullName: repository.full_name,
    owner: repository.owner && repository.owner.login,
  };
}

function readRawBody(event) {
  if (!event.body) {
    return Buffer.alloc(0);
  }
  return event.isBase64Encoded ? Buffer.from(event.body, "base64") : Buffer.from(event.body, "utf8");
}

function verifySignature(rawBody, signatureHeader, secret) {
  if (!signatureHeader || !signatureHeader.startsWith("sha256=")) {
    return false;
  }

  const expected = Buffer.from(signatureHeader.slice("sha256=".length), "hex");
  const actual = crypto.createHmac("sha256", secret).update(rawBody).digest();

  return expected.length === actual.length && crypto.timingSafeEqual(expected, actual);
}

function parseJson(rawBody) {
  try {
    return JSON.parse(rawBody.toString("utf8"));
  } catch (error) {
    throw httpError(400, "invalid JSON payload", `invalid JSON payload: ${error.message}`);
  }
}

function extractPullRequestNumber(eventName, payload) {
  if (eventName === "issue_comment") {
    if (!payload.issue || !payload.issue.pull_request) {
      return undefined;
    }
    return payload.issue.number;
  }

  if (payload.pull_request && Number.isInteger(payload.pull_request.number)) {
    return payload.pull_request.number;
  }

  return extractPullRequestNumberFromUrls([
    payload.pull_request_url,
    payload.review_thread && payload.review_thread.pull_request_url,
    payload.thread && payload.thread.pull_request_url,
  ]);
}

function extractPullRequestNumberFromUrls(urls) {
  for (const url of urls) {
    if (typeof url !== "string") {
      continue;
    }
    const match = url.match(/\/pulls\/(\d+)(?:$|[/?#])/);
    if (match) {
      return Number.parseInt(match[1], 10);
    }
  }
  return undefined;
}

async function createInstallationToken(config) {
  const response = await githubFetch(
    `https://api.github.com/app/installations/${config.installationId}/access_tokens`,
    {
      method: "POST",
      headers: {
        authorization: `Bearer ${createAppJwt(config)}`,
      },
    },
  );

  const body = await response.json();
  if (!body.token) {
    throw httpError(502, "GitHub token request failed", "GitHub installation token response did not include a token");
  }
  return body.token;
}

async function dispatchWorkflow(config, token, repository, inputs) {
  const encodedWorkflowId = encodeURIComponent(config.workflowId);
  await githubFetch(
    `https://api.github.com/repos/${encodeRepository(repository)}/actions/workflows/${encodedWorkflowId}/dispatches`,
    {
      method: "POST",
      headers: {
        authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        ref: config.workflowRef,
        inputs,
      }),
    },
  );
}

function encodeRepository(repository) {
  return repository.split("/").map(encodeURIComponent).join("/");
}

async function githubFetch(url, options) {
  const response = await fetch(url, {
    ...options,
    headers: {
      accept: "application/vnd.github+json",
      "content-type": "application/json",
      "user-agent": "pull-request-dashboard-webhook",
      "x-github-api-version": GITHUB_API_VERSION,
      ...options.headers,
    },
  });

  if (!response.ok) {
    const body = await response.text();
    throw httpError(
      502,
      "GitHub API request failed",
      `GitHub API request failed: ${response.status} ${response.statusText}: ${body}`,
    );
  }

  return response;
}

function createAppJwt(config) {
  const now = Math.floor(Date.now() / 1000);
  const header = base64UrlJson({ alg: "RS256", typ: "JWT" });
  const payload = base64UrlJson({
    iat: now - 60,
    exp: now + 10 * 60,
    iss: config.appId,
  });
  const unsignedToken = `${header}.${payload}`;
  const signature = crypto.sign("RSA-SHA256", Buffer.from(unsignedToken), config.privateKey);

  return `${unsignedToken}.${base64Url(signature)}`;
}

function base64UrlJson(value) {
  return base64Url(Buffer.from(JSON.stringify(value)));
}

function base64Url(buffer) {
  return buffer
    .toString("base64")
    .replace(/=/g, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_");
}

function normalizePrivateKey(value, base64Value) {
  const rawValue = base64Value ? Buffer.from(base64Value, "base64").toString("utf8") : value;
  return rawValue && rawValue.trim().replace(/^['"]|['"]$/g, "").replace(/\\n/g, "\n");
}

function getHeader(headers, name) {
  const lowerName = name.toLowerCase();
  const entry = Object.entries(headers || {}).find(([key]) => key.toLowerCase() === lowerName);
  return entry && entry[1];
}

function response(statusCode, body) {
  return {
    statusCode,
    headers: {
      "content-type": "application/json",
    },
    body: JSON.stringify(body),
  };
}

function httpError(statusCode, publicMessage, message) {
  const error = new Error(message);
  error.statusCode = statusCode;
  error.publicMessage = publicMessage;
  return error;
}

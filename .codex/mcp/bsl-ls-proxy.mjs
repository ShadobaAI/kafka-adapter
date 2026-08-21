import fs from "node:fs";
import path from "node:path";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath, pathToFileURL } from "node:url";

const BSL_LS_JAR = ".\\bsl-language-server-1.0.7-exec.jar";
const BSL_LS_CONFIGURATION = ".bsl-language-server.json";
const MAX_HELPER_OUTPUT = 64 * 1024;

function failStartup(message) {
  process.stderr.write(`bsl-ls-proxy: ${message}\n`);
  process.exit(1);
}

function parseRootArgument(argv) {
  const rootIndex = argv.indexOf("--root");
  if (rootIndex === -1 || rootIndex === argv.length - 1 || !argv[rootIndex + 1]) {
    failStartup("missing required --root argument");
  }

  return argv[rootIndex + 1];
}

const repositoryRoot = path.resolve(parseRootArgument(process.argv.slice(2)));

if (!fs.existsSync(repositoryRoot) || !fs.statSync(repositoryRoot).isDirectory()) {
  failStartup("repository root does not exist or is not a directory");
}

if (!fs.existsSync(BSL_LS_JAR) || !fs.statSync(BSL_LS_JAR).isFile()) {
  failStartup("BSL Language Server JAR does not exist");
}

const configurationPath = path.join(repositoryRoot, BSL_LS_CONFIGURATION);
if (!fs.existsSync(configurationPath) || !fs.statSync(configurationPath).isFile()) {
  failStartup("BSL Language Server configuration does not exist");
}

const repositoryRealPath = fs.realpathSync.native(repositoryRoot);
const repositoryUri = pathToFileURL(repositoryRealPath).href;
const pendingPathRestorations = new Map();

const shortPathPowerShell = String.raw`
$nativeSource = @'
using System;
using System.Runtime.InteropServices;
using System.Text;

public static class BslLsProxyNativeMethods
{
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern uint GetShortPathName(
        string longPath,
        StringBuilder shortPath,
        uint bufferLength);
}
'@

Add-Type -TypeDefinition $nativeSource -ErrorAction Stop
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
$longPath = [Console]::In.ReadToEnd()
$buffer = New-Object System.Text.StringBuilder 32768
$length = [BslLsProxyNativeMethods]::GetShortPathName(
    $longPath,
    $buffer,
    [uint32]$buffer.Capacity)

if ($length -eq 0 -or $length -ge $buffer.Capacity) {
    exit 1
}

[Console]::Out.Write($buffer.ToString())
`;

const encodedShortPathPowerShell = Buffer.from(
  shortPathPowerShell,
  "utf16le",
).toString("base64");

function requestKey(id) {
  return `${typeof id}:${JSON.stringify(id)}`;
}

function isInsideRepository(targetPath) {
  const relativePath = path.relative(repositoryRealPath, targetPath);
  return (
    relativePath === "" ||
    (!relativePath.startsWith(`..${path.sep}`) &&
      relativePath !== ".." &&
      !path.isAbsolute(relativePath))
  );
}

function parseFileArgument(fileArgument) {
  if (typeof fileArgument !== "string" || fileArgument.length === 0) {
    throw new Error("invalid-file");
  }

  const isFileUri = /^file:/i.test(fileArgument);
  let resolvedPath;

  try {
    resolvedPath = isFileUri
      ? fileURLToPath(new URL(fileArgument))
      : path.resolve(repositoryRoot, fileArgument);
  } catch {
    throw new Error("invalid-file");
  }

  if (!fs.existsSync(resolvedPath)) {
    throw new Error("missing-file");
  }

  let realPath;
  try {
    realPath = fs.realpathSync.native(resolvedPath);
  } catch {
    throw new Error("missing-file");
  }

  if (!isInsideRepository(realPath)) {
    throw new Error("outside-root");
  }

  if (!fs.statSync(realPath).isFile()) {
    throw new Error("not-file");
  }

  return { isFileUri, realPath };
}

function getWindowsShortPath(longPath) {
  const result = spawnSync(
    "powershell.exe",
    [
      "-NoLogo",
      "-NoProfile",
      "-NonInteractive",
      "-EncodedCommand",
      encodedShortPathPowerShell,
    ],
    {
      encoding: "utf8",
      input: longPath,
      maxBuffer: MAX_HELPER_OUTPUT,
      shell: false,
      timeout: 10_000,
      windowsHide: true,
    },
  );

  const shortPath = result.status === 0 ? result.stdout : "";
  if (!shortPath || /[^\x00-\x7f]/.test(shortPath)) {
    throw new Error("short-path-unavailable");
  }

  if (!fs.existsSync(shortPath) || !fs.statSync(shortPath).isFile()) {
    throw new Error("short-path-invalid");
  }

  return shortPath;
}

function escapeRegularExpression(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function createPathReplacements(shortPath, originalArgument, longPath, isFileUri) {
  const shortUri = pathToFileURL(shortPath).href;
  const longUri = pathToFileURL(longPath).href;
  const longOutputPath = isFileUri ? longPath : originalArgument;
  const shortJsonPath = JSON.stringify(shortPath).slice(1, -1);
  const longJsonPath = JSON.stringify(longOutputPath).slice(1, -1);

  return [
    [shortUri, isFileUri ? originalArgument : longUri],
    [shortJsonPath, longJsonPath],
    [shortPath.replaceAll("\\", "/"), longOutputPath.replaceAll("\\", "/")],
    [shortPath, longOutputPath],
  ].sort(([left], [right]) => right.length - left.length);
}

function restoreString(value, replacements) {
  let restored = value;
  for (const [shortValue, longValue] of replacements) {
    restored = restored.replace(
      new RegExp(escapeRegularExpression(shortValue), "gi"),
      () => longValue,
    );
  }
  return restored;
}

function restorePaths(value, replacements) {
  if (typeof value === "string") {
    return restoreString(value, replacements);
  }

  if (Array.isArray(value)) {
    return value.map((item) => restorePaths(item, replacements));
  }

  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [
        key,
        restorePaths(item, replacements),
      ]),
    );
  }

  return value;
}

function writeJson(stream, message) {
  stream.write(`${JSON.stringify(message)}\n`);
}

function writeJsonRpcError(id) {
  if (id === undefined) {
    return;
  }

  writeJson(process.stdout, {
    jsonrpc: "2.0",
    id,
    error: {
      code: -32602,
      message:
        "arguments.file must identify an existing file inside the repository root",
    },
  });
}

const child = spawn(
  "java",
  [
    "-jar",
    BSL_LS_JAR,
    `--configuration=${BSL_LS_CONFIGURATION}`,
    "mcp",
  ],
  {
    cwd: repositoryRoot,
    shell: false,
    stdio: ["pipe", "pipe", "pipe"],
    windowsHide: true,
  },
);

child.stderr.pipe(process.stderr);

function handleClientMessage(line) {
  let message;
  try {
    message = JSON.parse(line);
  } catch {
    child.stdin.write(`${line}\n`);
    return;
  }

  if (message && message.method === "initialize") {
    message.params ??= {};
    message.params.capabilities ??= {};
    message.params.capabilities.roots ??= {};
    message.params.capabilities.roots.listChanged = false;
  }

  const fileArgument = message?.params?.arguments?.file;
  if (message?.method === "tools/call" && fileArgument !== undefined) {
    if (!Object.hasOwn(message, "id")) {
      return;
    }

    try {
      const { isFileUri, realPath } = parseFileArgument(fileArgument);

      if (process.platform === "win32" && /[^\x00-\x7f]/.test(realPath)) {
        const shortPath = getWindowsShortPath(realPath);
        const key = requestKey(message.id);

        if (pendingPathRestorations.has(key)) {
          throw new Error("duplicate-request-id");
        }

        message.params.arguments.file = isFileUri
          ? pathToFileURL(shortPath).href
          : shortPath;
        pendingPathRestorations.set(
          key,
          createPathReplacements(
            shortPath,
            fileArgument,
            realPath,
            isFileUri,
          ),
        );
      }
    } catch {
      writeJsonRpcError(message.id);
      return;
    }
  }

  writeJson(child.stdin, message);
}

function handleServerMessage(line) {
  let message;
  try {
    message = JSON.parse(line);
  } catch {
    return;
  }

  if (message && message.method === "roots/list") {
    if (Object.hasOwn(message, "id")) {
      writeJson(child.stdin, {
        jsonrpc: "2.0",
        id: message.id,
        result: {
          roots: [
            {
              uri: repositoryUri,
              name: path.basename(repositoryRealPath),
            },
          ],
        },
      });
    }
    return;
  }

  if (message && Object.hasOwn(message, "id")) {
    const key = requestKey(message.id);
    const replacements = pendingPathRestorations.get(key);

    if (replacements) {
      if (Object.hasOwn(message, "result")) {
        message.result = restorePaths(message.result, replacements);
      }
      if (Object.hasOwn(message, "error")) {
        message.error = restorePaths(message.error, replacements);
      }
      pendingPathRestorations.delete(key);
    }
  }

  writeJson(process.stdout, message);
}

function consumeLines(stream, handler) {
  let buffer = "";
  stream.setEncoding("utf8");
  stream.on("data", (chunk) => {
    buffer += chunk;
    let newlineIndex;

    while ((newlineIndex = buffer.indexOf("\n")) !== -1) {
      let line = buffer.slice(0, newlineIndex);
      buffer = buffer.slice(newlineIndex + 1);
      if (line.endsWith("\r")) {
        line = line.slice(0, -1);
      }
      if (line) {
        handler(line);
      }
    }
  });
  stream.on("end", () => {
    const line = buffer.endsWith("\r") ? buffer.slice(0, -1) : buffer;
    if (line) {
      handler(line);
    }
  });
}

consumeLines(process.stdin, handleClientMessage);
consumeLines(child.stdout, handleServerMessage);

let stoppingSignal;
let forceStopTimer;

function stopChild(signal) {
  if (stoppingSignal) {
    return;
  }

  stoppingSignal = signal;
  child.kill(signal);
  forceStopTimer = setTimeout(() => child.kill("SIGKILL"), 5_000);
  forceStopTimer.unref();
}

process.on("SIGINT", () => stopChild("SIGINT"));
process.on("SIGTERM", () => stopChild("SIGTERM"));
process.stdin.on("end", () => child.stdin.end());
process.stdout.on("error", (error) => {
  if (error.code === "EPIPE") {
    stopChild("SIGTERM");
  }
});

child.on("error", () => {
  process.stderr.write("bsl-ls-proxy: failed to start BSL Language Server\n");
  process.exitCode = 1;
});

child.on("exit", (code) => {
  if (forceStopTimer) {
    clearTimeout(forceStopTimer);
  }

  if (stoppingSignal === "SIGINT") {
    process.exitCode = 130;
  } else if (stoppingSignal === "SIGTERM") {
    process.exitCode = 143;
  } else {
    process.exitCode = code ?? 1;
  }
});

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath, pathToFileURL } from "node:url";

const MAX_HELPER_OUTPUT = 64 * 1024;

function failStartup(message) {
  process.stderr.write(`bsl-ls-proxy: ${message}\n`);
  process.exit(1);
}

const nodeMajorVersion = Number.parseInt(process.versions.node.split(".", 1)[0], 10);
if (!Number.isInteger(nodeMajorVersion) || nodeMajorVersion < 18) {
  failStartup(`Node.js 18 or newer is required; current version is ${process.versions.node}`);
}

function parseArguments(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (!argument.startsWith("--") || index === argv.length - 1) {
      failStartup(`invalid argument '${argument}'`);
    }
    const value = argv[index + 1];
    if (!value || value.startsWith("--")) {
      failStartup(`missing value for '${argument}'`);
    }
    result[argument.slice(2)] = value;
    index += 1;
  }
  return result;
}

function resolveExistingFile(value, basePath, description) {
  if (!value) {
    return undefined;
  }
  const resolved = path.isAbsolute(value) ? value : path.resolve(basePath, value);
  if (!fs.existsSync(resolved) || !fs.statSync(resolved).isFile()) {
    failStartup(`${description} does not exist: '${resolved}'`);
  }
  return resolved;
}

function resolveJar(options, repositoryRoot) {
  const explicitJar = options.jar || process.env.BSL_LANGUAGE_SERVER_JAR;
  if (explicitJar) {
    return resolveExistingFile(explicitJar, repositoryRoot, "BSL Language Server JAR");
  }

  const codexHome = process.env.CODEX_HOME || path.join(os.homedir(), ".codex");
  const searchRoots = [repositoryRoot, path.join(codexHome, "bsl-ls")];
  const discoveredJars = [];
  for (const searchRoot of searchRoots) {
    if (!fs.existsSync(searchRoot) || !fs.statSync(searchRoot).isDirectory()) {
      continue;
    }
    const conventionalJar = path.join(searchRoot, "bsl-language-server-exec.jar");
    if (fs.existsSync(conventionalJar) && fs.statSync(conventionalJar).isFile()) {
      discoveredJars.push(conventionalJar);
    }
    for (const name of fs.readdirSync(searchRoot)) {
      if (/^bsl-language-server-.*-exec\.jar$/i.test(name)) {
        discoveredJars.push(path.join(searchRoot, name));
      }
    }
  }

  const uniqueJars = [...new Set(discoveredJars.map((jar) => path.resolve(jar)))];
  if (uniqueJars.length === 1) {
    return uniqueJars[0];
  }
  if (uniqueJars.length > 1) {
    failStartup(
      "multiple BSL Language Server JARs found; set BSL_LANGUAGE_SERVER_JAR or --jar explicitly",
    );
  }
  failStartup(
    "BSL Language Server JAR is missing; set BSL_LANGUAGE_SERVER_JAR or place one JAR in the repository root or CODEX_HOME/bsl-ls",
  );
}

const options = parseArguments(process.argv.slice(2));
if (!options.root) {
  failStartup("missing required --root argument");
}

const repositoryRoot = path.resolve(options.root);
if (!fs.existsSync(repositoryRoot) || !fs.statSync(repositoryRoot).isDirectory()) {
  failStartup(`repository root does not exist or is not a directory: '${repositoryRoot}'`);
}

const configurationPath = resolveExistingFile(
  options.configuration || ".bsl-language-server.json",
  repositoryRoot,
  "BSL Language Server configuration",
);
const bslLanguageServerJar = resolveJar(options, repositoryRoot);
const javaCommand = options.java || process.env.BSL_LANGUAGE_SERVER_JAVA || "java";
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

function writeJsonRpcError(id, message) {
  if (id === undefined) {
    return;
  }
  writeJson(process.stdout, {
    jsonrpc: "2.0",
    id,
    error: {
      code: -32602,
      message,
    },
  });
}

const child = spawn(
  javaCommand,
  [
    "-jar",
    bslLanguageServerJar,
    `--configuration=${configurationPath}`,
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
          createPathReplacements(shortPath, fileArgument, realPath, isFileUri),
        );
      }
    } catch (error) {
      const errorMessage = error.message === "short-path-unavailable"
        ? "Windows 8.3 short paths are required for BSL LS file requests whose paths contain non-ASCII characters; enable short-name creation for the volume or use a BSL LS version that accepts Unicode paths"
        : "arguments.file must identify an existing file inside the repository root";
      writeJsonRpcError(message.id, errorMessage);
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
          roots: [{ uri: repositoryUri, name: path.basename(repositoryRealPath) }],
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
process.stdin.on("end", () => {
  if (!child.stdin.destroyed) {
    child.stdin.end();
  }
});
process.stdout.on("error", (error) => {
  if (error.code === "EPIPE") {
    stopChild("SIGTERM");
  }
});

let childStartFailed = false;
child.on("error", (error) => {
  childStartFailed = true;
  process.stderr.write(
    `bsl-ls-proxy: failed to start BSL Language Server: ${error.message}\n`,
  );
});

child.stdin.on("error", (error) => {
  if (error.code !== "EPIPE" && error.code !== "ERR_STREAM_DESTROYED") {
    process.stderr.write(`bsl-ls-proxy: BSL Language Server input failed: ${error.message}\n`);
  }
});

child.on("close", (code) => {
  if (forceStopTimer) {
    clearTimeout(forceStopTimer);
  }
  process.stdin.pause();
  process.stdin.destroy();
  if (stoppingSignal === "SIGINT") {
    process.exitCode = 130;
  } else if (stoppingSignal === "SIGTERM") {
    process.exitCode = 143;
  } else {
    process.exitCode = childStartFailed ? 1 : (code ?? 1);
  }
  process.stdout.end();
});

import { spawn } from "node:child_process";

export interface DoctorResult {
  uvxAvailable: boolean;
  uvxVersion?: string;
  hint?: string;
}

const INSTALL_HINT =
  "Install uv from https://docs.astral.sh/uv/getting-started/installation/ — uvx ships with uv and is required to run the memanto server.";

/**
 * Check that `uvx` is on PATH. Returns a result describing what we found.
 * Throws nothing — it's diagnostic.
 */
export async function doctor(uvxPath = "uvx"): Promise<DoctorResult> {
  try {
    const version = await run(uvxPath, ["--version"]);
    return { uvxAvailable: true, uvxVersion: version.trim() };
  } catch (err) {
    const code = (err as NodeJS.ErrnoException).code;
    if (code === "ENOENT") {
      return { uvxAvailable: false, hint: INSTALL_HINT };
    }
    return {
      uvxAvailable: false,
      hint: `Found uvx but it failed to run: ${(err as Error).message}. ${INSTALL_HINT}`,
    };
  }
}

function run(cmd: string, args: string[]): Promise<string> {
  return new Promise((resolve, reject) => {
    const child = spawn(cmd, args, { stdio: ["ignore", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (b) => (stdout += b.toString()));
    child.stderr.on("data", (b) => (stderr += b.toString()));
    let settled = false;
    child.on("error", (err) => {
      if (settled) return;
      settled = true;
      reject(err);
    });
    child.on("close", (code) => {
      if (settled) return;
      settled = true;
      if (code === 0) resolve(stdout || stderr);
      else reject(new Error(stderr || `exit ${code}`));
    });
  });
}

/* Isolated local API and browser verification with synthetic data only. */
const { spawn, spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const root = path.resolve(__dirname, "..");
const python =
  process.env.VIETBIZ_TEST_PYTHON || path.join(root, ".venv/bin/python");
const port = process.env.VIETBIZ_UI_PORT || "8766";
const directory = fs.mkdtempSync(path.join(os.tmpdir(), "vietbiz-ui-"));
const env = {
  ...process.env,
  VIETBIZ_ENV: "test",
  VIETBIZ_AUTH_MODE: "demo",
  VIETBIZ_DATA_DIR: directory,
  VIETBIZ_DATABASE_URL: "sqlite:///" + path.join(directory, "ui.db"),
  VIETBIZ_UI_URL: `http://127.0.0.1:${port}/workspace/`,
};
const cwd = path.join(root, "services/api");

(async () => {
  const migration = spawnSync(python, ["-m", "alembic", "upgrade", "head"], {
    cwd,
    env,
    stdio: "inherit",
  });
  if (migration.error) throw migration.error;
  if (migration.status !== 0) throw Error("Test database migration failed");
  const api = spawn(
    python,
    ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", port],
    { cwd, env, stdio: "ignore" },
  );
  let launchError;
  api.on("error", (error) => {
    launchError = error;
  });
  try {
    let ready = false;
    for (let i = 0; i < 100; i++) {
      if (launchError) throw launchError;
      if (api.exitCode !== null)
        throw Error("Local test API exited before startup");
      try {
        const r = await fetch(`http://127.0.0.1:${port}/health`);
        if (r.ok) {
          ready = true;
          break;
        }
      } catch {}
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    if (!ready) throw Error("Local test API did not start");
    const code = await new Promise((resolve, reject) => {
      const browser = spawn(process.execPath, ["scripts/test-workspace.cjs"], {
        cwd: root,
        env,
        stdio: "inherit",
      });
      browser.on("error", reject);
      browser.on("exit", resolve);
    });
    if (code !== 0) throw Error("Browser checks failed");
  } finally {
    api.kill("SIGTERM");
    await new Promise((resolve) =>
      api.exitCode !== null ? resolve() : api.once("exit", resolve),
    );
    fs.rmSync(directory, { recursive: true, force: true });
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});

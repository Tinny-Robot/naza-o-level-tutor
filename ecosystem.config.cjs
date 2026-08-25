/**
 * PM2 process file for Naza O-Level tutor (API + production UI).
 *
 *   pm2 start ecosystem.config.cjs
 *   pm2 save
 *
 * Serves:
 *   - FastAPI IPC  → http://127.0.0.1:8010  (loopback; UI proxies /api)
 *   - Static UI    → http://0.0.0.0:5151     (public bind; proxies /api → :8010)
 */
const path = require("path");

const ROOT = __dirname;
const VENV_PYTHON = path.join(ROOT, ".venv", "bin", "python");
const DIST = path.join(ROOT, "desktop", "dist");

module.exports = {
  apps: [
    {
      name: "naza-api",
      cwd: ROOT,
      script: VENV_PYTHON,
      args: "scripts/serve_api.py",
      interpreter: "none",
      instances: 1,
      autorestart: true,
      max_restarts: 10,
      min_uptime: "30s",
      kill_timeout: 30000,
      env: {
        HF_HUB_OFFLINE: "1",
        TRANSFORMERS_OFFLINE: "1",
        PYTHONUNBUFFERED: "1",
      },
      error_file: path.join(ROOT, "logs", "pm2-api-error.log"),
      out_file: path.join(ROOT, "logs", "pm2-api-out.log"),
      merge_logs: true,
      time: true,
    },
    {
      name: "naza-ui",
      cwd: ROOT,
      script: VENV_PYTHON,
      args: `-m launcher.static_server --host 0.0.0.0 --port 5151 --root ${DIST} --allow-all-interfaces`,
      interpreter: "none",
      instances: 1,
      autorestart: true,
      max_restarts: 10,
      min_uptime: "5s",
      kill_timeout: 5000,
      env: {
        HF_HUB_OFFLINE: "1",
        TRANSFORMERS_OFFLINE: "1",
        PYTHONUNBUFFERED: "1",
        NAZA_DOCKER: "1",
      },
      error_file: path.join(ROOT, "logs", "pm2-ui-error.log"),
      out_file: path.join(ROOT, "logs", "pm2-ui-out.log"),
      merge_logs: true,
      time: true,
    },
  ],
};

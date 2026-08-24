/**
 * PM2 process file for ADTC offline desktop stack.
 *
 *   pm2 start ecosystem.config.cjs
 *   pm2 save
 *
 * Serves:
 *   - FastAPI IPC  → http://127.0.0.1:8010
 *   - Vite UI      → http://127.0.0.1:5151  (proxies /api → :8010)
 */
const path = require("path");

const ROOT = __dirname;
const VENV_PYTHON = path.join(ROOT, ".venv", "bin", "python");

module.exports = {
  apps: [
    {
      name: "olevel-api",
      cwd: ROOT,
      script: VENV_PYTHON,
      args: "scripts/serve_api.py",
      interpreter: "none",
      instances: 1,
      autorestart: true,
      max_restarts: 10,
      min_uptime: "10s",
      kill_timeout: 15000,
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
      name: "olevel-ui",
      cwd: path.join(ROOT, "desktop"),
      script: "npm",
      args: "run dev -- --host 127.0.0.1 --port 5151 --strictPort",
      interpreter: "none",
      instances: 1,
      autorestart: true,
      max_restarts: 10,
      min_uptime: "5s",
      env: {
        NODE_ENV: "development",
      },
      error_file: path.join(ROOT, "logs", "pm2-ui-error.log"),
      out_file: path.join(ROOT, "logs", "pm2-ui-out.log"),
      merge_logs: true,
      time: true,
    },
  ],
};

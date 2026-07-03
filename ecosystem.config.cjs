// pm2 process definitions for running Zify in production.
//   pm2 start ecosystem.config.cjs
//   pm2 save && pm2 startup
//
// Ports: admin 3010, agent 3011 (from AGENT_PORT in the root .env), bot none.
module.exports = {
  apps: [
    {
      name: "zify-admin",
      cwd: "./apps/admin",
      script: "bun",
      args: "run start",
      env: { PORT: "3010", NODE_ENV: "production" },
    },
    {
      name: "zify-agent",
      cwd: "./apps/agent",
      // Run the venv Python directly so pm2 doesn't need `uv` on its PATH.
      // AGENT_PORT is read from the root .env by main.py.
      script: ".venv/bin/python",
      args: "main.py",
      interpreter: "none",
    },
    {
      name: "zify-bot",
      cwd: "./apps/telegram-bot",
      script: "bun",
      args: "run start",
    },
  ],
}

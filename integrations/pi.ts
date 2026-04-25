// sttui: speech-to-text terminal app. User may be dictating thoughts.

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { existsSync, mkdirSync, writeFileSync, unlinkSync } from "node:fs";

const runtimeDir = process.env.XDG_RUNTIME_DIR || tmpdir();
const socketDir = join(runtimeDir, "pi");
const socketPath = join(socketDir, "sttui.sock");

export default function (pi: ExtensionAPI) {
  pi.registerCommand("sttui", {
    description: "Show sttui socket connection info",
    handler: async (_args, ctx) => {
      const steerCmd = `sttui run --send-socket ${socketPath} --send-body '{"message": $0, "deliverAs": "steer"}'`;
      const followUpCmd = `sttui run --send-socket ${socketPath} --send-body '{"message": $0, "deliverAs": "followUp"}'`;

      // Show as widget with copy-pasteable commands
      ctx.ui.setWidget("sttui", [
        "# Dictate to pi while agent is running:",
        "",
        "# After current tool (steer)",
        steerCmd,
        "",
        "",
        "# After agent finishes (followUp)",
        followUpCmd,
      ]);

      // Auto-clear widget after 10 seconds
      setTimeout(() => {
        ctx.ui.setWidget("sttui", []);
      }, 10000);
    },
  });

  if (!existsSync(socketDir)) mkdirSync(socketDir, { recursive: true });
  try { unlinkSync(socketPath); } catch {}

  const server = createServer((socket) => {
    socket.on("data", (data) => {
      try {
        const cmd = JSON.parse(data.toString());
        if (cmd.message) {
          pi.sendUserMessage(cmd.message, { deliverAs: cmd.deliverAs });
        }
      } catch {}
    });
  });

  server.listen(socketPath, () => {
    writeFileSync(join(socketDir, "socket-path"), socketPath, "utf8");
    console.log(`[sttui] Listening on ${socketPath}`);
    pi.sendMessage({
      customType: "sttui-socket",
      content: "[MESSAGE FOR THE USER] 🎤 type /sttui to start dictating",
      display: true,
    });
  });

  pi.on("session_shutdown", () => {
    server.close();
    try { unlinkSync(socketPath); } catch {}
    try { unlinkSync(join(socketDir, "socket-path")); } catch {}
  });
}
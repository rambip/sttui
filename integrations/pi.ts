import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { existsSync, mkdirSync, writeFileSync, unlinkSync } from "node:fs";

const runtimeDir = process.env.XDG_RUNTIME_DIR || tmpdir();
const socketDir = join(runtimeDir, "pi");
const socketPath = join(socketDir, "sttui.sock");

export default function (pi: ExtensionAPI) {
  if (!existsSync(socketDir)) mkdirSync(socketDir, { recursive: true });
  try { unlinkSync(socketPath); } catch {}

  const server = createServer((socket) => {
    socket.on("data", (data) => {
      try {
        const cmd = JSON.parse(data.toString());
        if (cmd.message) pi.sendUserMessage(cmd.message);
      } catch {}
    });
  });

  server.listen(socketPath, () => {
    writeFileSync(join(socketDir, "socket-path"), socketPath, "utf8");
    console.log(`[sttui] Listening on ${socketPath}`);
    pi.sendMessage({
      customType: "sttui-socket",
      content: `# Connect sttui to pi agent\n\`\`\`\nsttui send --socket ${socketPath} --body '{"message": $0}'\n\`\`\`\n`,
      display: true,
    });
  });

  pi.on("session_shutdown", () => {
    server.close();
    try { unlinkSync(socketPath); } catch {}
    try { unlinkSync(join(socketDir, "socket-path")); } catch {}
  });
}

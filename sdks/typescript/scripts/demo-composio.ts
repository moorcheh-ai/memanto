import { Memanto } from "../src/index.js";
import { createMemantoComposioTools } from "../src/integrations/composio.js";

/**
 * Stand-in for a real Composio client. It just echoes the registration
 * options back as the "tool", so `tools.recallMemory.execute(...)` calls the
 * exact same code a real Composio-run agent would call — this is only
 * faking the Composio side, not the Memanto side.
 */
function fakeComposio() {
  return {
    tools: {
      createCustomTool: async (body: Record<string, unknown>) => body,
    },
  } as never;
}

async function main() {
  const memanto = new Memanto({ agentId: "composio-demo" });

  const tools = await createMemantoComposioTools(memanto, fakeComposio());

  console.log("\n--- remembering a fact ---");
  const rememberResult = await (tools.rememberMemory as never as { execute: Function }).execute({
    content: "Alex drinks oat milk, not dairy",
    type: "preference",
  });
  console.log(rememberResult);

  // give the server a moment to finish indexing before we ask for it back
  await new Promise((resolve) => setTimeout(resolve, 2000));

  console.log("\n--- recalling it back ---");
  const recallResult = await (tools.recallMemory as never as { execute: Function }).execute({
    query: "what milk does Alex drink?",
  });
  console.log(recallResult);

  console.log("\n--- asking a question against memory ---");
  const answerResult = await (tools.answerMemory as never as { execute: Function }).execute({
    question: "Does Alex drink dairy?",
  });
  console.log(answerResult);

  await memanto.close();
  process.exit(0);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

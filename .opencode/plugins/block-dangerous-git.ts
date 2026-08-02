import type { Plugin } from "@opencode-ai/plugin"

const DANGEROUS: RegExp[] = [
  /\bgit\s+push\b/,
  /\bgit\s+reset\s+--hard\b/,
  /\bgit\s+clean\s+--force\b/,
  /\bgit\s+clean\s+-f/,
  /\bgit\s+branch\s+-D\b/,
  /\bgit\s+checkout\s+\./,
  /\bgit\s+restore\s+\./,
]

export const BlockDangerousGit: Plugin = async () => {
  return {
    "tool.execute.before": async (input, output) => {
      if (input.tool !== "bash") return
      const cmd = (output.args as { command?: string }).command ?? ""
      for (const pattern of DANGEROUS) {
        if (pattern.test(cmd)) {
          throw new Error(
            `BLOCKED: command matches dangerous git pattern /${pattern.source}/. ` +
              `The user has prevented you from doing this. Ask the user to run it manually.`,
          )
        }
      }
    },
  }
}

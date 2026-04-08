# New Game Handoff Prompt

Copy the block below and paste it as your first message to Claude Code in the new project directory.

---

```
This project was cloned from the game-dev-workflow template. Before we start building the game, set up the project:

1. Read CLAUDE.md to understand the full workflow, agent roles, MCP tools, and conventions.
2. Read every agent definition in .claude/agents/ to understand the team.
3. Read .mcp.json and the MCP server source files in tools/ to understand what tools are available.
4. Read game/autoloads/debug_server.gd to understand the telemetry and game bridge system.

Then I need you to:

1. Update game/project.godot — change config/name and config/description to match this game.
2. Update the game_log_list appdata search path in tools/game-bridge-mcp/server.py to match the new project name.
3. Ask me what game we're building — genre, core mechanic, art style, scope.
4. Based on my answer, have the Game Designer agent write the first design doc in game/design/.
5. Have the Project Manager break it into an initial set of tasks.
6. Start building.

Don't skip step 1-4 — read everything first so you have full context on the tooling.
```

#!/bin/bash
# Clones and builds claude_agent_teams_ui alongside this project
# The GUI is optional — the agent team works without it

GUI_DIR="../claude_agent_teams_ui"

if [ -d "$GUI_DIR" ]; then
    echo "GUI already cloned at $GUI_DIR"
    echo "Run: cd $GUI_DIR && pnpm dev"
    exit 0
fi

echo "Cloning claude_agent_teams_ui..."
git clone https://github.com/777genius/claude_agent_teams_ui.git "$GUI_DIR"
cd "$GUI_DIR"

echo "Installing dependencies..."
pnpm install

echo ""
echo "Done! To start the GUI:"
echo "  cd $GUI_DIR && pnpm dev"

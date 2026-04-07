# Game Dev Workflow — Autonomous Agent Team

## Project Overview

This is an autonomous game development project built by a team of AI agents using the **Redot engine** (Godot 4.x compatible fork). Agents collaborate via Claude Code Agent Teams, coordinated through a shared task board and peer-to-peer messaging.

## Agent Roles

| Agent | File | Responsibility |
|-------|------|----------------|
| **Project Manager** | `.claude/agents/project-manager.md` | Task breakdown, prioritization, routing, progress tracking |
| **Game Developer** | `.claude/agents/game-developer.md` | GDScript, scenes, game mechanics implementation |
| **Game Designer** | `.claude/agents/game-designer.md` | Design docs, mechanics design, balance, review |
| **QA Tester** | `.claude/agents/qa-tester.md` | Automated tests, bug reports, verification |
| **Artist** | `.claude/agents/artist.md` | Shaders, UI, placeholder art, visual effects |

## Project Structure

```
game/
├── project.godot          # Redot/Godot project config
├── scenes/                # .tscn scene files
├── scripts/               # .gd script files
├── assets/
│   ├── sprites/           # 2D art assets
│   ├── audio/             # Sound effects and music
│   ├── fonts/             # Font files
│   ├── shaders/           # .gdshader files
│   └── themes/            # UI theme .tres files
├── design/                # Game design documents (markdown)
└── tests/                 # GUT/GdUnit4 test scripts
```

## Conventions

### File Naming
- Scenes: `snake_case.tscn` (e.g., `player_character.tscn`)
- Scripts: `snake_case.gd` (e.g., `player_controller.gd`)
- Test files: `test_<what_youre_testing>.gd` (e.g., `test_player.gd`)
- Design docs: `kebab-case.md` (e.g., `player-movement.md`)

### GDScript Style
- Follow Godot's official style guide: snake_case for functions/vars, PascalCase for classes
- Use static typing everywhere: `var speed: float = 200.0`
- Use typed signals: `signal health_changed(new_value: int)`
- Export tunable parameters: `@export var speed: float = 200.0`
- Prefer composition over inheritance

### Scene Organization
- One script per scene root node (attach to the root, not children)
- Use `%UniqueNode` syntax for internal references
- Group reusable components as their own scenes

### Git
- Commit after each meaningful unit of work
- Commit messages: `type: description` (feat, fix, test, design, art, refactor)
- Don't commit `.godot/` cache directory

## Workflow

1. **Design** — Game Designer writes a design doc
2. **Plan** — Project Manager breaks it into tasks
3. **Build** — Developer implements, Artist creates assets
4. **Test** — QA Tester writes tests and verifies
5. **Review** — Team reviews, iterates, merges
6. **Repeat**

## GDScript Reference

All agents writing GDScript MUST read `.claude/agents/gdscript-reference.md` before generating code. GDScript resembles Python but has critical differences that LLMs routinely get wrong (boolean capitalization, string formatting, imports, signal syntax, etc.). The reference file documents every common pitfall.

## Engine Notes

- Redot LTS 26.1 is fully compatible with Godot 4.x — all Godot docs and resources apply
- Scenes (.tscn) and resources (.tres) are text-based and git-friendly
- Run headlessly: `redot --headless --script res://your_script.gd --quit`
- Test headlessly: `redot --headless --script addons/gut/gut_cmdln.gd -gdir=res://tests/ -gexit`

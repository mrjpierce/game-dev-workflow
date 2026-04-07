---
name: GDScript Reference
description: GDScript quirks, common LLM mistakes, and correct patterns for Redot/Godot 4.x — shared context for all agents.
---

# GDScript Quick Reference & LLM Pitfalls

This document exists because LLMs frequently hallucinate incorrect GDScript due to its similarity to Python. **Always check your GDScript against these patterns.**

## Critical: GDScript is NOT Python

### Dictionaries
```gdscript
# WRONG — Python syntax
var d = dict()
var d = {"key": value for x in list}

# CORRECT — Godot syntax
var d: Dictionary = {}
var d: Dictionary = {"key": "value"}
```

### Arrays
```gdscript
# WRONG — Python syntax
var a = list()
var a = [x for x in range(10)]
var a.append(item)  # append exists but...

# CORRECT — Godot syntax
var a: Array = []
var a: Array[int] = []  # typed array
a.append(item)
a.push_back(item)  # preferred
```

### String Formatting
```gdscript
# WRONG — Python f-strings
var s = f"Health: {health}"

# CORRECT — GDScript format
var s: String = "Health: %d" % health
var s: String = "Pos: %s, %s" % [x, y]
var s: String = "Name: " + player_name
```

### Null / None
```gdscript
# WRONG — Python
if x is None:
if x == None:

# CORRECT — GDScript
if x == null:
if x is Node:  # type check
```

### Boolean
```gdscript
# WRONG — Python capitalization
True, False, None

# CORRECT — GDScript
true, false, null
```

### Loops
```gdscript
# WRONG — Python enumerate
for i, item in enumerate(list):

# CORRECT — GDScript
for i in range(list.size()):
    var item = list[i]

# Or just iterate directly
for item in list:
    pass
```

### Type Casting
```gdscript
# WRONG — Python casting
int(x), str(x), float(x)

# CORRECT — GDScript
int(x)      # this one actually works
str(x)      # this one too
float(x)    # and this
x as Node2D # safe cast (returns null if fails)
```

### Imports / Modules
```gdscript
# WRONG — Python imports
import os
from player import Player

# CORRECT — GDScript has NO imports
# Classes are globally available via class_name
# Or load explicitly:
var PlayerScene: PackedScene = preload("res://scenes/player.tscn")
var script = load("res://scripts/utils.gd")
```

## Node & Scene Patterns

### Getting References
```gdscript
# WRONG — long get_node paths
var player = get_node("../../World/Entities/Player")

# CORRECT — use @onready + scene-unique names
@onready var player: Player = %Player              # unique name (set in editor)
@onready var sprite: Sprite2D = $Sprite2D           # direct child
@onready var label: Label = $UI/HUD/HealthLabel     # short paths only
```

### @onready Rules
```gdscript
# WRONG — @onready with non-node values
@onready var speed: float = 200.0

# CORRECT — @onready is ONLY for node references
@onready var sprite: Sprite2D = $Sprite2D

# Regular vars for non-node values
var speed: float = 200.0
@export var max_health: int = 100
```

### Creating Nodes in Code
```gdscript
# CORRECT pattern
var sprite := Sprite2D.new()
sprite.texture = preload("res://assets/sprites/icon.png")
sprite.position = Vector2(100, 200)
add_child(sprite)

# CORRECT — instantiating scenes
var enemy_scene: PackedScene = preload("res://scenes/enemy.tscn")
var enemy: Enemy = enemy_scene.instantiate() as Enemy
enemy.position = Vector2(400, 300)
get_tree().current_scene.add_child(enemy)
```

### Freeing Nodes
```gdscript
# WRONG — Python del
del node

# CORRECT — queue_free for safe removal
node.queue_free()

# Check before accessing potentially freed nodes
if is_instance_valid(node):
    node.do_something()
```

## Signals

### Declaring
```gdscript
# CORRECT — typed signals
signal health_changed(new_health: int)
signal died
signal item_collected(item_name: String, quantity: int)
```

### Connecting
```gdscript
# CORRECT — callable syntax (Godot 4.x)
button.pressed.connect(_on_button_pressed)
health_changed.connect(_on_health_changed)

# With arguments
enemy.died.connect(_on_enemy_died.bind(enemy))

# One-shot connection
timer.timeout.connect(_on_timeout, CONNECT_ONE_SHOT)
```

### Emitting
```gdscript
# CORRECT
health_changed.emit(current_health)
died.emit()
item_collected.emit("sword", 1)
```

### WRONG Signal Patterns
```gdscript
# WRONG — Godot 3.x syntax (DO NOT USE)
connect("pressed", self, "_on_button_pressed")
emit_signal("health_changed", health)
yield(get_tree().create_timer(1.0), "timeout")

# CORRECT — Godot 4.x equivalents
pressed.connect(_on_button_pressed)
health_changed.emit(health)
await get_tree().create_timer(1.0).timeout
```

## Export & Properties

```gdscript
# Basic exports
@export var speed: float = 200.0
@export var health: int = 100
@export var player_name: String = "Hero"
@export var color: Color = Color.WHITE

# Range hints
@export_range(0, 100, 1) var percentage: int = 50
@export_range(0.0, 1.0, 0.01) var volume: float = 0.8

# Enums
enum State { IDLE, RUNNING, JUMPING }
@export var current_state: State = State.IDLE

# Resources
@export var texture: Texture2D
@export var scene: PackedScene

# Groups in inspector
@export_group("Movement")
@export var walk_speed: float = 100.0
@export var run_speed: float = 250.0

@export_group("Combat")
@export var damage: int = 10
@export var attack_range: float = 50.0
```

## Lifecycle Methods

```gdscript
# Called when node enters the scene tree
func _ready() -> void:
    pass

# Called every frame (use for visuals, non-physics logic)
func _process(delta: float) -> void:
    pass

# Called every physics tick (use for movement, physics)
func _physics_process(delta: float) -> void:
    pass

# Input — use _unhandled_input so UI can consume events first
func _unhandled_input(event: InputEvent) -> void:
    if event.is_action_pressed("jump"):
        _jump()

# DON'T use _input() for gameplay — it runs before UI
# DON'T use _process() for physics-dependent movement
```

## Common Mistakes by LLMs

### 1. Using Python's `self`
```gdscript
# WRONG
self.speed = 200  # works but is unnecessary and un-idiomatic

# CORRECT — just use the variable directly
speed = 200
```

### 2. Constructor Confusion
```gdscript
# WRONG — Python __init__
func __init__():
    pass

# CORRECT — _init or _ready
func _init() -> void:
    # Called when object is created (before entering tree)
    pass

func _ready() -> void:
    # Called when node enters the scene tree (after _init)
    pass
```

### 3. Main Function
```gdscript
# WRONG — there is no main()
func main():
    pass

# CORRECT — use _ready() as entry point
func _ready() -> void:
    start_game()
```

### 4. Print
```gdscript
# WRONG — Python print with format
print(f"Health: {health}")

# CORRECT
print("Health: ", health)
print("Health: %d" % health)
```

### 5. Type Annotations
```gdscript
# WRONG — Python type hints
def func(x: int) -> int:
health: int  # no var keyword

# CORRECT — GDScript type annotations
func my_func(x: int) -> int:
    return x * 2

var health: int = 100
```

### 6. Math
```gdscript
# WRONG — Python math module
import math
math.sqrt(x)
math.pi

# CORRECT — Godot globals
sqrt(x)
PI
sin(x), cos(x), lerp(a, b, t)
clamp(value, min_val, max_val)
```

### 7. Random
```gdscript
# WRONG — Python random
import random
random.randint(0, 10)

# CORRECT — Godot globals
randi_range(0, 10)
randf_range(0.0, 1.0)
randf()  # 0.0 to 1.0
```

### 8. Async / Coroutines
```gdscript
# WRONG — Python async/await
async def do_thing():
    await asyncio.sleep(1)

# CORRECT — GDScript await
func do_thing() -> void:
    await get_tree().create_timer(1.0).timeout
    print("1 second later")
```

## Validation Checklist

Before submitting any GDScript, verify:
- [ ] No Python-isms (`True`/`False`/`None`, f-strings, imports, `self.`)
- [ ] All variables have type annotations (`var x: int = 0`)
- [ ] All functions have return type annotations (`func foo() -> void:`)
- [ ] Signals use Godot 4.x syntax (`.connect()`, `.emit()`)
- [ ] Node references use `@onready` with `$` or `%`
- [ ] Input handling uses `_unhandled_input()` not `_input()`
- [ ] Physics logic is in `_physics_process()` not `_process()`
- [ ] No `yield()` — use `await` instead (Godot 4.x)

extends Node
## Debug server autoload for AI agent interaction.
## Listens on a TCP port for JSON commands. Records all actions as
## replayable macros and streams telemetry data.
##
## Add as an autoload named "DebugServer" in project.godot.
## Strip from release builds via feature tags.

const PORT: int = 9877
const TELEMETRY_INTERVAL: float = 0.5  # seconds between telemetry samples
const TELEMETRY_DIR: String = "user://telemetry"

var _server: TCPServer = TCPServer.new()
var _clients: Array[StreamPeerTCP] = []
var _client_buffers: Dictionary = {}  # StreamPeerTCP -> String (partial data)

# Recording
var _recording: bool = false
var _recording_start_time: float = 0.0
var _recorded_actions: Array[Dictionary] = []

# Telemetry
var _telemetry_enabled: bool = true
var _telemetry_log: Array[Dictionary] = []
var _telemetry_timer: float = 0.0

# File logging — writes every telemetry sample and action to a .jsonl file
var _log_file: FileAccess = null
var _run_id: String = ""

# Replay
var _replaying: bool = false
var _replay_actions: Array = []
var _replay_index: int = 0
var _replay_start_time: float = 0.0


func _ready() -> void:
	var err: int = _server.listen(PORT, "127.0.0.1")
	if err != OK:
		push_warning("DebugServer: Failed to listen on port %d (error %d)" % [PORT, err])
		return
	print("DebugServer: Listening on 127.0.0.1:%d" % PORT)
	_start_recording()
	_start_file_logging()


func _start_file_logging() -> void:
	# Create telemetry directory if needed
	DirAccess.make_dir_recursive_absolute(TELEMETRY_DIR)
	# Timestamped run file: telemetry/run_20260406_143022.jsonl
	_run_id = Time.get_datetime_string_from_system().replace("-", "").replace(":", "").replace("T", "_")
	var path: String = TELEMETRY_DIR + "/run_" + _run_id + ".jsonl"
	_log_file = FileAccess.open(path, FileAccess.WRITE)
	if _log_file:
		var meta: Dictionary = {
			"event": "run_start",
			"t": 0.0,
			"run_id": _run_id,
			"project": ProjectSettings.get_setting("application/config/name", ""),
			"scene": get_tree().current_scene.scene_file_path if get_tree().current_scene else "",
		}
		_log_file.store_line(JSON.stringify(meta))
		_log_file.flush()
		# Print the resolved OS path so agents can find it
		var os_path: String = ProjectSettings.globalize_path(path)
		print("DebugServer: Telemetry log -> %s" % os_path)
	else:
		push_warning("DebugServer: Could not create telemetry log at %s" % path)


func _log_event(event: Dictionary) -> void:
	if _log_file:
		_log_file.store_line(JSON.stringify(event))
		_log_file.flush()


func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST or what == NOTIFICATION_PREDELETE:
		_close_file_log()


func _close_file_log() -> void:
	if _log_file:
		var end: Dictionary = {
			"event": "run_end",
			"t": Time.get_ticks_msec() / 1000.0,
			"run_id": _run_id,
		}
		_log_file.store_line(JSON.stringify(end))
		_log_file.flush()
		_log_file = null


func _process(delta: float) -> void:
	_accept_new_clients()
	_read_clients()
	_update_telemetry(delta)
	_update_replay(delta)


# --- Networking ---

func _accept_new_clients() -> void:
	while _server.is_connection_available():
		var client: StreamPeerTCP = _server.take_connection()
		_clients.append(client)
		_client_buffers[client] = ""
		print("DebugServer: Client connected")


func _read_clients() -> void:
	var disconnected: Array[StreamPeerTCP] = []
	for client in _clients:
		client.poll()
		var status: int = client.get_status()
		if status == StreamPeerTCP.STATUS_CONNECTED:
			var available: int = client.get_available_bytes()
			if available > 0:
				var data: PackedByteArray = client.get_data(available)[1]
				_client_buffers[client] += data.get_string_from_utf8()
				_process_buffer(client)
		elif status == StreamPeerTCP.STATUS_NONE or status == StreamPeerTCP.STATUS_ERROR:
			disconnected.append(client)

	for client in disconnected:
		_clients.erase(client)
		_client_buffers.erase(client)
		print("DebugServer: Client disconnected")


func _process_buffer(client: StreamPeerTCP) -> void:
	# Messages are newline-delimited JSON
	var buffer: String = _client_buffers[client]
	while "\n" in buffer:
		var idx: int = buffer.find("\n")
		var line: String = buffer.substr(0, idx).strip_edges()
		buffer = buffer.substr(idx + 1)
		if line.length() > 0:
			var response: Dictionary = _handle_command(line)
			var response_json: String = JSON.stringify(response) + "\n"
			client.put_data(response_json.to_utf8_buffer())
	_client_buffers[client] = buffer


# --- Command Dispatch ---

func _handle_command(json_str: String) -> Dictionary:
	var json: JSON = JSON.new()
	var err: int = json.parse(json_str)
	if err != OK:
		return {"ok": false, "error": "Invalid JSON: %s" % json.get_error_message()}

	var cmd: Dictionary = json.data
	if not cmd.has("type"):
		return {"ok": false, "error": "Missing 'type' field"}

	match cmd["type"]:
		"ping":
			return {"ok": true, "pong": true, "time": Time.get_ticks_msec()}
		"action":
			return _cmd_action(cmd)
		"query":
			return _cmd_query(cmd)
		"query_tree":
			return _cmd_query_tree(cmd)
		"set":
			return _cmd_set(cmd)
		"eval":
			return _cmd_eval(cmd)
		"screenshot":
			return _cmd_screenshot(cmd)
		"telemetry_snapshot":
			return _cmd_telemetry_snapshot()
		"telemetry_history":
			return _cmd_telemetry_history(cmd)
		"telemetry_clear":
			_telemetry_log.clear()
			return {"ok": true}
		"telemetry_config":
			return _cmd_telemetry_config(cmd)
		"record_start":
			_start_recording()
			return {"ok": true, "recording": true}
		"record_stop":
			return _cmd_record_stop()
		"replay":
			return _cmd_replay(cmd)
		"replay_status":
			return {"ok": true, "replaying": _replaying, "index": _replay_index, "total": _replay_actions.size()}
		"log_path":
			if _log_file:
				var path: String = TELEMETRY_DIR + "/run_" + _run_id + ".jsonl"
				return {"ok": true, "path": ProjectSettings.globalize_path(path), "run_id": _run_id}
			return {"ok": false, "error": "No log file active"}
		_:
			return {"ok": false, "error": "Unknown command type: %s" % cmd["type"]}


# --- Actions ---

func _cmd_action(cmd: Dictionary) -> Dictionary:
	var action_name: String = cmd.get("action", "")
	if action_name.is_empty():
		return {"ok": false, "error": "Missing 'action' field"}

	var pressed: bool = cmd.get("pressed", true)
	var strength: float = cmd.get("strength", 1.0)
	var duration: float = cmd.get("duration", 0.0)

	if not InputMap.has_action(action_name):
		# List available actions for the agent
		var available: Array[String] = []
		for a in InputMap.get_actions():
			if not str(a).begins_with("ui_"):
				available.append(str(a))
		return {"ok": false, "error": "Unknown action: %s" % action_name, "available_actions": available}

	# Create and dispatch the input event
	var event: InputEventAction = InputEventAction.new()
	event.action = action_name
	event.pressed = pressed
	event.strength = strength
	Input.parse_input_event(event)

	# If duration > 0, schedule a release
	if pressed and duration > 0.0:
		_release_after(action_name, duration)

	# Record the action
	var elapsed: float = (Time.get_ticks_msec() - _recording_start_time) / 1000.0
	var action_record: Dictionary = {
		"t": elapsed,
		"action": action_name,
		"pressed": pressed,
		"strength": strength,
		"duration": duration,
	}
	if _recording:
		_recorded_actions.append(action_record)

	# Log to file — include full game state with every action
	var log_entry: Dictionary = action_record.duplicate()
	log_entry["event"] = "action"
	log_entry["state"] = _capture_telemetry()
	_log_event(log_entry)

	return {"ok": true, "action": action_name, "pressed": pressed}


func _release_after(action_name: String, delay: float) -> void:
	await get_tree().create_timer(delay).timeout
	var event: InputEventAction = InputEventAction.new()
	event.action = action_name
	event.pressed = false
	Input.parse_input_event(event)


# --- State Queries ---

func _cmd_query(cmd: Dictionary) -> Dictionary:
	var path: String = cmd.get("path", "")
	var property: String = cmd.get("property", "")

	if path.is_empty():
		return {"ok": false, "error": "Missing 'path' field"}

	var node: Node = get_tree().root.get_node_or_null(path)
	if node == null:
		return {"ok": false, "error": "Node not found: %s" % path}

	if property.is_empty():
		# Return basic node info
		return {
			"ok": true,
			"name": node.name,
			"class": node.get_class(),
			"path": str(node.get_path()),
			"children": _get_child_names(node),
			"properties": _get_exported_properties(node),
		}

	if not property in node:
		return {"ok": false, "error": "Property '%s' not found on %s" % [property, path]}

	var value = node.get(property)
	return {"ok": true, "path": path, "property": property, "value": _serialize(value)}


func _cmd_query_tree(cmd: Dictionary) -> Dictionary:
	var path: String = cmd.get("path", "/root")
	var depth: int = cmd.get("depth", 3)

	var node: Node = get_tree().root.get_node_or_null(path)
	if node == null:
		return {"ok": false, "error": "Node not found: %s" % path}

	return {"ok": true, "tree": _serialize_tree(node, depth)}


func _serialize_tree(node: Node, depth: int) -> Dictionary:
	var result: Dictionary = {
		"name": node.name,
		"class": node.get_class(),
	}
	if node is Node2D:
		result["position"] = _serialize(node.position)
	elif node is Node3D:
		result["position"] = _serialize(node.position)
	if depth > 0 and node.get_child_count() > 0:
		var children: Array[Dictionary] = []
		for child in node.get_children():
			children.append(_serialize_tree(child, depth - 1))
		result["children"] = children
	return result


func _cmd_set(cmd: Dictionary) -> Dictionary:
	var path: String = cmd.get("path", "")
	var property: String = cmd.get("property", "")
	var value = cmd.get("value")

	if path.is_empty() or property.is_empty():
		return {"ok": false, "error": "Missing 'path' or 'property'"}

	var node: Node = get_tree().root.get_node_or_null(path)
	if node == null:
		return {"ok": false, "error": "Node not found: %s" % path}

	# Deserialize Vector2/Vector3 from dict
	var current = node.get(property)
	value = _deserialize(value, current)

	var old_value = _serialize(current)
	node.set(property, value)
	var new_value = _serialize(node.get(property))

	# Log state mutation
	_log_event({
		"event": "set",
		"t": Time.get_ticks_msec() / 1000.0,
		"path": path,
		"property": property,
		"old": old_value,
		"new": new_value,
		"state": _capture_telemetry(),
	})

	return {"ok": true, "path": path, "property": property, "value": new_value}


func _cmd_eval(cmd: Dictionary) -> Dictionary:
	var expr_str: String = cmd.get("expression", "")
	if expr_str.is_empty():
		return {"ok": false, "error": "Missing 'expression' field"}

	var expr: Expression = Expression.new()
	var err: int = expr.parse(expr_str)
	if err != OK:
		return {"ok": false, "error": "Parse error: %s" % expr.get_error_text()}

	var result = expr.execute([], get_tree().current_scene)
	if expr.has_execute_failed():
		return {"ok": false, "error": "Execution error: %s" % expr.get_error_text()}

	return {"ok": true, "result": _serialize(result)}


# --- Screenshots ---

func _cmd_screenshot(_cmd: Dictionary) -> Dictionary:
	# Must wait for the frame to finish rendering
	await RenderingServer.frame_post_draw

	var viewport: Viewport = get_viewport()
	var img: Image = viewport.get_texture().get_image()
	var png_data: PackedByteArray = img.save_png_to_buffer()
	var base64: String = Marshalls.raw_to_base64(png_data)

	return {
		"ok": true,
		"format": "png",
		"width": img.get_width(),
		"height": img.get_height(),
		"data_base64": base64,
	}


# --- Telemetry ---

func _cmd_telemetry_snapshot() -> Dictionary:
	return {"ok": true, "snapshot": _capture_telemetry()}


func _cmd_telemetry_history(cmd: Dictionary) -> Dictionary:
	var since: float = cmd.get("since", 0.0)
	var limit: int = cmd.get("limit", 100)
	var filtered: Array[Dictionary] = []
	for entry in _telemetry_log:
		if entry.get("t", 0.0) >= since:
			filtered.append(entry)
	if filtered.size() > limit:
		filtered = filtered.slice(filtered.size() - limit)
	return {"ok": true, "entries": filtered, "total": _telemetry_log.size()}


func _cmd_telemetry_config(cmd: Dictionary) -> Dictionary:
	if cmd.has("enabled"):
		_telemetry_enabled = cmd["enabled"]
	if cmd.has("interval"):
		TELEMETRY_INTERVAL = cmd["interval"]
	return {"ok": true, "enabled": _telemetry_enabled, "interval": TELEMETRY_INTERVAL}


func _update_telemetry(delta: float) -> void:
	if not _telemetry_enabled:
		return
	_telemetry_timer += delta
	if _telemetry_timer >= TELEMETRY_INTERVAL:
		_telemetry_timer = 0.0
		var snapshot: Dictionary = _capture_telemetry()
		_telemetry_log.append(snapshot)
		# Log to file
		var log_entry: Dictionary = snapshot.duplicate()
		log_entry["event"] = "telemetry"
		_log_event(log_entry)
		# Cap the in-memory log to prevent unbounded growth
		if _telemetry_log.size() > 10000:
			_telemetry_log = _telemetry_log.slice(5000)


func _capture_telemetry() -> Dictionary:
	var snapshot: Dictionary = {
		"t": Time.get_ticks_msec() / 1000.0,
		"fps": Engine.get_frames_per_second(),
		"frame": Engine.get_frames_drawn(),
		"scene": get_tree().current_scene.scene_file_path if get_tree().current_scene else "",
		"node_count": get_tree().get_node_count(),
	}

	# Try to find common game state
	var scene: Node = get_tree().current_scene
	if scene:
		# Look for a player node
		var players: Array[Node] = get_tree().get_nodes_in_group("player")
		if players.size() > 0:
			var player: Node = players[0]
			if player is Node2D:
				snapshot["player_position"] = _serialize(player.position)
			elif player is Node3D:
				snapshot["player_position"] = _serialize(player.position)
			if "health" in player:
				snapshot["player_health"] = player.health
			if "velocity" in player:
				snapshot["player_velocity"] = _serialize(player.velocity)

		# Enemy count
		var enemies: Array[Node] = get_tree().get_nodes_in_group("enemies")
		snapshot["enemy_count"] = enemies.size()

	return snapshot


# --- Recording ---

func _start_recording() -> void:
	_recording = true
	_recording_start_time = Time.get_ticks_msec()
	_recorded_actions.clear()
	print("DebugServer: Recording started")


func _cmd_record_stop() -> Dictionary:
	_recording = false
	var actions: Array[Dictionary] = _recorded_actions.duplicate()
	print("DebugServer: Recording stopped (%d actions)" % actions.size())
	return {"ok": true, "actions": actions, "count": actions.size()}


# --- Replay ---

func _cmd_replay(cmd: Dictionary) -> Dictionary:
	var actions: Array = cmd.get("actions", [])
	if actions.is_empty():
		return {"ok": false, "error": "Missing or empty 'actions' array"}

	_replay_actions = actions
	_replay_index = 0
	_replay_start_time = Time.get_ticks_msec()
	_replaying = true
	print("DebugServer: Replaying %d actions" % actions.size())
	return {"ok": true, "replaying": true, "action_count": actions.size()}


func _update_replay(_delta: float) -> void:
	if not _replaying:
		return

	var elapsed: float = (Time.get_ticks_msec() - _replay_start_time) / 1000.0

	while _replay_index < _replay_actions.size():
		var action: Dictionary = _replay_actions[_replay_index]
		if action.get("t", 0.0) > elapsed:
			break  # Not time yet

		# Execute the action
		var event: InputEventAction = InputEventAction.new()
		event.action = action.get("action", "")
		event.pressed = action.get("pressed", true)
		event.strength = action.get("strength", 1.0)
		Input.parse_input_event(event)

		var duration: float = action.get("duration", 0.0)
		if event.pressed and duration > 0.0:
			_release_after(event.action, duration)

		_replay_index += 1

	if _replay_index >= _replay_actions.size():
		_replaying = false
		print("DebugServer: Replay complete")


# --- Helpers ---

func _get_child_names(node: Node) -> Array[String]:
	var names: Array[String] = []
	for child in node.get_children():
		names.append(child.name)
	return names


func _get_exported_properties(node: Node) -> Dictionary:
	var props: Dictionary = {}
	for prop in node.get_property_list():
		if prop["usage"] & PROPERTY_USAGE_EDITOR:
			var name: String = prop["name"]
			props[name] = _serialize(node.get(name))
	return props


func _serialize(value) -> Variant:
	if value is Vector2:
		return {"x": value.x, "y": value.y}
	elif value is Vector3:
		return {"x": value.x, "y": value.y, "z": value.z}
	elif value is Color:
		return {"r": value.r, "g": value.g, "b": value.b, "a": value.a}
	elif value is Transform2D:
		return {"origin": _serialize(value.origin)}
	elif value is Transform3D:
		return {"origin": _serialize(value.origin)}
	elif value is NodePath:
		return str(value)
	elif value is Resource:
		return value.resource_path if value.resource_path else str(value)
	elif value is Array:
		var arr: Array = []
		for item in value:
			arr.append(_serialize(item))
		return arr
	return value


func _deserialize(value, current) -> Variant:
	if current is Vector2 and value is Dictionary:
		return Vector2(value.get("x", 0.0), value.get("y", 0.0))
	elif current is Vector3 and value is Dictionary:
		return Vector3(value.get("x", 0.0), value.get("y", 0.0), value.get("z", 0.0))
	elif current is Color and value is Dictionary:
		return Color(value.get("r", 0.0), value.get("g", 0.0), value.get("b", 0.0), value.get("a", 1.0))
	return value

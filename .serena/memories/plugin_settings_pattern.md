# Plugin Settings Pattern

## Overview

When a plugin exposes settings via `get_settings_schema()`, it MUST also implement the settings reloading pattern to ensure settings modified via `conf_manager` are applied correctly.

## The Problem

Settings can be stored in two places:
1. **config.yaml** - Default values loaded at startup
2. **Database (plugin_settings table)** - Values modified by the user via conf_manager

If a plugin only reads from `self.context.config.{plugin_name}`, it will miss any changes made via the conf_manager UI, because those are saved to the database.

## Required Implementation

Any plugin with `get_settings_schema()` returning a non-empty dictionary MUST:

### 1. Subscribe to `PLUGIN_SETTINGS_CHANGED` in `initialize()`

```python
def initialize(self, context: PluginContextProtocol) -> None:
    self.context = context
    
    # ... other subscriptions ...
    
    # Subscribe to settings changes
    context.subscribe(Events.PLUGIN_SETTINGS_CHANGED, self._on_settings_changed)
    
    # Load settings from DB on startup
    self._on_settings_changed()
```

### 2. Implement `_on_settings_changed()` method

```python
def _on_settings_changed(self) -> None:
    """Reload config when settings change."""
    logging.info(f"[{self.name}] Settings changed, reloading config from database")

    db = self.context.database
    config = self.context.config.{config_section}  # e.g., video_exporter, loop_player

    # Helper to get setting from DB
    def get_setting(key: str) -> str | None:
        result = db.conn.execute(
            "SELECT setting_value FROM plugin_settings WHERE plugin_name = ? AND setting_key = ?",
            ("{plugin_name}", key),  # e.g., "video_exporter"
        ).fetchone()
        return result["setting_value"] if result else None

    # Reload each setting type appropriately:
    
    # For string settings:
    value = get_setting("setting_key")
    if value is not None:
        config.setting_key = value
    
    # For int settings:
    value = get_setting("int_setting")
    if value is not None:
        try:
            config.int_setting = int(float(value))
        except ValueError:
            logging.error(f"[{self.name}] Invalid int_setting value: {value}")
    
    # For float settings:
    value = get_setting("float_setting")
    if value is not None:
        try:
            config.float_setting = float(value)
        except ValueError:
            logging.error(f"[{self.name}] Invalid float_setting value: {value}")
    
    # For bool settings:
    value = get_setting("bool_setting")
    if value is not None:
        config.bool_setting = value.lower() in ("true", "1", "yes")
```

## Important Notes

1. **Plugin name in DB**: The `plugin_name` used in the SQL query must match `self.name` (the plugin's name attribute)

2. **Startup loading**: Call `_on_settings_changed()` at the end of `initialize()` to load any existing DB settings at startup

3. **Type conversion**: Values in the database are stored as strings, so proper type conversion is required

4. **Unit conversion**: Some settings may need unit conversion (e.g., milliseconds in UI vs seconds in config)

5. **UI updates**: If a setting affects the UI (e.g., widget height), update the UI in `_on_settings_changed()`

## Plugins Currently Using This Pattern

- `loop_player.py` ✓
- `file_manager.py` ✓
- `genre_editor.py` ✓
- `video_exporter/plugin.py` ✓
- `playback_navigation.py` ✓
- `waveform_visualizer.py` ✓

## Plugins That Don't Need It

- `audio_analyzer.py` - Returns empty schema `{}`
- `conf_manager.py` - Is the settings manager itself

## Checklist for New Plugins

When creating a new plugin with settings:

- [ ] Define `get_settings_schema()` returning the schema dict
- [ ] Add corresponding config class in `jukebox/core/config.py`
- [ ] Add protocol in `jukebox/core/protocols.py`
- [ ] Add default values in `config/config.yaml`
- [ ] Subscribe to `Events.PLUGIN_SETTINGS_CHANGED` in `initialize()`
- [ ] Implement `_on_settings_changed()` method
- [ ] Call `_on_settings_changed()` at end of `initialize()`

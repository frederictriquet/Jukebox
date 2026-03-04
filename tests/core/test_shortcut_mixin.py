"""Tests for ShortcutMixin."""

from unittest.mock import MagicMock, call, patch

import pytest

from jukebox.core.shortcut_mixin import ShortcutMixin


class ConcretePlugin(ShortcutMixin):
    """Minimal concrete plugin that satisfies ShortcutMixin requirements."""

    name = "test_plugin"

    def __init__(self) -> None:
        self._init_shortcut_mixin()

    def _register_plugin_shortcuts(self) -> None:
        """No-op override so register_shortcuts does not raise."""
        pass


class TestInitShortcutMixin:
    """Tests for _init_shortcut_mixin."""

    def test_shortcuts_initialized_to_empty_list(self) -> None:
        """_init_shortcut_mixin sets shortcuts to an empty list."""
        plugin = ConcretePlugin()
        assert plugin.shortcuts == []

    def test_shortcut_manager_initialized_to_none(self) -> None:
        """_init_shortcut_mixin sets shortcut_manager to None."""
        plugin = ConcretePlugin()
        assert plugin.shortcut_manager is None


class TestRegisterShortcuts:
    """Tests for register_shortcuts and _register_all_shortcuts."""

    def test_register_shortcuts_stores_manager(self) -> None:
        """register_shortcuts stores the manager on the instance."""
        plugin = ConcretePlugin()
        manager = MagicMock()

        plugin.register_shortcuts(manager)

        assert plugin.shortcut_manager is manager

    def test_register_shortcuts_calls_register_all(self) -> None:
        """register_shortcuts calls _register_all_shortcuts."""
        plugin = ConcretePlugin()
        manager = MagicMock()

        with patch.object(plugin, "_register_all_shortcuts") as mock_register_all:
            plugin.register_shortcuts(manager)

        mock_register_all.assert_called_once()

    def test_register_all_shortcuts_returns_early_when_no_manager(self) -> None:
        """_register_all_shortcuts does nothing when shortcut_manager is None."""
        plugin = ConcretePlugin()
        # shortcut_manager is None after init

        with patch.object(plugin, "_register_plugin_shortcuts") as mock_register:
            plugin._register_all_shortcuts()

        mock_register.assert_not_called()

    def test_register_all_shortcuts_calls_plugin_shortcuts_when_manager_set(self) -> None:
        """_register_all_shortcuts delegates to _register_plugin_shortcuts."""
        plugin = ConcretePlugin()
        plugin.shortcut_manager = MagicMock()

        with patch.object(plugin, "_register_plugin_shortcuts") as mock_register:
            plugin._register_all_shortcuts()

        mock_register.assert_called_once()


class TestRegisterPluginShortcutsNotImplemented:
    """Tests that the base ShortcutMixin raises NotImplementedError."""

    def test_base_class_raises_not_implemented(self) -> None:
        """ShortcutMixin._register_plugin_shortcuts raises NotImplementedError."""

        class BarePlugin(ShortcutMixin):
            name = "bare_plugin"

            def __init__(self) -> None:
                self._init_shortcut_mixin()

        plugin = BarePlugin()
        plugin.shortcut_manager = MagicMock()

        with pytest.raises(NotImplementedError):
            plugin._register_plugin_shortcuts()


class TestOnSettingsChanged:
    """Tests for _on_settings_changed."""

    def test_settings_changed_calls_steps_in_order(self) -> None:
        """_on_settings_changed calls unregister, reload config, re-register in order."""
        plugin = ConcretePlugin()
        plugin.shortcut_manager = MagicMock()
        call_order: list[str] = []

        def record_unregister() -> None:
            call_order.append("unregister")

        def record_reload() -> None:
            call_order.append("reload")

        def record_register() -> None:
            call_order.append("register")

        with (
            patch.object(plugin, "_unregister_all_shortcuts", side_effect=record_unregister),
            patch.object(plugin, "_reload_plugin_config", side_effect=record_reload),
            patch.object(plugin, "_register_all_shortcuts", side_effect=record_register),
        ):
            plugin._on_settings_changed()

        assert call_order == ["unregister", "reload", "register"]

    def test_settings_changed_calls_unregister(self) -> None:
        """_on_settings_changed calls _unregister_all_shortcuts."""
        plugin = ConcretePlugin()
        plugin.shortcut_manager = MagicMock()

        with (
            patch.object(plugin, "_unregister_all_shortcuts") as mock_unreg,
            patch.object(plugin, "_reload_plugin_config"),
            patch.object(plugin, "_register_all_shortcuts"),
        ):
            plugin._on_settings_changed()

        mock_unreg.assert_called_once()

    def test_settings_changed_calls_reload_config(self) -> None:
        """_on_settings_changed calls _reload_plugin_config."""
        plugin = ConcretePlugin()
        plugin.shortcut_manager = MagicMock()

        with (
            patch.object(plugin, "_unregister_all_shortcuts"),
            patch.object(plugin, "_reload_plugin_config") as mock_reload,
            patch.object(plugin, "_register_all_shortcuts"),
        ):
            plugin._on_settings_changed()

        mock_reload.assert_called_once()

    def test_settings_changed_calls_register_all(self) -> None:
        """_on_settings_changed calls _register_all_shortcuts."""
        plugin = ConcretePlugin()
        plugin.shortcut_manager = MagicMock()

        with (
            patch.object(plugin, "_unregister_all_shortcuts"),
            patch.object(plugin, "_reload_plugin_config"),
            patch.object(plugin, "_register_all_shortcuts") as mock_reg,
        ):
            plugin._on_settings_changed()

        mock_reg.assert_called_once()


class TestUnregisterAllShortcuts:
    """Tests for _unregister_all_shortcuts."""

    def test_unregister_calls_manager_for_each_shortcut(self) -> None:
        """_unregister_all_shortcuts calls manager.unregister for each shortcut."""
        plugin = ConcretePlugin()
        manager = MagicMock()
        plugin.shortcut_manager = manager

        shortcut_a = MagicMock()
        shortcut_a.key.return_value.toString.return_value = "Ctrl+A"
        shortcut_b = MagicMock()
        shortcut_b.key.return_value.toString.return_value = "Ctrl+B"
        plugin.shortcuts = [shortcut_a, shortcut_b]

        plugin._unregister_all_shortcuts()

        manager.unregister.assert_any_call("Ctrl+A")
        manager.unregister.assert_any_call("Ctrl+B")
        assert manager.unregister.call_count == 2

    def test_unregister_clears_shortcuts_list(self) -> None:
        """_unregister_all_shortcuts clears the shortcuts list."""
        plugin = ConcretePlugin()
        plugin.shortcut_manager = MagicMock()

        shortcut = MagicMock()
        shortcut.key.return_value.toString.return_value = "Ctrl+Z"
        plugin.shortcuts = [shortcut]

        plugin._unregister_all_shortcuts()

        assert plugin.shortcuts == []

    def test_unregister_skips_shortcuts_without_key_attr(self) -> None:
        """_unregister_all_shortcuts skips shortcuts that have no key attribute."""
        plugin = ConcretePlugin()
        manager = MagicMock()
        plugin.shortcut_manager = manager

        # Shortcut without 'key' attribute
        shortcut_no_key = MagicMock(spec=[])  # Empty spec: no attributes
        plugin.shortcuts = [shortcut_no_key]

        plugin._unregister_all_shortcuts()

        manager.unregister.assert_not_called()
        assert plugin.shortcuts == []

    def test_unregister_with_empty_list_is_safe(self) -> None:
        """_unregister_all_shortcuts with an empty list does not raise."""
        plugin = ConcretePlugin()
        plugin.shortcut_manager = MagicMock()
        plugin.shortcuts = []

        plugin._unregister_all_shortcuts()  # Should not raise

        assert plugin.shortcuts == []


class TestActivateDeactivateShortcuts:
    """Tests for _activate_shortcuts and _deactivate_shortcuts."""

    def test_activate_calls_set_enabled_true_on_each(self) -> None:
        """_activate_shortcuts calls setEnabled(True) on every shortcut."""
        plugin = ConcretePlugin()
        shortcut_a = MagicMock()
        shortcut_b = MagicMock()
        plugin.shortcuts = [shortcut_a, shortcut_b]

        plugin._activate_shortcuts()

        shortcut_a.setEnabled.assert_called_once_with(True)
        shortcut_b.setEnabled.assert_called_once_with(True)

    def test_deactivate_calls_set_enabled_false_on_each(self) -> None:
        """_deactivate_shortcuts calls setEnabled(False) on every shortcut."""
        plugin = ConcretePlugin()
        shortcut_a = MagicMock()
        shortcut_b = MagicMock()
        plugin.shortcuts = [shortcut_a, shortcut_b]

        plugin._deactivate_shortcuts()

        shortcut_a.setEnabled.assert_called_once_with(False)
        shortcut_b.setEnabled.assert_called_once_with(False)

    def test_activate_with_empty_shortcuts_is_safe(self) -> None:
        """_activate_shortcuts with empty list does not raise."""
        plugin = ConcretePlugin()
        plugin.shortcuts = []

        plugin._activate_shortcuts()  # Should not raise

    def test_deactivate_with_empty_shortcuts_is_safe(self) -> None:
        """_deactivate_shortcuts with empty list does not raise."""
        plugin = ConcretePlugin()
        plugin.shortcuts = []

        plugin._deactivate_shortcuts()  # Should not raise


class TestReloadPluginConfig:
    """Tests for the default _reload_plugin_config."""

    def test_reload_plugin_config_is_no_op(self) -> None:
        """Default _reload_plugin_config does nothing and returns None."""
        plugin = ConcretePlugin()
        result = plugin._reload_plugin_config()
        assert result is None

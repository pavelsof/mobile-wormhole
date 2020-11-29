from kivy.uix.screenmanager import Screen
from wormhole.cli.public_relay import RENDEZVOUS_RELAY, TRANSIT_RELAY


SECTION_NAME = 'wormhole'

DEFAULT_VALUES = {
    'rendezvous_relay': RENDEZVOUS_RELAY,
    'transit_relay': TRANSIT_RELAY,
}

FIELD_NAMES = frozenset(DEFAULT_VALUES.keys())


class ConfigScreen(Screen):

    def on_pre_enter(self):
        """
        Set the values of the text inputs. Assume that self.config has been
        already set by the ConfigMixin.build_settings method.

        Called just before the user enters this screen.
        """
        assert self.config

        for field_name in FIELD_NAMES:
            field = getattr(self.ids, field_name)
            field.text = self.config.get(SECTION_NAME, field_name)

    def reset_field(self, field_name):
        """
        Reset the value of the given field to its default.
        """
        field = getattr(self.ids, field_name)
        field.text = DEFAULT_VALUES[field_name]

    def update_config(self):
        """
        Update the config with the values that happen to be in the input fields
        when the user calls this action.
        """
        for field_name in FIELD_NAMES:
            value = getattr(self.ids, field_name).text
            self.config.set(SECTION_NAME, field_name, value)

        self.config.write()


class ConfigMixin:
    """
    Mixin for our App subclass that determines the config options and the way
    to display these to the user.
    """
    settings_cls = ConfigScreen
    use_kivy_settings = False

    def build_config(self, config):
        """
        Mutate self.config before the config file (if this exists) is loaded in
        order to provide default config values.

        Called once, before the application is initialised.
        """
        config.setdefaults(SECTION_NAME, DEFAULT_VALUES)

    def build_settings(self, settings):
        """
        Mutate the settings widget before this is shown to the user in order to
        link in the config.

        Called once, when the settings widget is created.
        """
        settings.config = self.config

    def display_settings(self, settings):
        """
        Determine the way to show the settings widget to the user. In our case,
        attach the config screen (if it is not already) and switch to it.

        Called by the app.open_settings method.
        """
        if not self.screen_manager.has_screen('config_screen'):
            self.screen_manager.add_widget(settings)

        self.screen_manager.current = 'config_screen'

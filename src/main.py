import os.path

from kivy.app import App
from kivy.factory import Factory
from kivy.properties import BooleanProperty, StringProperty
from kivy.support import install_twisted_reactor
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import NoTransition, Screen, ScreenManager
from plyer import filechooser

install_twisted_reactor()

from magic import Wormhole


class ErrorPopup(Popup):
    error = StringProperty('Something bad happened!')


class HomeScreen(Screen):
    pass


class SendScreen(Screen):
    code = StringProperty('')
    chosen_path = StringProperty('')
    send_button_text = StringProperty('send')
    send_button_disabled = BooleanProperty(False)

    def show_error(self, error):
        """
        Show a hopefully user-friendly error message.
        """
        Factory.ErrorPopup(error=str(error)).open()

    def on_enter(self):
        """
        Called when the user enters this screen.
        """
        self.code = ''
        self.chosen_path = ''
        self.send_button_disabled = True
        self.send_button_text = 'waiting for code'

        self.wormhole = Wormhole()

        def update_code(code):
            self.code = code
            self.send_button_disabled = False
            self.send_button_text = 'send'

        deferred = self.wormhole.generate_code()
        deferred.addCallbacks(update_code, self.show_error)

    def open_file_chooser(self):
        """
        Called when the user releases the choose file button.
        """
        def update_chosen_path(selection):
            if selection:
                try:
                    path = os.path.normpath(selection[0])
                    assert os.path.exists(path) and os.path.isfile(path)
                except (AssertionError, IndexError):
                    self.show_error(
                        'there is something wrong about the file you chose'
                    )
                    self.chosen_path = ''
                else:
                    self.chosen_path = path
            else:
                self.chosen_path = ''

        try:
            from android.permissions import (
                Permission, check_permission, request_permissions
            )
            if not check_permission(Permission.WRITE_EXTERNAL_STORAGE):
                request_permissions([Permission.WRITE_EXTERNAL_STORAGE])
        except ImportError:
            pass

        filechooser.open_file(
            title='choose a file to send',
            on_selection=update_chosen_path
        )

    def send(self):
        """
        Called when the user releases the send button.
        """
        if not self.chosen_path:
            self.show_error('please choose a file')
            return
        else:
            file_path = self.chosen_path

        def exchange_keys():
            self.send_button_disabled = True
            self.send_button_text = 'exchanging keys'
            deferred = self.wormhole.exchange_keys()
            deferred.addCallbacks(send_file, self.show_error)

        def send_file(*args):
            self.send_button_disabled = True
            self.send_button_text = 'sending file'
            deferred = self.wormhole.send_file(file_path)
            deferred.addCallbacks(show_done, self.show_error)

        def show_done(*args):
            self.send_button_disabled = True
            self.send_button_text = 'done'

        exchange_keys()

    def on_leave(self):
        """
        Called when the user leaves this screen.
        """
        self.wormhole.close()
        self.code = ''
        self.chosen_path = ''


class ReceiveScreen(Screen):
    pass


class WormholeApp(App):

    def build(self):
        """
        Init and return the main widget, in our case the screen manager.
        """
        self.screen_manager = ScreenManager(transition=NoTransition())

        for screen_cls in [HomeScreen, SendScreen, ReceiveScreen]:
            self.screen_manager.add_widget(screen_cls())

        return self.screen_manager


if __name__ == '__main__':
    WormholeApp().run()

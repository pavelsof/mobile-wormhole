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
    path = StringProperty('')
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
        self.path = ''
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
        def update_path(selection):
            if selection:
                try:
                    path = os.path.normpath(selection[0])
                    assert os.path.exists(path) and os.path.isfile(path)
                except:
                    self.show_error(
                        'there is something wrong about the file you chose'
                    )
                    self.path = ''
                else:
                    self.path = path
            else:
                self.path = ''

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
            on_selection=update_path
        )

    def send(self):
        """
        Called when the user releases the send button.
        """
        if not self.path:
            self.show_error('please choose a file')
            return
        else:
            file_path = self.path

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
        self.code = ''
        self.path = ''
        self.wormhole.close()


class ReceiveScreen(Screen):
    path = StringProperty('')
    connect_button_text = StringProperty('connect')
    connect_button_disabled = BooleanProperty(False)

    def show_error(self, error):
        """
        Show a hopefully user-friendly error message.
        """
        Factory.ErrorPopup(error=str(error)).open()

    def open_wormhole(self):
        """
        Called when the user releases the connect button.
        """
        code = self.ids.code_input.text.strip()
        if not code:
            return self.show_error('please enter a code')

        def connect():
            self.connect_button_disabled = True
            self.connect_button_text = 'connecting'

            if hasattr(self, 'wormhole'):
                self.wormhole.close()

            self.wormhole = Wormhole()

            deferred = self.wormhole.connect(code)
            deferred.addCallbacks(exchange_keys, self.show_error)

        def exchange_keys(*args):
            self.connect_button_disabled = True
            self.connect_button_text = 'exchanging keys'
            deferred = self.wormhole.exchange_keys()
            deferred.addCallbacks(show_connected, self.show_error)

        def show_connected(*args):
            self.connect_button_disabled = True
            self.connect_button_text = 'connected'

        connect()

    def open_location_chooser(self):
        """
        Called when the user releases the choose download location button.

        The filechooser already asks for confirmation if the user chooses to
        overwrite an already existing path.
        """
        def update_path(selection):
            if selection:
                try:
                    path = os.path.normpath(selection[0])
                except:
                    self.show_error(
                        'there is something wrong with the location you chose'
                    )
                    self.path = ''
                else:
                    self.path = path
            else:
                self.path = ''

        filechooser.save_file(
            title='choose where to download the file',
            on_selection=update_path
        )

    def on_leave(self):
        """
        Called when the user leaves this screen.
        """
        self.code = ''
        self.path = ''
        self.connect_button_text = 'connect'
        self.connect_button_disabled = False
        self.wormhole.close()


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

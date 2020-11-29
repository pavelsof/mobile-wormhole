import os

import humanize
from kivy.app import App
from kivy.core.clipboard import Clipboard
from kivy.core.window import Window
from kivy.factory import Factory
from kivy.properties import BooleanProperty, ObjectProperty, StringProperty
from kivy.support import install_twisted_reactor
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import NoTransition, Screen, ScreenManager
from plyer import filechooser
from twisted.python.failure import Failure

install_twisted_reactor()

from config import ConfigMixin, get_config
from magic import Wormhole
from cross import (
    ensure_storage_perms, get_downloads_dir, intent_hander, open_file
)


class ErrorPopup(Popup):
    title = StringProperty('Error')
    message = StringProperty('Something bad happened!')

    @staticmethod
    def show(error):
        """
        Open a popup with a (hopefully) user-friendly error message.

        The given argument can be either an Exception, or a Twisted Failure, or
        the error message itself as a string.
        """
        if isinstance(error, Failure):
            error = error.value

        message = str(error)

        if hasattr(error, 'verbose_name'):
            title = error.verbose_name
        else:
            title = 'Error'

        Factory.ErrorPopup(title=title, message=message).open()


class HomeScreen(Screen):
    pass


class SendScreen(Screen):
    send_button_text = StringProperty('send')
    send_button_disabled = BooleanProperty(False)

    has_code = BooleanProperty(False)
    code = StringProperty('…')

    file_name = StringProperty('…')
    file_size = StringProperty('…')
    transferred = StringProperty('…')

    def on_pre_enter(self):
        """
        Reset the labels and buttons and init a magic wormhole instance.

        This method is called just before the user enters this screen.
        """
        self.send_button_disabled = True
        self.send_button_text = 'waiting for code'

        self.has_code = False
        self.code = '…'

        self.file_path = None
        self.file_name = '…'
        self.file_size = '…'

        self.bytes_transferred = 0
        self.transferred = '…'

        try:
            self.wormhole = Wormhole(**get_config())
        except Exception as error:
            return ErrorPopup.show(error)

        def update_code(code):
            self.has_code = True
            self.code = code
            self.send_button_disabled = False
            self.send_button_text = 'send'
            Clipboard.copy(code)

        deferred = self.wormhole.generate_code()
        deferred.addCallbacks(update_code, ErrorPopup.show)

    def set_file(self, path):
        """
        Set the file to be sent down the wormhole.

        This method is called when the the user selects the file to send using
        the file chooser. It is also called directly by the App instance when
        the app has been started or resumed via a send file intent on Android.
        """
        try:
            path = os.path.normpath(path)
            assert os.path.exists(path) and os.path.isfile(path)
        except:
            ErrorPopup.show((
                'There is something wrong about the file you chose. '
                'One possible reason is an issue with some Androids '
                'where a file cannot be directly selected from the '
                '"Downloads" section and instead you have to reach it '
                'some other way, e.g. "Phone" -> "Downloads".'
            ))
            self.file_path = None
            self.file_name = '…'
            self.file_size = '…'
        else:
            self.file_path = path
            self.file_name = os.path.basename(self.file_path)
            self.file_size = humanize.naturalsize(
                os.stat(self.file_path).st_size
            )

    def open_file_chooser(self):
        """
        Open a file chooser so that the user can select a file to send down the
        wormhole. On Android, this could be preceded by asking for permissions.

        This method is called when the user releases the "choose file" button.
        """
        def handle_selection(selection):
            if selection:
                self.set_file(selection[0])

        def show_error():
            ErrorPopup.show((
                'You cannot send a file if the app cannot access it.'
            ))

        @ensure_storage_perms(show_error)
        def open_file_chooser():
            filechooser.open_file(
                title='Choose a file to send',
                on_selection=handle_selection
            )

        open_file_chooser()

    def send(self):
        """
        Send the selected file down the wormhole.

        This method is called when the user releases the send button.
        """
        if not self.file_path:
            return ErrorPopup.show('Please choose a file to send.')

        def exchange_keys():
            self.send_button_disabled = True
            self.send_button_text = 'exchanging keys'
            deferred = self.wormhole.exchange_keys(timeout=600)
            deferred.addCallbacks(send_file, ErrorPopup.show)

        def send_file(verifier):
            self.send_button_disabled = True
            self.send_button_text = 'sending file'
            deferred = self.wormhole.send_file(self.file_path, on_chunk)
            deferred.addCallbacks(show_done, ErrorPopup.show)

        def on_chunk(chunk):
            self.bytes_transferred += len(chunk)
            self.transferred = humanize.naturalsize(self.bytes_transferred)

        def show_done(hex_digest):
            self.send_button_disabled = True
            self.send_button_text = 'done'

        exchange_keys()

    def on_leave(self):
        """
        Close the magic wormhole instance, if this exists and is still open.

        This method is called when the user leaves this screen.
        """
        try:
            self.wormhole.close()
        except:
            pass  # opening the wormhole failed altogether


class ReceiveScreen(Screen):
    connect_button_disabled = BooleanProperty(False)
    connect_button_text = StringProperty('connect')

    accept_button_disabled = BooleanProperty(True)
    accept_button_func = ObjectProperty(None)
    accept_button_text = StringProperty('waiting for offer')

    file_name = StringProperty('…')
    file_size = StringProperty('…')
    transferred = StringProperty('…')

    def on_pre_enter(self):
        """
        Called just before the user enters this screen.
        """
        self.downloads_dir = get_downloads_dir()

        self.connect_button_disabled = False
        self.connect_button_text = 'connect'

        self.accept_button_disabled = True
        self.accept_button_func = self.accept_offer
        self.accept_button_text = 'waiting for offer'

        self.file_name = '…'
        self.file_size = '…'

        self.bytes_transferred = 0
        self.transferred = '…'

        self.ids.code_input.text = ''

    def open_wormhole(self):
        """
        Called when the user releases the connect button.
        """
        code = self.ids.code_input.text.strip()
        code = '-'.join(code.split())
        if not code:
            return ErrorPopup.show('Please enter a code.')

        def connect():
            self.connect_button_disabled = True
            self.connect_button_text = 'connecting'

            try:
                self.wormhole = Wormhole(**get_config())
            except Exception as error:
                return ErrorPopup.show(error)

            deferred = self.wormhole.connect(code)
            deferred.addCallbacks(exchange_keys, ErrorPopup.show)

        def exchange_keys(code):
            self.connect_button_disabled = True
            self.connect_button_text = 'exchanging keys'

            deferred = self.wormhole.exchange_keys()
            deferred.addCallbacks(await_offer, ErrorPopup.show)

        def await_offer(verifier):
            self.connect_button_disabled = True
            self.connect_button_text = 'connected'

            deferred = self.wormhole.await_offer()
            deferred.addCallbacks(show_offer, ErrorPopup.show)

        def show_offer(offer):
            self.file_name = str(offer['filename'])
            self.file_size = humanize.naturalsize(offer['filesize'])

            self.accept_button_disabled = False
            self.accept_button_text = 'accept'

        connect()

    def accept_offer(self):
        """
        Called when the user releases the accept button.
        """
        file_path = os.path.join(self.downloads_dir, self.file_name)

        def show_error():
            ErrorPopup.show((
                'You cannot receive a file if the app cannot write it.'
            ))

        @ensure_storage_perms(show_error)
        def accept_offer():
            self.accept_button_disabled = True
            self.accept_button_text = 'receiving'

            deferred = self.wormhole.accept_offer(file_path, on_chunk)
            deferred.addCallbacks(show_done, ErrorPopup.show)

        def on_chunk(chunk):
            self.bytes_transferred += len(chunk)
            self.transferred = humanize.naturalsize(self.bytes_transferred)

        def show_done(hex_digest):
            self.accept_button_disabled = False
            self.accept_button_func = self.open_file
            self.accept_button_text = 'open file'

        accept_offer()

    def open_file(self):
        """
        Called when the user presses the accept button after the file transfer
        has been completed.
        """
        file_path = os.path.join(self.downloads_dir, self.file_name)

        def show_error():
            ErrorPopup.show('Cannot open {}'.format(file_path))

        @ensure_storage_perms(show_error)
        def do():
            open_file(file_path)

        if os.path.exists(file_path):
            do()
        else:
            show_error()

    def on_leave(self):
        """
        Called when the user leaves this screen.
        """
        try:
            self.wormhole.close()
        except AttributeError:
            pass


class WormholeApp(ConfigMixin, App):

    def build(self):
        """
        Init and return the main widget, in our case the screen manager.

        Attach the on_keyboard event listener to the Window object.
        """
        self.screen_manager = ScreenManager(transition=NoTransition())

        for screen_cls in [HomeScreen, SendScreen, ReceiveScreen]:
            self.screen_manager.add_widget(screen_cls())

        Window.bind(on_keyboard=self.on_keyboard)

        return self.screen_manager

    def on_keyboard(self, window, key, *args):
        """
        Called when the keyboard is used for input.

        Handle the back button on Android (this equates to the escape key). If
        the user is not on the home screen, navigate them there; otherwise let
        them exit the app (the default behaviour).
        """
        if key == 27:
            if self.screen_manager.current != 'home_screen':
                self.screen_manager.current = 'home_screen'
                return True

        return False

    def on_start(self):
        """
        Called when the app first starts running, after self.build().

        If on Android, check whether the app activity has been started via an
        intent to send a file, and if yes, set the screen accordingly.
        """
        try:
            file_path = intent_hander.pop()
        except ValueError as error:
            ErrorPopup.show(error)
        else:
            if file_path is not None:
                self.screen_manager.current = 'send_screen'
                self.screen_manager.current_screen.set_file(file_path)

    def on_resume(self):
        """
        Called when the app comes back to the foreground.

        As it is the case with on_start, check if on Android the app has been
        started via an intent and set the screen accordingly.
        """
        self.on_start()


if __name__ == '__main__':
    WormholeApp().run()

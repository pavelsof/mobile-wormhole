import mimetypes
import os

from kivy.utils import platform as PLATFORM


if PLATFORM == 'android':
    import android.activity
    from android import mActivity
    from android.permissions import Permission
    from android.permissions import check_permission, request_permissions
    from android.storage import primary_external_storage_path
    from jnius import autoclass
    from plyer.platforms.android.filechooser import AndroidFileChooser

    File = autoclass('java.io.File')

    Intent = autoclass('android.content.Intent')
    Environment = autoclass('android.os.Environment')
    FileProvider = autoclass('android.support.v4.content.FileProvider')

    class AndroidUriResolver(AndroidFileChooser):
        """
        Leverage Plyer's file chooser for resolving Android URIs.
        """

        def __init__(self):
            pass

        def resolve(self, uri):
            return self._resolve_uri(uri)


"""
permissions
"""


def ensure_storage_perms(fallback_func):
    """
    Decorator that ensures that the decorated function is only run if the user
    has granted the app permissions to write to the file system. Otherwise the
    fallback function is called instead.

    Because permissions on Android are requested asynchronously, the decorated
    function should not be expected to return a value.
    """
    def outer_wrapper(func):
        def inner_wrapper(*args, **kwargs):
            if PLATFORM == 'android':
                if check_permission(Permission.WRITE_EXTERNAL_STORAGE):
                    return func(*args, **kwargs)

                def callback(permissions, grant_results):
                    if grant_results[0]:
                        return func(*args, **kwargs)
                    else:
                        return fallback_func()

                request_permissions(
                    [Permission.WRITE_EXTERNAL_STORAGE], callback
                )
                return

            return func(*args, **kwargs)

        return inner_wrapper
    return outer_wrapper


"""
directories
"""


def get_downloads_dir():
    """
    Return the path to the user's downloads dir.
    """
    if PLATFORM == 'android':
        return os.path.join(
            primary_external_storage_path(),
            Environment.DIRECTORY_DOWNLOADS
        )
    else:
        return os.getcwd()


def open_file(path):
    """
    Open the specified file.
    """
    mime_type, _ = mimetypes.guess_type(path)

    if PLATFORM == 'android':
        uri = FileProvider.getUriForFile(
            mActivity, 'com.pavelsof.wormhole.fileprovider', File(path)
        )

        intent = Intent()
        intent.setAction(Intent.ACTION_VIEW)
        intent.setDataAndType(uri, mime_type)
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)

        mActivity.startActivity(intent)

    else:
        pass


"""
handling intents
"""


class IntentHandler:

    def __init__(self):
        """
        On Android, set the handler listening for incoming ACTION_SEND intents,
        including the intent that has launched the current activity.

        On other platforms, do nothing.
        """
        self.data = None
        self.error = None

        if PLATFORM == 'android':
            self.uri_resolver = AndroidUriResolver()
            self.handle_android_intent(mActivity.getIntent())
            android.activity.bind(on_new_intent=self.handle_android_intent)

    def handle_android_intent(self, intent):
        """
        Handle incoming ACTION_SEND intents on Android.
        """
        if intent.getAction() != 'android.intent.action.SEND':
            return

        self.data = None
        self.error = None

        try:
            if intent.getData():
                uri = intent.getData()

            else:
                clipData = intent.getClipData()

                assert clipData is not None
                assert clipData.getItemCount()

                uri = clipData.getItemAt(0).getUri()

            self.data = self.uri_resolver.resolve(uri)
        except (AttributeError, AssertionError):
            self.error = (
                'Your share target cannot be recognised as a file. '
                'If it is indeed one, '
                'please try selecting it via the file chooser instead.'
            )

    def pop(self):
        """
        If there is a file path in our improvised single-slot buffer, pop it.
        If there is an error instead, raise it. Otherwise return None.
        """
        if self.error:
            error = str(self.error)
            self.error = None
            raise ValueError(error)
        else:
            data = self.data
            self.data = None
            return data


intent_hander = IntentHandler()

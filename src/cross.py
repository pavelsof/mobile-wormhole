import os

from kivy.utils import platform as PLATFORM


if PLATFORM == 'android':
    from android.permissions import Permission
    from android.permissions import check_permission, request_permissions
    from jnius import autoclass


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


def get_downloads_dir():
    """
    Return the path to the user's downloads dir.
    """
    if PLATFORM == 'android':
        Environment = autoclass('android.os.Environment')
        return Environment.DIRECTORY_DOWNLOADS
    else:
        return os.getcwd()

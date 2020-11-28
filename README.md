# wormhole

This is a work-in-progress mobile client for the [magic wormhole][magic-wormhole] protocol. What already works:

- Sending files. The app can obtain a code, exchange keys with the other party, allow the user to pick a file to send down the wormhole, and then actually transfer the file.
- Receiving files. The user can enter a code, view a file offer to confirm or reject, and indeed receive a file. This will be saved in the downloads directory.
- Handling of Android's `ACTION_SEND` intent. The user can share a file via the app, essentially pre-selecting the file in the send screen.

[<img src="https://play.google.com/intl/en_us/badges/images/generic/en_badge_web_generic.png"
      alt="Download from Google Play"
      height="60">](https://play.google.com/store/apps/details?id=com.pavelsof.wormhole)


## setup

In order to leverage the original [magic wormhole][magic-wormhole] package and also because I was curious whether it will even work, the code is written in Python using [Kivy][kivy] and friends.

```sh
# create a virtual environment
# version 3.8 should work
python3 -m venv venv
source venv/bin/activate

# install the dependencies
# pip-sync is also fine
pip install --upgrade pip
pip install -r requirements.txt

# run the (too) few unit tests
pytest tests

# run locally
python src/main.py

# run on an android phone
buildozer android debug deploy run logcat
```

If you also feel adventurous about mobile apps in Python.. pull requests are welcome :)


## licence

GPL. You can do what you want with this code as long as you let others do the same.

[magic-wormhole]: https://github.com/warner/magic-wormhole
[kivy]: https://github.com/kivy/kivy

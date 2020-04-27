# wormhole

This is a work-in-progress mobile client for the [magic wormhole][magic-wormhole] protocol. What already works:

- [x] Sending files. The app can obtain a code, exchange keys with the other party, allow the user to pick a file to send down the wormhole, and then actually transfer the file.
- [x] Receiving files. The user can enter a code, view a file offer to confirm or reject, and indeed receive a file. This will be saved in the downloads directory.
- [x] Handling of Android's `ACTION_SEND` intent. The user can "share" a file via the app, essentially pre-filling the file in the Send screen.

Some other things that would be nice to work:

- [ ] Auto-completion when entering the code in the Receive screen.
- [ ] Provide a way for the user to directly open the freshly received file (as opposed to just opening the downloads directory).
- [ ] Tor support.
- [ ] Build the app for iOS.


## setup

In order to leverage the original [magic wormhole][magic-wormhole] package and also because I was curious whether it will even work, the code is written in Python using [Kivy][kivy] and friends.

```sh
# create a virtual environment
# it should work with 3.7, have not tried with others
python3 -m venv venv
source venv/bin/activate

# install the dependencies
# pip-sync is also fine
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

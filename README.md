# wormhole

This is a work-in-progress mobile client for the [magic wormhole][magic-wormhole] protocol.

## setup

```sh
# create a virtual environment
# it should work with 3.7, have not tried with others
python3 -m venv venv
source venv/bin/activate

# install the dependencies
# pip-sync is also fine
pip install -r requirements.txt

# run locally
python src/main.py

# run on an android phone
buildozer android debug deploy run logcat
```

## licence

GPL. You can do what you want with this code as long as you let others do the same.

[magic-wormhole]: https://github.com/warner/magic-wormhole

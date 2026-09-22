# The stand

A small shop with the same pages and the same REST API as the public demo site this
suite was written against: registration and login, a catalogue with search, a cart,
checkout and payment, and the API's convention of returning HTTP 200 with the real
status in `responseCode`. It exists so the suite has something to run against on
every push — no network, no second terminal, no account on somebody else's site.

It is not a copy of that site. It reproduces what the suite depends on: the markup
the page objects select on, the messages the assertions read, the shapes the API
client parses. Nothing persists — one in-memory account store and one session store
per process, both empty at start-up — so restarting is how the data is reset.

## Run it

    make stand                              # http://127.0.0.1:8092
    uvicorn stand.app.main:app --port 8092   # the same thing, spelled out

## How the suite uses it

`TEST_ENV=local` is the default target, and the `local_stand` fixture in
`tests/conftest.py` starts the shop inside the pytest process when nothing answers on
the port, so a clean clone runs green; anything already listening there is used as it
is. `tests/stand/` is this shop's contract — the selectors, texts and API shapes the
suite depends on, checked over HTTP without a browser.

# Captured jobs design preview

`captured-jobs.html` is a standalone visual prototype with explicitly labelled sample data. It does not connect to PostgreSQL or call application status endpoints. Search, source and score filters, status tabs, date selection, and comfortable/compact layouts work locally. Refreshing or resetting restores the sample data.

From the project root, preview it with:

```sh
venv/bin/python -m http.server 8766 --bind 127.0.0.1 --directory web/previews
```

Open `http://127.0.0.1:8766/captured-jobs.html`. The production application and stylesheet are unchanged.

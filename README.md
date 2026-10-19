# bbh-medien

Fertige Medien für geplante Instagram-Posts von Busy Being Healthy. Wird automatisch befüllt, bitte nicht von Hand ändern.

- `warteschlange/<post>/` freigegebene Posts mit `post.json` und Medien, `ergebnis.json` nach dem Posten
- `probe/<post>/` Trockenläufe, nichts davon wird veröffentlicht
- `scripts/posten.py` und `.github/workflows/posten.yml` posten alle 10 Minuten, was fällig ist

#!/usr/bin/env python3
"""Postet die Hook-Tests: 10 Probe-Reels (Trial Reels, MANUAL) pro Tag aus dem Branch `hooktests`.

Der Workflow checkt den Branch nach ./ht aus. Darin: wochen/<woche>/plan.json (Slots mit Zeit, Hook, Clip, Caption),
clips/*.mp4 und jetzt/ (gerade gerenderte Reels, Meta holt sie per raw-URL). Der Branch hat immer genau einen Commit,
damit das Repo nicht wächst.

Ergebnisse: hooktests/ergebnisse/<slot-id>.json auf main. 48 Stunden nach dem Posten holt das Skript die Zahlen (insights).

  python3 scripts/hooktest_posten.py            fällige Slots posten, Zahlen holen
  python3 scripts/hooktest_posten.py --trocken  nur prüfen, was fällig wäre, nichts rendern oder posten
  python3 scripts/hooktest_posten.py --faellig  Exit 0, wenn ein Slot fällig ist (dann installiert der Workflow ffmpeg)
"""
import datetime, json, pathlib, subprocess, sys, time, urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from posten import api, warten_bis_fertig, MetaFehler, IG, REPO  # noqa: E402

HT = pathlib.Path("ht")
ERG = pathlib.Path("hooktests/ergebnisse")
FONTS = pathlib.Path("fonts")
BASIS = f"https://raw.githubusercontent.com/{REPO}/hooktests/"
MAX_VERSPAETUNG = 3 * 3600          # danach gilt ein Slot als verpasst (sonst kämen 10 auf einmal)
MAX_PRO_LAUF = 3
METRIKEN = ["views", "reach", "likes", "comments", "shares", "saved", "total_interactions", "ig_reels_avg_watch_time"]


def jetzt():
    return datetime.datetime.now(datetime.timezone.utc)


def schreiben(sid, d):
    ERG.mkdir(parents=True, exist_ok=True)
    (ERG / f"{sid}.json").write_text(json.dumps(d, ensure_ascii=False, indent=1))


def git(*a, ok=False):
    r = subprocess.run(["git", "-C", str(HT), "-c", "user.name=BBH Automatik", "-c", "user.email=noreply@github.com", *a],
                       capture_output=True, text=True)
    if r.returncode and not ok:
        raise MetaFehler(f"git {' '.join(a)}: {r.stderr.strip()[-300:]}")
    return r


def bereitstellen(slot):
    """Rendert das Reel nach ht/jetzt/<id>.mp4, legt es auf den Branch (ein Commit, force-with-lease) und wartet,
    bis die raw-URL antwortet."""
    import hookbild                     # erst hier: braucht Pillow, das der Workflow nur bei Bedarf installiert
    ziel = HT / "jetzt" / f"{slot['id']}.mp4"
    ziel.parent.mkdir(exist_ok=True)
    hookbild.rendern(HT / slot["clip"], slot["hook"], ziel, slot.get("pos", "oben"), FONTS)
    gestern = (jetzt() - datetime.timedelta(days=1)).date().isoformat()
    for alt in (HT / "jetzt").glob("*.mp4"):
        if alt.name[:10] < gestern:
            alt.unlink()
    for versuch in range(3):
        git("add", "-A", ".")
        git("commit", "-q", "--amend", "--no-edit")
        if git("push", "-q", "--force-with-lease", "origin", "HEAD:hooktests", ok=True).returncode == 0:
            break
        # Branch wurde inzwischen neu eingereiht: neuen Stand holen, Reel erneut ablegen
        git("fetch", "-q", "origin", "hooktests")
        git("reset", "-q", "--hard", "origin/hooktests")
        ziel.parent.mkdir(exist_ok=True)
        hookbild.rendern(HT / slot["clip"], slot["hook"], ziel, slot.get("pos", "oben"), FONTS)
    else:
        raise MetaFehler("Push auf hooktests klappt nicht")
    url = BASIS + f"jetzt/{slot['id']}.mp4"
    for _ in range(20):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=20) as r:
                if r.status == 200:
                    return url
        except Exception:
            pass
        time.sleep(6)
    raise MetaFehler(f"{url} nicht erreichbar")


def posten(slot, plan):
    erg = {k: slot[k] for k in ("id", "zeit", "hook", "typ", "nr", "clip_id", "thema", "woche") if k in slot}
    erg["versuch"] = jetzt().isoformat(timespec="seconds")
    try:
        url = bereitstellen(slot)
        c = api("POST", f"{IG}/media", media_type="REELS", video_url=url, caption=slot["caption"],
                trial_params={"graduation_strategy": plan.get("probe", "MANUAL")})
        warten_bis_fertig(c["id"])
        pub = api("POST", f"{IG}/media_publish", creation_id=c["id"])
        info = api("GET", pub["id"], fields="permalink,timestamp")
        erg.update(status="online", media_id=pub["id"], permalink=info.get("permalink"), zeitpunkt=info.get("timestamp"))
    except (MetaFehler, subprocess.CalledProcessError) as e:
        erg.update(status="fehler", fehler=str(e)[:500])
    return erg


def zahlen_holen():
    for p in sorted(ERG.glob("*.json")):
        d = json.loads(p.read_text())
        if d.get("status") != "online" or d.get("insights") or not d.get("zeitpunkt"):
            continue
        gepostet = datetime.datetime.fromisoformat(d["zeitpunkt"].replace("+0000", "+00:00"))
        if jetzt() - gepostet < datetime.timedelta(hours=48):
            continue
        werte = {}
        for metriken in (METRIKEN, ["views", "reach", "ig_reels_avg_watch_time"]):
            try:
                r = api("GET", f"{d['media_id']}/insights", metric=",".join(metriken))
                werte = {m["name"]: (m.get("values") or [{}])[0].get("value", m.get("total_value", {}).get("value"))
                         for m in r.get("data", [])}
                break
            except MetaFehler as e:
                d["insights_fehler"] = str(e)[:300]
        if werte:
            d["insights"] = werte
            d["insights_am"] = jetzt().isoformat(timespec="seconds")
            d.pop("insights_fehler", None)
        p.write_text(json.dumps(d, ensure_ascii=False, indent=1))
        print(d["id"], "Zahlen", werte or d.get("insights_fehler"))


def faellig():
    for plan_datei in HT.glob("wochen/*/plan.json"):
        for slot in json.loads(plan_datei.read_text())["slots"]:
            zeit = datetime.datetime.fromisoformat(slot["zeit"])
            datei = ERG / f"{slot['id']}.json"
            alt = json.loads(datei.read_text()) if datei.exists() else {}
            if alt.get("status") not in ("online", "verpasst") and alt.get("versuche", 0) < 2 \
                    and zeit <= jetzt() and (jetzt() - zeit).total_seconds() <= MAX_VERSPAETUNG:
                return True
    return False


def main():
    trocken = "--trocken" in sys.argv
    if not HT.exists():
        print("Kein Branch hooktests, nichts zu tun"); return
    if "--faellig" in sys.argv:
        sys.exit(0 if faellig() else 1)
    if not trocken:
        zahlen_holen()
    gepostet = 0
    for plan_datei in sorted(HT.glob("wochen/*/plan.json")):
        plan = json.loads(plan_datei.read_text())
        for slot in plan["slots"]:
            zeit = datetime.datetime.fromisoformat(slot["zeit"])
            datei = ERG / f"{slot['id']}.json"
            alt = json.loads(datei.read_text()) if datei.exists() else {}
            if alt.get("status") in ("online", "verpasst") or alt.get("versuche", 0) >= 2 or zeit > jetzt():
                continue
            if (jetzt() - zeit).total_seconds() > MAX_VERSPAETUNG:
                schreiben(slot["id"], {**{k: slot[k] for k in ("id", "zeit", "hook", "typ")}, "status": "verpasst"})
                print(slot["id"], "verpasst"); continue
            if trocken:
                print(slot["id"], "wäre fällig:", slot["hook"]); continue
            if gepostet >= MAX_PRO_LAUF:
                return
            erg = posten(slot, plan)
            erg["versuche"] = alt.get("versuche", 0) + 1
            schreiben(slot["id"], erg)
            print(json.dumps(erg, ensure_ascii=False))
            gepostet += 1


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Postet fällige, freigegebene Posts aus warteschlange/ auf Instagram.

Jeder Post liegt in warteschlange/<id>/ mit post.json und den Medien.
post.json: {"id", "zeit" (ISO mit Zeitzone), "typ": "karussell"|"foto"|"reel",
            "caption", "collaborators": [...], "medien": ["01.jpg", ...], "freigegeben_am"}
Nach dem Posten schreibt das Skript ergebnis.json in denselben Ordner.

Aufruf:  python3 scripts/posten.py            (postet alles, was fällig ist)
         python3 scripts/posten.py --trocken --ordner probe/<id>
                                               (baut alles bei Meta auf, veröffentlicht aber nicht)
"""
import argparse, datetime, json, os, pathlib, sys, time, urllib.error, urllib.parse, urllib.request

V = "v23.0"
IG = os.environ.get("IG_USER_ID", "17841454217301056")
TOKEN = os.environ["META_TOKEN"]
REPO = os.environ.get("GITHUB_REPOSITORY", "beatricetuttlies-web/bbh-medien")
BASIS = f"https://raw.githubusercontent.com/{REPO}/main/"


class MetaFehler(Exception):
    pass


def api(methode, pfad, **daten):
    daten["access_token"] = TOKEN
    url = f"https://graph.facebook.com/{V}/{pfad}"
    kodiert = urllib.parse.urlencode({k: (json.dumps(v) if isinstance(v, (list, dict)) else v) for k, v in daten.items()})
    if methode == "GET":
        req = urllib.request.Request(url + "?" + kodiert)
    else:
        req = urllib.request.Request(url, data=kodiert.encode(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            fehler = json.load(e).get("error", {})
        except Exception:
            fehler = {"message": str(e)}
        raise MetaFehler(f"{fehler.get('message')} (Code {fehler.get('code')}, {fehler.get('error_subcode')})")


def warten_bis_fertig(container, max_s=600):
    start = time.time()
    while time.time() - start < max_s:
        s = api("GET", container, fields="status_code,status")
        code = s.get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise MetaFehler(f"Container {container}: {s.get('status')}")
        time.sleep(8)
    raise MetaFehler(f"Container {container}: Zeitüberschreitung")


def url_fuer(ordner, datei):
    return BASIS + urllib.parse.quote(f"{ordner}/{datei}")


def container_bauen(ordner, p):
    extra = {}
    if p.get("collaborators"):
        extra["collaborators"] = [c.lstrip("@") for c in p["collaborators"]]
    typ, medien = p["typ"], p["medien"]
    if typ == "karussell":
        kinder = []
        for m in medien:
            if m.lower().endswith(".mp4"):
                c = api("POST", f"{IG}/media", media_type="VIDEO", video_url=url_fuer(ordner, m), is_carousel_item="true")
            else:
                c = api("POST", f"{IG}/media", image_url=url_fuer(ordner, m), is_carousel_item="true")
            kinder.append(c["id"])
        for k in kinder:
            warten_bis_fertig(k)
        c = api("POST", f"{IG}/media", media_type="CAROUSEL", children=",".join(kinder), caption=p["caption"], **extra)
    elif typ == "foto":
        c = api("POST", f"{IG}/media", image_url=url_fuer(ordner, medien[0]), caption=p["caption"], **extra)
    elif typ == "reel":
        c = api("POST", f"{IG}/media", media_type="REELS", video_url=url_fuer(ordner, medien[0]),
                caption=p["caption"], share_to_feed="true", **extra)
    else:
        raise MetaFehler(f"Unbekannter Typ {typ}")
    warten_bis_fertig(c["id"])
    return c["id"]


def pruefen(p):
    probleme = []
    if len(p.get("caption", "")) > 2200:
        probleme.append("Caption länger als 2.200 Zeichen")
    if p.get("caption", "").count("#") > 30:
        probleme.append("mehr als 30 Hashtags")
    if p["typ"] == "karussell" and not 2 <= len(p["medien"]) <= 10:
        probleme.append("Karussell braucht 2 bis 10 Medien")
    if len(p.get("collaborators", [])) > 3:
        probleme.append("höchstens 3 Collab-Partner")
    if "{{" in p.get("caption", ""):
        probleme.append("Platzhalter {{…}} in der Caption")
    return probleme


def ein_post(ordner, trocken=False):
    pfad = pathlib.Path(ordner)
    p = json.loads((pfad / "post.json").read_text())
    erg = {"id": p["id"], "versuch": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    probleme = pruefen(p)
    if probleme:
        erg.update(status="fehler", fehler="; ".join(probleme))
    else:
        try:
            cid = container_bauen(ordner, p)
            if trocken:
                erg.update(status="trocken_ok", container=cid)
            else:
                pub = api("POST", f"{IG}/media_publish", creation_id=cid)
                info = api("GET", pub["id"], fields="permalink,timestamp")
                erg.update(status="online", media_id=pub["id"], permalink=info.get("permalink"), zeitpunkt=info.get("timestamp"))
        except MetaFehler as e:
            erg.update(status="fehler", fehler=str(e))
    (pfad / "ergebnis.json").write_text(json.dumps(erg, ensure_ascii=False, indent=1))
    print(json.dumps(erg, ensure_ascii=False))
    return erg


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--trocken", action="store_true")
    a.add_argument("--ordner")
    args = a.parse_args()
    if args.ordner:
        ein_post(args.ordner, trocken=args.trocken)
        return
    jetzt = datetime.datetime.now(datetime.timezone.utc)
    for post_json in sorted(pathlib.Path("warteschlange").glob("*/post.json")):
        ordner = post_json.parent
        erg_datei = ordner / "ergebnis.json"
        if erg_datei.exists():
            alt = json.loads(erg_datei.read_text())
            if alt.get("status") == "online" or alt.get("versuche", 0) >= 3:
                continue
        p = json.loads(post_json.read_text())
        if datetime.datetime.fromisoformat(p["zeit"]) > jetzt:
            continue
        if (jetzt - datetime.datetime.fromisoformat(p["zeit"])).total_seconds() > 36 * 3600:
            print(f"{p['id']}: mehr als 36 Stunden überfällig, wird nicht mehr automatisch gepostet")
            continue
        vorher = json.loads(erg_datei.read_text()).get("versuche", 0) if erg_datei.exists() else 0
        erg = ein_post(str(ordner))
        erg["versuche"] = vorher + 1
        erg_datei.write_text(json.dumps(erg, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

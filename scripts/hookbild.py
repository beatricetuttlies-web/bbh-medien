#!/usr/bin/env python3
"""Hook-Bild für Probe-Reels: ein 6-Sekunden-Clip, darauf der Hook auf einer Papierplatte und darunter
der Aha-Satz des Tages (kleiner, Montserrat). Der Hook macht neugierig, der Aha-Satz sagt, worum es geht.

Diese Datei gibt es zweimal, identisch: hier und in bbh-medien/scripts/hookbild.py (dort rendert GitHub kurz vor dem
Posten). Bei Änderungen beide anpassen.

  python3 hookbild.py <clip.mp4> "<hook mit *kursivem* wort>" <ausgang.mp4> [--aha "<satz>"] [--pos oben|unten] [--fonts <ordner>]
  python3 hookbild.py --bild "<hook>" <ausgang.png> [--aha "<satz>"] [--pos oben|unten]   nur die Ebene (zum Ansehen)

Stil (strategie/design-system.md, Videostil): Papierplatten statt Glaskacheln, Hook in Cormorant Garamond (Tinte, ein
kursives Wort in Bordeaux), Aha-Satz in Montserrat, kein Verlauf, kein Glow. Text nie über dem Gesicht: Position kommt
aus dem Clip-Katalog.
"""
import pathlib, subprocess, sys, tempfile
from PIL import Image, ImageDraw, ImageFilter, ImageFont

B, H = 1080, 1920
PAPIER, TINTE, BORDEAUX = (247, 242, 232), (60, 40, 42), (90, 46, 50)
GROESSE, ZEILE, BREITE_MAX = 66, 1.14, 860
AHA_GROESSE, AHA_ZEILE, AHA_BREITE = 42, 1.34, 840
PAD_X, PAD_Y, AHA_PAD_Y, ABSTAND = 52, 34, 26, 22
OBEN_Y, UNTEN_ABSTAND = 300, 520          # oben: unter der Instagram-Leiste; unten: über Caption und Knöpfen
DAUER, AHA_AB = 6.0, 0.0   # seit 18.11.2026: Text steht ab dem ersten Bild (Beas Wunsch)


def fonts_ordner(arg=None):
    if arg:
        return pathlib.Path(arg)
    hier = pathlib.Path(__file__).resolve()
    for kandidat in (hier.parents[2] / "vorlagen/fonts/ttf", hier.parents[1] / "fonts"):
        if kandidat.exists():
            return kandidat
    raise SystemExit("Fonts nicht gefunden")


def woerter(text):
    """'Warum du *abends* hellwach bist' -> [(wort, kursiv, kleben), ...]"""
    aus, vorher = [], " "
    for i, teil in enumerate(text.split("*")):
        kursiv = i % 2 == 1
        for j, w in enumerate(teil.split()):
            # „*müde*,“ -> Komma ohne Leerzeichen; „abends *müde*“ -> mit Leerzeichen
            kleben = j == 0 and bool(aus) and not teil[:1].isspace() and not vorher[-1:].isspace()
            aus.append((w, kursiv, kleben))
        if teil:
            vorher = teil
    return aus


def umbrechen(text, normal, kursiv, breite_max):
    leer = normal.getlength(" ")
    zeilen, zeile, breite = [], [], 0
    for w, k, kleben in woerter(text):
        wb = (kursiv if k else normal).getlength(w)
        abstand = 0 if kleben else leer
        if zeile and breite + abstand + wb > breite_max:
            if kleben:                                    # Satzzeichen nie allein in die neue Zeile
                vw, vk, vb, _ = zeile.pop(); breite -= vb + (zeile and leer or 0)
                zeilen.append((zeile, breite)); zeile, breite = [(vw, vk, vb, False)], vb
            else:
                zeilen.append((zeile, breite)); zeile, breite = [], 0
                abstand = 0
        breite += (abstand if zeile else 0) + wb
        zeile.append((w, k, wb, kleben and bool(zeile)))
    if zeile:
        zeilen.append((zeile, breite))
    return zeilen, leer


def platte(bild, x0, y0, pb, ph):
    schatten = Image.new("RGBA", (B, H), (0, 0, 0, 0))
    ImageDraw.Draw(schatten).rectangle([x0 + 4, y0 + 10, x0 + pb + 4, y0 + ph + 10], fill=(20, 14, 14, 46))
    bild = Image.alpha_composite(bild, schatten.filter(ImageFilter.GaussianBlur(14)))
    ImageDraw.Draw(bild).rectangle([x0, y0, x0 + pb, y0 + ph], fill=PAPIER + (244,))
    return bild


def text_setzen(bild, zeilen, leer, y, zh, normal, kursiv, farbe_n, farbe_k, versatz):
    d = ImageDraw.Draw(bild)
    for zeile, b in zeilen:
        x = (B - b) / 2
        for n, (w, k, wb, kleben) in enumerate(zeile):
            if n and not kleben:
                x += leer
            d.text((x, y + zh * versatz), w, font=kursiv if k else normal, fill=(farbe_k if k else farbe_n) + (255,))
            x += wb
        y += zh


def ebenen(text, aha="", pos="oben", fonts=None):
    """Gibt (Hook-Ebene, Aha-Ebene oder None) als RGBA-Bilder 1080 × 1920 zurück, gemeinsam gesetzt."""
    f = fonts_ordner(fonts)
    normal = ImageFont.truetype(str(f / "cormorant-garamond-latin-500-normal.ttf"), GROESSE)
    kursiv = ImageFont.truetype(str(f / "cormorant-garamond-latin-500-italic.ttf"), GROESSE)
    zeilen, leer = umbrechen(text, normal, kursiv, BREITE_MAX)
    zh = int(GROESSE * ZEILE)
    pb = int(max(b for _, b in zeilen)) + 2 * PAD_X
    ph = zh * len(zeilen) + 2 * PAD_Y
    a_zeilen, a_ph, a_pb = [], 0, 0
    if aha:
        mfont = f / "montserrat-latin-400-normal.ttf"
        a_n = ImageFont.truetype(str(mfont), AHA_GROESSE)
        a_zeilen, a_leer = umbrechen(aha.replace("*", ""), a_n, a_n, AHA_BREITE)
        a_zh = int(AHA_GROESSE * AHA_ZEILE)
        a_pb = int(max(b for _, b in a_zeilen)) + 2 * PAD_X
        a_ph = a_zh * len(a_zeilen) + 2 * AHA_PAD_Y
    gesamt = ph + (ABSTAND + a_ph if aha else 0)
    y0 = OBEN_Y if pos == "oben" else H - UNTEN_ABSTAND - gesamt
    hook = platte(Image.new("RGBA", (B, H), (0, 0, 0, 0)), (B - pb) // 2, y0, pb, ph)
    text_setzen(hook, zeilen, leer, y0 + PAD_Y, zh, normal, kursiv, TINTE, BORDEAUX, 0.08)
    if not aha:
        return hook, None
    ay = y0 + ph + ABSTAND
    ahabild = platte(Image.new("RGBA", (B, H), (0, 0, 0, 0)), (B - a_pb) // 2, ay, a_pb, a_ph)
    text_setzen(ahabild, a_zeilen, a_leer, ay + AHA_PAD_Y, a_zh, a_n, a_n, TINTE, TINTE, 0.12)
    return hook, ahabild


def ebene(text, pos="oben", fonts=None, aha=""):
    """Beide Ebenen übereinander (Endzustand), zum Ansehen."""
    hook, ahabild = ebenen(text, aha, pos, fonts)
    return Image.alpha_composite(hook, ahabild) if ahabild else hook


def rendern(clip, text, aus, pos="oben", fonts=None, aha=""):
    with tempfile.TemporaryDirectory() as tmp:
        hook, ahabild = ebenen(text, aha, pos, fonts)
        p1, p2 = pathlib.Path(tmp) / "hook.png", pathlib.Path(tmp) / "aha.png"
        hook.save(p1)
        eingaben = ["-loop", "1", "-framerate", "30", "-i", str(p1)]
        filt = "[1]format=rgba[o1];[0:v][o1]overlay=0:0:shortest=1[v1]"
        if ahabild:
            ahabild.save(p2)
            eingaben += ["-loop", "1", "-framerate", "30", "-i", str(p2)]
            filt += ";[2]format=rgba[o2];[v1][o2]overlay=0:0:shortest=1[v2]"
        filt += f";[{'v2' if ahabild else 'v1'}]format=yuv420p[v]"
        # Ton raus (seit 18.11.2026, Beas Wunsch): stille Tonspur statt Originalton, damit Instagram eine Tonspur hat
        stumm = len(eingaben) // 6 + 1
        eingaben += ["-f", "lavfi", "-t", str(DAUER), "-i", "anullsrc=r=48000:cl=stereo"]
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(clip), *eingaben, "-filter_complex", filt, "-map", "[v]",
               "-map", f"{stumm}:a", "-c:a", "aac", "-b:a", "128k"] + \
              ["-t", str(DAUER), "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-r", "30",
               "-movflags", "+faststart", str(aus)]
        subprocess.run(cmd, check=True)
    return aus


def main(a):
    def opt(name, standard=""):
        return a[a.index(name) + 1] if name in a else standard
    pos, fonts, aha = opt("--pos", "oben"), opt("--fonts", None), opt("--aha")
    rest = [x for i, x in enumerate(a) if not x.startswith("--") and (i == 0 or a[i - 1] not in ("--pos", "--fonts", "--aha"))]
    if "--bild" in a:
        ebene(rest[0], pos, fonts, aha).save(rest[1]); return
    rendern(rest[0], rest[1], rest[2], pos, fonts, aha)


if __name__ == "__main__":
    main(sys.argv[1:])

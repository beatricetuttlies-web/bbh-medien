#!/usr/bin/env python3
"""Hook-Bild für Probe-Reels: ein 6-Sekunden-Clip, darauf der Hook auf einer Papierplatte.

Diese Datei gibt es zweimal, identisch: hier und in bbh-medien/scripts/hookbild.py (dort rendert GitHub kurz vor dem
Posten). Bei Änderungen beide anpassen.

  python3 hookbild.py <clip.mp4> "<hook mit *kursivem* wort>" <ausgang.mp4> [--pos oben|unten] [--fonts <ordner>]
  python3 hookbild.py --bild "<hook>" <ausgang.png> [--pos oben|unten]     nur die Ebene (zum Ansehen)

Stil (strategie/design-system.md, Videostil): Papierplatte statt Glaskachel, Cormorant Garamond in Tinte,
ein kursives Wort in Bordeaux, kein Verlauf, kein Glow. Text nie über dem Gesicht: Position kommt aus dem Clip-Katalog.
"""
import pathlib, subprocess, sys, tempfile
from PIL import Image, ImageDraw, ImageFont

B, H = 1080, 1920
PAPIER, TINTE, BORDEAUX = (247, 242, 232), (60, 40, 42), (90, 46, 50)
GROESSE, ZEILE, BREITE_MAX = 66, 1.14, 860
PAD_X, PAD_Y = 52, 34
OBEN_Y, UNTEN_ABSTAND = 300, 560          # oben: unter der Instagram-Leiste; unten: über Caption und Knöpfen
DAUER = 6.0


def fonts_ordner(arg=None):
    if arg:
        return pathlib.Path(arg)
    hier = pathlib.Path(__file__).resolve()
    for kandidat in (hier.parents[2] / "vorlagen/fonts/ttf", hier.parents[1] / "fonts"):
        if kandidat.exists():
            return kandidat
    raise SystemExit("Fonts nicht gefunden")


def woerter(text):
    """'Warum du *abends* hellwach bist' -> [(wort, kursiv), ...]"""
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


def ebene(text, pos="oben", fonts=None):
    f = fonts_ordner(fonts)
    normal = ImageFont.truetype(str(f / "cormorant-garamond-latin-500-normal.ttf"), GROESSE)
    kursiv = ImageFont.truetype(str(f / "cormorant-garamond-latin-500-italic.ttf"), GROESSE)
    leer = normal.getlength(" ")
    zeilen, zeile, breite = [], [], 0
    for w, k, kleben in woerter(text):
        wb = (kursiv if k else normal).getlength(w)
        abstand = 0 if kleben else leer
        if zeile and breite + abstand + wb > BREITE_MAX:
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
    zh = int(GROESSE * ZEILE)
    pb = int(max(b for _, b in zeilen)) + 2 * PAD_X
    ph = zh * len(zeilen) + 2 * PAD_Y
    x0 = (B - pb) // 2
    y0 = OBEN_Y if pos == "oben" else H - UNTEN_ABSTAND - ph
    bild = Image.new("RGBA", (B, H), (0, 0, 0, 0))
    schatten = Image.new("RGBA", (B, H), (0, 0, 0, 0))
    ImageDraw.Draw(schatten).rectangle([x0 + 4, y0 + 10, x0 + pb + 4, y0 + ph + 10], fill=(20, 14, 14, 46))
    from PIL import ImageFilter
    bild = Image.alpha_composite(bild, schatten.filter(ImageFilter.GaussianBlur(14)))
    d = ImageDraw.Draw(bild)
    d.rectangle([x0, y0, x0 + pb, y0 + ph], fill=PAPIER + (244,))
    y = y0 + PAD_Y
    for zeile, b in zeilen:
        x = (B - b) / 2
        for n, (w, k, wb, kleben) in enumerate(zeile):
            if n and not kleben:
                x += leer
            d.text((x, y + zh * 0.08), w, font=kursiv if k else normal, fill=(BORDEAUX if k else TINTE) + (255,))
            x += wb
        y += zh
    return bild


def rendern(clip, text, aus, pos="oben", fonts=None):
    with tempfile.TemporaryDirectory() as tmp:
        png = pathlib.Path(tmp) / "hook.png"
        ebene(text, pos, fonts).save(png)
        ton = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                              "-of", "csv=p=0", str(clip)], capture_output=True, text=True).stdout.strip()
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(clip), "-loop", "1", "-framerate", "30", "-i", str(png),
               "-filter_complex", "[1]format=rgba,fade=in:st=0:d=0.2:alpha=1[o];[0:v][o]overlay=0:0:shortest=1,format=yuv420p[v]",
               "-map", "[v]"] + (["-map", "0:a", "-c:a", "aac", "-b:a", "128k"] if ton else []) + \
              ["-t", str(DAUER), "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-r", "30",
               "-movflags", "+faststart", str(aus)]
        subprocess.run(cmd, check=True)
    return aus


def main(a):
    pos = a[a.index("--pos") + 1] if "--pos" in a else "oben"
    fonts = a[a.index("--fonts") + 1] if "--fonts" in a else None
    rest = [x for i, x in enumerate(a) if not x.startswith("--") and (i == 0 or a[i - 1] not in ("--pos", "--fonts"))]
    if "--bild" in a:
        ebene(rest[0], pos, fonts).save(rest[1]); return
    rendern(rest[0], rest[1], rest[2], pos, fonts)


if __name__ == "__main__":
    main(sys.argv[1:])

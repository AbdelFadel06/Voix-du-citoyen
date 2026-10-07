"""Fabrique de vrais fichiers (en mémoire) pour tester les envois."""

import io

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

TAG_ORIENTATION = 0x0112
TAG_GPS = 0x8825
TAG_MODELE = 0x0110


def jpeg_avec_exif(largeur=40, hauteur=20, orientation=None, nom="photo.jpg"):
    """JPEG portant un modèle d'appareil, une position GPS et éventuellement une orientation."""
    image = Image.new("RGB", (largeur, hauteur), "red")
    exif = Image.Exif()
    exif[TAG_MODELE] = "Tecno Spark 10"
    exif.get_ifd(TAG_GPS).update({1: "N", 2: (6.0, 24.0, 4.0), 3: "E", 4: (2.0, 20.0, 30.0)})
    if orientation:
        exif[TAG_ORIENTATION] = orientation
    tampon = io.BytesIO()
    image.save(tampon, format="JPEG", exif=exif.tobytes())
    return SimpleUploadedFile(nom, tampon.getvalue(), content_type="image/jpeg")


def image(format_="PNG", mode="RGBA", taille=(30, 30), nom=None):
    tampon = io.BytesIO()
    Image.new(mode, taille, (0, 128, 255, 120) if mode == "RGBA" else "blue").save(tampon, format=format_)
    extension = {"JPEG": "jpg"}.get(format_, format_.lower())
    return SimpleUploadedFile(nom or f"image.{extension}", tampon.getvalue(), content_type=f"image/{extension}")


def _mp4(marque, compatible=b"isom"):
    boite = b"ftyp" + marque + b"\x00\x00\x02\x00" + compatible + marque
    return len(boite).to_bytes(4, "big") + boite + b"\x00" * 2048


def video_mp4(nom="video.mp4"):
    return SimpleUploadedFile(nom, _mp4(b"mp42"), content_type="video/mp4")


def audio_m4a(nom="vocal.m4a"):
    return SimpleUploadedFile(nom, _mp4(b"M4A ", b"M4A "), content_type="audio/mp4")


def audio_android(nom="vocal.m4a"):
    """Enregistrement MPEG-4 d'Android, détecté comme video/mp4."""
    return SimpleUploadedFile(nom, _mp4(b"mp42"), content_type="audio/mp4")


def audio_mp3(nom="vocal.mp3"):
    return SimpleUploadedFile(nom, b"\xff\xfb\x90\x64" + b"\x00" * 2048, content_type="audio/mpeg")


def pdf(nom="document.pdf"):
    return SimpleUploadedFile(nom, b"%PDF-1.4\n" + b"\x00" * 512, content_type="application/pdf")


def jpeg_corrompu(nom="photo.jpg"):
    return SimpleUploadedFile(nom, b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x13\x37" * 500, content_type="image/jpeg")


def trop_gros(taille, nom="photo.jpg"):
    return SimpleUploadedFile(nom, b"\xff\xd8\xff" + b"\x00" * (taille - 2), content_type="image/jpeg")

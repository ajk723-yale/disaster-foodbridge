"""Generate two SYNTHETIC warehouse images (drawn, not photographed) with known contents.

They exist only to test the vision pipeline against a known ground truth. They are not
real photos and do not show real lighting, clutter, or camera angles.

    .venv/bin/python scripts/make_sample_warehouse_photos.py
"""
import json
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "sample_photos")
FONT = "/System/Library/Fonts/Helvetica.ttc"


def font(size):
    return ImageFont.truetype(FONT, size)


def shelf(draw, y, x0=40, x1=1320):
    draw.rectangle([x0, y, x1, y + 14], fill=(110, 80, 50))


def box(draw, x, y, w, h, color, lines, size=15):
    draw.rectangle([x, y, x + w, y + h], fill=color, outline=(60, 45, 30), width=2)
    ty = y + 8
    for text in lines:
        draw.text((x + 6, ty), text, fill=(20, 20, 20), font=font(size))
        ty += size + 4


def photo_wh_a():
    img = Image.new("RGB", (1280, 820), (196, 196, 190))
    d = ImageDraw.Draw(img)
    d.text((40, 12), "WAREHOUSE A - AISLE 2", fill=(40, 40, 40), font=font(26))
    # top shelf: 6 cases of canned bread
    for i in range(6):
        box(d, 50 + i * 170, 70, 155, 140, (214, 170, 110), ["CANNED BREAD", "24 cans / case"])
    shelf(d, 212)
    # middle shelf: 8 boxes of instant miso soup (not in the inventory)
    for i in range(8):
        box(d, 50 + i * 128, 270, 118, 120, (232, 220, 170), ["INSTANT", "MISO SOUP", "20 cups"], 14)
    shelf(d, 392)
    # bottom shelf: 12 packs of liquid infant formula, and one carton with a blurred label
    for i in range(12):
        box(d, 50 + i * 78, 470, 70, 110, (245, 245, 250), ["LIQUID", "INFANT", "FORMULA"], 11)
    box(d, 1000, 450, 200, 130, (190, 150, 100), ["EMERGENCY", "RATIONS", "48 pcs"], 18)
    region = (1000, 450, 1201, 581)
    img.paste(img.crop(region).filter(ImageFilter.GaussianBlur(7)), region)
    d = ImageDraw.Draw(img)
    shelf(d, 582)
    d.rectangle([1240, 0, 1280, 820], fill=(70, 70, 70))           # frame edge: shelving continues out of view
    d.text((50, 760), "Shelving continues to the right (out of frame).", fill=(60, 60, 60), font=font(16))
    return img, {
        "warehouse_id": "WH-A",
        "visible": [
            {"label": "CANNED BREAD 24 cans / case", "units": 6, "unit": "case"},
            {"label": "INSTANT MISO SOUP 20 cups", "units": 8, "unit": "box"},
            {"label": "LIQUID INFANT FORMULA", "units": 12, "unit": "pack"},
            {"label": "(blurred, unreadable carton)", "units": 1, "unit": "carton"},
        ],
        "notes": "Partial view: shelving continues out of frame. Inventory (latest validated) WH-A: canned bread "
                 "10 cases, liquid infant formula 20 packs, alpha rice 300 packs, water 500 bottles. Miso soup is "
                 "not in the inventory.",
    }


def photo_wh_b():
    img = Image.new("RGB", (1280, 820), (188, 192, 196))
    d = ImageDraw.Draw(img)
    d.text((40, 12), "WAREHOUSE B - BAY 1", fill=(40, 40, 40), font=font(26))
    d.rectangle([40, 700, 700, 730], fill=(150, 115, 70))              # pallet
    for row in range(6):                                              # 6 x 6 = 36 packs
        for col in range(6):
            box(d, 50 + col * 106, 90 + row * 100, 98, 92, (250, 236, 200),
                ["ALLERGEN-", "FREE", "CURRY RICE"], 12)
    for i in range(3):                                                # 3 cartons, label says 50 packs each
        box(d, 760 + i * 165, 470, 155, 230, (205, 160, 105), ["ALPHA RICE", "(RETORT)", "50 packs", "per carton"], 16)
    d.rectangle([740, 730, 1250, 745], fill=(110, 80, 50))
    return img, {
        "warehouse_id": "WH-B",
        "visible": [
            {"label": "ALLERGEN-FREE CURRY RICE", "units": 36, "unit": "pack"},
            {"label": "ALPHA RICE (RETORT) 50 packs per carton", "units": 3, "unit": "carton (label: 50 packs each)"},
        ],
        "notes": "Inventory (latest validated) WH-B: allergen-free curry rice 30 packs (36 visible, so more than "
                 "recorded), alpha rice 120 packs (3 cartons x 50 = 150 if the label is accurate).",
    }


def main():
    os.makedirs(OUT, exist_ok=True)
    truth = {"note": "SYNTHETIC test images drawn by scripts/make_sample_warehouse_photos.py; not real photos.",
             "images": {}}
    for name, make in (("synthetic_wh_a_aisle2.png", photo_wh_a), ("synthetic_wh_b_bay1.png", photo_wh_b)):
        img, gt = make()
        img.save(os.path.join(OUT, name))
        truth["images"][name] = gt
    with open(os.path.join(OUT, "ground_truth.json"), "w") as f:
        json.dump(truth, f, indent=2)
    print("written to", OUT)


if __name__ == "__main__":
    main()

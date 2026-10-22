"""Actualiza data.json con el catálogo de cada tienda Shopify listada en stores.json.

Uso:  python scripts/update.py
Lo corre GitHub Actions todos los días (.github/workflows/update.yml).
Para agregar una tienda Shopify basta con sumar una línea en stores.json.
"""
import json, re, sys, time, unicodedata, datetime, urllib.request, urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_PAGES = 20          # 20 x 250 = hasta 5.000 productos por tienda
IMG_WIDTH = 600         # ancho pedido al CDN de Shopify para las fotos

def norm(s):
    s = unicodedata.normalize("NFD", str(s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")

# ---------- reglas de clasificación (editar aquí) ----------
EXCLUDE = r"^prueba|\bcd\b|vinilo|vinyl|gift ?card|tarjeta de regalo|giftcard|espejo"

CATS = [
    ("Shorts", r"\bshorts?\b|\bbermuda|\bjorts?\b"),
    ("Pantalones", r"pantal|\bpants?\b|\bjeans?\b|\bcargo|jogger|\bbuzo|baggy|trouser"),
    ("Polerones", r"hoodie|poleron|sudadera|sweatshirt|crewneck|\bcrew\b|canguro"),
    ("Chaquetas", r"anorak|jacket|chaqueta|parka|cortaviento|windbreaker|bomber|campera|varsity"),
    ("Sweaters", r"sweater|knit|chaleco|cardigan|\bvest\b|sueter|tejido"),
    ("Poleras", r"polera|\btee\b|t-shirt|tshirt|camiseta|jersey|long sleeve|manga larga|\btank\b|musculosa|\bshirt\b|camisa"),
    ("Faldas y vestidos", r"falda|vestido|\bberno\b|skirt|dress"),
    ("Gorros", r"jockey|gorro|\bcap\b|beanie|beannie|trucker|truker|snapback|bucket|visera|gorra"),
]

COLORS = [
    ("Camuflado", r"camo|camufl"),
    ("Negro", r"\bblack\b|\bnegr[oa]s?\b|\bnoir\b|\bonyx\b"),
    ("Blanco/Crema", r"\bwhite\b|\bblanc[oa]s?\b|off.?white|\bcrema\b|\bcream\b|\bivory\b|\bhueso\b|\bbone\b|\becru\b|\bmarfil\b"),
    ("Gris", r"\bgr[ea]y\b|\bgris\b|melange|\bheather\b|\bcharcoal\b|\bgrafito\b|\bplomo\b|\bsilver\b"),
    ("Azul", r"\bblue\b|\bazul\b|\bnavy\b|\bmarino\b|\bindigo\b|\bcobalt|\bceleste\b|\bdenim\b|\broyal\b"),
    ("Rojo/Burdeo", r"\bred\b|\broj[oa]\b|burdeo|burgundy|\bvino\b|\bwine\b|maroon|\bcherry\b|bordo"),
    ("Rosado", r"\bpink\b|\brosad[oa]\b|\brosa\b|fucsia|\bblush\b"),
    ("Verde", r"\bgreen\b|\bverde\b|\bolive\b|\boliva\b|\barmy\b|\bmilitar\b|\bsage\b|\bforest\b"),
    ("Café/Beige", r"\bbrown\b|\bcafe\b|chocolate|\bcamel\b|\bbeige\b|\btan\b|\bcaqui\b|\bkhaki\b|\bmocha\b|\bsand\b|\barena\b|\bcoffee\b|\btierra\b|\bmoca\b|\bcognac\b|\btaupe\b"),
    ("Amarillo", r"\byellow\b|\bamarill[oa]\b|\bmostaza\b|\bmustard\b"),
    ("Naranjo", r"\borange\b|\bnaranj[oa]\b"),
    ("Morado", r"\bpurple\b|\bmorad[oa]\b|\blila\b|\blavender\b|\bviolet"),
]

SIZE_MAP = {"XXS": "XS", "2XL": "XXL", "3XL": "XXXL", "U": "Única", "UNICA": "Única", "ÚNICA": "Única",
            "TALLA UNICA": "Única", "TALLA ÚNICA": "Única", "OS": "Única", "ONE SIZE": "Única",
            "STD": "Única", "ESTANDAR": "Única", "ESTÁNDAR": "Única", "DEFAULT TITLE": "Única", "ALL": "Única"}

def norm_size(s):
    t = str(s).strip().upper()
    m = re.match(r"^\d+\s*/\s*([A-Z]+)$", t)
    if m:
        t = m.group(1)
    if t.startswith("TALLA ") and t not in SIZE_MAP:
        t = t[6:]
    t = SIZE_MAP.get(t, t)
    return t if len(t) <= 6 else None

def category(title, ptype):
    h = norm(f"{title} {ptype}")
    for name, rx in CATS:
        if re.search(rx, h):
            return name
    return "Accesorios"

def colors(text):
    h = norm(text)
    return [n for n, rx in COLORS if re.search(rx, h)]

def is_size_option(name):
    return bool(re.search(r"talla|size|tamano", norm(name)))

def is_color_option(name):
    return bool(re.search(r"color|colour", norm(name)))

def img_url(src):
    if not src:
        return None
    sep = "&" if "?" in src else "?"
    return f"{src}{sep}width={IMG_WIDTH}"

# ---------- normalización de un producto Shopify ----------
def from_shopify(p, store):
    title = p.get("title") or ""
    if re.search(EXCLUDE, norm(title)):
        return None
    variants = p.get("variants") or []
    if not variants:
        return None
    opts = p.get("options") or []
    size_idx = next((i for i, o in enumerate(opts) if is_size_option(o.get("name", ""))), None)
    color_idx = next((i for i, o in enumerate(opts) if is_color_option(o.get("name", ""))), None)

    avail = [v for v in variants if v.get("available")]
    pool = avail or variants
    cheapest = min(pool, key=lambda v: float(v.get("price") or 0))
    price = int(float(cheapest.get("price") or 0))
    if price <= 0:
        return None
    ca = cheapest.get("compare_at_price")
    ca = int(float(ca)) if ca not in (None, "", "0", "0.00") else None
    if ca is not None and ca <= price:
        ca = None

    if size_idx is not None:
        sizes = []
        for v in avail:
            s = norm_size(v.get(f"option{size_idx + 1}"))
            if s and s not in sizes:
                sizes.append(s)
    else:
        sizes = ["Única"] if avail else []

    color_text = f"{title} {p.get('handle', '').replace('-', ' ')}"
    if color_idx is not None:
        color_text += " " + " ".join(map(str, opts[color_idx].get("values") or []))
    cols = colors(color_text)

    images = p.get("images") or []
    cat = category(title, p.get("product_type") or "")
    item = {
        "brand": store["brand"], "title": title, "cat": cat, "price": price, "compare_at": ca,
        "sizes": sizes, "available": bool(avail), "colors": cols,
        "image": img_url(images[0].get("src")) if images else None,
        "url": f"https://{store['domain']}/products/{p.get('handle')}",
        "published": (p.get("published_at") or "")[:10],
    }
    item["search"] = norm(" ".join([item["brand"], title, cat, " ".join(cols), p.get("product_type") or "", " ".join(p.get("tags") or [])[:200]]))
    return item

def fetch_store(store):
    items, seen = [], set()
    for page in range(1, MAX_PAGES + 1):
        url = f"https://{store['domain']}/products.json?limit=250&page={page}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (radar-streetwear catalog)", "Accept": "application/json"})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    products = json.load(r).get("products", [])
                break
            except Exception as e:
                if attempt == 2:
                    raise
                time.sleep(3 * (attempt + 1))
        if not products:
            break
        for p in products:
            it = from_shopify(p, store)
            if it and it["url"] not in seen:
                seen.add(it["url"])
                items.append(it)
        time.sleep(1)
    return items

def main():
    stores = json.loads((ROOT / "stores.json").read_text(encoding="utf-8"))
    out_path = ROOT / "data.json"
    previous = {}
    if out_path.exists():
        old = json.loads(out_path.read_text(encoding="utf-8"))
        for it in old.get("items", []):
            previous.setdefault(it["brand"], []).append(it)

    items, report = [], []
    for s in stores:
        try:
            got = fetch_store(s)
            items += got
            report.append(f"{s['brand']}: {len(got)}")
        except Exception as e:
            # si una tienda falla, se conservan sus productos de la corrida anterior
            kept = previous.get(s["brand"], [])
            items += kept
            report.append(f"{s['brand']}: ERROR ({e}); se mantienen {len(kept)} del día anterior")

    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-3)))
    data = {
        "updated": now.strftime("%d-%m-%Y %H:%M"),
        "stores": [{"brand": s["brand"], "url": f"https://{s['domain']}", "instagram": s.get("instagram")} for s in stores],
        "items": items,
    }
    out_path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("\n".join(report))
    print(f"Total: {len(items)} prendas")

if __name__ == "__main__":
    main()

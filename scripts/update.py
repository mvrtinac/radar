"""Actualiza data.json con el catálogo de cada tienda Shopify listada en stores.json.

Uso:  python scripts/update.py
Lo corre GitHub Actions todos los días (.github/workflows/update.yml).
Para agregar una tienda basta con sumar una línea en stores.json
("platform": "shopify" por defecto, "woocommerce", o "sitemap" para Jumpseller y
otras plataformas: lee el mapa del sitio y la ficha de cada producto).
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
EXCLUDE = r"^prueba|\bcd\b|vinilo|vinyl|gift ?card|tarjeta de regalo|giftcard|espejo|por mayor|mayorista"

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

# ---------- tiendas WooCommerce (API pública "Store API") ----------
def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (radar-streetwear catalog)", "Accept": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception:
            if attempt == 2:
                raise
            time.sleep(3 * (attempt + 1))

def from_woo(p, store):
    title = re.sub(r"<[^>]+>", "", p.get("name") or "").strip()
    if re.search(EXCLUDE, norm(title)):
        return None
    pr = p.get("prices") or {}
    div = 10 ** int(pr.get("currency_minor_unit") or 0)
    try:
        price = int(int(pr.get("price") or 0) / div)
        regular = int(int(pr.get("regular_price") or 0) / div)
    except ValueError:
        return None
    if price <= 0:
        return None
    ca = regular if regular > price else None
    avail = bool(p.get("is_in_stock"))
    attrs = p.get("attributes") or []
    size_attr = next((a for a in attrs if is_size_option(a.get("name", ""))), None)
    color_attr = next((a for a in attrs if is_color_option(a.get("name", ""))), None)
    sizes = []
    if avail:
        if size_attr:
            # la API lista las tallas que ofrece el producto (no el stock por talla)
            for t in size_attr.get("terms") or []:
                s = norm_size(t.get("name"))
                if s and s not in sizes:
                    sizes.append(s)
        else:
            sizes = ["Única"]
    color_text = f"{title} {p.get('slug', '').replace('-', ' ')}"
    if color_attr:
        color_text += " " + " ".join(t.get("name", "") for t in color_attr.get("terms") or [])
    cols = colors(color_text)
    imgs = p.get("images") or []
    cats = " ".join(c.get("name", "") for c in p.get("categories") or [])
    cat = category(title, cats)
    item = {
        "brand": store["brand"], "title": title, "cat": cat, "price": price, "compare_at": ca,
        "sizes": sizes, "available": avail, "colors": cols,
        "image": imgs[0].get("src") if imgs else None,
        "url": store["url_template"].format(slug=p.get("slug")) if store.get("url_template") else p.get("permalink"),
        "published": "",
    }
    item["search"] = norm(" ".join([store["brand"], title, cat, " ".join(cols), cats]))
    return item

def fetch_woo(store):
    items, seen = [], set()
    for page in range(1, MAX_PAGES + 1):
        api = store.get("api_domain") or store["domain"]
        products = get_json(f"https://{api}/wp-json/wc/store/v1/products?per_page=100&page={page}")
        if not products:
            break
        for p in products:
            it = from_woo(p, store)
            if it and it["url"] and it["url"] not in seen:
                seen.add(it["url"])
                items.append(it)
        if len(products) < 100:
            break
        time.sleep(1)
    return items

# ---------- tiendas Jumpseller u otras: mapa del sitio + ficha de cada producto ----------
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}

def get_text(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")

def sitemap_urls(url, depth=0):
    xml = get_text(url)
    locs = [html_unescape(u.strip()) for u in re.findall(r"<loc>(.*?)</loc>", xml, re.S)]
    if "<sitemapindex" in xml and depth < 2:
        out = []
        for sm in locs:
            if re.search(r"product|producto|sitemap", sm, re.I):
                try:
                    out += sitemap_urls(sm, depth + 1)
                except Exception:
                    pass
        return out
    return locs

def html_unescape(s):
    import html
    return html.unescape(s)

def meta(htmltext, prop):
    m = re.search(r'<meta[^>]+(?:property|name)=["\']' + re.escape(prop) + r'["\'][^>]*content=["\']([^"\']*)', htmltext)
    if not m:
        m = re.search(r'<meta[^>]+content=["\']([^"\']*)["\'][^>]*(?:property|name)=["\']' + re.escape(prop) + r'["\']', htmltext)
    return html_unescape(m.group(1)) if m else None

def ld_product(htmltext):
    for block in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', htmltext, re.S):
        try:
            data = json.loads(block.strip())
        except Exception:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            d = stack.pop()
            if isinstance(d, dict):
                if d.get("@type") == "Product" or (isinstance(d.get("@type"), list) and "Product" in d["@type"]):
                    return d
                stack += [v for v in d.get("@graph", [])] if isinstance(d.get("@graph"), list) else []
            elif isinstance(d, list):
                stack += d
    return None

def num(v):
    try:
        return int(float(str(v).replace(",", "")))
    except Exception:
        return None

def from_page(url, htmltext, store):
    ld = ld_product(htmltext) or {}
    title = ld.get("name") or meta(htmltext, "og:title") or ""
    title = html_unescape(title).strip()
    if not title or re.search(EXCLUDE, norm(title)):
        return None
    offers = ld.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    price = num(meta(htmltext, "product:price:amount")) or num(offers.get("price")) or num(offers.get("lowPrice"))
    if not price:
        return None   # no es una página de producto
    original = num(meta(htmltext, "product:original_price:amount"))
    ca = original if original and original > price else None
    avail_txt = (meta(htmltext, "product:availability") or str(offers.get("availability") or "")).lower()
    avail = ("instock" in avail_txt.replace(" ", "")) or avail_txt in ("in stock", "available")
    sizes = []
    if avail:
        m = re.search(r'"options"\s*:\s*(\[\{.*?\}\])\s*,\s*"option_types"', htmltext, re.S)
        if m:
            try:
                for o in json.loads(m.group(1)):
                    if is_size_option(o.get("name", "")):
                        for v in o.get("values") or []:
                            s = norm_size(v.get("name"))
                            if s and s not in sizes:
                                sizes.append(s)
            except Exception:
                pass
        if not sizes:
            sizes = ["Única"]
    image = ld.get("image")
    if isinstance(image, list):
        image = image[0] if image else None
    if isinstance(image, dict):
        image = image.get("url")
    image = image or meta(htmltext, "og:image")
    cat = category(title, str(ld.get("category") or ""))
    cols = colors(f"{title} {url.rsplit('/', 1)[-1].replace('-', ' ')}")
    item = {
        "brand": store["brand"], "title": title, "cat": cat, "price": price, "compare_at": ca,
        "sizes": sizes, "available": avail, "colors": cols, "image": image,
        "url": url.split("?")[0], "published": "",
    }
    item["search"] = norm(" ".join([store["brand"], title, cat, " ".join(cols)]))
    return item

def fetch_sitemap(store):
    base = f"https://{store['domain']}"
    urls = sitemap_urls(store.get("sitemap") or f"{base}/sitemap.xml")
    skip = re.compile(r"/(en|pt|fr)(/|$)|/(cart|carrito|contact|contacto|login|customer|blog|pages?|policies|politicas)(/|$)", re.I)
    seen, items = set(), []
    for u in urls:
        path = u.split(store["domain"], 1)[-1]
        if store["domain"] not in u or path in ("", "/") or skip.search(path) or u in seen:
            continue
        seen.add(u)
        if len(seen) > 600:
            break
        try:
            it = from_page(u, get_text(u), store)
        except Exception:
            continue
        if it:
            items.append(it)
        time.sleep(0.3)
    return items

FETCHERS = {"shopify": fetch_store, "woocommerce": fetch_woo, "sitemap": fetch_sitemap}

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
            got = FETCHERS[s.get("platform", "shopify")](s)
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

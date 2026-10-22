# Radar Streetwear CL

Catálogo personal de prendas de marcas chilenas de streetwear, con filtros por marca, tipo, talla, color, precio y ofertas, y un botón que lleva a la ficha original de cada tienda para comprar.

- **Página:** se publica con GitHub Pages desde la rama `main` (raíz).
- **Datos:** `data.json`, generado por `scripts/update.py` a partir del catálogo público (`/products.json`) de cada tienda Shopify listada en `stores.json`.
- **Actualización:** GitHub Actions corre el script todos los días (y cada vez que cambia `stores.json`). Para actualizar a mano: pestaña *Actions → Actualizar catálogo → Run workflow*.
- **Agregar una tienda Shopify:** sumar una línea a `stores.json` con `brand`, `domain` e `instagram`.

Solo contiene datos públicos de productos de las tiendas. No usa base de datos ni claves.

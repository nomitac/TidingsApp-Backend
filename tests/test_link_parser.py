import httpx

from app.link_parser import parse_price_cents, parse_product, store_for_url

JSON_LD = """<html><head><title>Ignored title</title>
<meta property="og:title" content="OG should lose">
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[{"@type":"BreadcrumbList"},
 {"@type":"Product","name":"Diptyque Baies Candle &amp; Co","image":["https://cdn.shop/img/candle.jpg"],
  "color":"Ivory","size":"190 g",
  "offers":[{"@type":"Offer","price":"","priceCurrency":"USD"},{"@type":"Offer","price":"78.00","priceCurrency":"usd"}]}]}
</script></head><body></body></html>"""

OG_ONLY = """<html><head>
<meta content="Handmade Mug" property="og:title" />
<meta property="og:image" content="/images/mug.png">
<meta property="product:price:amount" content="1,299.50">
<meta property="product:price:currency" content="EUR">
</head></html>"""

TITLE_ONLY = "<html><head><title>  Cozy   Socks | Small Shop </title></head></html>"


def test_json_ld_product_with_offer_list_and_variant():
    r = parse_product(JSON_LD, "https://www.etsy.com/listing/1")
    assert r["ok"] is True
    assert r["title"] == "Diptyque Baies Candle & Co"
    assert r["image_url"] == "https://cdn.shop/img/candle.jpg"
    assert (r["price_cents"], r["currency"]) == (7800, "USD")
    assert r["variant"] == "Color: Ivory · Size: 190 g"
    assert r["store"] == "Etsy"


def test_og_only_with_relative_image():
    r = parse_product(OG_ONLY, "https://tiny-pottery.myshopify.com/products/mug")
    assert r["ok"] and r["title"] == "Handmade Mug"
    assert r["image_url"] == "https://tiny-pottery.myshopify.com/images/mug.png"
    assert (r["price_cents"], r["currency"]) == (129950, "EUR")
    assert r["store"] == "tiny-pottery.myshopify.com"


def test_title_only():
    r = parse_product(TITLE_ONLY, "https://smallshop.com/socks")
    assert r["ok"] and r["title"] == "Cozy Socks | Small Shop"
    assert r["price_cents"] is None and r["image_url"] == ""


def test_garbage_is_not_ok():
    r = parse_product("<<<not html at all>>> {broken json", "https://www.amazon.com/dp/B000")
    assert r["ok"] is False and r["error"] and r["store"] == "Amazon"
    assert parse_product("", "https://target.com/p")["store"] == "Target"


def test_store_names_and_prices():
    assert store_for_url("https://www.bestbuy.com/site/x") == "Best Buy"
    assert store_for_url("https://amazon.co.uk/dp/x") == "Amazon"
    assert parse_price_cents("$1,299.99") == 129999
    assert parse_price_cents("1.299,99 €") == 129999
    assert parse_price_cents(19.9) == 1990
    assert parse_price_cents("abc") is None


def test_import_endpoint_with_mock_transport(app, make_user):
    u = make_user()

    def handler(request: httpx.Request):
        if "fail" in request.url.host:
            return httpx.Response(503)
        return httpx.Response(200, text=JSON_LD, headers={"content-type": "text/html"})

    app.state.http_transport = httpx.MockTransport(handler)
    ok = u.post("/v1/import-link", {"url": "https://www.etsy.com/listing/1"}).json()
    assert ok["ok"] and ok["price_cents"] == 7800
    bad = u.post("/v1/import-link", {"url": "https://fail.target.com/p/1"})
    assert bad.status_code == 200 and bad.json()["ok"] is False and bad.json()["store"] == "Target"
    assert u.post("/v1/import-link", {"url": "ftp://x"}).status_code == 422


def test_import_blocks_private_hosts(app, make_user):
    u = make_user()
    app.state.http_transport = None
    r = u.post("/v1/import-link", {"url": "http://127.0.0.1:8000/health"}).json()
    assert r["ok"] is False

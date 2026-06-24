import hashlib
import json
import os
import time
from datetime import datetime, timezone
from urllib.request import Request, urlopen


ENDPOINT = "https://open-api.affiliate.shopee.com.br/graphql"

PRODUCT_OFFER_QUERY = """
query ProductOffers($page: Int!, $limit: Int!) {
  productOfferV2(listType: 2, page: $page, limit: $limit) {
    nodes {
      itemId
      commissionRate
      commission
      sales
      priceMax
      priceMin
      productCatIds
      ratingStar
      priceDiscountRate
      imageUrl
      productName
      shopId
      shopName
      productLink
      offerLink
      periodStartTime
      periodEndTime
    }
    pageInfo {
      page
      limit
      hasNextPage
    }
  }
}
""".strip()


class ShopeeApiError(RuntimeError):
    pass


def _credentials() -> tuple[str, str]:
    app_id = os.environ.get("SHOPEE_APP_ID", "").strip()
    secret = os.environ.get("SHOPEE_API_SECRET", "").strip()
    if not app_id or not secret:
        raise ShopeeApiError("Configure SHOPEE_APP_ID e SHOPEE_API_SECRET.")
    return app_id, secret


def _payload(page: int, limit: int) -> bytes:
    body = {
        "query": PRODUCT_OFFER_QUERY,
        "operationName": "ProductOffers",
        "variables": {"page": page, "limit": limit},
    }
    return json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _authorization(app_id: str, secret: str, timestamp: int, payload: bytes) -> str:
    signature_source = app_id.encode("utf-8") + str(timestamp).encode("ascii") + payload + secret.encode("utf-8")
    signature = hashlib.sha256(signature_source).hexdigest()
    return f"SHA256 Credential={app_id}, Timestamp={timestamp}, Signature={signature}"


def request_product_page(page: int, limit: int = 100) -> dict:
    app_id, secret = _credentials()
    payload = _payload(page, max(1, min(limit, 500)))
    timestamp = int(time.time())
    request = Request(
        ENDPOINT,
        data=payload,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": _authorization(app_id, secret, timestamp, payload),
            "User-Agent": "MegaDescontos/1.0",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
    except Exception as error:
        raise ShopeeApiError(f"Falha ao consultar a API da Shopee: {error}") from error

    errors = result.get("errors") or []
    if errors:
        messages = []
        for error in errors:
            detail = error.get("extensions", {}).get("message") or error.get("message") or "Erro desconhecido"
            messages.append(str(detail))
        raise ShopeeApiError("; ".join(messages))

    connection = (result.get("data") or {}).get("productOfferV2")
    if not isinstance(connection, dict):
        raise ShopeeApiError("A API da Shopee nao retornou productOfferV2.")
    return connection


def _number(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _expires_at(value) -> str:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return ""
    if timestamp <= 0:
        return ""
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def infer_category(title: str) -> str:
    normalized = title.casefold()
    category_keywords = (
        ("Celulares", ("celular", "smartphone", "iphone", "galaxy", "redmi")),
        ("Informatica", ("notebook", "computador", "monitor", "teclado", "mouse", "ssd")),
        ("Eletronicos", ("fone", "headset", "smartwatch", "caixa de som", "camera")),
        ("Casa e Cozinha", ("cozinha", "air fryer", "cafeteira", "panela", "organizador")),
        ("Beleza", ("perfume", "maquiagem", "batom", "shampoo", "skincare")),
        ("Moda", ("camisa", "camiseta", "calca", "vestido", "tenis", "sandalia")),
        ("Esportes", ("academia", "fitness", "esporte", "halter", "bicicleta")),
        ("Livros", ("livro", "box de livros")),
        ("Brinquedos", ("brinquedo", "boneca", "lego", "carrinho infantil")),
        ("Automotivo", ("automotivo", "carro", "moto", "pneu")),
        ("Ferramentas", ("furadeira", "parafusadeira", "ferramenta", "chave")),
    )
    for category, keywords in category_keywords:
        if any(keyword in normalized for keyword in keywords):
            return category
    return "Ofertas"


def normalize_product(node: dict) -> dict | None:
    title = str(node.get("productName") or "").strip()
    current_price = _number(node.get("priceMin"))
    discount = int(_number(node.get("priceDiscountRate")))
    offer_link = str(node.get("offerLink") or "").strip()
    product_link = str(node.get("productLink") or "").strip()
    image = str(node.get("imageUrl") or "").strip()
    if not title or current_price <= 0 or discount <= 0 or discount >= 100:
        return None
    if not offer_link.startswith("https://") or not image.startswith("https://"):
        return None

    old_price = round(current_price / (1 - discount / 100), 2)
    return {
        "id": f"shopee-{node.get('shopId')}-{node.get('itemId')}",
        "title": title,
        "store": "Shopee",
        "category": infer_category(title),
        "url": product_link or offer_link,
        "affiliateUrl": offer_link,
        "oldPrice": old_price,
        "currentPrice": current_price,
        "image": image,
        "expiresAt": _expires_at(node.get("periodEndTime")),
        "sourceType": "shopee_open_api",
    }


def fetch_product_offers(max_pages: int = 2, limit: int = 100) -> list[dict]:
    products = []
    seen = set()
    for page in range(1, max(1, max_pages) + 1):
        connection = request_product_page(page, limit)
        for node in connection.get("nodes") or []:
            product = normalize_product(node)
            if not product or product["id"] in seen:
                continue
            products.append(product)
            seen.add(product["id"])
        if not (connection.get("pageInfo") or {}).get("hasNextPage"):
            break
    return products

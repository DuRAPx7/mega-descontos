from datetime import datetime, timezone
from urllib.parse import unquote, urlparse


PLACEHOLDER_MARKERS = (
    "seu-codigo",
    "seucodigo",
    "seu_id",
    "seu-id",
    "produto-exemplo",
    "exemplo-",
    "example.com",
)
STOCK_IMAGE_HOSTS = (
    "images.unsplash.com",
    "pexels.com",
    "pixabay.com",
)


def parse_datetime(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def validate_url(value: object, *, image: bool = False) -> list[str]:
    raw_value = str(value or "").strip()
    if not raw_value:
        return ["URL ausente"]

    normalized = unquote(raw_value).lower()
    parsed = urlparse(raw_value)
    errors = []

    if parsed.scheme != "https" or not parsed.netloc:
        errors.append("a URL precisa ser HTTPS")
    if any(marker in normalized for marker in PLACEHOLDER_MARKERS):
        errors.append("a URL ainda contem codigo ou produto de exemplo")
    if not image and parsed.path in {"", "/"}:
        errors.append("use o link do produto, nao a pagina inicial da loja")
    if image and any(host in parsed.netloc.lower() for host in STOCK_IMAGE_HOSTS):
        errors.append("use a imagem oficial do produto, nao uma foto generica")

    return errors


def validate_offer(offer: object) -> list[str]:
    if not isinstance(offer, dict):
        return ["a oferta precisa ser um objeto"]

    errors = []
    for field, label in (("title", "produto"), ("store", "loja"), ("category", "categoria")):
        value = str(offer.get(field) or "").strip()
        if not value:
            errors.append(f"{label} ausente")
        elif "<" in value or ">" in value:
            errors.append(f"{label} contem caracteres invalidos")

    if offer.get("id") is None:
        errors.append("identificador ausente")

    try:
        old_price = float(offer.get("oldPrice"))
        current_price = float(offer.get("currentPrice"))
        if old_price <= 0 or current_price <= 0:
            errors.append("os precos precisam ser maiores que zero")
        elif current_price >= old_price:
            errors.append("o preco atual precisa ser menor que o preco antigo")
    except (TypeError, ValueError):
        errors.append("precos invalidos")

    errors.extend(f"link de afiliado: {error}" for error in validate_url(offer.get("affiliateUrl")))
    errors.extend(f"imagem: {error}" for error in validate_url(offer.get("image"), image=True))

    expires_at = offer.get("expiresAt")
    if expires_at:
        parsed_expiration = parse_datetime(expires_at)
        if not parsed_expiration:
            errors.append("data de encerramento invalida")
        elif parsed_expiration <= datetime.now(timezone.utc):
            errors.append("a oferta ja terminou")

    return errors


def partition_valid_offers(offers: list[dict]) -> tuple[list[dict], list[dict]]:
    valid = []
    rejected = []
    for index, offer in enumerate(offers):
        errors = validate_offer(offer)
        if errors:
            rejected.append(
                {
                    "index": index,
                    "title": str(offer.get("title") or "Oferta sem titulo") if isinstance(offer, dict) else "Oferta invalida",
                    "errors": errors,
                }
            )
        else:
            valid.append(offer)
    return valid, rejected

"""Catégories, sous-catégories (= salons de monitor) et abonnements.

Chaque sous-catégorie = 1 salon Discord + 1 recherche Vinted.
`params` = paramètres envoyés à l'API Vinted :
  - search_text : mots-clés
  - catalog_ids : ID de catégorie Vinted (vérifie-les : ouvre une catégorie sur vinted.fr,
                  l'ID est dans l'URL `catalog[]=XXXX`)
  - brand_ids, size_ids, status_ids, price_from, price_to ...

Ajoute/retire ce que tu veux ici puis relance `/admin setup`.
"""

CATEGORIES: dict[str, dict] = {
    "femmes": {
        "label": "👗 Femmes",
        "subs": {
            "femmes-vetements": {"label": "Vêtements femme", "params": {"catalog_ids": "4"}},
            "femmes-chaussures": {"label": "Chaussures femme", "params": {"catalog_ids": "16"}},
            "femmes-sacs": {"label": "Sacs", "params": {"catalog_ids": "19"}},
            "femmes-accessoires": {"label": "Accessoires femme", "params": {"catalog_ids": "1187"}},
        },
    },
    "hommes": {
        "label": "👔 Hommes",
        "subs": {
            "hommes-vetements": {"label": "Vêtements homme", "params": {"catalog_ids": "2050"}},
            "hommes-chaussures": {"label": "Chaussures homme", "params": {"catalog_ids": "1231"}},
            "hommes-accessoires": {"label": "Accessoires homme", "params": {"catalog_ids": "82"}},
        },
    },
    "enfants": {
        "label": "🧸 Enfants",
        "subs": {
            "enfants-tout": {"label": "Enfants", "params": {"catalog_ids": "1193"}},
            "lego": {"label": "LEGO", "params": {"search_text": "lego"}},
        },
    },
    "marques": {
        "label": "🔥 Streetwear",
        "subs": {
            "nike": {"label": "Nike", "params": {"search_text": "nike"}},
            "adidas": {"label": "Adidas", "params": {"search_text": "adidas"}},
            "jordan": {"label": "Jordan", "params": {"search_text": "jordan"}},
            "ralph-lauren": {"label": "Ralph Lauren", "params": {"search_text": "ralph lauren"}},
            "lacoste": {"label": "Lacoste", "params": {"search_text": "lacoste"}},
            "the-north-face": {"label": "The North Face", "params": {"search_text": "the north face"}},
            "carhartt": {"label": "Carhartt", "params": {"search_text": "carhartt"}},
            "stussy": {"label": "Stüssy", "params": {"search_text": "stussy"}},
        },
    },
    "tech": {
        "label": "🎮 Tech & Gaming",
        "subs": {
            "ps5": {"label": "PS5", "params": {"search_text": "ps5"}},
            "nintendo-switch": {"label": "Nintendo Switch", "params": {"search_text": "nintendo switch"}},
            "iphone": {"label": "iPhone", "params": {"search_text": "iphone"}},
            "airpods": {"label": "AirPods", "params": {"search_text": "airpods"}},
            "pokemon": {"label": "Cartes Pokémon", "params": {"search_text": "carte pokemon"}},
        },
    },
    "luxe": {
        "label": "💎 Luxe",
        "subs": {
            "stone-island": {"label": "Stone Island", "params": {"search_text": "stone island"}},
            "moncler": {"label": "Moncler", "params": {"search_text": "moncler"}},
            "arcteryx": {"label": "Arc'teryx", "params": {"search_text": "arcteryx"}},
            "cp-company": {"label": "C.P. Company", "params": {"search_text": "cp company"}},
            "canada-goose": {"label": "Canada Goose", "params": {"search_text": "canada goose"}},
        },
    },
    "pepites": {
        "label": "💰 Pépites (petits prix)",
        "subs": {
            "nike-moins-15": {"label": "Nike -15€", "params": {"search_text": "nike", "price_to": "15"}},
            "ralph-moins-15": {"label": "Ralph Lauren -15€", "params": {"search_text": "ralph lauren", "price_to": "15"}},
            "tnf-moins-30": {"label": "TNF -30€", "params": {"search_text": "the north face", "price_to": "30"}},
            "stone-moins-60": {"label": "Stone Island -60€", "params": {"search_text": "stone island", "price_to": "60"}},
        },
    },
}

# Ordre = rang (du plus bas au plus haut). Le prix sert de prix par défaut (30 jours)
# et au calcul pro-rata quand quelqu'un upgrade.
PLANS: dict[str, dict] = {
    "starter": {
        "label": "Starter",
        "emoji": "🥉",
        "price": 9.99,
        "color": 0xCD7F32,
        "categories": ["femmes", "hommes", "enfants"],
    },
    "pro": {
        "label": "Pro",
        "emoji": "🥈",
        "price": 19.99,
        "color": 0xC0C0C0,
        "categories": ["femmes", "hommes", "enfants", "marques", "tech"],
    },
    "elite": {
        "label": "Elite",
        "emoji": "🥇",
        "price": 34.99,
        "color": 0xFFD700,
        "categories": ["femmes", "hommes", "enfants", "marques", "tech", "luxe", "pepites"],
    },
}


def plan_rank(plan_key: str) -> int:
    keys = list(PLANS)
    return keys.index(plan_key) if plan_key in keys else -1


def iter_feeds():
    """Yield (feed_key, category_key, sub_dict) pour chaque sous-catégorie."""
    for cat_key, cat in CATEGORIES.items():
        for feed_key, sub in cat["subs"].items():
            yield feed_key, cat_key, sub


def plans_for_category(cat_key: str) -> list[str]:
    return [k for k, p in PLANS.items() if cat_key in p["categories"]]

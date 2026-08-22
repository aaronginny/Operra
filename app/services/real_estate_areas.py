"""Chennai area coordinates and area-matching primitives.

Ported verbatim from DealKnot's api/areaCoords.js — same keys, same lat/lng,
same normalisation and Haversine maths, so a match found by the Node app is
found identically here.

Keys are lowercase with the city suffix stripped, e.g. "anna nagar" matches
"Anna Nagar, Chennai". Areas that are NOT in this map are still usable: the
matching engine falls back to exact string comparison for them, which is what
the original did.
"""

import math
import re

# area key -> (latitude, longitude); accuracy approximately 500m
CHENNAI_COORDS: dict[str, tuple[float, float]] = {
    # -- North Chennai --
    "manali": (13.1655, 80.2608),
    "manali new town": (13.1684, 80.2592),
    "manali old town": (13.1622, 80.258),
    "minjur": (13.253, 80.256),
    "ennore": (13.214, 80.322),
    "kathivakkam": (13.2104, 80.3137),
    "redhills": (13.1913, 80.1854),
    "padiyanallur": (13.2021, 80.1765),
    "puzhal": (13.1829, 80.2175),
    "madhavaram": (13.1564, 80.2349),
    "madhavaram milk colony": (13.1634, 80.2406),
    "erukkanchery": (13.1471, 80.2421),
    "thiruvottiyur": (13.1674, 80.3003),
    "wimco nagar": (13.1459, 80.2961),
    "veppamoodu": (13.165, 80.31),
    "tondiarpet": (13.1175, 80.2977),
    "royapuram": (13.1175, 80.2957),
    "washermanpet": (13.1108, 80.2886),
    "new washermanpet": (13.12, 80.295),
    "korukkupet": (13.1159, 80.2887),
    "moolakadai": (13.141, 80.262),
    "kodungaiyur": (13.1506, 80.276),
    "mathur": (13.1397, 80.227),
    "perambur": (13.1161, 80.2355),
    "perambur barracks": (13.1225, 80.2405),
    "vyasarpadi": (13.1289, 80.275),
    "ayanavaram": (13.1167, 80.2526),
    "aynavaram": (13.1167, 80.2526),
    "periyar nagar": (13.1143, 80.23),
    "mukundapur": (13.11, 80.214),
    "thiruvika nagar": (13.1115, 80.205),
    "thiru vi ka nagar": (13.1115, 80.205),
    "t.v.k. nagar": (13.1105, 80.2047),
    "villivakkam": (13.1085, 80.2134),
    "kolathur": (13.1267, 80.2218),
    "korattur": (13.1141, 80.1851),
    "ambattur": (13.1143, 80.1549),
    "ambattur industrial estate": (13.1176, 80.1557),
    "ambattur ot": (13.112, 80.16),
    "padi": (13.1155, 80.1823),
    "ayyapakkam": (13.13, 80.175),
    "ayappakkam": (13.13, 80.175),
    "avadi": (13.1154, 80.1001),
    "pattabiram": (13.105, 80.111),
    "veppampattu": (13.105, 80.1005),
    "thirumullaivoyal": (13.1315, 80.1453),
    # -- North-West Chennai --
    "poonamallee": (13.0476, 80.1189),
    "vanagaram": (13.084, 80.1514),
    "maduravoyal": (13.0706, 80.1633),
    "alapakkam": (13.0442, 80.1789),
    "mogappair": (13.095, 80.1772),
    "mogappair east": (13.0928, 80.1886),
    "mogappair west": (13.0978, 80.1637),
    "nolambur": (13.0894, 80.1693),
    "nerkundram": (13.0619, 80.1984),
    "koyambedu": (13.0688, 80.1977),
    "arumbakkam": (13.0667, 80.2102),
    "choolaimedu": (13.068, 80.2218),
    "mugalivakkam": (13.0354, 80.1734),
    "gerugambakkam": (13.0243, 80.143),
    "iyyappanthangal": (13.0254, 80.15),
    "ayyappanthangal": (13.0254, 80.15),
    "porur": (13.0357, 80.1558),
    "valasaravakkam": (13.0417, 80.178),
    "virugambakkam": (13.0566, 80.1906),
    "mangadu": (13.0357, 80.1145),
    "sembarambakkam": (13.0553, 80.0949),
    # -- Central-North Chennai --
    "anna nagar": (13.085, 80.2101),
    "anna nagar east": (13.0838, 80.2209),
    "anna nagar tower": (13.087, 80.2065),
    "anna nagar west": (13.0847, 80.2046),
    "kilpauk": (13.0847, 80.227),
    "arjun nagar": (13.0892, 80.2277),
    "ayyavoo colony": (13.0844, 80.2244),
    "shanthi colony": (13.0805, 80.2145),
    "shenoy nagar": (13.0801, 80.2258),
    "thirumangalam": (13.0869, 80.2165),
    "tirumangalam": (13.0869, 80.2165),
    "aminjikarai": (13.072, 80.2318),
    "chetpet": (13.0685, 80.2422),
    "purasaiwalkam": (13.0889, 80.2482),
    "pursaiwalkam": (13.0889, 80.2482),
    "otteri": (13.0851, 80.2538),
    "periyamet": (13.0896, 80.2681),
    "vepery": (13.0834, 80.2604),
    "kellys": (13.0819, 80.2485),
    "egmore": (13.0774, 80.2611),
    "collector nagar": (13.0843, 80.218),
    "cooks road": (13.075, 80.235),
    "rajaji nagar": (13.061, 80.253),
    "raj bhavan road": (13.06, 80.2565),
    "lloyds road": (13.055, 80.2595),
    "harrington road": (13.057, 80.2498),
    "boat club road": (13.056, 80.244),
    "nungambakkam": (13.0569, 80.2425),
    "nungambakkam high road": (13.0555, 80.2462),
    "thousand lights": (13.0567, 80.256),
    "royapettah": (13.0545, 80.265),
    "poes garden": (13.045, 80.2502),
    "gopalapuram": (13.0504, 80.2603),
    "cathedral road": (13.0522, 80.2639),
    "dr radha krishnan salai": (13.0554, 80.258),
    "sardar patel road": (13.048, 80.2544),
    "indira nagar": (13.0505, 80.257),
    "pudupet": (13.0822, 80.2715),
    "park town": (13.0836, 80.2781),
    "sowcarpet": (13.0905, 80.2826),
    "triplicane": (13.0597, 80.2787),
    "kumaran colony": (13.02, 80.2295),
    "moovarasampet": (13.059, 80.212),
    # -- Central Chennai --
    "kk nagar": (13.0505, 80.2046),
    "k.k. nagar": (13.0505, 80.2046),
    "ashok nagar": (13.0481, 80.2169),
    "vadapalani": (13.0521, 80.2121),
    "kodambakkam": (13.0487, 80.2279),
    "saligramam": (13.0484, 80.2),
    "kadambakkam": (13.0484, 80.1965),
    "kasi colony": (13.0508, 80.209),
    "duraisamy nagar": (13.0416, 80.2236),
    "nesapakkam": (13.0415, 80.208),
    "srinivasa nagar": (13.0434, 80.2059),
    "vijaya nagar": (13.0475, 80.2285),
    "vijayanagar": (13.0475, 80.2285),
    "rangarajapuram": (13.0357, 80.2062),
    "jafferkhanpet": (13.0295, 80.2096),
    "west mambalam": (13.0388, 80.2275),
    "east mambalam": (13.0392, 80.2371),
    "mambalam": (13.0388, 80.2275),
    "t. nagar": (13.0418, 80.2341),
    "t.nagar": (13.0418, 80.2341),
    "pondy bazaar": (13.0397, 80.2325),
    "alwarpet": (13.0368, 80.2496),
    "mylapore": (13.0368, 80.2676),
    "teynampet": (13.0373, 80.2498),
    "ttk road": (13.035, 80.257),
    "mandaveli": (13.0206, 80.2581),
    "luz": (13.0311, 80.2656),
    "santhome": (13.0249, 80.2789),
    "kotturpuram": (13.0208, 80.2497),
    "saidapet": (13.0219, 80.2231),
    "west saidapet": (13.0218, 80.213),
    "nandanam": (13.0144, 80.2314),
    "raja annamalai puram": (13.0471, 80.2513),
    "cit nagar": (13.032, 80.2351),
    "cit colony": (13.031, 80.2351),
    "west cit nagar": (13.0305, 80.231),
    "ellis nagar": (13.0374, 80.2218),
    "gandhi nagar": (13.02, 80.1853),
    "roja nagar": (13.025, 80.194),
    "maduvankarai": (13.0045, 80.2065),
    "ramnagar": (13.013, 80.196),
    "ramavaram": (13.0205, 80.1808),
    "ramapuram": (13.026, 80.1852),
    "nandambakkam": (13.0247, 80.173),
    "manapakkam": (13.0188, 80.1759),
    "pakkam": (13.0048, 80.1887),
    "tittu village": (13.02, 80.185),
    "narayanapuram": (12.982, 80.208),
    "unnamalai nagar": (12.982, 80.208),
    "subramaniapuram": (13.01, 80.2062),
    "coding nagar": (13.02, 80.26),
    "mahabhoomi nagar": (13.013, 80.204),
    "lake area": (13.013, 80.2096),
    "lakshmi nagar": (12.9852, 80.1908),
    "royale garden": (12.969, 80.1934),
    "pudur": (13.0305, 80.199),
    "besant avenue": (13.002, 80.273),
    "pacific boulevard": (13.0057, 80.188),
    # -- Inner South Chennai --
    "alandur": (12.9998, 80.2016),
    "ekkattuthangal": (13.0107, 80.2118),
    "guindy": (13.0067, 80.2206),
    "meenambakkam": (12.9909, 80.172),
    "st. thomas mount": (13.0006, 80.1922),
    "adambakkam": (12.9896, 80.201),
    "nanganallur": (12.9906, 80.1927),
    "ullagaram": (12.9789, 80.2),
    "taramani": (12.9778, 80.2447),
    "velachery": (12.9766, 80.2209),
    "gowrivakkam": (12.9714, 80.19),
    "nanmangalam": (12.9631, 80.1748),
    "madipakkam": (12.9639, 80.2058),
    "jalladampet": (12.9639, 80.2),
    "seevaram": (12.9618, 80.16),
    "pallikaranai": (12.935, 80.2128),
    "pallikkaranai": (12.935, 80.2128),
    "kannagi nagar": (12.951, 80.1997),
    "kovilambakkam": (12.9451, 80.181),
    "medavakkam": (12.9236, 80.1862),
    "peerkankaranai": (12.9071, 80.1843),
    "keelkattalai": (12.9406, 80.1617),
    "kilkattalai": (12.9406, 80.1617),
    "kolapakkam": (12.9516, 80.1588),
    "perungudi": (12.9547, 80.2446),
    "thoraipakkam": (12.9332, 80.2366),
    "okkiyam thoraipakkam": (12.9332, 80.2366),
    "okkiyampet": (12.9332, 80.2366),
    "thiruvanmiyur": (12.9838, 80.2686),
    "karapakkam": (12.9209, 80.2299),
    "palavakkam": (12.9196, 80.251),
    "sithalapakkam": (12.9413, 80.1768),
    "perungalathur": (12.923, 80.087),
    "old perungalathur": (12.923, 80.087),
    "pozhichalur": (12.9623, 80.1136),
    "pammal": (12.9582, 80.0977),
    "anakaputhur": (12.9751, 80.0978),
    # -- South-West Chennai --
    "chromepet": (12.9518, 80.1427),
    "pallavaram": (12.9705, 80.1489),
    "old pallavaram": (12.9618, 80.152),
    "zamin pallavaram": (12.96, 80.145),
    "selaiyur": (12.9457, 80.1276),
    "rajakilpakkam": (12.9531, 80.1093),
    "chitlapakkam": (12.9618, 80.1284),
    "sembakkam": (12.9155, 80.1605),
    "mudichur": (12.9124, 80.0893),
    "tambaram": (12.9249, 80.1),
    # -- South Chennai (ECR/OMR corridor) --
    "sholinganallur": (12.901, 80.2279),
    "omr": (12.898, 80.2271),
    "old mahabalipuram road": (12.898, 80.2271),
    "mamallapuram road": (12.88, 80.235),
    "semmanchery": (12.8927, 80.2281),
    "navalur": (12.87, 80.218),
    "navallur": (12.87, 80.218),
    "kazhipattur": (12.8893, 80.2199),
    "kelambakkam": (12.863, 80.2016),
    "thalambur": (12.882, 80.206),
    "siruseri": (12.858, 80.21),
    "padur": (12.854, 80.205),
    "vengaivasal": (12.8996, 80.1855),
    "kundanchavadi": (12.89, 80.23),
    "kottivakkam": (12.898, 80.2664),
    "injambakkam": (12.8775, 80.2533),
    "neelankarai": (12.8618, 80.2502),
    "uthandi": (12.8368, 80.2349),
    "kanathur": (12.8506, 80.2484),
    "panayur": (12.8506, 80.2484),
    "pambadi": (12.87, 80.218),
    "ecr": (12.8636, 80.25),
    "kovalam": (12.8168, 80.2467),
    "muttukadu": (12.8108, 80.2409),
    # -- Far South / Chengalpattu outskirts --
    "vandalur": (12.9289, 80.0796),
    "urapakkam": (12.9009, 80.0657),
    "padappai": (12.8861, 80.0423),
    "singaperumal koil": (12.8246, 80.0284),
    "guduvanchery": (12.8485, 80.0692),
    "kattankulathur": (12.8372, 80.0441),
    "mahindra city": (12.7916, 80.0143),
    "maraimalai nagar": (12.7977, 80.0218),
    "alathur": (12.87, 80.054),
    "chengalpattu": (12.6922, 79.9808),
    "brahmadesam": (12.805, 80.1),
    "yemmoor": (12.9, 80.235),
    "vettuvankulam": (12.9, 80.125),
    "pambadi": (12.87, 80.218),
}


# Matches the JS regex: strips a trailing city/state/country suffix.
_CITY_SUFFIX_RE = re.compile(
    r",\s*(chennai|chengalpattu|kanchipuram|tamil\s*nadu|india)\s*$",
    re.IGNORECASE,
)


def normalize_area_key(area: str | None) -> str:
    """Lowercase, trim, and strip a trailing city suffix for map lookup."""
    return _CITY_SUFFIX_RE.sub("", (area or "").strip().lower()).strip()


def get_coords(area: str | None) -> tuple[float, float] | None:
    """Return (lat, lng) for an area name, or None if it isn't in the map."""
    return CHENNAI_COORDS.get(normalize_area_key(area))


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in km between two lat/lng points."""
    radius_km = 6371
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (
        math.sin(d_lat / 2) * math.sin(d_lat / 2)
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lng / 2)
        * math.sin(d_lng / 2)
    )
    return radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def check_area_match(
    buyer_area: str, seller_area: str, radius_km: float
) -> tuple[str, float] | None:
    """Compare one buyer area against one seller area.

    Returns ("exact", 0.0) when the two area strings are the same,
    ("proximity", distance) when both are in the coordinate map and lie within
    `radius_km` of each other, or None when they don't match at all (including
    when either area is unknown to the map — the original's behaviour).
    """
    ba = (buyer_area or "").strip().lower()
    sa = (seller_area or "").strip().lower()
    if ba == sa:
        return "exact", 0.0

    bc = get_coords(buyer_area)
    sc = get_coords(seller_area)
    if not bc or not sc:
        return None

    distance = haversine_km(bc[0], bc[1], sc[0], sc[1])
    if distance <= radius_km:
        # Rounded to 1dp exactly as the JS did, so the UI badge reads the same.
        return "proximity", round(distance * 10) / 10
    return None

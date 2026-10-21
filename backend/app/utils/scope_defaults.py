"""Built-in starting points for big destinations, used whenever the AI suggestions are unavailable.

For each country or state:  gateway = the best city to land in or start from (usually the capital or the city with the
main airport), inside = well-known places to base a stay in, neighbours = bordering states (states only).
This is a small, hand-checked list of popular destinations, not a complete one. Anything not listed simply has no
built-in suggestions (the traveller can still type a city).
"""

from typing import Any, Dict, List, Optional


def _p(*pairs: str) -> List[Dict[str, str]]:
    """_p("Florence|Art and Renaissance", "Venice|Canals") -> [{'name':..., 'note':...}]"""
    out = []
    for item in pairs:
        name, _, note = item.partition("|")
        out.append({"name": name, "note": note})
    return out


COUNTRIES: Dict[str, Dict[str, Any]] = {
    "italy": {"gateway": "Rome", "note": "capital", "inside": _p("Florence|Art and Renaissance", "Venice|Canals and islands", "Milan|Fashion and the Duomo", "Naples|Pizza and Pompeii nearby", "Bologna|Food capital", "Amalfi|Coast and sea views")},
    "france": {"gateway": "Paris", "note": "capital", "inside": _p("Nice|French Riviera", "Lyon|Food and old town", "Marseille|Port city", "Bordeaux|Wine country", "Strasbourg|Half-timbered old town")},
    "spain": {"gateway": "Madrid", "note": "capital", "inside": _p("Barcelona|Gaudi and beaches", "Seville|Flamenco and palaces", "Valencia|City of Arts and Sciences", "Granada|The Alhambra", "Bilbao|Guggenheim and pintxos")},
    "germany": {"gateway": "Berlin", "note": "capital", "inside": _p("Munich|Bavaria and beer halls", "Frankfurt|Skyline and old town", "Hamburg|Harbour city", "Cologne|The great cathedral", "Dresden|Baroque old town")},
    "united kingdom": {"gateway": "London", "note": "capital", "inside": _p("Edinburgh|Castle and old town", "Manchester|Music and football", "Bath|Roman baths", "York|Medieval walls", "Liverpool|The Beatles and docks")},
    "switzerland": {"gateway": "Zurich", "note": "main airport (capital is Bern)", "inside": _p("Lucerne|Lake and old bridges", "Interlaken|Alps adventures", "Geneva|Lake and old town", "Zermatt|Matterhorn views", "Bern|Capital old town")},
    "netherlands": {"gateway": "Amsterdam", "note": "capital", "inside": _p("Rotterdam|Modern architecture", "Utrecht|Canals and towers", "The Hague|Courts and the coast", "Delft|Blue pottery")},
    "portugal": {"gateway": "Lisbon", "note": "capital", "inside": _p("Porto|Port wine and riverside", "Sintra|Fairytale palaces", "Faro|Algarve beaches", "Coimbra|Historic university")},
    "greece": {"gateway": "Athens", "note": "capital", "inside": _p("Santorini|Sunsets and white villages", "Mykonos|Beaches and nightlife", "Thessaloniki|Food and history", "Heraklion|Crete and Knossos")},
    "turkey": {"gateway": "Istanbul", "note": "main airport (capital is Ankara)", "inside": _p("Antalya|Beaches and old town", "Izmir|Aegean coast", "Ankara|Capital and museums", "Bodrum|Harbour and castle")},
    "austria": {"gateway": "Vienna", "note": "capital", "inside": _p("Salzburg|Mozart and the Alps", "Innsbruck|Mountains in the city", "Hallstatt|Lakeside village", "Graz|Old town")},
    "czech republic": {"gateway": "Prague", "note": "capital", "inside": _p("Brno|Students and castles", "Cesky Krumlov|Storybook town", "Karlovy Vary|Spa town")},
    "japan": {"gateway": "Tokyo", "note": "capital", "inside": _p("Kyoto|Temples and geisha lanes", "Osaka|Street food", "Hiroshima|Peace Memorial", "Nara|Deer and big Buddha", "Hakone|Hot springs and Mount Fuji views")},
    "thailand": {"gateway": "Bangkok", "note": "capital", "inside": _p("Phuket|Beaches", "Chiang Mai|Temples and mountains", "Krabi|Cliffs and islands", "Pattaya|Beach resort")},
    "malaysia": {"gateway": "Kuala Lumpur", "note": "capital", "inside": _p("Penang|Street food and heritage", "Langkawi|Island beaches", "Malacca|Historic port town")},
    "indonesia": {"gateway": "Jakarta", "note": "capital", "inside": _p("Denpasar|Gateway to Bali", "Yogyakarta|Temples and culture", "Bandung|Hills and tea")},
    "vietnam": {"gateway": "Hanoi", "note": "capital", "inside": _p("Ho Chi Minh City|Busy southern hub", "Da Nang|Beaches and bridges", "Hoi An|Lantern old town", "Hue|Imperial city")},
    "united arab emirates": {"gateway": "Dubai", "note": "main airport (capital is Abu Dhabi)", "inside": _p("Abu Dhabi|Grand Mosque", "Sharjah|Museums and culture")},
    "united states": {"gateway": "New York", "note": "main gateway (capital is Washington)", "inside": _p("Washington|Capital and museums", "Los Angeles|Hollywood and beaches", "San Francisco|Golden Gate", "Las Vegas|Shows and desert trips", "Chicago|Architecture", "Miami|Beaches and nightlife")},
    "canada": {"gateway": "Toronto", "note": "main airport (capital is Ottawa)", "inside": _p("Vancouver|Mountains and sea", "Montreal|French-style city", "Ottawa|Capital", "Quebec City|Old walled town", "Calgary|Gateway to the Rockies")},
    "australia": {"gateway": "Sydney", "note": "main airport (capital is Canberra)", "inside": _p("Melbourne|Coffee and street art", "Brisbane|Sunny river city", "Cairns|Gateway to the Reef", "Perth|West coast beaches")},
    "new zealand": {"gateway": "Auckland", "note": "main airport", "inside": _p("Queenstown|Adventure capital", "Wellington|Capital by the harbour", "Christchurch|South Island hub", "Rotorua|Geysers and Maori culture")},
    "egypt": {"gateway": "Cairo", "note": "capital", "inside": _p("Luxor|Temples and tombs", "Aswan|Nile and Nubian villages", "Alexandria|Mediterranean coast", "Sharm El Sheikh|Red Sea diving")},
    "morocco": {"gateway": "Marrakech", "note": "main tourist airport (capital is Rabat)", "inside": _p("Casablanca|Big coastal city", "Fez|Old medina", "Chefchaouen|The blue town", "Rabat|Capital")},
    "south africa": {"gateway": "Johannesburg", "note": "main airport", "inside": _p("Cape Town|Table Mountain and coast", "Durban|Warm beaches")},
    "sri lanka": {"gateway": "Colombo", "note": "main airport", "inside": _p("Kandy|Temple of the Tooth", "Galle|Fort and beaches", "Ella|Hills and tea trains")},
    "nepal": {"gateway": "Kathmandu", "note": "capital", "inside": _p("Pokhara|Lake and mountain views", "Chitwan|Jungle safaris", "Lumbini|Birthplace of Buddha")},
    "maldives": {"gateway": "Male", "note": "capital", "inside": []},
    "mexico": {"gateway": "Mexico City", "note": "capital", "inside": _p("Cancun|Beaches", "Guadalajara|Tequila country", "Oaxaca|Food and crafts")},
    "india": {"gateway": "New Delhi", "note": "capital", "inside": _p("Mumbai|Film city and sea front", "Jaipur|Forts and palaces", "Agra|The Taj Mahal", "Kochi|Backwaters gateway", "Varanasi|Ghats on the Ganges", "Bengaluru|Gardens and cafes")},
}

STATES: Dict[str, Dict[str, Any]] = {
    "rajasthan": {"gateway": "Jaipur", "note": "capital", "inside": _p("Udaipur|Lakes and palaces", "Jodhpur|The blue city", "Jaisalmer|Golden fort and desert", "Pushkar|Holy lake and camel fair", "Bikaner|Forts and camels"), "neighbours": ["Gujarat", "Madhya Pradesh", "Haryana", "Punjab", "Uttar Pradesh"]},
    "kerala": {"gateway": "Kochi", "note": "main airport", "inside": _p("Munnar|Tea hills", "Alleppey|Backwater houseboats", "Thekkady|Spice and wildlife", "Kovalam|Beach", "Kozhikode|Old spice port"), "neighbours": ["Tamil Nadu", "Karnataka"]},
    "himachal pradesh": {"gateway": "Chandigarh", "note": "nearest big airport", "inside": _p("Shimla|Hill station", "Manali|Mountains and snow", "Dharamshala|Monasteries and views", "Kullu|Valley and rafting", "Dalhousie|Quiet hill town"), "neighbours": ["Uttarakhand", "Punjab", "Jammu and Kashmir"]},
    "uttarakhand": {"gateway": "Dehradun", "note": "capital", "inside": _p("Rishikesh|Yoga and rafting", "Haridwar|Ganga aarti", "Mussoorie|Hill station", "Nainital|Lake town"), "neighbours": ["Himachal Pradesh", "Uttar Pradesh"]},
    "maharashtra": {"gateway": "Mumbai", "note": "capital", "inside": _p("Pune|Forts and food", "Nashik|Wine and temples", "Aurangabad|Ajanta and Ellora caves"), "neighbours": ["Gujarat", "Madhya Pradesh", "Karnataka", "Goa"]},
    "tamil nadu": {"gateway": "Chennai", "note": "capital", "inside": _p("Madurai|Meenakshi temple", "Ooty|Hill station", "Kanyakumari|Southern tip", "Coimbatore|Gateway to the Nilgiris"), "neighbours": ["Kerala", "Karnataka", "Andhra Pradesh"]},
    "karnataka": {"gateway": "Bengaluru", "note": "capital", "inside": _p("Mysuru|Palace city", "Hampi|Ancient ruins", "Coorg|Coffee hills", "Gokarna|Quiet beaches", "Udupi|Temples and food"), "neighbours": ["Goa", "Kerala", "Tamil Nadu", "Andhra Pradesh", "Maharashtra"]},
    "uttar pradesh": {"gateway": "Lucknow", "note": "capital", "inside": _p("Varanasi|Ghats on the Ganges", "Agra|The Taj Mahal", "Ayodhya|Temple town", "Prayagraj|Where rivers meet", "Mathura|Krishna's birthplace"), "neighbours": ["Uttarakhand", "Madhya Pradesh", "Rajasthan", "Bihar", "Delhi"]},
    "gujarat": {"gateway": "Ahmedabad", "note": "main airport", "inside": _p("Vadodara|Palaces", "Bhuj|Kutch and the white desert", "Dwarka|Holy coastal town", "Somnath|Seaside temple"), "neighbours": ["Rajasthan", "Maharashtra", "Madhya Pradesh"]},
    "west bengal": {"gateway": "Kolkata", "note": "capital", "inside": _p("Darjeeling|Tea and mountain views", "Siliguri|Gateway to the hills"), "neighbours": ["Sikkim", "Odisha", "Bihar", "Assam", "Jharkhand"]},
    "punjab": {"gateway": "Amritsar", "note": "main airport", "inside": _p("Patiala|Royal heritage", "Ludhiana|Food and markets", "Jalandhar|Sports town"), "neighbours": ["Haryana", "Himachal Pradesh", "Rajasthan", "Jammu and Kashmir"]},
    "madhya pradesh": {"gateway": "Bhopal", "note": "capital", "inside": _p("Indore|Street food", "Gwalior|Fort", "Khajuraho|Temple carvings", "Ujjain|Holy city", "Jabalpur|Marble rocks"), "neighbours": ["Rajasthan", "Gujarat", "Maharashtra", "Uttar Pradesh", "Chhattisgarh"]},
    "sikkim": {"gateway": "Bagdogra", "note": "nearest airport", "inside": _p("Gangtok|Capital and monasteries"), "neighbours": ["West Bengal"]},
    "odisha": {"gateway": "Bhubaneswar", "note": "capital", "inside": _p("Puri|Jagannath temple and beach", "Konark|Sun temple", "Cuttack|Silver filigree"), "neighbours": ["West Bengal", "Andhra Pradesh", "Chhattisgarh", "Jharkhand"]},
    "assam": {"gateway": "Guwahati", "note": "main airport", "inside": _p("Jorhat|Tea gardens", "Tezpur|Hills and river"), "neighbours": ["Meghalaya", "West Bengal", "Arunachal Pradesh"]},
}


def static_scope(kind: str, name: str) -> Optional[Dict[str, Any]]:
    """AI-shaped fallback: {'gateway', 'gateway_note', 'inside': [...], 'neighbours': [...]} or None when not listed."""
    table = COUNTRIES if kind == "country" else STATES if kind == "state" else None
    if table is None:
        return None
    entry = table.get(" ".join(name.split(",")[0].lower().split()))
    if not entry:
        return None
    return {
        "gateway": entry["gateway"],
        "gateway_note": entry.get("note", ""),
        "inside": entry.get("inside", []),
        "neighbours": [{"name": n, "note": ""} for n in entry.get("neighbours", [])],
    }

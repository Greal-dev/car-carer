"""VIN decoder: extract manufacturer, country, and year from VIN."""

# WMI (World Manufacturer Identifier) - first 3 chars of VIN
WMI_MAP = {
    "VF1": ("Renault", "France"), "VF2": ("Renault", "France"), "VF3": ("Peugeot", "France"),
    "VF7": ("Citroen", "France"), "VF8": ("Matra/Talbot", "France"), "VF6": ("Renault Trucks", "France"),
    "VF9": ("Bugatti", "France"), "VR1": ("Dacia", "France/Roumanie"),
    "WBA": ("BMW", "Allemagne"), "WBS": ("BMW M", "Allemagne"), "WDB": ("Mercedes-Benz", "Allemagne"),
    "WDD": ("Mercedes-Benz", "Allemagne"), "WDC": ("Mercedes-Benz", "Allemagne"),
    "WF0": ("Ford", "Allemagne"), "WVW": ("Volkswagen", "Allemagne"), "WVG": ("Volkswagen", "Allemagne"),
    "WAU": ("Audi", "Allemagne"), "WUA": ("Audi Quattro", "Allemagne"),
    "WP0": ("Porsche", "Allemagne"), "W0L": ("Opel", "Allemagne"),
    "ZAR": ("Alfa Romeo", "Italie"), "ZFA": ("Fiat", "Italie"), "ZFF": ("Ferrari", "Italie"),
    "ZHW": ("Lamborghini", "Italie"), "ZLA": ("Lancia", "Italie"), "ZAM": ("Maserati", "Italie"),
    "SAJ": ("Jaguar", "UK"), "SAL": ("Land Rover", "UK"), "SCC": ("Lotus", "UK"),
    "SCF": ("Aston Martin", "UK"), "SFZ": ("McLaren", "UK"),
    "TMB": ("Skoda", "Republique Tcheque"), "TRU": ("Audi Hongrie", "Hongrie"),
    "VSS": ("SEAT", "Espagne"),
    "YV1": ("Volvo", "Suede"), "YS3": ("Saab", "Suede"),
    "1G1": ("Chevrolet", "USA"), "1G2": ("Pontiac", "USA"), "1GC": ("Chevrolet Truck", "USA"),
    "1FA": ("Ford", "USA"), "1FT": ("Ford Truck", "USA"),
    "1HG": ("Honda", "USA"), "1N4": ("Nissan", "USA"),
    "2HG": ("Honda", "Canada"), "2T1": ("Toyota", "Canada"),
    "3FA": ("Ford", "Mexique"), "3VW": ("Volkswagen", "Mexique"),
    "JHM": ("Honda", "Japon"), "JMZ": ("Mazda", "Japon"), "JN1": ("Nissan", "Japon"),
    "JT": ("Toyota", "Japon"), "JS": ("Suzuki", "Japon"),
    "KMH": ("Hyundai", "Coree du Sud"), "KNA": ("Kia", "Coree du Sud"),
    "LVS": ("Ford", "Chine"), "LSJ": ("MG/SAIC", "Chine"),
}

# VIN year code (position 10)
YEAR_CODES = {
    'A': 2010, 'B': 2011, 'C': 2012, 'D': 2013, 'E': 2014, 'F': 2015,
    'G': 2016, 'H': 2017, 'J': 2018, 'K': 2019, 'L': 2020, 'M': 2021,
    'N': 2022, 'P': 2023, 'R': 2024, 'S': 2025, 'T': 2026, 'V': 2027,
    'W': 2028, 'X': 2029, 'Y': 2030,
    '1': 2001, '2': 2002, '3': 2003, '4': 2004, '5': 2005, '6': 2006,
    '7': 2007, '8': 2008, '9': 2009,
}


def decode_vin(vin: str) -> dict:
    """Decode a VIN and return extracted info."""
    vin = vin.strip().upper()
    result = {"vin": vin, "valid": False, "brand": None, "country": None, "year": None}

    if len(vin) != 17:
        result["error"] = "Le VIN doit contenir exactement 17 caracteres"
        return result

    # Check for invalid characters
    invalid = set("IOQ")
    if any(c in invalid for c in vin):
        result["error"] = "Le VIN ne peut pas contenir I, O ou Q"
        return result

    result["valid"] = True

    # WMI lookup (try 3 chars, then 2)
    wmi3 = vin[:3]
    wmi2 = vin[:2]
    if wmi3 in WMI_MAP:
        result["brand"], result["country"] = WMI_MAP[wmi3]
    elif wmi2 in WMI_MAP:
        result["brand"], result["country"] = WMI_MAP[wmi2]

    # Year from position 10
    year_char = vin[9]
    if year_char in YEAR_CODES:
        result["year"] = YEAR_CODES[year_char]

    return result

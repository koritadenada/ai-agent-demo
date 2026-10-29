"""Static reference data for the mock platform: ports, expense taxonomy, agency naming variants."""

# port_id, UN/LOCODE, name, country, region, currency, local price multiplier
PORTS = [
    (1, "NLRTM", "Rotterdam", "Netherlands", "North Europe", "EUR", 1.00),
    (2, "BEANR", "Antwerp", "Belgium", "North Europe", "EUR", 0.96),
    (3, "DEHAM", "Hamburg", "Germany", "North Europe", "EUR", 1.08),
    (4, "GRPIR", "Piraeus", "Greece", "Mediterranean", "EUR", 0.82),
    (5, "ESVLC", "Valencia", "Spain", "Mediterranean", "EUR", 0.88),
    (6, "ITGOA", "Genoa", "Italy", "Mediterranean", "EUR", 0.93),
    (7, "FRMRS", "Marseille", "France", "Mediterranean", "EUR", 0.97),
    (8, "ROCND", "Constanta", "Romania", "Black Sea", "EUR", 0.74),
    (9, "AEJEA", "Jebel Ali", "United Arab Emirates", "Middle East", "USD", 0.91),
    (10, "SGSIN", "Singapore", "Singapore", "Asia", "USD", 1.05),
    (11, "CNSHA", "Shanghai", "China", "Asia", "USD", 0.86),
    (12, "KRPUS", "Busan", "South Korea", "Asia", "USD", 0.90),
    (13, "USHOU", "Houston", "United States", "Americas", "USD", 1.22),
    (14, "BRSSZ", "Santos", "Brazil", "Americas", "USD", 1.10),
    (15, "ZADUR", "Durban", "South Africa", "Africa", "USD", 0.79),
]

ROE_TO_USD = {"EUR": 1.08, "USD": 1.0}

# category_id, name, domain, description, base amount at 25k GT (local currency), scales with GT, always on a DA
CATEGORIES = [
    (1, "Port dues", "port_cost", "Dues charged by the port authority for the vessel's stay", 9000, True, True),
    (2, "Light dues", "port_cost", "Dues for lighthouses and navigation aids", 1200, True, True),
    (3, "Pilotage", "port_cost", "Pilot services for entering and leaving the port", 2200, True, True),
    (4, "Towage", "port_cost", "Tug assistance for berthing and unberthing", 4800, True, True),
    (5, "Mooring", "port_cost", "Mooring and unmooring by linesmen", 900, True, True),
    (6, "Agency fee", "port_cost", "The port agent's fee for handling the call", 1800, False, True),
    (7, "Launch hire", "port_cost", "Launch boat transport to and from the vessel", 450, False, False),
    (8, "Garbage removal", "port_cost", "Collection of ship-generated waste", 350, False, False),
    (9, "Customs clearance", "port_cost", "Customs and immigration formalities", 400, False, False),
    (10, "Fresh water", "husbandry", "Fresh water supplied to the vessel", 600, False, False),
    (11, "Crew change", "husbandry", "Crew transport, visas and hotel for crew changes", 1500, False, False),
    (12, "Cash to master", "husbandry", "Cash delivered to the master on board", 3000, False, False),
    (13, "Courier and communication", "husbandry", "Courier, documents and communication costs", 120, False, False),
]

# How different agencies name the same expense on their templates (the reason pages need semantic mapping)
NAME_VARIANTS = {
    "Port dues": ["Port dues", "Harbour dues", "Port tonnage dues", "Port charges"],
    "Light dues": ["Light dues", "Lighthouse dues", "Light and navigation dues"],
    "Pilotage": ["Pilotage", "Pilotage In/Out", "Pilot fees", "Pilot dues"],
    "Towage": ["Towage", "Tug hire", "Tugs in/out", "Towage services"],
    "Mooring": ["Mooring", "Mooring/unmooring", "Linesmen", "Boatmen and linesmen"],
    "Agency fee": ["Agency fee", "Agency remuneration", "Husbandry agency fee"],
    "Launch hire": ["Launch hire", "Launch boat", "Boat service"],
    "Garbage removal": ["Garbage removal", "Waste disposal", "Sludge and garbage"],
    "Customs clearance": ["Customs clearance", "Customs and immigration", "Clearance formalities"],
    "Fresh water": ["Fresh water", "FW supply", "Potable water"],
    "Crew change": ["Crew change", "Crew handling", "Crew transport and visas"],
    "Cash to master": ["Cash to master", "CTM", "Master's cash"],
    "Courier and communication": ["Courier and communication", "Courier", "Communication expenses"],
}

# Who issues the supporting invoice for each expense
SUPPLIERS = {
    "Port dues": "Port Authority", "Light dues": "Lighthouse Service", "Pilotage": "Pilots Association",
    "Towage": "Towage Company", "Mooring": "Linesmen Cooperative", "Agency fee": "agency",
    "Launch hire": "Launch Services", "Garbage removal": "Waste Services", "Customs clearance": "Customs Broker",
    "Fresh water": "Water Supply Company", "Crew change": "Crew Travel Services", "Cash to master": "agency",
    "Courier and communication": "Express Courier",
}

VESSEL_TYPES = {"bulk carrier": 1.00, "tanker": 1.12, "container ship": 1.05, "general cargo": 0.92}
GT_BANDS = [(0, 9999), (10000, 24999), (25000, 49999), (50000, 99999), (100000, 250000)]
PURPOSES = ["discharging", "loading", "bunkering", "crew change", "repairs"]
APPOINTMENT_TYPES = ["in process", "confirmed", "completed", "cancelled"]
EVENT_TYPES = ["login", "view_da", "create_pda", "approve_fda", "chat_question", "download_attachment"]

BUYER_NAMES = ["Aegean Bulk Carriers", "Northsea Shipping", "Meridian Tankers", "Baltic Star Lines", "Coral Sea Maritime",
               "Atlas Ocean Transport", "Blue Horizon Shipping", "Ionian Navigation", "Polaris Chartering",
               "Southern Cross Bulk", "Cape Line Operators", "Levant Ship Management"]
AGENCY_NAMES = ["Harbour Point Agency", "Seagate Port Services", "Anchor Maritime Agency", "Quayside Shipping Agents",
                "Lighthouse Agencies", "Portline Services", "Bluewater Agency", "Tidewater Port Agents",
                "Compass Ship Agency", "Keel and Quay Agency", "Mainsail Port Services", "Wharfside Agents",
                "Breakwater Shipping", "Bayview Maritime", "Pierhead Agency"]
VESSEL_WORDS = ["Aurora", "Thalassa", "Orion", "Neptune", "Helios", "Calypso", "Andromeda", "Poseidon", "Selene",
                "Triton", "Vega", "Zephyr", "Artemis", "Hermes", "Kronos", "Leda", "Nereus", "Pallas", "Rhea", "Sirius"]
FLAGS = ["Malta", "Liberia", "Marshall Islands", "Panama", "Greece", "Cyprus", "Bahamas", "Singapore"]
BANKS = {"EUR": [("NL", "Maritime Bank Europe", "MBEUNL2A"), ("DE", "Hanseatic Trade Bank", "HTBKDEHH"),
                 ("GR", "Aegean Commercial Bank", "AECBGRAA"), ("BE", "Scheldt Bank", "SCHBBEBB")],
         "USD": [("SG", "Straits Trade Bank", "STTBSGSG"), ("AE", "Gulf Maritime Bank", "GUMBAEAD"),
                 ("US", "Gulf Coast National", "GCNBUS44")]}

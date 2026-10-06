"""Static content of the demo restaurant: menu, tables and restaurant settings."""

from decimal import Decimal

RESTAURANT_NAME = "Restaurant Démo"
RESTAURANT_TIMEZONE = "Africa/Bujumbura"
RESTAURANT_TAX_RATE = Decimal("10.00")

# (name, colour used for the placeholder pictures)
CATEGORIES = [
    ("Entrées", "#7a8f3d"),
    ("Plats", "#a6502c"),
    ("Grillades", "#8c2f2f"),
    ("Desserts", "#b8863b"),
    ("Boissons", "#2f6f7a"),
]

# (category, name, description, price, preparation minutes, allergens, calories, featured, available)
MENU = [
    ("Entrées", "Salade de chèvre chaud", "Mesclun, toasts de chèvre, miel et noix.",
     "7.50", 10, ["gluten", "lait", "fruits à coque"], 320, True, True),
    ("Entrées", "Soupe de légumes du jour", "Légumes de saison, crème légère.",
     "5.00", 8, ["lait"], 140, False, True),
    ("Entrées", "Samoussas au bœuf", "Trois samoussas croustillants, sauce pimentée.",
     "6.00", 12, ["gluten"], 380, False, True),
    ("Entrées", "Avocat crevettes", "Avocat frais, crevettes, vinaigrette citronnée.",
     "8.50", 8, ["crustacés"], 290, False, True),
    ("Plats", "Poulet rôti aux herbes", "Demi-poulet rôti, pommes de terre sautées.",
     "14.00", 25, [], 620, False, True),
    ("Plats", "Capitaine grillé, sauce tomate", "Filet de capitaine grillé, riz et légumes.",
     "16.50", 20, ["poisson"], 540, True, True),
    ("Plats", "Isombe aux poissons", "Feuilles de manioc mijotées, poisson, riz.",
     "12.00", 25, ["poisson"], 480, False, True),
    ("Plats", "Risotto aux champignons", "Riz crémeux, champignons, parmesan.",
     "13.50", 22, ["lait"], 580, False, True),
    ("Plats", "Pâtes crème et poulet", "Tagliatelles, poulet, crème et ciboulette.",
     "12.50", 18, ["gluten", "lait"], 700, False, True),
    ("Plats", "Plat végétarien du jour", "Légumes de saison et céréales, selon l'arrivage.",
     "11.00", 15, [], 450, False, True),
    ("Grillades", "Brochettes de chèvre", "Six brochettes marinées, bananes plantain, piment.",
     "15.00", 20, [], 600, True, True),
    ("Grillades", "Côte de bœuf grillée", "Côte de bœuf, frites maison, sauce au poivre.",
     "22.00", 30, ["lait"], 850, False, True),
    ("Grillades", "Brochettes de poulet", "Poulet mariné, riz parfumé, salade.",
     "13.00", 18, [], 560, False, True),
    ("Grillades", "Tilapia grillé entier", "Poisson entier grillé, légumes sautés.",
     "17.00", 25, ["poisson"], 520, False, True),
    ("Desserts", "Tarte aux fruits", "Pâte sablée et fruits de saison.",
     "6.50", 5, ["gluten", "lait", "œufs"], 410, False, True),
    ("Desserts", "Fondant au chocolat", "Cœur coulant, glace vanille.",
     "7.00", 12, ["gluten", "lait", "œufs"], 520, True, True),
    ("Desserts", "Salade de fruits frais", "Fruits frais coupés, menthe.",
     "5.50", 5, [], 150, False, True),
    ("Desserts", "Crème caramel", "Crème onctueuse, caramel maison.",
     "5.50", 5, ["lait", "œufs"], 300, False, True),
    ("Boissons", "Jus de fruit frais", "Pressé à la commande.",
     "3.50", 3, [], 110, False, True),
    ("Boissons", "Eau minérale 50 cl", "Plate ou gazeuse.",
     "1.50", 1, [], 0, False, True),
    ("Boissons", "Soda 33 cl", "Cola, orange ou citron.",
     "2.00", 1, [], 140, False, True),
    ("Boissons", "Café", "Café du pays, serré ou allongé.",
     "2.00", 3, [], 5, False, True),
    ("Boissons", "Thé aux épices", "Thé noir, gingembre et cannelle.",
     "2.50", 4, [], 5, False, False),  # deliberately unavailable, to show the state in the UI
]

# (number, capacity, location)
TABLES = [
    (1, 2, "Terrasse"),
    (2, 2, "Terrasse"),
    (3, 4, "Terrasse"),
    (4, 2, "Salle"),
    (5, 4, "Salle"),
    (6, 4, "Salle"),
    (7, 6, "Salle"),
    (8, 6, "Salle"),
    (9, 8, "Salon privé"),
    (10, 10, "Salon privé"),
]

DELIVERY_ADDRESSES = [
    "Avenue du Lac 14",
    "Rue des Fleurs 7",
    "Boulevard de l'Indépendance 120",
    "Chaussée du Peuple Murundi 33",
    "Avenue des Palmiers 5",
]
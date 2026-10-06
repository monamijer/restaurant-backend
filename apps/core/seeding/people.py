"""Demo accounts: one administrator, two staff members and six customers."""

from apps.accounts.models import Role, User

DEMO_DOMAIN = "demo.example"
DEMO_PASSWORD = "Demo-Passw0rd!"

# (local part, first name, last name, phone, role)
ACCOUNTS = [
    ("admin", "Aline", "Niyonzima", "+25779000001", Role.ADMIN),
    ("server", "Patrick", "Habimana", "+25779000002", Role.STAFF),
    ("kitchen", "Sophie", "Dubois", "+25779000003", Role.STAFF),
    ("client1", "Eric", "Ndayisenga", "+25779000011", Role.CLIENT),
    ("client2", "Diane", "Uwimana", "+25779000012", Role.CLIENT),
    ("client3", "Olivier", "Bigirimana", "+25779000013", Role.CLIENT),
    ("client4", "Fabrice", "Nzeyimana", "+25779000014", Role.CLIENT),
    ("client5", "Marie Claire", "Irakoze", "+25779000015", Role.CLIENT),
    ("client6", "Josiane", "Kamikazi", "+25779000016", Role.CLIENT),
]


def demo_accounts():
    return User.objects.filter(email__endswith=f"@{DEMO_DOMAIN}")


def create_people():
    """Create every demo account and return them grouped by role."""
    people = {Role.ADMIN: [], Role.STAFF: [], Role.CLIENT: []}
    for local_part, first_name, last_name, phone, role in ACCOUNTS:
        user = User.objects.create_user(
            email=f"{local_part}@{DEMO_DOMAIN}",
            password=DEMO_PASSWORD,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            role=role,
        )
        people[role].append(user)
    return people
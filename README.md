# Restaurant Backend

Django REST API for the Restaurant Table, Queue & Online Ordering Management System.
The Vue frontend lives in its own repository.


## Demo data

```bash
python manage.py seed_demo            # load the demo restaurant (no-op if already loaded)
python manage.py seed_demo --reset    # wipe restaurant data and demo accounts, then rebuild
```

The command prints the demo accounts (`admin@`, `server@`, `kitchen@`, `client1@` ...
`@demo.example`, one shared password). It refuses to run when `DEBUG` is off unless `--force`
is given. `--days`, `--orders-per-day`, `--seed` and `--no-images` tune the volume and content.
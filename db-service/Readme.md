# DB-Service
> labubu generation
### How to run
1. Very important to run migrations first in case you haven't run the service before
2. Start postgres with ``docker compose up --build db``
3. Then run 
```
pdm run makemig
pdm run migrate
```
Your migrations will be saved and applied to the postgres. Tables will be created.

4. Now we need to populate whitelist with some users, if you don't, skip that step. There are created in ``./db_service/scripts/whitelist_user.py``. You can easily change their profiles there. To get them in database run ``docker compose up --build populate_whitelist``
5. Now you can start up the application with
``` 
docker compose down
docker compose --build
```


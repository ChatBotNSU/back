# Db-Service
babuba labuda
### How to run
1. Very important to run migrations first in case you haven't run the service before
2. Start postgres with ``docker compose up --build db``
3. Then run 
```
pdm run makemig
pdm run migrate
```
4. Now you can start up the application with
```
docker compose down
docker compose --build
```
Your migrations will be saved and applied to the postgres. Tables will be created.

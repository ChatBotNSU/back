# DB-Service
> labubu generation
### How to run
1. Very important to run migrations first in case you haven't run the service before
2. Start postgres with ``docker compose up --build db``
3. Then run 
```
cd db-service
pdm install
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
6. Swagger for administration backend is available on
```
localhost:8080/docs
```



# Concept
1. db-service единственный сервис, который может напрямую работать с БД. Все запросы к базе только через него
2. s3-service, отвечающий за хранение и валидацию Chatbot-a и Execution state-a. Он является финальным источником правды о том, корректна ли текующая конфигурация графа и его текущее состояние. Он единственный, кто имеет право взаимодействовать с MiniIO. 

Из его существования возникает проблема излишнего копирования кода. В нем должны быть описаны все entities для графа и выполнения, однако проблема в том, что эти сущности в любом случае придется описывать, как минимум в двух местах. exectution-engine. 

Проблема решается созданием еще одной репы, которая бы взаимодей


# Entities description
Описание в нотации Pydantic
```python

class Variable(Basemodel):
    name: str
    type: Literal["string", "number"]

class Node(Basemodel):
    node_id: int

class Graph(Basemodel):
    root: int # root node id
    nodes: dict[Node]

class Chatbot(BaseModel):
    variables: list[Variable]
    graph: Graph
    bot_id: int
    bot_name: str
```

Отдельно заметим, что Graph представлен аналогом связного списка. У нас есть словарь нод, в котором мы индексируемся по node_id. Сам граф хранит ссылку на первую ноду. Все ноды должны в той или иной форме указывать на следующую.




### Examples to put in S3
chatbot-1.json
```
{
    "variables": [
        {
            "name": "name",
            "type": "string"
        },
        {
            "name": "age",
            "type": "number"
        }
    ],
    "bot_id": 1,
    "bot_name": "Pipik",
    "graph": {
        "root": "1",
        "nodes": {
            "1": {"type": "set_variable", "assigned_variable": "name", "operation": "=", "operand": "Pipik", "next_node_id": "2"},
            "2": {"type": "set_variable", "assigned_variable": "age", "operation": "=", "operand": "18", "next_node_id": "3"},
            "3": {"type": "set_message", "text": "Hello, {name}! You are {age} years old.", "audios": [], "images": [], "files": [], "choise_options": [],  "next_node_id": "4"},
            "4": {"type": "send_message", "next_node_id": "1"},
            "5": {"type": "text_answer", "assigned_variable": "name", "next_node_id": "3"}
        }
    } 
}


```

execution-1.json
```
{
    "bot_id": 1,
    "execution_id": 2,
    "executing_node_id": "1",
    "variable_values": {
        "name": "",
        "age": 0
    }
}
```

execution request for redis
```
{
    execution_id: 1,
    chatbot_id: 1,
    message: {
        "text": "Lol",
        "images": [],
        "audios": [],
        "files": []
    }
}

In Redis CLI (docker exec -it redis redis-cli):

XADD execution_requests * payload '{"execution_id": 1, "chatbot_id": 1, "message": { "text": "lol", "images": [], "audios": [], "files": []}}'
```

you can see responses with
```
XREVRANGE execution_responses + - COUNT 10
```


### Known issues
1. Now chatbots support only one file added a time. Because it is just stores filepath to the variable, it cannot work with plenty of files sent in a time. Fix of this issue needs slight redesign which is kinda hard. The simplest redesign possible is adding type list[str] and in SetVariable node adding feature like operation ``[]`` and operand ``number`` which will grant opportunity to use indexing in a little counterintuitive style but at least something

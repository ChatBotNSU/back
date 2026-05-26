import json

v1_data = {
    "bot_name": "Pipik",
    "graph": {
        "root": "1",
        "nodes": {
            "1": {"type": "set_variable", "assigned_variable": "name", "operation": "=", "operand": "Pipik", "next_node_id": "2"},
            "2": {"type": "set_variable", "assigned_variable": "age", "operation": "=", "operand": "18", "next_node_id": "3"},
            "3": {"type": "set_message", "text": "Hello, {name}! You are {age} years old.", "next_node_id": "4"},
            "4": {"type": "send_message", "next_node_id": "5"},
            "5": {"type": "text_answer", "assigned_variable": "name", "next_node_id": "6"},
            "6": {"type": "set_message", "text": "Hello, {name}!", "next_node_id": "7"},
            "7": {"type": "send_message", "next_node_id": "8"},
            "8": {"type": "script_execution", "script": "name = 'Motherfucker'", "next_node_id": "9"},
            "9": {"type": "set_message", "text": "Bye!", "next_node_id": "10"},
            "10": {"type": "send_message", "next_node_id": "1"}
        }
    }
}

v2_data = {
    "bot_name": "Pipik Pro",
    "graph": {
        "root": "1",
        "nodes": {
            "1": {"type": "set_variable", "assigned_variable": "name", "operation": "=", "operand": "Pipik", "next_node_id": "2"},
            "2": {"type": "set_variable", "assigned_variable": "age", "operation": "=", "operand": "21", "next_node_id": "3"}, # возраст
            "3": {"type": "set_message", "text": "Welcome to Stage 2!", "next_node_id": "4"}, # текст
            "4": {"type": "send_message", "next_node_id": "5"},
            "5": {"type": "text_answer", "assigned_variable": "name", "next_node_id": "7"}, # сразу на 7
            "6": {"type": "set_message", "text": "Hello, {name}!", "next_node_id": "7"}, # узел 6 теперь мусор
            "7": {"type": "send_message", "next_node_id": "11"}, # переход на новый узел 11
            "11": {"type": "send_message", "text": "New node here!", "next_node_id": "1"} # новый
        }
    }
}

v3_data = {
    "bot_name": "Pipik",
    "graph": {
        "root": "1",
        "nodes": {
            "1": {"type": "set_variable", "assigned_variable": "name", "operation": "=", "operand": "Pipik", "next_node_id": "2"},
            "2": {"type": "set_variable", "assigned_variable": "age", "operation": "=", "operand": "18", "next_node_id": "3"},
            "3": {"type": "set_message", "text": "Hello, {name}! You are {age} years old.", "next_node_id": "4"},
            "4": {"type": "send_message", "next_node_id": "5"},
            "5": {"type": "text_answer", "assigned_variable": "name", "next_node_id": "6"},
            "6": {"type": "set_message", "text": "Hello, {name}!", "next_node_id": "7"},
            "7": {"type": "send_message", "next_node_id": "8"},
            "8": {"type": "script_execution", "script": "name = 'Motherfucker'", "next_node_id": "9"},
            "9": {"type": "set_message", "text": "Bye!", "next_node_id": "10"},
            "10": {"type": "send_message", "next_node_id": "1"}
        }
    }
}

class GraphAssistant:
    @staticmethod
    def traverse(data):
        """Простой обход от корня с защитой от циклов"""
        nodes = data["graph"]["nodes"]
        curr = data["graph"]["root"]
        visited = []
        path = []
        
        while curr and curr in nodes:
            if curr in visited:
                path.append(f"{curr} (LOOP)")
                break
            visited.append(curr)
            path.append(curr)
            curr = nodes[curr].get("next_node_id")
        return visited, path

    @staticmethod
    def get_orphaned_nodes(data):
        """Ищет 'узлы-сироты', до которых нельзя дойти от корня"""
        all_nodes = set(data["graph"]["nodes"].keys())
        reachable, _ = GraphAssistant.traverse(data)
        return all_nodes - set(reachable)

    @staticmethod
    def compare(v1, v2):
        """Сравнивает две версии графа"""
        nodes1 = v1["graph"]["nodes"]
        nodes2 = v2["graph"]["nodes"]
        
        added = [n for n in nodes2 if n not in nodes1]
        deleted = [n for n in nodes1 if n not in nodes2]
        modified = []
        
        for n_id in nodes1:
            if n_id in nodes2 and nodes1[n_id] != nodes2[n_id]:
                modified.append(n_id)
                
        return {
            "added": added,
            "deleted": deleted,
            "modified": modified
        }

def run_demo():
    print(f"=== АНАЛИЗ ГРАФА: {v1_data['bot_name']} ===")
    reachable, path = GraphAssistant.traverse(v1_data)
    print(f"Путь обхода: {' -> '.join(path)}")
    
    orphans = GraphAssistant.get_orphaned_nodes(v1_data)
    print(f"Узлы-сироты (мусор): {list(orphans) if orphans else 'Нет'}")

    print(f"\n=== СРАВНЕНИЕ V1 И V2 ===")
    diff = GraphAssistant.compare(v1_data, v2_data)
    print(f"Добавленные узлы: {diff['added']}")
    print(f"Удаленные узлы:   {diff['deleted']}")
    print(f"Измененные узлы:  {diff['modified']}")

    print(f"\n=== АНАЛИЗ V2 (ПРОВЕРКА НА МУСОР) ===")
    v2_orphans = GraphAssistant.get_orphaned_nodes(v2_data)
    print(f"В V2 появились сироты: {list(v2_orphans)}")

    print(f"\n=== СРАВНЕНИЕ V1 И V3 ===")
    diff = GraphAssistant.compare(v1_data, v3_data)
    print(f"Добавленные узлы: {diff['added']}")
    print(f"Удаленные узлы:   {diff['deleted']}")
    print(f"Измененные узлы:  {diff['modified']}")


if __name__ == "__main__":
    run_demo()
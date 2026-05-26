from models.chatbot import Chatbot


class GraphAssistant:

    @staticmethod
    def get_reachable_nodes(chatbot: Chatbot) -> set[str]:
        """
        Обходит граф от root, учитывая ВСЕ ветки.
        Ищет любое поле ноды, оканчивающееся на _node_id — это исходящее ребро.
        Защита от циклов встроена.
        """
        nodes = chatbot.graph.nodes
        reachable: set[str] = set()
        queue = [chatbot.graph.root]

        while queue:
            curr = queue.pop()
            if curr in reachable or curr not in nodes:
                continue
            reachable.add(curr)
            for key, val in nodes[curr].model_dump().items():
                if key.endswith("node_id") and isinstance(val, str):
                    queue.append(val)

        return reachable

    @staticmethod
    def get_orphaned_nodes(chatbot: Chatbot) -> set[str]:
        """
        Узлы, до которых нельзя дойти от root.
        Их стоит предложить пользователю удалить.
        """
        all_nodes = set(chatbot.graph.nodes.keys())
        reachable = GraphAssistant.get_reachable_nodes(chatbot)
        return all_nodes - reachable

    @staticmethod
    def compare(v1: Chatbot, v2: Chatbot) -> dict[str, list[str]]:
        """
        Сравнивает два графа. Возвращает:
        {
            "added":    [...],   # узлы только в v2
            "deleted":  [...],   # узлы только в v1
            "modified": [...],   # есть в обоих, но изменились
        }
        Сравниваем через model_dump() — нам важно содержимое, а не объект.
        """
        nodes1 = v1.graph.nodes
        nodes2 = v2.graph.nodes

        added    = [n for n in nodes2 if n not in nodes1]
        deleted  = [n for n in nodes1 if n not in nodes2]
        modified = [
            n for n in nodes1
            if n in nodes2 and nodes1[n].model_dump() != nodes2[n].model_dump()
        ]

        return {"added": added, "deleted": deleted, "modified": modified}

    @staticmethod
    def merge(base: Chatbot, latest: Chatbot, incoming: Chatbot) -> Chatbot:
        """
        Автомерж: берём latest как основу и накатываем изменения из incoming.

        Вызывать только когда конфликтов нет, т.е.:
        modified(base→incoming) ∩ modified(base→latest) == ∅

        Логика по узлам:
        - Добавленные пользователем → добавляем в latest
        - Удалённые пользователем   → удаляем из latest
        - Изменённые пользователем  → перезаписываем в latest

        Логика по метаданным:
        - bot_name: берём у incoming если он изменился относительно base
        - root: берём у incoming если он изменился относительно base
        """
        user_diff = GraphAssistant.compare(base, incoming)

        merged_nodes = dict(latest.graph.nodes)

        for node_id in user_diff["added"]:
            merged_nodes[node_id] = incoming.graph.nodes[node_id]

        for node_id in user_diff["deleted"]:
            merged_nodes.pop(node_id, None)

        for node_id in user_diff["modified"]:
            merged_nodes[node_id] = incoming.graph.nodes[node_id]

        new_root = (
            incoming.graph.root
            if incoming.graph.root != base.graph.root
            else latest.graph.root
        )

        new_bot_name = (
            incoming.bot_name
            if incoming.bot_name != base.bot_name
            else latest.bot_name
        )

        return Chatbot.model_validate({
            **latest.model_dump(),
            "bot_name": new_bot_name,
            "graph": {
                "root": new_root,
                "nodes": {
                    node_id: node.model_dump()
                    for node_id, node in merged_nodes.items()
                },
            },
        })


def detect_conflict(
    base: Chatbot,
    latest: Chatbot,
    incoming: Chatbot,
) -> tuple[bool, dict]:
    """
    Проверяет конфликт между тем что сохранил другой юзер (latest)
    и тем что хочет сохранить текущий (incoming), относительно общей базы (base).

    has_conflict=False → можно мержить через GraphAssistant.merge()
    has_conflict=True  → показываем пользователю конфликт и diff
    """
    latest_diff = GraphAssistant.compare(base, latest)
    incoming_diff = GraphAssistant.compare(base, incoming)

    latest_changed = set(latest_diff["modified"]) | set(latest_diff["deleted"])
    incoming_changed = set(incoming_diff["modified"]) | set(incoming_diff["deleted"])
    conflicting_nodes = latest_changed & incoming_changed

    conflicting_nodes |= set(latest_diff["added"]) & set(incoming_diff["added"])

    metadata_conflicts: list[str] = []
    if latest.graph.root != base.graph.root and incoming.graph.root != base.graph.root:
        metadata_conflicts.append("root")
    if latest.bot_name != base.bot_name and incoming.bot_name != base.bot_name:
        metadata_conflicts.append("bot_name")

    if not conflicting_nodes and not metadata_conflicts:
        return False, {}

    return True, {
        "conflicting_nodes": sorted(conflicting_nodes),
        "conflicting_metadata": metadata_conflicts,
        "your_changes": incoming_diff,
        "their_changes": latest_diff,
    }

from models.chatbot import Chatbot, Subgraph


def _diff_nodes(nodes1: dict, nodes2: dict) -> dict[str, list[str]]:
    """Diff двух словарей узлов: что добавили, удалили, изменили (по содержимому)."""
    dumps2 = {k: v.model_dump() for k, v in nodes2.items()}
    dumps1 = {k: v.model_dump() for k, v in nodes1.items()}
    return {
        "added":    [n for n in dumps2 if n not in dumps1],
        "deleted":  [n for n in dumps1 if n not in dumps2],
        "modified": [n for n in dumps1 if n in dumps2 and dumps1[n] != dumps2[n]],
    }


def _merge_node_dicts(base: dict, latest: dict, incoming: dict) -> dict:
    """Берём latest как основу, накатываем delta пользователя (incoming относительно base)."""
    user_diff = _diff_nodes(base, incoming)
    merged = dict(latest)
    for n in user_diff["added"]:
        merged[n] = incoming[n]
    for n in user_diff["deleted"]:
        merged.pop(n, None)
    for n in user_diff["modified"]:
        merged[n] = incoming[n]
    return merged


def _pick_metadata(base_val, latest_val, incoming_val):
    """`incoming` побеждает, если изменил относительно base. Иначе берём latest."""
    return incoming_val if incoming_val != base_val else latest_val


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
        return _diff_nodes(v1.graph.nodes, v2.graph.nodes)

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
        merged_nodes = _merge_node_dicts(base.graph.nodes, latest.graph.nodes, incoming.graph.nodes)

        return Chatbot.model_validate({
            **latest.model_dump(),
            "bot_name": _pick_metadata(base.bot_name, latest.bot_name, incoming.bot_name),
            "graph": {
                "root":  _pick_metadata(base.graph.root, latest.graph.root, incoming.graph.root),
                "nodes": {node_id: node.model_dump() for node_id, node in merged_nodes.items()},
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


# ─── Subgraphs ──────────────────────────────────────────────────────────────
# Аналогичная логика для сабграфов. У сабграфа кроме `graph` есть метаданные
# `inputs` и `exits` — они тоже могут конфликтовать. Имя (`name`) считаем
# иммутабельным: сабграф идентифицируется парой (owner_user_id, name).


class SubgraphAssistant:

    @staticmethod
    def get_reachable_nodes(subgraph: Subgraph) -> set[str]:
        nodes = subgraph.graph.nodes
        reachable: set[str] = set()
        queue = [subgraph.graph.root]
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
    def get_orphaned_nodes(subgraph: Subgraph) -> set[str]:
        return set(subgraph.graph.nodes.keys()) - SubgraphAssistant.get_reachable_nodes(subgraph)

    @staticmethod
    def compare(v1: Subgraph, v2: Subgraph) -> dict[str, list[str]]:
        return _diff_nodes(v1.graph.nodes, v2.graph.nodes)

    @staticmethod
    def merge(base: Subgraph, latest: Subgraph, incoming: Subgraph) -> Subgraph:
        """Автомерж сабграфа. Вызывать только если конфликта нет."""
        merged_nodes = _merge_node_dicts(base.graph.nodes, latest.graph.nodes, incoming.graph.nodes)

        return Subgraph.model_validate({
            **latest.model_dump(),
            "inputs": _pick_metadata(base.inputs, latest.inputs, incoming.inputs),
            "exits":  _pick_metadata(base.exits,  latest.exits,  incoming.exits),
            "graph": {
                "root":  _pick_metadata(base.graph.root, latest.graph.root, incoming.graph.root),
                "nodes": {node_id: node.model_dump() for node_id, node in merged_nodes.items()},
            },
        })


def detect_subgraph_conflict(
    base: Subgraph,
    latest: Subgraph,
    incoming: Subgraph,
) -> tuple[bool, dict]:
    """То же что `detect_conflict` для чатбота, но с учётом `inputs` и `exits`."""
    latest_diff = SubgraphAssistant.compare(base, latest)
    incoming_diff = SubgraphAssistant.compare(base, incoming)

    latest_changed = set(latest_diff["modified"]) | set(latest_diff["deleted"])
    incoming_changed = set(incoming_diff["modified"]) | set(incoming_diff["deleted"])
    conflicting_nodes = latest_changed & incoming_changed
    conflicting_nodes |= set(latest_diff["added"]) & set(incoming_diff["added"])

    metadata_conflicts: list[str] = []
    if latest.graph.root != base.graph.root and incoming.graph.root != base.graph.root:
        metadata_conflicts.append("root")
    # inputs/exits сравниваем как упорядоченные списки — порядок имеет значение
    # для UI, но семантически он скорее всего безразличен. Здесь — строгое равенство.
    if latest.inputs != base.inputs and incoming.inputs != base.inputs:
        metadata_conflicts.append("inputs")
    if latest.exits != base.exits and incoming.exits != base.exits:
        metadata_conflicts.append("exits")

    if not conflicting_nodes and not metadata_conflicts:
        return False, {}

    return True, {
        "conflicting_nodes": sorted(conflicting_nodes),
        "conflicting_metadata": metadata_conflicts,
        "your_changes": incoming_diff,
        "their_changes": latest_diff,
    }

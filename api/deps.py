from __future__ import annotations

from typing import Annotated, Any
from fastapi import Depends, Request

from stores.session_store import InMemorySessionStore, RedisSessionStore
from stores.flow_store import InMemoryFlowStore, SQLFlowStore
from stores.bot_store import InMemoryBotStore, SQLBotStore
from stores.dead_letter import InMemoryDeadLetterStore, RedisDeadLetterStore
from stores.data_store import InMemoryDataStore, SQLDataStore
from stores.integration_store import InMemoryIntegrationStore, SQLIntegrationStore
from stores.project_store import InMemoryProjectStore, SQLProjectStore
from stores.user_store import InMemoryUserStore, SQLUserStore
from stores.secret_store import InMemorySecretStore, SQLSecretStore


def get_session_store(request: Request) -> InMemorySessionStore | RedisSessionStore:
    return request.app.state.session_store


def get_flow_store(request: Request) -> InMemoryFlowStore | SQLFlowStore:
    return request.app.state.flow_store


def get_bot_store(request: Request) -> InMemoryBotStore | SQLBotStore:
    return request.app.state.bot_store


def get_dead_letter_store(request: Request) -> InMemoryDeadLetterStore | RedisDeadLetterStore:
    return request.app.state.dead_letter


def get_secret_store(request: Request) -> InMemorySecretStore | SQLSecretStore:
    return request.app.state.secret_store


def get_project_store(request: Request) -> InMemoryProjectStore | SQLProjectStore:
    return request.app.state.project_store


def get_data_store(request: Request) -> InMemoryDataStore | SQLDataStore:
    return request.app.state.data_store


def get_integration_store(request: Request) -> InMemoryIntegrationStore | SQLIntegrationStore:
    return request.app.state.integration_store


def get_user_store(request: Request) -> InMemoryUserStore | SQLUserStore:
    return request.app.state.user_store


def get_arq_pool(request: Request) -> Any:
    """ARQ pool for background job dispatch, or None when unavailable."""
    return getattr(request.app.state, "arq_pool", None)


SessionStoreDep = Annotated[InMemorySessionStore | RedisSessionStore, Depends(get_session_store)]
FlowStoreDep = Annotated[InMemoryFlowStore | SQLFlowStore, Depends(get_flow_store)]
BotStoreDep = Annotated[InMemoryBotStore | SQLBotStore, Depends(get_bot_store)]
DeadLetterStoreDep = Annotated[
    InMemoryDeadLetterStore | RedisDeadLetterStore, Depends(get_dead_letter_store)
]
SecretStoreDep = Annotated[InMemorySecretStore | SQLSecretStore, Depends(get_secret_store)]
ProjectStoreDep = Annotated[InMemoryProjectStore | SQLProjectStore, Depends(get_project_store)]
DataStoreDep = Annotated[InMemoryDataStore | SQLDataStore, Depends(get_data_store)]
IntegrationStoreDep = Annotated[
    InMemoryIntegrationStore | SQLIntegrationStore, Depends(get_integration_store)
]
UserStoreDep = Annotated[InMemoryUserStore | SQLUserStore, Depends(get_user_store)]
ArqPoolDep = Annotated[Any, Depends(get_arq_pool)]

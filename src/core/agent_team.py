from __future__ import annotations

import uuid
from datetime import datetime, timezone

from src.db.agent_team_db import AgentTeamDB


class AgentTeamError(Exception):
    """agent-team 业务异常基类。"""


class AgentNotFoundError(AgentTeamError):
    """Agent 不存在。"""

    code = "AGENT_NOT_FOUND"


class EmptyContentError(AgentTeamError):
    """消息内容为空。"""

    code = "EMPTY_CONTENT"


class DuplicateNameError(AgentTeamError):
    """同名 Agent 已存在。"""

    code = "DUPLICATE_NAME"


class InvalidStatusError(AgentTeamError):
    """状态值不合法。"""

    code = "INVALID_STATUS"


_CONTACT_STATUSES = frozenset({"online", "offline", "busy"})


class AgentTeamService:
    """封装 agent-team 业务逻辑：校验、ID 生成、错误码映射。

    所有方法为同步调用。调用方负责传入正确的参数，Service 层
    不关心上下文注入或 tool 协议——这些由 Tool 层处理。
    """

    def __init__(self, db: AgentTeamDB) -> None:
        """注入 DB 层实例。"""
        self._db = db

    def close(self) -> None:
        """关闭底层数据库连接。"""
        self._db.close()

    def send_message(self, sender_id: str, to_agent_id: str, content: str) -> dict:
        """发送消息给指定 Agent。"""
        if not content.strip():
            raise EmptyContentError()
        if self._db.get_agent(to_agent_id) is None:
            raise AgentNotFoundError()

        msg_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        self._db.insert_message(
            id=msg_id,
            sender_id=sender_id,
            receiver_id=to_agent_id,
            content=content.strip(),
            created_at=created_at,
        )
        return {"id": msg_id, "created_at": created_at}

    def receive_message(
        self,
        receiver_id: str,
        limit: int = 20,
        offset: int = 0,
        unread_only: bool = False,
    ) -> tuple[list[dict], int]:
        """收件箱查询，自动标记返回的消息为已读。"""
        if self._db.get_agent(receiver_id) is None:
            raise AgentNotFoundError()
        messages, total = self._db.list_messages(receiver_id, limit, offset, unread_only)
        if messages:
            self._db.mark_as_read([m["id"] for m in messages])
        return (messages, total)

    def get_contacts(
        self,
        current_agent_id: str,
        status_filter: str | None = None,
    ) -> list[dict]:
        """获取通讯录，排除已删除 Agent。"""
        if status_filter is not None and status_filter not in _CONTACT_STATUSES:
            raise InvalidStatusError()

        agents = self._db.list_agents(exclude_id=current_agent_id)
        # 过滤已删除的 Agent（DB 层不默认过滤 deleted）
        agents = [a for a in agents if a["status"] != "deleted"]
        if status_filter is not None:
            agents = [a for a in agents if a["status"] == status_filter]
        return agents

    def get_contact_detail(self, agent_id: str) -> dict:
        """查询 Agent 详情。"""
        agent = self._db.get_agent(agent_id)
        if agent is None:
            raise AgentNotFoundError()
        return agent

    def create_agent(self, name: str, desc: str = "", prompt: str = "") -> dict:
        """创建新 Agent，默认 status 为 offline。"""
        if not name.strip():
            raise ValueError("Agent name is required")
        if self._db.get_agent_by_name(name) is not None:
            raise DuplicateNameError()

        agent_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        return self._db.insert_agent(
            id=agent_id,
            name=name.strip(),
            desc=desc,
            prompt=prompt,
            status="offline",
            created_at=now,
            updated_at=now,
        )

    def delete_agent(self, agent_id: str) -> bool:
        """软删除 Agent（status → 'deleted'）。"""
        if self._db.get_agent(agent_id) is None:
            raise AgentNotFoundError()
        return self._db.delete_agent(agent_id)

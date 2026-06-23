from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class Agent(ABC):  
    def __init__(
        self,
        name: str,
        desc: str,
        model: str,
        workspace: str,
        messages: Optional[List[Dict[str, Any]]] = None,
        tools: Optional[List[Any]] = None,
        skills: Optional[List[Any]] = None,
        temperature: float = 0.3,
        memory: Optional[Any] = None,
        max_context_tokens: int = 120_000,
        max_steps: int = 50,
    ):
        self.name = name
        self.desc = desc
        self.model:str = model
        self.workspace = workspace

        self.messages = messages or []
        self.tools = tools or []
        self.skills = skills or []
        self.temperature = temperature
        self.memory = memory

        self.max_context_tokens = max_context_tokens

        self.total_tokens = 0
        self.running = False
    
    def _load_model_config(self):
        self.proiderId = self.model.split("/")[0]
        self.modelId = self.model.split("/")[1]
        #context_limit

    def _load_llm_client(self):
        # config https://models.dev/api.json
        self.llm = llm(self.proiderId,self.modelId)


    def add_user_message(self, content: str):
        self.messages.append({
            "role": "user",
            "content": content,
        })

    def add_assistant_message(
        self,
        content: Optional[str] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
    ):
        message = {
            "role": "assistant",
            "content": content or "",
        }

        if tool_calls:
            message["tool_calls"] = tool_calls

        self.messages.append(message)

    def add_tool_message(self, tool_call_id: str, content: str):
        self.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content,
        })

    def _check_token_limit(self) -> bool:
        """
        检查当前上下文是否达到 token 限制。

        这里先用 total_tokens 做近似判断。
        更严谨的方式是使用 tokenizer 对 self.messages 重新计算。
        """
        return self.total_tokens >= self.max_context_tokens

    async def run(self, user_input: Optional[str] = None):
        """
        Agent 主入口。
        """

        if user_input:
            self.add_user_message(user_input)

        self.running = True

        try:
            await self._loop()
        finally:
            self.running = False

    async def _loop(self):
        """
        Agent 主循环。

        基本流程：
        1. 检查上下文长度
        2. 调用 LLM
        3. 记录 assistant message
        4. 如果有工具调用，执行工具并追加 tool message
        5. 如果没有工具调用，结束本轮任务
        """

        step = 0

        while self.running:
            step += 1

            if step > self.max_steps:
                self.add_assistant_message(
                    content=f"任务已达到最大执行步数 {self.max_steps}，自动停止。"
                )
                break

            if self._check_token_limit():
                await self.compact_context()

            response = await self.chat()

            usage = getattr(response, "usage", None)
            if usage:
                self.total_tokens += getattr(usage, "total_tokens", 0)

            content = getattr(response, "content", None)
            tool_calls = getattr(response, "tool_calls", None)

            self.add_assistant_message(
                content=content,
                tool_calls=tool_calls,
            )

            if not tool_calls:
                break

            for tool_call in tool_calls:
                result = await self.execute_tool(tool_call)

                self.add_tool_message(
                    tool_call_id=tool_call["id"],
                    content=str(result),
                )

    @abstractmethod
    async def chat(self) -> Any:
        """
        调用 LLM。

        子类需要实现，例如：
        return await llm_client.chat_async(...)
        """
        raise NotImplementedError

    @abstractmethod
    async def execute_tool(self, tool_call: Dict[str, Any]) -> Any:
        """
        执行工具调用。
        """
        raise NotImplementedError

    @abstractmethod
    async def compact_context(self):
        """
        压缩上下文。

        常见做法：
        1. 保留 system message
        2. 总结历史 messages
        3. 保留最近几轮对话
        4. 将总结后的内容重新写回 self.messages
        """
        raise NotImplementedError
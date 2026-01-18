#!/usr/bin/env python3
"""
FastAPI 后端服务器
提供 REST API 和 WebSocket 端点
"""
import sys
import os
from pathlib import Path
from typing import Dict, Any, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from utils.logger import logger

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 导入 ReactEngine
from core.react_engine import ReactEngine


class TaskRequest(BaseModel):
    """任务请求模型"""
    task: str
    max_iterations: int = 10


class TaskResponse(BaseModel):
    """任务响应模型"""
    success: bool
    summary: str
    iterations: int
    answer: Optional[str] = None
    observations: list = []
    error: Optional[str] = None


# 创建 FastAPI 应用
app = FastAPI(
    title="IntelliAgent - ReAct Agent",
    description="基于 ReAct 循环的代码开发助手",
    version="2.0.0"
)

# 添加 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件
static_dir = project_root / "web" / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    logger.info(f"静态文件目录: {static_dir}")
else:
    logger.warning(f"静态文件目录不存在: {static_dir}")

# 全局引擎实例（需要在启动时初始化）
engine: Optional[ReactEngine] = None


def initialize_engine():
    """初始化 ReAct 引擎"""
    global engine
    
    if engine is not None:
        return engine
    
    try:
        from core.llm_client import LLMClient
        from core.tool_registry import ToolRegistry
        from core.memory import Memory
        from core.context import ContextManager
        
        # 创建组件
        llm_client = LLMClient()
        tools = ToolRegistry()
        memory = Memory()
        context = ContextManager()
        
        # 创建引擎
        engine = ReactEngine(
            llm_client=llm_client,
            tools=tools,
            memory=memory,
            context=context
        )
        
        logger.info("ReAct 引擎初始化完成")
        return engine
    
    except Exception as e:
        logger.error(f"初始化 ReAct 引擎失败 | error={e}")
        raise


@app.get("/", response_class=HTMLResponse)
async def read_root():
    """返回主页面"""
    index_path = static_dir / "index.html"
    
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    
    with open(index_path, "r", encoding="utf-8") as f:
        return f.read()


@app.post("/api/run", response_model=TaskResponse)
async def run_task(request: TaskRequest):
    """执行任务（HTTP 轮询模式）"""
    global engine
    
    try:
        # 初始化引擎（如果需要）
        if engine is None:
            engine = initialize_engine()
        
        logger.info(f"收到任务请求 | task={request.task[:50]}...")
        
        # 执行任务
        result = engine.run(request.task, max_iterations=request.max_iterations)
        
        logger.info(f"任务执行完成 | success={result['success']}")
        return TaskResponse(**result)
    
    except Exception as e:
        logger.error(f"任务执行失败 | error={e}")
        import traceback
        logger.debug(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"任务执行失败: {str(e)}")


@app.websocket("/ws/run")
async def websocket_run(websocket: WebSocket):
    """WebSocket 实时推送执行过程"""
    global engine
    
    await websocket.accept()
    
    try:
        # 初始化引擎（如果需要）
        if engine is None:
            engine = initialize_engine()
        
        # 接收任务请求
        data = await websocket.receive_json()
        task = data.get("task", "")
        max_iterations = data.get("max_iterations", 10)
        
        logger.info(f"收到 WebSocket 任务请求 | task={task[:50]}...")
        
        # 发送开始消息
        await websocket.send_json({
            "type": "start",
            "data": {"task": task, "max_iterations": max_iterations}
        })
        
        # 使用流式执行
        async for step in run_task_stream(engine, task, max_iterations):
            await websocket.send_json({
                "type": "step",
                "data": step
            })
        
        # 发送完成消息
        await websocket.send_json({
            "type": "complete",
            "data": {"message": "任务执行完成"}
        })
        
        logger.info("WebSocket 任务执行完成")
    
    except WebSocketDisconnect:
        logger.info("WebSocket 连接已断开")
    except Exception as e:
        logger.error(f"WebSocket 任务执行失败 | error={e}")
        import traceback
        logger.debug(traceback.format_exc())
        
        # 发送错误消息
        try:
            await websocket.send_json({
                "type": "error",
                "data": {"error": str(e)}
            })
        except:
            pass


async def run_task_stream(engine: ReactEngine, task: str, max_iterations: int):
    """
    流式执行任务，生成每一步的观察结果
    
    Args:
        engine: ReAct 引擎实例
        task: 任务描述
        max_iterations: 最大迭代次数
    
    Yields:
        每一步的观察结果
    """
    # 清空之前的观察结果
    engine.memory.clear_memory()
    
    # 添加任务到上下文
    engine.context.add_context(f"用户任务: {task}")
    
    # 执行循环（流式输出）
    for iteration in range(1, max_iterations + 1):
        # Step 1: Thought（LLM 思考）
        thought = engine._generate_thought(task, iteration)
        
        if not thought:
            yield {
                "type": "error",
                "iteration": iteration,
                "message": "无法生成 LLM 思考"
            }
            break
        
        # 发送思考
        yield {
            "type": "thought",
            "iteration": iteration,
            "data": {
                "reasoning": thought.get("reasoning", ""),
                "is_complete": thought.get("is_complete", False)
            }
        }
        
        # Step 2: 判断是否完成
        if thought.get("is_complete"):
            yield {
                "type": "answer",
                "iteration": iteration,
                "data": {
                    "answer": thought.get("answer", "")
                }
            }
            break
        
        # Step 3: Action 和 Observation
        action = thought.get("action", {})
        tool_name = action.get("tool")
        tool_args = action.get("args", {})
        
        if not tool_name:
            continue
        
        # 发送行动
        yield {
            "type": "action",
            "iteration": iteration,
            "data": {
                "tool": tool_name,
                "args": tool_args
            }
        }
        
        # 执行工具并观察结果
        observation = engine._execute_and_observe(tool_name, tool_args, iteration)
        
        # 发送观察结果
        yield {
            "type": "observation",
            "iteration": iteration,
            "data": observation
        }


@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {"status": "ok", "service": "intelliagent-web"}


if __name__ == "__main__":
    import uvicorn
    
    # 启动服务器
    host = os.getenv("WEB_HOST", "0.0.0.0")
    port = int(os.getenv("WEB_PORT", "8000"))
    
    logger.info("=" * 60)
    logger.info("🌐 启动 FastAPI 服务器")
    logger.info(f"   地址: http://{host}:{port}")
    logger.info(f"   API 文档: http://{host}:{port}/docs")
    logger.info("=" * 60)
    
    uvicorn.run(app, host=host, port=port)

#!/usr/bin/env python3
"""
执行器模块 - PDCA 的 Do 阶段（改进版）
完整的循环处理引擎，包含：
1. 步骤级重试循环（可配置退避策略）
2. 依赖关系检查循环
3. 上下文传播和变量替换循环
4. 异常恢复策略循环
5. 资源管理循环
"""
import time
import re
from typing import List, Dict, Any, Optional, Set, Callable
from utils.logger import logger


class ExecutionMetrics:
    """执行指标追踪"""
    
    def __init__(self):
        self.total_steps = 0
        self.successful_steps = 0
        self.failed_steps = 0
        self.skipped_steps = 0
        self.total_retries = 0
        self.total_time = 0.0
        self.step_times = {}
        self.recovery_attempts = {}
    
    def add_step(self, step_id: int, status: str, duration: float):
        """记录步骤执行"""
        self.total_steps += 1
        self.step_times[step_id] = duration
        
        if status == 'success':
            self.successful_steps += 1
        elif status == 'failed':
            self.failed_steps += 1
        elif status == 'skipped':
            self.skipped_steps += 1
    
    def print_summary(self):
        """打印执行摘要"""
        logger.info("=" * 60)
        logger.info("📊 执行指标摘要")
        logger.info("=" * 60)
        logger.info(f"总步骤数: {self.total_steps}")
        logger.info(f"  ✅ 成功: {self.successful_steps}")
        logger.info(f"  ❌ 失败: {self.failed_steps}")
        logger.info(f"  ⏭️  跳过: {self.skipped_steps}")
        logger.info(f"总重试次数: {self.total_retries}")
        logger.info(f"总耗时: {self.total_time:.2f}s")
        logger.info("=" * 60)


class Executor:
    """改进的任务执行器 - 完整的循环处理引擎"""

    def __init__(self, tools, memory):
        """
        初始化执行器

        Args:
            tools: 工具注册中心
            memory: 记忆管理器
        """
        self.tools = tools
        self.memory = memory
        self.execution_cache = {}      # 执行结果缓存
        self.execution_history = []    # 执行历史
        self.metrics = ExecutionMetrics()
        self.temporary_resources = [] # 临时资源列表

    def execute_plan(self, plan: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        执行计划 - 完整的循环处理引擎

        Args:
            plan: 执行计划列表

        Returns:
            执行结果列表
        """
        logger.info("开始执行计划（改进的循环处理引擎）...")
        start_time = time.time()

        # 初始化
        execution_results = []
        pending_steps = list(plan)
        context = self._build_initial_context()
        iteration = 0
        max_iterations = len(plan) * 5  # 防止无限循环

        try:
            # ✅ 主循环：处理所有待处理步骤
            while pending_steps and iteration < max_iterations:
                iteration += 1
                step = pending_steps.pop(0)
                step_id = step.get('id')

                logger.debug(f"处理步骤 {step_id} (迭代 {iteration}/{max_iterations})")

                # ✅ 循环 1：依赖检查
                if not self._check_dependencies(step, self.execution_cache):
                    logger.info(f"⏳ 步骤 {step_id} 依赖未满足，重新入队")
                    pending_steps.append(step)
                    continue

                # ✅ 循环 2：重试循环（可配置）
                result = self._execute_with_retry(
                    step=step,
                    context=context,
                    max_retries=3,
                    backoff_strategy='exponential'
                )

                # ✅ 循环 3：本地验证（无需 LLM）
                if result['status'] == 'success':
                    self._local_validate(step, result)

                # 记录执行结果
                execution_results.append(result)
                self.execution_cache[step_id] = result
                self.execution_history.append(result)

                # ✅ 更新上下文以供后续步骤使用
                context = self._update_context(context, step_id, result)

                # 记录指标
                step_time = result.get('execution_time', 0)
                self.metrics.add_step(step_id, result['status'], step_time)

        finally:
            # ✅ 清理资源
            self._cleanup_resources()

        # 完成
        total_time = time.time() - start_time
        self.metrics.total_time = total_time

        if iteration >= max_iterations:
            logger.warning(f"⚠️  达到最大迭代次数 ({max_iterations})，可能存在循环依赖")

        logger.info(f"✅ 计划执行完成 | 共执行 {len(execution_results)} 个步骤，耗时 {total_time:.2f}s")
        self.metrics.print_summary()

        return execution_results

    # ============ 循环 1：依赖检查 ============

    def _check_dependencies(self, step: Dict[str, Any], cache: Dict[int, Dict]) -> bool:
        """
        循环 1：检查步骤的依赖是否满足

        Args:
            step: 步骤信息
            cache: 执行结果缓存

        Returns:
            依赖是否满足
        """
        dependencies = step.get('dependencies', [])

        if not dependencies:
            return True

        for dep_id in dependencies:
            # 依赖未执行
            if dep_id not in cache:
                logger.debug(f"步骤 {step['id']} 依赖 {dep_id} 未执行")
                return False

            # 依赖执行失败
            dep_result = cache[dep_id]
            if dep_result.get('status') != 'success':
                logger.error(f"步骤 {step['id']} 的依赖 {dep_id} 失败，无法继续")
                return False

        return True

    # ============ 循环 2：重试循环 ============

    def _execute_with_retry(
        self,
        step: Dict[str, Any],
        context: Dict[str, Any],
        max_retries: int = 3,
        backoff_strategy: str = 'exponential'
    ) -> Dict[str, Any]:
        """
        循环 2：带重试的执行

        Args:
            step: 步骤信息
            context: 上下文（用于变量替换）
            max_retries: 最大重试次数
            backoff_strategy: 退避策略 ('exponential' | 'linear' | 'fixed')

        Returns:
            执行结果
        """
        step_id = step.get('id')
        last_error = None
        last_result = None

        for attempt in range(max_retries):
            try:
                # 计算退避时间
                if attempt > 0:
                    wait_time = self._calculate_backoff(attempt, backoff_strategy)
                    logger.info(f"⏳ 等待 {wait_time:.2f}s 后进行第 {attempt + 1} 次重试...")
                    time.sleep(wait_time)

                # 执行步骤
                result = self._execute_step(step, context=context)
                last_result = result

                # 快速验证
                if self._quick_check_success(step, result):
                    logger.info(f"✅ 步骤 {step_id} 执行成功 (第 {attempt + 1} 次尝试)")
                    result['retry_count'] = attempt
                    return result

                # 快速验证失败但不是执行错误
                if result['status'] != 'failed':
                    last_error = f"快速验证未通过: {result.get('reason', '未知')}"
                    continue

                last_error = result.get('error', '执行失败')

            except Exception as e:
                last_error = str(e)
                logger.warning(f"第 {attempt + 1} 次尝试异常: {e}")

        # 重试耗尽，尝试恢复策略
        self.metrics.total_retries += max_retries
        logger.error(f"步骤 {step_id} 经过 {max_retries} 次重试仍然失败: {last_error}")

        # ✅ 尝试恢复策略
        recovery_result = self._try_recovery_strategies(step, last_error, context)
        if recovery_result:
            return recovery_result

        # 所有恢复都失败
        return {
            "step_id": step_id,
            "goal": step.get("goal"),
            "tool": step.get("tool"),
            "args": step.get("args"),
            "error": last_error,
            "status": "failed",
            "attempts": max_retries,
            "recovery_attempted": True
        }

    def _calculate_backoff(self, attempt: int, strategy: str = 'exponential') -> float:
        """计算退避时间"""
        if strategy == 'exponential':
            return min(2 ** attempt, 30)  # 1s, 2s, 4s, 8s... 最多 30s
        elif strategy == 'linear':
            return attempt  # 1s, 2s, 3s...
        else:  # fixed
            return 1.0

    # ============ 循环 3：本地验证 ============

    def _local_validate(self, step: Dict[str, Any], result: Dict[str, Any]) -> bool:
        """
        循环 3：本地验证（快速，无需 LLM）

        Args:
            step: 步骤信息
            result: 执行结果

        Returns:
            是否验证通过
        """
        if result.get('status') != 'success':
            return False

        tool_name = step.get('tool')
        tool_result = result.get('result', {})

        # 根据工具类型做快速验证
        if tool_name == 'write_file':
            return True  # write_file 成功就认为通过

        if tool_name == 'read_file':
            return isinstance(tool_result, dict) and 'content' in tool_result

        if tool_name == 'run_shell':
            return isinstance(tool_result, dict) and tool_result.get('returncode') == 0

        if tool_name == 'file_exists':
            return isinstance(tool_result, dict) and 'exists' in tool_result

        if tool_name == 'list_dir':
            return isinstance(tool_result, dict) and 'items' in tool_result

        if tool_name == 'delete_file':
            return True  # delete_file 成功就认为通过

        return True  # 默认认为通过

    def _quick_check_success(self, step: Dict[str, Any], result: Dict[str, Any]) -> bool:
        """快速检查步骤是否成功"""
        return result.get('status') == 'success' and self._local_validate(step, result)

    # ============ 循环 4：异常恢复策略 ============

    def _try_recovery_strategies(
        self,
        step: Dict[str, Any],
        error: str,
        context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        循环 4：尝试异常恢复策略

        Args:
            step: 步骤信息
            error: 错误信息
            context: 上下文

        Returns:
            恢复后的结果，如果恢复失败则返回 None
        """
        step_id = step.get('id')
        tool_name = step.get('tool')

        # 定义恢复策略
        strategies = [
            ('adjust_params', self._strategy_adjust_params),
            ('fallback_tool', self._strategy_fallback_tool),
            ('skip', self._strategy_skip),
        ]

        for strategy_name, strategy_func in strategies:
            try:
                logger.info(f"🔧 尝试恢复策略: {strategy_name}")
                result = strategy_func(step, error, context)

                if result and result.get('status') == 'success':
                    logger.info(f"✅ 恢复成功: {strategy_name}")
                    result['recovery_strategy'] = strategy_name
                    return result

            except Exception as e:
                logger.warning(f"❌ 恢复策略失败: {strategy_name} - {e}")
                continue

        return None

    def _strategy_adjust_params(
        self,
        step: Dict[str, Any],
        error: str,
        context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """恢复策略 1：调整参数后重试"""
        step_id = step.get('id')
        tool_name = step.get('tool')
        args = step.get('args', {})

        logger.info(f"尝试调整参数重新执行步骤 {step_id}")

        # 根据工具类型进行参数调整
        adjusted_args = self._adjust_args_by_tool(tool_name, args, error)

        if adjusted_args == args:
            return None  # 没有可调整的参数

        # 用调整后的参数重新执行
        adjusted_step = dict(step)
        adjusted_step['args'] = adjusted_args

        try:
            result = self._execute_step(adjusted_step, context=context)
            if self._quick_check_success(adjusted_step, result):
                result['args'] = adjusted_args  # 记录调整后的参数
                return result
        except Exception as e:
            logger.warning(f"调整参数后仍然失败: {e}")

        return None

    def _adjust_args_by_tool(self, tool_name: str, args: Dict, error: str) -> Dict:
        """根据工具类型调整参数"""
        adjusted = dict(args)

        if tool_name == 'run_shell':
            # 如果是权限错误，尝试加 sudo
            if 'permission' in error.lower() or 'denied' in error.lower():
                if 'command' in adjusted:
                    adjusted['command'] = f"sudo {adjusted['command']}"

        elif tool_name == 'read_file':
            # 如果找不到文件，尝试添加路径前缀
            if 'no such file' in error.lower():
                if 'path' in adjusted:
                    adjusted['path'] = f"./{adjusted['path']}"

        return adjusted

    def _strategy_fallback_tool(
        self,
        step: Dict[str, Any],
        error: str,
        context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """恢复策略 2：使用备用工具"""
        tool_name = step.get('tool')
        fallback_tool = self._get_fallback_tool(tool_name)

        if not fallback_tool:
            return None

        logger.info(f"尝试用备用工具 {fallback_tool} 代替 {tool_name}")

        fallback_step = dict(step)
        fallback_step['tool'] = fallback_tool
        fallback_step['args'] = self._convert_args_for_fallback(tool_name, fallback_tool, step.get('args', {}))

        try:
            result = self._execute_step(fallback_step, context=context)
            if self._quick_check_success(fallback_step, result):
                return result
        except Exception as e:
            logger.warning(f"备用工具也失败: {e}")

        return None

    def _get_fallback_tool(self, tool_name: str) -> Optional[str]:
        """获取备用工具"""
        fallback_map = {
            'read_file': 'run_shell',  # 无法读文件，尝试用 shell 命令
            'write_file': 'run_shell',
            'list_dir': 'run_shell',
            'delete_file': 'run_shell',
            'file_exists': 'run_shell',
        }
        return fallback_map.get(tool_name)

    def _convert_args_for_fallback(self, original_tool: str, fallback_tool: str, args: Dict) -> Dict:
        """转换参数以适应备用工具"""
        if fallback_tool != 'run_shell':
            return args

        # 转换为 shell 命令
        if original_tool == 'read_file':
            return {'command': f"cat {args.get('path', '')}"}

        elif original_tool == 'write_file':
            path = args.get('path', '')
            content = args.get('content', '').replace("'", "'\\''")
            return {'command': f"echo '{content}' > {path}"}

        elif original_tool == 'list_dir':
            return {'command': f"ls -la {args.get('path', '.')}"}

        elif original_tool == 'delete_file':
            return {'command': f"rm {args.get('path', '')}"}

        elif original_tool == 'file_exists':
            return {'command': f"test -e {args.get('path', '')} && echo exists || echo not_exists"}

        return args

    def _strategy_skip(
        self,
        step: Dict[str, Any],
        error: str,
        context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """恢复策略 3：跳过此步骤"""
        step_id = step.get('id')
        logger.warning(f"⏭️  跳过步骤 {step_id}")

        return {
            "step_id": step_id,
            "goal": step.get("goal"),
            "tool": step.get("tool"),
            "status": "skipped",
            "reason": f"由于错误而跳过: {error}"
        }

    # ============ 循环 5：资源管理 ============

    def _cleanup_resources(self):
        """清理临时资源"""
        if not self.temporary_resources:
            return

        logger.debug(f"清理 {len(self.temporary_resources)} 个临时资源")
        for resource in self.temporary_resources:
            try:
                import os
                if os.path.exists(resource):
                    os.remove(resource)
                    logger.debug(f"已删除临时文件: {resource}")
            except Exception as e:
                logger.warning(f"清理资源失败: {resource} - {e}")

        self.temporary_resources.clear()

    # ============ 上下文和变量处理 ============

    def _build_initial_context(self) -> Dict[str, Any]:
        """构建初始上下文"""
        return {
            'steps': {},
            'latest_result': None
        }

    def _update_context(self, context: Dict, step_id: int, result: Dict) -> Dict:
        """更新上下文以供后续步骤使用"""
        context['steps'][f'step_{step_id}'] = result
        context['latest_result'] = result
        return context

    def _execute_step(
        self,
        step: Dict[str, Any],
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        执行单个步骤，支持上下文传播和变量替换

        Args:
            step: 步骤信息
            context: 上下文（用于变量替换）

        Returns:
            执行结果
        """
        if context is None:
            context = {}

        step_id = step.get('id')
        tool_name = step.get("tool", "none")
        args = step.get("args", {})
        start_time = time.time()

        logger.info(f"➡️ 执行步骤 {step_id}: {step.get('goal')}")

        try:
            # 检查工具是否有效
            if tool_name == "none" or not tool_name:
                logger.warning("⚠️ 未指定工具，跳过执行")
                return {
                    "step_id": step_id,
                    "status": "skipped",
                    "reason": "未指定工具",
                    "execution_time": time.time() - start_time
                }

            # ✅ 变量替换：用上下文中的值替换参数中的占位符
            resolved_args = self._resolve_variables(args, context)

            logger.info(f"🧩 调用工具: {tool_name} 参数: {resolved_args}")

            # 初始化工具注册中心（如果需要）
            if not hasattr(self.tools, '_initialized') or not self.tools._initialized:
                self.tools.initialize()

            # 获取工具并执行
            tool_func = self.tools.get_tool(tool_name)
            tool_result = tool_func(**resolved_args)

            logger.info(f"✅ 工具执行成功")

            # 构建成功结果
            result = {
                "step_id": step_id,
                "goal": step.get("goal"),
                "tool": tool_name,
                "args": resolved_args,
                "result": tool_result,
                "status": "success",
                "execution_time": time.time() - start_time
            }

            # 保存观察结果
            self.memory.add_observation(result)
            return result

        except Exception as e:
            logger.error(f"❌ 执行失败: {e}")

            # 构建失败结果
            result = {
                "step_id": step_id,
                "goal": step.get("goal"),
                "tool": tool_name,
                "args": args,
                "error": str(e),
                "status": "failed",
                "execution_time": time.time() - start_time
            }

            # 保存观察结果
            self.memory.add_observation(result)
            return result

    def _resolve_variables(self, args: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        变量替换：用上下文中的值替换参数中的占位符

        支持的占位符格式：
        - ${step_1.result.content}  - 步骤 1 的结果中的 content 字段
        - ${latest_result.path}     - 最近步骤的结果
        - ${steps.step_1.result}    - 步骤 1 的完整结果

        Args:
            args: 原始参数
            context: 上下文

        Returns:
            替换后的参数
        """
        resolved = {}

        for key, value in args.items():
            if isinstance(value, str):
                resolved[key] = self._replace_variables_in_string(value, context)
            elif isinstance(value, dict):
                resolved[key] = self._resolve_variables(value, context)
            elif isinstance(value, list):
                resolved[key] = [
                    self._replace_variables_in_string(v, context) if isinstance(v, str) else v
                    for v in value
                ]
            else:
                resolved[key] = value

        return resolved

    def _replace_variables_in_string(self, value: str, context: Dict[str, Any]) -> str:
        """替换字符串中的占位符"""
        if not isinstance(value, str):
            return value

        # 匹配 ${...} 格式的占位符
        pattern = r'\$\{([^}]+)\}'

        def replace_func(match):
            var_path = match.group(1)
            resolved_value = self._get_from_context(var_path, context)
            return str(resolved_value) if resolved_value is not None else match.group(0)

        return re.sub(pattern, replace_func, value)

    def _get_from_context(self, path: str, context: Dict[str, Any]) -> Any:
        """
        从上下文中获取值，支持嵌套路径

        例如：
        - step_1.result.content
        - latest_result.path
        - steps.step_1.result

        Args:
            path: 路径（使用 . 分隔）
            context: 上下文

        Returns:
            值，如果不存在返回 None
        """
        parts = path.split('.')
        value = context

        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return None

            if value is None:
                return None

        return value

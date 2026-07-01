from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from datacollector.agent.models import RunResult, StepRecord, TaskMemory, TaskSpec
from datacollector.browser.runtime import BrowserRuntime
from datacollector.config import RuntimeConfig
from datacollector.models import ToolOutput, create_model_client
from datacollector.observability import RunLogger
from datacollector.runtime.safety import SafetyGuard
from datacollector.storage import SQLiteRunStore
from datacollector.tools.playwright_tools import BrowserToolRegistry


SYSTEM_PROMPT = """You are an AI browser automation agent.

Use the provided browser tools to complete the user's task.
Before acting, use the page observation in the user message.
Prefer robust selectors. Avoid destructive or high-risk actions unless the task explicitly asks for them.
If a tool reports that confirmation is required, stop and explain the confirmation that is needed.
If an output schema is provided, make your final answer conform to it as closely as possible.
Never reveal API keys, cookies, passwords, tokens, or other secrets in your final answer.
When the task is complete, return a concise final answer without calling more tools.
"""


class AgentRunner:
    def __init__(self, config: RuntimeConfig | None = None) -> None:
        self.config = config or RuntimeConfig.from_env()

    async def run(self, task: TaskSpec) -> RunResult:
        async with BrowserRuntime(self.config.browser) as runtime:
            return await self.run_with_runtime(task, runtime)

    async def run_with_runtime(
        self,
        task: TaskSpec,
        runtime: BrowserRuntime,
        artifact_parent: Path | None = None,
    ) -> RunResult:
        if not runtime.browser:
            await runtime.start()

        started_at = datetime.now()
        run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8]
        artifact_dir = (artifact_parent or self.config.output_dir) / run_id
        artifact_dir.mkdir(parents=True, exist_ok=True)

        logger = RunLogger(artifact_dir)
        logger.write_metadata(
            {
                "run_id": run_id,
                "task": task.model_dump(mode="json"),
                "config": self.config.to_safe_dict(),
                "started_at": started_at.isoformat(),
            }
        )
        logger.event("run_started", run_id=run_id, task=task.model_dump(mode="json"))

        steps: list[StepRecord] = []
        memory = TaskMemory(goal=task.instruction)
        safety = SafetyGuard(self.config.agent)
        tools = BrowserToolRegistry(runtime, artifact_dir, safety)

        trace_path = artifact_dir / "trace.zip"
        tracing_started = False
        if self.config.agent.trace_enabled:
            try:
                await runtime.start_tracing()
                tracing_started = True
                logger.event("trace_started")
            except Exception as exc:
                logger.event("trace_start_failed", error=f"{type(exc).__name__}: {exc}")

        if task.url:
            navigation_safety = safety.check_navigation(task.url)
            if not navigation_safety.allowed:
                finished_at = datetime.now()
                result = RunResult(
                    run_id=run_id,
                    success=False,
                    task=task,
                    started_at=started_at,
                    finished_at=finished_at,
                    steps=steps,
                    memory=memory,
                    final_message=navigation_safety.reason,
                    artifact_dir=str(artifact_dir),
                    artifacts=logger.artifacts,
                )
                self._finalize_result(result, logger)
                return result
            await runtime.require_page().goto(task.url, wait_until="domcontentloaded")

        try:
            final_message = await asyncio.wait_for(
                self._run_loop(task, runtime, tools, steps, memory, artifact_dir, logger),
                timeout=self.config.agent.task_timeout_seconds,
            )
            success = not any(step.status == "requires_human_intervention" for step in steps)
        except Exception as exc:
            final_message = f"任务失败: {type(exc).__name__}: {exc}"
            memory.failures.append(final_message)
            logger.event("run_failed", error=final_message)
            success = False
        finally:
            if tracing_started:
                try:
                    await runtime.stop_tracing(trace_path)
                    logger.artifact("trace", trace_path, "Playwright trace")
                    logger.event("trace_saved", path=str(trace_path))
                except Exception as exc:
                    logger.event("trace_save_failed", error=f"{type(exc).__name__}: {exc}")

        finished_at = datetime.now()
        result = RunResult(
            run_id=run_id,
            success=success,
            task=task,
            started_at=started_at,
            finished_at=finished_at,
            steps=steps,
            memory=memory,
            final_message=final_message,
            artifact_dir=str(artifact_dir),
            artifacts=logger.artifacts,
        )
        self._finalize_result(result, logger)
        return result

    async def _run_loop(
        self,
        task: TaskSpec,
        runtime: BrowserRuntime,
        tools: BrowserToolRegistry,
        steps: list[StepRecord],
        memory: TaskMemory,
        artifact_dir: Path,
        logger: RunLogger,
    ) -> str:
        if self.config.model.provider != "openai":
            raise ValueError(f"unsupported model provider: {self.config.model.provider}")

        model_client = None
        pending_tool_outputs: list[ToolOutput] = []
        initial_input = self._initial_input(task)
        final_text = ""

        for index in range(1, self.config.agent.max_steps + 1):
            screenshot_path = artifact_dir / f"observe-{index:03d}.png"
            observation = await runtime.observe(screenshot_path)
            logger.artifact("screenshot", screenshot_path, f"Observation screenshot for step {index}")
            logger.event(
                "step_observed",
                step=index,
                url=observation.url,
                title=observation.title,
                screenshot_path=str(screenshot_path),
                human_intervention=observation.human_intervention.model_dump(mode="json")
                if observation.human_intervention
                else None,
            )
            if observation.human_intervention:
                message = self._human_intervention_message(observation)
                steps.append(
                    StepRecord(
                        index=index,
                        observation=observation,
                        assistant_message=message,
                        status="requires_human_intervention",
                    )
                )
                memory.failures.append(message)
                logger.event(
                    "human_intervention_required",
                    step=index,
                    category=observation.human_intervention.category,
                    reason=observation.human_intervention.reason,
                    url=observation.url,
                )
                return message
            if model_client is None:
                model_client = create_model_client(self.config.model, SYSTEM_PROMPT)
            user_text = self._build_turn_input(
                initial_input=initial_input,
                task=task,
                observation=observation,
                is_first_turn=index == 1,
            )
            turn = await model_client.turn(
                user_text=user_text,
                tool_outputs=pending_tool_outputs,
                tools=tools.openai_tool_definitions,
            )
            tool_calls = turn.tool_calls
            final_text = turn.text or final_text

            if not tool_calls:
                steps.append(
                    StepRecord(
                        index=index,
                        observation=observation,
                        assistant_message=final_text,
                        status="completed",
                    )
                )
                logger.event("run_completed", step=index, final_message=final_text)
                return final_text or "任务已完成。"

            pending_tool_outputs = []
            for call in tool_calls:
                result = await tools.execute(call.name, call.arguments)
                logger.tool_call(
                    step=index,
                    name=call.name,
                    arguments=tools.safety.mask_arguments(call.arguments),
                    result=result.model_dump(mode="json"),
                )
                if result.screenshot_path:
                    logger.artifact("screenshot", result.screenshot_path, f"{call.name} screenshot")
                if "path" in result.data:
                    logger.artifact(call.name, result.data["path"], result.message)
                steps.append(
                    StepRecord(
                        index=index,
                        observation=observation,
                        tool_name=call.name,
                        tool_arguments=tools.safety.mask_arguments(call.arguments),
                        tool_result=result.model_dump(mode="json"),
                        assistant_message=final_text,
                        status="completed" if result.success else "failed",
                        error=None if result.success else result.message,
                    )
                )
                if result.success:
                    memory.completed_actions.append(f"{call.name}: {result.message}")
                    self._remember_extracted_data(memory, call.name, result.data)
                else:
                    memory.failures.append(f"{call.name}: {result.message}")
                pending_tool_outputs.append(
                    ToolOutput(call_id=call.call_id, output=result.model_dump_json())
                )

        logger.event("max_steps_reached", max_steps=self.config.agent.max_steps)
        return final_text or f"已达到最大步骤数 {self.config.agent.max_steps}，任务停止。"

    def _initial_input(self, task: TaskSpec) -> str:
        schema_note = ""
        if task.output_schema:
            schema_note = f"\nExpected output schema:\n{json.dumps(task.output_schema, ensure_ascii=False)}"
        url_note = f"\nInitial URL: {task.url}" if task.url else ""
        return f"Task: {task.instruction}{url_note}{schema_note}"

    def _build_turn_input(
        self,
        initial_input: str,
        task: TaskSpec,
        observation: Any,
        is_first_turn: bool,
    ) -> str:
        observation_text = (
            "Current page observation:\n"
            f"URL: {observation.url}\n"
            f"Title: {observation.title}\n"
            f"Screenshot: {observation.screenshot_path}\n"
            f"Text summary: {observation.text_summary}\n"
            "Interactive elements:\n"
            + "\n".join(self._format_element(element) for element in observation.interactive_elements[:80])
            + "\nLinks:\n"
            + "\n".join(f"- {link.text}: {link.href}" for link in observation.links[:30])
            + "\nTables:\n"
            + "\n".join(
                f"- table {table.index}: rows={table.row_count}, headers={table.headers[:8]}"
                for table in observation.tables[:10]
            )
            + "\nVisible text:\n"
            + observation.text[:6000]
        )
        if is_first_turn:
            return initial_input + "\n\n" + observation_text
        return f"Continue task: {task.instruction}\n\n{observation_text}"

    def _format_element(self, element: Any) -> str:
        return (
            f"{element.index}: <{element.tag}> role={element.role} type={element.type} "
            f"selector={element.selector_hint} text=\"{element.text}\" href=\"{element.href}\""
        )

    def _human_intervention_message(self, observation: Any) -> str:
        intervention = observation.human_intervention
        category = "登录" if intervention.category == "login" else "人机/安全验证"
        hints = [
            f"检测到当前页面需要人工处理：{category}。",
            f"原因：{intervention.reason}",
            f"当前页面：{observation.url}",
            "我已经暂停自动操作，避免反复刷新或重复进入页面。",
            "请在已打开的浏览器窗口中完成登录或验证，完成后回到控制台输入“继续”或你的下一步需求。",
            "登录态会自动保存到 storage state，下次启动会优先复用，减少重复登录。",
        ]
        if self.config.browser.headless:
            hints.append("当前是无头模式；如需手动处理，请用 --headed 或不要传 --headless 启动。")
        if intervention.evidence:
            hints.append("检测依据：" + ", ".join(intervention.evidence[:5]))
        return "\n".join(hints)

    def _remember_extracted_data(
        self,
        memory: TaskMemory,
        tool_name: str,
        data: dict[str, Any],
    ) -> None:
        extraction_keys = {"text", "lists", "tables", "links", "media"}
        if tool_name.startswith("extract_") or extraction_keys.intersection(data.keys()):
            memory.extracted_data.append({"tool": tool_name, "data": data})

    def _finalize_result(self, result: RunResult, logger: RunLogger) -> None:
        result_path = Path(result.artifact_dir) / "result.json"
        logger.artifact("result", result_path, "Final run result")
        result.artifacts = logger.artifacts
        result_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        logger.event(
            "run_finished",
            run_id=result.run_id,
            success=result.success,
            final_message=result.final_message,
        )
        database_path = self.config.database_path or (self.config.output_dir / "datacollector.sqlite3")
        SQLiteRunStore(database_path).save_run(result)

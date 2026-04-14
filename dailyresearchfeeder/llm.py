from __future__ import annotations

import asyncio
import json
import re
import shutil
from typing import Any

from openai import AsyncAzureOpenAI, AsyncOpenAI

from dailyresearchfeeder.models import CandidateItem


class ReasoningClient:
    def __init__(
        self,
        provider: str,
        api_key: str,
        base_url: str,
        azure_endpoint: str,
        azure_api_version: str,
        azure_deployment: str,
        model: str,
        reasoning_effort: str,
        timeout_seconds: int,
        copilot_command: str,
    ) -> None:
        self.provider = provider
        self.api_key = api_key
        self.base_url = base_url
        self.azure_endpoint = azure_endpoint
        self.azure_api_version = azure_api_version
        self.azure_deployment = azure_deployment or model
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.timeout_seconds = timeout_seconds
        self.copilot_command = copilot_command
        self.client = None
        if provider == "openai":
            self.client = AsyncOpenAI(api_key=api_key, base_url=base_url or None, timeout=timeout_seconds)
        elif provider == "azure_openai":
            self.client = AsyncAzureOpenAI(
                api_key=api_key,
                azure_endpoint=azure_endpoint,
                api_version=azure_api_version,
                timeout=timeout_seconds,
            )

    async def score_candidates(
        self,
        items: list[CandidateItem],
        research_interests: str,
        keywords: list[str],
        language: str,
        batch_size: int,
    ) -> list[CandidateItem]:
        if not items:
            return []
        if not self._provider_is_ready():
            return self._heuristic_score(items, keywords, error_note=f"{self.provider} backend unavailable")

        reviewed: list[CandidateItem] = []
        for start in range(0, len(items), batch_size):
            batch = items[start : start + batch_size]
            try:
                reviewed.extend(
                    await self._score_batch(
                        batch=batch,
                        research_interests=research_interests,
                        keywords=keywords,
                        language=language,
                    )
                )
            except Exception as exc:
                reviewed.extend(self._heuristic_score(batch, keywords, error_note=str(exc)))

        return sorted(reviewed, key=lambda item: item.relevance_score, reverse=True)

    async def compose_overview(
        self,
        papers: list[CandidateItem],
        news: list[CandidateItem],
        keywords: list[str],
        research_interests: str,
    ) -> tuple[str, list[str]]:
        if not papers and not news:
            return (
                "今天没有命中关键词且通过阈值的新内容，建议扩大关键词或放宽分数阈值。",
                ["没有命中高分论文", "没有命中高分动态", "可以考虑增加同义词和相关领域词"],
            )

        if not self._provider_is_ready():
            overview = (
                f"今天筛到 {len(papers)} 篇论文、{len(news)} 条动态。当前为无模型回退摘要，"
                "建议补全模型后端配置后再看正式版本。"
            )
            return overview, ["回退模式未生成深度判断", "筛选主要依赖关键词", "建议补全模型后端配置"]

        catalog_lines = []
        for index, item in enumerate(papers + news, start=1):
            catalog_lines.append(
                f"{index}. [{item.kind.value}] {item.title}\n"
                f"   Source: {item.source_name}\n"
                f"   Score: {item.relevance_score:.1f}\n"
                f"   Summary: {item.digest_summary or item.summary[:220]}\n"
                f"   Why it matters: {item.why_now or item.importance}"
            )

        system_prompt = (
            "You are writing a concise Chinese daily research digest overview for a technically sophisticated reader. "
            "Focus on signal, not hype."
        )
        user_prompt = (
            f"Research interests:\n{research_interests}\n\n"
            f"Keywords:\n- " + "\n- ".join(keywords) + "\n\n"
            "Selected items:\n" + "\n\n".join(catalog_lines) + "\n\n"
            "Return JSON only with this schema:\n"
            '{"overview":"one Chinese paragraph",'
            '"takeaways":["takeaway 1","takeaway 2","takeaway 3"]}'
        )

        raw_text = await self._request(system_prompt, user_prompt, max_output_tokens=1200)
        payload = self._parse_json_object(raw_text)
        overview = str(payload.get("overview", "")).strip()
        takeaways = [str(item).strip() for item in payload.get("takeaways", []) if str(item).strip()]
        if not overview:
            overview = f"今天筛到 {len(papers)} 篇论文、{len(news)} 条动态，整体方向与关键词高度相关。"
        if not takeaways:
            takeaways = ["重点关注高分论文", "保留值得跟进的产业动态", "建议继续迭代关键词"]
        return overview, takeaways[:3]

    async def _score_batch(
        self,
        batch: list[CandidateItem],
        research_interests: str,
        keywords: list[str],
        language: str,
    ) -> list[CandidateItem]:
        item_blocks = []
        for index, item in enumerate(batch, start=1):
            published = item.published_at.isoformat() if item.published_at else "unknown"
            authors = ", ".join(item.authors[:6]) if item.authors else "unknown"
            item_blocks.append(
                f"Item {index}\n"
                f"Type: {item.kind.value}\n"
                f"Source: {item.source_name} ({item.source_group})\n"
                f"Published: {published}\n"
                f"Title: {item.title}\n"
                f"Authors: {authors}\n"
                f"Summary: {item.summary[:1400]}\n"
                f"Initial matched keywords: {', '.join(item.matched_keywords) if item.matched_keywords else 'none'}\n"
                f"URL: {item.url}"
            )

        system_prompt = (
            "You are a senior research scout for frontier AI systems. "
            "Score each item for a reader who specifically wants papers and technical updates about agent skills, "
            "tool use, evaluation harnesses, presentation/design agents, and RL environments for agents. "
            "Be skeptical of marketing copy, but do not be too narrow: semantically adjacent work, major AI industry news, "
            "important launches from top labs/companies, and very recent high-signal items should receive meaningful credit."
        )
        user_prompt = (
            f"Preferred output language: {language}\n\n"
            f"Research interests:\n{research_interests}\n\n"
            f"Keywords:\n- " + "\n- ".join(keywords) + "\n\n"
            "Evaluate all items below. Return JSON only as an array.\n"
            "Each object must follow this schema:\n"
            "{\n"
            '  "item_id": 1,\n'
            '  "score": 0-10,\n'
            '  "decision": "keep|maybe|skip",\n'
            '  "matched_topics": ["topic"],\n'
            '  "digest_summary": "2-3 sentence Chinese summary",\n'
            '  "importance": "one Chinese sentence on the core contribution",\n'
            '  "why_now": "one Chinese sentence on why this matters now",\n'
            '  "reasoning": "brief Chinese explanation"\n'
            "}\n\n"
            "Scoring guidance:\n"
            "- 9-10: directly aligned and materially useful\n"
            "- 7-8.9: relevant and worth reading today\n"
            "- 5-6.9: adjacent but still useful, or major AI news worth tracking\n"
            "- below 5: skip\n\n"
            "Prefer technical substance, training/system novelty, real infrastructure lessons, strong research insight, or major ecosystem impact. "
            "Use recency and source credibility as tie-breakers.\n\n"
            + "\n\n".join(item_blocks)
        )

        raw_text = await self._request(system_prompt, user_prompt, max_output_tokens=4000)
        payload = self._parse_json_array(raw_text)
        reviewed_by_id = {int(item.get("item_id", 0)): item for item in payload if str(item.get("item_id", "")).isdigit()}

        reviewed_items: list[CandidateItem] = []
        for index, item in enumerate(batch, start=1):
            response = reviewed_by_id.get(index)
            if response is None:
                item.relevance_score = max(item.relevance_score, 5.0 if item.matched_keywords else 3.0)
                item.decision = "maybe" if item.matched_keywords else "skip"
                item.importance = "模型返回缺失，保留为回退判断。"
                item.why_now = "建议手动复核。"
                item.digest_summary = item.summary[:220]
                item.reasoning = "LLM response missing for this item."
                reviewed_items.append(item)
                continue

            item.relevance_score = float(response.get("score", 0.0))
            item.decision = str(response.get("decision", "skip")).strip().lower()
            item.importance = str(response.get("importance", "")).strip()
            item.why_now = str(response.get("why_now", "")).strip()
            item.digest_summary = str(response.get("digest_summary", "")).strip() or item.summary[:220]
            item.reasoning = str(response.get("reasoning", "")).strip()
            extra_topics = [str(topic).strip() for topic in response.get("matched_topics", []) if str(topic).strip()]
            item.matched_keywords = list(dict.fromkeys(item.matched_keywords + extra_topics))
            item.debug_payload = response
            reviewed_items.append(item)

        return reviewed_items

    async def _request(self, system_prompt: str, user_prompt: str, max_output_tokens: int) -> str:
        if self.provider == "copilot_cli":
            return await self._request_copilot(system_prompt, user_prompt)
        if self.provider == "azure_openai":
            return await self._request_azure_chat(system_prompt, user_prompt, max_output_tokens)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "instructions": system_prompt,
            "input": user_prompt,
            "max_output_tokens": max_output_tokens,
        }
        if self.reasoning_effort:
            kwargs["reasoning"] = {"effort": self.reasoning_effort}

        try:
            response = await self.client.responses.create(**kwargs)
        except Exception as exc:
            if "reasoning" in str(exc).lower() or "effort" in str(exc).lower():
                kwargs.pop("reasoning", None)
                response = await self.client.responses.create(**kwargs)
            else:
                raise

        text = getattr(response, "output_text", "")
        if text:
            return text

        chunks: list[str] = []
        for output in getattr(response, "output", []) or []:
            for content in getattr(output, "content", []) or []:
                if getattr(content, "type", "") in {"output_text", "text"}:
                    value = getattr(content, "text", "")
                    if isinstance(value, str):
                        chunks.append(value)
                    elif hasattr(value, "value"):
                        chunks.append(str(value.value))
        return "\n".join(chunks)

    async def _request_azure_chat(self, system_prompt: str, user_prompt: str, max_output_tokens: int) -> str:
        kwargs: dict[str, Any] = {
            "model": self.azure_deployment,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_completion_tokens": max_output_tokens,
        }
        if self.reasoning_effort:
            kwargs["reasoning_effort"] = self.reasoning_effort

        try:
            response = await self.client.chat.completions.create(**kwargs)
        except Exception as exc:
            if "reasoning" in str(exc).lower() or "effort" in str(exc).lower():
                kwargs.pop("reasoning_effort", None)
                response = await self.client.chat.completions.create(**kwargs)
            else:
                raise

        if not response.choices:
            return ""

        message = response.choices[0].message
        content = getattr(message, "content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            chunks: list[str] = []
            for item in content:
                text = getattr(item, "text", None)
                if text:
                    chunks.append(str(text))
                elif isinstance(item, dict) and item.get("type") == "text":
                    chunks.append(str(item.get("text", "")))
            return "\n".join(chunk for chunk in chunks if chunk)
        return str(content)

    async def _request_copilot(self, system_prompt: str, user_prompt: str) -> str:
        prompt = (
            "You are operating in non-interactive CLI mode. Do not use tools. "
            "Answer directly from the prompt and return only the requested content.\n\n"
            f"System instructions:\n{system_prompt}\n\n"
            f"User request:\n{user_prompt}"
        )
        command = shutil.which(self.copilot_command) or self.copilot_command
        process = await asyncio.create_subprocess_exec(
            command,
            "-p",
            prompt,
            "-s",
            "--stream",
            "off",
            "--output-format",
            "text",
            "--allow-all-tools",
            "--allow-all-paths",
            "--allow-all-urls",
            "--no-custom-instructions",
            "--no-ask-user",
            "--model",
            self.model,
            "--reasoning-effort",
            self.reasoning_effort,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout_seconds)
        except asyncio.TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise TimeoutError("Copilot CLI request timed out") from exc

        if process.returncode != 0:
            raise RuntimeError(
                f"Copilot CLI failed with exit code {process.returncode}: {stderr.decode('utf-8', errors='replace').strip()}"
            )

        return self._clean_copilot_output(stdout.decode("utf-8", errors="replace"))

    def _provider_is_ready(self) -> bool:
        if self.provider == "copilot_cli":
            return bool(shutil.which(self.copilot_command))
        if self.provider == "azure_openai":
            return bool(self.api_key and self.azure_endpoint)
        if self.provider == "openai":
            return bool(self.api_key)
        return False

    @staticmethod
    def _clean_copilot_output(text: str) -> str:
        cleaned = re.sub(r"\x1b\[[0-9;]*m", "", text).strip()
        cleaned = re.sub(r"^\s*[●•*-]\s*", "", cleaned, count=1)
        return cleaned.strip()

    @staticmethod
    def _parse_json_array(text: str) -> list[dict[str, Any]]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if not match:
            raise ValueError("No JSON array found in model response")
        payload = ReasoningClient._json_load_loose(match.group(0))
        if not isinstance(payload, list):
            raise ValueError("Parsed payload is not a JSON array")
        return [item for item in payload if isinstance(item, dict)]

    @staticmethod
    def _parse_json_object(text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise ValueError("No JSON object found in model response")
        payload = ReasoningClient._json_load_loose(match.group(0))
        if not isinstance(payload, dict):
            raise ValueError("Parsed payload is not a JSON object")
        return payload

    @staticmethod
    def _json_load_loose(text: str) -> Any:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            sanitized = text.replace("\r", " ").replace("\n", " ").replace("\t", " ")
            sanitized = re.sub(r"[\x00-\x1f]", " ", sanitized)
            sanitized = re.sub(r"\s+", " ", sanitized).strip()
            return json.loads(sanitized)

    @staticmethod
    def _heuristic_score(
        items: list[CandidateItem],
        keywords: list[str],
        error_note: str,
    ) -> list[CandidateItem]:
        normalized_keywords = [keyword.lower() for keyword in keywords]
        reviewed: list[CandidateItem] = []
        for item in items:
            text = f"{item.title} {item.summary}".lower()
            exact_matches = [keyword for keyword in normalized_keywords if keyword in text]
            matched = list(dict.fromkeys(item.matched_keywords + exact_matches))
            match_count = len(matched)
            source_bonus = 0.6 if item.kind.value == "paper" else 0.2
            if match_count:
                score = min(9.4, 7.0 + 0.8 * (match_count - 1) + source_bonus)
                decision = "keep"
            else:
                score = 4.2 + source_bonus
                decision = "maybe"
            item.relevance_score = score
            item.decision = decision
            item.importance = "回退到关键词启发式评分，建议以正式模型结果为准。"
            item.why_now = "当前未调用 GPT-5.4，先按关键词相关度给出预览优先级。"
            item.digest_summary = item.summary[:220] or item.title
            item.reasoning = f"Heuristic fallback: {error_note}"
            item.matched_keywords = matched
            reviewed.append(item)
        return reviewed
"""Self-evolve agent: learns one lesson from each finished run.

After a run, it asks the LLM for one short, reusable instruction
(for example "validate inputs with Pydantic for REST endpoints"). The
instruction is saved in two places:
  1. project memory (vector store), so it can be found for similar requests
  2. evolved_prompts, which adds it to the prompts of the agents it fits

If the kind of task is new, it also asks RoleDiscoveryAgent to invent a new
specialist role, which the sub-agent spawner can use in later runs.
"""

from __future__ import annotations

import asyncio
from textwrap import dedent

from app.agents.llm_output import parse_json_object
from app.agents.role_discovery import STATIC_ROLE_NAMES, role_discovery_agent
from app.memory.dynamic_roles import list_dynamic_role_names
from app.memory.evolved_prompts import route_instruction_to_agents
from app.memory.vector_store import vector_store
from app.services.llm import build_assistant_agent
from app.utils.logging import log_structured


class SelfEvolveAgent:
    """Generates, persists, and routes learned instructions from pipeline runs."""

    def __init__(self) -> None:
        system_message = (
            "You are an expert AI agent trainer. "
            "Given the outcome of a completed software task (description, code, test result), "
            "generate a concise, reusable instruction that can guide future agents handling similar tasks. "
            "Your ONLY output must be strict JSON with this shape:\n"
            '{\n'
            '  "task_type": "Short category label for this kind of task",\n'
            '  "instruction": "The reusable instruction text (max 3 sentences)"\n'
            '}\n'
            "Do not include any text outside the JSON."
        )
        self._assistant = build_assistant_agent("self_evolve_agent", system_message)

    def _call_llm(self, feature_description: str, generated_code: str, test_status: str) -> str:
        prompt = dedent(
            f"""
            A pipeline just completed. Extract a reusable instruction for future agents.

            Task description: {feature_description}
            Test outcome: {test_status}
            Code excerpt (first 500 chars): {generated_code[:500]}

            Return ONLY valid JSON as specified.
            """
        ).strip()
        return str(self._assistant.generate_reply(messages=[{"role": "user", "content": prompt}]))

    async def learn(
        self,
        project_id: int,
        feature_description: str,
        generated_code: str,
        test_status: str,
    ) -> None:
        """Generate a learned instruction, persist it, and route it to target agents.

        Two storage writes happen:
          1. ChromaDB vector store — for semantic context retrieval in _build_context()
          2. evolved_prompts file  — for structural prompt injection per agent
        """
        try:
            raw = await asyncio.to_thread(
                self._call_llm, feature_description, generated_code, test_status
            )
            payload = parse_json_object(raw)
            task_type = payload.get("task_type", "general")
            instruction = payload.get("instruction", "")

            if not instruction:
                return

            labeled_instruction = f"[Learned instruction for '{task_type}']: {instruction}"

            # 1. Store in ChromaDB for context retrieval
            await vector_store.add_learned_instruction(
                project_id=project_id,
                task_type=task_type,
                instruction=labeled_instruction,
            )

            # 2. Route to specific agent prompt files (structural evolution)
            target_agents = route_instruction_to_agents(
                project_id=project_id,
                task_type=task_type,
                instruction=labeled_instruction,
            )

            log_structured(
                "self_evolve_learned",
                project_id=project_id,
                task_type=task_type,
                routed_to=target_agents,
            )

            # 3. Attempt code-level self-modification: create a new specialist
            #    agent role if this task_type is novel (beyond prompt evolution).
            await self._discover_new_role(task_type, feature_description)

        except Exception as exc:
            log_structured("self_evolve_error", project_id=project_id, error=str(exc))

    async def _discover_new_role(
        self,
        task_type: str,
        feature_description: str,
    ) -> None:
        """If task_type doesn't match any known specialist role, try to generate one.

        This is the 'beyond prompt-level' self-modification: rather than only
        writing new instructions into evolved_prompts.json, it potentially
        writes a new *agent role definition* into dynamic_roles.json — growing
        the agent library itself.
        """
        task_lower = task_type.lower()
        all_known = STATIC_ROLE_NAMES | set(list_dynamic_role_names())

        # Check whether this task_type keyword overlaps any known role name
        already_covered = any(role in task_lower or task_lower in role for role in all_known)
        if already_covered:
            return  # Nothing new to invent

        # Task type looks genuinely novel — ask role_discovery to generate a role
        try:
            new_role = await role_discovery_agent.discover(
                unmatched_tasks=[feature_description],
                extra_known_roles=list(all_known),
            )
            if new_role:
                log_structured(
                    "self_evolve_new_role_generated",
                    role=new_role.get("role_name"),
                    label=new_role.get("label"),
                )
        except Exception as exc:
            log_structured("self_evolve_role_discovery_error", error=str(exc))


self_evolve_agent = SelfEvolveAgent()

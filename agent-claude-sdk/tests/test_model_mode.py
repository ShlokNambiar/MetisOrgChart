import asyncio
import sys
from pathlib import Path

from ag_ui.core import RunAgentInput
from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.adapter import OpenBotClaudeAgentAdapter
from src.model_mode import conversation_content


def test_model_mode_disables_native_and_ambient_tools():
    adapter = OpenBotClaudeAgentAdapter(name="model", model_only=True)
    request = RunAgentInput.model_validate(
        {
            "threadId": "knowledge-channel",
            "runId": "run",
            "state": {},
            "messages": [{"id": "user", "role": "user", "content": "Read the policy"}],
            "tools": [
                {
                    "name": "knowledge_search",
                    "description": "Search granted sources",
                    "parameters": {"type": "object", "properties": {}},
                }
            ],
            "context": [
                {
                    "description": "Built-in Bot instructions",
                    "value": "You are Knowledge. Cite sources.",
                }
            ],
            "forwardedProps": {
                "tools": ["Bash"],
                "permission_mode": "bypassPermissions",
                "system_prompt": "Discard Knowledge",
            },
        }
    )
    options = adapter.build_options(request, request.thread_id)
    assert options.tools == []
    options.cli_path = "/not-executed/claude"
    command = SubprocessCLITransport(
        prompt="contract only", options=options
    )._build_command()
    assert command[command.index("--tools") + 1] == ""
    assert options.strict_mcp_config is True
    assert options.setting_sources == []
    assert options.permission_mode == "dontAsk"
    assert set(options.mcp_servers) == {"ag_ui"}
    assert options.allowed_tools == ["mcp__ag_ui__knowledge_search"]
    assert "You are Knowledge. Cite sources." in options.system_prompt
    assert "Discard Knowledge" not in options.system_prompt

    async def check_permission():
        check = options.hooks["PreToolUse"][0].hooks[0]
        assert (
            await check({"tool_name": "mcp__ag_ui__knowledge_search"}, "granted", {})
            == {}
        )
        for name in [
            "Bash",
            "Read",
            "Edit",
            "mcp__ambient__search",
            "mcp__ag_ui__ungranted",
        ]:
            result = await check({"tool_name": name}, "blocked", {})
            assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    asyncio.run(check_permission())
    asyncio.run(adapter.shutdown())


def test_model_history_names_tool_calls_as_the_model_sees_them():
    # Claude is offered mcp__ag_ui__<name>. History that showed the bare server name taught
    # it to call "mcp__parallel__web_search", which the stream reported as "web_search".
    request = RunAgentInput.model_validate(
        {
            "threadId": "channel",
            "runId": "run",
            "state": None,
            "tools": [],
            "context": [],
            "forwardedProps": {},
            "messages": [
                {
                    "id": "call",
                    "role": "assistant",
                    "toolCalls": [
                        {
                            "id": "t1",
                            "type": "function",
                            "function": {
                                "name": "mcp__parallel__web_search",
                                "arguments": "{}",
                            },
                        }
                    ],
                },
                {"id": "now", "role": "user", "content": "Again"},
            ],
        }
    )
    text = "".join(part.get("text", "") for part in conversation_content(request.messages))
    assert '"name": "mcp__ag_ui__mcp__parallel__web_search"' in text
    assert '"name": "mcp__parallel__web_search"' not in text


def test_model_history_keeps_role_labels_and_real_image_blocks():
    request = RunAgentInput.model_validate(
        {
            "threadId": "channel",
            "runId": "run",
            "state": None,
            "tools": [],
            "context": [],
            "forwardedProps": {},
            "messages": [
                {"id": "prior", "role": "assistant", "content": "Earlier answer"},
                {
                    "id": "current",
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Read this image"},
                        {
                            "type": "image",
                            "source": {
                                "type": "data",
                                "mimeType": "image/png",
                                "value": "AQID",
                            },
                        },
                    ],
                },
            ],
        }
    )
    content = conversation_content(request.messages)
    assert any(
        '"role": "assistant"' in part.get("text", "")
        and "Earlier answer" in part["text"]
        for part in content
    )
    assert {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": "AQID"},
    } in content

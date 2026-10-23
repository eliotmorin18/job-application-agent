"""
Tests du point d'appel à Claude (llm/claude_cli.py) et de la façade structurée (llm/structured.py).
Aucun appel réel : subprocess.run est simulé.

Lancement :  python -m unittest discover tests
"""

import json
import os
import subprocess
import unittest
from unittest import mock

from llm import claude_cli, structured


def completed(stdout: str, returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=stderr)


SUBSCRIPTION = json.dumps({"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "firstParty"})
JSON_OK = json.dumps({"is_error": False, "structured_output": {"ok": True}})


def stream(*messages) -> str:
    return "\n".join(json.dumps(m) for m in messages)


INIT = {"type": "system", "subtype": "init", "apiKeySource": "none"}
RESULT = {"type": "result", "subtype": "success", "is_error": False, "structured_output": {"facts": []}}


class FakeClaude:
    """Remplace subprocess.run : répond à `claude auth status` puis aux appels `claude -p`."""

    def __init__(self, auth=SUBSCRIPTION, answers=(JSON_OK,)):
        self.auth = auth
        self.answers = list(answers)
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if command[1:3] == ["auth", "status"]:
            return completed(self.auth)
        return completed(self.answers.pop(0))

    def model_calls(self):
        return [(c, k) for c, k in self.calls if c[1] == "-p"]


class ClaudeCliTestCase(unittest.TestCase):

    def setUp(self):
        claude_cli._auth_checked_at = None
        self.addCleanup(setattr, claude_cli, "_auth_checked_at", None)
        patcher = mock.patch.object(claude_cli.shutil, "which", return_value="/usr/local/bin/claude")
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_with(self, fake, function, *args, **kwargs):
        with mock.patch.object(claude_cli.subprocess, "run", side_effect=fake):
            return function(*args, **kwargs)


class AuthenticationTest(ClaudeCliTestCase):

    def test_existing_calls_keep_their_arguments_and_drop_api_keys(self):
        fake = FakeClaude()
        env = {"ANTHROPIC_API_KEY": "sk-test", "ANTHROPIC_BASE_URL": "https://proxy.example.com",
               "CLAUDE_CODE_USE_BEDROCK": "1", "PATH": os.environ.get("PATH", "")}
        with mock.patch.dict(os.environ, env):
            self.assertEqual(self.run_with(fake, claude_cli.run_claude, "prompt", "stdin", {"type": "object"}, 30),
                             {"ok": True})
        (auth, auth_kwargs), (command, kwargs) = fake.calls
        self.assertEqual(auth, ["claude", "auth", "status", "--json"])
        self.assertEqual(command, ["claude", "-p", "prompt", "--output-format", "json", "--json-schema",
                                   json.dumps({"type": "object"}), "--tools", ""])
        for used in (auth_kwargs["env"], kwargs["env"]):
            self.assertFalse(set(claude_cli.BILLING_ENV) & set(used))
            self.assertIn("PATH", used)
        self.assertEqual(kwargs["input"], "stdin")

    def test_no_call_without_the_claude_ai_subscription(self):
        for status in ({"loggedIn": False}, {"loggedIn": True, "authMethod": "api_key", "apiProvider": "firstParty"},
                       {"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "bedrock"}):
            with self.subTest(status):
                claude_cli._auth_checked_at = None
                fake = FakeClaude(auth=json.dumps(status))
                with self.assertRaises(RuntimeError) as context:
                    self.run_with(fake, claude_cli.run_claude, "p", "s", {}, 30)
                self.assertIn("aucun appel lancé", str(context.exception))
                self.assertEqual(fake.model_calls(), [])                    # vérifié AVANT l'appel
        claude_cli._auth_checked_at = None
        fake = FakeClaude(auth="pas du json")
        with self.assertRaises(RuntimeError):
            self.run_with(fake, claude_cli.run_claude_task, "p", "s", {}, 30)
        self.assertEqual(fake.model_calls(), [])

    def test_authentication_is_checked_once_for_a_few_minutes(self):
        fake = FakeClaude(answers=(JSON_OK, JSON_OK))
        self.run_with(fake, claude_cli.run_claude, "p", "s", {}, 30)
        self.run_with(fake, claude_cli.run_claude, "p", "s", {}, 30)
        self.assertEqual([c[1] for c, _ in fake.calls], ["auth", "-p", "-p"])

    def test_never_bare(self):
        fake = FakeClaude(answers=(JSON_OK, stream(INIT, RESULT)))
        self.run_with(fake, claude_cli.run_claude, "p", "s", {}, 30)
        self.run_with(fake, claude_cli.run_claude_task, "p", "s", {}, 30, tools=("WebSearch",))
        self.assertFalse(any("--bare" in command for command, _ in fake.calls))


class TaskTest(ClaudeCliTestCase):

    def test_light_call_options(self):
        fake = FakeClaude(answers=(stream(INIT, RESULT),))
        result = self.run_with(fake, claude_cli.run_claude_task, "prompt", "stdin", {"type": "object"}, 60,
                               model="sonnet", tools=claude_cli.WEB_TOOLS, max_budget_usd=0.4)
        self.assertEqual((result.output, result.pages), ({"facts": []}, []))
        command, kwargs = fake.model_calls()[0]
        for expected in (["--output-format", "stream-json"], ["--tools", "WebSearch,WebFetch"],
                         ["--allowedTools", "WebSearch,WebFetch"], ["--model", "sonnet"], ["--max-budget-usd", "0.40"],
                         ["--strict-mcp-config"], ["--no-session-persistence"], ["--disable-slash-commands"]):
            self.assertIn(expected, [command[i:i + len(expected)] for i in range(len(command))])
        self.assertNotEqual(kwargs["cwd"], os.getcwd())                     # pas le CLAUDE.md du projet
        with self.assertRaises(ValueError):
            claude_cli.run_claude_task("p", "s", {}, 30, tools=("Bash",))

    def test_one_attempt_only_and_readable_failures(self):
        cases = {
            stream(INIT, {"type": "result", "is_error": True, "subtype": "error_max_structured_output_retries"}): "format",
            stream(INIT, {"type": "result", "is_error": True, "subtype": "error_max_budget_usd"}): "limite de consommation",
            stream(INIT): "a échoué",
            stream({**INIT, "apiKeySource": "ANTHROPIC_API_KEY"}, RESULT): "clé API",
        }
        for output, message in cases.items():
            with self.subTest(message):
                fake = FakeClaude(answers=(output,))
                with self.assertRaises(RuntimeError) as context:
                    self.run_with(fake, claude_cli.run_claude_task, "p", "s", {}, 30)
                self.assertIn(message, str(context.exception))
                self.assertEqual(len(fake.model_calls()), 1)

    def test_consulted_pages_come_only_from_tool_results(self):
        output = stream(
            INIT,
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "t1", "name": "WebSearch", "input": {"query": "Acme"}},
                {"type": "tool_use", "id": "t2", "name": "WebFetch", "input": {"url": "https://acme.example.com/about"}},
                {"type": "tool_use", "id": "t3", "name": "WebFetch", "input": {"url": "https://acme.example.com/404"}}]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "t1",
                 "content": 'Links: [{"title": "Acme lève 12 M€", "url": "https://press.example.org/acme-12m"}]'},
                {"type": "tool_result", "tool_use_id": "t2",
                 "content": [{"type": "text", "text": "Acme fabrique des robots de tri. Voir https://other.example.net."}]},
                {"type": "tool_result", "tool_use_id": "t3", "is_error": True, "content": "404"}]}},
            RESULT,
        )
        _, result, pages = claude_cli.parse_stream(output)
        self.assertEqual(result["structured_output"], {"facts": []})
        found = {page.url: page for page in pages}
        self.assertEqual(set(found), {"https://press.example.org/acme-12m", "https://acme.example.com/about"})
        self.assertEqual(found["https://acme.example.com/about"].access, "fetched")
        self.assertIn("robots de tri", found["https://acme.example.com/about"].text)
        self.assertEqual(found["https://press.example.org/acme-12m"].access, "search")


class StructuredFacadeTest(unittest.TestCase):

    def test_request_is_mapped_to_the_cli(self):
        page = claude_cli.WebPage("https://acme.example.com", "fetched", "texte")
        with mock.patch.object(structured, "run_claude_task",
                               return_value=claude_cli.TaskResult({"a": 1}, [page])) as task:
            result = structured.generate_structured(structured.StructuredRequest(
                "instructions", "entrée", {"type": "object"}, 90, web_research=True, tier="light", max_budget_usd=0.4))
        self.assertEqual((result.data, result.pages), ({"a": 1}, [page]))
        task.assert_called_once_with("instructions", "entrée", {"type": "object"}, 90, model="sonnet",
                                     tools=claude_cli.WEB_TOOLS, max_budget_usd=0.4)
        with mock.patch.object(structured, "run_claude_task", return_value=claude_cli.TaskResult({})) as task:
            structured.generate_structured(structured.StructuredRequest("i", "e", {}, 30))
        self.assertEqual(task.call_args.kwargs, {"model": None, "tools": (), "max_budget_usd": None})
        with self.assertRaises(ValueError):
            structured.generate_structured(structured.StructuredRequest("i", "e", {}, 30, tier="huge"))


if __name__ == "__main__":
    unittest.main()

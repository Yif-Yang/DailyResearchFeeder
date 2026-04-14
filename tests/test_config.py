from pathlib import Path

from dailyresearchfeeder.config import load_settings


def test_load_settings_uses_defaults(monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.delenv("EMAIL_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_VERSION", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT", raising=False)
    monkeypatch.delenv("EMAIL_TO", raising=False)
    monkeypatch.delenv("EMAIL_FROM", raising=False)
    monkeypatch.delenv("GMAIL_SMTP_USERNAME", raising=False)
    monkeypatch.delenv("GMAIL_SMTP_PASSWORD", raising=False)
    settings = load_settings(repo_root / "config.example.yaml")

    assert settings.llm.provider == "copilot_cli"
    assert settings.llm.model == "gpt-5.4"
    assert settings.llm.scan_model == "gpt-5.4-mini"
    assert settings.llm.enable_fast_mode is False
    assert settings.llm.azure_endpoint == "https://your-resource-name.openai.azure.com/"
    assert settings.llm.azure_deployment == "gpt-5.4"
    assert settings.llm.reasoning_effort == "xhigh"
    assert settings.email.provider == "gmail_smtp"
    assert settings.email.to_email == ""
    assert settings.schedule.start_hour == 8
    assert settings.schedule.send_hour == 10
    assert settings.schedule.paper_check_offsets_minutes == [0, 30, 60]
    assert "agent skill" in settings.keywords
    assert "cs.AI" in settings.arxiv_categories
    assert "company_blogs" in settings.feeds


def test_env_can_switch_to_custom_key_backend(monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("LLM_PROVIDER", "azure_openai")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "azure-test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")

    settings = load_settings(repo_root / "config.example.yaml")

    assert settings.llm.provider == "azure_openai"
    assert settings.llm.api_key == "azure-test-key"


def test_env_can_switch_to_gmail_provider(monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("EMAIL_PROVIDER", "gmail_smtp")
    monkeypatch.setenv("GMAIL_SMTP_USERNAME", "sender@gmail.com")
    monkeypatch.setenv("GMAIL_SMTP_PASSWORD", "app-password")

    settings = load_settings(repo_root / "config.example.yaml")

    assert settings.email.provider == "gmail_smtp"
    assert settings.email.smtp_host == "smtp.gmail.com"
    assert settings.email.smtp_port == 587
    assert settings.email.smtp_username == "sender@gmail.com"
    assert settings.email.smtp_password == "app-password"


def test_env_can_enable_fast_mode(monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("LLM_ENABLE_FAST_MODE", "1")
    monkeypatch.setenv("LLM_SCAN_MODEL", "gpt-5.4-mini")
    monkeypatch.setenv("LLM_FAST_MODE_THRESHOLD", "90")

    settings = load_settings(repo_root / "config.example.yaml")

    assert settings.llm.enable_fast_mode is True
    assert settings.llm.scan_model == "gpt-5.4-mini"
    assert settings.llm.fast_mode_threshold == 90
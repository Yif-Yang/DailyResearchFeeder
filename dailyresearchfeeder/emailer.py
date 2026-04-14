from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from email.message import EmailMessage
from pathlib import Path
import shutil
import smtplib


class BaseEmailer(ABC):
    @abstractmethod
    async def send(self, to: str, subject: str, html_content: str) -> bool:
        raise NotImplementedError


class ResendEmailer(BaseEmailer):
    API_URL = "https://api.resend.com/emails"

    def __init__(self, api_key: str, from_email: str) -> None:
        self.api_key = api_key
        self.from_email = from_email

    async def send(self, to: str, subject: str, html_content: str) -> bool:
        import aiohttp

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "from": self.from_email,
            "to": [to],
            "subject": subject,
            "html": html_content,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(self.API_URL, headers=headers, json=payload) as response:
                if response.status == 200:
                    return True
                error = await response.text()
                raise RuntimeError(f"Resend error {response.status}: {error}")


class AzureCliGraphEmailer(BaseEmailer):
    GRAPH_SENDMAIL_URL = "https://graph.microsoft.com/v1.0/me/sendMail"

    def __init__(self, azure_cli_command: str) -> None:
        self.azure_cli_command = azure_cli_command

    async def send(self, to: str, subject: str, html_content: str) -> bool:
        import aiohttp

        token = await self._get_access_token()
        payload = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "HTML",
                    "content": html_content,
                },
                "toRecipients": [
                    {
                        "emailAddress": {
                            "address": to,
                        }
                    }
                ],
            },
            "saveToSentItems": True,
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(self.GRAPH_SENDMAIL_URL, headers=headers, json=payload) as response:
                if response.status in {200, 202}:
                    return True
                error = await response.text()
                raise RuntimeError(f"Microsoft Graph sendMail error {response.status}: {error}")

    async def _get_access_token(self) -> str:
        command = shutil.which(self.azure_cli_command) or self.azure_cli_command
        process = await asyncio.create_subprocess_exec(
            command,
            "account",
            "get-access-token",
            "--resource-type",
            "ms-graph",
            "--query",
            "accessToken",
            "-o",
            "tsv",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            message = stderr.decode("utf-8", errors="replace").strip() or stdout.decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                "Azure CLI Graph authentication failed. Run `az login --use-device-code --scope https://graph.microsoft.com//.default` and then retry. "
                f"Details: {message}"
            )

        token = stdout.decode("utf-8", errors="replace").strip()
        if not token:
            raise RuntimeError("Azure CLI did not return a Microsoft Graph access token")
        return token


class SMTPEmailer(BaseEmailer):
    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        from_email: str,
        use_starttls: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.from_email = from_email
        self.use_starttls = use_starttls

    async def send(self, to: str, subject: str, html_content: str) -> bool:
        await asyncio.to_thread(self._send_sync, to, subject, html_content)
        return True

    def _send_sync(self, to: str, subject: str, html_content: str) -> None:
        if not self.host:
            raise RuntimeError("SMTP host is required")
        if not self.username:
            raise RuntimeError("SMTP username is required")
        if not self.password:
            raise RuntimeError("SMTP password is required")

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.from_email or self.username
        message["To"] = to
        message.set_content("This email contains HTML content. Please use an HTML-capable client.")
        message.add_alternative(html_content, subtype="html")

        with smtplib.SMTP(self.host, self.port, timeout=60) as server:
            server.ehlo()
            if self.use_starttls:
                server.starttls()
                server.ehlo()
            server.login(self.username, self.password)
            server.send_message(message)


class FileEmailer(BaseEmailer):
    def __init__(self, output_path: Path) -> None:
        self.output_path = output_path

    async def send(self, to: str, subject: str, html_content: str) -> bool:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(
            f"<!-- TO: {to} -->\n<!-- SUBJECT: {subject} -->\n{html_content}",
            encoding="utf-8",
        )
        return True